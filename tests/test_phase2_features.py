from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from marketintel.features import (
    FeatureIntegrityError,
    book_features,
    closed_candles,
    order_flow_features,
    resample_closed_candles,
    structure_events,
)
from marketintel.models import Candle, Instrument, StructureKind, TradeRecord


def instrument(symbol="BTCUSD", underlying="BTC", contract_value="0.001"):
    return Instrument(
        product_id=27,
        symbol=symbol,
        contract_type="perpetual_futures",
        contract_value=Decimal(contract_value),
        contract_unit_currency=underlying,
        tick_size=Decimal("0.5"),
        underlying_asset=underlying,
        quoting_asset="USD",
        settling_asset="USD",
        notional_type="vanilla",
    )


def candle(start, index, *, close=100, high=101, low=99, volume=10):
    open_price = min(max(100, low), max(high, close))
    return Candle(
        symbol="BTCUSD",
        resolution="1m",
        open_time=start + timedelta(minutes=index),
        open=open_price,
        high=max(high, close),
        low=low,
        close=close,
        volume_contracts=volume,
        source="TEST_FIXTURE_NOT_LIVE",
    )


def trade(index, when, aggressor):
    return TradeRecord(
        event_id=f"trade-{index}",
        symbol="BTCUSD",
        price=Decimal("70000") + index,
        contracts=Decimal("2"),
        aggressor=aggressor,
        event_time_utc=when + timedelta(milliseconds=index),
        received_at_utc=when + timedelta(milliseconds=index + 1),
    )


def test_resampling_uses_complete_closed_buckets_without_forward_fill():
    start = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    rows = [candle(start, index, close=100 + index) for index in range(10)]
    complete = resample_closed_candles(
        rows, target_resolution="5m", through=start + timedelta(minutes=10)
    )
    assert [row.open_time for row in complete] == [start, start + timedelta(minutes=5)]
    assert complete[0].close == 104
    assert complete[0].volume_contracts == 50

    with_gap = rows.copy()
    with_gap.pop(2)
    gapped = resample_closed_candles(
        with_gap, target_resolution="5m", through=start + timedelta(minutes=10)
    )
    assert [row.open_time for row in gapped] == [start + timedelta(minutes=5)]


def test_closed_series_rejects_duplicate_and_missing_intervals():
    start = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    with pytest.raises(FeatureIntegrityError, match="Missing"):
        closed_candles(
            [candle(start, 0), candle(start, 2)],
            through=start + timedelta(minutes=3),
        )
    with pytest.raises(FeatureIntegrityError, match="Duplicate"):
        closed_candles(
            [candle(start, 0), candle(start, 0)],
            through=start + timedelta(minutes=1),
        )


def test_exact_500_and_5000_trade_windows_are_replay_stable_and_normalized():
    through = datetime(2026, 11, 20, 12, 15, tzinfo=UTC)
    start = through - timedelta(seconds=5.1)
    rows = [
        trade(
            index,
            start,
            "BUY" if index % 4 in {0, 1} else "SELL" if index % 4 == 2 else None,
        )
        for index in range(5_100)
    ]
    first = order_flow_features(rows, instrument=instrument(), through=through)
    second = order_flow_features(reversed(rows), instrument=instrument(), through=through)

    assert first == second
    assert first.last_500.trade_count == 500
    assert first.last_5000.trade_count == 5_000
    assert first.last_500.unclassified_trade_count == 125
    assert first.last_500.cvd_contracts == Decimal("250")
    assert first.last_500.cvd_base_units == Decimal("0.250")
    assert first.last_500.cvd_quote_notional > 0
    assert first.last_5m.trade_count == 5_100
    assert first.last_15m.trade_count == 5_100


def test_unknown_aggressors_never_enter_signed_delta():
    now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    rows = [trade(0, now, "BUY"), trade(1, now, "SELL"), trade(2, now, None)]
    result = order_flow_features(rows, instrument=instrument(), through=now + timedelta(seconds=1))
    assert result.last_500.cvd_contracts == 0
    assert result.last_500.unclassified_contracts == 2


