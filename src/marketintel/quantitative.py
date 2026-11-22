"""Six independent deterministic M2 signal policies and lifecycle rules."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from marketintel.application_policy import executed_stop_breached
from marketintel.features import (
    RESOLUTION_MINUTES,
    BookView,
    FeatureIntegrityError,
    breakout_retest,
    build_feature_snapshot,
    candle_close,
    closed_candles,
    false_breakout,
    resample_closed_candles,
    sweep_reclaim,
)
from marketintel.models import (
    BookFeatures,
    CandidateLifecycleEvent,
    CandidateSignal,
    Candle,
    CoverageWindow,
    DetectionResult,
    Direction,
    ExternalMetric,
    FeatureSnapshot,
    Instrument,
    SignalState,
    StructureKind,
    TradeRecord,
)

Asset = Literal["GOLD", "BTC"]
TriggerFamily = Literal["FAST", "HOURLY", "SESSION"]


@dataclass(frozen=True)
class QuantEngineConfig:
    engine: str
    asset: Asset
    primary_resolution: str
    context_resolutions: tuple[str, ...]
    horizon_minutes: Literal[30, 60, 240]
    trigger_family: TriggerFamily
    min_candles: int
    stale_after_seconds: int
    min_relative_volume: Decimal
    min_range_expansion: Decimal
    min_classified_trades: int
    min_flow_ratio: Decimal
    min_book_imbalance: Decimal
    requires_book: bool
    stop_atr_multiplier: Decimal
    volatility_budget_multiplier: Decimal
    min_reward_risk: Decimal
    book_max_age_seconds: int = 10
    gold_target_distances: tuple[Decimal, ...] = ()
    btc_target_percentages: tuple[Decimal, ...] = ()
    btc_target_atr_multipliers: tuple[Decimal, ...] = ()
    rule_version: str = "m3a-v2"
    allow_token_market_only: bool = True


QUANT_ENGINE_CONFIGS: tuple[QuantEngineConfig, ...] = (
    QuantEngineConfig(
        "GOLD_FAST",
        "GOLD",
        "1m",
        ("3m", "5m"),
        30,
        "FAST",
        40,
        120,
        Decimal("1.10"),
        Decimal("1.05"),
        20,
        Decimal("0.08"),
        Decimal("0.05"),
        True,
        Decimal("1.10"),
        Decimal("1.50"),
        Decimal("1.20"),
        gold_target_distances=(Decimal("10"), Decimal("20"), Decimal("30")),
    ),
    QuantEngineConfig(
        "GOLD_HOURLY",
        "GOLD",
        "5m",
        ("15m", "1h"),
        60,
        "HOURLY",
        60,
        420,
        Decimal("1.00"),
        Decimal("0.90"),
        30,
        Decimal("0.06"),
        Decimal("0.04"),
        True,
        Decimal("1.25"),
        Decimal("1.65"),
        Decimal("1.30"),
        gold_target_distances=(Decimal("10"), Decimal("20"), Decimal("30")),
    ),
    QuantEngineConfig(
        "GOLD_SESSION",
        "GOLD",
        "15m",
        ("1h", "4h"),
        240,
        "SESSION",
        100,
        1_200,
        Decimal("0.80"),
        Decimal("0.75"),
        40,
        Decimal("0.04"),
        Decimal("0.03"),
        False,
        Decimal("1.50"),
        Decimal("1.80"),
        Decimal("1.35"),
        gold_target_distances=(Decimal("10"), Decimal("20"), Decimal("30")),
    ),
    QuantEngineConfig(
        "BTC_FAST",
        "BTC",
        "1m",
        ("3m", "5m"),
        30,
        "FAST",
        40,
        120,
        Decimal("1.10"),
        Decimal("1.05"),
        20,
        Decimal("0.08"),
        Decimal("0.05"),
        True,
        Decimal("1.10"),
        Decimal("1.50"),
        Decimal("1.20"),
        btc_target_percentages=(Decimal("0.0025"), Decimal("0.005"), Decimal("0.0075")),
        btc_target_atr_multipliers=(Decimal("1.0"), Decimal("1.8"), Decimal("2.6")),
    ),
    QuantEngineConfig(
        "BTC_HOURLY",
        "BTC",
        "5m",
        ("15m", "1h"),
        60,
        "HOURLY",
        60,
        420,
        Decimal("1.00"),
        Decimal("0.90"),
        30,
        Decimal("0.06"),
        Decimal("0.04"),
        True,
        Decimal("1.25"),
        Decimal("1.65"),
        Decimal("1.30"),
        btc_target_percentages=(Decimal("0.003"), Decimal("0.006"), Decimal("0.010")),
        btc_target_atr_multipliers=(Decimal("1.1"), Decimal("2.0"), Decimal("3.0")),
    ),
    QuantEngineConfig(
        "BTC_SESSION",
        "BTC",
        "15m",
        ("1h", "4h"),
        240,
        "SESSION",
        100,
        1_200,
        Decimal("0.80"),
        Decimal("0.75"),
        40,
        Decimal("0.04"),
        Decimal("0.03"),
        False,
        Decimal("1.50"),
        Decimal("1.80"),
        Decimal("1.35"),
        btc_target_percentages=(Decimal("0.005"), Decimal("0.010"), Decimal("0.015")),
        btc_target_atr_multipliers=(Decimal("1.2"), Decimal("2.2"), Decimal("3.2")),
    ),
)

QUANT_ENGINE_BY_ID = {config.engine: config for config in QUANT_ENGINE_CONFIGS}


def _result(
    config: QuantEngineConfig,
    state: SignalState,
    now: datetime,
    reason: str,
    *,
    snapshot: FeatureSnapshot | None = None,
    candidate: CandidateSignal | None = None,
) -> DetectionResult:
    return DetectionResult(
        engine=config.engine,
        state=state,
        observed_at_utc=now,
        reason=reason,
        snapshot=snapshot,
        candidate=candidate,
    )


def _asset_matches(config: QuantEngineConfig, instrument: Instrument) -> bool:
    underlying = instrument.underlying_asset.upper()
    return underlying == "BTC" if config.asset == "BTC" else underlying in {"XAUT", "PAXG"}


def _flow_ratio(
    snapshot: FeatureSnapshot, direction: Direction, *, long_window: bool = False
) -> Decimal:
    window = snapshot.order_flow.last_5000 if long_window else snapshot.order_flow.last_500
    classified = window.buy_contracts + window.sell_contracts
    if classified <= 0:
        return Decimal("0")
    ratio = window.cvd_contracts / classified
    return ratio if direction is Direction.BULLISH else -ratio


def _trigger(
    config: QuantEngineConfig,
    candles: Sequence[Candle],
    snapshot: FeatureSnapshot,
    contexts: Mapping[str, Sequence[Candle]],
) -> tuple[Direction | None, str, SignalState | None]:
    def sweep(rows: Sequence[Candle]) -> Direction | None:
        lookback = min(20, len(rows) - 1)
        return sweep_reclaim(rows, lookback=lookback) if lookback >= 5 else None

    def retest(rows: Sequence[Candle]) -> Direction | None:
        lookback = min(20, len(rows) - 2)
        return breakout_retest(rows, lookback=lookback) if lookback >= 5 else None

    def failed_breakout(rows: Sequence[Candle]) -> Direction | None:
        lookback = min(20, len(rows) - 1)
        return false_breakout(rows, lookback=lookback) if lookback >= 5 else None

    aligned_contexts = {
        resolution: rows
        for resolution, rows in contexts.items()
        if rows and candle_close(rows[-1]) == snapshot.candle_close_utc
    }
    if config.trigger_family == "FAST":
        trigger_sets = [(config.primary_resolution, candles)] + [
            (resolution, aligned_contexts[resolution])
            for resolution in config.context_resolutions
            if resolution in aligned_contexts
        ]
        for resolution, trigger_rows in trigger_sets:
            sweep_direction = sweep(trigger_rows)
            if sweep_direction is not None:
                return (
                    sweep_direction,
                    f"{resolution} liquidity sweep and closed-candle reclaim",
                    None,
                )
            retest_direction = retest(trigger_rows)
            if retest_direction is not None:
                return (
                    retest_direction,
                    f"{resolution} breakout with closed-candle follow-through/retest",
                    None,
                )
        for resolution, trigger_rows in trigger_sets:
            failed = failed_breakout(trigger_rows)
            if failed is not None:
                return (
                    None,
                    f"false {resolution} {failed.value.lower()} breakout returned inside range",
                    SignalState.REJECTED,
                )
        return None, "No confirmed sweep/reclaim or breakout follow-through", SignalState.WATCH

    if config.trigger_family == "HOURLY":
        trigger_sets = [(config.primary_resolution, candles)] + [
            (resolution, aligned_contexts[resolution])
            for resolution in config.context_resolutions[:1]
            if resolution in aligned_contexts
        ]
        for resolution, trigger_rows in trigger_sets:
            retest_direction = retest(trigger_rows)
            if retest_direction is not None:
                return (
                    retest_direction,
                    f"{resolution} closed breakout and retest with persistence gates",
                    None,
                )
        for resolution, trigger_rows in trigger_sets:
            failed = failed_breakout(trigger_rows)
            if failed is not None:
                reversal = Direction.BEARISH if failed is Direction.BULLISH else Direction.BULLISH
                return (
                    reversal,
                    f"{resolution} failed breakout rejection back through the range boundary",
                    None,
                )
        return None, "No closed breakout/retest or rejection trigger", SignalState.WATCH

    context_structure = next(
        (
            event
            for event in reversed(snapshot.structures)
            if event.kind in {StructureKind.BOS, StructureKind.CHOCH}
            and event.resolution in config.context_resolutions
            and event.confirmed_at_utc == snapshot.candle_close_utc
        ),
        None,
    )
    latest_structure = context_structure or next(
        (
            event
            for event in reversed(snapshot.structures)
            if event.kind in {StructureKind.BOS, StructureKind.CHOCH}
            and event.resolution == config.primary_resolution
            and event.confirmed_at_utc == snapshot.candle_close_utc
        ),
        None,
    )
    if latest_structure is None:
        return None, "No newly confirmed higher-timeframe BOS/CHOCH", SignalState.WATCH
    return latest_structure.direction, f"higher-timeframe {latest_structure.kind.value}", None


def _opposing_room(snapshot: FeatureSnapshot, entry: Decimal, direction: Direction) -> Decimal:
    established = [
        level
        for level in snapshot.liquidity_levels
        if level.source.startswith("confirmed_structure")
        or level.source in {"utc_session", "utc_previous_day"}
    ]
    if direction is Direction.BULLISH:
        levels = [level.price - entry for level in established if level.price > entry]
    else:
        levels = [entry - level.price for level in established if level.price < entry]
    positive = [distance for distance in levels if distance > 0]
    return min(positive) if positive else snapshot.volatility.projected_move


def _targets(
    config: QuantEngineConfig,
    snapshot: FeatureSnapshot,
    *,
    entry: Decimal,
    risk: Decimal,
    direction: Direction,
) -> tuple[list[Decimal], list[str]]:
    if config.asset == "GOLD":
        raw_distances = list(config.gold_target_distances)
    else:
        raw_distances = [
            max(entry * percent, snapshot.volatility.atr * atr_multiplier)
            for percent, atr_multiplier in zip(
                config.btc_target_percentages,
                config.btc_target_atr_multipliers,
                strict=True,
            )
        ]
    room = _opposing_room(snapshot, entry, direction)
    maximum = min(snapshot.volatility.projected_move, room * Decimal("0.90"))
    feasible: list[Decimal] = []
    rejected: list[str] = []
    for distance in raw_distances:
        if distance > maximum:
            rejected.append(f"distance {distance} exceeds volatility/opposing-level room {maximum}")
            continue
        if distance / risk < config.min_reward_risk:
            rejected.append(f"distance {distance} fails minimum reward/risk")
            continue
        target = entry + distance if direction is Direction.BULLISH else entry - distance
        if target <= 0:
            rejected.append(f"distance {distance} would produce a nonpositive target")
            continue
        feasible.append(target)
    return feasible, rejected


def detect_signal(
    config: QuantEngineConfig,
    *,
    candles: Sequence[Candle],
    trades: Sequence[TradeRecord],
    instrument: Instrument,
    now: datetime,
    book: BookView | None = None,
    book_override: BookFeatures | None = None,
    external_metrics: Sequence[ExternalMetric] = (),
    reference_available: bool = False,
) -> DetectionResult:
    """Evaluate one engine at one event-time clock without reading future observations."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone aware")
    if not _asset_matches(config, instrument):
        return _result(
            config, SignalState.UNAVAILABLE, now, "Instrument does not match engine asset"
        )
    if any(row.symbol != instrument.symbol for row in candles):
        return _result(config, SignalState.UNAVAILABLE, now, "Wrong or mixed instrument symbol")
    if any(row.resolution != config.primary_resolution for row in candles):
        return _result(config, SignalState.UNAVAILABLE, now, "Wrong primary candle resolution")
    try:
        rows = closed_candles(candles, through=now)
    except FeatureIntegrityError as exc:
        return _result(config, SignalState.WAIT, now, str(exc))
    if len(rows) < config.min_candles:
        return _result(config, SignalState.WAIT, now, "Insufficient contiguous closed history")
    trigger_rows = rows[-config.min_candles :]
    latest_close = candle_close(trigger_rows[-1])
    age = (now - latest_close).total_seconds()
    if age < 0 or age > config.stale_after_seconds:
        return _result(
            config, SignalState.WAIT, now, "Latest closed candle is stale or in the future"
        )
    base_minutes = RESOLUTION_MINUTES[config.primary_resolution]
    interval = timedelta(minutes=base_minutes)
    session_start = datetime.combine(
        trigger_rows[-1].open_time.astimezone(UTC).date(), datetime.min.time(), tzinfo=UTC
    )
    session_rows = [row for row in rows if row.open_time >= session_start]
    expected_session_count = int((latest_close - session_start) / interval)
    session_complete = (
        bool(session_rows)
        and session_rows[0].open_time.astimezone(UTC) == session_start
        and candle_close(session_rows[-1]).astimezone(UTC) == latest_close.astimezone(UTC)
        and len(session_rows) == expected_session_count
    )
    prior_start = session_start - timedelta(days=1)
    prior_rows = [row for row in rows if prior_start <= row.open_time < session_start]
    expected_prior_count = int(timedelta(days=1) / interval)
    prior_complete = (
        len(prior_rows) == expected_prior_count
        and bool(prior_rows)
        and prior_rows[0].open_time.astimezone(UTC) == prior_start
        and candle_close(prior_rows[-1]).astimezone(UTC) == session_start
    )
    coverage = (
        CoverageWindow(
            name="TRIGGER",
            required=True,
            complete=len(trigger_rows) == config.min_candles,
            expected_start_utc=latest_close - interval * config.min_candles,
            expected_end_utc=latest_close,
            actual_start_utc=trigger_rows[0].open_time,
            actual_end_utc=candle_close(trigger_rows[-1]),
            candle_count=len(trigger_rows),
            reason="complete"
            if len(trigger_rows) == config.min_candles
            else "missing trigger bars",
        ),
        CoverageWindow(
            name="UTC_SESSION",
            required=True,
            complete=session_complete,
            expected_start_utc=session_start,
            expected_end_utc=latest_close,
            actual_start_utc=session_rows[0].open_time if session_rows else None,
            actual_end_utc=candle_close(session_rows[-1]) if session_rows else None,
            candle_count=len(session_rows),
            reason="complete" if session_complete else "partial UTC session",
        ),
        CoverageWindow(
            name="PREVIOUS_UTC_DAY",
            required=False,
            complete=prior_complete,
            expected_start_utc=prior_start,
            expected_end_utc=session_start,
            actual_start_utc=prior_rows[0].open_time if prior_rows else None,
            actual_end_utc=candle_close(prior_rows[-1]) if prior_rows else None,
            candle_count=len(prior_rows),
            reason="complete" if prior_complete else "previous UTC day unavailable or partial",
        ),
    )
    if not session_complete:
        return _result(
            config,
            SignalState.WAIT,
            now,
            "Incomplete required UTC-session coverage",
        )

    contexts: dict[str, Sequence[Candle]] = {}
    for resolution in config.context_resolutions:
        try:
            context = resample_closed_candles(rows, target_resolution=resolution, through=now)
        except FeatureIntegrityError as exc:
            return _result(config, SignalState.WAIT, now, f"Context {resolution}: {exc}")
        if len(context) < 2:
            return _result(
                config, SignalState.WAIT, now, f"Insufficient closed {resolution} context"
            )
        contexts[resolution] = context

    warnings: list[str] = []
    if config.asset == "GOLD" and not reference_available:
        if not config.allow_token_market_only:
            return _result(
                config, SignalState.UNAVAILABLE, now, "Licensed XAU reference unavailable"
            )
        warnings.append("XAU/USD reference unavailable; token-market-only signal, no basis claim")
    valid_external_metrics = tuple(
        metric
        for metric in external_metrics
        if metric.symbol == "BTC"
        and metric.observed_at_utc <= now
        and metric.received_at_utc is not None
        and metric.received_at_utc <= now
        and (now - metric.received_at_utc).total_seconds() <= config.stale_after_seconds
    )
    if len(valid_external_metrics) != len(external_metrics):
        warnings.append("Future, wrong-symbol, or invalid external metrics were excluded")
    if config.asset == "BTC" and not valid_external_metrics:
        warnings.append("CoinGlass funding/OI unavailable; no derivatives claim used")
    safe_book_override = book_override
    if book_override is not None and book_override.available:
        observed = book_override.observed_at_utc
        age = (now - observed).total_seconds() if observed is not None else -1
        if observed is None or age < 0 or age > config.book_max_age_seconds:
            safe_book_override = BookFeatures(
                available=False,
                observed_at_utc=observed,
                reason="book_override_missing_stale_or_future_timestamp",
            )
    try:
        snapshot = build_feature_snapshot(
            asset=config.asset,
            engine=config.engine,
            horizon_minutes=config.horizon_minutes,
            candles=rows,
            trigger_candles=trigger_rows,
            trades=trades,
            instrument=instrument,
            through=now,
            book=book,
            book_override=safe_book_override,
            external_metrics=valid_external_metrics,
            context_candles=contexts,
            warnings=warnings,
            coverage=coverage,
            volatility_budget_multiplier=config.volatility_budget_multiplier,
            trade_max_age_seconds=config.stale_after_seconds,
        )
    except FeatureIntegrityError as exc:
        return _result(config, SignalState.WAIT, now, str(exc))

    if config.requires_book and not snapshot.book.available:
        return _result(
            config,
            SignalState.WAIT,
            now,
            f"Sequence-validated fresh order book required: {snapshot.book.reason}",
            snapshot=snapshot,
        )
    if snapshot.source_quality != "FRESH":
        return _result(
            config,
            SignalState.WAIT,
            now,
            f"Executed-trade source quality is {snapshot.source_quality}",
            snapshot=snapshot,
        )
    if (
        snapshot.order_flow.last_500.trade_count < 500
        or snapshot.order_flow.last_5000.trade_count < 5_000
    ):
        return _result(
            config,
            SignalState.WAIT,
            now,
            "Complete rolling 500 and 5,000 executed-trade windows are required",
            snapshot=snapshot,
        )
    if snapshot.order_flow.last_500.classified_trade_count < config.min_classified_trades:
        return _result(
            config,
            SignalState.WAIT,
            now,
            "Insufficient classified executed trades",
            snapshot=snapshot,
        )

    direction, trigger, terminal = _trigger(config, trigger_rows, snapshot, contexts)
    if direction is None:
        return _result(config, terminal or SignalState.WATCH, now, trigger, snapshot=snapshot)

    latest_context_break = next(
        (
            event
            for event in reversed(snapshot.structures)
            if event.resolution in config.context_resolutions
            and event.kind in {StructureKind.BOS, StructureKind.CHOCH}
            and event.confirmed_at_utc <= latest_close
        ),
        None,
    )
    if latest_context_break is not None and latest_context_break.direction is not direction:
        return _result(
            config,
            SignalState.WATCH,
            now,
            f"Trigger opposes latest {latest_context_break.resolution} structure break",
            snapshot=snapshot,
        )

    rel_volume = snapshot.volatility.relative_volume
    expansion = snapshot.volatility.range_expansion
    if rel_volume is None or rel_volume < config.min_relative_volume:
        return _result(
            config, SignalState.WATCH, now, "Relative volume gate not met", snapshot=snapshot
        )
    if expansion is None or expansion < config.min_range_expansion:
        return _result(
            config, SignalState.WATCH, now, "Range expansion gate not met", snapshot=snapshot
        )
    short_flow = _flow_ratio(snapshot, direction)
    long_flow = _flow_ratio(snapshot, direction, long_window=True)
    if short_flow < config.min_flow_ratio or long_flow <= 0:
        return _result(
            config,
            SignalState.WATCH,
            now,
            "Aggressive flow is weak or not persistent across 500/5,000 windows",
            snapshot=snapshot,
        )
    if snapshot.book.available and snapshot.book.imbalance is not None:
        directional_book = (
            snapshot.book.imbalance if direction is Direction.BULLISH else -snapshot.book.imbalance
        )
        if directional_book < config.min_book_imbalance:
            return _result(
                config,
                SignalState.WATCH,
                now,
                "Order-book imbalance does not support direction",
                snapshot=snapshot,
            )
        opposing_absorption = (
            snapshot.book.absorption == "SELL"
            if direction is Direction.BULLISH
            else snapshot.book.absorption == "BUY"
        )
        if opposing_absorption:
            return _result(
                config,
                SignalState.REJECTED,
                now,
                "Absorption proxy opposes the trigger",
                snapshot=snapshot,
            )
    if config.trigger_family != "FAST" and snapshot.vwap is not None:
        entry_check = Decimal(str(trigger_rows[-1].close))
        if direction is Direction.BULLISH and entry_check < snapshot.vwap:
            return _result(
                config,
                SignalState.WATCH,
                now,
                "Bullish trigger remains below UTC-session VWAP",
                snapshot=snapshot,
            )
        if direction is Direction.BEARISH and entry_check > snapshot.vwap:
            return _result(
                config,
                SignalState.WATCH,
                now,
                "Bearish trigger remains above UTC-session VWAP",
                snapshot=snapshot,
            )

    entry = Decimal(str(trigger_rows[-1].close))
    recent = trigger_rows[-5:]
    if direction is Direction.BULLISH:
        structural_risk = entry - Decimal(str(min(row.low for row in recent)))
    else:
        structural_risk = Decimal(str(max(row.high for row in recent))) - entry
    execution_buffer = (
        snapshot.book.spread
        if snapshot.book.available and snapshot.book.spread is not None
        else instrument.tick_size * Decimal("2")
    )
    risk = (
        max(
            structural_risk,
            snapshot.volatility.atr * config.stop_atr_multiplier,
            instrument.tick_size * Decimal("2"),
        )
        + execution_buffer
    )
    invalidation = entry - risk if direction is Direction.BULLISH else entry + risk
    if invalidation <= 0:
        return _result(
            config,
            SignalState.WAIT,
            now,
            "Stop geometry would produce a nonpositive invalidation price",
            snapshot=snapshot,
        )
    targets, target_rejections = _targets(
        config,
        snapshot,
        entry=entry,
        risk=risk,
        direction=direction,
    )
    if not targets:
        return _result(
            config,
            SignalState.WAIT,
            now,
            "Insufficient volatility/opposing-level budget for the first target",
            snapshot=snapshot,
        )
    candidate_key = "|".join(
        [
            config.asset,
            instrument.symbol,
            config.engine,
            str(config.horizon_minutes),
            latest_close.astimezone(UTC).isoformat(),
            direction.value,
            config.rule_version,
        ]
    )
    candidate_id = hashlib.sha256(candidate_key.encode()).hexdigest()[:24]
    explanation_payload = {
        "engine": config.engine,
        "trigger": trigger,
        "direction": direction.value,
        "flow_ratio_500": str(short_flow),
        "flow_ratio_5000": str(long_flow),
        "regime": snapshot.regime.value,
        "targets": [str(target) for target in targets],
    }
    candidate = CandidateSignal(
        candidate_id=candidate_id,
        snapshot_id=snapshot.snapshot_id,
        asset=config.asset,
        symbol=instrument.symbol,
        engine=config.engine,
        horizon_minutes=config.horizon_minutes,
        candle_close_utc=latest_close,
        observed_at_utc=now,
        expires_at_utc=latest_close + timedelta(minutes=config.horizon_minutes),
        direction=direction.value,
        state=SignalState.CANDIDATE,
        trigger=trigger,
        entry=float(entry),
        invalidation=float(invalidation),
        targets=[float(target) for target in targets],
        feature_evidence=[
            f"regime={snapshot.regime.value}",
            f"ATR={snapshot.volatility.atr}",
            f"relative_volume={rel_volume}",
            f"range_expansion={expansion}",
            f"CVD ratio last500={short_flow}",
            f"CVD ratio last5000={long_flow}",
            f"book_imbalance={snapshot.book.imbalance}",
            f"execution_buffer={execution_buffer}",
            "Context structure="
            + (
                f"{latest_context_break.resolution}:{latest_context_break.kind.value}"
                if latest_context_break is not None
                else "none"
            ),
            "Targets are provisional geometric feasibility tiers, not probabilities",
        ],
        counter_evidence=list(snapshot.warnings) + target_rejections,
        explanation=json.dumps(explanation_payload, sort_keys=True, separators=(",", ":")),
        source_quality=snapshot.source_quality,
        rule_version=config.rule_version,
    )
    return _result(
        config,
        SignalState.CANDIDATE,
        now,
        "Deterministic M2 candidate; NOT AI CONFIRMED",
        snapshot=snapshot,
        candidate=candidate,
    )


