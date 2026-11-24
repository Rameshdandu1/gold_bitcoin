import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from marketintel.config import Settings
from marketintel.delta import DeltaAPIError, parse_trade_message
from marketintel.detectors import EngineConfig
from marketintel.models import CandidateSignal, Candle, DetectionResult, Instrument, SignalState
from marketintel.quantitative import QUANT_ENGINE_BY_ID, lifecycle_event
from marketintel.storage import Store
from marketintel.worker import main as worker_main
from marketintel.worker import poll_closed_candles, public_market_stream


def trade_event(when: datetime, price: str = "100"):
    event_micros = int(when.timestamp() * 1_000_000)
    message = {
        "type": "trades",
        "sy": "BTCUSD",
        "p": price,
        "s": "1",
        "r": "t",
        "t": event_micros,
        "ts": event_micros + 1_000,
    }
    return parse_trade_message(message, received_at=when + timedelta(milliseconds=2))[0]


def persist_active_btc_candidate(store: Store, now: datetime) -> CandidateSignal:
    candidate = CandidateSignal(
        candidate_id="m2-active-btc-fixture-0001",
        snapshot_id="b" * 64,
        asset="BTC",
        symbol="BTCUSD",
        engine="BTC_FAST",
        horizon_minutes=30,
        candle_close_utc=now - timedelta(minutes=1),
        observed_at_utc=now - timedelta(minutes=1),
        expires_at_utc=now + timedelta(minutes=29),
        direction="BULLISH",
        trigger="TEST_FIXTURE_NOT_LIVE",
        entry=70000,
        invalidation=69000,
        targets=[71000],
        feature_evidence=["TEST_FIXTURE_NOT_LIVE"],
        rule_version="m2-v1",
    )
    initial = lifecycle_event(
        candidate_id=candidate.candidate_id,
        snapshot_id=candidate.snapshot_id,
        from_state=None,
        to_state=SignalState.CANDIDATE,
        occurred_at=candidate.observed_at_utc,
        reason="TEST_FIXTURE_NOT_LIVE candidate emitted",
    )
    assert store.add_candidate_with_lifecycle(candidate, initial)
    return candidate


@pytest.mark.asyncio
async def test_public_stream_persists_once_and_archives_connection_transitions(
    tmp_path, monkeypatch
):
    event = trade_event(datetime.now(UTC))

    class FakeStream:
        def __init__(self, _url, _symbols, *, status_callback, **_kwargs):
            self.status_callback = status_callback
            self.last_seen_utc = event.received_at_utc

        async def messages(self):
            self.status_callback("CONNECTING", "fixture connect")
            self.status_callback("CONNECTED", "fixture event")
            yield event
            yield event

        def book_quality(self, _symbol, *, now=None):
            return False, "snapshot_required"

        def mark_stale(self, detail):
            self.status_callback("STALE", detail)

    monkeypatch.setattr("marketintel.worker.DeltaPublicStream", FakeStream)
    store = Store(tmp_path / "market.sqlite3")
    settings = Settings(database_path=tmp_path / "market.sqlite3")

    await public_market_stream(settings, store, ["BTCUSD"])

    assert len(store.raw_events(symbol="BTCUSD")) == 1
    assert [row["state"] for row in store.source_status_history("delta_websocket")] == [
        "CONNECTING",
        "CONNECTED",
    ]


