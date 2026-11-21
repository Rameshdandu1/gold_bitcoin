"""Six independent configured candle-based candidate detectors (provisional rules)."""

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from marketintel.indicators import average_true_range, prior_range
from marketintel.models import Candidate, Candle, EngineDescriptor

BAR_MINUTES = {"1m": 1, "5m": 5, "15m": 15}


@dataclass(frozen=True)
class EngineConfig:
    asset: str
    resolution: str
    horizon_minutes: int
    breakout_lookback: int = 20
    atr_periods: int = 14
    stop_atr_multiplier: float = 1.25
    # Experimental feasibility budget; do not confuse with probability.
    volatility_budget_multiplier: float = 1.5

    @property
    def engine_id(self) -> str:
        return f"{self.asset}_{self.horizon_minutes}M"


ENGINE_CONFIGS = (
    EngineConfig("GOLD", "1m", 30),
    EngineConfig("GOLD", "5m", 60),
    EngineConfig("GOLD", "15m", 240),
    EngineConfig("BTC", "1m", 30),
    EngineConfig("BTC", "5m", 60),
    EngineConfig("BTC", "15m", 240),
)


def describe_engines(gold_symbol: str, btc_symbol: str) -> list[EngineDescriptor]:
    return [
        EngineDescriptor(
            id=engine.engine_id,
            asset=engine.asset,
            symbol=gold_symbol if engine.asset == "GOLD" else btc_symbol,
            resolution=engine.resolution,
            horizon_minutes=engine.horizon_minutes,
        )
        for engine in ENGINE_CONFIGS
    ]


def create_candidate(
    engine: EngineConfig,
    candles: list[Candle],
    *,
    now: datetime | None = None,
) -> Candidate | None:
    """Only accepts candles that are closed at `now` and contiguous at base resolution."""
    now = now or datetime.now(UTC)
    if not candles or now.tzinfo is None:
        return None
    bar_minutes = BAR_MINUTES[engine.resolution]
    ordered = sorted(candles, key=lambda c: c.open_time)
    if any(c.resolution != engine.resolution for c in ordered):
        return None
    if len({c.symbol for c in ordered}) != 1 or len(ordered) < engine.breakout_lookback + 1:
        return None
    # Must be contiguous; all timestamps must represent candle OPEN time.
    for prev, nxt in zip(ordered, ordered[1:], strict=False):
        if nxt.open_time - prev.open_time != timedelta(minutes=bar_minutes):
            return None
    latest = ordered[-1]
    candle_close = latest.open_time + timedelta(minutes=bar_minutes)
    if candle_close > now or (now - candle_close).total_seconds() > 180:
        return None
    atr = average_true_range(ordered, engine.atr_periods)
    levels = prior_range(ordered, engine.breakout_lookback)
    if atr is None or atr <= 0 or levels is None:
        return None
    resistance, support = levels
    if latest.close > resistance:
        direction = "BULLISH"
    elif latest.close < support:
        direction = "BEARISH"
    else:
        return None
    entry = latest.close
    risk = max(atr * engine.stop_atr_multiplier, entry * 0.00001)
    max_move = atr * math.sqrt(engine.horizon_minutes / bar_minutes)
    max_move *= engine.volatility_budget_multiplier
    distances = (
        [10.0, 20.0, 30.0]
        if engine.asset == "GOLD"
        else [entry * fraction for fraction in [0.0025, 0.005, 0.0075]]
    )
    feasible = [d for d in distances if d <= max_move and d / risk >= 1.5]
    if not feasible:
        return None
    invalidation = entry - risk if direction == "BULLISH" else entry + risk
    targets = [entry + d if direction == "BULLISH" else entry - d for d in feasible]
    candidate_key = "|".join(
        [
            ordered[-1].symbol,
            engine.engine_id,
            candle_close.isoformat(),
            direction,
            "breakout-v0.1",
        ]
    )
    candidate_id = hashlib.sha256(candidate_key.encode()).hexdigest()[:24]
    # Hash ONLY facts and rule constants, never an LLM-generated field.
    features = {
        "candidate_id": candidate_id,
        "entry": round(entry, 8),
        "atr": round(atr, 8),
        "prior_high": resistance,
        "prior_low": support,
        "targets": [round(x, 8) for x in targets],
        "stop": round(invalidation, 8),
    }
    snapshot_id = hashlib.sha256(json.dumps(features, sort_keys=True).encode()).hexdigest()
    return Candidate(
        candidate_id=candidate_id,
        snapshot_id=snapshot_id,
        asset=engine.asset,
        symbol=latest.symbol,
        horizon_minutes=engine.horizon_minutes,
        candle_close_utc=candle_close,
        observed_at_utc=now,
        expires_at_utc=candle_close + timedelta(minutes=engine.horizon_minutes),
        direction=direction,
        trigger=f"Closed {engine.resolution} breakout of preceding {engine.breakout_lookback} bars",
        entry=entry,
        invalidation=invalidation,
        targets=targets,
        source_quality="INCOMPLETE",  # Starter lacks verified orderflow/macro; never auto-confirm.
        feature_evidence=[
            f"ATR({engine.atr_periods}) {atr:.4f} quote USD per underlying",
            f"Previous range {support:.4f} to {resistance:.4f}",
            f"Experimental volatility budget {max_move:.4f}; uncalibrated",
            "No true order-flow, macro or CoinGlass confirmation in this starter rule",
        ],
    )