LEGAL_TRANSITIONS: Mapping[SignalState | None, frozenset[SignalState]] = {
    None: frozenset(
        {
            SignalState.UNAVAILABLE,
            SignalState.WAIT,
            SignalState.WATCH,
            SignalState.CANDIDATE,
            SignalState.REJECTED,
        }
    ),
    SignalState.UNAVAILABLE: frozenset({SignalState.WAIT, SignalState.WATCH}),
    SignalState.WAIT: frozenset(
        {SignalState.WATCH, SignalState.CANDIDATE, SignalState.UNAVAILABLE}
    ),
    SignalState.WATCH: frozenset(
        {SignalState.CANDIDATE, SignalState.REJECTED, SignalState.UNAVAILABLE, SignalState.WAIT}
    ),
    SignalState.CANDIDATE: frozenset({SignalState.INVALIDATED, SignalState.EXPIRED}),
    SignalState.REJECTED: frozenset(),
    SignalState.INVALIDATED: frozenset(),
    SignalState.EXPIRED: frozenset(),
}


def lifecycle_event(
    *,
    candidate_id: str,
    snapshot_id: str,
    from_state: SignalState | None,
    to_state: SignalState,
    occurred_at: datetime,
    reason: str,
    price_source: Literal["EXECUTED_TRADE", "BID_ASK", "CLOSED_CANDLE", "NONE"] = "NONE",
    price_policy_version: str = "m3a-price-v1",
    source_event_id: str | None = None,
) -> CandidateLifecycleEvent:
    if to_state not in LEGAL_TRANSITIONS[from_state]:
        raise ValueError(f"Illegal signal transition: {from_state} -> {to_state}")
    canonical = "|".join(
        [
            candidate_id,
            snapshot_id,
            str(from_state),
            to_state.value,
            occurred_at.astimezone(UTC).isoformat(),
            reason,
            price_source,
            price_policy_version,
            source_event_id or "",
        ]
    )
    return CandidateLifecycleEvent(
        event_id=hashlib.sha256(canonical.encode()).hexdigest(),
        candidate_id=candidate_id,
        snapshot_id=snapshot_id,
        from_state=from_state,
        to_state=to_state,
        occurred_at_utc=occurred_at,
        reason=reason,
        price_source=price_source,
        price_policy_version=price_policy_version,
        source_event_id=source_event_id,
    )