@pytest.mark.asyncio
async def test_public_stream_batches_persistence_without_blocking_each_received_frame(
    tmp_path, monkeypatch
):
    events = [
        trade_event(datetime.now(UTC) + timedelta(microseconds=index), str(100 + index))
        for index in range(24)
    ]

    class FakeStream:
        def __init__(self, _url, _symbols, *, status_callback, **_kwargs):
            self.status_callback = status_callback
            self.last_seen_utc = events[-1].received_at_utc
            self.books = {}

        async def messages(self):
            self.status_callback("CONNECTING", "fixture connect")
            self.status_callback("CONNECTED", "fixture event")
            for event in events:
                yield event

        def book_quality(self, _symbol, *, now=None):
            return False, "snapshot_required"

        def mark_stale(self, detail):
            self.status_callback("STALE", detail)

    monkeypatch.setattr("marketintel.worker.DeltaPublicStream", FakeStream)
    store = Store(tmp_path / "market.sqlite3")
    batch_sizes: list[int] = []
    original_batch = store.append_raw_events

    def forbid_single_event_writes(_event):
        raise AssertionError("the receive loop must not synchronously persist one frame at a time")

    def observe_batch(events_to_store):
        batch_sizes.append(len(events_to_store))
        return original_batch(events_to_store)

    monkeypatch.setattr(store, "append_raw_event", forbid_single_event_writes)
    monkeypatch.setattr(store, "append_raw_events", observe_batch)
    settings = Settings(database_path=tmp_path / "market.sqlite3")

    await public_market_stream(settings, store, ["BTCUSD"])

    assert len(store.raw_events(symbol="BTCUSD")) == len(events)
    assert max(batch_sizes) > 1


@pytest.mark.asyncio
async def test_book_monitor_uses_each_symbols_current_observation_clock(tmp_path, monkeypatch):
    """A frame received while the previous symbol persists is not future evidence."""
    stream_holder = {}

    class FakeStream:
        def __init__(self, _url, _symbols, *, status_callback, **_kwargs):
            self.status_callback = status_callback
            self.last_seen_utc = datetime.now(UTC)
            self.xaut_received_at = self.last_seen_utc
            self.books = {}
            stream_holder["stream"] = self

        async def messages(self):
            self.status_callback("CONNECTED", "fixture event")
            await asyncio.sleep(0.7)
            if False:
                yield trade_event(self.last_seen_utc)

        def book_quality(self, symbol, *, now=None):
            if symbol == "BTCUSD":
                return False, "snapshot_required"
            if now < self.xaut_received_at:
                return False, "received_after_evaluation_clock"
            return True, "valid"

        def mark_stale(self, detail):
            self.status_callback("STALE", detail)

    monkeypatch.setattr("marketintel.worker.DeltaPublicStream", FakeStream)
    store = Store(tmp_path / "market.sqlite3")
    original_status = store.record_source_status

    def record_status(source, state, detail="", **kwargs):
        if source == "delta_book:BTCUSD":
            stream_holder["stream"].xaut_received_at = datetime.now(UTC)
        return original_status(source, state, detail, **kwargs)

    monkeypatch.setattr(store, "record_source_status", record_status)
    settings = Settings(database_path=tmp_path / "market.sqlite3", delta_book_max_age_seconds=1)

    await public_market_stream(settings, store, ["BTCUSD", "XAUTUSD"])

    xaut = store.source_status_history("delta_book:XAUTUSD")
    assert xaut[-1]["state"] == "VALID"
    assert xaut[-1]["detail"] == "valid"


@pytest.mark.asyncio
async def test_worker_reconciles_closed_trade_candle_and_persists_valid_status(
    tmp_path, monkeypatch
):
    now = datetime.now(UTC)
    open_time = now.replace(second=0, microsecond=0) - timedelta(minutes=2)
    event = trade_event(open_time + timedelta(seconds=5))
    store = Store(tmp_path / "market.sqlite3")
    store.record_source_status(
        "delta_websocket",
        "CONNECTED",
        "TEST_FIXTURE_NOT_LIVE",
        occurred_at=open_time - timedelta(seconds=1),
    )
    store.append_raw_event(event)
    candle = Candle(
        symbol="BTCUSD",
        resolution="1m",
        open_time=open_time,
        open=100,
        high=100,
        low=100,
        close=100,
        volume_contracts=1,
    )

    class FakeREST:
        def __init__(self, _url):
            pass

        async def historical_candles(self, *_args, **_kwargs):
            return [candle]

    async def stop_after_iteration(_delay):
        raise asyncio.CancelledError

    monkeypatch.setattr("marketintel.worker.DeltaREST", FakeREST)
    monkeypatch.setattr("marketintel.worker.ENGINE_CONFIGS", (EngineConfig("BTC", "1m", 30),))
    monkeypatch.setattr("marketintel.worker.asyncio.sleep", stop_after_iteration)
    settings = Settings(database_path=tmp_path / "market.sqlite3")

    with pytest.raises(asyncio.CancelledError):
        await poll_closed_candles(settings, store, {"BTC": "BTCUSD"})

    history = store.source_status_history("candle_reconciliation:BTCUSD")
    assert history[-1]["state"] == "VALID"
    assert "matched=1" in history[-1]["detail"]
    assert store.source_status_history("delta_rest:BTCUSD:1m")[-1]["state"] == "AVAILABLE"


