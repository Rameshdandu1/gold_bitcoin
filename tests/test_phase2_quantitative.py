import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from marketintel.delta import parse_book_message, parse_trade_message
from marketintel.detectors import describe_engines
from marketintel.models import (
    BookFeatures,
    CandidateSignal,
    Candle,
    ExternalMetric,
    Instrument,
    SignalState,
    TradeRecord,
)
from marketintel.quantitative import (
    QUANT_ENGINE_CONFIGS,
    detect_signal,
    lifecycle_event,
    replay_engine,
    terminal_transition,
)
from marketintel.replay import replay_order_book, replay_trade_records
from marketintel.storage import Store

FIXTURES = Path(__file__).parent / "fixtures" / "delta"


def instrument(asset):
    underlying = "XAUT" if asset == "GOLD" else "BTC"
    return Instrument(
        product_id=131253 if asset == "GOLD" else 27,
        symbol="XAUTUSD" if asset == "GOLD" else "BTCUSD",
        contract_type="perpetual_futures",
        contract_value=Decimal("0.001"),
        contract_unit_currency=underlying,
        tick_size=Decimal("0.01" if asset == "GOLD" else "0.5"),
        underlying_asset=underlying,
        quoting_asset="USD",
        settling_asset="USD",
        notional_type="vanilla",
    )


def supporting_book(now, direction):
    imbalance = Decimal("0.40") if direction == "BULLISH" else Decimal("-0.40")
    return BookFeatures(
        available=True,
        observed_at_utc=now,
        best_bid=Decimal("100"),
        best_ask=Decimal("100.1"),
        spread=Decimal("0.1"),
        bid_depth_quote=Decimal("1400") if direction == "BULLISH" else Decimal("600"),
        ask_depth_quote=Decimal("600") if direction == "BULLISH" else Decimal("1400"),
        imbalance=imbalance,
        absorption="NONE",
        reason="TEST_FIXTURE_NOT_LIVE",
    )


def supportive_trades(symbol, now, direction, count=5_100):
    rows = []
    for index in range(count):
        supporting = index % 5 != 0
        if direction == "BULLISH":
            aggressor = "BUY" if supporting else "SELL"
        else:
            aggressor = "SELL" if supporting else "BUY"
        rows.append(
            TradeRecord(
                event_id=f"{symbol}-{index}",
                symbol=symbol,
                price=Decimal("2600" if symbol == "XAUTUSD" else "70000"),
                contracts=Decimal("1"),
                aggressor=aggressor,
                event_time_utc=now - timedelta(seconds=count - index),
                received_at_utc=now - timedelta(seconds=count - index - 0.1),
            )
        )
    return rows


