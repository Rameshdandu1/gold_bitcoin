"""Conservative target-before-stop event labelling on future closed OHLC bars."""

from collections.abc import Sequence
from enum import StrEnum

from marketintel.models import Candidate, Candle


class Outcome(StrEnum):
    TARGET = "TARGET"
    STOP = "STOP"
    AMBIGUOUS = "AMBIGUOUS"
    EXPIRED = "EXPIRED"
    INCOMPLETE = "INCOMPLETE"


def evaluate_target_before_stop(
    candidate: Candidate,
    future_bars: Sequence[Candle],
    *,
    target_index: int = 1,
) -> Outcome:
    """Only bars starting at/after candidate candle CLOSE are allowed.

    A bar that hits both stop and target has unknown intrabar order and must
    NOT be labelled a win. Same goes for open gaps that cross a stop.
    """
    if not 1 <= target_index <= len(candidate.targets):
        raise ValueError("Invalid target_index")
    target = candidate.targets[target_index - 1]
    examined = 0
    most_recent_end = candidate.candle_close_utc
    for bar in sorted(future_bars, key=lambda b: b.open_time):
        if bar.open_time < candidate.candle_close_utc:
            continue  # future-only / avoid look-ahead
        if bar.open_time >= candidate.expires_at_utc:
            break
        examined += 1
        if candidate.direction == "BULLISH":
            hit_target = bar.high >= target
            hit_stop = bar.low <= candidate.invalidation
        else:
            hit_target = bar.low <= target
            hit_stop = bar.high >= candidate.invalidation
        if hit_target and hit_stop:
            return Outcome.AMBIGUOUS
        if hit_stop:
            return Outcome.STOP
        if hit_target:
            return Outcome.TARGET
        period = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}.get(bar.resolution)
        if period is None:
            raise ValueError("Unknown bar resolution")
        from datetime import timedelta

        most_recent_end = bar.open_time + timedelta(minutes=period)
    if not examined:
        return Outcome.INCOMPLETE
    return Outcome.EXPIRED if most_recent_end >= candidate.expires_at_utc else Outcome.INCOMPLETE