def terminal_transition(
    candidate: CandidateSignal,
    *,
    current_state: SignalState,
    now: datetime,
    latest_price: Decimal,
    source_fresh: bool,
    evaluation_snapshot_id: str | None = None,
    price_source: Literal["EXECUTED_TRADE", "BID_ASK", "CLOSED_CANDLE", "NONE"] = "NONE",
    source_event_id: str | None = None,
) -> CandidateLifecycleEvent | None:
    if current_state is not SignalState.CANDIDATE:
        return None
    to_state: SignalState | None = None
    reason = ""
    if now >= candidate.expires_at_utc:
        to_state = SignalState.EXPIRED
        reason = "Candidate expiry reached"
    elif not source_fresh:
        to_state = SignalState.INVALIDATED
        reason = "Required source became stale or invalid"
    elif executed_stop_breached(
        candidate.direction,
        Decimal(str(candidate.invalidation)),
        latest_price,
    ):
        to_state = SignalState.INVALIDATED
        reason = f"{candidate.direction.title()} invalidation price breached"
    if to_state is None:
        return None
    return lifecycle_event(
        candidate_id=candidate.candidate_id,
        snapshot_id=evaluation_snapshot_id or candidate.snapshot_id,
        from_state=current_state,
        to_state=to_state,
        occurred_at=now,
        reason=reason,
        price_source=price_source,
        source_event_id=source_event_id,
    )