def policy_bars(config, direction):
    symbol = "XAUTUSD" if config.asset == "GOLD" else "BTCUSD"
    base = 2600.0 if config.asset == "GOLD" else 70000.0
    half_range = 3.0 if config.asset == "GOLD" else 250.0
    minutes = {"1m": 1, "5m": 5, "15m": 15}[config.primary_resolution]
    start = datetime(2026, 11, 18, 0, 0, tzinfo=UTC)
    rows = []
    for index in range(config.min_candles):
        rows.append(
            Candle(
                symbol=symbol,
                resolution=config.primary_resolution,
                open_time=start + timedelta(minutes=minutes * index),
                open=base,
                high=base + half_range,
                low=base - half_range,
                close=base,
                volume_contracts=100,
                source="TEST_FIXTURE_NOT_LIVE",
                available_at_utc=start + timedelta(minutes=minutes * (index + 1)),
            )
        )

    move = 7.0 if config.asset == "GOLD" else 600.0
    if config.trigger_family == "FAST":
        if direction == "BULLISH":
            rows[-1] = rows[-1].model_copy(
                update={
                    "open": base,
                    "high": base + move,
                    "low": base - half_range - 1,
                    "close": base + half_range + 1,
                    "volume_contracts": 220,
                }
            )
        else:
            rows[-1] = rows[-1].model_copy(
                update={
                    "open": base,
                    "high": base + half_range + 1,
                    "low": base - move,
                    "close": base - half_range - 1,
                    "volume_contracts": 220,
                }
            )
    elif config.trigger_family == "HOURLY":
        if direction == "BULLISH":
            rows[-2] = rows[-2].model_copy(
                update={
                    "high": base + move,
                    "low": base,
                    "close": base + half_range + 2,
                    "volume_contracts": 200,
                }
            )
            rows[-1] = rows[-1].model_copy(
                update={
                    "open": base + half_range + 2,
                    "high": base + move + half_range,
                    "low": base + half_range - 0.02,
                    "close": base + move + 1,
                    "volume_contracts": 210,
                }
            )
        else:
            rows[-2] = rows[-2].model_copy(
                update={
                    "high": base,
                    "low": base - move,
                    "close": base - half_range - 2,
                    "volume_contracts": 200,
                }
            )
            rows[-1] = rows[-1].model_copy(
                update={
                    "open": base - half_range - 2,
                    "high": base - half_range + 0.02,
                    "low": base - move - half_range,
                    "close": base - move - 1,
                    "volume_contracts": 210,
                }
            )
    else:
        pivot_index = config.min_candles - 8
        if direction == "BULLISH":
            rows[pivot_index] = rows[pivot_index].model_copy(
                update={"high": base + half_range + 2, "low": base - half_range, "close": base + 1}
            )
            for index in range(config.min_candles - 5, config.min_candles - 1):
                rows[index] = rows[index].model_copy(
                    update={
                        "open": base + 2,
                        "high": base + half_range + 1,
                        "low": base,
                        "close": base + 2,
                    }
                )
            rows[-1] = rows[-1].model_copy(
                update={
                    "open": base + 2,
                    "high": base + move + 2,
                    "low": base + 1,
                    "close": base + move,
                    "volume_contracts": 220,
                }
            )
        else:
            rows[pivot_index] = rows[pivot_index].model_copy(
                update={"high": base + half_range, "low": base - half_range - 2, "close": base - 1}
            )
            for index in range(config.min_candles - 5, config.min_candles - 1):
                rows[index] = rows[index].model_copy(
                    update={
                        "open": base - 2,
                        "high": base,
                        "low": base - half_range - 1,
                        "close": base - 2,
                    }
                )
            rows[-1] = rows[-1].model_copy(
                update={
                    "open": base - 2,
                    "high": base - 1,
                    "low": base - move - 2,
                    "close": base - move,
                    "volume_contracts": 220,
                }
            )
    return rows


@pytest.mark.parametrize("config", QUANT_ENGINE_CONFIGS, ids=lambda item: item.engine)
@pytest.mark.parametrize("direction", ["BULLISH", "BEARISH"])
def test_each_engine_independently_emits_bullish_and_bearish_candidate(config, direction):
    bars = policy_bars(config, direction)
    now = bars[-1].open_time + timedelta(
        minutes={"1m": 1, "5m": 5, "15m": 15}[config.primary_resolution]
    )
    result = detect_signal(
        config,
        candles=bars,
        trades=supportive_trades(instrument(config.asset).symbol, now, direction),
        instrument=instrument(config.asset),
        now=now,
        book_override=supporting_book(now, direction),
        reference_available=config.asset == "GOLD",
    )
    assert result.state is SignalState.CANDIDATE, result.reason
    assert result.candidate is not None
    assert result.candidate.engine == config.engine
    assert result.candidate.direction == direction
    assert result.candidate.not_ai_confirmed is True
    assert result.candidate.horizon_minutes == config.horizon_minutes
    assert result.candidate.expires_at_utc - result.candidate.candle_close_utc == timedelta(
        minutes=config.horizon_minutes
    )


@pytest.mark.parametrize("config", QUANT_ENGINE_CONFIGS, ids=lambda item: item.engine)
def test_each_engine_replays_historical_fixture_deterministically(config):
    bars = policy_bars(config, "BULLISH")
    final_close = bars[-1].open_time + timedelta(
        minutes={"1m": 1, "5m": 5, "15m": 15}[config.primary_resolution]
    )
    trades = supportive_trades(instrument(config.asset).symbol, final_close, "BULLISH")

    def book_at(when):
        return supporting_book(when, "BULLISH")

    first = replay_engine(
        config,
        candles=bars,
        trades=trades,
        instrument=instrument(config.asset),
        book_at=book_at,
        reference_available=config.asset == "GOLD",
    )
    second = replay_engine(
        config,
        candles=list(reversed(bars)),
        trades=list(reversed(trades)),
        instrument=instrument(config.asset),
        book_at=book_at,
        reference_available=config.asset == "GOLD",
    )
    first_candidates = [result.candidate for result in first if result.candidate]
    second_candidates = [result.candidate for result in second if result.candidate]
    assert first_candidates == second_candidates
    assert first_candidates[-1].engine == config.engine


