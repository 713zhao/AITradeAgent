"""
TD Ameritrade (TDA) Market Data Module

This module provides market data integration with TD Ameritrade API,
handling real-time quotes, price history, and market data subscriptions.

Key Features:
- Real-time quote fetching
- Historical price data retrieval
- Market data caching and management
- Data validation and cleaning
- Rate limiting and request optimization
- Performance monitoring

Author: PicotradeAgent
Version: 6.3.0
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import json

from finance_service.brokers.tda_broker import TDAConfig, TDAAuthManager
from finance_service.brokers.tda_client import TDAClient
from finance_service.brokers.base_broker import MarketData, AssetType
from finance_service.core.data_types import (
    BarData as OurBarData, TimeFrame, MarketDataRequest, HistoricalDataRequest
)


class TDADataType(str, Enum):
    """TDA data types"""
    QUOTE = "QUOTE"
    PRICE_HISTORY = "PRICE_HISTORY"
    FUNDAMENTAL = "FUNDAMENTAL"
    OPTION_CHAIN = "OPTION_CHAIN"


class TDAQuoteField(str, Enum):
    """TDA quote fields"""
    SYMBOL = "symbol"
    BID_PRICE = "bidPrice"
    ASK_PRICE = "askPrice"
    LAST_PRICE = "lastPrice"
    BID_SIZE = "bidSize"
    ASK_SIZE = "askSize"
    LAST_SIZE = "lastSize"
    TOTAL_VOLUME = "totalVolume"
    OPEN_PRICE = "openPrice"
    HIGH_PRICE = "highPrice"
    LOW_PRICE = "lowPrice"
    CLOSE_PRICE = "closePrice"
    NET_CHANGE = "netChange"
    NET_CHANGE_PERCENT = "netChangePercent"
    DELAYED = "delayed"
    TRADING_HALTED = "tradingHalted"
    DAYS_TO_EXPIRATION = "daysToExpiration"
    TIME_VALUE = "timeValue"
    OPTION_DELIVERABLE_LIST = "optionDeliverableList"


@dataclass
class TDAQuote:
    """TDA quote data structure"""
    symbol: str
    bid_price: float
    ask_price: float
    last_price: float
    bid_size: int
    ask_size: int
    last_size: int
    total_volume: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    net_change: float
    net_change_percent: float
    timestamp: datetime
    
    def to_market_data(self) -> MarketData:
        """Convert to MarketData format"""
        return MarketData(
            symbol=self.symbol,
            bid=self.bid_price,
            ask=self.ask_price,
            last=self.last_price,
            volume=self.total_volume,
            timestamp=self.timestamp
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "bid_price": self.bid_price,
            "ask_price": self.ask_price,
            "last_price": self.last_price,
            "bid_size": self.bid_size,
            "ask_size": self.ask_size,
            "last_size": self.last_size,
            "total_volume": self.total_volume,
            "open_price": self.open_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "close_price": self.close_price,
            "net_change": self.net_change,
            "net_change_percent": self.net_change_percent,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class TDAPriceBar:
    """TDA price bar data"""
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: datetime
    
    def to_our_bar_data(self, symbol: str) -> OurBarData:
        """Convert to our BarData format"""
        return OurBarData(
            symbol=symbol,
            timestamp=self.timestamp,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class TDADataCache:
    """TDA data cache configuration"""
    max_size: int = 1000
    ttl_seconds: int = 300  # 5 minutes
    cleanup_interval: int = 60  # 1 minute


class TDAMarketDataManager:
    """
    TDA Market Data Manager
    
    Manages market data fetching, caching, and distribution for TD Ameritrade.
    """
    
    def __init__(self, config: TDAConfig, tda_client: TDAClient):
        self.config = config
        self.tda_client = tda_client
        self.logger = logging.getLogger(f"{__name__}.TDAMarketDataManager")
        
        # Data storage
        self.quotes_cache: Dict[str, TDAQuote] = {}
        self.price_history_cache: Dict[str, List[TDAPriceBar]] = {}
        self.subscribed_symbols: List[str] = []
        self.data_callbacks: Dict[str, List[Callable]] = {}
        
        # Cache management
        self.cache_config = TDADataCache()
        self.last_cleanup = datetime.now()
        
        # Threading
        self.executor = ThreadPoolExecutor(max_workers=3)
        self._shutdown_event = asyncio.Event()
        
        # Performance tracking
        self.request_stats: Dict[str, int] = {}
        self.cache_hit_stats: Dict[str, int] = {}
        self.last_request_times: Dict[str, datetime] = {}
        
        self.logger.info("TDA Market Data Manager initialized")
    
    async def get_quotes(self, symbols: List[str], force_refresh: bool = False) -> Dict[str, MarketData]:
        """
        Get quotes for symbols
        
        Args:
            symbols: List of symbols to get quotes for
            force_refresh: Force refresh from TDA even if cached
            
        Returns:
            Dict[str, MarketData]: Dictionary of market data by symbol
        """
        try:
            quotes = {}
            
            # Check cache first
            symbols_to_fetch = []
            for symbol in symbols:
                if force_refresh or self._should_refresh_quote(symbol):
                    symbols_to_fetch.append(symbol)
                elif symbol in self.quotes_cache:
                    quotes[symbol] = self.quotes_cache[symbol].to_market_data()
                    self._update_cache_hit_stats(symbol, True)
            
            # Fetch fresh quotes if needed
            if symbols_to_fetch:
                self.logger.debug(f"Fetching {len(symbols_to_fetch)} fresh quotes")
                fresh_quotes = await self._fetch_quotes_from_tda(symbols_to_fetch)
                quotes.update(fresh_quotes)
                
                # Update cache
                for symbol, market_data in fresh_quotes.items():
                    tda_quote = TDAQuote(
                        symbol=symbol,
                        bid_price=market_data.bid,
                        ask_price=market_data.ask,
                        last_price=market_data.last,
                        bid_size=0,  # TDA doesn't provide bid/ask size in quotes
                        ask_size=0,
                        last_size=0,
                        total_volume=market_data.volume,
                        open_price=0.0,
                        high_price=0.0,
                        low_price=0.0,
                        close_price=market_data.last,
                        net_change=0.0,
                        net_change_percent=0.0,
                        timestamp=market_data.timestamp
                    )
                    self.quotes_cache[symbol] = tda_quote
                    self.last_request_times[symbol] = datetime.now()
            
            # Notify callbacks
            for symbol in quotes.keys():
                self._notify_data_callbacks(symbol, quotes[symbol])
            
            self.logger.info(f"Retrieved quotes for {len(quotes)} symbols")
            return quotes
            
        except Exception as e:
            self.logger.error(f"Error getting quotes: {e}")
            return {}
    
    async def get_price_history(self, symbol: str, timeframe: TimeFrame, 
                               start_date: datetime, end_date: datetime,
                               force_refresh: bool = False) -> List[OurBarData]:
        """
        Get price history for a symbol
        
        Args:
            symbol: Symbol to get history for
            timeframe: Time frame for the data
            start_date: Start date
            end_date: End date
            force_refresh: Force refresh from TDA
            
        Returns:
            List[OurBarData]: Historical bar data
        """
        try:
            # Check cache first
            cache_key = f"{symbol}_{timeframe.value}_{start_date.date()}_{end_date.date()}"
            
            if not force_refresh and cache_key in self.price_history_cache:
                cached_bars = self.price_history_cache[cache_key]
                # Filter by date range
                filtered_bars = [
                    bar.to_our_bar_data(symbol) for bar in cached_bars
                    if start_date <= bar.timestamp <= end_date
                ]
                if filtered_bars:
                    self.logger.debug(f"Using cached price history for {symbol}")
                    self._update_cache_hit_stats(cache_key, True)
                    return filtered_bars
            
            # Fetch from TDA
            self.logger.debug(f"Fetching price history for {symbol}")
            tda_bars = await self._fetch_price_history_from_tda(symbol, timeframe, start_date, end_date)
            
            # Convert to our format
            our_bars = [bar.to_our_bar_data(symbol) for bar in tda_bars]
            
            # Cache the result
            self.price_history_cache[cache_key] = tda_bars
            
            # Cleanup cache periodically
            await self._cleanup_cache()
            
            self.logger.info(f"Retrieved {len(our_bars)} bars for {symbol}")
            return our_bars
            
        except Exception as e:
            self.logger.error(f"Error getting price history for {symbol}: {e}")
            return []
    
    async def subscribe_quotes(self, symbols: List[str]) -> bool:
        """
        Subscribe to quote updates
        
        Args:
            symbols: List of symbols to subscribe to
            
        Returns:
            bool: True if subscription successful
        """
        try:
            self.logger.info(f"Subscribing to quotes for: {symbols}")
            
            # Add to subscribed symbols
            for symbol in symbols:
                if symbol not in self.subscribed_symbols:
                    self.subscribed_symbols.append(symbol)
                if symbol not in self.data_callbacks:
                    self.data_callbacks[symbol] = []
            
            # Start quote monitoring task
            asyncio.create_task(self._monitor_quotes())
            
            self.logger.info(f"Subscribed to quotes for {len(symbols)} symbols")
            return True
            
        except Exception as e:
            self.logger.error(f"Error subscribing to quotes: {e}")
            return False
    
    async def unsubscribe_quotes(self, symbols: List[str]) -> bool:
        """
        Unsubscribe from quote updates
        
        Args:
            symbols: List of symbols to unsubscribe from
            
        Returns:
            bool: True if unsubscription successful
        """
        try:
            self.logger.info(f"Unsubscribing from quotes for: {symbols}")
            
            for symbol in symbols:
                if symbol in self.subscribed_symbols:
                    self.subscribed_symbols.remove(symbol)
                if symbol in self.data_callbacks:
                    del self.data_callbacks[symbol]
            
            self.logger.info(f"Unsubscribed from quotes for {len(symbols)} symbols")
            return True
            
        except Exception as e:
            self.logger.error(f"Error unsubscribing from quotes: {e}")
            return False
    
    def add_data_callback(self, symbol: str, callback: Callable):
        """
        Add data callback for a symbol
        
        Args:
            symbol: Symbol to add callback for
            callback: Callback function
        """
        if symbol not in self.data_callbacks:
            self.data_callbacks[symbol] = []
        self.data_callbacks[symbol].append(callback)
    
    def remove_data_callback(self, symbol: str, callback: Callable):
        """
        Remove data callback for a symbol
        
        Args:
            symbol: Symbol to remove callback from
            callback: Callback function
        """
        if symbol in self.data_callbacks and callback in self.data_callbacks[symbol]:
            self.data_callbacks[symbol].remove(callback)
    
    def get_subscription_status(self) -> Dict[str, bool]:
        """Get subscription status for all symbols"""
        return {symbol: symbol in self.subscribed_symbols for symbol in self.data_callbacks.keys()}
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            "quotes_cache_size": len(self.quotes_cache),
            "price_history_cache_size": len(self.price_history_cache),
            "cache_hit_stats": self.cache_hit_stats.copy(),
            "request_stats": self.request_stats.copy(),
            "subscribed_symbols": len(self.subscribed_symbols)
        }
    
    async def close(self):
        """Close the market data manager"""
        self._shutdown_event.set()
    
    # Private methods
    
    def _should_refresh_quote(self, symbol: str) -> bool:
        """Check if quote should be refreshed"""
        # Check if we have cached data
        if symbol not in self.quotes_cache:
            return True
        
        # Check if cache has expired
        last_request = self.last_request_times.get(symbol)
        if not last_request:
            return True
        
        # Refresh if older than 5 seconds for subscribed symbols
        if symbol in self.subscribed_symbols:
            return (datetime.now() - last_request).total_seconds() > 5.0
        
        # Refresh if older than 30 seconds for non-subscribed
        return (datetime.now() - last_request).total_seconds() > 30.0
    
    async def _fetch_quotes_from_tda(self, symbols: List[str]) -> Dict[str, MarketData]:
        """Fetch quotes from TDA API"""
        try:
            # Use TDA client to get quotes
            quotes_data = await self.tda_client.get_quotes(symbols)
            
            quotes = {}
            if quotes_data and "quote" in quotes_data:
                for quote_info in quotes_data["quote"]:
                    symbol = quote_info.get("symbol", "")
                    
                    market_data = MarketData(
                        symbol=symbol,
                        bid=quote_info.get("bidPrice", 0.0),
                        ask=quote_info.get("askPrice", 0.0),
                        last=quote_info.get("lastPrice", 0.0),
                        volume=quote_info.get("totalVolume", 0),
                        timestamp=datetime.now()
                    )
                    
                    quotes[symbol] = market_data
                    self._update_request_stats("quotes")
            
            return quotes
            
        except Exception as e:
            self.logger.error(f"Error fetching quotes from TDA: {e}")
            return {}
    
    async def _fetch_price_history_from_tda(self, symbol: str, timeframe: TimeFrame,
                                          start_date: datetime, end_date: datetime) -> List[TDAPriceBar]:
        """Fetch price history from TDA API"""
        try:
            # Convert timeframe to TDA format
            tda_period_type, tda_period, tda_frequency_type, tda_frequency = \
                self._convert_timeframe_to_tda(timeframe)
            
            # Prepare parameters
            params = {
                "symbol": symbol,
                "periodType": tda_period_type,
                "period": tda_period,
                "frequencyType": tda_frequency_type,
                "frequency": tda_frequency,
                "needExtendedHoursData": "true"
            }
            
            # Adjust for specific date range if needed
            if start_date != end_date:
                params["startDate"] = int(start_date.timestamp() * 1000)
                params["endDate"] = int(end_date.timestamp() * 1000)
            
            # Use TDA client to get price history
            history_data = await self.tda_client.get_price_history(symbol, **params)
            
            bars = []
            if history_data and "candles" in history_data:
                for candle in history_data["candles"]:
                    bar = TDAPriceBar(
                        open=candle["open"],
                        high=candle["high"],
                        low=candle["low"],
                        close=candle["close"],
                        volume=candle["volume"],
                        timestamp=datetime.fromtimestamp(candle["datetime"] / 1000)
                    )
                    bars.append(bar)
                
                self._update_request_stats("price_history")
            
            return bars
            
        except Exception as e:
            self.logger.error(f"Error fetching price history from TDA: {e}")
            return []
    
    def _convert_timeframe_to_tda(self, timeframe: TimeFrame) -> Tuple[str, int, str, int]:
        """Convert TimeFrame to TDA parameters"""
        mapping = {
            TimeFrame.M1: ("day", 1, "minute", 1),
            TimeFrame.M5: ("day", 1, "minute", 5),
            TimeFrame.M15: ("day", 1, "minute", 15),
            TimeFrame.M30: ("day", 1, "minute", 30),
            TimeFrame.H1: ("day", 1, "hour", 1),
            TimeFrame.H4: ("day", 1, "hour", 4),
            TimeFrame.D1: ("day", 1, "daily", 1),
            TimeFrame.W1: ("month", 1, "weekly", 1),
            TimeFrame.MN1: ("year", 1, "monthly", 1)
        }
        return mapping.get(timeframe, ("day", 1, "daily", 1))
    
    async def _monitor_quotes(self):
        """Monitor and update quotes for subscribed symbols"""
        while not self._shutdown_event.is_set() and self.subscribed_symbols:
            try:
                # Get fresh quotes for subscribed symbols
                quotes = await self.get_quotes(self.subscribed_symbols, force_refresh=True)
                
                # Small delay between updates
                await asyncio.sleep(5.0)
                
            except Exception as e:
                self.logger.error(f"Error in quote monitoring: {e}")
                await asyncio.sleep(10.0)
    
    def _notify_data_callbacks(self, symbol: str, market_data: MarketData):
        """Notify registered callbacks for a symbol"""
        if symbol in self.data_callbacks:
            for callback in self.data_callbacks[symbol]:
                try:
                    callback(market_data)
                except Exception as e:
                    self.logger.error(f"Error in data callback for {symbol}: {e}")
    
    def _update_cache_hit_stats(self, key: str, hit: bool):
        """Update cache hit/miss statistics"""
        if hit:
            self.cache_hit_stats[key] = self.cache_hit_stats.get(key, 0) + 1
        else:
            # Track misses separately if needed
            pass
    
    def _update_request_stats(self, data_type: str):
        """Update request statistics"""
        self.request_stats[data_type] = self.request_stats.get(data_type, 0) + 1
    
    async def _cleanup_cache(self):
        """Cleanup expired cache entries"""
        try:
            current_time = datetime.now()
            
            # Cleanup quotes cache
            expired_quotes = []
            for symbol, quote in self.quotes_cache.items():
                if (current_time - quote.timestamp).total_seconds() > self.cache_config.ttl_seconds:
                    expired_quotes.append(symbol)
            
            for symbol in expired_quotes:
                del self.quotes_cache[symbol]
                if symbol in self.last_request_times:
                    del self.last_request_times[symbol]
            
            # Cleanup price history cache
            expired_history = []
            for cache_key, bars in self.price_history_cache.items():
                if bars and (current_time - bars[0].timestamp).total_seconds() > self.cache_config.ttl_seconds:
                    expired_history.append(cache_key)
            
            for cache_key in expired_history:
                del self.price_history_cache[cache_key]
            
            # Cleanup statistics periodically
            if (current_time - self.last_cleanup).total_seconds() > 3600:  # 1 hour
                # Keep only recent stats
                for key in list(self.cache_hit_stats.keys()):
                    if self.cache_hit_stats[key] < 5:  # Remove rarely used entries
                        del self.cache_hit_stats[key]
                
                self.last_cleanup = current_time
            
            if expired_quotes or expired_history:
                self.logger.debug(f"Cleaned up {len(expired_quotes)} quotes and {len(expired_history)} history entries")
            
        except Exception as e:
            self.logger.error(f"Error during cache cleanup: {e}")