def replay_engine(
    config: QuantEngineConfig,
    *,
    candles: Sequence[Candle],
    trades: Sequence[TradeRecord],
    instrument: Instrument,
    book_at: Callable[[datetime], BookFeatures | None] | None = None,
    external_metrics_at: Callable[[datetime], Sequence[ExternalMetric]] | None = None,
    reference_available: bool = False,
) -> list[DetectionResult]:
    """Replay once per primary close using explicit point-in-time candle availability."""
    ordered = sorted(candles, key=lambda row: row.open_time)
    if any(row.available_at_utc is None for row in ordered):
        raise ValueError("Replay candles require available_at_utc")
    results: list[DetectionResult] = []
    seen_candidate_ids: set[str] = set()
    for index, row in enumerate(ordered):
        decision_time = candle_close(row)
        if index + 1 < config.min_candles:
            continue
        available_candles = [
            item
            for item in ordered[: index + 1]
            if candle_close(item) <= decision_time
            and item.available_at_utc is not None
            and item.available_at_utc <= decision_time
        ]
        available_trades = [
            trade
            for trade in trades
            if trade.event_time_utc <= decision_time and trade.received_at_utc <= decision_time
        ]
        result = detect_signal(
            config,
            candles=available_candles,
            trades=available_trades,
            instrument=instrument,
            now=decision_time,
            book_override=book_at(decision_time) if book_at else None,
            external_metrics=external_metrics_at(decision_time) if external_metrics_at else (),
            reference_available=reference_available,
        )
        if result.candidate is not None:
            if result.candidate.candidate_id in seen_candidate_ids:
                continue
            seen_candidate_ids.add(result.candidate.candidate_id)
        results.append(result)
    return results
