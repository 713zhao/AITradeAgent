"""Data Manager - Orchestrates data fetching, caching, and universe management"""
import logging
from typing import Dict, List, Optional, Any
import pandas as pd
from datetime import datetime, timedelta

from .yfinance_provider import YfinanceProvider, RateLimitConfig
from .data_cache import DataCache
from .universe_scanner import UniverseScanner
from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.core.event_bus import get_event_bus, Event, Events

logger = logging.getLogger(__name__)


class DataManager:
    """Central data manager for fetching, caching, and universe management"""
    
    def __init__(self, config_engine: YAMLConfigEngine):
        self.config = config_engine
        
        # Initialize components
        rate_limit_config = self._get_rate_limit_config()
        self.provider = YfinanceProvider(rate_limit_config)
        self.cache = DataCache(
            db_path="storage/cache.sqlite",
            ttl_minutes=self.config.get("finance", "data/cache_ttl_minutes", default=1440)
        )
        self.scanner = UniverseScanner(config_engine)
        self.event_bus = get_event_bus()
        
        logger.info("DataManager initialized")
    
    def _get_rate_limit_config(self) -> RateLimitConfig:
        """Load rate limit config from YAML"""
        return RateLimitConfig(
            batch_size=self.config.get("finance", "data/batch_size", default=10),
            batch_delay_sec=self.config.get("finance", "data/batch_delay_sec", default=0.5),
            request_jitter_sec=self.config.get("finance", "data/request_jitter_sec", default=0.5),
            backoff_initial_sec=self.config.get("finance", "data/backoff/initial_wait_sec", default=1),
            backoff_max_sec=self.config.get("finance", "data/backoff/max_wait_sec", default=30),
            backoff_multiplier=self.config.get("finance", "data/backoff/multiplier", default=2.0),
            max_retries=self.config.get("finance", "performance/api_retries", default=3),
            timeout_sec=self.config.get("finance", "performance/api_timeout_sec", default=30),
        )
    
    def fetch_symbols(
        self,
        symbols: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        interval: str = "1d",
        use_cache: bool = True,
        emit_events: bool = True
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch OHLCV data for symbols with caching
        
        Args:
            symbols: List of ticker symbols
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            interval: Data interval (1d, 1h, 5m, etc)
            use_cache: Use cache before fetching from provider
            emit_events: Emit DATA_FETCH_COMPLETE event
        
        Returns:
            Dictionary of {symbol: DataFrame}
        """
        logger.info(f"Fetching {len(symbols)} symbols (cache={use_cache})")
        
        # Emit start event
        if emit_events:
            self.event_bus.publish(
                Event(
                    event_type=Events.DATA_FETCH_STARTED,
                    data={"symbols": symbols, "interval": interval}
                )
            )
        
        results: Dict[str, pd.DataFrame] = {}
        symbols_to_fetch: List[str] = []
        
        # Check cache first
        if use_cache:
            for symbol in symbols:
                cached_data = self.cache.get(symbol, interval)
                if cached_data is not None:
                    results[symbol] = cached_data
                else:
                    symbols_to_fetch.append(symbol)
            
            logger.debug(f"Cache hit: {len(results)} symbols, fetching {len(symbols_to_fetch)}")
        else:
            symbols_to_fetch = symbols
        
        # Fetch from provider if needed
        if symbols_to_fetch:
            try:
                provider_data = self.provider.fetch_ohlcv(
                    symbols_to_fetch,
                    start_date=start_date,
                    end_date=end_date,
                    interval=interval
                )
                
                # Cache results
                for symbol, df in provider_data.items():
                    self.cache.set(symbol, df, interval)
                
                results.update(provider_data)
            
            except Exception as e:
                logger.error(f"Error fetching from provider: {e}")
        
        # Emit completion event
        if emit_events:
            self.event_bus.publish(
                Event(
                    event_type=Events.DATA_FETCH_COMPLETE,
                    data={
                        "symbols": symbols,
                        "fetched_count": len(results),
                        "interval": interval,
                        "timestamp": datetime.now().isoformat()
                    }
                )
            )
            
            # Emit DATA_READY for each symbol
            for symbol in results.keys():
                self.event_bus.publish(
                    Event(
                        event_type=Events.DATA_READY,
                        data={"symbol": symbol, "candles": len(results[symbol])}
                    )
                )
        
        return results
    
    def fetch_universe(
        self,
        include_themes: Optional[List[str]] = None,
        lookback_days: Optional[int] = None,
        interval: str = "1d",
        emit_events: bool = True
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch data for entire universe
        
        Args:
            include_themes: Specific themes to fetch (None = all)
            lookback_days: Historical lookback period
            interval: Data interval
            emit_events: Emit events
        
        Returns:
            Dictionary of {symbol: DataFrame}
        """
        # Get universe
        symbols = self.scanner.scan_universe(include_themes)
        
        # Calculate dates
        end_date = datetime.now().date()
        start_date = (
            end_date - timedelta(days=lookback_days)
            if lookback_days
            else end_date - timedelta(days=252)  # Default 1 year
        )
        
        # Fetch
        logger.info(f"Fetching universe: {len(symbols)} symbols, "
                   f"{start_date} to {end_date}, interval={interval}")
        
        return self.fetch_symbols(
            symbols,
            start_date=str(start_date),
            end_date=str(end_date),
            interval=interval,
            use_cache=True,
            emit_events=emit_events
        )
    
    def fetch_latest_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Fetch latest closing prices
        
        Args:
            symbols: List of ticker symbols
        
        Returns:
            Dictionary of {symbol: price}
        """
        logger.debug(f"Fetching latest prices for {len(symbols)} symbols")
        return self.provider.fetch_latest(symbols)
    
    def get_universe(self, theme: Optional[str] = None) -> List[str]:
        """
        Get trading universe
        
        Args:
            theme: Specific theme (None = all themes)
        
        Returns:
            List of symbols
        """
        if theme:
            return self.scanner.get_symbols_by_theme(theme)
        else:
            return self.scanner.scan_universe()
    
    def get_universe_info(self) -> Dict[str, Any]:
        """Get detailed universe information"""
        return {
            "universe": self.get_universe(),
            "stats": self.scanner.get_stats(),
            "all_themes": self.scanner.scan_all_themes()
        }
    
    def clear_cache(self, symbol: Optional[str] = None) -> bool:
        """Clear cache entries"""
        if symbol:
            return self.cache.invalidate(symbol)
        else:
            return self.cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get data manager statistics"""
        return {
            "provider": self.provider.get_stats(),
            "cache": self.cache.get_stats(),
            "universe": self.scanner.get_stats(),
            "timestamp": datetime.now().isoformat()
        }
    
    def __repr__(self) -> str:
        stats = self.get_stats()
        return (f"DataManager(symbols={stats['universe']['total_symbols']}, "
                f"themes={stats['universe']['total_themes']}, "
                f"cached_symbols={stats['cache'].get('symbols_cached', 0)})")