def test_false_breakout_is_not_a_candidate():
    config = next(item for item in QUANT_ENGINE_CONFIGS if item.engine == "BTC_FAST")
    bars = policy_bars(config, "BULLISH")
    base = 70000.0
    bars[-1] = bars[-1].model_copy(
        update={"high": base + 700, "low": base - 700, "close": base, "volume_contracts": 220}
    )
    now = bars[-1].open_time + timedelta(minutes=1)
    result = detect_signal(
        config,
        candles=bars,
        trades=supportive_trades("BTCUSD", now, "BULLISH"),
        instrument=instrument("BTC"),
        now=now,
        book_override=supporting_book(now, "BULLISH"),
    )
    assert result.state is SignalState.REJECTED
    assert result.candidate is None


def test_fast_engine_can_trigger_from_aligned_closed_three_minute_context():
    config = next(item for item in QUANT_ENGINE_CONFIGS if item.engine == "GOLD_FAST")
    shifted = [
        row.model_copy(update={"open_time": row.open_time + timedelta(minutes=2)})
        for row in policy_bars(config, "BULLISH")
    ]
    bars = [
        Candle(
            symbol="XAUTUSD",
            resolution="1m",
            open_time=shifted[0].open_time - timedelta(minutes=2 - index),
            open=2600,
            high=2603,
            low=2597,
            close=2600,
            volume_contracts=100,
            source="TEST_FIXTURE_NOT_LIVE",
            available_at_utc=shifted[0].open_time - timedelta(minutes=1 - index),
        )
        for index in range(2)
    ] + shifted
    base = 2600.0
    bars[-3] = bars[-3].model_copy(
        update={"open": base, "high": base + 3, "low": base - 10, "close": base}
    )
    bars[-2] = bars[-2].model_copy(
        update={"open": base, "high": base + 3, "low": base - 3, "close": base}
    )
    bars[-1] = bars[-1].model_copy(
        update={
            "open": base,
            "high": base + 4,
            "low": base - 3,
            "close": base + 4,
            "volume_contracts": 220,
        }
    )
    now = bars[-1].open_time + timedelta(minutes=1)
    result = detect_signal(
        config,
        candles=bars,
        trades=supportive_trades("XAUTUSD", now, "BULLISH"),
        instrument=instrument("GOLD"),
        now=now,
        book_override=supporting_book(now, "BULLISH"),
        reference_available=True,
    )
    assert result.state is SignalState.CANDIDATE, result.reason
    assert result.candidate and result.candidate.trigger.startswith("3m liquidity sweep")


def test_hourly_failed_breakout_can_emit_the_opposite_direction():
    config = next(item for item in QUANT_ENGINE_CONFIGS if item.engine == "BTC_HOURLY")
    bars = policy_bars(config, "BULLISH")
    base = 70000.0
    bars[-2] = bars[-2].model_copy(
        update={"open": base, "high": base + 250, "low": base - 250, "close": base}
    )
    bars[-1] = bars[-1].model_copy(
        update={
            "open": base,
            "high": base + 900,
            "low": base - 500,
            "close": base - 400,
            "volume_contracts": 240,
        }
    )
    now = bars[-1].open_time + timedelta(minutes=5)
    result = detect_signal(
        config,
        candles=bars,
        trades=supportive_trades("BTCUSD", now, "BEARISH"),
        instrument=instrument("BTC"),
        now=now,
        book_override=supporting_book(now, "BEARISH"),
    )
    assert result.state is SignalState.CANDIDATE, result.reason
    assert result.candidate and result.candidate.direction == "BEARISH"
    assert "failed breakout rejection" in result.candidate.trigger


