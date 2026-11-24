import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from marketintel.delta import (
    DeltaAPIError,
    DeltaDataIntegrityError,
    DeltaPublicStream,
    DeltaREST,
    OrderBookAssembler,
    discover_instruments,
    parse_book_message,
    parse_trade_message,
    trade_aggressor,
)

FIXTURES = Path(__file__).parent / "fixtures" / "delta"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def received_after(message, seconds=1):
    micros = message.get("ts", message.get("t"))
    return datetime.fromtimestamp(micros / 1_000_000, tz=UTC) + timedelta(seconds=seconds)


def test_discovers_live_btc_and_preferred_gold_with_units():
    discovery = discover_instruments(load_fixture("products.json"))
    assert discovery.btc and discovery.btc.symbol == "BTCUSD"
    assert discovery.gold and discovery.gold.symbol == "XAUTUSD"
    assert [item.symbol for item in discovery.gold_alternatives] == ["PAXGUSD"]
    assert discovery.btc.quote_notional(Decimal("2"), Decimal("70000")) == Decimal("140")


def test_delisted_preferred_gold_falls_back_without_fabrication():
    products = load_fixture("products.json")
    for product in products:
        if product["symbol"] == "XAUTUSD":
            product["state"] = "expired"
    discovery = discover_instruments(products)
    assert discovery.gold and discovery.gold.symbol == "PAXGUSD"


def test_missing_gold_is_explicitly_unavailable():
    products = [
        product
        for product in load_fixture("products.json")
        if product["underlying_asset"]["symbol"] not in {"XAUT", "PAXG"}
    ]
    discovery = discover_instruments(products)
    assert discovery.gold is None
    assert "GOLD" in discovery.unavailable


def test_wrong_contract_size_rejects_instrument():
    products = load_fixture("products.json")
    for product in products:
        if product["symbol"] == "BTCUSD":
            product["contract_value"] = "0"
    discovery = discover_instruments(products)
    assert discovery.btc is None
    assert discovery.invalid_product_count == 1


def test_mismatched_contract_unit_rejects_instrument():
    products = load_fixture("products.json")
    for product in products:
        if product["symbol"] == "BTCUSD":
            product["contract_unit_currency"] = "USD"
    discovery = discover_instruments(products)
    assert discovery.btc is None
    assert "unverified units" in discovery.unavailable["BTC"]


def test_inverse_or_base_settled_contract_is_rejected():
    products = load_fixture("products.json")
    for product in products:
        if product["symbol"] == "BTCUSD":
            product["notional_type"] = "inverse"
            product["settling_asset"] = {"symbol": "BTC", "precision": 8}
    discovery = discover_instruments(products)
    assert discovery.btc is None
    assert "unverified units" in discovery.unavailable["BTC"]


def test_aggressor_buyer_role_and_unknown_preserved():
    assert trade_aggressor({"r": "t"}) == "BUY"
    assert trade_aggressor({"r": "m"}) == "SELL"
    assert trade_aggressor({"r": "unknown"}) is None
    unknown = load_fixture("websocket.json")["trades"][2]
    _, trade = parse_trade_message(unknown, received_at=received_after(unknown))
    assert trade.aggressor is None


def test_stale_and_future_trade_timestamps_fail_closed():
    trade = load_fixture("websocket.json")["trades"][0]
    with pytest.raises(DeltaDataIntegrityError, match="stale"):
        parse_trade_message(trade, received_at=received_after(trade, seconds=121))

    event_time = datetime.fromtimestamp(trade["t"] / 1_000_000, tz=UTC)
    with pytest.raises(DeltaDataIntegrityError, match="future"):
        parse_trade_message(trade, received_at=event_time - timedelta(seconds=6))


