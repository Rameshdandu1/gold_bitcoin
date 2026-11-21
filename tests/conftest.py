from datetime import UTC, datetime, timedelta

import pytest

from marketintel.models import Candle


@pytest.fixture
def make_bars():
    def _bars(symbol="XAUTUSD", resolution="1m", n=40, last_close=100.0):
        minutes = {"1m": 1, "5m": 5, "15m": 15}[resolution]
        # Fixed reference time: deterministic no live clock leakage into tests.
        start = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
        values = []
        for i in range(n):
            price = last_close if i == n - 1 else 100.0
            values.append(
                Candle(
                    symbol=symbol,
                    resolution=resolution,
                    open_time=start + timedelta(minutes=minutes * i),
                    open=100.0,
                    high=max(101.0, price),
                    low=99.0,
                    close=price,
                    volume_contracts=100,
                )
            )
        return values

    return _bars
