"""
Cryptocurrency Exchange Client Module

This module provides unified client interface for multiple cryptocurrency exchanges,
including Binance and Coinbase Pro, with common functionality and error handling.

Key Features:
- Unified client interface for crypto exchanges
- Exchange-specific implementations (Binance, Coinbase Pro)
- Common trading operations
- Market data aggregation
- Rate limiting and error handling
- Performance monitoring

Author: PicotradeAgent
Version: 6.3.0
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union, Type
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import json

from finance_service.brokers.binance_broker import BinanceConfig, BinanceBroker
from finance_service.brokers.coinbase_broker import CoinbaseConfig, CoinbaseBroker
from finance_service.core.events import EventManager


class CryptoExchange(str, Enum):
    """Supported cryptocurrency exchanges"""
    BINANCE = "BINANCE"
    COINBASE = "COINBASE"


class CryptoOrderSide(str, Enum):
    """Crypto order sides"""
    BUY = "BUY"
    SELL = "SELL"


class CryptoOrderType(str, Enum):
    """Crypto order types"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class CryptoTimeInForce(str, Enum):
    """Crypto time in force options"""
    GOOD_TILL_CANCEL = "GTC"
    IMMEDIATE_OR_CANCEL = "IOC"
    FILL_OR_KILL = "FOK"


@dataclass
class CryptoMarketData:
    """Unified crypto market data"""
    exchange: str
    symbol: str
    bid: float
    ask: float
    last: float
    volume_24h: float
    price_change_24h: float
    price_change_percent_24h: float
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "volume_24h": self.volume_24h,
            "price_change_24h": self.price_change_24h,
            "price_change_percent_24h": self.price_change_percent_24h,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class CryptoBalance:
    """Unified crypto balance"""
    exchange: str
    asset: str
    free: float
    locked: float
    total: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "exchange": self.exchange,
            "asset": self.asset,
            "free": self.free,
            "locked": self.locked,
            "total": self.total
        }


@dataclass
class CryptoOrder:
    """Unified crypto order"""
    exchange: str
    order_id: str
    symbol: str
    side: CryptoOrderSide
    order_type: CryptoOrderType
    quantity: float
    price: Optional[float]
    status: str
    filled_quantity: float
    remaining_quantity: float
    average_price: Optional[float]
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "exchange": self.exchange,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": self.quantity,
            "price": self.price,
            "status": self.status,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "average_price": self.average_price,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class CryptoExchangeConfig:
    """Unified crypto exchange configuration"""
    # Binance configuration
    binance_api_key: str = ""
    binance_secret_key: str = ""
    binance_use_testnet: bool = True
    
    # Coinbase configuration
    coinbase_api_key: str = ""
    coinbase_secret_key: str = ""
    coinbase_passphrase: str = ""
    coinbase_use_sandbox: bool = True
    
    # Common settings
    enabled_exchanges: List[CryptoExchange] = field(default_factory=lambda: [CryptoExchange.BINANCE])
    default_exchange: CryptoExchange = CryptoExchange.BINANCE
    
    # Connection settings
    connection_timeout: int = 30
    request_timeout: int = 10
    max_retries: int = 3
    
    # Rate limiting
    requests_per_second: int = 10
    orders_per_second: int = 5
    
    # Market data settings
    update_interval: int = 5  # seconds
    max_symbols_per_subscription: int = 50
    
    # Logging
    log_level: str = "INFO"


