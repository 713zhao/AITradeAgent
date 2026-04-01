"""Historical data loading with caching for backtesting.

Provides `load_data()` function that fetches OHLCV data from yfinance,
caches results in storage/backtest_cache/ as parquet for faster reloads.
"""
import os
import pandas as pd
import yfinance as yf
from typing import List, Optional, Dict, Any
from pathlib import Path
import hashlib
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


def _cache_key(symbols: List[str], start: str, end: str, interval: str = "1d") -> str:
    """Generate unique cache key for data request"""
    symbols_str = "_".join(sorted(symbols))
    content = f"{symbols_str}_{start}_{end}_{interval}"
    return hashlib.md5(content.encode()).hexdigest()


def load_data(
    symbols: List[str],
    start: str,
    end: str,
    interval: str = "1d",
    use_cache: bool = True,
    cache_dir: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load historical OHLCV data for multiple symbols.

    Args:
        symbols: List of ticker symbols
        start: Start date (YYYY-MM-DD)
        end: End date (YYYY-MM-DD)
        interval: Data interval (1d, 1h, etc.)
        use_cache: Whether to use cached data if available
        cache_dir: Custom cache directory (default: storage/backtest_cache)

    Returns:
        DataFrame with MultiIndex (date, symbol) and columns: open, high, low, close, volume
    """
    if cache_dir is None:
        cache_dir = os.path.join(os.getenv("STORAGE_DIR", "storage"), "backtest_cache")
    os.makedirs(cache_dir, exist_ok=True)

    cache_key = _cache_key(symbols, start, end, interval)
    cache_file = Path(cache_dir) / f"{cache_key}.parquet"

    # Try cache
    if use_cache and cache_file.exists():
        try:
            df = pd.read_parquet(cache_file)
            logger.info(f"Loaded cached data: {len(df)} bars for {len(symbols)} symbols")
            return df
        except Exception as e:
            logger.warning(f"Cache load failed: {e}, fetching fresh data")

    # Fetch from yfinance
    logger.info(f"Fetching data for {len(symbols)} symbols from {start} to {end}")
    all_data = []
    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start, end=end, interval=interval, auto_adjust=True)
            if hist.empty:
                logger.warning(f"No data for {symbol}")
                continue
            hist = hist.reset_index()
            hist['symbol'] = symbol
            # Standardize column names
            hist = hist.rename(columns={
                'Date': 'date',
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume',
            })
            # Ensure date column is datetime
            hist['date'] = pd.to_datetime(hist['date'])
            all_data.append(hist[['date', 'symbol', 'open', 'high', 'low', 'close', 'volume']])
        except Exception as e:
            logger.error(f"Failed to fetch {symbol}: {e}")

    if not all_data:
        raise ValueError("No data fetched for any symbols")

    combined = pd.concat(all_data, ignore_index=True)
    combined = combined.set_index(['date', 'symbol']).sort_index()

    # Save to cache
    try:
        combined.to_parquet(cache_file)
        logger.info(f"Cached data to {cache_file}")
    except Exception as e:
        logger.warning(f"Failed to write cache: {e}")

    return combined
