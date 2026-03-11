"""Data Manager - Orchestrates data fetching, caching, and universe management"""
import logging
from typing import Dict, List, Optional, Any
import pandas as pd
from datetime import datetime, timedelta

from .yfinance_provider import YfinanceProvider, RateLimitConfig
from .data_cache import DataCache
from finance_service.agents.market_scanner_agent import MarketScannerAgent
from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.core.event_bus import get_event_bus, Event, Events
from finance_service.agents.agent_interface import Agent, AgentReport

logger = logging.getLogger(__name__)


class DataAgent(Agent):
    """Data Agent - Maintains reliable market data through fetching, caching, and normalization."""

    @property
    def agent_id(self) -> str:
        return "data_agent"

    @property
    def goal(self) -> str:
        return "Maintain reliable and up-to-date market data, including OHLCV and fundamental data."

    
    def __init__(self, config_engine: YAMLConfigEngine):
        self.config = config_engine
        
        # Initialize components
        rate_limit_config = self._get_rate_limit_config()
        self.provider = YfinanceProvider(rate_limit_config)
        self.cache = DataCache(
            db_path="storage/cache.sqlite",
            ttl_minutes=self.config.get("finance", "data/cache_ttl_minutes", default=1440)
        )
        self.scanner = MarketScannerAgent(config_engine)
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
    
    async def run(self, symbol: str, 
                  start_date: Optional[str] = None,
                  end_date: Optional[str] = None,
                  interval: str = "1d",
                  use_cache: bool = True,
                  emit_events: bool = True, # This parameter will control event emission per symbol
                  refresh_all: bool = False) -> AgentReport:
        """
        Executes the data fetching and caching logic for a given symbol or refreshes all symbols.

        If `refresh_all` is True, it will attempt to fetch data for the entire known universe.
        """
        logger.info(f"DataAgent run: Fetching data for symbol {symbol} (interval: {interval}, refresh_all: {refresh_all}).")
        
        if refresh_all:
            # This path is for DATA_REFRESH_TRIGGER, will fetch for all known symbols
            # For now, we will re-scan the universe and fetch for all of them.
            report = await self.scanner.run() # Rescan universe
            symbols_to_refresh = report.payload.get("symbols", [])
            all_fetched_data = {}
            for sym in symbols_to_refresh:
                df = await self._fetch_data_for_symbol(
                    symbol=sym,
                    start_date=start_date,
                    end_date=end_date,
                    interval=interval,
                    use_cache=use_cache
                )
                if df is not None and not df.empty:
                    all_fetched_data[sym] = df
                    if emit_events:
                        await self.event_bus.publish(Event(
                            event_type=Events.DATA_FETCH_COMPLETE,
                            data={
                                "symbol": sym,
                                "interval": interval,
                                "dataframe": df.to_dict() # Serialize DataFrame for event payload
                            }
                        ))
            message = f"Refreshed data for {len(all_fetched_data)} symbols."
            payload = {"symbols": list(all_fetched_data.keys()), "count": len(all_fetched_data)}
            return AgentReport(agent_id=self.agent_id, status="success", message=message, payload=payload)

        # Path for single symbol fetch
        df = await self._fetch_data_for_symbol(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            use_cache=use_cache
        )

        if df is not None and not df.empty:
            message = f"Successfully fetched data for {symbol}."
            payload = {"symbol": symbol, "interval": interval, "dataframe": df.to_dict()}
            if emit_events:
                await self.event_bus.publish(Event(
                    event_type=Events.DATA_FETCH_COMPLETE,
                    data=payload # Send dataframe in event payload
                ))
            return AgentReport(agent_id=self.agent_id, status="success", message=message, payload=payload)
        else:
            message = f"Failed to fetch data for {symbol} or data is empty."
            return AgentReport(agent_id=self.agent_id, status="error", message=message, payload={"symbol": symbol})
    async def _fetch_data_for_symbol(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        interval: str = "1d",
        use_cache: bool = True
    ) -> Optional[pd.DataFrame]:
        """Fetches and caches data for a single symbol."""
        cache_key = f"{symbol}_{interval}_{start_date or ''}_{end_date or ''}"
        cached_df = None

        if use_cache:
            cached_df = self.cache.retrieve(cache_key)
            if cached_df is not None and not cached_df.empty:
                logger.debug(f"[Cache Hit] {symbol} data from cache.")
                return cached_df

        logger.debug(f"[Cache Miss] Fetching {symbol} data from provider.")
        df = await self.provider.fetch_ohlcv(
            symbol, start_date=start_date, end_date=end_date, interval=interval
        )

        if df is not None and not df.empty:
            if use_cache:
                self.cache.store(cache_key, df)
                logger.debug(f"[Cache Store] {symbol} data cached.")
            return df
        else:
            logger.warning(f"No data fetched for {symbol} or DataFrame is empty.")
            return None

    async def fetch_universe(
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
        report = await self.scanner.run(include_themes=include_themes)
        symbols = report.payload["symbols"] if report and report.payload else []
        
        end_date = datetime.now().date()
        start_date = (
            end_date - timedelta(days=lookback_days)
            if lookback_days
            else end_date - timedelta(days=252)  # Default 1 year
        )
        
        logger.info(f"Fetching universe: {len(symbols)} symbols, "
                   f"{start_date} to {end_date}, interval={interval}")
        
        all_fetched_data = {}
        for sym in symbols:
            df = await self._fetch_data_for_symbol(
                symbol=sym,
                start_date=str(start_date),
                end_date=str(end_date),
                interval=interval,
                use_cache=True
            )
            if df is not None and not df.empty:
                all_fetched_data[sym] = df
                if emit_events:
                    await self.event_bus.publish(Event(
                        event_type=Events.DATA_FETCH_COMPLETE,
                        data={
                            "symbol": sym,
                            "interval": interval,
                            "dataframe": df.to_dict() # Serialize DataFrame for event payload
                        }
                    ))
        return all_fetched_data

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
    
    async def get_universe(self, theme: Optional[str] = None) -> List[str]:
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
            report = await self.scanner.run()
            return report.payload["symbols"] if report and report.payload else []
    
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
        return (f"DataAgent(symbols={stats['universe']['total_symbols']}, "
                f"themes={stats['universe']['total_themes']}, "
                f"cached_symbols={stats['cache'].get('symbols_cached', 0)})")