class CryptoExchangeClient:
    """
    Unified Cryptocurrency Exchange Client
    
    Provides a unified interface for multiple cryptocurrency exchanges
    with common operations and cross-exchange functionality.
    """
    
    def __init__(self, config: CryptoExchangeConfig, event_manager: EventManager):
        self.config = config
        self.event_manager = event_manager
        self.logger = logging.getLogger(f"{__name__}.CryptoExchangeClient")
        
        # Exchange clients
        self.binance_client: Optional[BinanceBroker] = None
        self.coinbase_client: Optional[CoinbaseBroker] = None
        
        # Market data caching
        self.market_data_cache: Dict[str, Dict[str, CryptoMarketData]] = {}  # exchange -> symbol -> data
        self.balance_cache: Dict[str, List[CryptoBalance]] = {}  # exchange -> balances
        self.order_cache: Dict[str, List[CryptoOrder]] = {}  # exchange -> orders
        
        # Subscription management
        self.subscribed_symbols: Dict[str, List[str]] = {}  # exchange -> symbols
        self.data_callbacks: Dict[str, List[Callable]] = {}
        
        # Threading
        self.executor = ThreadPoolExecutor(max_workers=5)
        self._shutdown_event = asyncio.Event()
        
        # Performance tracking
        self.request_stats: Dict[str, int] = {}
        self.error_stats: Dict[str, int] = {}
        self.last_update_times: Dict[str, datetime] = {}
        
        self.logger.info("Crypto Exchange Client initialized")
    
    async def initialize(self) -> bool:
        """
        Initialize exchange clients
        
        Returns:
            bool: True if initialization successful
        """
        try:
            self.logger.info("Initializing crypto exchange clients")
            
            success = True
            
            # Initialize Binance if enabled
            if CryptoExchange.BINANCE in self.config.enabled_exchanges:
                if await self._initialize_binance():
                    self.logger.info("Binance client initialized successfully")
                else:
                    self.logger.error("Failed to initialize Binance client")
                    success = False
            
            # Initialize Coinbase if enabled
            if CryptoExchange.COINBASE in self.config.enabled_exchanges:
                if await self._initialize_coinbase():
                    self.logger.info("Coinbase client initialized successfully")
                else:
                    self.logger.error("Failed to initialize Coinbase client")
                    success = False
            
            if success:
                self.logger.info("All crypto exchange clients initialized successfully")
            else:
                self.logger.warning("Some crypto exchange clients failed to initialize")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error initializing crypto exchange clients: {e}")
            return False
    
    async def _initialize_binance(self) -> bool:
        """Initialize Binance client"""
        try:
            if not self.config.binance_api_key or not self.config.binance_secret_key:
                self.logger.warning("Binance API credentials not provided")
                return False
            
            binance_config = BinanceConfig(
                api_key=self.config.binance_api_key,
                secret_key=self.config.binance_secret_key,
                use_testnet=self.config.binance_use_testnet,
                connection_timeout=self.config.connection_timeout,
                request_timeout=self.config.request_timeout
            )
            
            self.binance_client = BinanceBroker(binance_config, self.event_manager)
            return await self.binance_client.connect()
            
        except Exception as e:
            self.logger.error(f"Error initializing Binance client: {e}")
            return False
    
    async def _initialize_coinbase(self) -> bool:
        """Initialize Coinbase client"""
        try:
            if not all([self.config.coinbase_api_key, self.config.coinbase_secret_key, self.config.coinbase_passphrase]):
                self.logger.warning("Coinbase API credentials not provided")
                return False
            
            coinbase_config = CoinbaseConfig(
                api_key=self.config.coinbase_api_key,
                secret_key=self.config.coinbase_secret_key,
                passphrase=self.config.coinbase_passphrase,
                use_sandbox=self.config.coinbase_use_sandbox,
                connection_timeout=self.config.connection_timeout,
                request_timeout=self.config.request_timeout
            )
            
            self.coinbase_client = CoinbaseBroker(coinbase_config, self.event_manager)
            return await self.coinbase_client.connect()
            
        except Exception as e:
            self.logger.error(f"Error initializing Coinbase client: {e}")
            return False
    
    async def place_order(self, exchange: CryptoExchange, symbol: str, side: CryptoOrderSide,
                         order_type: CryptoOrderType, quantity: float, 
                         price: Optional[float] = None) -> Optional[CryptoOrder]:
        """
        Place an order on specified exchange
        
        Args:
            exchange: Exchange to place order on
            symbol: Trading symbol
            side: Order side (BUY/SELL)
            order_type: Order type
            quantity: Order quantity
            price: Order price (for limit orders)
            
        Returns:
            CryptoOrder: Placed order or None if failed
        """
        try:
            self.logger.info(f"Placing {exchange.value} order: {symbol} {side.value} {quantity}")
            
            # Convert to broker-specific order request
            from finance_service.core.data_types import OrderRequest, OrderSide, OrderType
            
            order_request = OrderRequest(
                symbol=symbol,
                side=OrderSide(side.value),
                quantity=quantity,
                order_type=OrderType(order_type.value),
                limit_price=price
            )
            
            # Route to appropriate exchange
            if exchange == CryptoExchange.BINANCE and self.binance_client:
                result = await self.binance_client.place_order(order_request)
            elif exchange == CryptoExchange.COINBASE and self.coinbase_client:
                result = await self.coinbase_client.place_order(order_request)
            else:
                self.logger.error(f"Exchange {exchange.value} not available")
                return None
            
            if result and result.success:
                # Convert to unified order format
                order = CryptoOrder(
                    exchange=exchange.value,
                    order_id=result.order_id,
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    quantity=quantity,
                    price=price,
                    status="PENDING",
                    filled_quantity=0.0,
                    remaining_quantity=quantity,
                    average_price=None,
                    timestamp=datetime.now()
                )
                
                # Cache order
                if exchange.value not in self.order_cache:
                    self.order_cache[exchange.value] = []
                self.order_cache[exchange.value].append(order)
                
                self._update_request_stats(f"place_order_{exchange.value}")
                return order
            else:
                self.logger.error(f"Failed to place {exchange.value} order: {result.error_message if result else 'Unknown error'}")
                return None
            
        except Exception as e:
            self.logger.error(f"Error placing {exchange.value} order: {e}")
            self._update_error_stats(f"place_order_{exchange.value}")
            return None
    
    async def cancel_order(self, exchange: CryptoExchange, order_id: str, symbol: str) -> bool:
        """
        Cancel an order
        
        Args:
            exchange: Exchange where order was placed
            order_id: Order ID to cancel
            symbol: Symbol of the order
            
        Returns:
            bool: True if cancellation successful
        """
        try:
            self.logger.info(f"Cancelling {exchange.value} order: {order_id}")
            
            # Route to appropriate exchange
            success = False
            if exchange == CryptoExchange.BINANCE and self.binance_client:
                success = await self.binance_client.cancel_order(order_id, symbol)
            elif exchange == CryptoExchange.COINBASE and self.coinbase_client:
                success = await self.coinbase_client.cancel_order(order_id)
            
            if success:
                # Update order cache
                if exchange.value in self.order_cache:
                    for order in self.order_cache[exchange.value]:
                        if order.order_id == order_id:
                            order.status = "CANCELLED"
                            break
                
                self._update_request_stats(f"cancel_order_{exchange.value}")
            else:
                self.logger.error(f"Failed to cancel {exchange.value} order {order_id}")
                self._update_error_stats(f"cancel_order_{exchange.value}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error cancelling {exchange.value} order: {e}")
            return False
    
    async def get_balances(self, exchange: CryptoExchange) -> List[CryptoBalance]:
        """
        Get balances from specified exchange
        
        Args:
            exchange: Exchange to get balances from
            
        Returns:
            List[CryptoBalance]: List of balances
        """
        try:
            balances = []
            
            # Route to appropriate exchange
            if exchange == CryptoExchange.BINANCE and self.binance_client:
                positions = await self.binance_client.get_positions()
                for position in positions:
                    balance = CryptoBalance(
                        exchange=exchange.value,
                        asset=position.symbol,
                        free=position.quantity,  # Simplified
                        locked=0.0,  # Would need separate locked balance
                        total=position.quantity
                    )
                    balances.append(balance)
                    
            elif exchange == CryptoExchange.COINBASE and self.coinbase_client:
                positions = await self.coinbase_client.get_positions()
                for position in positions:
                    balance = CryptoBalance(
                        exchange=exchange.value,
                        asset=position.symbol,
                        free=position.quantity,
                        locked=0.0,
                        total=position.quantity
                    )
                    balances.append(balance)
            
            # Cache balances
            self.balance_cache[exchange.value] = balances
            self._update_request_stats(f"get_balances_{exchange.value}")
            
            return balances
            
        except Exception as e:
            self.logger.error(f"Error getting {exchange.value} balances: {e}")
            self._update_error_stats(f"get_balances_{exchange.value}")
            return []
    
    async def get_market_data(self, exchange: CryptoExchange, symbols: List[str]) -> Dict[str, CryptoMarketData]:
        """
        Get market data from specified exchange
        
        Args:
            exchange: Exchange to get data from
            symbols: List of symbols
            
        Returns:
            Dict[str, CryptoMarketData]: Market data by symbol
        """
        try:
            market_data = {}
            
            # Route to appropriate exchange
            if exchange == CryptoExchange.BINANCE and self.binance_client:
                # Subscribe to market data
                await self.binance_client.subscribe_market_data(symbols)
                
                # Get current data
                for symbol in symbols:
                    if symbol in self.binance_client.market_data_cache:
                        data = self.binance_client.market_data_cache[symbol]
                        market_data[symbol] = CryptoMarketData(
                            exchange=exchange.value,
                            symbol=symbol,
                            bid=data.bid,
                            ask=data.ask,
                            last=data.last,
                            volume_24h=data.volume,
                            price_change_24h=0.0,  # Would need to calculate
                            price_change_percent_24h=0.0,
                            timestamp=data.timestamp
                        )
                        
            elif exchange == CryptoExchange.COINBASE and self.coinbase_client:
                # Subscribe to market data
                await self.coinbase_client.subscribe_market_data(symbols)
                
                # Get current data
                for symbol in symbols:
                    if symbol in self.coinbase_client.market_data_cache:
                        data = self.coinbase_client.market_data_cache[symbol]
                        market_data[symbol] = CryptoMarketData(
                            exchange=exchange.value,
                            symbol=symbol,
                            bid=data.bid,
                            ask=data.ask,
                            last=data.last,
                            volume_24h=data.volume,
                            price_change_24h=0.0,
                            price_change_percent_24h=0.0,
                            timestamp=data.timestamp
                        )
            
            # Cache market data
            if exchange.value not in self.market_data_cache:
                self.market_data_cache[exchange.value] = {}
            self.market_data_cache[exchange.value].update(market_data)
            
            self._update_request_stats(f"get_market_data_{exchange.value}")
            return market_data
            
        except Exception as e:
            self.logger.error(f"Error getting {exchange.value} market data: {e}")
            self._update_error_stats(f"get_market_data_{exchange.value}")
            return {}
    
    async def get_best_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get best price across all exchanges for a symbol
        
        Args:
            symbol: Symbol to get price for
            
        Returns:
            Dict[str, Any]: Best price information
        """
        try:
            best_price = None
            best_exchange = None
            
            # Get prices from all enabled exchanges
            for exchange in self.config.enabled_exchanges:
                try:
                    market_data = await self.get_market_data(exchange, [symbol])
                    if symbol in market_data and market_data[symbol].bid > 0:
                        if best_price is None or market_data[symbol].bid > best_price:
                            best_price = market_data[symbol].bid
                            best_exchange = exchange.value
                except Exception as e:
                    self.logger.warning(f"Failed to get price from {exchange.value}: {e}")
                    continue
            
            if best_price:
                return {
                    "symbol": symbol,
                    "best_price": best_price,
                    "best_exchange": best_exchange,
                    "timestamp": datetime.now()
                }
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting best price for {symbol}: {e}")
            return None
    
    async def subscribe_market_data(self, symbols: List[str]) -> bool:
        """
        Subscribe to market data for symbols across all exchanges
        
        Args:
            symbols: List of symbols to subscribe to
            
        Returns:
            bool: True if subscription successful
        """
        try:
            success = True
            
            # Subscribe on each enabled exchange
            for exchange in self.config.enabled_exchanges:
                try:
                    if exchange == CryptoExchange.BINANCE and self.binance_client:
                        result = await self.binance_client.subscribe_market_data(symbols)
                    elif exchange == CryptoExchange.COINBASE and self.coinbase_client:
                        result = await self.coinbase_client.subscribe_market_data(symbols)
                    else:
                        result = False
                    
                    if result:
                        if exchange.value not in self.subscribed_symbols:
                            self.subscribed_symbols[exchange.value] = []
                        self.subscribed_symbols[exchange.value].extend(symbols)
                    else:
                        success = False
                        
                except Exception as e:
                    self.logger.error(f"Failed to subscribe to {exchange.value}: {e}")
                    success = False
            
            if success:
                self.logger.info(f"Subscribed to market data for {len(symbols)} symbols")
            else:
                self.logger.warning("Some subscriptions failed")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error subscribing to market data: {e}")
            return False
    
    async def unsubscribe_market_data(self, symbols: List[str]) -> bool:
        """
        Unsubscribe from market data
        
        Args:
            symbols: List of symbols to unsubscribe from
            
        Returns:
            bool: True if unsubscription successful
        """
        try:
            success = True
            
            # Unsubscribe from each exchange
            for exchange in self.config.enabled_exchanges:
                try:
                    if exchange == CryptoExchange.BINANCE and self.binance_client:
                        result = await self.binance_client.unsubscribe_market_data(symbols)
                    elif exchange == CryptoExchange.COINBASE and self.coinbase_client:
                        result = await self.coinbase_client.unsubscribe_market_data(symbols)
                    else:
                        result = False
                    
                    if result and exchange.value in self.subscribed_symbols:
                        for symbol in symbols:
                            if symbol in self.subscribed_symbols[exchange.value]:
                                self.subscribed_symbols[exchange.value].remove(symbol)
                    else:
                        success = False
                        
                except Exception as e:
                    self.logger.error(f"Failed to unsubscribe from {exchange.value}: {e}")
                    success = False
            
            self.logger.info(f"Unsubscribed from market data for {len(symbols)} symbols")
            return success
            
        except Exception as e:
            self.logger.error(f"Error unsubscribing from market data: {e}")
            return False
    
    def add_data_callback(self, symbol: str, callback: Callable):
        """Add data callback for a symbol"""
        if symbol not in self.data_callbacks:
            self.data_callbacks[symbol] = []
        self.data_callbacks[symbol].append(callback)
    
    def remove_data_callback(self, symbol: str, callback: Callable):
        """Remove data callback for a symbol"""
        if symbol in self.data_callbacks and callback in self.data_callbacks[symbol]:
            self.data_callbacks[symbol].remove(callback)
    
    def get_exchange_status(self) -> Dict[str, bool]:
        """Get connection status for all exchanges"""
        status = {}
        
        if self.binance_client:
            status["BINANCE"] = self.binance_client.is_connected()
        if self.coinbase_client:
            status["COINBASE"] = self.coinbase_client.is_connected()
        
        return status
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        return {
            "request_stats": self.request_stats.copy(),
            "error_stats": self.error_stats.copy(),
            "exchange_status": self.get_exchange_status(),
            "cached_market_data": {
                exchange: len(data) for exchange, data in self.market_data_cache.items()
            },
            "cached_balances": {
                exchange: len(balances) for exchange, balances in self.balance_cache.items()
            },
            "subscribed_symbols": self.subscribed_symbols.copy()
        }
    
    async def close(self):
        """Close all exchange connections"""
        try:
            self.logger.info("Closing crypto exchange connections")
            
            self._shutdown_event.set()
            
            # Close Binance connection
            if self.binance_client:
                await self.binance_client.disconnect()
            
            # Close Coinbase connection
            if self.coinbase_client:
                await self.coinbase_client.disconnect()
            
            self.logger.info("Crypto exchange connections closed")
            
        except Exception as e:
            self.logger.error(f"Error closing crypto exchange connections: {e}")
    
    # Private helper methods
    
    def _update_request_stats(self, operation: str):
        """Update request statistics"""
        self.request_stats[operation] = self.request_stats.get(operation, 0) + 1
    
    def _update_error_stats(self, operation: str):
        """Update error statistics"""
        self.error_stats[operation] = self.error_stats.get(operation, 0) + 1