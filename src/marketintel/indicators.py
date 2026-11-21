"""Pure indicator calculations on closed, chronologically ordered candles."""

from collections.abc import Sequence

from marketintel.models import Candle


def average_true_range(candles: Sequence[Candle], periods: int = 14) -> float | None:
    """Mean of the last N true ranges; no look-ahead and no extrapolation."""
    if periods < 1 or len(candles) < periods + 1:
        return None
    true_ranges: list[float] = []
    for previous, current in zip(candles[-periods - 1 : -1], candles[-periods:], strict=True):
        tr = max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )
        true_ranges.append(tr)
    return sum(true_ranges) / periods


def prior_range(candles: Sequence[Candle], lookback: int = 20) -> tuple[float, float] | None:
    if len(candles) < lookback + 1:
        return None
    prior = candles[-lookback - 1 : -1]  # exclude current breakout candle
    return max(bar.high for bar in prior), min(bar.low for bar in prior)