@pytest.mark.asyncio
async def test_reconciliation_uses_complete_contiguous_suffix_after_reconnect(
    tmp_path, monkeypatch
):
    now = datetime.now(UTC).replace(second=20, microsecond=0)
    early_open = now.replace(second=0) - timedelta(minutes=4)
    late_open = early_open + timedelta(minutes=2)
    store = Store(tmp_path / "market.sqlite3")
    store.record_source_status(
        "delta_websocket",
        "CONNECTED",
        "initial fixture connection",
        occurred_at=early_open - timedelta(seconds=1),
    )
    store.record_source_status(
        "delta_websocket",
        "DISCONNECTED",
        "fixture reconnect boundary",
        occurred_at=early_open + timedelta(seconds=30),
    )
    store.record_source_status(
        "delta_websocket",
        "CONNECTED",
        "fixture recovered",
        occurred_at=early_open + timedelta(seconds=45),
    )
    store.append_raw_events(
        [
            trade_event(early_open + timedelta(seconds=5)),
            trade_event(late_open + timedelta(seconds=5)),
        ]
    )
    candles = [
        Candle(
            symbol="BTCUSD",
            resolution="1m",
            open_time=open_time,
            open=100,
            high=100,
            low=100,
            close=100,
            volume_contracts=1,
        )
        for open_time in (early_open, late_open)
    ]

    class FakeREST:
        def __init__(self, _url):
            pass

        async def historical_candles(self, *_args, **_kwargs):
            return candles

    async def stop_after_iteration(_delay):
        raise asyncio.CancelledError

    monkeypatch.setattr("marketintel.worker.DeltaREST", FakeREST)
    monkeypatch.setattr("marketintel.worker.ENGINE_CONFIGS", (EngineConfig("BTC", "1m", 30),))
    monkeypatch.setattr("marketintel.worker.asyncio.sleep", stop_after_iteration)

    with pytest.raises(asyncio.CancelledError):
        await poll_closed_candles(
            Settings(database_path=tmp_path / "market.sqlite3"), store, {"BTC": "BTCUSD"}
        )

    status = store.source_status_history("candle_reconciliation:BTCUSD")[-1]
    assert status["state"] == "VALID"
    assert "matched=1" in status["detail"]
    assert f"coverage_start={late_open.isoformat()}" in status["detail"]


@pytest.mark.asyncio
async def test_worker_archives_rest_outage_as_unavailable(tmp_path, monkeypatch):
    class FailingREST:
        def __init__(self, _url):
            pass

        async def historical_candles(self, *_args, **_kwargs):
            raise DeltaAPIError("fixture outage")

    async def stop_after_iteration(_delay):
        raise asyncio.CancelledError

    monkeypatch.setattr("marketintel.worker.DeltaREST", FailingREST)
    monkeypatch.setattr("marketintel.worker.ENGINE_CONFIGS", (EngineConfig("BTC", "1m", 30),))
    monkeypatch.setattr("marketintel.worker.asyncio.sleep", stop_after_iteration)
    store = Store(tmp_path / "market.sqlite3")
    settings = Settings(database_path=tmp_path / "market.sqlite3")

    with pytest.raises(asyncio.CancelledError):
        await poll_closed_candles(settings, store, {"BTC": "BTCUSD"})

    history = store.source_status_history("delta_rest:BTCUSD:1m")
    assert history[-1]["state"] == "UNAVAILABLE"
    assert history[-1]["detail"] == "DeltaAPIError"


