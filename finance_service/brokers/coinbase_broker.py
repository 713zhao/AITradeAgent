"""
Coinbase Pro Cryptocurrency Exchange Broker Implementation

This module provides comprehensive integration with Coinbase Pro API for cryptocurrency trading,
supporting spot trading, real-time market data, and portfolio management.

Key Features:
- Coinbase Pro API integration for spot trading
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
class CoinbaseConfig:
    """Coinbase Pro broker configuration"""
    api_key: str
    api_secret: str
    passphrase: str
    sandbox_api_url: str = "https://api-sandbox.coinbase.com"
    production_api_url: str = "https://api.coinbase.com"
    use_sandbox: bool = False
    timeout: float = 10.0


# Coinbase-specific enums and constants
class CoinbaseAccountType(str, Enum):
    """Coinbase account types"""
    SPOT = "spot"
    MARGIN = "margin"


class CoinbaseOrderSide(str, Enum):
    """Coinbase order sides"""
    BUY = "buy"
    SELL = "sell"


class CoinbaseOrderType(str, Enum):
    """Coinbase order types"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class CoinbaseConnectionStatus(str, Enum):
    """Coinbase connection status"""
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"


@dataclass
class CoinbaseConfig:
    """Coinbase configuration settings"""
    api_key: str = ""
    secret_key: str = ""
    passphrase: str = ""
    account_type: CoinbaseAccountType = CoinbaseAccountType.SPOT
    
    # API settings
    base_url: str = "https://api.pro.coinbase.com"
    sandbox_url: str = "https://api-public.sandbox.pro.coinbase.com"
    use_sandbox: bool = True
    
    # WebSocket settings
    ws_url: str = "wss://ws-feed.pro.coinbase.com"
    sandbox_ws_url: str = "wss://ws-feed-public.sandbox.pro.coinbase.com"
    
    # Connection settings
    connection_timeout: int = 30
    request_timeout: int = 10
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # Rate limiting
    requests_per_second: int = 10
    orders_per_second: int = 10
    
    # Product settings
    default_product: str = "BTC-USD"
    
    # Order settings
    default_time_in_force: str = "GTC"  # Good Till Cancel
    
    # Logging
    log_level: str = "INFO"
    log_requests: bool = False
    log_responses: bool = False


@dataclass
class CoinbaseConnectionInfo:
    """Coinbase connection information"""
    status: CoinbaseConnectionStatus = CoinbaseConnectionStatus.DISCONNECTED
    connected_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    reconnect_attempts: int = 0
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset: Optional[datetime] = None
    error_message: Optional[str] = None
    
    def is_connected(self) -> bool:
        return self.status == CoinbaseConnectionStatus.CONNECTED
    
    def is_authenticated(self) -> bool:
        return self.status in [CoinbaseConnectionStatus.CONNECTED, CoinbaseConnectionStatus.RECONNECTING]


