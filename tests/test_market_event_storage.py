import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from marketintel.delta import parse_trade_message
from marketintel.replay import aggregate_trade_candles
from marketintel.storage import Store

FIXTURES = Path(__file__).parent / "fixtures" / "delta"


def fixture_trade():
    payload = json.loads((FIXTURES / "websocket.json").read_text(encoding="utf-8"))
    return payload["trades"][0]


def test_raw_event_is_idempotent_and_replayable(tmp_path):
    message = fixture_trade()
    received = datetime.fromtimestamp(message["ts"] / 1_000_000, tz=UTC) + timedelta(seconds=1)
    event, _ = parse_trade_message(message, received_at=received)
    store = Store(tmp_path / "events.sqlite3")
    assert store.append_raw_event(event) is True
    assert store.append_raw_event(event) is False
    loaded = store.raw_events(symbol="BTCUSD", channels=("trades",))
    assert loaded == [event]


def test_raw_event_rows_cannot_be_updated_or_deleted(tmp_path):
    message = fixture_trade()
    received = datetime.fromtimestamp(message["ts"] / 1_000_000, tz=UTC)
    event, _ = parse_trade_message(message, received_at=received)
    path = tmp_path / "events.sqlite3"
    store = Store(path)
    store.append_raw_event(event)
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE raw_market_events SET symbol='OTHER' WHERE event_id=?",
                (event.event_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM raw_market_events WHERE event_id=?", (event.event_id,))


def test_source_status_history_is_append_only_and_timestamped(tmp_path):
    store = Store(tmp_path / "events.sqlite3")
    when = datetime(2026, 11, 21, 10, 0, tzinfo=UTC)
    assert store.record_source_status("delta_rest", "RATE_LIMITED", "HTTP 429", occurred_at=when)
    assert not store.record_source_status(
        "delta_rest", "RATE_LIMITED", "HTTP 429", occurred_at=when
    )
    assert store.source_status_history("delta_rest") == [
        {
            "event_id": store.source_status_history("delta_rest")[0]["event_id"],
            "occurred_at_utc": when.isoformat(),
            "source": "delta_rest",
            "state": "RATE_LIMITED",
            "detail": "HTTP 429",
        }
    ]


def test_raw_event_time_filter_requires_aware_clock(tmp_path):
    store = Store(tmp_path / "events.sqlite3")
    with pytest.raises(ValueError, match="timezone aware"):
        store.raw_events(start=datetime(2026, 1, 1))


def test_parse_persist_replay_closed_candle_vertical_slice(tmp_path):
    store = Store(tmp_path / "events.sqlite3")
    start = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    for offset, price in ((5, "100"), (35, "102")):
        event_time = start + timedelta(seconds=offset)
        micros = int(event_time.timestamp() * 1_000_000)
        message = {
            "type": "trades",
            "sy": "BTCUSD",
            "p": price,
            "s": 2,
            "r": "t",
            "t": micros,
            "ts": micros + 1_000,
        }
        event, _ = parse_trade_message(message, received_at=event_time + timedelta(milliseconds=2))
        assert store.append_raw_event(event)
    replayed = aggregate_trade_candles(
        store.raw_events(symbol="BTCUSD"),
        symbol="BTCUSD",
        through=start + timedelta(minutes=1),
    )
    assert len(replayed) == 1
    assert replayed[0].open == 100
    assert replayed[0].close == 102
    assert replayed[0].volume_contracts == 4
