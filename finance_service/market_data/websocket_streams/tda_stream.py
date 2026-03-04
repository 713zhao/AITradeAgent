"""
TD Ameritrade WebSocket Stream

Real-time market data streaming for TD Ameritrade via API WebSocket.
Handles WebSocket connections, data parsing, and event publishing.

Features:
- TD Ameritrade API WebSocket integration
- Real-time tick data streaming
- OAuth 2.0 authentication
- Rate limiting and error handling
- Performance monitoring
"""

import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
import websockets
from websockets.exceptions import ConnectionClosed
import aiohttp

from ..tick_data import TickData, TickEvent, TickEventType


@dataclass
class TDAStreamConfig:
    """Configuration for TD Ameritrade WebSocket stream"""
    api_key: str
    account_id: str
    rate_limit: int = 1000  # requests per minute
    reconnect_attempts: int = 5
    heartbeat_interval: int = 30
    connection_timeout: int = 10
    subscribe_timeout: int = 5
    base_url: str = "https://api.tdameritrade.com/v1"


class TDAWebSocketStream:
    """
    WebSocket stream for TD Ameritrade market data.
    
    Connects to TD Ameritrade API and streams real-time
    market data and quotes.
    """
    
    def __init__(self, config: Dict[str, Any], event_manager):
        self.config = config
        self.event_manager = event_manager
        
        # Stream configuration
        tda_config = config.get('tda', {})
        self.tda_config = TDAStreamConfig(
            api_key=tda_config.get('api_key', ''),
            account_id=tda_config.get('account_id', ''),
            rate_limit=tda_config.get('rate_limit', 1000),
            reconnect_attempts=tda_config.get('reconnect_attempts', 5),
            heartbeat_interval=tda_config.get('heartbeat_interval', 30)
        )
        
        # Connection state
        self.websocket = None
        self.connected = False
        self.session = None
        self.auth_token = None
        self.subscribed_symbols: set[str] = set()
        
        # Event handlers
        self.tick_handlers: List[Callable[[TickData], None]] = []
        self.connection_handlers: List[Callable[[str, str], None]] = []
        self.error_handlers: List[Callable[[Exception], None]] = []
        
        # Performance metrics
        self.messages_received = 0
        self.bytes_received = 0
        self.last_heartbeat = None
        self.connection_start_time = None
        self.rate_limit_remaining = self.tda_config.rate_limit
        
        # Logging
        self.logger = logging.getLogger(__name__)
        
    async def connect(self):
        """Connect to TD Ameritrade API and establish WebSocket"""
        try:
            self.logger.info("Connecting to TD Ameritrade API")
            
            # Create HTTP session
            self.session = aiohttp.ClientSession()
            
            # Authenticate and get access token
            await self._authenticate()
            
            # Get WebSocket URL
            ws_url = await self._get_websocket_url()
            
            # Connect to WebSocket
            headers = {
                'Authorization': f'Bearer {self.auth_token}',
                'Content-Type': 'application/json'
            }
            
            self.websocket = await asyncio.wait_for(
                websockets.connect(
                    ws_url,
                    extra_headers=headers,
                    ping_interval=self.tda_config.heartbeat_interval,
                    ping_timeout=10
                ),
                timeout=self.tda_config.connection_timeout
            )
            
            self.connected = True
            self.connection_start_time = datetime.now(timezone.utc)
            
            # Start background tasks
            asyncio.create_task(self._message_handler())
            asyncio.create_task(self._heartbeat_task())
            asyncio.create_task(self._rate_limit_monitor())
            
            self.logger.info("Connected to TD Ameritrade WebSocket")
            await self._notify_connection_status("CONNECTED")
            
        except asyncio.TimeoutError:
            self.logger.error("Connection timeout to TD Ameritrade")
            raise ConnectionError("Connection timeout")
        except Exception as e:
            self.logger.error(f"Failed to connect to TD Ameritrade: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from TD Ameritrade API"""
        self.connected = False
        
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                self.logger.error(f"Error closing WebSocket: {e}")
            finally:
                self.websocket = None
                
        if self.session:
            try:
                await self.session.close()
            except Exception as e:
                self.logger.error(f"Error closing session: {e}")
            finally:
                self.session = None
                
        await self._notify_connection_status("DISCONNECTED")
        self.logger.info("Disconnected from TD Ameritrade")
    
    async def wait_connected(self):
        """Wait for connection to be established"""
        while not self.connected:
            await asyncio.sleep(0.1)
    
    async def _authenticate(self):
        """Authenticate with TD Ameritrade API"""
        try:
            auth_url = f"{self.tda_config.base_url}/oauth2/accesstoken"
            
            auth_data = {
                'grant_type': 'client_credentials',
                'access_type': 'online'
            }
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': f'Basic {self._get_basic_auth()}'
            }
            
            async with self.session.post(auth_url, data=auth_data, headers=headers) as response:
                if response.status == 200:
                    auth_response = await response.json()
                    self.auth_token = auth_response.get('access_token')
                    self.logger.info("Successfully authenticated with TD Ameritrade")
                else:
                    error_text = await response.text()
                    raise Exception(f"Authentication failed: {error_text}")
                    
        except Exception as e:
            self.logger.error(f"Authentication error: {e}")
            raise
    
    async def _get_websocket_url(self) -> str:
        """Get WebSocket URL from TD Ameritrade API"""
        try:
            ws_url = f"{self.tda_config.base_url}/streamer"
            
            async with self.session.get(ws_url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('streamer_url', 'wss://streamer.tdameritrade.com/ws')
                else:
                    # Return default URL if API fails
                    return 'wss://streamer.tdameritrade.com/ws'
                    
        except Exception as e:
            self.logger.warning(f"Could not get WebSocket URL from API: {e}")
            return 'wss://streamer.tdameritrade.com/ws'
    
    async def subscribe_symbols(self, symbols: List[str]):
        """Subscribe to real-time data for symbols"""
        if not self.connected:
            raise ConnectionError("Not connected to TD Ameritrade")
        
        new_symbols = set(symbols) - self.subscribed_symbols
        if not new_symbols:
            return
            
        self.logger.info(f"Subscribing to {len(new_symbols)} new symbols: {new_symbols}")
        
        try:
            # Create subscription request
            subscription_request = {
                'service': 'QUOTE',
                'command': 'SUBS',
                'account': self.tda_config.account_id,
                'source': 'TD',
                'parameters': {
                    'symbols': list(new_symbols)
                }
            }
            
            await self.websocket.send(json.dumps(subscription_request))
            self.subscribed_symbols.update(new_symbols)
            
        except Exception as e:
            self.logger.error(f"Error subscribing to symbols: {e}")
            raise
    
    async def unsubscribe_symbols(self, symbols: List[str]):
        """Unsubscribe from real-time data for symbols"""
        if not self.connected:
            return
            
        symbols_to_remove = set(symbols) & self.subscribed_symbols
        if not symbols_to_remove:
            return
            
        self.logger.info(f"Unsubscribing from {len(symbols_to_remove)} symbols: {symbols_to_remove}")
        
        try:
            # Create unsubscription request
            unsubscription_request = {
                'service': 'QUOTE',
                'command': 'UNSUBS',
                'account': self.tda_config.account_id,
                'source': 'TD',
                'parameters': {
                    'symbols': list(symbols_to_remove)
                }
            }
            
            await self.websocket.send(json.dumps(unsubscription_request))
            self.subscribed_symbols -= symbols_to_remove
            
        except Exception as e:
            self.logger.error(f"Error unsubscribing from symbols: {e}")
    
    async def _message_handler(self):
        """Handle incoming WebSocket messages"""
        try:
            async for message in self.websocket:
                await self._process_message(message)
                
        except ConnectionClosed:
            self.logger.warning("TD Ameritrade WebSocket connection closed")
            self.connected = False
            await self._notify_connection_status("DISCONNECTED")
        except Exception as e:
            self.logger.error(f"Error in message handler: {e}")
            self.connected = False
            await self._notify_connection_status("ERROR")
    
    async def _process_message(self, message: str):
        """Process incoming WebSocket message"""
        try:
            self.messages_received += 1
            self.bytes_received += len(message)
            
            # Parse JSON message
            data = json.loads(message)
            
            # Handle different message types
            if 'service' in data:
                await self._handle_service_message(data)
            elif 'response' in data:
                await self._handle_response_message(data)
            elif 'data' in data:
                await self._handle_data_message(data)
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON message: {e}")
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            await self._handle_error(e)
    
    async def _handle_service_message(self, data: Dict[str, Any]):
        """Handle service-level message"""
        service = data.get('service', '')
        if service == 'QUOTE':
            await self._handle_quote_data(data)
    
    async def _handle_quote_data(self, data: Dict[str, Any]):
        """Handle quote data from TD Ameritrade"""
        try:
            # Extract symbol and quote data
            symbol = data.get('symbol', '')
            quote_data = data.get('quote', {})
            
            if not symbol or not quote_data:
                return
            
            # Extract tick data fields
            bid = float(quote_data.get('bidPrice', 0))
            ask = float(quote_data.get('askPrice', 0))
            bid_size = int(quote_data.get('bidSize', 0))
            ask_size = int(quote_data.get('askSize', 0))
            last_price = float(quote_data.get('lastPrice', 0))
            last_size = int(quote_data.get('lastSize', 0))
            volume = int(quote_data.get('totalVolume', 0))
            
            # Create TickData object
            tick_data = TickData(
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                bid=bid,
                ask=ask,
                bid_size=bid_size,
                ask_size=ask_size,
                last_price=last_price,
                last_size=last_size,
                volume=volume,
                broker='td_ameritrade',
                exchange='TDA',
                sequence_number=data.get('sequence', None)
            )
            
            # Update OHLC if available
            if 'openPrice' in quote_data:
                tick_data.open = float(quote_data['openPrice'])
            if 'highPrice' in quote_data:
                tick_data.high = float(quote_data['highPrice'])
            if 'lowPrice' in quote_data:
                tick_data.low = float(quote_data['lowPrice'])
            if 'closePrice' in quote_data:
                tick_data.close = float(quote_data['closePrice'])
            
            # Notify handlers
            await self._notify_tick_handlers(tick_data)
            
        except Exception as e:
            self.logger.error(f"Error processing quote data: {e}")
    
    async def _handle_response_message(self, data: Dict[str, Any]):
        """Handle response message"""
        # Handle subscription responses, errors, etc.
        pass
    
    async def _handle_data_message(self, data: Dict[str, Any]):
        """Handle data message"""
        # Handle other data types
        pass
    
    async def _heartbeat_task(self):
        """Send periodic heartbeat to maintain connection"""
        while self.connected:
            try:
                if self.websocket:
                    heartbeat = {
                        'service': 'QUOTE',
                        'command': 'HEARTBEAT',
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                    await self.websocket.send(json.dumps(heartbeat))
                    
                await asyncio.sleep(self.tda_config.heartbeat_interval)
                
            except Exception as e:
                self.logger.error(f"Error in heartbeat task: {e}")
                break
    
    async def _rate_limit_monitor(self):
        """Monitor and update rate limit status"""
        while self.connected:
            try:
                # Reset rate limit every minute
                await asyncio.sleep(60)
                self.rate_limit_remaining = self.tda_config.rate_limit
                
            except Exception as e:
                self.logger.error(f"Error in rate limit monitor: {e}")
                break
    
    async def _notify_connection_status(self, status: str):
        """Notify connection status change"""
        for handler in self.connection_handlers:
            try:
                await handler('tda', status)
            except Exception as e:
                self.logger.error(f"Error in connection handler: {e}")
    
    async def _notify_tick_handlers(self, data):
        """Notify all tick data handlers"""
        for handler in self.tick_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                self.logger.error(f"Error in tick handler: {e}")
    
    async def _handle_error(self, error: Exception):
        """Handle internal errors"""
        for handler in self.error_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(error)
                else:
                    handler(error)
            except Exception as e:
                self.logger.error(f"Error in error handler: {e}")
    
    def _get_basic_auth(self) -> str:
        """Get basic authentication header"""
        import base64
        credentials = f"{self.tda_config.api_key}:"
        return base64.b64encode(credentials.encode()).decode()
    
    # Public API methods
    
    def add_tick_handler(self, handler: Callable[[TickData], None]):
        """Add handler for tick data"""
        self.tick_handlers.append(handler)
    
    def add_connection_handler(self, handler: Callable[[str, str], None]):
        """Add handler for connection status changes"""
        self.connection_handlers.append(handler)
    
    def add_error_handler(self, handler: Callable[[Exception], None]):
        """Add handler for errors"""
        self.error_handlers.append(handler)
    
    def remove_tick_handler(self, handler: Callable):
        """Remove tick data handler"""
        if handler in self.tick_handlers:
            self.tick_handlers.remove(handler)
    
    def remove_connection_handler(self, handler: Callable):
        """Remove connection status handler"""
        if handler in self.connection_handlers:
            self.connection_handlers.remove(handler)
    
    def remove_error_handler(self, handler: Callable):
        """Remove error handler"""
        if handler in self.error_handlers:
            self.error_handlers.remove(handler)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get stream performance metrics"""
        uptime = 0
        if self.connection_start_time:
            uptime = (datetime.now(timezone.utc) - self.connection_start_time).total_seconds()
        
        return {
            'connected': self.connected,
            'messages_received': self.messages_received,
            'bytes_received': self.bytes_received,
            'subscribed_symbols': len(self.subscribed_symbols),
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            'connection_uptime_seconds': uptime,
            'rate_limit_remaining': self.rate_limit_remaining,
            'symbols': list(self.subscribed_symbols)
        }
    
    def is_connected(self) -> bool:
        """Check if stream is connected"""
        return self.connected
    
    @property
    def broker_name(self) -> str:
        """Get broker name"""
        return 'TDA'
    
    def parse_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a raw message from TDA stream into normalized format"""
        return {
            'symbol': message.get('symbol', ''),
            'bid': message.get('bid', 0.0),
            'ask': message.get('ask', 0.0),
            'bid_size': message.get('bidSize', 0),
            'ask_size': message.get('askSize', 0),
            'last_price': message.get('last', 0.0),
            'last_size': message.get('lastSize', 0),
            'volume': message.get('volume', 0),
            'timestamp': message.get('timestamp')
        }
    
    async def close(self):
        """Close the WebSocket connection"""
        await self.disconnect()