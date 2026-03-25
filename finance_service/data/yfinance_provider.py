"""yfinance Data Provider with rate-limiting optimization"""
import yfinance as yf
import pandas as pd
import logging
import time
import random
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limiting configuration"""
    batch_size: int = 10                    # Fetch N symbols per request
    batch_delay_sec: float = 1.0            # Delay between batches
    request_jitter_sec: float = 0.5         # Random jitter per request
    backoff_initial_sec: int = 1            # Initial backoff wait
    backoff_max_sec: int = 60               # Max backoff wait
    backoff_multiplier: float = 1.5         # Exponential multiplier
    max_retries: int = 3                    # Max retry attempts
    timeout_sec: int = 30                   # HTTP timeout


class YfinanceProvider:
    """Data provider using yfinance with rate-limit optimization"""
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self._retry_count = 0
        self._last_request_time = 0
        self._request_count = 0
        
        logger.info(f"YfinanceProvider initialized with batch_size={self.config.batch_size}")
    
    def _add_jitter(self) -> None:
        """Add random jitter delay to prevent rate limiting"""
        jitter = random.uniform(0, self.config.request_jitter_sec)
        time.sleep(jitter)
    
    def _apply_backoff(self, attempt: int) -> None:
        """Apply exponential backoff on rate limit"""
        wait_time = min(
            self.config.backoff_initial_sec * (self.config.backoff_multiplier ** attempt),
            self.config.backoff_max_sec
        )
        logger.warning(f"Rate limit hit, waiting {wait_time:.1f}s (attempt {attempt}/{self.config.max_retries})")
        time.sleep(wait_time)
    
    def _enforce_batch_delay(self) -> None:
        """Enforce delay between batch requests"""
        time.sleep(self.config.batch_delay_sec)
    
    def fetch_ohlcv(
        self,
        symbols: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        interval: str = "1d"
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch OHLCV data with batching and rate-limit handling
        
        Args:
            symbols: List of ticker symbols
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            interval: Interval (1m, 5m, 1h, 1d, 1wk, 1mo)
        
        Returns:
            Dictionary of {symbol: DataFrame with OHLCV}
        """
        logger.info(f"[YfinanceProvider.fetch_ohlcv] called with symbols={symbols}, start={start_date}, end={end_date}, interval={interval}")
        if not symbols:
            logger.warning("No symbols provided")
            return {}
        
        results: Dict[str, pd.DataFrame] = {}
        
        # Process symbols in batches
        for i in range(0, len(symbols), self.config.batch_size):
            batch = symbols[i:i + self.config.batch_size]
            
            logger.debug(f"Fetching batch {i//self.config.batch_size + 1}/{(len(symbols)-1)//self.config.batch_size + 1}: {batch}")
            
            batch_data = self._fetch_batch_with_retry(batch, start_date, end_date, interval)
            results.update(batch_data)
            
            # Add delay between batches
            if i + self.config.batch_size < len(symbols):
                self._enforce_batch_delay()
        
        logger.info(f"Successfully fetched {len(results)}/{len(symbols)} symbols")
        return results
    
    def _fetch_batch_with_retry(
        self,
        symbols: List[str],
        start_date: Optional[str],
        end_date: Optional[str],
        interval: str
    ) -> Dict[str, pd.DataFrame]:
        """Fetch a batch with retry logic"""
        for attempt in range(self.config.max_retries):
            try:
                self._add_jitter()
                
                logger.info(f"[YfinanceProvider] Fetching batch {symbols} with start={start_date}, end={end_date}, interval={interval}")
                
                # Fetch batch
                data = yf.download(
                    " ".join(symbols),
                    start=start_date,
                    end=end_date,
                    interval=interval,
                    progress=False,
                    timeout=self.config.timeout_sec
                )
                
                logger.info(f"[YfinanceProvider] download returned {len(data)} rows, columns: {data.columns.tolist() if hasattr(data, 'columns') else 'N/A'}")
                
                # Parse results
                results = self._parse_yfinance_data(data, symbols)
                for sym, df in results.items():
                    logger.info(f"[YfinanceProvider] Parsed {sym}: {len(df)} rows, index range: {df.index.min()} to {df.index.max()}")
                return results
            
            except Exception as e:
                if "Too Many Requests" in str(e) or "429" in str(e):
                    # Rate limited
                    if attempt < self.config.max_retries - 1:
                        self._apply_backoff(attempt + 1)
                    else:
                        logger.error(f"Rate limit exceeded after {self.config.max_retries} attempts")
                        raise
                else:
                    # Other error
                    logger.error(f"Error fetching batch: {e}")
                    if attempt < self.config.max_retries - 1:
                        time.sleep(1 + attempt)
                    else:
                        raise
        
        return {}
    
    def _parse_yfinance_data(self, data: Any, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """Parse yfinance response into individual symbol DataFrames with proper column structure."""
        results: Dict[str, pd.DataFrame] = {}
        
        if data.empty:
            return results
        
        # If columns is MultiIndex, extract each symbol's sub-frame
        if isinstance(data.columns, pd.MultiIndex):
            # Determine which level contains tickers
            # Usually level 0 = fields (Close, High, etc.), level 1 = tickers
            level0_vals = set(data.columns.get_level_values(0))
            level1_vals = set(data.columns.get_level_values(1))
            
            # Identify ticker level: the level that contains our symbols
            if any(sym in level1_vals for sym in symbols):
                ticker_level = 1
                field_level = 0
            elif any(sym in level0_vals for sym in symbols):
                ticker_level = 0
                field_level = 1
            else:
                logger.warning("Could not determine ticker level in MultiIndex")
                return results
            
            for symbol in symbols:
                try:
                    if symbol in data.columns.get_level_values(ticker_level):
                        # Extract cross-section for this symbol
                        symbol_df = data.xs(symbol, axis=1, level=ticker_level)
                        # Ensure standard column names: they should be fields already
                        if self._validate_ohlcv(symbol_df):
                            results[symbol] = symbol_df
                            logger.debug(f"✓ {symbol}: {len(symbol_df)} candles")
                        else:
                            logger.warning(f"✗ {symbol}: invalid data")
                except Exception as e:
                    logger.warning(f"Error parsing {symbol}: {e}")
        else:
            # Single-level columns: whole DataFrame is for one symbol (the first one requested)
            # Usually this happens when only one symbol was requested and yfinance returned a flat DataFrame
            # But if multiple symbols were requested and we got flat columns, that's unexpected.
            if len(symbols) == 1:
                symbol = symbols[0]
                if self._validate_ohlcv(data):
                    results[symbol] = data
                    logger.debug(f"✓ {symbol}: {len(data)} candles")
                else:
                    logger.warning(f"✗ {symbol}: invalid data")
            else:
                logger.warning(f"Multi-symbol request returned single-level columns; cannot parse")
        
        return results
    
    def _validate_ohlcv(self, df: pd.DataFrame) -> bool:
        """Validate OHLCV data quality"""
        if df.empty:
            return False
        
        # Check required columns
        required = {'Open', 'High', 'Low', 'Close', 'Volume'}
        if not required.issubset(df.columns):
            return False
        
        # Check for all-zero prices (invalid candle)
        if (df['Open'] == 0).all() and (df['Close'] == 0).all():
            return False
        
        # Check minimum rows
        if len(df) < 5:
            return False
        
        return True
    
    def fetch_latest(self, symbols: List[str]) -> Dict[str, float]:
        """
        Fetch latest closing prices
        
        Args:
            symbols: List of ticker symbols
        
        Returns:
            Dictionary of {symbol: latest_price}
        """
        data = self.fetch_ohlcv(symbols, interval="1d")
        results = {}
        
        for symbol, df in data.items():
            if not df.empty:
                latest_close = df['Close'].iloc[-1]
                results[symbol] = float(latest_close)
        
        return results

    def fetch_fundamentals(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch fundamental data for symbols using yfinance info.
        
        Args:
            symbols: List of ticker symbols
        
        Returns:
            Dictionary of {symbol: fundamentals_dict} with keys:
                - pe_ratio (trailing PE)
                - forward_pe_ratio
                - revenue_growth_yoy (as decimal, e.g., 0.15 for 15%)
                - profit_margins
                - market_cap
                - sector
                - industry
        """
        if not symbols:
            return {}
        
        results: Dict[str, Dict[str, Any]] = {}
        
        # Process in batches to respect rate limits
        for i in range(0, len(symbols), self.config.batch_size):
            batch = symbols[i:i + self.config.batch_size]
            logger.debug(f"Fetching fundamentals batch {i//self.config.batch_size + 1}: {batch}")
            
            batch_results = self._fetch_fundamentals_batch(batch)
            results.update(batch_results)
            
            if i + self.config.batch_size < len(symbols):
                self._enforce_batch_delay()
        
        logger.info(f"Fetched fundamentals for {len(results)}/{len(symbols)} symbols")
        return results

    def _fetch_fundamentals_batch(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch fundamentals for a batch with retry logic."""
        for attempt in range(self.config.max_retries):
            try:
                self._add_jitter()
                batch_results: Dict[str, Dict[str, Any]] = {}
                
                for symbol in symbols:
                    try:
                        ticker = yf.Ticker(symbol)
                        info = ticker.info or {}
                        
                        # Extract key metrics
                        pe = info.get('trailingPE')
                        if pe is None:
                            # Sometimes trailingPE not available; try regularMarketPrice / earningsShare
                            eps = info.get('trailingEps')
                            price = info.get('regularMarketPrice')
                            if eps and price and eps != 0:
                                pe = price / eps
                        
                        forward_pe = info.get('forwardPE')
                        revenue_growth = info.get('revenueGrowth')  # Already decimal
                        profit_margin = info.get('profitMargins')
                        market_cap = info.get('marketCap')
                        sector = info.get('sector')
                        industry = info.get('industry')
                        
                        # Sanitize: Ensure revenue_growth is decimal; if missing, try to compute from financial statements
                        # but that's heavy. We'll leave as None if not available.
                        
                        batch_results[symbol] = {
                            'pe_ratio': float(pe) if pe is not None and not pd.isna(pe) else None,
                            'forward_pe_ratio': float(forward_pe) if forward_pe is not None and not pd.isna(forward_pe) else None,
                            'revenue_growth_yoy': float(revenue_growth) if revenue_growth is not None and not pd.isna(revenue_growth) else None,
                            'profit_margins': float(profit_margin) if profit_margin is not None and not pd.isna(profit_margin) else None,
                            'market_cap': float(market_cap) if market_cap is not None and not pd.isna(market_cap) else None,
                            'sector': sector,
                            'industry': industry,
                        }
                        logger.debug(f"Fetched fundamentals for {symbol}: PE={pe}, RevGrowth={revenue_growth}")
                    except Exception as e:
                        logger.warning(f"Error fetching fundamentals for {symbol}: {e}")
                        batch_results[symbol] = {}
                
                return batch_results
                
            except Exception as e:
                if "Too Many Requests" in str(e) or "429" in str(e):
                    if attempt < self.config.max_retries - 1:
                        self._apply_backoff(attempt + 1)
                    else:
                        logger.error(f"Rate limit exceeded fetching fundamentals after {self.config.max_retries} attempts")
                        raise
                else:
                    logger.error(f"Error fetching fundamentals batch: {e}")
                    if attempt < self.config.max_retries - 1:
                        time.sleep(1 + attempt)
                    else:
                        raise
        
        return {}
    
    def get_stats(self) -> Dict[str, Any]:
        """Get provider statistics"""
        return {
            "provider": "yfinance",
            "total_requests": self._request_count,
            "configuration": {
                "batch_size": self.config.batch_size,
                "batch_delay_sec": self.config.batch_delay_sec,
                "request_jitter_sec": self.config.request_jitter_sec,
                "max_retries": self.config.max_retries,
            }
        }
    
    def __repr__(self) -> str:
        return f"YfinanceProvider(batch_size={self.config.batch_size}, timeout={self.config.timeout_sec}s)"
