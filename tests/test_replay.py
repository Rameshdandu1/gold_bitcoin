import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from marketintel.delta import DeltaDataIntegrityError, parse_book_message, parse_trade_message
from marketintel.models import Candle
from marketintel.replay import (
    aggregate_trade_candles,
    finalized_candles,
    reconcile_candles,
    replay_order_book,
    replay_trade_records,
)

FIXTURES = Path(__file__).parent / "fixtures" / "delta"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def received_after(message, seconds=1):
    micros = message.get("ts", message.get("t"))
    return datetime.fromtimestamp(micros / 1_000_000, tz=UTC) + timedelta(seconds=seconds)


def trade(symbol, when, price, size=1, role="t"):
    event_micros = int(when.timestamp() * 1_000_000)
    message = {
        "type": "trades",
        "sy": symbol,
        "p": str(price),
        "s": size,
        "r": role,
        "t": event_micros,
        "ts": event_micros + 1_000,
    }
    return parse_trade_message(message, received_at=when + timedelta(milliseconds=2))[0]


def test_trade_replay_is_deterministic_and_excludes_open_candle():
    start = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    events = [
        trade("BTCUSD", start + timedelta(seconds=5), 100, 2),
        trade("BTCUSD", start + timedelta(seconds=40), 103, 3),
        trade("BTCUSD", start + timedelta(minutes=1, seconds=10), 102, 4, "m"),
        trade("BTCUSD", start + timedelta(minutes=2, seconds=5), 999, 1),
    ]
    through = start + timedelta(minutes=2, seconds=30)
    first = aggregate_trade_candles(events, symbol="BTCUSD", resolution="1m", through=through)
    second = aggregate_trade_candles(
        reversed(events), symbol="BTCUSD", resolution="1m", through=through
    )
    assert first == second
    assert len(first) == 2
    assert (first[0].open, first[0].high, first[0].low, first[0].close) == (
        100,
        103,
        100,
        103,
    )
    assert first[0].volume_contracts == 5
    assert all(candle.close != 999 for candle in first)


def test_trade_replay_deduplicates_event_id():
    start = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    event = trade("BTCUSD", start + timedelta(seconds=5), 100, 2)
    candles = aggregate_trade_candles(
        [event, event],
        symbol="BTCUSD",
        resolution="1m",
        through=start + timedelta(minutes=1),
    )
    assert candles[0].volume_contracts == 2


def test_trade_record_replay_is_deterministic_and_preserves_unknown_aggressor():
    start = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    buy = trade("BTCUSD", start + timedelta(seconds=5), 100, 2)
    unknown = trade("BTCUSD", start + timedelta(seconds=6), 101, 3, "unknown")
    first = replay_trade_records(
        [unknown, buy, buy], symbol="BTCUSD", through=start + timedelta(seconds=10)
    )
    second = replay_trade_records(
        [buy, unknown], symbol="BTCUSD", through=start + timedelta(seconds=10)
    )
    assert first == second
    assert [row.aggressor for row in first] == ["BUY", None]


def test_late_received_trade_does_not_leak_into_earlier_replay():
    event_time = datetime(2026, 11, 21, 12, 0, 5, tzinfo=UTC)
    event = trade("BTCUSD", event_time, 100, 2)
    late = event.model_copy(update={"received_at_utc": event_time + timedelta(minutes=2)})
    through = event_time + timedelta(minutes=1)
    assert replay_trade_records([late], symbol="BTCUSD", through=through) == []
    assert aggregate_trade_candles([late], symbol="BTCUSD", through=through) == []


def test_equal_exchange_timestamps_use_publish_order_for_open_close():
    when = datetime(2026, 11, 21, 12, 0, 5, tzinfo=UTC)
    event_micros = int(when.timestamp() * 1_000_000)
    events = []
    for price, publish_offset in ((100, 1_000), (105, 2_000)):
        message = {
            "type": "trades",
            "sy": "BTCUSD",
            "p": str(price),
            "s": 1,
            "r": "t",
            "t": event_micros,
            "ts": event_micros + publish_offset,
        }
        events.append(
            parse_trade_message(
                message, received_at=when + timedelta(microseconds=publish_offset + 1_000)
            )[0]
        )
    candles = aggregate_trade_candles(
        reversed(events),
        symbol="BTCUSD",
        resolution="1m",
        through=when.replace(second=0) + timedelta(minutes=1),
    )
    assert (candles[0].open, candles[0].close) == (100, 105)


def test_invalid_candle_clock_is_rejected():
    candle = Candle(
        symbol="BTCUSD",
        resolution="1m",
        open_time=datetime(2026, 11, 21, 12, 0, 1, tzinfo=UTC),
        open=100,
        high=101,
        low=99,
        close=100,
    )
    with pytest.raises(DeltaDataIntegrityError, match="resolution-aligned"):
        finalized_candles(
            [candle], resolution="1m", through=candle.open_time + timedelta(minutes=1)
        )


def test_rest_stream_reconciliation_reports_mismatch_without_filling():
    when = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    rest = Candle(
        symbol="BTCUSD",
        resolution="1m",
        open_time=when,
        open=100,
        high=102,
        low=99,
        close=101,
        volume_contracts=5,
    )
    streamed = rest.model_copy(update={"close": 100.5})
    result = reconcile_candles([rest], [streamed])
    assert result.valid is False
    assert result.matched == 0
    assert result.mismatched == (when,)


def test_reconciliation_reports_missing_candles_on_both_sides():
    when = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    candle = Candle(
        symbol="BTCUSD",
        resolution="1m",
        open_time=when,
        open=100,
        high=100,
        low=100,
        close=100,
    )
    later = candle.model_copy(update={"open_time": when + timedelta(minutes=1)})
    result = reconcile_candles([candle], [later])
    assert result.missing_from_stream == (when,)
    assert result.missing_from_rest == (later.open_time,)
    assert result.valid is False


def test_order_book_replay_uses_ingest_order_when_exchange_times_regress():
    fixture = load_fixture("websocket.json")
    snapshot = parse_book_message(
        fixture["book_snapshot"], received_at=received_after(fixture["book_snapshot"])
    )
    update = parse_book_message(
        fixture["book_update"], received_at=received_after(fixture["book_update"])
    )
    base = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    snapshot = snapshot.model_copy(
        update={
            "event_time_utc": base + timedelta(seconds=2),
            "received_at_utc": base + timedelta(seconds=2),
        }
    )
    update = update.model_copy(
        update={
            "event_time_utc": base + timedelta(seconds=1),
            "received_at_utc": base + timedelta(seconds=3),
        }
    )

    book = replay_order_book([update, snapshot], symbol="BTCUSD")
    assert book.valid is True
    assert book.last_sequence == update.sequence