@pytest.mark.asyncio
async def test_quant_candidate_invalidates_when_instrument_disappears(tmp_path, monkeypatch):
    now = datetime.now(UTC)
    store = Store(tmp_path / "market.sqlite3")
    candidate = persist_active_btc_candidate(store, now)
    store.record_source_status(
        "product_discovery:BTC", "AVAILABLE", "TEST_FIXTURE_NOT_LIVE", occurred_at=now
    )

    async def stop_after_iteration(_delay):
        raise asyncio.CancelledError

    monkeypatch.setattr("marketintel.worker.ENGINE_CONFIGS", (QUANT_ENGINE_BY_ID["BTC_FAST"],))
    monkeypatch.setattr("marketintel.worker.asyncio.sleep", stop_after_iteration)
    settings = Settings(database_path=tmp_path / "market.sqlite3")

    with pytest.raises(asyncio.CancelledError):
        await poll_closed_candles(settings, store, {})

    lifecycle = store.candidate_lifecycle(candidate.candidate_id)
    assert [event.to_state for event in lifecycle] == [
        SignalState.CANDIDATE,
        SignalState.INVALIDATED,
    ]


@pytest.mark.asyncio
async def test_quant_candidate_invalidates_during_rest_outage(tmp_path, monkeypatch):
    now = datetime.now(UTC)
    store = Store(tmp_path / "market.sqlite3")
    candidate = persist_active_btc_candidate(store, now)

    class FailingREST:
        def __init__(self, _url):
            pass

        async def historical_candles(self, *_args, **_kwargs):
            raise DeltaAPIError("fixture outage")

    async def stop_after_iteration(_delay):
        raise asyncio.CancelledError

    instrument = Instrument(
        product_id=27,
        symbol="BTCUSD",
        contract_type="perpetual_futures",
        contract_value=Decimal("0.001"),
        contract_unit_currency="BTC",
        tick_size=Decimal("0.5"),
        underlying_asset="BTC",
        quoting_asset="USD",
        settling_asset="USD",
        notional_type="vanilla",
    )
    monkeypatch.setattr("marketintel.worker.DeltaREST", FailingREST)
    monkeypatch.setattr("marketintel.worker.ENGINE_CONFIGS", (QUANT_ENGINE_BY_ID["BTC_FAST"],))
    monkeypatch.setattr("marketintel.worker.asyncio.sleep", stop_after_iteration)
    settings = Settings(database_path=tmp_path / "market.sqlite3")

    with pytest.raises(asyncio.CancelledError):
        await poll_closed_candles(settings, store, {"BTC": instrument})

    lifecycle = store.candidate_lifecycle(candidate.candidate_id)
    assert [event.to_state for event in lifecycle] == [
        SignalState.CANDIDATE,
        SignalState.INVALIDATED,
    ]


@pytest.mark.asyncio
async def test_r2_durable_trade_breach_invalidates_after_price_recovers(tmp_path, monkeypatch):
    """R2: every post-observation breach matters; the latest candle is insufficient."""
    now = datetime.now(UTC).replace(microsecond=0)
    store = Store(tmp_path / "market.sqlite3")
    candidate = persist_active_btc_candidate(store, now)
    store.record_source_status(
        "product_discovery:BTC", "AVAILABLE", "TEST_FIXTURE_NOT_LIVE", occurred_at=now
    )
    assert store.append_raw_event(trade_event(now - timedelta(seconds=30), "68999"))
    assert store.append_raw_event(trade_event(now - timedelta(seconds=10), "70000"))
    candle = Candle(
        symbol="BTCUSD",
        resolution="1m",
        open_time=now.replace(second=0) - timedelta(minutes=2),
        open=70200,
        high=70300,
        low=70100,
        close=70251,
        volume_contracts=100,
        source="TEST_FIXTURE_NOT_LIVE",
        available_at_utc=now - timedelta(minutes=1),
    )

    class FakeREST:
        def __init__(self, _url):
            pass

        async def historical_candles(self, *_args, **_kwargs):
            return [candle]

    def fake_detect(*_args, **_kwargs):
        return SimpleNamespace(
            engine="BTC_FAST",
            state=SignalState.WAIT,
            reason="TEST_FIXTURE_NOT_LIVE",
            candidate=None,
            snapshot=SimpleNamespace(
                snapshot_id="f" * 64,
                source_quality="FRESH",
                book=SimpleNamespace(available=True),
            ),
        )

    async def stop_after_iteration(_delay):
        raise asyncio.CancelledError

    instrument = Instrument(
        product_id=27,
        symbol="BTCUSD",
        contract_type="perpetual_futures",
        contract_value=Decimal("0.001"),
        contract_unit_currency="BTC",
        tick_size=Decimal("0.5"),
        underlying_asset="BTC",
        quoting_asset="USD",
        settling_asset="USD",
        notional_type="vanilla",
    )
    monkeypatch.setattr("marketintel.worker.DeltaREST", FakeREST)
    monkeypatch.setattr("marketintel.worker.ENGINE_CONFIGS", (QUANT_ENGINE_BY_ID["BTC_FAST"],))
    monkeypatch.setattr("marketintel.worker.detect_signal", fake_detect)
    monkeypatch.setattr(store, "add_feature_snapshot", lambda _snapshot: True)
    monkeypatch.setattr("marketintel.worker.asyncio.sleep", stop_after_iteration)
    settings = Settings(database_path=tmp_path / "market.sqlite3")

    with pytest.raises(asyncio.CancelledError):
        await poll_closed_candles(settings, store, {"BTC": instrument})

    lifecycle = store.candidate_lifecycle(candidate.candidate_id)
    assert [event.to_state for event in lifecycle] == [
        SignalState.CANDIDATE,
        SignalState.INVALIDATED,
    ]


