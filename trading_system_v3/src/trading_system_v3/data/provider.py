"""OHLCV data provider protocol + yfinance implementation.

Kept behind a Protocol so the DataStage is testable without network
access and the vendor is swappable.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

from trading_system_v3.core.models import Bar, OHLCV


class DataProvider(Protocol):
    def fetch(self, symbol: str, lookback_days: int, interval: str) -> OHLCV: ...


class YFinanceProvider:
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
