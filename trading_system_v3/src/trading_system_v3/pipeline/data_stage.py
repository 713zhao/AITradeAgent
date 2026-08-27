"""DataStage: fetch + TTL-cache OHLCV history. Stateless from the pipeline's
perspective (its cache is a performance optimization, not decision state),
so it is not one of the isolated actors."""
from __future__ import annotations

import logging
import time

from trading_system_v3.core.models import OHLCV
from trading_system_v3.data.provider import DataProvider

logger = logging.getLogger(__name__)


class _CacheEntry:
    __slots__ = ("data", "expires_at")

    def __init__(self, data: OHLCV, expires_at: float) -> None:
        self.data = data
        self.expires_at = expires_at


class DataStage:
    def __init__(self, provider: DataProvider, ttl_seconds: int = 900) -> None:
        self._provider = provider
        self._ttl = ttl_seconds
        self._cache: dict[str, _CacheEntry] = {}

    async def fetch(self, symbol: str, lookback_days: int = 250, interval: str = "1d") -> OHLCV:
        key = f"{symbol}:{interval}:{lookback_days}"
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and cached.expires_at > now:
            return cached.data
        ohlcv = self._provider.fetch(symbol, lookback_days, interval)
        self._cache[key] = _CacheEntry(ohlcv, now + self._ttl)
        return ohlcv
