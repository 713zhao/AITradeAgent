"""Data Cache - SQLite-based OHLCV caching with TTL"""
import logging
import sqlite3
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
import pandas as pd
import threading

logger = logging.getLogger(__name__)


class DataCache:
    """SQLite-based cache for OHLCV data with TTL"""
    
    def __init__(self, db_path: str = "storage/cache.sqlite", ttl_minutes: int = 1440):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl_minutes = ttl_minutes
        self._lock = threading.Lock()
        
        self._init_schema()
        logger.info(f"DataCache initialized (path={db_path}, ttl={ttl_minutes} min)")
    
    def _init_schema(self) -> None:
        """Initialize cache schema"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            
            # Check if table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ohlcv_cache'"
            )
            
            if not cursor.fetchone():
                cursor.execute('''
                    CREATE TABLE ohlcv_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        interval TEXT NOT NULL,
                        timestamp TIMESTAMP NOT NULL,
                        open REAL NOT NULL,
                        high REAL NOT NULL,
                        low REAL NOT NULL,
                        close REAL NOT NULL,
                        volume INTEGER NOT NULL,
                        cached_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(symbol, interval, timestamp)
                    )
                ''')
                
                cursor.execute('''
                    CREATE INDEX idx_ohlcv_symbol_interval 
                    ON ohlcv_cache(symbol, interval)
                ''')
                
                cursor.execute('''
                    CREATE INDEX idx_ohlcv_cached_at 
                    ON ohlcv_cache(cached_at)
                ''')
                
                conn.commit()
                logger.info("Cache schema created")
    
    def get(self, symbol: str, interval: str = "1d") -> Optional[pd.DataFrame]:
        """
        Get cached OHLCV data if available and not expired
        
        Args:
            symbol: Ticker symbol
            interval: Data interval (1d, 1h, 5m, etc)
        
        Returns:
            DataFrame with OHLCV data or None if not cached/expired
        """
        with self._lock:
            try:
                with sqlite3.connect(str(self.db_path)) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    
                    # Check if data is cached and not expired
                    cutoff = datetime.now() - timedelta(minutes=self.ttl_minutes)
                    
                    cursor.execute('''
                        SELECT timestamp, open, high, low, close, volume
                        FROM ohlcv_cache
                        WHERE symbol = ? AND interval = ? AND cached_at > ?
                        ORDER BY timestamp ASC
                    ''', (symbol, interval, cutoff))
                    
                    rows = cursor.fetchall()
                    
                    if not rows:
                        return None
                    
                    # Convert to DataFrame
                    data = pd.DataFrame([dict(row) for row in rows])
                    data['timestamp'] = pd.to_datetime(data['timestamp'])
                    data.set_index('timestamp', inplace=True)
                    
                    logger.debug(f"Cache hit for {symbol}: {len(data)} candles")
                    return data
            
            except Exception as e:
                logger.error(f"Error reading cache: {e}")
                return None
    
    def set(self, symbol: str, df: pd.DataFrame, interval: str = "1d") -> bool:
        """
        Cache OHLCV data
        
        Args:
            symbol: Ticker symbol
            df: DataFrame with OHLCV data (must have Open, High, Low, Close, Volume)
            interval: Data interval
        
        Returns:
            True if successful
        """
        if df.empty:
            return False
        
        required_cols = {'Open', 'High', 'Low', 'Close', 'Volume'}
        if not required_cols.issubset(df.columns):
            logger.error(f"Missing required columns for {symbol}")
            return False
        
        with self._lock:
            try:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    
                    # Clear old data for this symbol/interval
                    cursor.execute(
                        'DELETE FROM ohlcv_cache WHERE symbol = ? AND interval = ?',
                        (symbol, interval)
                    )
                    
                    # Insert new data
                    for timestamp, row in df.iterrows():
                        try:
                            # Convert timestamp to string if needed
                            ts_str = str(timestamp) if not isinstance(timestamp, str) else timestamp
                            
                            cursor.execute('''
                                INSERT INTO ohlcv_cache
                                (symbol, interval, timestamp, open, high, low, close, volume)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                symbol,
                                interval,
                                ts_str,
                                float(row['Open']),
                                float(row['High']),
                                float(row['Low']),
                                float(row['Close']),
                                int(row['Volume'])
                            ))
                        except sqlite3.IntegrityError:
                            # Duplicate, skip
                            pass
                    
                    conn.commit()
                    logger.debug(f"Cached {len(df)} candles for {symbol}/{interval}")
                    return True
            
            except Exception as e:
                logger.error(f"Error writing cache: {e}")
                return False
    
    def invalidate(self, symbol: Optional[str] = None) -> bool:
        """
        Invalidate cache entries
        
        Args:
            symbol: Symbol to invalidate (None = invalidate all expired)
        
        Returns:
            True if successful
        """
        with self._lock:
            try:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    
                    if symbol:
                        cursor.execute('DELETE FROM ohlcv_cache WHERE symbol = ?', (symbol,))
                    else:
                        # Delete expired entries
                        cutoff = datetime.now() - timedelta(minutes=self.ttl_minutes)
                        cursor.execute('DELETE FROM ohlcv_cache WHERE cached_at < ?', (cutoff,))
                    
                    conn.commit()
                    return True
            
            except Exception as e:
                logger.error(f"Error invalidating cache: {e}")
                return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                
                # Total entries
                cursor.execute('SELECT COUNT(*) FROM ohlcv_cache')
                total = cursor.fetchone()[0]
                
                # Symbols cached
                cursor.execute('SELECT DISTINCT symbol FROM ohlcv_cache')
                symbols = [row[0] for row in cursor.fetchall()]
                
                # Expired entries
                cutoff = datetime.now() - timedelta(minutes=self.ttl_minutes)
                cursor.execute(
                    'SELECT COUNT(*) FROM ohlcv_cache WHERE cached_at < ?',
                    (cutoff,)
                )
                expired = cursor.fetchone()[0]
                
                return {
                    "total_candles": total,
                    "symbols_cached": len(symbols),
                    "expired_candles": expired,
                    "ttl_minutes": self.ttl_minutes,
                    "cache_size_symbols": symbols[:10]  # Show first 10
                }
        
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {}
    
    def clear(self) -> bool:
        """Clear entire cache"""
        with self._lock:
            try:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM ohlcv_cache')
                    conn.commit()
                    logger.info("Cache cleared")
                    return True
            except Exception as e:
                logger.error(f"Error clearing cache: {e}")
                return False
    
    def __repr__(self) -> str:
        stats = self.get_stats()
        return f"DataCache(symbols={stats.get('symbols_cached', 0)}, ttl={self.ttl_minutes}min)"