def test_stale_or_corrupt_book_fails_closed():
    config = next(item for item in QUANT_ENGINE_CONFIGS if item.engine == "GOLD_FAST")
    bars = policy_bars(config, "BULLISH")
    now = bars[-1].open_time + timedelta(minutes=1)
    invalid = BookFeatures(available=False, reason="checksum_mismatch")
    result = detect_signal(
        config,
        candles=bars,
        trades=supportive_trades("XAUTUSD", now, "BULLISH"),
        instrument=instrument("GOLD"),
        now=now,
        book_override=invalid,
        reference_available=True,
    )
    assert result.state is SignalState.WAIT
    assert "book required" in result.reason


def test_stale_trade_flow_fails_closed_despite_fresh_candles_and_book():
    config = next(item for item in QUANT_ENGINE_CONFIGS if item.engine == "BTC_FAST")
    bars = policy_bars(config, "BULLISH")
    now = bars[-1].open_time + timedelta(minutes=1)
    stale = supportive_trades("BTCUSD", now - timedelta(hours=1), "BULLISH")
    result = detect_signal(
        config,
        candles=bars,
        trades=stale,
        instrument=instrument("BTC"),
        now=now,
        book_override=supporting_book(now, "BULLISH"),
    )
    assert result.state is SignalState.WAIT
    assert result.snapshot is not None
    assert result.snapshot.source_quality == "STALE"


def test_future_book_and_external_metric_cannot_enter_snapshot():
    config = next(item for item in QUANT_ENGINE_CONFIGS if item.engine == "BTC_FAST")
    bars = policy_bars(config, "BULLISH")
    now = bars[-1].open_time + timedelta(minutes=1)
    future_book = supporting_book(now + timedelta(seconds=1), "BULLISH")
    future_metric = ExternalMetric(
        provider="TEST_FIXTURE_NOT_LIVE",
        metric="open_interest_usd",
        symbol="BTC",
        value=Decimal("1"),
        unit="USD",
        observed_at_utc=now + timedelta(seconds=1),
        received_at_utc=now + timedelta(seconds=1),
        timestamp_basis="RECEIVED_AT",
        entitlement="fixture",
        source_scope="test_only",
    )
    result = detect_signal(
        config,
        candles=bars,
        trades=supportive_trades("BTCUSD", now, "BULLISH"),
        instrument=instrument("BTC"),
        now=now,
        book_override=future_book,
        external_metrics=(future_metric,),
    )
    assert result.state is SignalState.WAIT
    assert result.snapshot is not None
    assert result.snapshot.book.available is False
    assert result.snapshot.external_metrics == ()
    assert any("external metrics were excluded" in item for item in result.snapshot.warnings)


@pytest.mark.parametrize("engine_id", ["GOLD_FAST", "BTC_FAST"])
def test_r4_direct_detector_rejects_candles_not_yet_available(engine_id):
    config = next(item for item in QUANT_ENGINE_CONFIGS if item.engine == engine_id)
    bars = policy_bars(config, "BULLISH")
    now = bars[-1].open_time + timedelta(minutes=1)
    delayed = [row.model_copy(update={"available_at_utc": now + timedelta(days=1)}) for row in bars]
    result = detect_signal(
        config,
        candles=delayed,
        trades=supportive_trades(instrument(config.asset).symbol, now, "BULLISH"),
        instrument=instrument(config.asset),
        now=now,
        book_override=supporting_book(now, "BULLISH"),
        reference_available=config.asset == "GOLD",
    )
    assert result.state is SignalState.WAIT
    assert result.candidate is None


def test_missing_candle_stale_feed_and_wrong_gold_instrument_fail_closed():
    config = next(item for item in QUANT_ENGINE_CONFIGS if item.engine == "GOLD_FAST")
    bars = policy_bars(config, "BULLISH")
    close = bars[-1].open_time + timedelta(minutes=1)
    common = {
        "config": config,
        "trades": supportive_trades("XAUTUSD", close, "BULLISH"),
        "now": close,
        "book_override": supporting_book(close, "BULLISH"),
        "reference_available": True,
    }
    gapped = bars.copy()
    gapped.pop(10)
    missing = detect_signal(candles=gapped, instrument=instrument("GOLD"), **common)
    assert missing.state is SignalState.WAIT

    stale = detect_signal(
        candles=bars,
        instrument=instrument("GOLD"),
        **{**common, "now": close + timedelta(minutes=10)},
    )
    assert stale.state is SignalState.WAIT

    wrong = detect_signal(candles=bars, instrument=instrument("BTC"), **common)
    assert wrong.state is SignalState.UNAVAILABLE