def test_trade_window_deduplicates_and_orders_by_event_time():
    messages = load_fixture("websocket.json")["trades"]
    stream = DeltaPublicStream("wss://example.invalid", ["BTCUSD"])
    for message in messages:
        assert stream.ingest_message(message, received_at=received_after(message)) is not None
    assert stream.ingest_message(messages[0], received_at=received_after(messages[0])) is None
    summary = stream.trade_window_summary("BTCUSD", 500)
    assert summary
    assert summary.trade_count == 3
    assert summary.classified_trade_count == 2
    assert summary.unclassified_trade_count == 1
    assert summary.buy_contracts == Decimal("4.0")
    assert summary.sell_contracts == Decimal("6.0")
    assert summary.delta_contracts == Decimal("-2.0")
    assert summary.elapsed_seconds == Decimal("2.0")


def test_default_trade_buffer_is_true_rolling_5000():
    stream = DeltaPublicStream("wss://example.invalid", ["BTCUSD"])
    base = 1_775_800_000_000_000
    for index in range(5_001):
        message = {
            "type": "trades",
            "sy": "BTCUSD",
            "p": "70000",
            "s": 1,
            "r": "t",
            "t": base + index,
            "ts": base + index + 1,
        }
        stream.ingest_message(
            message,
            received_at=datetime.fromtimestamp((base + index + 2) / 1_000_000, tz=UTC),
        )
    assert len(stream.trades["BTCUSD"]) == 5_000
    assert stream.trade_window_summary("BTCUSD", 5_000).trade_count == 5_000
    assert stream.trade_window_summary("BTCUSD", 500).trade_count == 500


def test_malformed_trade_fails_contract_validation():
    message = deepcopy(load_fixture("websocket.json")["trades"][0])
    message["s"] = 0
    with pytest.raises(DeltaDataIntegrityError, match="trade size"):
        parse_trade_message(message, received_at=received_after(message))


def test_order_book_snapshot_update_and_zero_deletion():
    fixture = load_fixture("websocket.json")
    snapshot = parse_book_message(
        fixture["book_snapshot"], received_at=received_after(fixture["book_snapshot"])
    )
    update = parse_book_message(
        fixture["book_update"], received_at=received_after(fixture["book_update"])
    )
    book = OrderBookAssembler("BTCUSD")
    assert book.apply(snapshot) is True
    assert book.apply(update) is True
    assert book.valid is True
    assert Decimal("16919.0") not in book.asks
    assert book.top_of_book(now=update.event_time_utc + timedelta(seconds=1)) == (
        Decimal("16918.5"),
        Decimal("16919.5"),
    )


def test_book_sequence_gap_invalid_until_new_snapshot():
    fixture = load_fixture("websocket.json")
    snapshot_message = fixture["book_snapshot"]
    update_message = deepcopy(fixture["book_update"])
    update_message["seq"] = 6201
    book = OrderBookAssembler("BTCUSD")
    assert book.apply(
        parse_book_message(snapshot_message, received_at=received_after(snapshot_message))
    )
    assert not book.apply(
        parse_book_message(update_message, received_at=received_after(update_message))
    )
    assert book.reason == "sequence_gap_or_reorder"
    assert book.top_of_book() is None
    assert book.apply(
        parse_book_message(snapshot_message, received_at=received_after(snapshot_message))
    )


def test_duplicate_or_out_of_order_book_update_invalidates():
    fixture = load_fixture("websocket.json")
    book = OrderBookAssembler("BTCUSD")
    snapshot = parse_book_message(
        fixture["book_snapshot"], received_at=received_after(fixture["book_snapshot"])
    )
    assert book.apply(snapshot)
    update_message = deepcopy(fixture["book_update"])
    update_message["seq"] = fixture["book_snapshot"]["seq"]
    update = parse_book_message(update_message, received_at=received_after(update_message))
    assert book.apply(update) is False
    assert book.reason == "sequence_gap_or_reorder"
    assert book.top_of_book() is None
    assert book.apply(
        parse_book_message(
            fixture["book_snapshot"], received_at=received_after(fixture["book_snapshot"])
        )
    )


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"cs": 1}, "checksum_mismatch"),
        ({"b": []}, "missing_bid_or_ask"),
        ({"a": [["16918.0", "1"]]}, "crossed_or_locked_book"),
    ],
)
def test_impossible_book_snapshots_fail_closed(change, expected):
    message = deepcopy(load_fixture("websocket.json")["book_snapshot"])
    message.update(change)
    event = parse_book_message(message, received_at=received_after(message))
    book = OrderBookAssembler("BTCUSD")
    assert book.apply(event) is False
    assert book.reason == expected