class CoinbaseAuthManager:
    """Coinbase Authentication Manager"""
    
    def __init__(self, config: CoinbaseConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.CoinbaseAuthManager")
        
        # Session management
        self.session: Optional[aiohttp.ClientSession] = None
        self.api_key: Optional[str] = None
        self.secret_key: Optional[str] = None
        self.passphrase: Optional[str] = None
        
        # Rate limiting
        self.request_times: List[float] = []
        
    async def authenticate(self) -> bool:
        """
        Authenticate with Coinbase Pro API
        
        Returns:
            bool: True if authentication successful
        """
        try:
            self.logger.info("Authenticating with Coinbase Pro API")
            
            # Check credentials
            if not all([self.config.api_key, self.config.secret_key, self.config.passphrase]):
                self.logger.warning("Incomplete Coinbase Pro API credentials")
                return False
            
            # Create session
            self.session = aiohttp.ClientSession()
            
            # Store credentials
            self.api_key = self.config.api_key
            self.secret_key = self.config.secret_key
            self.passphrase = self.config.passphrase
            
            # Test connection with account info
            account_info = await self.get_accounts()
            if account_info is not None:
                self.logger.info("Successfully authenticated with Coinbase Pro")
                return True
            else:
                self.logger.error("Authentication failed - could not get accounts")
                return False
                
        except Exception as e:
            self.logger.error(f"Coinbase Pro authentication failed: {e}")
            return False
    
    async def get_accounts(self) -> Optional[List[Dict[str, Any]]]:
        """Get account information"""
        try:
            if not self.session:
                await self.authenticate()
            
            # Prepare request
            timestamp = str(time.time())
            method = "GET"
            request_path = "/accounts"
            body = ""
            
            # Create signature
            signature = self._create_signature(timestamp, method, request_path, body)
            
            # Prepare headers
            headers = {
                "CB-ACCESS-KEY": self.api_key,
                "CB-ACCESS-SIGN": signature,
                "CB-ACCESS-TIMESTAMP": timestamp,
                "CB-ACCESS-PASSPHRASE": self.passphrase,
                "Content-Type": "application/json"
            }
            
            # Make request
            base_url = self._get_base_url()
            url = f"{base_url}{request_path}"
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    self.logger.error(f"Coinbase accounts request failed: {response.status}")
                    return None
            
        except Exception as e:
            self.logger.error(f"Error getting Coinbase accounts: {e}")
            return None
    
    def _get_base_url(self) -> str:
        """Get base URL based on sandbox setting"""
        if self.config.use_sandbox:
            return self.config.sandbox_url
        else:
            return self.config.base_url
    
    def _create_signature(self, timestamp: str, method: str, request_path: str, body: str) -> str:
        """Create HMAC SHA256 signature for Coinbase Pro requests"""
        # Coinbase Pro uses a specific signature format
        message = timestamp + method.upper() + request_path + body
        signature = hmac.new(
            base64.b64decode(self.secret_key),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode('utf-8')
    
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
        """Make signed request to Coinbase Pro API"""
        try:
            if not self.session:
                await self.authenticate()
            
            # Check rate limit
            self._check_rate_limit()
            
            # Prepare parameters
            timestamp = str(time.time())
            body = json.dumps(data) if data else ""
            request_path = endpoint
            
            # Create signature
            signature = self._create_signature(timestamp, method, request_path, body)
            
            # Prepare headers
            headers = {
                "CB-ACCESS-KEY": self.api_key,
                "CB-ACCESS-SIGN": signature,
                "CB-ACCESS-TIMESTAMP": timestamp,
                "CB-ACCESS-PASSPHRASE": self.passphrase,
                "Content-Type": "application/json"
            }
            
            # Get base URL
            base_url = self._get_base_url()
            url = f"{base_url}{endpoint}"
            
            # Make request
            async with self.session.request(
                method=method,
                url=url,
                data=body if method in ["POST", "PUT", "DELETE"] else None,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.config.request_timeout)
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    self.logger.error(f"Coinbase Pro API error: {response.status} - {error_text}")
                    return None
            
        except Exception as e:
            self.logger.error(f"Coinbase Pro API request failed: {e}")
            return None
    
    async def close(self):
        """Close session"""
        if self.session:
            await self.session.close()


class CoinbaseBroker(BaseBroker):
    """
    Coinbase Pro Cryptocurrency Exchange Broker
    
    Provides comprehensive integration with Coinbase Pro API for cryptocurrency trading.
    """
    
    def __init__(self, config: CoinbaseConfig, event_manager: EventManager):
        super().__init__(event_manager)
        
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.CoinbaseBroker")
        
        # Authentication
        self.auth_manager = CoinbaseAuthManager(config)
        self.connection_info = CoinbaseConnectionInfo()
        
        # Market data tracking
        self.subscribed_channels: List[str] = []
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
        
        self.logger.info("Coinbase Broker initialized")
    
    async def connect(self) -> bool:
        """
        Connect to Coinbase Pro
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self.logger.info("Connecting to Coinbase Pro")
            
            self.connection_info.status = CoinbaseConnectionStatus.CONNECTING
            
            # Authenticate with Coinbase Pro
            if await self.auth_manager.authenticate():
                self.connection_info.status = CoinbaseConnectionStatus.CONNECTED
                self.connection_info.connected_at = datetime.now()
                
                # Start WebSocket connection if available
                if WEBSOCKETS_AVAILABLE:
                    await self._start_websocket()
                
                # Test connection with accounts
                accounts = await self.auth_manager.get_accounts()
                if accounts is not None:
                    self.logger.info("Successfully connected to Coinbase Pro")
                    return True
                else:
                    self.logger.warning("Connected but accounts unavailable")
                    return True
            else:
                self.connection_info.status = CoinbaseConnectionStatus.ERROR
                self.logger.error("Failed to authenticate with Coinbase Pro")
                return False
                
        except Exception as e:
            self.logger.error(f"Error connecting to Coinbase Pro: {e}")
            self.connection_info.status = CoinbaseConnectionStatus.ERROR
            self.connection_info.error_message = str(e)
            return False
    
    async def disconnect(self) -> bool:
        """
        Disconnect from Coinbase Pro
        
        Returns:
            bool: True if disconnection successful
        """
        try:
            self.logger.info("Disconnecting from Coinbase Pro")
            
            # Close WebSocket connection
            if self.websocket:
                await self.websocket.close()
                self.websocket_connected = False
            
            # Close auth manager session
            await self.auth_manager.close()
            
            self.connection_info.status = CoinbaseConnectionStatus.DISCONNECTED
            self.connection_info.connected_at = None
            
            self.logger.info("Disconnected from Coinbase Pro")
            return True
            
        except Exception as e:
            self.logger.error(f"Error disconnecting from Coinbase Pro: {e}")
            return False
    
    async def place_order(self, order_request: OrderRequest) -> OrderResult:
        """
        Place an order through Coinbase Pro
        
        Args:
            order_request: Order request with symbol, side, quantity, type, etc.
            
        Returns:
            OrderResult: Order placement result with ID and status
        """
        try:
            self.logger.info(f"Placing Coinbase order: {order_request.symbol} {order_request.side} {order_request.quantity}")
            
            # Validate order
            if not self.is_connected():
                return OrderResult(
                    success=False,
                    error_message="Not connected to Coinbase Pro"
                )
            
            # Convert to Coinbase order format
            coinbase_order = self._create_coinbase_order(order_request)
            
            # Place order
            result = await self.auth_manager.make_signed_request(
                method="POST",
                endpoint="/orders",
                data=coinbase_order
            )
            
            if result:
                # Extract order ID from response
                order_id = result.get("id")
                
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
                        "broker": "COINBASE",
                        "order": result
                    }
                )
                
                # Publish event
                self.event_manager.publish(Event(
                    type=EventType.ORDER_SUBMITTED,
                    data={
                        "broker": "COINBASE",
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
            self.logger.error(f"Error placing Coinbase order: {e}")
            return OrderResult(
                success=False,
                error_message=f"Order placement failed: {e}"
            )
    
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            bool: True if cancellation successful
        """
        try:
            self.logger.info(f"Cancelling Coinbase order: {order_id}")
            
            if not self.is_connected():
                return False
            
            # Cancel order
            result = await self.auth_manager.make_signed_request(
                method="DELETE",
                endpoint=f"/orders/{order_id}"
            )
            
            if result:
                # Update order status
                if order_id in self.pending_orders:
                    self.pending_orders[order_id].status = OrderStatus.CANCELLED
                
                # Publish event
                self.event_manager.publish(Event(
                    type=EventType.ORDER_CANCELLED,
                    data={
                        "broker": "COINBASE",
                        "order_id": order_id
                    }
                ))
                
                self.logger.info(f"Order cancelled successfully: {order_id}")
                return True
            else:
                self.logger.error(f"Failed to cancel order {order_id}")
                return False
            
        except Exception as e:
            self.logger.error(f"Error cancelling Coinbase order {order_id}: {e}")
            return False
    
    async def get_positions(self) -> List[Position]:
        """
        Get current positions from Coinbase Pro
        
        Returns:
            List[Position]: List of current positions
        """
        try:
            if not self.is_connected():
                return []
            
            # Get accounts from Coinbase Pro
            accounts = await self.auth_manager.get_accounts()
            
            positions = []
            
            if accounts:
                for account in accounts:
                    currency = account["currency"]
                    balance = float(account["balance"])
                    
                    # Only include positions with non-zero balance
                    if balance > 0:
                        position = Position(
                            symbol=currency,
                            quantity=balance,
                            avg_price=0.0,  # Would need trade history
                            market_value=0.0,  # Would need current price
                            unrealized_pnl=0.0,
                            realized_pnl=0.0,
                            asset_type=AssetType.CRYPTO,
                            broker="COINBASE",
                            last_updated=datetime.now()
                        )
                        positions.append(position)
            
            # Update cache
            self.positions_cache.clear()
            for position in positions:
                self.positions_cache[position.symbol] = position
            
            self.logger.info(f"Retrieved {len(positions)} positions from Coinbase Pro")
            return positions
            
        except Exception as e:
            self.logger.error(f"Error getting Coinbase positions: {e}")
            return []
    
    async def get_account_info(self) -> Optional[AccountInfo]:
        """
        Get account information from Coinbase Pro
        
        Returns:
            AccountInfo: Account information or None if unavailable
        """
        try:
            if not self.is_connected():
                return None
            
            # Get accounts from Coinbase Pro
            accounts = await self.auth_manager.get_accounts()
            
            if accounts:
                account = self._convert_coinbase_account_info(accounts)
                self.account_info_cache = account
                return account
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting Coinbase account info: {e}")
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
                await self._subscribe_to_channels(symbols)
            else:
                # Fallback to polling
                for symbol in symbols:
                    ticker = await self._get_ticker(symbol)
                    if ticker:
                        self.market_data_cache[symbol] = ticker
                    
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
            
            if WEBSOCKETS_AVAILABLE and self.websocket_connected:
                # Unsubscribe via WebSocket
                await self._unsubscribe_from_channels(symbols)
            
            for symbol in symbols:
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
        Check if connected to Coinbase Pro
        
        Returns:
            bool: True if connected
        """
        return self.connection_info.is_connected()
    
    def get_connection_status(self) -> CoinbaseConnectionInfo:
        """
        Get current connection status
        
        Returns:
            CoinbaseConnectionInfo: Connection status information
        """
        return self.connection_info
    
    # Private helper methods
    
    def _create_coinbase_order(self, order_request: OrderRequest) -> Dict[str, Any]:
        """Create Coinbase order from order request"""
        # Basic order structure
        coinbase_order = {
            "product_id": order_request.symbol,
            "side": order_request.side.value,
            "type": self._map_order_type(order_request.order_type)
        }
        
        # Add quantity or funds based on order type
        if order_request.order_type == OrderType.MARKET:
            if order_request.side == OrderSide.BUY:
                coinbase_order["funds"] = str(order_request.quantity)  # Market buy uses funds
            else:
                coinbase_order["size"] = str(order_request.quantity)  # Market sell uses size
        else:
            coinbase_order["size"] = str(order_request.quantity)
            if order_request.limit_price:
                coinbase_order["price"] = str(order_request.limit_price)
        
        # Add time in force
        coinbase_order["time_in_force"] = self.config.default_time_in_force
        
        return coinbase_order
    
    def _map_order_type(self, order_type: OrderType) -> str:
        """Map our order type to Coinbase order type"""
        mapping = {
            OrderType.MARKET: CoinbaseOrderType.MARKET.value,
            OrderType.LIMIT: CoinbaseOrderType.LIMIT.value,
            OrderType.STOP: CoinbaseOrderType.STOP.value,
            OrderType.STOP_LIMIT: CoinbaseOrderType.STOP_LIMIT.value
        }
        return mapping.get(order_type, CoinbaseOrderType.MARKET.value)
    
    def _convert_coinbase_account_info(self, accounts: List[Dict]) -> AccountInfo:
        """Convert Coinbase account info to our AccountInfo format"""
        # Calculate total balance in USD (simplified)
        total_balance_usd = 0.0
        total_crypto_value = 0.0
        
        # This is simplified - would need actual USD conversion rates
        for account in accounts:
            currency = account["currency"]
            balance = float(account["balance"])
            
            if balance > 0:
                if currency == "USD":
                    total_balance_usd += balance
                else:
                    # Simple crypto valuation (would need real prices)
                    if currency == "BTC":
                        total_crypto_value += balance * 50000  # Assume $50k per BTC
                    elif currency == "ETH":
                        total_crypto_value += balance * 3000   # Assume $3k per ETH
        
        total_value = total_balance_usd + total_crypto_value
        
        return AccountInfo(
            account_id="COINBASE_SPOT",
            broker="COINBASE",
            currency="USD",
            cash_balance=total_balance_usd,
            buying_power=total_value,
            total_value=total_value,
            day_trade_count=0,
            maintenance_margin=0.0,
            equity_with_loan=total_value,
            last_updated=datetime.now()
        )
    
    async def _start_websocket(self):
        """Start WebSocket connection for real-time data"""
        try:
            if not WEBSOCKETS_AVAILABLE:
                self.logger.warning("WebSockets not available, using polling mode")
                return
            
            # Determine WebSocket URL
            if self.config.use_sandbox:
                ws_url = self.config.sandbox_ws_url
            else:
                ws_url = self.config.ws_url
            
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
            if "type" in data:
                message_type = data["type"]
                
                if message_type == "ticker":
                    symbol = data["product_id"]
                    market_data = MarketData(
                        symbol=symbol,
                        bid=float(data["bid"]),
                        ask=float(data["ask"]),
                        last=float(data["price"]),
                        volume=int(float(data["volume_24h"])),
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
                
                elif message_type == "subscriptions":
                    self.logger.debug("WebSocket subscriptions confirmed")
                
        except Exception as e:
            self.logger.error(f"Error handling WebSocket message: {e}")
    
    async def _subscribe_to_channels(self, symbols: List[str]):
        """Subscribe to WebSocket channels"""
        if not self.websocket_connected:
            return
        
        subscribe_msg = {
            "type": "subscribe",
            "product_ids": symbols,
            "channels": ["ticker"]
        }
        
        await self.websocket.send(json.dumps(subscribe_msg))
        self.subscribed_channels.extend(symbols)
    
    async def _unsubscribe_from_channels(self, symbols: List[str]):
        """Unsubscribe from WebSocket channels"""
        if not self.websocket_connected:
            return
        
        unsubscribe_msg = {
            "type": "unsubscribe",
            "product_ids": symbols,
            "channels": ["ticker"]
        }
        
        await self.websocket.send(json.dumps(unsubscribe_msg))
        
        for symbol in symbols:
            if symbol in self.subscribed_channels:
                self.subscribed_channels.remove(symbol)
    
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