def test_gold_thirty_dollar_target_is_filtered_when_only_ten_is_feasible():
    original = next(item for item in QUANT_ENGINE_CONFIGS if item.engine == "GOLD_FAST")
    config = replace(original, volatility_budget_multiplier=Decimal("0.60"))
    bars = policy_bars(config, "BULLISH")
    now = bars[-1].open_time + timedelta(minutes=1)
    result = detect_signal(
        config,
        candles=bars,
        trades=supportive_trades("XAUTUSD", now, "BULLISH"),
        instrument=instrument("GOLD"),
        now=now,
        book_override=supporting_book(now, "BULLISH"),
        reference_available=True,
    )
    assert result.candidate is not None, result.reason
    distances = [
        Decimal(str(target)) - Decimal(str(result.candidate.entry))
        for target in result.candidate.targets
    ]
    assert Decimal("10") in distances
    assert Decimal("30") not in distances


@pytest.mark.parametrize(
    ("direction", "session_price", "session_high", "session_low"),
    [
        ("BULLISH", 2612.0, 2615.0, 2609.0),
        ("BEARISH", 2588.0, 2591.0, 2585.0),
    ],
)
def test_r1_hourly_engine_uses_complete_utc_session_context(
    direction, session_price, session_high, session_low
):
    """R1: trigger lookback must not replace complete session VWAP/levels."""
    config = next(item for item in QUANT_ENGINE_CONFIGS if item.engine == "GOLD_HOURLY")
    trigger_rows = [
        row.model_copy(update={"open_time": row.open_time + timedelta(hours=5)})
        for row in policy_bars(config, direction)
    ]
    session_start = datetime(2026, 11, 18, 0, 0, tzinfo=UTC)
    earlier_rows = [
        Candle(
            symbol="XAUTUSD",
            resolution="5m",
            open_time=session_start + timedelta(minutes=5 * index),
            open=session_price,
            high=session_high,
            low=session_low,
            close=session_price,
            volume_contracts=1_000,
            source="TEST_FIXTURE_NOT_LIVE",
            available_at_utc=session_start + timedelta(minutes=5 * (index + 1)),
        )
        for index in range(60)
    ]
    bars = earlier_rows + trigger_rows
    now = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)

    result = detect_signal(
        config,
        candles=bars,
        trades=supportive_trades("XAUTUSD", now, direction),
        instrument=instrument("GOLD"),
        now=now,
        book_override=supporting_book(now, direction),
        reference_available=True,
    )

    assert result.candidate is None, (
        "complete session VWAP and opposing levels must block the cropped-window candidate"
    )


def test_wide_spread_can_eliminate_otherwise_feasible_gold_targets():
    config = next(item for item in QUANT_ENGINE_CONFIGS if item.engine == "GOLD_FAST")
    bars = policy_bars(config, "BULLISH")
    now = bars[-1].open_time + timedelta(minutes=1)
    wide = supporting_book(now, "BULLISH").model_copy(
        update={"best_ask": Decimal("200"), "spread": Decimal("100")}
    )
    result = detect_signal(
        config,
        candles=bars,
        trades=supportive_trades("XAUTUSD", now, "BULLISH"),
        instrument=instrument("GOLD"),
        now=now,
        book_override=wide,
        reference_available=True,
    )
    assert result.state is SignalState.WAIT
    assert result.candidate is None