def test_stale_book_snapshot_fails_closed():
    message = load_fixture("websocket.json")["book_snapshot"]
    event = parse_book_message(message, received_at=received_after(message, seconds=11))
    book = OrderBookAssembler("BTCUSD", max_age_seconds=10)
    assert book.apply(event) is False
    assert book.reason == "stale_event"


def test_valid_book_expires_when_feed_goes_quiet():
    message = load_fixture("websocket.json")["book_snapshot"]
    received_at = received_after(message)
    event = parse_book_message(message, received_at=received_at)
    book = OrderBookAssembler("BTCUSD", max_age_seconds=10)
    assert book.apply(event) is True

    later = event.event_time_utc + timedelta(seconds=11)
    assert book.quality(now=later) == (False, "stale_book")
    assert book.top_of_book(now=later) is None

    update = load_fixture("websocket.json")["book_update"]
    assert book.apply(parse_book_message(update, received_at=received_after(update))) is True


def test_book_received_after_evaluation_clock_is_not_available_yet():
    message = load_fixture("websocket.json")["book_snapshot"]
    received_at = received_after(message)
    book = OrderBookAssembler("BTCUSD", max_age_seconds=10)
    assert book.apply(parse_book_message(message, received_at=received_at)) is True

    evaluation_clock = received_at - timedelta(microseconds=1)
    assert book.quality(now=evaluation_clock) == (
        False,
        "received_after_evaluation_clock",
    )
    assert book.top_of_book(now=evaluation_clock) is None


def test_connection_generation_invalidates_all_books_until_fresh_snapshot():
    message = load_fixture("websocket.json")["book_snapshot"]
    stream = DeltaPublicStream("wss://example.invalid", ["BTCUSD"])
    received_at = received_after(message)
    stream.ingest_message(message, received_at=received_at)
    assert stream.book_quality("BTCUSD", now=received_at)[0] is True

    stream.invalidate_books("fresh_snapshot_required_after_disconnect")
    assert stream.book_quality("BTCUSD") == (
        False,
        "fresh_snapshot_required_after_disconnect",
    )
    assert stream.books["BTCUSD"].top_of_book() is None


def test_missing_book_sequence_rejected():
    message = deepcopy(load_fixture("websocket.json")["book_snapshot"])
    del message["seq"]
    with pytest.raises(DeltaDataIntegrityError, match="sequence"):
        parse_book_message(message, received_at=received_after(message))


def test_future_and_exchange_error_book_messages_fail_closed():
    snapshot = load_fixture("websocket.json")["book_snapshot"]
    event = parse_book_message(snapshot, received_at=received_after(snapshot, seconds=-11))
    book = OrderBookAssembler("BTCUSD", max_age_seconds=10)
    assert book.apply(event) is False
    assert book.reason == "event_time_too_far_in_future"

    error_event = parse_book_message(
        {"type": "ob_updates", "action": "error", "sy": "BTCUSD"},
        received_at=datetime.now(UTC),
    )
    assert book.apply(error_event) is False
    assert book.reason == "exchange_snapshot_error"


def test_subscription_uses_documented_incremental_book_channel():
    stream = DeltaPublicStream("wss://example.invalid", ["BTCUSD"])
    names = [item["name"] for item in stream.subscription_message()["payload"]["channels"]]
    assert names == ["trades", "ob_updates"]