@pytest.mark.asyncio
async def test_periodic_discovery_keeps_collectors_when_symbols_are_unchanged(monkeypatch):
    discovery_calls = 0
    poller_starts = 0
    streamer_starts = 0

    class FakeSettings:
        live_ingestion_enabled = True
        delta_rest_url = "https://example.invalid"
        delta_ws_url = "wss://example.invalid"
        btc_symbol = "BTCUSD"
        gold_symbol = "XAUTUSD"
        database_path = ":memory:"
        delta_discovery_refresh_seconds = 0
        delta_book_max_age_seconds = 10

    class FakeStore:
        def __init__(self, _path):
            self.statuses = []

        def record_source_status(self, *args):
            self.statuses.append(args)

        def save_book_checkpoint(self, _book):
            return None

    class FakeREST:
        def __init__(self, _url):
            pass

        async def discover_instruments(self, **_kwargs):
            nonlocal discovery_calls
            discovery_calls += 1
            if discovery_calls == 3:
                raise asyncio.CancelledError
            return SimpleNamespace(
                btc=SimpleNamespace(symbol="BTCUSD"),
                gold=None,
                unavailable={"GOLD": "fixture unavailable"},
                invalid_product_count=0,
            )

    async def fake_poller(*_args):
        nonlocal poller_starts
        poller_starts += 1
        await asyncio.Event().wait()

    async def fake_streamer(*_args):
        nonlocal streamer_starts
        streamer_starts += 1
        await asyncio.Event().wait()

    monkeypatch.setattr("marketintel.worker.Settings", FakeSettings)
    monkeypatch.setattr("marketintel.worker.Store", FakeStore)
    monkeypatch.setattr("marketintel.worker.DeltaREST", FakeREST)
    monkeypatch.setattr("marketintel.worker.poll_closed_candles", fake_poller)
    monkeypatch.setattr("marketintel.worker.public_market_stream", fake_streamer)

    with pytest.raises(asyncio.CancelledError):
        await worker_main()

    assert discovery_calls == 3
    assert poller_starts == 1
    assert streamer_starts == 1


def test_r6_discovery_cache_expires_and_recovers_after_fresh_verification(tmp_path):
    store = Store(tmp_path / "market.sqlite3")
    start = datetime(2026, 11, 21, 0, 0, tzinfo=UTC)
    assert not store.source_is_eligible(
        "product_discovery:BTC", now=start, maximum_success_age_seconds=300
    )

    store.record_source_status(
        "product_discovery:BTC", "AVAILABLE", "verified fixture", occurred_at=start
    )
    store.record_source_status(
        "product_discovery:BTC",
        "DEGRADED",
        "refresh outage fixture",
        occurred_at=start + timedelta(seconds=10),
    )
    assert store.source_is_eligible(
        "product_discovery:BTC",
        now=start + timedelta(seconds=299),
        maximum_success_age_seconds=300,
    )
    assert not store.source_is_eligible(
        "product_discovery:BTC",
        now=start + timedelta(seconds=301),
        maximum_success_age_seconds=300,
    )

    recovered = start + timedelta(seconds=302)
    store.record_source_status(
        "product_discovery:BTC", "AVAILABLE", "verified again", occurred_at=recovered
    )
    assert store.source_is_eligible(
        "product_discovery:BTC", now=recovered, maximum_success_age_seconds=300
    )