def test_gold_reference_absence_is_explicit_and_basis_dependent_policy_fails_closed():
    original = next(item for item in QUANT_ENGINE_CONFIGS if item.engine == "GOLD_FAST")
    bars = policy_bars(original, "BULLISH")
    now = bars[-1].open_time + timedelta(minutes=1)
    common = {
        "candles": bars,
        "trades": supportive_trades("XAUTUSD", now, "BULLISH"),
        "instrument": instrument("GOLD"),
        "now": now,
        "book_override": supporting_book(now, "BULLISH"),
    }
    token_only = detect_signal(original, reference_available=False, **common)
    assert token_only.candidate is not None
    assert any("token-market-only" in item for item in token_only.candidate.counter_evidence)

    basis_required = detect_signal(
        replace(original, allow_token_market_only=False), reference_available=False, **common
    )
    assert basis_required.state is SignalState.UNAVAILABLE


def test_candidate_contract_rejects_nonpositive_target():
    config = next(item for item in QUANT_ENGINE_CONFIGS if item.engine == "BTC_FAST")
    bars = policy_bars(config, "BULLISH")
    now = bars[-1].open_time + timedelta(minutes=1)
    candidate = detect_signal(
        config,
        candles=bars,
        trades=supportive_trades("BTCUSD", now, "BULLISH"),
        instrument=instrument("BTC"),
        now=now,
        book_override=supporting_book(now, "BULLISH"),
    ).candidate
    assert candidate
    payload = candidate.model_dump()
    payload["targets"] = [0]
    with pytest.raises(ValueError, match="positive"):
        CandidateSignal.model_validate(payload)


def test_m1_journal_replays_into_candidate_snapshot_and_idempotent_lifecycle(tmp_path):
    config = next(item for item in QUANT_ENGINE_CONFIGS if item.engine == "BTC_FAST")
    bars = policy_bars(config, "BULLISH")
    decision_time = bars[-1].open_time + timedelta(minutes=1)
    raw_trades = []
    start = decision_time - timedelta(seconds=6)
    for index in range(5_100):
        when = start + timedelta(microseconds=index * 1_000)
        micros = int(when.timestamp() * 1_000_000)
        message = {
            "type": "trades",
            "sy": "BTCUSD",
            "p": "70000",
            "s": "1",
            "r": "t" if index % 5 else "m",
            "t": micros,
            "ts": micros + 100,
        }
        raw_trades.append(
            parse_trade_message(message, received_at=when + timedelta(microseconds=200))[0]
        )

    book_payload = json.loads((FIXTURES / "websocket.json").read_text(encoding="utf-8"))[
        "book_snapshot"
    ]
    original_book = parse_book_message(
        book_payload,
        received_at=datetime.fromtimestamp(book_payload["ts"] / 1_000_000, tz=UTC)
        + timedelta(seconds=1),
    )
    book_event = original_book.model_copy(
        update={
            "event_time_utc": decision_time - timedelta(seconds=1),
            "received_at_utc": decision_time - timedelta(milliseconds=500),
            "publish_time_utc": decision_time - timedelta(seconds=1),
        }
    )
    store = Store(tmp_path / "journal.sqlite3")
    assert store.append_raw_events(raw_trades + [book_event]) == 5_101
    persisted = store.raw_events(symbol="BTCUSD", end=decision_time + timedelta(microseconds=1))
    trades = replay_trade_records(persisted, symbol="BTCUSD", through=decision_time)
    book = replay_order_book(persisted, symbol="BTCUSD", through=decision_time)
    result = detect_signal(
        config,
        candles=bars,
        trades=trades,
        instrument=instrument("BTC"),
        now=decision_time,
        book=book,
    )
    assert result.candidate is not None, result.reason
    assert result.snapshot is not None
    assert store.add_feature_snapshot(result.snapshot) is True
    initial = lifecycle_event(
        candidate_id=result.candidate.candidate_id,
        snapshot_id=result.candidate.snapshot_id,
        from_state=None,
        to_state=SignalState.CANDIDATE,
        occurred_at=result.candidate.observed_at_utc,
        reason="TEST_FIXTURE_NOT_LIVE journal replay",
    )
    assert store.add_candidate_with_lifecycle(result.candidate, initial) is True
    assert store.add_candidate_with_lifecycle(result.candidate, initial) is False
    assert store.feature_snapshot(result.snapshot.snapshot_id) == result.snapshot
    assert store.candidate_lifecycle(result.candidate.candidate_id) == [initial]

    store.set_status(config.engine, SignalState.CANDIDATE.value, "NOT AI CONFIRMED")
    engine_state = next(
        item
        for item in store.last_engine_states(describe_engines("XAUTUSD", "WRONG_PREFERENCE"))
        if item["id"] == config.engine
    )
    assert engine_state["symbol"] == "BTCUSD"
    assert engine_state["state"] == "CANDIDATE"


