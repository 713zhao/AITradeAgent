"""
Binance WebSocket Stream

Real-time market data streaming for Binance cryptocurrency exchange.
Handles WebSocket connections, data parsing, and event publishing.

Features:
- Binance WebSocket API integration
- Real-time tick data streaming
- Order book depth data
- Cryptocurrency market data
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
class BinanceStreamConfig:
    """Configuration for Binance WebSocket stream"""
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    base_url: str = "https://api.binance.com"
    stream_url: str = "wss://stream.binance.com:9443"
    reconnect_attempts: int = 5
    heartbeat_interval: int = 30
    max_streams: int = 5  # Binance limits concurrent streams
    connection_timeout: int = 10


class BinanceWebSocketStream:
    """
    WebSocket stream for Binance market data.
    
    Connects to Binance WebSocket API and streams real-time
    cryptocurrency market data and order book updates.
    """
    
    def __init__(self, config: Dict[str, Any], event_manager):
        self.config = config
        self.event_manager = event_manager
        
        # Stream configuration
        binance_config = config.get('binance', {})
        self.binance_config = BinanceStreamConfig(
            api_key=binance_config.get('api_key'),
            api_secret=binance_config.get('api_secret'),
            base_url=binance_config.get('base_url', 'https://api.binance.com'),
            stream_url=binance_config.get('stream_url', 'wss://stream.binance.com:9443'),
            reconnect_attempts=binance_config.get('reconnect_attempts', 5),
            heartbeat_interval=binance_config.get('heartbeat_interval', 30)
        )
        
        # Connection state
        self.websockets: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.connected = False
        self.subscribed_streams: Dict[str, set[str]] = {}  # stream_type -> symbols
        
        # Event handlers
        self.tick_handlers: List[Callable[[TickData], None]] = []
        self.connection_handlers: List[Callable[[str, str], None]] = []
        self.error_handlers: List[Callable[[Exception], None]] = []
        
        # Performance metrics
        self.messages_received = 0
        self.bytes_received = 0
        self.last_heartbeat = None
        self.connection_start_time = None
        self.stream_counts = {'ticker': 0, 'depth': 0, 'kline': 0}
        
        # Logging
        self.logger = logging.getLogger(__name__)
        
    async def connect(self):
        """Connect to Binance WebSocket streams"""
        try:
            self.logger.info("Connecting to Binance WebSocket streams")
            
            self.connected = True
            self.connection_start_time = datetime.now(timezone.utc)
            
            # Start background tasks
            asyncio.create_task(self._heartbeat_task())
            asyncio.create_task(self._connection_monitor())
            
            self.logger.info("Connected to Binance WebSocket streams")
            await self._notify_connection_status("CONNECTED")
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Binance: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from all Binance WebSocket streams"""
        self.connected = False
        
        # Close all WebSocket connections
        for stream_name, ws in self.websockets.items():
            try:
                await ws.close()
            except Exception as e:
                self.logger.error(f"Error closing {stream_name} WebSocket: {e}")
        
        self.websockets.clear()
        self.subscribed_streams.clear()
                
        await self._notify_connection_status("DISCONNECTED")
        self.logger.info("Disconnected from Binance WebSocket streams")
    
    async def wait_connected(self):
        """Wait for connection to be established"""
        while not self.connected:
            await asyncio.sleep(0.1)
    
    async def subscribe_symbols(self, symbols: List[str]):
        """Subscribe to real-time data for symbols"""
        if not self.connected:
            raise ConnectionError("Not connected to Binance")
        
        new_symbols = set(symbols)
        
        self.logger.info(f"Subscribing to {len(new_symbols)} symbols: {new_symbols}")
        
        # Subscribe to ticker streams
        await self._subscribe_ticker_streams(new_symbols)
        
        # Subscribe to order book depth streams
        await self._subscribe_depth_streams(new_symbols)
    
    async def unsubscribe_symbols(self, symbols: List[str]):
        """Unsubscribe from real-time data for symbols"""
        if not self.connected:
            return
            
        symbols_to_remove = set(symbols)
        
        self.logger.info(f"Unsubscribing from {len(symbols_to_remove)} symbols: {symbols_to_remove}")
        
        # Unsubscribe from streams
        for stream_type in self.subscribed_streams:
            self.subscribed_streams[stream_type] -= symbols_to_remove
            
            # Close stream if no symbols left
            if not self.subscribed_streams[stream_type]:
                stream_name = f"{stream_type}_stream"
                if stream_name in self.websockets:
                    await self.websockets[stream_name].close()
                    del self.websockets[stream_name]
    
    async def _subscribe_ticker_streams(self, symbols: set[str]):
        """Subscribe to ticker streams for symbols"""
        try:
            # Binance uses lowercase symbols
            binance_symbols = {symbol.lower() + '@ticker' for symbol in symbols}
            
            # Create stream URL
            streams = '/'.join(binance_symbols)
            stream_url = f"{self.binance_config.stream_url}/stream?streams={streams}"
            
            # Connect to ticker stream
            ws = await websockets.connect(
                stream_url,
                ping_interval=self.binance_config.heartbeat_interval,
                ping_timeout=10
            )
            
            self.websockets['ticker_stream'] = ws
            self.subscribed_streams['ticker'] = symbols.copy()
            self.stream_counts['ticker'] += 1
            
            # Start message handler for this stream
            asyncio.create_task(self._ticker_message_handler(ws))
            
        except Exception as e:
            self.logger.error(f"Error subscribing to ticker streams: {e}")
    
    async def _subscribe_depth_streams(self, symbols: set[str]):
        """Subscribe to order book depth streams for symbols"""
        try:
            # Binance uses lowercase symbols with depth level
            binance_symbols = {symbol.lower() + '@depth20@100ms' for symbol in symbols}
            
            # Create stream URL
            streams = '/'.join(binance_symbols)
            stream_url = f"{self.binance_config.stream_url}/stream?streams={streams}"
            
            # Connect to depth stream
            ws = await websockets.connect(
                stream_url,
                ping_interval=self.binance_config.heartbeat_interval,
                ping_timeout=10
            )
            
            self.websockets['depth_stream'] = ws
            self.subscribed_streams['depth'] = symbols.copy()
            self.stream_counts['depth'] += 1
            
            # Start message handler for this stream
            asyncio.create_task(self._depth_message_handler(ws))
            
        except Exception as e:
            self.logger.error(f"Error subscribing to depth streams: {e}")
    
    async def _ticker_message_handler(self, ws: websockets.WebSocketServerProtocol):
        """Handle ticker stream messages"""
        try:
            async for message in ws:
                await self._process_ticker_message(message)
                
        except ConnectionClosed:
            self.logger.warning("Binance ticker stream connection closed")
        except Exception as e:
            self.logger.error(f"Error in ticker message handler: {e}")
    
    async def _depth_message_handler(self, ws: websockets.WebSocketServerProtocol):
        """Handle depth stream messages"""
        try:
            async for message in ws:
                await self._process_depth_message(message)
                
        except ConnectionClosed:
            self.logger.warning("Binance depth stream connection closed")
        except Exception as e:
            self.logger.error(f"Error in depth message handler: {e}")
    
    async def _process_ticker_message(self, message: str):
        """Process ticker stream message"""
        try:
            self.messages_received += 1
            self.bytes_received += len(message)
            
            # Parse JSON message
            data = json.loads(message)
            
            # Check if it's a combined stream response
            if 'stream' in data and 'data' in data:
                stream_data = data['data']
                await self._process_ticker_data(stream_data)
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse ticker JSON: {e}")
        except Exception as e:
            self.logger.error(f"Error processing ticker message: {e}")
    
    async def _process_depth_message(self, message: str):
        """Process depth stream message"""
        try:
            self.messages_received += 1
            self.bytes_received += len(message)
            
            # Parse JSON message
            data = json.loads(message)
            
            # Check if it's a combined stream response
            if 'stream' in data and 'data' in data:
                stream_data = data['data']
                await self._process_depth_data(stream_data)
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse depth JSON: {e}")
        except Exception as e:
            self.logger.error(f"Error processing depth message: {e}")
    
    async def _process_ticker_data(self, data: Dict[str, Any]):
        """Process ticker data from Binance"""
        try:
            # Extract symbol (remove @ticker suffix)
            symbol = data.get('s', '').upper().replace('@TICKER', '')
            
            # Extract tick data fields
            bid = float(data.get('b', 0))  # Best bid price
            ask = float(data.get('a', 0))  # Best ask price
            bid_size = 0  # Binance ticker doesn't provide sizes
            ask_size = 0  # Binance ticker doesn't provide sizes
            last_price = float(data.get('c', 0))  # Last price
            last_size = 0  # Not available in ticker
            volume = float(data.get('v', 0))  # 24h volume
            
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
                volume=int(volume),
                broker='binance',
                exchange='BINANCE',
                sequence_number=data.get('E', None)  # Event time
            )
            
            # Update OHLC if available
            if 'o' in data:  # Open price
                tick_data.open = float(data['o'])
            if 'h' in data:  # High price
                tick_data.high = float(data['h'])
            if 'l' in data:  # Low price
                tick_data.low = float(data['l'])
            if 'c' in data:  # Close price
                tick_data.close = float(data['c'])
            
            # Notify handlers
            await self._notify_tick_handlers(tick_data)
            
        except Exception as e:
            self.logger.error(f"Error processing ticker data: {e}")
    
    async def _process_depth_data(self, data: Dict[str, Any]):
        """Process order book depth data from Binance"""
        try:
            # Extract symbol (remove @depth suffix)
            symbol = data.get('s', '').upper().replace('@DEPTH', '')
            
            # Process bid levels
            bids = data.get('b', [])  # [[price, quantity], ...]
            for bid_data in bids:
                price = float(bid_data[0])
                size = int(float(bid_data[1]))
                
                level_update = PriceLevelUpdate(
                    symbol=symbol,
                    side='BID',
                    price=price,
                    size=size,
                    timestamp=datetime.now(timezone.utc),
                    broker='binance',
                    update_type='UPDATE',
                    sequence_number=data.get('u', None)
                )
                
                await self._notify_tick_handlers(level_update)
            
            # Process ask levels
            asks = data.get('a', [])  # [[price, quantity], ...]
            for ask_data in asks:
                price = float(ask_data[0])
                size = int(float(ask_data[1]))
                
                level_update = PriceLevelUpdate(
                    symbol=symbol,
                    side='ASK',
                    price=price,
                    size=size,
                    timestamp=datetime.now(timezone.utc),
                    broker='binance',
                    update_type='UPDATE',
                    sequence_number=data.get('u', None)
                )
                
                await self._notify_tick_handlers(level_update)
                
        except Exception as e:
            self.logger.error(f"Error processing depth data: {e}")
    
    async def _heartbeat_task(self):
        """Send periodic heartbeat to maintain connection"""
        while self.connected:
            try:
                self.last_heartbeat = datetime.now(timezone.utc)
                await asyncio.sleep(self.binance_config.heartbeat_interval)
                
            except Exception as e:
                self.logger.error(f"Error in heartbeat task: {e}")
                break
    
    async def _connection_monitor(self):
        """Monitor connection health and reconnect if needed"""
        while self.connected:
            try:
                # Check each WebSocket connection
                for stream_name, ws in self.websockets.items():
                    if ws.closed:
                        self.logger.warning(f"{stream_name} connection closed, will attempt to reconnect")
                        # Trigger reconnection logic here if needed
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                self.logger.error(f"Error in connection monitor: {e}")
                await asyncio.sleep(30)
    
    async def _notify_connection_status(self, status: str):
        """Notify connection status change"""
        for handler in self.connection_handlers:
            try:
                await handler('binance', status)
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
            'active_streams': len(self.websockets),
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            'connection_uptime_seconds': uptime,
            'stream_counts': self.stream_counts.copy(),
            'subscribed_streams': {k: list(v) for k, v in self.subscribed_streams.items()}
        }
    
    def is_connected(self) -> bool:
        """Check if stream is connected"""
        return self.connected
    
    @property
    def broker_name(self) -> str:
        """Get broker name"""
        return 'BINANCE'
    
    def parse_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a raw message from Binance stream into normalized format"""
        return {
            'symbol': message.get('s', ''),
            'bid': message.get('b', 0.0),
            'ask': message.get('a', 0.0),
            'bid_size': message.get('B', 0),
            'ask_size': message.get('A', 0),
            'last_price': message.get('c', 0.0),
            'last_size': message.get('v', 0),
            'volume': message.get('v', 0),
            'timestamp': message.get('E')
        }
    
    async def close(self):
        """Close the WebSocket connection"""
        await self.disconnect()