@pytest.mark.asyncio
async def test_m2_candidate_persists_without_ai_confirmation_call(tmp_path, monkeypatch):
    now = datetime.now(UTC)
    open_time = now.replace(second=0, microsecond=0) - timedelta(minutes=10)
    candle = Candle(
        symbol="XAUTUSD",
        resolution="5m",
        open_time=open_time,
        open=2600,
        high=2610,
        low=2595,
        close=2605,
        volume_contracts=100,
        source="TEST_FIXTURE_NOT_LIVE",
    )
    candidate = CandidateSignal(
        candidate_id="m2-candidate-fixture-0001",
        snapshot_id="a" * 64,
        asset="GOLD",
        symbol="XAUTUSD",
        engine="GOLD_HOURLY",
        horizon_minutes=60,
        candle_close_utc=open_time + timedelta(minutes=5),
        observed_at_utc=now,
        expires_at_utc=now + timedelta(minutes=60),
        direction="BULLISH",
        trigger="TEST_FIXTURE_NOT_LIVE breakout retest",
        entry=2605,
        invalidation=2595,
        targets=[2615],
        feature_evidence=["TEST_FIXTURE_NOT_LIVE"],
        source_quality="FRESH",
        rule_version="m2-v1",
    )

    class FakeREST:
        def __init__(self, _url):
            pass

        async def historical_candles(self, *_args, **_kwargs):
            return [candle]

    async def stop_after_iteration(_delay):
        raise asyncio.CancelledError

    async def ai_must_not_run(*_args, **_kwargs):
        raise AssertionError("M2 must not call paid AI")

    def fake_detect(*_args, **_kwargs):
        return DetectionResult(
            engine="GOLD_HOURLY",
            state=SignalState.CANDIDATE,
            observed_at_utc=now,
            reason="TEST_FIXTURE_NOT_LIVE",
            candidate=candidate,
        )

    instrument = Instrument(
        product_id=131253,
        symbol="XAUTUSD",
        contract_type="perpetual_futures",
        contract_value=Decimal("0.001"),
        contract_unit_currency="XAUT",
        tick_size=Decimal("0.01"),
        underlying_asset="XAUT",
        quoting_asset="USD",
        settling_asset="USD",
        notional_type="vanilla",
    )
    monkeypatch.setattr("marketintel.worker.DeltaREST", FakeREST)
    monkeypatch.setattr("marketintel.worker.ENGINE_CONFIGS", (QUANT_ENGINE_BY_ID["GOLD_HOURLY"],))
    monkeypatch.setattr("marketintel.worker.detect_signal", fake_detect)
    monkeypatch.setattr("marketintel.worker.independent_review", ai_must_not_run)
    monkeypatch.setattr("marketintel.worker.asyncio.sleep", stop_after_iteration)
    store = Store(tmp_path / "market.sqlite3")
    event_micros = int((now - timedelta(seconds=2)).timestamp() * 1_000_000)
    gold_event = parse_trade_message(
        {
            "type": "trades",
            "sy": "XAUTUSD",
            "p": "2605",
            "s": "1",
            "r": "t",
            "t": event_micros,
            "ts": event_micros + 1_000,
        },
        received_at=now - timedelta(seconds=1),
    )[0]
    store.append_raw_event(gold_event)
    store.record_source_status(
        "product_discovery:GOLD", "AVAILABLE", "TEST_FIXTURE_NOT_LIVE", occurred_at=now
    )
    store.record_source_status(
        "candle_reconciliation:XAUTUSD", "VALID", "TEST_FIXTURE_NOT_LIVE", occurred_at=now
    )
    settings = Settings(database_path=tmp_path / "market.sqlite3", ai_enabled=True)

    with pytest.raises(asyncio.CancelledError):
        await poll_closed_candles(settings, store, {"GOLD": instrument})

    assert store.recent_candidates()[0]["candidate"]["candidate_id"] == candidate.candidate_id
    lifecycle = store.candidate_lifecycle(candidate.candidate_id)
    assert [event.to_state for event in lifecycle] == [SignalState.CANDIDATE]


