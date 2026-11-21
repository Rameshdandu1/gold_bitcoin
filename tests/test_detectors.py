from datetime import timedelta

from marketintel.detectors import EngineConfig, create_candidate


def test_bullish_candidate_fresh_closed_candle(make_bars):
    candles = make_bars(n=35, last_close=125.0)
    # Last bar highs 125; prior bars have 101, ATR is volatile enough for $10.
    when = candles[-1].open_time + timedelta(minutes=1, seconds=20)
    candidate = create_candidate(EngineConfig("GOLD", "1m", 30), candles, now=when)
    assert candidate is not None
    assert candidate.direction == "BULLISH"
    assert all(t > candidate.entry for t in candidate.targets)
    assert candidate.invalidation < candidate.entry
    assert candidate.snapshot_id


def test_current_candle_never_used(make_bars):
    candles = make_bars(n=35, last_close=125)
    assert (
        create_candidate(EngineConfig("GOLD", "1m", 30), candles, now=candles[-1].open_time) is None
    )


def test_stale_candle_not_used(make_bars):
    candles = make_bars(n=35, last_close=125)
    now = candles[-1].open_time + timedelta(minutes=5)
    assert create_candidate(EngineConfig("GOLD", "1m", 30), candles, now=now) is None


def test_gapped_candles_fail_closed(make_bars):
    candles = make_bars(n=35, last_close=125)
    candles.pop(10)
    now = candles[-1].open_time + timedelta(minutes=1)
    assert create_candidate(EngineConfig("GOLD", "1m", 30), candles, now=now) is None


def test_no_breakout_is_no_signal(make_bars):
    candles = make_bars(n=35, last_close=100)
    now = candles[-1].open_time + timedelta(minutes=1)
    assert create_candidate(EngineConfig("GOLD", "1m", 30), candles, now=now) is None


def test_duplicate_candidate_deterministic(make_bars):
    candles = make_bars(n=35, last_close=125)
    when = candles[-1].open_time + timedelta(minutes=1, seconds=20)
    engine = EngineConfig("GOLD", "1m", 30)
    c1 = create_candidate(engine, candles, now=when)
    c2 = create_candidate(engine, candles, now=when + timedelta(seconds=5))
    assert c1 and c2
    assert c1.candidate_id == c2.candidate_id
    assert c1.snapshot_id == c2.snapshot_id
