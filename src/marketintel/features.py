"""Deterministic, closed-candle quantitative features shared by all six M2 engines."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import Protocol

from marketintel.indicators import average_true_range
from marketintel.models import (
    BookFeatures,
    Candle,
    CoverageWindow,
    Direction,
    ExternalMetric,
    FeatureSnapshot,
    FlowWindow,
    Instrument,
    LiquidityLevel,
    MarketRegime,
    OrderFlowFeatures,
    StructureEvent,
    StructureKind,
    TradeRecord,
    VolatilityBudget,
)

RESOLUTION_MINUTES = {
    "1m": 1,
    "3m": 3,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
}


class FeatureIntegrityError(ValueError):
    """Raised when a feature would otherwise hide missing or future data."""


class BookView(Protocol):
    bids: dict[Decimal, tuple[str, str]]
    asks: dict[Decimal, tuple[str, str]]
    last_event_time_utc: datetime | None

    def quality(self, *, now: datetime | None = None) -> tuple[bool, str]: ...


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise FeatureIntegrityError(f"{name} must be timezone aware")


def candle_close(candle: Candle) -> datetime:
    minutes = RESOLUTION_MINUTES.get(candle.resolution)
    if minutes is None:
        raise FeatureIntegrityError(f"Unsupported resolution: {candle.resolution}")
    return candle.open_time + timedelta(minutes=minutes)


def closed_candles(
    candles: Iterable[Candle], *, through: datetime, require_contiguous: bool = True
) -> list[Candle]:
    """Return a unique closed series and reject gaps instead of filling them."""
    _aware(through, "through")
    closed = [candle for candle in candles if candle_close(candle) <= through]
    if any(candle.available_at_utc is None for candle in closed):
        raise FeatureIntegrityError("Closed candles require factual available_at_utc")
    ordered = sorted(
        (
            candle
            for candle in closed
            if candle.available_at_utc is not None and candle.available_at_utc <= through
        ),
        key=lambda candle: candle.open_time,
    )
    if not ordered:
        return []
    symbols = {candle.symbol for candle in ordered}
    resolutions = {candle.resolution for candle in ordered}
    if len(symbols) != 1 or len(resolutions) != 1:
        raise FeatureIntegrityError("Candle series must have one symbol and resolution")
    minutes = RESOLUTION_MINUTES.get(ordered[0].resolution)
    if minutes is None:
        raise FeatureIntegrityError("Unsupported candle resolution")
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current.open_time == previous.open_time:
            raise FeatureIntegrityError("Duplicate candle open time")
        if require_contiguous and current.open_time - previous.open_time != timedelta(
            minutes=minutes
        ):
            raise FeatureIntegrityError("Missing or irregular candle interval")
    return ordered


def resample_closed_candles(
    candles: Sequence[Candle], *, target_resolution: str, through: datetime
) -> list[Candle]:
    """Aggregate only complete UTC-aligned buckets; never forward-fill a gap."""
    source = closed_candles(candles, through=through, require_contiguous=False)
    if not source:
        return []
    source_minutes = RESOLUTION_MINUTES[source[0].resolution]
    target_minutes = RESOLUTION_MINUTES.get(target_resolution)
    if target_minutes is None or target_minutes <= source_minutes:
        raise FeatureIntegrityError("Target resolution must be a supported larger interval")
    if target_minutes % source_minutes:
        raise FeatureIntegrityError("Target resolution must divide evenly by source resolution")
    expected = target_minutes // source_minutes
    buckets: dict[datetime, list[Candle]] = {}
    for candle in source:
        epoch_minutes = int(candle.open_time.astimezone(UTC).timestamp() // 60)
        bucket_epoch = epoch_minutes - (epoch_minutes % target_minutes)
        bucket = datetime.fromtimestamp(bucket_epoch * 60, tz=UTC)
        buckets.setdefault(bucket, []).append(candle)

    result: list[Candle] = []
    for bucket, rows in sorted(buckets.items()):
        if bucket + timedelta(minutes=target_minutes) > through.astimezone(UTC):
            continue
        rows.sort(key=lambda candle: candle.open_time)
        expected_times = [
            bucket + timedelta(minutes=source_minutes * index) for index in range(expected)
        ]
        if (
            len(rows) != expected
            or [row.open_time.astimezone(UTC) for row in rows] != expected_times
        ):
            continue
        result.append(
            Candle(
                symbol=rows[0].symbol,
                resolution=target_resolution,
                open_time=bucket,
                open=rows[0].open,
                high=max(row.high for row in rows),
                low=min(row.low for row in rows),
                close=rows[-1].close,
                volume_contracts=sum(row.volume_contracts for row in rows),
                source=f"{rows[0].source}_resampled",
                available_at_utc=max(
                    row.available_at_utc for row in rows if row.available_at_utc is not None
                ),
            )
        )
    return result


def session_vwap(candles: Sequence[Candle], *, through: datetime) -> Decimal | None:
    """UTC-day VWAP using closed candles and typical price as the price proxy."""
    rows = closed_candles(candles, through=through, require_contiguous=False)
    if not rows:
        return None
    session_day = rows[-1].open_time.astimezone(UTC).date()
    session = [row for row in rows if row.open_time.astimezone(UTC).date() == session_day]
    total_volume = sum((Decimal(str(row.volume_contracts)) for row in session), Decimal("0"))
    if total_volume <= 0:
        return None
    weighted = sum(
        (
            (Decimal(str(row.high)) + Decimal(str(row.low)) + Decimal(str(row.close)))
            / Decimal("3")
            * Decimal(str(row.volume_contracts))
            for row in session
        ),
        Decimal("0"),
    )
    return weighted / total_volume


def relative_volume(candles: Sequence[Candle], periods: int = 20) -> Decimal | None:
    if periods < 1 or len(candles) < periods + 1:
        return None
    baseline = [Decimal(str(row.volume_contracts)) for row in candles[-periods - 1 : -1]]
    mean = sum(baseline, Decimal("0")) / Decimal(periods)
    if mean <= 0:
        return None
    return Decimal(str(candles[-1].volume_contracts)) / mean


def range_expansion(candles: Sequence[Candle], periods: int = 20) -> Decimal | None:
    if periods < 1 or len(candles) < periods + 1:
        return None
    prior_ranges = [Decimal(str(row.high - row.low)) for row in candles[-periods - 1 : -1]]
    baseline = Decimal(str(median(prior_ranges)))
    if baseline <= 0:
        return None
    return Decimal(str(candles[-1].high - candles[-1].low)) / baseline


def market_regime(candles: Sequence[Candle], *, atr: Decimal) -> MarketRegime:
    if len(candles) < 10 or atr <= 0:
        return MarketRegime.UNKNOWN
    closes = [Decimal(str(row.close)) for row in candles[-20:]]
    path = sum(
        (abs(current - previous) for previous, current in zip(closes, closes[1:], strict=False)),
        Decimal("0"),
    )
    if path <= 0:
        return MarketRegime.RANGING
    efficiency = abs(closes[-1] - closes[0]) / path
    expansion = range_expansion(candles, min(10, len(candles) - 1))
    atr_fraction = atr / closes[-1]
    if (expansion is not None and expansion >= Decimal("1.8")) or atr_fraction >= Decimal("0.02"):
        return MarketRegime.VOLATILE
    if efficiency >= Decimal("0.55"):
        return MarketRegime.TRENDING
    if efficiency <= Decimal("0.30"):
        return MarketRegime.RANGING
    return MarketRegime.UNKNOWN


def structure_events(
    candles: Sequence[Candle], *, left: int = 2, right: int = 2
) -> tuple[StructureEvent, ...]:
    """Confirmed pivots plus latest BOS/CHOCH; right-side bars prevent repainting."""
    if left < 1 or right < 1:
        raise ValueError("Pivot confirmation windows must be positive")
    rows = list(candles)
    highs: list[tuple[int, Decimal, datetime]] = []
    lows: list[tuple[int, Decimal, datetime]] = []
    events: list[StructureEvent] = []
    for index in range(left, len(rows) - right):
        current = rows[index]
        high = Decimal(str(current.high))
        low = Decimal(str(current.low))
        left_rows = rows[index - left : index]
        right_rows = rows[index + 1 : index + right + 1]
        confirmed_at = candle_close(rows[index + right])
        if all(current.high > row.high for row in left_rows + right_rows):
            kind = StructureKind.HH if highs and high > highs[-1][1] else StructureKind.LH
            if not highs:
                kind = StructureKind.HH
            highs.append((index, high, confirmed_at))
            events.append(
                StructureEvent(
                    kind=kind,
                    direction=Direction.BULLISH if kind is StructureKind.HH else Direction.BEARISH,
                    resolution=current.resolution,
                    level=high,
                    pivot_time_utc=current.open_time,
                    confirmed_at_utc=confirmed_at,
                    explanation="Non-repainting swing high confirmed by right-side closed bars",
                )
            )
        if all(current.low < row.low for row in left_rows + right_rows):
            kind = StructureKind.HL if lows and low > lows[-1][1] else StructureKind.LL
            if not lows:
                kind = StructureKind.LL
            lows.append((index, low, confirmed_at))
            events.append(
                StructureEvent(
                    kind=kind,
                    direction=Direction.BULLISH if kind is StructureKind.HL else Direction.BEARISH,
                    resolution=current.resolution,
                    level=low,
                    pivot_time_utc=current.open_time,
                    confirmed_at_utc=confirmed_at,
                    explanation="Non-repainting swing low confirmed by right-side closed bars",
                )
            )
    pivot_events = tuple(events)

    def bias_before(when: datetime) -> Direction:
        kinds = {event.kind for event in pivot_events if event.confirmed_at_utc <= when}
        if {StructureKind.HH, StructureKind.HL} <= kinds:
            return Direction.BULLISH
        if {StructureKind.LH, StructureKind.LL} <= kinds:
            return Direction.BEARISH
        return Direction.NEUTRAL

    # Each confirmed pivot owns one immutable first-break identity. Re-evaluating an
    # expanding series therefore retains the original break time instead of stamping
    # every continuation bar as a new BOS/CHOCH.
    for pivot_index, level, confirmed_at in highs:
        broken = next(
            (
                row
                for row in rows[pivot_index + 1 :]
                if candle_close(row) > confirmed_at and Decimal(str(row.close)) > level
            ),
            None,
        )
        if broken is not None:
            prior_bias = bias_before(candle_close(broken))
            events.append(
                StructureEvent(
                    kind=(
                        StructureKind.CHOCH
                        if prior_bias is Direction.BEARISH
                        else StructureKind.BOS
                    ),
                    direction=Direction.BULLISH,
                    resolution=broken.resolution,
                    level=level,
                    pivot_time_utc=rows[pivot_index].open_time,
                    confirmed_at_utc=candle_close(broken),
                    explanation="First closed-candle break of confirmed swing high",
                )
            )
    for pivot_index, level, confirmed_at in lows:
        broken = next(
            (
                row
                for row in rows[pivot_index + 1 :]
                if candle_close(row) > confirmed_at and Decimal(str(row.close)) < level
            ),
            None,
        )
        if broken is not None:
            prior_bias = bias_before(candle_close(broken))
            events.append(
                StructureEvent(
                    kind=(
                        StructureKind.CHOCH
                        if prior_bias is Direction.BULLISH
                        else StructureKind.BOS
                    ),
                    direction=Direction.BEARISH,
                    resolution=broken.resolution,
                    level=level,
                    pivot_time_utc=rows[pivot_index].open_time,
                    confirmed_at_utc=candle_close(broken),
                    explanation="First closed-candle break of confirmed swing low",
                )
            )
    return tuple(
        sorted(
            events,
            key=lambda event: (
                event.confirmed_at_utc,
                event.pivot_time_utc,
                event.kind.value,
                str(event.level),
            ),
        )
    )


def liquidity_levels(candles: Sequence[Candle]) -> tuple[LiquidityLevel, ...]:
    if not candles:
        return ()
    rows = list(candles)
    levels: list[LiquidityLevel] = []
    for event in structure_events(rows):
        if event.kind in {StructureKind.HH, StructureKind.LH}:
            kind = "SWING_HIGH"
        elif event.kind in {StructureKind.HL, StructureKind.LL}:
            kind = "SWING_LOW"
        else:
            continue
        levels.append(
            LiquidityLevel(
                kind=kind,
                price=event.level,
                observed_at_utc=event.confirmed_at_utc,
                source=f"confirmed_structure:{event.resolution}",
            )
        )
    latest_day = rows[-1].open_time.astimezone(UTC).date()
    today = [row for row in rows if row.open_time.astimezone(UTC).date() == latest_day]
    prior_days = [row for row in rows if row.open_time.astimezone(UTC).date() < latest_day]
    # The current trigger bar is not an established opposing level yet.
    established_today = today[:-1]
    if established_today:
        levels.extend(
            [
                LiquidityLevel(
                    kind="SESSION_HIGH",
                    price=Decimal(str(max(row.high for row in established_today))),
                    observed_at_utc=candle_close(established_today[-1]),
                    source="utc_session",
                ),
                LiquidityLevel(
                    kind="SESSION_LOW",
                    price=Decimal(str(min(row.low for row in established_today))),
                    observed_at_utc=candle_close(established_today[-1]),
                    source="utc_session",
                ),
            ]
        )
    if prior_days:
        prior_day = max(row.open_time.astimezone(UTC).date() for row in prior_days)
        prior = [row for row in prior_days if row.open_time.astimezone(UTC).date() == prior_day]
        levels.extend(
            [
                LiquidityLevel(
                    kind="PREVIOUS_DAY_HIGH",
                    price=Decimal(str(max(row.high for row in prior))),
                    observed_at_utc=candle_close(prior[-1]),
                    source="utc_previous_day",
                ),
                LiquidityLevel(
                    kind="PREVIOUS_DAY_LOW",
                    price=Decimal(str(min(row.low for row in prior))),
                    observed_at_utc=candle_close(prior[-1]),
                    source="utc_previous_day",
                ),
            ]
        )
    return tuple(levels)


def sweep_reclaim(candles: Sequence[Candle], *, lookback: int = 20) -> Direction | None:
    if len(candles) < lookback + 1:
        return None
    prior = candles[-lookback - 1 : -1]
    latest = candles[-1]
    prior_low = min(row.low for row in prior)
    prior_high = max(row.high for row in prior)
    bullish = latest.low < prior_low and latest.close > prior_low
    bearish = latest.high > prior_high and latest.close < prior_high
    if bullish == bearish:
        return None
    return Direction.BULLISH if bullish else Direction.BEARISH


def breakout_retest(candles: Sequence[Candle], *, lookback: int = 20) -> Direction | None:
    if len(candles) < lookback + 2:
        return None
    context = candles[-lookback - 2 : -2]
    breakout, retest = candles[-2:]
    resistance = max(row.high for row in context)
    support = min(row.low for row in context)
    tolerance = max((resistance - support) * 0.02, resistance * 0.0001)
    bullish = (
        breakout.close > resistance
        and retest.low <= resistance + tolerance
        and retest.close > resistance
    )
    bearish = (
        breakout.close < support and retest.high >= support - tolerance and retest.close < support
    )
    if bullish == bearish:
        return None
    return Direction.BULLISH if bullish else Direction.BEARISH


def false_breakout(candles: Sequence[Candle], *, lookback: int = 20) -> Direction | None:
    """Return the attempted breakout direction that failed back inside the range."""
    if len(candles) < lookback + 1:
        return None
    prior = candles[-lookback - 1 : -1]
    latest = candles[-1]
    resistance = max(row.high for row in prior)
    support = min(row.low for row in prior)
    if latest.high > resistance and latest.close <= resistance:
        return Direction.BULLISH
    if latest.low < support and latest.close >= support:
        return Direction.BEARISH
    return None


def _flow_window(
    label: str,
    trades: Sequence[TradeRecord],
    instrument: Instrument,
    *,
    requested_trade_count: int | None = None,
    window_seconds: int | None = None,
) -> FlowWindow:
    buy = sum((trade.contracts for trade in trades if trade.aggressor == "BUY"), Decimal("0"))
    sell = sum((trade.contracts for trade in trades if trade.aggressor == "SELL"), Decimal("0"))
    unclassified = sum(
        (trade.contracts for trade in trades if trade.aggressor is None), Decimal("0")
    )
    quote_buy = sum(
        (
            instrument.quote_notional(trade.contracts, trade.price)
            for trade in trades
            if trade.aggressor == "BUY"
        ),
        Decimal("0"),
    )
    quote_sell = sum(
        (
            instrument.quote_notional(trade.contracts, trade.price)
            for trade in trades
            if trade.aggressor == "SELL"
        ),
        Decimal("0"),
    )
    elapsed = (
        Decimal(str((trades[-1].event_time_utc - trades[0].event_time_utc).total_seconds()))
        if len(trades) > 1
        else Decimal("0")
    )
    rate = Decimal(len(trades)) / elapsed if elapsed > 0 else Decimal("0")
    return FlowWindow(
        label=label,
        requested_trade_count=requested_trade_count,
        window_seconds=window_seconds,
        trade_count=len(trades),
        classified_trade_count=sum(trade.aggressor is not None for trade in trades),
        unclassified_trade_count=sum(trade.aggressor is None for trade in trades),
        elapsed_seconds=elapsed,
        trades_per_second=rate,
        latest_event_time_utc=trades[-1].event_time_utc if trades else None,
        latest_received_at_utc=max((trade.received_at_utc for trade in trades), default=None),
        buy_contracts=buy,
        sell_contracts=sell,
        unclassified_contracts=unclassified,
        cvd_contracts=buy - sell,
        cvd_base_units=(buy - sell) * instrument.contract_value,
        cvd_quote_notional=quote_buy - quote_sell,
    )


def order_flow_features(
    trades: Iterable[TradeRecord], *, instrument: Instrument, through: datetime
) -> OrderFlowFeatures:
    _aware(through, "through")
    unique = {
        trade.event_id: trade
        for trade in trades
        if trade.symbol == instrument.symbol
        and trade.event_time_utc <= through
        and trade.received_at_utc <= through
    }
    ordered = sorted(unique.values(), key=lambda trade: (trade.event_time_utc, trade.event_id))
    last_500 = ordered[-500:]
    last_5000 = ordered[-5000:]
    last_5m = [trade for trade in ordered if trade.event_time_utc > through - timedelta(minutes=5)]
    last_15m = [
        trade for trade in ordered if trade.event_time_utc > through - timedelta(minutes=15)
    ]
    return OrderFlowFeatures(
        last_500=_flow_window("last_500", last_500, instrument, requested_trade_count=500),
        last_5000=_flow_window("last_5000", last_5000, instrument, requested_trade_count=5000),
        last_5m=_flow_window("last_5m", last_5m, instrument, window_seconds=300),
        last_15m=_flow_window("last_15m", last_15m, instrument, window_seconds=900),
    )


def book_features(
    book: BookView | None,
    *,
    instrument: Instrument,
    through: datetime,
    depth: int = 10,
    flow: OrderFlowFeatures | None = None,
    latest_candle: Candle | None = None,
) -> BookFeatures:
    if book is None:
        return BookFeatures(available=False, reason="book_unavailable")
    valid, reason = book.quality(now=through)
    if not valid or not book.bids or not book.asks:
        return BookFeatures(
            available=False, observed_at_utc=book.last_event_time_utc, reason=reason
        )
    bids = sorted(book.bids.items(), reverse=True)[:depth]
    asks = sorted(book.asks.items())[:depth]
    best_bid = bids[0][0]
    best_ask = asks[0][0]
    bid_depth = sum(
        (instrument.quote_notional(Decimal(size), price) for price, (_raw, size) in bids),
        Decimal("0"),
    )
    ask_depth = sum(
        (instrument.quote_notional(Decimal(size), price) for price, (_raw, size) in asks),
        Decimal("0"),
    )
    total = bid_depth + ask_depth
    imbalance = (bid_depth - ask_depth) / total if total > 0 else None
    absorption = "NONE"
    if flow is not None and latest_candle is not None:
        classified = flow.last_500.buy_contracts + flow.last_500.sell_contracts
        if classified > 0:
            signed_ratio = flow.last_500.cvd_contracts / classified
            close_location = Decimal(str(latest_candle.close - latest_candle.low)) / max(
                Decimal(str(latest_candle.high - latest_candle.low)), Decimal("0.00000001")
            )
            if signed_ratio >= Decimal("0.35") and close_location <= Decimal("0.35"):
                absorption = "SELL"
            elif signed_ratio <= Decimal("-0.35") and close_location >= Decimal("0.65"):
                absorption = "BUY"
    return BookFeatures(
        available=True,
        observed_at_utc=book.last_event_time_utc,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=best_ask - best_bid,
        bid_depth_quote=bid_depth,
        ask_depth_quote=ask_depth,
        imbalance=imbalance,
        absorption=absorption,
        reason="validated_sequence_checksum_book",
    )


def build_feature_snapshot(
    *,
    asset: str,
    engine: str,
    horizon_minutes: int,
    candles: Sequence[Candle],
    trigger_candles: Sequence[Candle] | None = None,
    trades: Iterable[TradeRecord],
    instrument: Instrument,
    through: datetime,
    book: BookView | None = None,
    book_override: BookFeatures | None = None,
    external_metrics: Sequence[ExternalMetric] = (),
    context_candles: Mapping[str, Sequence[Candle]] | None = None,
    warnings: Sequence[str] = (),
    coverage: Sequence[CoverageWindow] = (),
    volatility_budget_multiplier: Decimal = Decimal("1.5"),
    trade_max_age_seconds: int = 180,
) -> FeatureSnapshot:
    rows = closed_candles(candles, through=through)
    trigger_rows = closed_candles(trigger_candles or candles, through=through)
    if len(trigger_rows) < 22:
        raise FeatureIntegrityError("At least 22 contiguous closed candles are required")
    atr_value = average_true_range(trigger_rows, 14)
    if atr_value is None or atr_value <= 0:
        raise FeatureIntegrityError("ATR is unavailable")
    atr = Decimal(str(atr_value))
    rel_volume = relative_volume(trigger_rows)
    expansion = range_expansion(trigger_rows)
    base_minutes = RESOLUTION_MINUTES[trigger_rows[-1].resolution]
    projected = (
        atr * Decimal(str(math.sqrt(horizon_minutes / base_minutes))) * volatility_budget_multiplier
    )
    flow = order_flow_features(trades, instrument=instrument, through=through)
    book_value = book_override or book_features(
        book,
        instrument=instrument,
        through=through,
        flow=flow,
        latest_candle=trigger_rows[-1],
    )
    context_candles = context_candles or {}
    structures = list(structure_events(rows))
    levels = list(liquidity_levels(rows))
    for resolution in sorted(context_candles):
        context_rows = closed_candles(
            context_candles[resolution], through=through, require_contiguous=False
        )
        structures.extend(structure_events(context_rows))
        levels.extend(liquidity_levels(context_rows))
    coverage_by_name = {item.name: item for item in coverage}
    if not coverage_by_name.get(
        "UTC_SESSION",
        CoverageWindow(
            name="UTC_SESSION",
            required=True,
            complete=False,
            expected_start_utc=through,
            expected_end_utc=through,
            reason="coverage not supplied",
        ),
    ).complete:
        levels = [level for level in levels if not level.kind.startswith("SESSION_")]
    if not coverage_by_name.get(
        "PREVIOUS_UTC_DAY",
        CoverageWindow(
            name="PREVIOUS_UTC_DAY",
            required=False,
            complete=False,
            expected_start_utc=through,
            expected_end_utc=through,
            reason="coverage not supplied",
        ),
    ).complete:
        levels = [level for level in levels if not level.kind.startswith("PREVIOUS_DAY_")]
    regime = market_regime(trigger_rows, atr=atr)
    session_coverage = coverage_by_name.get("UTC_SESSION")
    vwap = (
        session_vwap(rows, through=through)
        if session_coverage is None or session_coverage.complete
        else None
    )
    all_warnings = list(warnings)
    quality = "FRESH"
    if flow.last_500.trade_count < 500 or flow.last_5000.trade_count < 5_000:
        quality = "INCOMPLETE"
        all_warnings.append("Complete rolling 500/5,000 trade windows are unavailable")
    elif (
        flow.last_500.latest_event_time_utc is None
        or flow.last_500.latest_received_at_utc is None
        or (through - flow.last_500.latest_event_time_utc).total_seconds() > trade_max_age_seconds
        or (through - flow.last_500.latest_received_at_utc).total_seconds() > trade_max_age_seconds
    ):
        quality = "STALE"
        all_warnings.append("Latest executed trade event/receive time is stale")
    all_warnings = list(dict.fromkeys(all_warnings))
    payload = {
        "asset": asset,
        "symbol": instrument.symbol,
        "engine": engine,
        "horizon_minutes": horizon_minutes,
        "candle_close_utc": candle_close(rows[-1]).astimezone(UTC).isoformat(),
        "observed_at_utc": through.astimezone(UTC).isoformat(),
        "last_close": rows[-1].close,
        "atr": str(atr),
        "projected_move": str(projected),
        "volatility_method": "ATR horizon scaling; provisional, not a probability",
        "relative_volume": str(rel_volume),
        "range_expansion": str(expansion),
        "flow": flow.model_dump(mode="json"),
        "book": book_value.model_dump(mode="json"),
        "regime": regime.value,
        "structures": [event.model_dump(mode="json") for event in structures],
        "liquidity_levels": [level.model_dump(mode="json") for level in levels],
        "vwap": str(vwap) if vwap is not None else None,
        "coverage": [item.model_dump(mode="json") for item in coverage],
        "source_quality": quality,
        "warnings": all_warnings,
        "external_metrics": [metric.model_dump(mode="json") for metric in external_metrics],
    }
    snapshot_id = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    return FeatureSnapshot(
        snapshot_id=snapshot_id,
        asset=asset,
        symbol=instrument.symbol,
        engine=engine,
        horizon_minutes=horizon_minutes,
        candle_close_utc=candle_close(rows[-1]),
        observed_at_utc=through,
        regime=regime,
        structures=tuple(structures),
        liquidity_levels=tuple(levels),
        order_flow=flow,
        book=book_value,
        volatility=VolatilityBudget(
            atr=atr,
            projected_move=projected,
            relative_volume=rel_volume,
            range_expansion=expansion,
        ),
        vwap=vwap,
        coverage=tuple(coverage),
        source_quality=quality,
        warnings=tuple(all_warnings),
        external_metrics=tuple(external_metrics),
    )