@pytest.mark.asyncio
async def test_worker_persists_expiry_once_across_restart_poll(tmp_path, monkeypatch):
    now = datetime.now(UTC)
    open_time = now.replace(second=0, microsecond=0) - timedelta(minutes=10)
    candle = Candle(
        symbol="XAUTUSD",
        resolution="5m",
        open_time=open_time,
        open=2600,
        high=2602,
        low=2598,
        close=2600,
        volume_contracts=100,
        source="TEST_FIXTURE_NOT_LIVE",
    )
    candidate = CandidateSignal(
        candidate_id="m2-expired-fixture-0001",
        snapshot_id="e" * 64,
        asset="GOLD",
        symbol="XAUTUSD",
        engine="GOLD_HOURLY",
        horizon_minutes=60,
        candle_close_utc=now - timedelta(hours=2),
        observed_at_utc=now - timedelta(hours=2),
        expires_at_utc=now - timedelta(hours=1),
        direction="BULLISH",
        trigger="TEST_FIXTURE_NOT_LIVE",
        entry=2600,
        invalidation=2590,
        targets=[2610],
        feature_evidence=["TEST_FIXTURE_NOT_LIVE"],
        rule_version="m2-v1",
    )
    instrument = Instrument(
        product_id=131253,
        symbol="XAUTUSD",
        contract_type="perpetual_futures",
        contract_value=Decimal("0.001"),
        contract_unit_currency="XAUT",
        tick_size=Decimal("0.01"),
        underlying_asset="XAUT",
        quoting_asset="USD",
        settling_asset="USD",
        notional_type="vanilla",
    )

    class FakeREST:
        def __init__(self, _url):
            pass

        async def historical_candles(self, *_args, **_kwargs):
            return [candle]

    def fake_detect(*_args, **_kwargs):
        return DetectionResult(
            engine="GOLD_HOURLY",
            state=SignalState.WAIT,
            observed_at_utc=now,
            reason="TEST_FIXTURE_NOT_LIVE missing snapshot",
        )

    async def stop_after_iteration(_delay):
        raise asyncio.CancelledError

    async def ai_must_not_run(*_args, **_kwargs):
        raise AssertionError("M2 must not call paid AI")

    store = Store(tmp_path / "market.sqlite3")
    store.add_candidate(candidate)
    store.record_candidate_lifecycle(
        lifecycle_event(
            candidate_id=candidate.candidate_id,
            snapshot_id=candidate.snapshot_id,
            from_state=None,
            to_state=SignalState.CANDIDATE,
            occurred_at=candidate.observed_at_utc,
            reason="TEST_FIXTURE_NOT_LIVE candidate emitted",
        )
    )
    monkeypatch.setattr("marketintel.worker.DeltaREST", FakeREST)
    monkeypatch.setattr("marketintel.worker.ENGINE_CONFIGS", (QUANT_ENGINE_BY_ID["GOLD_HOURLY"],))
    monkeypatch.setattr("marketintel.worker.detect_signal", fake_detect)
    monkeypatch.setattr("marketintel.worker.independent_review", ai_must_not_run)
    monkeypatch.setattr("marketintel.worker.asyncio.sleep", stop_after_iteration)
    settings = Settings(database_path=tmp_path / "market.sqlite3", ai_enabled=True)

    with pytest.raises(asyncio.CancelledError):
        await poll_closed_candles(settings, store, {"GOLD": instrument})

    assert [event.to_state for event in store.candidate_lifecycle(candidate.candidate_id)] == [
        SignalState.CANDIDATE,
        SignalState.EXPIRED,
    ]
