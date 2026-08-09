"""DataAgent: fetches OHLCV history for a symbol.

Baseline used yfinance directly on the agent. Here the network/vendor
dependency is behind a `DataProvider` protocol so DataAgent is unit
testable without network access, and swapping data vendors later does
not touch agent logic.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Protocol

from trading_system.agents.base import Agent
from trading_system.core.models import AgentReport, Bar, OHLCV

logger = logging.getLogger(__name__)


class DataProvider(Protocol):
    def fetch(self, symbol: str, lookback_days: int, interval: str) -> OHLCV: ...


class YFinanceProvider:
    """Thin wrapper around yfinance, imported lazily so tests/environments
    without network access don't need the package importable at all."""

    def fetch(self, symbol: str, lookback_days: int, interval: str = "1d") -> OHLCV:
        import yfinance as yf

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=lookback_days)
        df = yf.download(
            symbol, start=start.date(), end=end.date(), interval=interval,
            progress=False, auto_adjust=True,
        )
        if df is None or df.empty:
            raise ValueError(f"No data returned for {symbol}")
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)

        bars = [
            Bar(
                date=idx.to_pydatetime(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
            )
            for idx, row in df.iterrows()
        ]
        return OHLCV(symbol=symbol, interval=interval, bars=bars)


class _CacheEntry:
    __slots__ = ("data", "expires_at")

    def __init__(self, data: OHLCV, expires_at: float) -> None:
        self.data = data
        self.expires_at = expires_at


class DataAgent(Agent):
    def __init__(self, provider: DataProvider, ttl_seconds: int = 900) -> None:
        self._provider = provider
        self._ttl = ttl_seconds
        self._cache: dict[str, _CacheEntry] = {}

    @property
    def agent_id(self) -> str:
        return "data_agent"

    @property
    def goal(self) -> str:
        return "Fetch and cache OHLCV history per symbol"

    def _cache_key(self, symbol: str, lookback_days: int, interval: str) -> str:
        return f"{symbol}:{interval}:{lookback_days}"

    async def run(self, symbol: str, lookback_days: int = 250, interval: str = "1d") -> AgentReport:
        key = self._cache_key(symbol, lookback_days, interval)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and cached.expires_at > now:
            return AgentReport(
                agent_id=self.agent_id, status="success",
                message=f"Cache hit for {symbol}", payload={"ohlcv": cached.data},
            )
        try:
            ohlcv = self._provider.fetch(symbol, lookback_days, interval)
        except Exception as exc:
            logger.warning("DataAgent failed for %s: %s", symbol, exc)
            return AgentReport(
                agent_id=self.agent_id, status="failure",
                message=f"Failed to fetch data for {symbol}: {exc}",
            )
        self._cache[key] = _CacheEntry(ohlcv, now + self._ttl)
        return AgentReport(
            agent_id=self.agent_id, status="success",
            message=f"Fetched {len(ohlcv.bars)} bars for {symbol}",
            payload={"ohlcv": ohlcv},
        )
