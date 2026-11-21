"""Delta Exchange India public REST/WS connectors. No trading API functions."""

import asyncio
import hashlib
import heapq
import json
import logging
import random
import zlib
from collections import defaultdict
from collections.abc import AsyncIterator, Callable, Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import websockets
from pydantic import ValidationError

from marketintel.models import (
    Candle,
    DeltaProduct,
    Instrument,
    InstrumentDiscovery,
    RawMarketEvent,
    TradeRecord,
    TradeWindow,
)

LOGGER = logging.getLogger(__name__)
LINEAR_CONTRACT_TYPES = {"futures", "perpetual_futures"}
GOLD_UNDERLYINGS = {"XAUT", "PAXG"}
TRADE_MAX_AGE_SECONDS = 120.0
TRADE_MAX_FUTURE_SKEW_SECONDS = 5.0


class DeltaAPIError(Exception):
    """Transient or invalid public market-data response."""


class DeltaDataIntegrityError(Exception):
    """A public market-data message cannot be used safely."""


class DeltaStreamResyncRequired(DeltaDataIntegrityError):
    """The incremental order book must be rebuilt from a new snapshot."""


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone aware")


def _microseconds_to_utc(value: Any, name: str) -> datetime:
    try:
        micros = int(value)
    except (TypeError, ValueError) as exc:
        raise DeltaDataIntegrityError(f"{name} must be an epoch-microsecond integer") from exc
    if micros <= 0:
        raise DeltaDataIntegrityError(f"{name} must be positive")
    try:
        return datetime.fromtimestamp(micros / 1_000_000, tz=UTC)
    except (OSError, OverflowError, ValueError) as exc:
        raise DeltaDataIntegrityError(f"{name} is outside the supported timestamp range") from exc


