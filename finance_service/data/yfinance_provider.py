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
                
                # Fetch batch
                data = yf.download(
                    " ".join(symbols),
                    start=start_date,
                    end=end_date,
                    interval=interval,
                    progress=False,
                    timeout=self.config.timeout_sec
                )
                
                # Parse results
                return self._parse_yfinance_data(data, symbols)
            
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
        """Parse yfinance response into individual symbol DataFrames"""
        results: Dict[str, pd.DataFrame] = {}
        
        if data.empty:
            return results
        
        # Handle single symbol response
        if len(symbols) == 1:
            symbol = symbols[0]
            if self._validate_ohlcv(data):
                results[symbol] = data
                logger.debug(f"✓ {symbol}: {len(data)} candles")
            else:
                logger.warning(f"✗ {symbol}: invalid data")
            return results
        
        # Handle multiple symbols response
        for symbol in symbols:
            try:
                if symbol in data.columns.get_level_values(0):
                    symbol_data = data[symbol].copy()
                    if self._validate_ohlcv(symbol_data):
                        results[symbol] = symbol_data
                        logger.debug(f"✓ {symbol}: {len(symbol_data)} candles")
                    else:
                        logger.warning(f"✗ {symbol}: invalid data")
            except Exception as e:
                logger.warning(f"Error parsing {symbol}: {e}")
        
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
