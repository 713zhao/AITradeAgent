from __future__ import annotations

import random
from datetime import datetime, timedelta

import pytest

from trading_system.core.models import Bar, OHLCV


def make_ohlcv(symbol: str, closes: list[float], interval: str = "1d") -> OHLCV:
    start = datetime(2024, 1, 1)
    bars = []
    for i, c in enumerate(closes):
        bars.append(
            Bar(
                date=start + timedelta(days=i),
                open=c * 0.99, high=c * 1.01, low=c * 0.98, close=c, volume=1_000_000,
            )
        )
    return OHLCV(symbol=symbol, interval=interval, bars=bars)


def _random_walk(seed: int, drift_low: float, drift_high: float, n: int = 80, start_price: float = 100.0) -> list[float]:
    rng = random.Random(seed)
    price = start_price
    closes = []
    for _ in range(n):
        price += rng.uniform(drift_low, drift_high)
        closes.append(price)
    return closes


@pytest.fixture
def uptrend_ohlcv() -> OHLCV:
    # Seeded random walk with upward drift; realistic enough to have a
    # normal (not pegged-at-100) RSI, unlike a perfectly monotonic series.
    closes = _random_walk(seed=42, drift_low=-1.0, drift_high=1.6)
    return make_ohlcv("UP", closes)


@pytest.fixture
def downtrend_ohlcv() -> OHLCV:
    closes = _random_walk(seed=0, drift_low=-1.6, drift_high=1.0)
    return make_ohlcv("DOWN", closes)
