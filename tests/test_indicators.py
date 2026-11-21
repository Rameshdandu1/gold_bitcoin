from marketintel.indicators import average_true_range, prior_range


def test_atr_and_prior_levels(make_bars):
    candles = make_bars(n=35, last_close=105)
    assert average_true_range(candles) is not None
    assert average_true_range(candles) > 0
    assert prior_range(candles, 20) == (101.0, 99.0)


def test_insufficient_atr_history(make_bars):
    assert average_true_range(make_bars(n=5), 14) is None
