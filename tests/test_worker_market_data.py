import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from marketintel.config import Settings
from marketintel.delta import DeltaAPIError, parse_trade_message
from marketintel.detectors import EngineConfig
from marketintel.models import Candle
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
async def test_worker_reconciles_closed_trade_candle_and_persists_valid_status(
    tmp_path, monkeypatch
):
    now = datetime.now(UTC)
    open_time = now.replace(second=0, microsecond=0) - timedelta(minutes=2)
    event = trade_event(open_time + timedelta(seconds=5))
    store = Store(tmp_path / "market.sqlite3")
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

    class FakeStore:
        def __init__(self, _path):
            self.statuses = []

        def record_source_status(self, *args):
            self.statuses.append(args)

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