@pytest.mark.asyncio
async def test_stream_reconnects_and_resubscribes(monkeypatch):
    trade = deepcopy(load_fixture("websocket.json")["trades"][0])
    event_micros = int(datetime.now(UTC).timestamp() * 1_000_000)
    trade["t"] = event_micros
    trade["ts"] = event_micros + 1_000
    sent = []
    statuses = []
    connection_count = 0

    class FakeSocket:
        def __init__(self):
            self.messages = [json.dumps(trade)]

        async def send(self, payload):
            sent.append(json.loads(payload))

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.messages:
                return self.messages.pop(0)
            raise StopAsyncIteration

    class FakeConnection:
        async def __aenter__(self):
            nonlocal connection_count
            connection_count += 1
            if connection_count == 1:
                raise OSError("fixture disconnect")
            return FakeSocket()

        async def __aexit__(self, *_args):
            return False

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr("marketintel.delta.websockets.connect", lambda *_a, **_k: FakeConnection())
    monkeypatch.setattr("marketintel.delta.asyncio.sleep", no_sleep)
    stream = DeltaPublicStream(
        "wss://example.invalid",
        ["BTCUSD"],
        status_callback=lambda state, detail: statuses.append((state, detail)),
    )
    iterator = stream.messages()
    event = await anext(iterator)
    await iterator.aclose()
    assert event.channel == "trades"
    assert connection_count == 2
    assert sent == [stream.subscription_message()]
    assert ("DISCONNECTED", "OSError") in statuses
    assert statuses[-1] == ("CONNECTED", "Validated public market event received")


def test_identical_connected_status_refreshes_throttled_health_heartbeat():
    statuses = []
    current = [datetime(2026, 11, 24, tzinfo=UTC)]
    stream = DeltaPublicStream(
        "wss://example.invalid",
        ["BTCUSD"],
        status_callback=lambda state, detail: statuses.append((state, detail)),
        status_heartbeat_seconds=5,
        clock=lambda: current[0],
    )

    stream._notify_connection_status("CONNECTED", "healthy")
    current[0] += timedelta(seconds=2)
    stream._notify_connection_status("CONNECTED", "healthy")
    current[0] += timedelta(seconds=4)
    stream._notify_connection_status("CONNECTED", "healthy")

    assert statuses == [("CONNECTED", "healthy"), ("CONNECTED", "healthy")]


@pytest.mark.asyncio
async def test_rest_rate_limit_retries_then_recovers(monkeypatch):
    calls = 0

    def handler(_request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"success": True, "result": load_fixture("products.json")})

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr("marketintel.delta.asyncio.sleep", no_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rest = DeltaREST("https://example.invalid", retries=1, client=client)
        products = await rest.products()
    assert calls == 2
    assert products[0]["symbol"] == "BTCUSD"


@pytest.mark.asyncio
async def test_rest_partial_outage_fails_after_bounded_retries(monkeypatch):
    calls = 0

    def handler(_request):
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"success": False})

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr("marketintel.delta.asyncio.sleep", no_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rest = DeltaREST("https://example.invalid", retries=2, client=client)
        with pytest.raises(DeltaAPIError, match="bounded retries"):
            await rest.products()
    assert calls == 3


@pytest.mark.asyncio
async def test_rest_non_retryable_4xx_fails_once_and_malformed_envelope_fails_closed():
    calls = 0

    def rejected(_request):
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"success": False, "error": "fixture"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(rejected)) as client:
        rest = DeltaREST("https://example.invalid", retries=3, client=client)
        with pytest.raises(DeltaAPIError, match="rejected"):
            await rest.products()
    assert calls == 1

    def malformed(_request):
        return httpx.Response(200, json=["not", "an", "envelope"])

    async with httpx.AsyncClient(transport=httpx.MockTransport(malformed)) as client:
        rest = DeltaREST("https://example.invalid", client=client)
        with pytest.raises(DeltaAPIError, match="Unsuccessful"):
            await rest.products()