def test_order_flow_excludes_wrong_symbol_and_future_trades():
    now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    valid = trade(0, now, "BUY")
    wrong_symbol = trade(1, now, "SELL").model_copy(update={"symbol": "XAUTUSD"})
    future = trade(2, now + timedelta(minutes=1), "SELL")
    result = order_flow_features(
        [valid, wrong_symbol, future], instrument=instrument(), through=now + timedelta(seconds=1)
    )
    assert result.last_500.trade_count == 1
    assert result.last_500.cvd_contracts == Decimal("2")


def test_structure_pivot_is_emitted_only_after_right_side_confirmation():
    start = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    rows = [candle(start, index) for index in range(7)]
    rows[2] = candle(start, 2, high=110, low=99, close=105)
    assert not structure_events(rows[:4])
    events = structure_events(rows[:5])
    high = next(event for event in events if event.level == Decimal("110"))
    assert high.kind is StructureKind.HH
    assert high.resolution == "1m"
    assert high.confirmed_at_utc == start + timedelta(minutes=5)


def test_structure_labels_hh_hl_lh_ll_bos_and_choch_without_repainting():
    start = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)

    def rows_from_ranges(ranges):
        return [
            candle(start, index, high=high, low=low, close=close)
            for index, (high, low, close) in enumerate(ranges)
        ]

    rising = rows_from_ranges(
        [
            (103, 97, 100),
            (104, 98, 101),
            (110, 99, 105),
            (105, 98, 102),
            (106, 90, 96),
            (107, 97, 103),
            (115, 100, 110),
            (108, 98, 104),
            (109, 94, 102),
            (110, 99, 106),
            (111, 100, 107),
            (117, 103, 116),
        ]
    )
    rising_events = structure_events(rising)
    rising_kinds = {event.kind for event in rising_events}
    assert {StructureKind.HH, StructureKind.HL, StructureKind.BOS} <= rising_kinds

    reversal = rising.copy()
    reversal[-1] = candle(start, 11, high=103, low=88, close=89)
    assert any(event.kind is StructureKind.CHOCH for event in structure_events(reversal))

    falling = rows_from_ranges(
        [
            (112, 100, 106),
            (111, 99, 105),
            (115, 98, 110),
            (109, 97, 103),
            (110, 90, 95),
            (108, 96, 102),
            (112, 94, 108),
            (107, 93, 100),
            (108, 85, 90),
            (106, 92, 98),
            (105, 80, 81),
        ]
    )
    falling_kinds = {event.kind for event in structure_events(falling)}
    assert {StructureKind.LH, StructureKind.LL} <= falling_kinds


def test_book_imbalance_and_absorption_use_only_validated_depth():
    now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)

    class DummyBook:
        bids = {Decimal("100"): ("100", "10")}
        asks = {Decimal("101"): ("101", "5")}
        last_event_time_utc = now

        def quality(self, *, now=None):
            return True, "valid"

    trades = [trade(index, now - timedelta(seconds=2), "BUY") for index in range(20)]
    flow = order_flow_features(trades, instrument=instrument(), through=now + timedelta(seconds=1))
    latest = candle(start=now - timedelta(minutes=1), index=0, high=101, low=99, close=99.2)
    result = book_features(
        DummyBook(),
        instrument=instrument(),
        through=now,
        flow=flow,
        latest_candle=latest,
    )
    assert result.available is True
    assert result.imbalance and result.imbalance > 0
    assert result.absorption == "SELL"

    class InvalidBook(DummyBook):
        def quality(self, *, now=None):
            return False, "checksum_mismatch"

    invalid = book_features(InvalidBook(), instrument=instrument(), through=now)
    assert invalid.available is False
    assert invalid.imbalance is None
