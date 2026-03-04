"""
Alpaca WebSocket Stream

Real-time market data streaming for Alpaca via WebSocket.
Handles WebSocket connections, data parsing, and event publishing.

Features:
- Alpaca WebSocket API integration
- Real-time tick data streaming
- WebSocket connection management
- Error handling and reconnection
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

from ..tick_data import TickData, TickEvent, TickEventType, OrderBookLevel, PriceLevelUpdate


@dataclass
class AlpacaStreamConfig:
    """Configuration for Alpaca WebSocket stream"""
    api_key: str
    secret_key: str
    paper: bool = True
    feed: str = "iex"  # "iex", "sip", "otc"
    rate_limit: int = 1000  # requests per minute
    reconnect_attempts: int = 5
    heartbeat_interval: int = 30
    connection_timeout: int = 10
    subscribe_timeout: int = 5
    paper_url: str = "wss://stream.data.alpaca.markets/v2/iex"
    live_url: str = "wss://stream.data.alpaca.markets/v2/iex"


class AlpacaWebSocketStream:
    """
    WebSocket stream for Alpaca market data.
    
    Connects to Alpaca WebSocket API and streams real-time
    market data and trades.
    """
    
    def __init__(self, config: Dict[str, Any], event_manager):
        self.config = config
        self.event_manager = event_manager
        
        # Stream configuration
        alpaca_config = config.get('alpaca', {})
        self.alpaca_config = AlpacaStreamConfig(
            api_key=alpaca_config.get('api_key', ''),
            secret_key=alpaca_config.get('secret_key', ''),
            paper=alpaca_config.get('paper', True),
            feed=alpaca_config.get('feed', 'iex'),
            rate_limit=alpaca_config.get('rate_limit', 1000),
            reconnect_attempts=alpaca_config.get('reconnect_attempts', 5),
            heartbeat_interval=alpaca_config.get('heartbeat_interval', 30)
        )
        
        # Connection state
        self.websocket = None
        self.connected = False
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
        self.rate_limit_remaining = self.alpaca_config.rate_limit
        
        # Logging
        self.logger = logging.getLogger(__name__)
        
    async def connect(self):
        """Connect to Alpaca WebSocket API"""
        try:
            self.logger.info("Connecting to Alpaca WebSocket")
            
            # Determine WebSocket URL
            if self.alpaca_config.paper:
                ws_url = f"wss://stream.data.alpaca.markets/v2/{self.alpaca_config.feed}"
            else:
                ws_url = f"wss://stream.data.alpaca.markets/v2/{self.alpaca_config.feed}"
            
            # Connect to WebSocket
            self.websocket = await asyncio.wait_for(
                websockets.connect(
                    ws_url,
                    extra_headers={
                        'APCA-API-KEY-ID': self.alpaca_config.api_key,
                        'APCA-API-SECRET-KEY': self.alpaca_config.secret_key
                    },
                    ping_interval=self.alpaca_config.heartbeat_interval,
                    ping_timeout=10
                ),
                timeout=self.alpaca_config.connection_timeout
            )
            
            self.connected = True
            self.connection_start_time = datetime.now(timezone.utc)
            
            # Start background tasks
            asyncio.create_task(self._message_handler())
            asyncio.create_task(self._heartbeat_task())
            asyncio.create_task(self._rate_limit_monitor())
            
            self.logger.info("Connected to Alpaca WebSocket")
            await self._notify_connection_status("CONNECTED")
            
        except asyncio.TimeoutError:
            self.logger.error("Connection timeout to Alpaca")
            raise ConnectionError("Connection timeout")
        except Exception as e:
            self.logger.error(f"Failed to connect to Alpaca: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from Alpaca WebSocket"""
        self.connected = False
        
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                self.logger.error(f"Error closing WebSocket: {e}")
            finally:
                self.websocket = None
                
        await self._notify_connection_status("DISCONNECTED")
        self.logger.info("Disconnected from Alpaca")
    
    async def wait_connected(self):
        """Wait for connection to be established"""
        while not self.connected:
            await asyncio.sleep(0.1)
    
    async def subscribe_symbols(self, symbols: List[str]):
        """Subscribe to real-time data for symbols"""
        if not self.connected:
            raise ConnectionError("Not connected to Alpaca")
        
        new_symbols = set(symbols) - self.subscribed_symbols
        if not new_symbols:
            return
            
        self.logger.info(f"Subscribing to {len(new_symbols)} new symbols: {new_symbols}")
        
        try:
            # Create subscription request
            subscription_request = {
                "action": "subscribe",
                "quotes": list(new_symbols),
                "trades": list(new_symbols),
                "bars": list(new_symbols)
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
                "action": "unsubscribe",
                "quotes": list(symbols_to_remove),
                "trades": list(symbols_to_remove),
                "bars": list(symbols_to_remove)
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
            self.logger.warning("Alpaca WebSocket connection closed")
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
            if isinstance(data, list):
                # Multiple messages
                for item in data:
                    await self._handle_single_message(item)
            else:
                # Single message
                await self._handle_single_message(data)
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON message: {e}")
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            await self._handle_error(e)
    
    async def _handle_single_message(self, data: Dict[str, Any]):
        """Handle a single message from Alpaca"""
        try:
            msg_type = data.get('T', '')
            
            if msg_type == 'success':
                await self._handle_success_message(data)
            elif msg_type == 'error':
                await self._handle_error_message(data)
            elif msg_type == 'subscription':
                await self._handle_subscription_message(data)
            elif msg_type == 'q':  # Quote
                await self._process_quote_data(data)
            elif msg_type == 't':  # Trade
                await self._process_trade_data(data)
            elif msg_type == 'b':  # Bar
                await self._process_bar_data(data)
            elif msg_type == 'heartbeat':
                self.last_heartbeat = datetime.now(timezone.utc)
                
        except Exception as e:
            self.logger.error(f"Error handling single message: {e}")
    
    async def _handle_success_message(self, data: Dict[str, Any]):
        """Handle success message"""
        msg = data.get('msg', '')
        self.logger.info(f"Alpaca success: {msg}")
    
    async def _handle_error_message(self, data: Dict[str, Any]):
        """Handle error message from Alpaca"""
        error_message = data.get('msg', 'Unknown error')
        
        self.logger.error(f"Alpaca error: {error_message}")
        
        error_event = TickEvent(
            event_type=TickEventType.ERROR,
            symbol="",
            broker='alpaca',
            timestamp=datetime.now(timezone.utc),
            data={'error': error_message, 'raw_data': data}
        )
        
        await self._notify_tick_handlers(error_event)
    
    async def _handle_subscription_message(self, data: Dict[str, Any]):
        """Handle subscription confirmation"""
        quotes = data.get('quotes', [])
        trades = data.get('trades', [])
        bars = data.get('bars', [])
        
        self.logger.info(f"Subscription confirmed - Quotes: {quotes}, Trades: {trades}, Bars: {bars}")
    
    async def _process_quote_data(self, data: Dict[str, Any]):
        """Process quote data from Alpaca"""
        try:
            symbol = data.get('S', '')
            bid = float(data.get('bp', 0))  # Bid price
            ask = float(data.get('ap', 0))  # Ask price
            bid_size = int(data.get('bs', 0))  # Bid size
            ask_size = int(data.get('as', 0))  # Ask size
            timestamp = datetime.fromtimestamp(data.get('t', 0) / 1000000000, tz=timezone.utc)
            
            # Create TickData object
            tick_data = TickData(
                symbol=symbol,
                timestamp=timestamp,
                bid=bid,
                ask=ask,
                bid_size=bid_size,
                ask_size=ask_size,
                last_price=0,  # Not provided in quote
                last_size=0,   # Not provided in quote
                volume=0,      # Not provided in quote
                broker='alpaca',
                exchange='ALPACA',
                sequence_number=data.get('q', None)  # Quote sequence
            )
            
            # Notify handlers
            await self._notify_tick_handlers(tick_data)
            
        except Exception as e:
            self.logger.error(f"Error processing quote data: {e}")
    
    async def _process_trade_data(self, data: Dict[str, Any]):
        """Process trade data from Alpaca"""
        try:
            symbol = data.get('S', '')
            price = float(data.get('p', 0))  # Trade price
            size = int(data.get('s', 0))     # Trade size
            timestamp = datetime.fromtimestamp(data.get('t', 0) / 1000000000, tz=timezone.utc)
            
            # Create trade event
            trade_event = TickEvent(
                event_type=TickEventType.TRADE,
                symbol=symbol,
                broker='alpaca',
                timestamp=timestamp,
                data={
                    'price': price,
                    'size': size,
                    'timestamp': timestamp.isoformat(),
                    'exchange': data.get('x', ''),
                    'conditions': data.get('c', [])
                }
            )
            
            await self._notify_tick_handlers(trade_event)
            
        except Exception as e:
            self.logger.error(f"Error processing trade data: {e}")
    
    async def _process_bar_data(self, data: Dict[str, Any]):
        """Process bar data from Alpaca"""
        try:
            symbol = data.get('S', '')
            open_price = float(data.get('o', 0))
            high_price = float(data.get('h', 0))
            low_price = float(data.get('l', 0))
            close_price = float(data.get('c', 0))
            volume = int(data.get('v', 0))
            timestamp = datetime.fromtimestamp(data.get('t', 0) / 1000000000, tz=timezone.utc)
            
            # Create TickData object with OHLC data
            tick_data = TickData(
                symbol=symbol,
                timestamp=timestamp,
                bid=close_price,  # Use close as both bid/ask for bars
                ask=close_price,
                bid_size=0,
                ask_size=0,
                last_price=close_price,
                last_size=0,
                volume=volume,
                broker='alpaca',
                exchange='ALPACA',
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                sequence_number=data.get('n', None)
            )
            
            # Notify handlers
            await self._notify_tick_handlers(tick_data)
            
        except Exception as e:
            self.logger.error(f"Error processing bar data: {e}")
    
    async def _heartbeat_task(self):
        """Send periodic heartbeat to maintain connection"""
        while self.connected:
            try:
                if self.websocket:
                    # Alpaca WebSocket handles heartbeats automatically
                    # Just maintain connection alive
                    pass
                    
                await asyncio.sleep(self.alpaca_config.heartbeat_interval)
                
            except Exception as e:
                self.logger.error(f"Error in heartbeat task: {e}")
                break
    
    async def _rate_limit_monitor(self):
        """Monitor and update rate limit status"""
        while self.connected:
            try:
                # Reset rate limit every minute
                await asyncio.sleep(60)
                self.rate_limit_remaining = self.alpaca_config.rate_limit
                
            except Exception as e:
                self.logger.error(f"Error in rate limit monitor: {e}")
                break
    
    async def _notify_connection_status(self, status: str):
        """Notify connection status change"""
        for handler in self.connection_handlers:
            try:
                await handler('alpaca', status)
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
            'symbols': list(self.subscribed_symbols),
            'feed': self.alpaca_config.feed,
            'paper': self.alpaca_config.paper
        }
    
    def is_connected(self) -> bool:
        """Check if stream is connected"""
        return self.connected
    
    @property
    def broker_name(self) -> str:
        """Get broker name"""
        return 'ALPACA'
    
    def parse_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a raw message from Alpaca stream into normalized format"""
        return {
            'symbol': message.get('S', ''),
            'bid': float(message.get('bp', 0.0)),
            'ask': float(message.get('ap', 0.0)),
            'bid_size': int(message.get('bs', 0)),
            'ask_size': int(message.get('as', 0)),
            'last_price': float(message.get('c', 0.0)),
            'last_size': int(message.get('s', 0)),
            'volume': int(message.get('v', 0)),
            'timestamp': message.get('t')
        }
    
    async def close(self):
        """Close the WebSocket connection"""
        await self.disconnect()