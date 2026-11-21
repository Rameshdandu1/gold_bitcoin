from datetime import timedelta

import pytest

from marketintel.backtesting import Outcome, evaluate_target_before_stop
from marketintel.detectors import EngineConfig, create_candidate
from marketintel.models import Candle


@pytest.fixture
def candidate(make_bars):
    bars = make_bars(n=35, last_close=125)
    return create_candidate(
        EngineConfig("GOLD", "1m", 30), bars,
        now=bars[-1].open_time + timedelta(minutes=1, seconds=10),
    )


def future(candidate, high, low):
    return Candle(
        symbol=candidate.symbol, resolution="1m", open_time=candidate.candle_close_utc,
        open=candidate.entry, high=high, low=low, close=candidate.entry,
    )


def test_target_first(candidate):
    assert evaluate_target_before_stop(candidate, [future(
        candidate, candidate.targets[0] + 1, candidate.entry - 1
    )]) == Outcome.TARGET


def test_stop_first(candidate):
    assert evaluate_target_before_stop(candidate, [future(
        candidate, candidate.entry + 1, candidate.invalidation - 1
    )]) == Outcome.STOP


def test_ambiguous_same_bar_not_counted_win(candidate):
    assert evaluate_target_before_stop(candidate, [future(
        candidate, candidate.targets[0] + 1, candidate.invalidation - 1
    )]) == Outcome.AMBIGUOUS


def test_no_future_data_is_incomplete(candidate):
    assert evaluate_target_before_stop(candidate, []) == Outcome.INCOMPLETE
