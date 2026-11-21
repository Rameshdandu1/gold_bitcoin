"""Deterministic event-time replay for M1 market-data verification."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from marketintel.delta import DeltaDataIntegrityError, OrderBookAssembler, parse_trade_message
from marketintel.models import Candle, RawMarketEvent

RESOLUTION_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1_800,
    "1h": 3_600,
    "2h": 7_200,
    "4h": 14_400,
}


@dataclass(frozen=True)
class CandleReconciliation:
    matched: int
    missing_from_stream: tuple[datetime, ...]
    missing_from_rest: tuple[datetime, ...]
    mismatched: tuple[datetime, ...]

    @property
    def valid(self) -> bool:
        return not (self.missing_from_stream or self.missing_from_rest or self.mismatched)


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone aware")


def finalized_candles(
    candles: Sequence[Candle], *, resolution: str, through: datetime
) -> list[Candle]:
    """Return only aligned, unique candles closed by the supplied event-time clock."""
    _require_aware(through, "through")
    seconds = RESOLUTION_SECONDS.get(resolution)
    if seconds is None:
        raise ValueError(f"Unsupported resolution: {resolution}")
    ordered = sorted(candles, key=lambda candle: candle.open_time)
    seen: set[datetime] = set()
    finalized: list[Candle] = []
    for candle in ordered:
        _require_aware(candle.open_time, "candle.open_time")
        if candle.resolution != resolution:
            raise DeltaDataIntegrityError("Candle resolution does not match requested clock")
        normalized = candle.open_time.astimezone(UTC)
        if normalized.microsecond or int(normalized.timestamp()) % seconds:
            raise DeltaDataIntegrityError("Candle open time is not resolution-aligned")
        if normalized in seen:
            raise DeltaDataIntegrityError("Duplicate candle open time")
        seen.add(normalized)
        if normalized + timedelta(seconds=seconds) <= through.astimezone(UTC):
            finalized.append(candle)
    return finalized


def aggregate_trade_candles(
    events: Iterable[RawMarketEvent],
    *,
    symbol: str,
    resolution: str = "1m",
    through: datetime,
) -> list[Candle]:
    """Aggregate persisted executed trades without emitting an in-progress candle."""
    _require_aware(through, "through")
    seconds = RESOLUTION_SECONDS.get(resolution)
    if seconds is None:
        raise ValueError(f"Unsupported resolution: {resolution}")
    unique: dict[str, RawMarketEvent] = {}
    for event in events:
        if event.channel == "trades" and event.symbol == symbol:
            unique[event.event_id] = event
    ordered = sorted(
        unique.values(),
        key=lambda event: (
            event.event_time_utc,
            event.publish_time_utc or event.event_time_utc,
            event.received_at_utc,
            event.event_id,
        ),
    )
    buckets: dict[datetime, list[tuple[Decimal, Decimal]]] = {}
    for event in ordered:
        if event.event_time_utc > through:
            continue
        _, trade = parse_trade_message(event.payload, received_at=event.received_at_utc)
        epoch = int(trade.event_time_utc.timestamp())
        bucket_epoch = epoch - (epoch % seconds)
        bucket = datetime.fromtimestamp(bucket_epoch, tz=UTC)
        buckets.setdefault(bucket, []).append((trade.price, trade.contracts))

    candles: list[Candle] = []
    for open_time in sorted(buckets):
        if open_time + timedelta(seconds=seconds) > through.astimezone(UTC):
            continue
        rows = buckets[open_time]
        prices = [price for price, _ in rows]
        volume = sum((contracts for _, contracts in rows), Decimal("0"))
        candles.append(
            Candle(
                symbol=symbol,
                resolution=resolution,
                open_time=open_time,
                open=float(prices[0]),
                high=float(max(prices)),
                low=float(min(prices)),
                close=float(prices[-1]),
                volume_contracts=float(volume),
                source="delta_india_trade_replay",
            )
        )
    return candles


def reconcile_candles(
    rest: Sequence[Candle], streamed: Sequence[Candle], *, tolerance: float = 1e-9
) -> CandleReconciliation:
    """Compare finalized REST and streamed OHLCV without filling either source."""
    rest_by_time = {candle.open_time.astimezone(UTC): candle for candle in rest}
    stream_by_time = {candle.open_time.astimezone(UTC): candle for candle in streamed}
    shared = sorted(rest_by_time.keys() & stream_by_time.keys())
    mismatched: list[datetime] = []
    for open_time in shared:
        left = rest_by_time[open_time]
        right = stream_by_time[open_time]
        pairs = (
            (left.open, right.open),
            (left.high, right.high),
            (left.low, right.low),
            (left.close, right.close),
            (left.volume_contracts, right.volume_contracts),
        )
        if (
            left.symbol != right.symbol
            or left.resolution != right.resolution
            or any(abs(first - second) > tolerance for first, second in pairs)
        ):
            mismatched.append(open_time)
    return CandleReconciliation(
        matched=len(shared) - len(mismatched),
        missing_from_stream=tuple(sorted(rest_by_time.keys() - stream_by_time.keys())),
        missing_from_rest=tuple(sorted(stream_by_time.keys() - rest_by_time.keys())),
        mismatched=tuple(mismatched),
    )


def replay_order_book(
    events: Iterable[RawMarketEvent], *, symbol: str, max_age_seconds: float = 10.0
) -> OrderBookAssembler:
    """Rebuild the book in deterministic event/sequence order for diagnostics."""
    book = OrderBookAssembler(symbol, max_age_seconds=max_age_seconds)
    ordered = sorted(
        (event for event in events if event.channel == "ob_updates" and event.symbol == symbol),
        key=lambda event: (
            event.received_at_utc,
            event.sequence if event.sequence is not None else -1,
            event.event_id,
        ),
    )
    for event in ordered:
        book.apply(event)
    return book
