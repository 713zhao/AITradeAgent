"""
Binance Cryptocurrency Exchange Broker Implementation

This module provides comprehensive integration with Binance API for cryptocurrency trading,
supporting spot trading, futures trading, and real-time market data.

Key Features:
- Binance API integration for spot and futures trading
- Real-time WebSocket market data feeds
- Order management and tracking
- Portfolio and balance management
- Advanced order types (limit, market, stop, etc.)
- Rate limiting and error handling
- Event-driven architecture

Author: PicotradeAgent
Version: 6.3.0
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import json
import hmac
import hashlib
import base64
import urllib.parse

# WebSocket and HTTP client (would need websockets and aiohttp in production)
try:
    import websockets
    import aiohttp
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    # Mock classes for development
    class websockets: pass
    class aiohttp: pass

from finance_service.brokers.base_broker import BaseBroker, OrderResult, Position, AccountInfo, MarketData
from finance_service.brokers.base_broker import OrderSide, OrderType, OrderStatus, AssetType
from finance_service.core.events import Event, EventType, EventManager
from finance_service.core.data_types import OrderRequest, PositionRequest, AccountRequest


@dataclass
class BinanceConfig:
    """Binance broker configuration"""
    api_key: str
    api_secret: str
    testnet_base_url: str = "https://testnet.binance.vision"
    production_base_url: str = "https://api.binance.com"
    use_testnet: bool = False
    timeout: float = 10.0


# Binance-specific enums and constants
class BinanceAccountType(str, Enum):
    """Binance account types"""
    SPOT = "SPOT"
    MARGIN = "MARGIN"
    FUTURES = "FUTURES"


class BinanceOrderSide(str, Enum):
    """Binance order sides"""
    BUY = "BUY"
    SELL = "SELL"


class BinanceOrderType(str, Enum):
    """Binance order types"""
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"
    LIMIT_MAKER = "LIMIT_MAKER"


class BinanceTimeInForce(str, Enum):
    """Binance time in force"""
    GOOD_TILL_CANCEL = "GTC"
    IMMEDIATE_OR_CANCEL = "IOC"
    FILL_OR_KILL = "FOK"


class BinanceConnectionStatus(str, Enum):
    """Binance connection status"""
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"


@dataclass
class BinanceConfig:
    """Binance configuration settings"""
    api_key: str = ""
    secret_key: str = ""
    account_type: BinanceAccountType = BinanceAccountType.SPOT
    
    # API settings
    base_url: str = "https://api.binance.com"
    futures_url: str = "https://fapi.binance.com"
    testnet_url: str = "https://testnet.binance.vision"
    use_testnet: bool = True
    
    # WebSocket settings
    stream_base_url: str = "wss://stream.binance.com:9443"
    futures_stream_url: str = "wss://fstream.binance.com"
    testnet_stream_url: str = "wss://testnet.binance.vision"
    
    # Connection settings
    connection_timeout: int = 30
    request_timeout: int = 10
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # Rate limiting
    requests_per_second: int = 10
    orders_per_second: int = 10
    
    # Market data settings
    kline_interval: str = "1m"
    max_klines: int = 1000
    
    # Order settings
    default_time_in_force: BinanceTimeInForce = BinanceTimeInForce.GOOD_TILL_CANCEL
    
    # Logging
    log_level: str = "INFO"
    log_requests: bool = False
    log_responses: bool = False


@dataclass
class BinanceConnectionInfo:
    """Binance connection information"""
    status: BinanceConnectionStatus = BinanceConnectionStatus.DISCONNECTED
    connected_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    reconnect_attempts: int = 0
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset: Optional[datetime] = None
    error_message: Optional[str] = None
    
    def is_connected(self) -> bool:
        return self.status == BinanceConnectionStatus.CONNECTED
    
    def is_authenticated(self) -> bool:
        return self.status in [BinanceConnectionStatus.CONNECTED, BinanceConnectionStatus.RECONNECTING]


class BinanceAuthManager:
    """Binance Authentication Manager"""
    
    def __init__(self, config: BinanceConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.BinanceAuthManager")
        
        # Session management
        self.session: Optional[aiohttp.ClientSession] = None
        self.api_key: Optional[str] = None
        self.secret_key: Optional[str] = None
        
        # Rate limiting
        self.request_times: List[float] = []
        
    async def authenticate(self) -> bool:
        """
        Authenticate with Binance API
        
        Returns:
            bool: True if authentication successful
        """
        try:
            self.logger.info("Authenticating with Binance API")
            
            # Check credentials
            if not self.config.api_key or not self.config.secret_key:
                self.logger.warning("No Binance API credentials provided")
                return False
            
            # Create session
            self.session = aiohttp.ClientSession()
            
            # Store credentials
            self.api_key = self.config.api_key
            self.secret_key = self.config.secret_key
            
            # Test connection with account info
            account_info = await self.get_account_info()
            if account_info:
                self.logger.info("Successfully authenticated with Binance")
                return True
            else:
                self.logger.error("Authentication failed - could not get account info")
                return False
                
        except Exception as e:
            self.logger.error(f"Binance authentication failed: {e}")
            return False
    
    async def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Get account information"""
        try:
            if not self.session:
                await self.authenticate()
            
            # Determine base URL based on account type
            base_url = self._get_base_url()
            
            # Prepare request
            params = {"timestamp": int(time.time() * 1000)}
            signature = self._create_signature(params)
            params["signature"] = signature
            
            headers = {"X-MBX-APIKEY": self.api_key}
            
            # Make request
            url = f"{base_url}/api/v3/account"
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    self.logger.error(f"Binance account info failed: {response.status}")
                    return None
            
        except Exception as e:
            self.logger.error(f"Error getting Binance account info: {e}")
            return None
    
    def _get_base_url(self) -> str:
        """Get base URL based on account type and testnet setting"""
        if self.config.use_testnet:
            return self.config.testnet_url
        elif self.config.account_type == BinanceAccountType.FUTURES:
            return self.config.futures_url
        else:
            return self.config.base_url
    
    def _create_signature(self, params: Dict[str, Any]) -> str:
        """Create HMAC SHA256 signature for signed requests"""
        query_string = urllib.parse.urlencode(params)
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _check_rate_limit(self):
        """Check and enforce rate limiting"""
        current_time = time.time()
        
        # Remove old request times
        self.request_times = [t for t in self.request_times if current_time - t < 1.0]
        
        # Check if we're at rate limit
        if len(self.request_times) >= self.config.requests_per_second:
            sleep_time = 1.0 - (current_time - self.request_times[-self.config.requests_per_second])
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        self.request_times.append(current_time)
    
    async def make_signed_request(self, method: str, endpoint: str, 
                                data: Optional[Dict] = None) -> Optional[Dict]:
        """Make signed request to Binance API"""
        try:
            if not self.session:
                await self.authenticate()
            
            # Check rate limit
            self._check_rate_limit()
            
            # Prepare parameters
            params = {"timestamp": int(time.time() * 1000)}
            if data:
                params.update(data)
            
            # Create signature
            signature = self._create_signature(params)
            params["signature"] = signature
            
            # Prepare headers
            headers = {"X-MBX-APIKEY": self.api_key}
            
            # Get base URL
            base_url = self._get_base_url()
            url = f"{base_url}{endpoint}"
            
            # Make request
            async with self.session.request(
                method=method,
                url=url,
                params=params if method == "GET" else None,
                json=data if method in ["POST", "PUT", "DELETE"] else None,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.config.request_timeout)
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    self.logger.error(f"Binance API error: {response.status} - {error_text}")
                    return None
            
        except Exception as e:
            self.logger.error(f"Binance API request failed: {e}")
            return None
    
    async def close(self):
        """Close session"""
        if self.session:
            await self.session.close()