def _positive_decimal(value: Any, name: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DeltaDataIntegrityError(f"{name} must be decimal-compatible") from exc
    if not number.is_finite() or number <= 0:
        raise DeltaDataIntegrityError(f"{name} must be positive and finite")
    return number


def _event_id(message: dict[str, Any]) -> str:
    canonical = json.dumps(message, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_product_catalog(rows: Iterable[Any]) -> tuple[list[DeltaProduct], int]:
    """Validate individual products without allowing one bad row to hide valid markets."""
    products: list[DeltaProduct] = []
    invalid_count = 0
    for row in rows:
        try:
            products.append(DeltaProduct.model_validate(row))
        except ValidationError:
            invalid_count += 1
    return products, invalid_count


def discover_instruments(
    rows: Iterable[Any],
    *,
    btc_symbol: str = "BTCUSD",
    preferred_gold_symbol: str | None = "XAUTUSD",
) -> InstrumentDiscovery:
    """Resolve live linear BTC and tokenized-gold markets from product metadata."""
    products, invalid_count = parse_product_catalog(rows)
    unavailable: dict[str, str] = {}

    btc: Instrument | None = None
    btc_matches = [product for product in products if product.symbol == btc_symbol]
    for product in btc_matches:
        try:
            candidate = Instrument.from_product(product)
        except ValueError:
            continue
        if (
            candidate.underlying_asset == "BTC"
            and candidate.quoting_asset == "USD"
            and candidate.contract_type in LINEAR_CONTRACT_TYPES
        ):
            btc = candidate
            break
    if btc is None:
        unavailable["BTC"] = f"{btc_symbol} is absent, inactive, or has unverified units"

    gold_candidates: list[Instrument] = []
    for product in products:
        if product.underlying_asset.symbol not in GOLD_UNDERLYINGS:
            continue
        try:
            candidate = Instrument.from_product(product)
        except ValueError:
            continue
        if candidate.quoting_asset == "USD" and candidate.contract_type in LINEAR_CONTRACT_TYPES:
            gold_candidates.append(candidate)
    gold_candidates.sort(
        key=lambda item: (
            0 if preferred_gold_symbol and item.symbol == preferred_gold_symbol else 1,
            item.symbol,
        )
    )
    gold = gold_candidates[0] if gold_candidates else None
    if gold is None:
        unavailable["GOLD"] = "No live operational XAUT/PAXG linear USD contract was discovered"

    return InstrumentDiscovery(
        btc=btc,
        gold=gold,
        gold_alternatives=gold_candidates[1:] if gold is not None else [],
        unavailable=unavailable,
        invalid_product_count=invalid_count,
    )


class DeltaREST:
    def __init__(
        self,
        base_url: str,
        timeout: float = 12,
        *,
        retries: int = 2,
        client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = max(retries, 0)
        self.client = client

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        owned_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.timeout)
        try:
            for attempt in range(self.retries + 1):
                try:
                    response = await client.get(
                        self.base_url + path,
                        params=params,
                        headers={"Accept": "application/json"},
                    )
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt >= self.retries:
                            raise DeltaAPIError(
                                "Delta "
                                f"{path} failed after bounded retries ({response.status_code})"
                            )
                        retry_after = response.headers.get("Retry-After")
                        delay = min(float(retry_after), 30.0) if retry_after else 2**attempt
                        await asyncio.sleep(max(delay, 0.1))
                        continue
                    response.raise_for_status()
                    payload = response.json()
                except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
                    if attempt >= self.retries:
                        raise DeltaAPIError(f"Delta request failed for {path}") from exc
                    await asyncio.sleep(2**attempt)
                    continue
                if not isinstance(payload, dict) or not payload.get("success", False):
                    raise DeltaAPIError(f"Unsuccessful Delta response from {path}")
                return payload.get("result")
        finally:
            if owned_client:
                await client.aclose()
        raise DeltaAPIError(f"Delta request did not complete for {path}")

    async def products(self) -> list[Any]:
        value = await self._get("/v2/products")
        if not isinstance(value, list):
            raise DeltaAPIError("Unexpected product-list schema")
        return value

    async def discover_instruments(
        self,
        *,
        btc_symbol: str = "BTCUSD",
        preferred_gold_symbol: str | None = "XAUTUSD",
    ) -> InstrumentDiscovery:
        return discover_instruments(
            await self.products(),
            btc_symbol=btc_symbol,
            preferred_gold_symbol=preferred_gold_symbol,
        )

    async def valid_symbols(self, wanted: list[str]) -> tuple[list[str], list[str]]:
        """Compatibility helper backed by strict product discovery semantics."""
        products, _ = parse_product_catalog(await self.products())
        actual: set[str] = set()
        for product in products:
            try:
                Instrument.from_product(product)
            except ValueError:
                continue
            actual.add(product.symbol)
        return [symbol for symbol in wanted if symbol in actual], [
            symbol for symbol in wanted if symbol not in actual
        ]

    async def historical_candles(
        self, symbol: str, resolution: str, start: datetime, end: datetime
    ) -> list[Candle]:
        _aware(start, "start")
        _aware(end, "end")
        if start >= end:
            raise ValueError("Historical candle start must be before end")
        result = await self._get(
            "/v2/history/candles",
            {
                "resolution": resolution,
                "symbol": symbol,
                "start": int(start.timestamp()),
                "end": int(end.timestamp()),
            },
        )
        if not isinstance(result, list):
            raise DeltaAPIError("Unexpected historical candle schema")
        candles: list[Candle] = []
        for raw in result:
            if not isinstance(raw, dict):
                raise DeltaAPIError("Candle row must be an object")
            epoch = raw.get("time", raw.get("t"))
            if epoch is None:
                raise DeltaAPIError("Candle has no documented timestamp")
            try:
                candles.append(
                    Candle(
                        symbol=symbol,
                        resolution=resolution,
                        open_time=datetime.fromtimestamp(float(epoch), tz=UTC),
                        open=float(raw["open"]),
                        high=float(raw["high"]),
                        low=float(raw["low"]),
                        close=float(raw["close"]),
                        volume_contracts=float(raw.get("volume", 0)),
                    )
                )
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                raise DeltaAPIError("Invalid historical candle row") from exc
        return sorted(candles, key=lambda candle: candle.open_time)


def trade_aggressor(trade: dict[str, Any]) -> str | None:
    """``r`` is the buyer role: taker means buy aggressor, maker means sell."""
    role = trade.get("r")
    return "BUY" if role == "t" else "SELL" if role == "m" else None


def parse_trade_message(
    message: dict[str, Any], *, received_at: datetime | None = None
) -> tuple[RawMarketEvent, TradeRecord]:
    received_at = received_at or datetime.now(UTC)
    _aware(received_at, "received_at")
    if message.get("type") != "trades" or not isinstance(message.get("sy"), str):
        raise DeltaDataIntegrityError("Not a Delta trades message")
    price = _positive_decimal(message.get("p"), "trade price")
    contracts = _positive_decimal(message.get("s"), "trade size")
    event_time = _microseconds_to_utc(message.get("t"), "trade time")
    publish_time = _microseconds_to_utc(message.get("ts"), "trade publish time")
    event_age = (received_at - event_time).total_seconds()
    if event_age > TRADE_MAX_AGE_SECONDS:
        raise DeltaDataIntegrityError("Trade event is stale")
    if event_age < -TRADE_MAX_FUTURE_SKEW_SECONDS:
        raise DeltaDataIntegrityError("Trade event time is too far in the future")
    if publish_time < event_time:
        raise DeltaDataIntegrityError("Trade publish time precedes event time")
    event_id = _event_id(message)
    event = RawMarketEvent(
        event_id=event_id,
        symbol=message["sy"],
        channel="trades",
        event_time_utc=event_time,
        received_at_utc=received_at,
        publish_time_utc=publish_time,
        payload=message,
    )
    return event, TradeRecord(
        event_id=event_id,
        symbol=message["sy"],
        price=price,
        contracts=contracts,
        aggressor=trade_aggressor(message),
        event_time_utc=event_time,
        received_at_utc=received_at,
        publish_time_utc=publish_time,
    )


def _validate_levels(value: Any, name: str) -> None:
    if not isinstance(value, list):
        raise DeltaDataIntegrityError(f"{name} must be a list")
    for level in value:
        if not isinstance(level, list) or len(level) != 2:
            raise DeltaDataIntegrityError(f"{name} levels must be [price, size]")
        _positive_decimal(level[0], f"{name} price")
        try:
            size = Decimal(str(level[1]))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise DeltaDataIntegrityError(f"{name} size must be decimal-compatible") from exc
        if not size.is_finite() or size < 0:
            raise DeltaDataIntegrityError(f"{name} size must be finite and non-negative")


def parse_book_message(
    message: dict[str, Any], *, received_at: datetime | None = None
) -> RawMarketEvent:
    received_at = received_at or datetime.now(UTC)
    _aware(received_at, "received_at")
    if message.get("type") != "ob_updates":
        raise DeltaDataIntegrityError("Not a Delta ob_updates message")
    action = message.get("action")
    symbol = message.get("sy", message.get("symbol"))
    if not isinstance(symbol, str) or action not in {"snapshot", "update", "error"}:
        raise DeltaDataIntegrityError("Invalid ob_updates action or symbol")
    if action == "error":
        return RawMarketEvent(
            event_id=_event_id(message),
            symbol=symbol,
            channel="ob_updates",
            event_time_utc=received_at,
            received_at_utc=received_at,
            payload=message,
        )
    _validate_levels(message.get("a"), "asks")
    _validate_levels(message.get("b"), "bids")
    try:
        sequence = int(message["seq"])
        checksum = int(message["cs"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DeltaDataIntegrityError("Book sequence and checksum are required") from exc
    event_time = _microseconds_to_utc(message.get("ts"), "book update time")
    return RawMarketEvent(
        event_id=_event_id(message),
        symbol=symbol,
        channel="ob_updates",
        event_time_utc=event_time,
        received_at_utc=received_at,
        sequence=sequence,
        checksum=checksum,
        payload=message,
    )


class OrderBookAssembler:
    """Fail-closed local book for Delta ``ob_updates`` snapshots and deltas."""

    def __init__(self, symbol: str, *, max_age_seconds: float = 10.0):
        if max_age_seconds <= 0:
            raise ValueError("Book maximum age must be positive")
        self.symbol = symbol
        self.max_age_seconds = max_age_seconds
        self.asks: dict[Decimal, tuple[str, str]] = {}
        self.bids: dict[Decimal, tuple[str, str]] = {}
        self.last_sequence: int | None = None
        self.last_event_time_utc: datetime | None = None
        self.valid = False
        self.reason = "snapshot_required"

    def _invalidate(self, reason: str) -> bool:
        self.valid = False
        self.reason = reason
        self.asks.clear()
        self.bids.clear()
        return False

    @staticmethod
    def _replace_levels(
        current: dict[Decimal, tuple[str, str]], updates: list[list[Any]]
    ) -> dict[Decimal, tuple[str, str]]:
        result = current.copy()
        for raw_price, raw_size in updates:
            price_text = str(raw_price)
            size_text = str(raw_size)
            price = Decimal(price_text)
            size = Decimal(size_text)
            if size == 0:
                result.pop(price, None)
            else:
                result[price] = (price_text, size_text)
        return result

    @staticmethod
    def _checksum(
        asks: dict[Decimal, tuple[str, str]], bids: dict[Decimal, tuple[str, str]]
    ) -> int:
        ask_levels = [asks[price] for price in sorted(asks)[:10]]
        bid_levels = [bids[price] for price in sorted(bids, reverse=True)[:10]]
        ask_text = ",".join(f"{price}:{size}" for price, size in ask_levels)
        bid_text = ",".join(f"{price}:{size}" for price, size in bid_levels)
        return zlib.crc32(f"{ask_text}|{bid_text}".encode()) & 0xFFFFFFFF

    def apply(self, event: RawMarketEvent) -> bool:
        if event.channel != "ob_updates" or event.symbol != self.symbol:
            return self._invalidate("wrong_channel_or_symbol")
        payload = event.payload
        action = payload.get("action")
        if action == "error":
            return self._invalidate("exchange_snapshot_error")
        if action not in {"snapshot", "update"}:
            return self._invalidate("unknown_action")
        age = (event.received_at_utc - event.event_time_utc).total_seconds()
        if age > self.max_age_seconds:
            return self._invalidate("stale_event")
        if age < -self.max_age_seconds:
            return self._invalidate("event_time_too_far_in_future")
        if event.sequence is None or event.checksum is None:
            return self._invalidate("missing_sequence_or_checksum")
        if action == "update" and not self.valid:
            return self._invalidate("snapshot_required")
        if action == "update" and event.sequence != (self.last_sequence or 0) + 1:
            return self._invalidate("sequence_gap_or_reorder")

        base_asks = {} if action == "snapshot" else self.asks
        base_bids = {} if action == "snapshot" else self.bids
        asks = self._replace_levels(base_asks, payload["a"])
        bids = self._replace_levels(base_bids, payload["b"])
        if not asks or not bids:
            return self._invalidate("missing_bid_or_ask")
        if max(bids) >= min(asks):
            return self._invalidate("crossed_or_locked_book")
        if self._checksum(asks, bids) != event.checksum:
            return self._invalidate("checksum_mismatch")

        self.asks = asks
        self.bids = bids
        self.last_sequence = event.sequence
        self.last_event_time_utc = event.event_time_utc
        self.valid = True
        self.reason = "valid"
        return True

    def quality(self, *, now: datetime | None = None) -> tuple[bool, str]:
        """Re-evaluate freshness so an idle feed cannot leave a book trusted forever."""
        if not self.valid:
            return False, self.reason
        now = now or datetime.now(UTC)
        _aware(now, "now")
        if self.last_event_time_utc is None:
            return self._invalidate("missing_event_time"), self.reason
        age = (now - self.last_event_time_utc).total_seconds()
        if age > self.max_age_seconds:
            return False, "stale_book"
        if age < -self.max_age_seconds:
            return False, "event_time_too_far_in_future"
        return True, "valid"

    def top_of_book(self, *, now: datetime | None = None) -> tuple[Decimal, Decimal] | None:
        if not self.quality(now=now)[0] or not self.bids or not self.asks:
            return None
        return max(self.bids), min(self.asks)


class DeltaPublicStream:
    """Bounded public stream with typed events and fail-closed book integrity."""

    def __init__(
        self,
        url: str,
        symbols: list[str],
        window: int = 5000,
        *,
        book_max_age_seconds: float = 10.0,
        status_callback: Callable[[str, str], None] | None = None,
    ):
        if window < 1:
            raise ValueError("Trade window must be positive")
        self.url = url
        self.symbols = list(dict.fromkeys(symbols))
        self.window = window
        self.book_max_age_seconds = book_max_age_seconds
        self.status_callback = status_callback
        self._last_connection_status: tuple[str, str] | None = None
        self.trades: dict[str, dict[str, TradeRecord]] = defaultdict(dict)
        self.trade_order: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
        self.books = {
            symbol: OrderBookAssembler(symbol, max_age_seconds=book_max_age_seconds)
            for symbol in self.symbols
        }
        self.last_seen_utc: datetime | None = None

    def _notify_connection_status(self, state: str, detail: str) -> None:
        status = (state, detail)
        if status == self._last_connection_status:
            return
        self._last_connection_status = status
        if self.status_callback is not None:
            self.status_callback(state, detail)

    def mark_stale(self, detail: str) -> None:
        """Expose a monitor-detected idle feed through the same transition channel."""
        self._notify_connection_status("STALE", detail)

    def subscription_message(self) -> dict[str, Any]:
        return {
            "type": "subscribe",
            "payload": {
                "channels": [
                    {"name": name, "symbols": self.symbols} for name in ("trades", "ob_updates")
                ]
            },
        }

    def ingest_message(
        self, message: dict[str, Any], *, received_at: datetime | None = None
    ) -> RawMarketEvent | None:
        symbol = message.get("sy", message.get("symbol"))
        if symbol not in self.symbols:
            return None
        received_at = received_at or datetime.now(UTC)
        msg_type = message.get("type")
        if msg_type == "trades":
            event, trade = parse_trade_message(message, received_at=received_at)
            bucket = self.trades[symbol]
            if event.event_id in bucket:
                return None
            bucket[event.event_id] = trade
            heapq.heappush(self.trade_order[symbol], (trade.event_time_utc, trade.event_id))
            if len(bucket) > self.window:
                while len(bucket) > self.window:
                    _, oldest_id = heapq.heappop(self.trade_order[symbol])
                    bucket.pop(oldest_id, None)
        elif msg_type == "ob_updates":
            event = parse_book_message(message, received_at=received_at)
            self.books[symbol].apply(event)
        else:
            return None
        self.last_seen_utc = received_at
        return event

    def trade_window_summary(self, symbol: str, last_n: int = 5000) -> TradeWindow | None:
        if last_n < 1:
            raise ValueError("last_n must be positive")
        trades = sorted(
            self.trades.get(symbol, {}).values(),
            key=lambda item: (item.event_time_utc, item.event_id),
        )[-last_n:]
        if not trades:
            return None
        buy = sum((trade.contracts for trade in trades if trade.aggressor == "BUY"), Decimal("0"))
        sell = sum((trade.contracts for trade in trades if trade.aggressor == "SELL"), Decimal("0"))
        classified = sum(trade.aggressor is not None for trade in trades)
        elapsed = Decimal(
            str((trades[-1].event_time_utc - trades[0].event_time_utc).total_seconds())
        )
        return TradeWindow(
            symbol=symbol,
            requested_size=last_n,
            trade_count=len(trades),
            classified_trade_count=classified,
            unclassified_trade_count=len(trades) - classified,
            buy_contracts=buy,
            sell_contracts=sell,
            delta_contracts=buy - sell,
            elapsed_seconds=max(elapsed, Decimal("0")),
        )

    def trade_delta_contracts(self, symbol: str, last_n: int = 5000) -> Decimal | None:
        summary = self.trade_window_summary(symbol, last_n)
        return summary.delta_contracts if summary is not None else None

    def book_quality(self, symbol: str, *, now: datetime | None = None) -> tuple[bool, str]:
        book = self.books.get(symbol)
        return book.quality(now=now) if book else (False, "unknown_symbol")

    async def messages(self) -> AsyncIterator[RawMarketEvent]:
        if not self.symbols:
            return
        backoff = 1.0
        while True:
            disconnect_detail = "stream_ended"
            self._notify_connection_status("CONNECTING", "Opening Delta public WebSocket")
            try:
                async with websockets.connect(
                    self.url,
                    ping_interval=20,
                    ping_timeout=15,
                    open_timeout=15,
                    close_timeout=5,
                    max_size=4_000_000,
                    max_queue=1024,
                ) as socket:
                    await socket.send(json.dumps(self.subscription_message()))
                    async for raw in socket:
                        parsed = json.loads(raw)
                        if not isinstance(parsed, dict):
                            continue
                        event = self.ingest_message(parsed, received_at=datetime.now(UTC))
                        if event is None:
                            continue
                        book_valid = event.channel != "ob_updates" or self.books[event.symbol].valid
                        if book_valid:
                            self._notify_connection_status(
                                "CONNECTED", "Validated public market event received"
                            )
                        yield event
                        if not book_valid:
                            raise DeltaStreamResyncRequired(self.books[event.symbol].reason)
                        if self.books and all(book.valid for book in self.books.values()):
                            backoff = 1.0
            except asyncio.CancelledError:
                raise
            except (
                OSError,
                ValueError,
                DeltaDataIntegrityError,
                websockets.exceptions.WebSocketException,
            ) as exc:
                disconnect_detail = type(exc).__name__
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code == 429:
                    backoff = max(backoff, 300.0)
                LOGGER.warning("Delta public stream disconnected: %s", type(exc).__name__)
            self._notify_connection_status("DISCONNECTED", disconnect_detail)
            jitter = random.uniform(0, min(backoff * 0.2, 5.0))
            await asyncio.sleep(backoff + jitter)
            backoff = min(backoff * 2, 600.0 if backoff >= 300 else 60.0)


def is_event_stale(
    event: RawMarketEvent, *, now: datetime | None = None, max_age_seconds: float = 10.0
) -> bool:
    now = now or datetime.now(UTC)
    _aware(now, "now")
    return now - event.event_time_utc > timedelta(seconds=max_age_seconds)
