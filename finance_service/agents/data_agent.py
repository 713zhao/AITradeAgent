"""Data Manager - Orchestrates data fetching, caching, and universe management"""
import asyncio
import logging
from typing import Dict, List, Optional, Any
import pandas as pd
from datetime import datetime, timedelta
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from finance_service.data.yfinance_provider import YfinanceProvider, RateLimitConfig
from finance_service.data.data_cache import DataCache
from finance_service.data.fundamentals import FundamentalsFetcher
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
        
        # Fundamentals fetcher (optional, with fallback providers)
        fundamentals_enabled = self.config.get("finance", "fundamentals/enabled", default=True)
        if fundamentals_enabled:
            providers = self.config.get("finance", "fundamentals/providers", default=["yfinance"])
            av_key = self.config.get("finance", "fundamentals/alphavantage_api_key", default="")
            try:
                self.fundamentals_fetcher = FundamentalsFetcher(providers, alphavantage_api_key=av_key)
                logger.info(f"Fundamentals fetcher initialized with providers: {providers}")
            except Exception as e:
                logger.warning(f"Failed to initialize fundamentals fetcher: {e}; fundamentals disabled")
                self.fundamentals_fetcher = None
        else:
            self.fundamentals_fetcher = None
        
        # Track last seen prices for volatility-based cache invalidation
        self.last_prices = {}  # {symbol: (price, timestamp)}
        
        logger.info("DataManager initialized with dynamic cache TTL")
    
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
    
    def _get_dynamic_cache_ttl(self) -> int:
        """
        Determine cache TTL based on market hours
        
        Returns:
            TTL in minutes (5 during market hours, 15 after hours, 60 on weekends)
        """
        from datetime import time
        import pytz
        
        now = datetime.now()
        
        # Check if it's weekend (Saturday=5, Sunday=6)
        if now.weekday() >= 5:
            ttl = self.config.get("finance", "data/cache_ttl_weekend", default=60)
            logger.debug(f"Weekend: using cache TTL {ttl} min")
            return ttl
        
        # Check US market hours (9:30 AM - 4:00 PM ET, Mon-Fri)
        try:
            ny_tz = pytz.timezone('America/New_York')
            ny_time = now.astimezone(ny_tz)
            us_market_open = time(9, 30)
            us_market_close = time(16, 0)
            is_us_market_open = us_market_open <= ny_time.time() < us_market_close
        except Exception as e:
            logger.warning(f"Could not check US market hours: {e}")
            is_us_market_open = False
        
        # Check HK market hours (9:30 AM - 4:00 PM HKT, Mon-Fri)
        try:
            hk_tz = pytz.timezone('Asia/Hong_Kong')
            hk_time = now.astimezone(hk_tz)
            hk_market_open = time(9, 30)
            hk_market_close = time(16, 0)
            is_hk_market_open = hk_market_open <= hk_time.time() < hk_market_close
        except Exception as e:
            logger.warning(f"Could not check HK market hours: {e}")
            is_hk_market_open = False
        
        if is_us_market_open or is_hk_market_open:
            ttl = self.config.get("finance", "data/cache_ttl_market_hours", default=5)
            logger.debug(f"Market hours (US: {is_us_market_open}, HK: {is_hk_market_open}): cache TTL {ttl} min")
            return ttl
        else:
            ttl = self.config.get("finance", "data/cache_ttl_after_hours", default=15)
            logger.debug(f"After hours: cache TTL {ttl} min")
            return ttl
    
    def _update_dynamic_cache_ttl(self) -> None:
        """Update cache TTL based on current market hours"""
        appropriate_ttl = self._get_dynamic_cache_ttl()
        if self.cache.ttl_minutes != appropriate_ttl:
            logger.info(f"Updating cache TTL: {self.cache.ttl_minutes} min → {appropriate_ttl} min")
            self.cache.ttl_minutes = appropriate_ttl
    
    def _get_dynamic_cache_ttl(self) -> int:
        """
        Determine cache TTL based on market hours
        
        Returns:
            TTL in minutes (5 during market hours, 15 after hours, 60 on weekends)
        """
        from datetime import time
        import pytz
        
        now = datetime.now()
        
        # Check if it's weekend (Saturday=5, Sunday=6)
        if now.weekday() >= 5:
            ttl = self.config.get("finance", "data/cache_ttl_weekend", default=60)
            logger.debug(f"Weekend: using cache TTL {ttl} min")
            return ttl
        
        # Check US market hours (9:30 AM - 4:00 PM ET, Mon-Fri)
        try:
            ny_tz = pytz.timezone('America/New_York')
            ny_time = now.astimezone(ny_tz)
            us_market_open = time(9, 30)
            us_market_close = time(16, 0)
            is_us_market_open = us_market_open <= ny_time.time() < us_market_close
        except Exception as e:
            logger.warning(f"Could not check US market hours: {e}")
            is_us_market_open = False
        
        # Check HK market hours (9:30 AM - 4:00 PM HKT, Mon-Fri)
        try:
            hk_tz = pytz.timezone('Asia/Hong_Kong')
            hk_time = now.astimezone(hk_tz)
            hk_market_open = time(9, 30)
            hk_market_close = time(16, 0)
            is_hk_market_open = hk_market_open <= hk_time.time() < hk_market_close
        except Exception as e:
            logger.warning(f"Could not check HK market hours: {e}")
            is_hk_market_open = False
        
        if is_us_market_open or is_hk_market_open:
            ttl = self.config.get("finance", "data/cache_ttl_market_hours", default=5)
            logger.debug(f"Market hours (US: {is_us_market_open}, HK: {is_hk_market_open}): cache TTL {ttl} min")
            return ttl
        else:
            ttl = self.config.get("finance", "data/cache_ttl_after_hours", default=15)
            logger.debug(f"After hours: cache TTL {ttl} min")
            return ttl
    
    def check_volatility_and_invalidate_cache(self, symbol: str, current_price: float) -> bool:
        """
        Check if price has moved >2% since last seen; invalidate cache if so
        
        Args:
            symbol: Ticker symbol
            current_price: Current price
        
        Returns:
            True if cache was invalidated due to high volatility
        """
        vol_threshold = self.config.get("finance", "data/cache_volatility_invalidation/price_change_threshold_pct", default=2.0)
        
        if symbol not in self.last_prices:
            self.last_prices[symbol] = (current_price, datetime.now())
            return False
        
        last_price, last_time = self.last_prices[symbol]
        if last_price <= 0:
            self.last_prices[symbol] = (current_price, datetime.now())
            return False
        
        price_change_pct = abs((current_price - last_price) / last_price) * 100
        
        if price_change_pct > vol_threshold:
            logger.warning(f"HIGH VOLATILITY DETECTED: {symbol} price moved {price_change_pct:.2f}% "
                          f"({last_price:.2f} → {current_price:.2f}). Invalidating cache.")
            # Invalidate cache for this symbol
            self.cache.invalidate(symbol)
            self.last_prices[symbol] = (current_price, datetime.now())
            return True
        
        self.last_prices[symbol] = (current_price, datetime.now())
        return False
    
    def _update_dynamic_cache_ttl(self) -> None:
        """Update cache TTL based on current market hours"""
        appropriate_ttl = self._get_dynamic_cache_ttl()
        if self.cache.ttl_minutes != appropriate_ttl:
            logger.info(f"Updating cache TTL: {self.cache.ttl_minutes} min → {appropriate_ttl} min")
            self.cache.ttl_minutes = appropriate_ttl
    
    async def run(self, symbol: str = "", 
                  start_date: Optional[str] = None,
                  end_date: Optional[str] = None,
                  interval: str = "1d",
                  use_cache: bool = True,
                  emit_events: bool = True, # This parameter will control event emission per symbol
                  refresh_all: bool = False,
                  fetch_fundamentals: Optional[bool] = None) -> AgentReport:
        """
        Executes the data fetching and caching logic for a given symbol or refreshes all symbols.

        If `refresh_all` is True, it will attempt to fetch data for the entire known universe.
        """
        logger.info(f"DataAgent run: Fetching data for symbol {symbol} (interval: {interval}, refresh_all: {refresh_all}).")
        
        # Update cache TTL based on current market hours
        self._update_dynamic_cache_ttl()
        
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

        # Validate symbol for single fetch
        if not symbol:
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message="Symbol is required for single-symbol fetch",
                payload={}
            )

        # Path for single symbol fetch
        df = await self._fetch_data_for_symbol(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            use_cache=use_cache
        )

        if df is not None and not df.empty:
            # Normalize column names to lowercase for consistency with AnalysisAgent
            df.columns = [col.lower() for col in df.columns]
            # Determine whether to fetch fundamentals
            if fetch_fundamentals is None:
                fetch_fundamentals = self.fundamentals_fetcher is not None
            should_fetch = fetch_fundamentals
            fundamentals = {}
            if should_fetch and self.fundamentals_fetcher:
                fundamentals = await asyncio.to_thread(self.fundamentals_fetcher.fetch, symbol)
            message = f"Fetched data{' and fundamentals' if should_fetch else ''} for {symbol}."
            # Convert to dict with index as a column to preserve all rows
            # Convert to dict with proper orient to preserve datetime index
            payload = {"symbol": symbol, "interval": interval, "dataframe": df.to_dict(), "fundamentals": fundamentals}
            if emit_events:
                await self.event_bus.publish(Event(
                    event_type=Events.DATA_FETCH_COMPLETE,
                    data=payload # Send dataframe and fundamentals in event payload
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
        logger.info(f"[_fetch_data_for_symbol] symbol={symbol}, start_date={start_date}, end_date={end_date}, interval={interval}")
        
        # Set default date range: ~400 calendar days to ensure 200+ trading days
        if start_date is None or end_date is None:
            end_dt = datetime.now().date() if end_date is None else datetime.strptime(end_date, "%Y-%m-%d").date()
            start_dt = end_dt - timedelta(days=400) if start_date is None else datetime.strptime(start_date, "%Y-%m-%d").date()
            start_date = start_dt.strftime("%Y-%m-%d")
            end_date = end_dt.strftime("%Y-%m-%d")
            logger.info(f"[_fetch_data_for_symbol] Using default date range: {start_date} to {end_date}")
        cache_key = f"{symbol}_{interval}_{start_date or ''}_{end_date or ''}"
        cached_df = None

        if use_cache:
            cached_df = self.cache.retrieve(cache_key)
            if cached_df is not None and not cached_df.empty:
                logger.debug(f"[Cache Hit] {symbol} data from cache.")
                return cached_df

        logger.debug(f"[Cache Miss] Fetching {symbol} data from provider.")
        # fetch_ohlcv is synchronous; run in thread to avoid blocking
        # It expects a list of symbols and returns dict {symbol: DataFrame}
        logger.info(f"[_fetch_data_for_symbol] about to fetch from provider: start={start_date}, end={end_date}, interval={interval}")
        
        df = None
        try:
            result_dict = await asyncio.to_thread(
                self.provider.fetch_ohlcv,
                [symbol],
                start_date=start_date,
                end_date=end_date,
                interval=interval
            )
            df = result_dict.get(symbol)
            if df is not None:
                logger.info(f"[_fetch_data_for_symbol] provider returned DataFrame with {len(df)} rows, date range: {df.index.min()} to {df.index.max()}")
            else:
                logger.warning(f"[_fetch_data_for_symbol] provider returned None for {symbol}")
        except Exception as e:
            logger.error(f"[_fetch_data_for_symbol] Provider error for {symbol}: {e}", exc_info=True)
            logger.info(f"[_fetch_data_for_symbol] Attempting to use cached data (even if expired) as fallback...")
            # Try to get any cached data, even if expired (graceful degradation)
            with self.cache._lock:
                try:
                    import sqlite3
                    with sqlite3.connect(str(self.cache.db_path)) as conn:
                        conn.row_factory = sqlite3.Row
                        cursor = conn.cursor()
                        cursor.execute('''
                            SELECT timestamp, open, high, low, close, volume
                            FROM ohlcv_cache
                            WHERE symbol = ? AND interval = ?
                            ORDER BY timestamp DESC
                            LIMIT 1
                        ''', (symbol, interval))
                        last_row = cursor.fetchone()
                        
                        if last_row:
                            # Get all cached data for this symbol/interval
                            cursor.execute('''
                                SELECT timestamp, open, high, low, close, volume
                                FROM ohlcv_cache
                                WHERE symbol = ? AND interval = ?
                                ORDER BY timestamp ASC
                            ''', (symbol, interval))
                            rows = cursor.fetchall()
                            if rows:
                                import pandas as pd
                                data = pd.DataFrame([dict(row) for row in rows])
                                data['timestamp'] = pd.to_datetime(data['timestamp'])
                                data.set_index('timestamp', inplace=True)
                                df = data
                                cached_at = last_row['cached_at']
                                logger.warning(f"[_fetch_data_for_symbol] Using STALE cached data for {symbol} (cached at {cached_at}). Data has {len(df)} rows.")
                except Exception as cache_err:
                    logger.error(f"[_fetch_data_for_symbol] Failed to retrieve cache fallback for {symbol}: {cache_err}")
        
        if df is not None and not df.empty:
            # Check for high volatility and invalidate cache if price moved >2%
            if 'Close' in df.columns or 'close' in df.columns:
                close_col = 'Close' if 'Close' in df.columns else 'close'
                current_price = df[close_col].iloc[-1]  # Last close price
                self.check_volatility_and_invalidate_cache(symbol, current_price)
            
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