class BinanceBroker(BaseBroker):
    """
    Binance Cryptocurrency Exchange Broker
    
    Provides comprehensive integration with Binance API for cryptocurrency trading.
    """
    
    def __init__(self, config: BinanceConfig, event_manager: EventManager):
        super().__init__(event_manager)
        
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.BinanceBroker")
        
        # Authentication
        self.auth_manager = BinanceAuthManager(config)
        self.connection_info = BinanceConnectionInfo()
        
        # Market data tracking
        self.subscribed_streams: List[str] = []
        self.market_data_cache: Dict[str, MarketData] = {}
        self.market_data_callbacks: Dict[str, List[Callable]] = {}
        
        # Order tracking
        self.pending_orders: Dict[str, OrderRequest] = {}
        self.order_status_callbacks: Dict[str, List[Callable]] = {}
        
        # Position and account tracking
        self.positions_cache: Dict[str, Position] = {}
        self.account_info_cache: Optional[AccountInfo] = None
        
        # Threading and async support
        self.executor = ThreadPoolExecutor(max_workers=3)
        self._shutdown_event = asyncio.Event()
        
        # WebSocket connection
        self.websocket: Optional[Any] = None
        self.websocket_connected = False
        
        self.logger.info("Binance Broker initialized")
    
    async def connect(self) -> bool:
        """
        Connect to Binance
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self.logger.info("Connecting to Binance")
            
            self.connection_info.status = BinanceConnectionStatus.CONNECTING
            
            # Authenticate with Binance
            if await self.auth_manager.authenticate():
                self.connection_info.status = BinanceConnectionStatus.CONNECTED
                self.connection_info.connected_at = datetime.now()
                
                # Start WebSocket connection if available
                if WEBSOCKETS_AVAILABLE:
                    await self._start_websocket()
                
                # Test connection with account info
                account_info = await self.get_account_info()
                if account_info:
                    self.logger.info("Successfully connected to Binance")
                    return True
                else:
                    self.logger.warning("Connected but account info unavailable")
                    return True
            else:
                self.connection_info.status = BinanceConnectionStatus.ERROR
                self.logger.error("Failed to authenticate with Binance")
                return False
                
        except Exception as e:
            self.logger.error(f"Error connecting to Binance: {e}")
            self.connection_info.status = BinanceConnectionStatus.ERROR
            self.connection_info.error_message = str(e)
            return False
    
    async def disconnect(self) -> bool:
        """
        Disconnect from Binance
        
        Returns:
            bool: True if disconnection successful
        """
        try:
            self.logger.info("Disconnecting from Binance")
            
            # Close WebSocket connection
            if self.websocket:
                await self.websocket.close()
                self.websocket_connected = False
            
            # Close auth manager session
            await self.auth_manager.close()
            
            self.connection_info.status = BinanceConnectionStatus.DISCONNECTED
            self.connection_info.connected_at = None
            
            self.logger.info("Disconnected from Binance")
            return True
            
        except Exception as e:
            self.logger.error(f"Error disconnecting from Binance: {e}")
            return False
    
    async def place_order(self, order_request: OrderRequest) -> OrderResult:
        """
        Place an order through Binance
        
        Args:
            order_request: Order request with symbol, side, quantity, type, etc.
            
        Returns:
            OrderResult: Order placement result with ID and status
        """
        try:
            self.logger.info(f"Placing Binance order: {order_request.symbol} {order_request.side} {order_request.quantity}")
            
            # Validate order
            if not self.is_connected():
                return OrderResult(
                    success=False,
                    error_message="Not connected to Binance"
                )
            
            # Convert to Binance order format
            binance_order = self._create_binance_order(order_request)
            
            # Place order
            result = await self.auth_manager.make_signed_request(
                method="POST",
                endpoint="/api/v3/order",
                data=binance_order
            )
            
            if result:
                # Extract order ID from response
                order_id = str(result.get("orderId"))
                
                # Track order
                self.pending_orders[order_id] = order_request
                
                order_result = OrderResult(
                    order_id=order_id,
                    broker_order_id=order_id,
                    symbol=order_request.symbol,
                    side=order_request.side,
                    quantity=order_request.quantity,
                    order_type=order_request.order_type,
                    status=OrderStatus.PENDING,
                    submitted_at=datetime.now(),
                    broker_info={
                        "broker": "BINANCE",
                        "order": result
                    }
                )
                
                # Publish event
                self.event_manager.publish(Event(
                    type=EventType.ORDER_SUBMITTED,
                    data={
                        "broker": "BINANCE",
                        "order_id": order_id,
                        "symbol": order_request.symbol,
                        "side": order_request.side.value,
                        "quantity": order_request.quantity,
                        "order_type": order_request.order_type.value
                    }
                ))
                
                self.logger.info(f"Order placed successfully: {order_id}")
                return order_result
            else:
                return OrderResult(
                    success=False,
                    error_message="Failed to place order"
                )
            
        except Exception as e:
            self.logger.error(f"Error placing Binance order: {e}")
            return OrderResult(
                success=False,
                error_message=f"Order placement failed: {e}"
            )
    
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """
        Cancel an order
        
        Args:
            order_id: Order ID to cancel
            symbol: Symbol of the order
            
        Returns:
            bool: True if cancellation successful
        """
        try:
            self.logger.info(f"Cancelling Binance order: {order_id}")
            
            if not self.is_connected():
                return False
            
            # Cancel order
            cancel_data = {
                "symbol": symbol,
                "orderId": int(order_id)
            }
            
            result = await self.auth_manager.make_signed_request(
                method="DELETE",
                endpoint="/api/v3/order",
                data=cancel_data
            )
            
            if result:
                # Update order status
                if order_id in self.pending_orders:
                    self.pending_orders[order_id].status = OrderStatus.CANCELLED
                
                # Publish event
                self.event_manager.publish(Event(
                    type=EventType.ORDER_CANCELLED,
                    data={
                        "broker": "BINANCE",
                        "order_id": order_id
                    }
                ))
                
                self.logger.info(f"Order cancelled successfully: {order_id}")
                return True
            else:
                self.logger.error(f"Failed to cancel order {order_id}")
                return False
            
        except Exception as e:
            self.logger.error(f"Error cancelling Binance order {order_id}: {e}")
            return False
    
    async def get_positions(self) -> List[Position]:
        """
        Get current positions from Binance
        
        Returns:
            List[Position]: List of current positions
        """
        try:
            if not self.is_connected():
                return []
            
            # Get account info from Binance
            account_info = await self.auth_manager.make_signed_request(
                method="GET",
                endpoint="/api/v3/account"
            )
            
            positions = []
            
            if account_info and "balances" in account_info:
                for balance in account_info["balances"]:
                    symbol = balance["asset"]
                    free_amount = float(balance["free"])
                    locked_amount = float(balance["locked"])
                    total_amount = free_amount + locked_amount
                    
                    # Only include positions with non-zero balance
                    if total_amount > 0:
                        position = Position(
                            symbol=symbol,
                            quantity=total_amount,
                            avg_price=0.0,  # Would need trade history
                            market_value=0.0,  # Would need current price
                            unrealized_pnl=0.0,
                            realized_pnl=0.0,
                            asset_type=AssetType.CRYPTO,
                            broker="BINANCE",
                            last_updated=datetime.now()
                        )
                        positions.append(position)
            
            # Update cache
            self.positions_cache.clear()
            for position in positions:
                self.positions_cache[position.symbol] = position
            
            self.logger.info(f"Retrieved {len(positions)} positions from Binance")
            return positions
            
        except Exception as e:
            self.logger.error(f"Error getting Binance positions: {e}")
            return []
    
    async def get_account_info(self) -> Optional[AccountInfo]:
        """
        Get account information from Binance
        
        Returns:
            AccountInfo: Account information or None if unavailable
        """
        try:
            if not self.is_connected():
                return None
            
            # Get account info from Binance
            account_info = await self.auth_manager.make_signed_request(
                method="GET",
                endpoint="/api/v3/account"
            )
            
            if account_info:
                account = self._convert_binance_account_info(account_info)
                self.account_info_cache = account
                return account
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting Binance account info: {e}")
            return None
    
    async def subscribe_market_data(self, symbols: List[str]) -> bool:
        """
        Subscribe to real-time market data
        
        Args:
            symbols: List of symbols to subscribe to
            
        Returns:
            bool: True if subscription successful
        """
        try:
            self.logger.info(f"Subscribing to market data for: {symbols}")
            
            if WEBSOCKETS_AVAILABLE and self.websocket_connected:
                # Subscribe via WebSocket
                for symbol in symbols:
                    stream_name = f"{symbol.lower()}@ticker"
                    await self._subscribe_to_stream(stream_name)
                    
                    if symbol not in self.market_data_callbacks:
                        self.market_data_callbacks[symbol] = []
            else:
                # Fallback to polling
                for symbol in symbols:
                    quotes = await self._get_ticker(symbol)
                    if quotes:
                        self.market_data_cache[symbol] = quotes
                    
                    if symbol not in self.market_data_callbacks:
                        self.market_data_callbacks[symbol] = []
            
            self.logger.info(f"Subscribed to market data for {len(symbols)} symbols")
            return True
            
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
            self.logger.info(f"Unsubscribing from market data for: {symbols}")
            
            for symbol in symbols:
                if symbol in self.subscribed_streams:
                    stream_name = f"{symbol.lower()}@ticker"
                    await self._unsubscribe_from_stream(stream_name)
                
                if symbol in self.market_data_cache:
                    del self.market_data_cache[symbol]
                if symbol in self.market_data_callbacks:
                    del self.market_data_callbacks[symbol]
            
            self.logger.info(f"Unsubscribed from market data for {len(symbols)} symbols")
            return True
            
        except Exception as e:
            self.logger.error(f"Error unsubscribing from market data: {e}")
            return False
    
    def is_connected(self) -> bool:
        """
        Check if connected to Binance
        
        Returns:
            bool: True if connected
        """
        return self.connection_info.is_connected()
    
    def get_connection_status(self) -> BinanceConnectionInfo:
        """
        Get current connection status
        
        Returns:
            BinanceConnectionInfo: Connection status information
        """
        return self.connection_info
    
    # Private helper methods
    
    def _create_binance_order(self, order_request: OrderRequest) -> Dict[str, Any]:
        """Create Binance order from order request"""
        # Basic order structure
        binance_order = {
            "symbol": order_request.symbol.upper(),
            "side": order_request.side.value.upper(),
            "type": self._map_order_type(order_request.order_type),
            "quantity": str(order_request.quantity)
        }
        
        # Add price information if needed
        if order_request.limit_price:
            binance_order["price"] = str(order_request.limit_price)
        
        # Add time in force
        binance_order["timeInForce"] = self.config.default_time_in_force.value
        
        # Add timestamp
        binance_order["timestamp"] = int(time.time() * 1000)
        
        return binance_order
    
    def _map_order_type(self, order_type: OrderType) -> str:
        """Map our order type to Binance order type"""
        mapping = {
            OrderType.MARKET: BinanceOrderType.MARKET.value,
            OrderType.LIMIT: BinanceOrderType.LIMIT.value,
            OrderType.STOP: BinanceOrderType.STOP_LOSS.value,
            OrderType.STOP_LIMIT: BinanceOrderType.STOP_LOSS_LIMIT.value
        }
        return mapping.get(order_type, BinanceOrderType.MARKET.value)
    
    def _convert_binance_account_info(self, binance_account: Dict) -> AccountInfo:
        """Convert Binance account info to our AccountInfo format"""
        # Calculate total balance in USD (simplified)
        total_balance_usd = 0.0
        
        # This is simplified - would need actual USD conversion rates
        for balance in binance_account.get("balances", []):
            asset = balance["asset"]
            free = float(balance["free"])
            locked = float(balance["locked"])
            total = free + locked
            
            # Simple USD estimation (would need proper conversion)
            if asset == "USDT":
                total_balance_usd += total
            elif asset == "BTC":
                # Assume BTC price of $50,000 for estimation
                total_balance_usd += total * 50000
        
        return AccountInfo(
            account_id="BINANCE_SPOT",
            broker="BINANCE",
            currency="USDT",
            cash_balance=0.0,  # Would need to calculate from balances
            buying_power=total_balance_usd,
            total_value=total_balance_usd,
            day_trade_count=0,
            maintenance_margin=0.0,
            equity_with_loan=total_balance_usd,
            last_updated=datetime.now()
        )
    
    async def _start_websocket(self):
        """Start WebSocket connection for real-time data"""
        try:
            if not WEBSOCKETS_AVAILABLE:
                self.logger.warning("WebSockets not available, using polling mode")
                return
            
            # Determine WebSocket URL
            if self.config.use_testnet:
                ws_url = f"{self.config.testnet_stream_url}/ws"
            elif self.config.account_type == BinanceAccountType.FUTURES:
                ws_url = f"{self.config.futures_stream_url}/ws"
            else:
                ws_url = f"{self.config.stream_base_url}/ws"
            
            # Connect to WebSocket
            self.websocket = await websockets.connect(ws_url)
            self.websocket_connected = True
            
            # Start listening to messages
            asyncio.create_task(self._websocket_listener())
            
            self.logger.info("WebSocket connection established")
            
        except Exception as e:
            self.logger.error(f"Failed to start WebSocket: {e}")
            self.websocket_connected = False
    
    async def _websocket_listener(self):
        """Listen to WebSocket messages"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                await self._handle_websocket_message(data)
                
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("WebSocket connection closed")
            self.websocket_connected = False
        except Exception as e:
            self.logger.error(f"WebSocket listener error: {e}")
            self.websocket_connected = False
    
    async def _handle_websocket_message(self, data: Dict[str, Any]):
        """Handle incoming WebSocket message"""
        try:
            if "e" in data:  # Event type
                event_type = data["e"]
                
                if event_type == "24hrTicker":
                    symbol = data["s"]
                    market_data = MarketData(
                        symbol=symbol,
                        bid=float(data["b"]),  # Bid price
                        ask=float(data["a"]),  # Ask price
                        last=float(data["c"]),  # Last price
                        volume=int(data["v"]),  # Volume
                        timestamp=datetime.now()
                    )
                    
                    self.market_data_cache[symbol] = market_data
                    
                    # Notify callbacks
                    if symbol in self.market_data_callbacks:
                        for callback in self.market_data_callbacks[symbol]:
                            try:
                                callback(market_data)
                            except Exception as e:
                                self.logger.error(f"Error in market data callback: {e}")
                
        except Exception as e:
            self.logger.error(f"Error handling WebSocket message: {e}")
    
    async def _subscribe_to_stream(self, stream_name: str):
        """Subscribe to a WebSocket stream"""
        if not self.websocket_connected:
            return
        
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [stream_name],
            "id": int(time.time())
        }
        
        await self.websocket.send(json.dumps(subscribe_msg))
        self.subscribed_streams.append(stream_name)
    
    async def _unsubscribe_from_stream(self, stream_name: str):
        """Unsubscribe from a WebSocket stream"""
        if not self.websocket_connected:
            return
        
        unsubscribe_msg = {
            "method": "UNSUBSCRIBE",
            "params": [stream_name],
            "id": int(time.time())
        }
        
        await self.websocket.send(json.dumps(unsubscribe_msg))
        if stream_name in self.subscribed_streams:
            self.subscribed_streams.remove(stream_name)
    
    async def _get_ticker(self, symbol: str) -> Optional[MarketData]:
        """Get ticker information for a symbol (fallback for polling)"""
        try:
            # This would use the regular HTTP API to get ticker info
            # Simplified for now
            return MarketData(
                symbol=symbol,
                bid=0.0,
                ask=0.0,
                last=0.0,
                volume=0,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            self.logger.error(f"Error getting ticker for {symbol}: {e}")
            return None