@pytest.mark.asyncio
async def test_stream_recovers_from_corrupt_json_and_ignores_unknown_frames(monkeypatch):
    trade = deepcopy(load_fixture("websocket.json")["trades"][0])
    event_micros = int(datetime.now(UTC).timestamp() * 1_000_000)
    trade["t"] = event_micros
    trade["ts"] = event_micros + 1_000
    connection_count = 0

    class FakeSocket:
        def __init__(self, messages):
            self.messages = messages

        async def send(self, _payload):
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.messages:
                return self.messages.pop(0)
            raise StopAsyncIteration

    class FakeConnection:
        async def __aenter__(self):
            nonlocal connection_count
            connection_count += 1
            if connection_count == 1:
                return FakeSocket(["{corrupt-json"])
            return FakeSocket([json.dumps({"type": "heartbeat"}), json.dumps(trade)])

        async def __aexit__(self, *_args):
            return False

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr("marketintel.delta.websockets.connect", lambda *_a, **_k: FakeConnection())
    monkeypatch.setattr("marketintel.delta.asyncio.sleep", no_sleep)
    stream = DeltaPublicStream("wss://example.invalid", ["BTCUSD"])
    iterator = stream.messages()
    event = await anext(iterator)
    await iterator.aclose()
    assert event.channel == "trades"
    assert connection_count == 2


@pytest.mark.asyncio
async def test_stream_429_uses_extended_cooldown(monkeypatch):
    trade = deepcopy(load_fixture("websocket.json")["trades"][0])
    event_micros = int(datetime.now(UTC).timestamp() * 1_000_000)
    trade["t"] = event_micros
    trade["ts"] = event_micros + 1_000
    sleeps = []
    connection_count = 0

    class RateLimited(OSError):
        response = type("Response", (), {"status_code": 429})()

    class FakeSocket:
        async def send(self, _payload):
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            if getattr(self, "done", False):
                raise StopAsyncIteration
            self.done = True
            return json.dumps(trade)

    class FakeConnection:
        async def __aenter__(self):
            nonlocal connection_count
            connection_count += 1
            if connection_count == 1:
                raise RateLimited("fixture 429")
            return FakeSocket()

        async def __aexit__(self, *_args):
            return False

    async def record_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("marketintel.delta.websockets.connect", lambda *_a, **_k: FakeConnection())
    monkeypatch.setattr("marketintel.delta.asyncio.sleep", record_sleep)
    monkeypatch.setattr("marketintel.delta.random.uniform", lambda *_args: 0)
    stream = DeltaPublicStream("wss://example.invalid", ["BTCUSD"])
    iterator = stream.messages()
    await anext(iterator)
    await iterator.aclose()
    assert sleeps[0] == 300


@pytest.mark.asyncio
async def test_rest_history_validates_rows_and_time_bounds():
    start = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    end = start + timedelta(minutes=1)

    def handler(_request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": [
                    {
                        "time": int(start.timestamp()),
                        "open": 100,
                        "high": 102,
                        "low": 99,
                        "close": 101,
                        "volume": 3,
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rest = DeltaREST("https://example.invalid", client=client)
        candles = await rest.historical_candles("BTCUSD", "1m", start, end)
    assert candles[0].open_time == start
    assert candles[0].volume_contracts == 3
    with pytest.raises(ValueError, match="start must be before end"):
        await rest.historical_candles("BTCUSD", "1m", end, start)


@pytest.mark.asyncio
async def test_rest_history_rejects_malformed_candle_row():
    start = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)

    def handler(_request):
        return httpx.Response(200, json={"success": True, "result": [{"open": 100}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rest = DeltaREST("https://example.invalid", client=client)
        with pytest.raises(DeltaAPIError, match="timestamp"):
            await rest.historical_candles("BTCUSD", "1m", start, start + timedelta(minutes=1))