def test_replay_is_deterministic_deduplicated_and_has_no_lookahead():
    config = next(item for item in QUANT_ENGINE_CONFIGS if item.engine == "BTC_FAST")
    bars = policy_bars(config, "BULLISH")
    last_close = bars[-1].open_time + timedelta(minutes=1)
    trades = supportive_trades("BTCUSD", last_close, "BULLISH")

    def book_at(when):
        return supporting_book(when, "BULLISH")

    first = replay_engine(
        config,
        candles=bars,
        trades=trades + [trades[0]],
        instrument=instrument("BTC"),
        book_at=book_at,
    )
    future = bars[-1].model_copy(
        update={
            "open_time": bars[-1].open_time + timedelta(minutes=1),
            "close": 1,
            "low": 1,
            "high": 2,
            "open": 2,
        }
    )
    second = replay_engine(
        config,
        candles=bars + [future],
        trades=list(reversed(trades)),
        instrument=instrument("BTC"),
        book_at=book_at,
    )
    first_candidate = next(result.candidate for result in first if result.candidate)
    second_candidate = next(result.candidate for result in second if result.candidate)
    assert first_candidate.candidate_id == second_candidate.candidate_id
    assert first_candidate.snapshot_id == second_candidate.snapshot_id
    assert len({result.candidate.candidate_id for result in first if result.candidate}) == 1


def test_replay_rejects_unknown_or_late_candle_availability():
    config = next(item for item in QUANT_ENGINE_CONFIGS if item.engine == "BTC_FAST")
    bars = policy_bars(config, "BULLISH")
    final_close = bars[-1].open_time + timedelta(minutes=1)
    trades = supportive_trades("BTCUSD", final_close, "BULLISH")

    without_clock = [bars[0].model_copy(update={"available_at_utc": None}), *bars[1:]]
    with pytest.raises(ValueError, match="available_at_utc"):
        replay_engine(
            config,
            candles=without_clock,
            trades=trades,
            instrument=instrument("BTC"),
        )

    delayed = [
        *bars[:-1],
        bars[-1].model_copy(update={"available_at_utc": final_close + timedelta(minutes=1)}),
    ]
    results = replay_engine(
        config,
        candles=delayed,
        trades=trades,
        instrument=instrument("BTC"),
        book_at=lambda when: supporting_book(when, "BULLISH"),
    )
    assert not any(result.candidate for result in results)


def test_lifecycle_expiry_invalidation_and_illegal_transition():
    config = next(item for item in QUANT_ENGINE_CONFIGS if item.engine == "BTC_FAST")
    bars = policy_bars(config, "BULLISH")
    now = bars[-1].open_time + timedelta(minutes=1)
    result = detect_signal(
        config,
        candles=bars,
        trades=supportive_trades("BTCUSD", now, "BULLISH"),
        instrument=instrument("BTC"),
        now=now,
        book_override=supporting_book(now, "BULLISH"),
    )
    candidate = result.candidate
    assert candidate
    expired = terminal_transition(
        candidate,
        current_state=SignalState.CANDIDATE,
        now=candidate.expires_at_utc,
        latest_price=Decimal(str(candidate.entry)),
        source_fresh=True,
    )
    assert expired and expired.to_state is SignalState.EXPIRED
    stale = terminal_transition(
        candidate,
        current_state=SignalState.CANDIDATE,
        now=now + timedelta(minutes=1),
        latest_price=Decimal(str(candidate.entry)),
        source_fresh=False,
    )
    assert stale and stale.to_state is SignalState.INVALIDATED
    with pytest.raises(ValueError, match="Illegal"):
        lifecycle_event(
            candidate_id=candidate.candidate_id,
            snapshot_id=candidate.snapshot_id,
            from_state=SignalState.EXPIRED,
            to_state=SignalState.CANDIDATE,
            occurred_at=now,
            reason="illegal fixture transition",
        )
