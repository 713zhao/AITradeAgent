"""
Interactive Brokers WebSocket Stream

Real-time market data streaming for Interactive Brokers via TWS API.
Handles WebSocket connections, data parsing, and event publishing.

Features:
- TWS API connection management
- Real-time tick data streaming
- Market depth data
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
class IBKRStreamConfig:
    """Configuration for IBKR WebSocket stream"""
    host: str = "localhost"
    port: int = 7497
    client_id: int = 1
    reconnect_attempts: int = 5
    heartbeat_interval: int = 30
    max_message_size: int = 1024 * 1024  # 1MB
    connection_timeout: int = 10
    subscribe_timeout: int = 5


class IBKRWebSocketStream:
    """
    WebSocket stream for Interactive Brokers market data.
    
    Connects to IBKR TWS API via WebSocket and streams
    real-time tick data and order book updates.
    """
    
    def __init__(self, config: Dict[str, Any], event_manager):
        self.config = config
        self.event_manager = event_manager
        
        # Stream configuration
        stream_config = config.get('ibkr', {})
        self.ibkr_config = IBKRStreamConfig(
            host=stream_config.get('host', 'localhost'),
            port=stream_config.get('port', 7497),
            client_id=stream_config.get('client_id', 1),
            reconnect_attempts=stream_config.get('reconnect_attempts', 5),
            heartbeat_interval=stream_config.get('heartbeat_interval', 30)
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
        
        # Logging
        self.logger = logging.getLogger(__name__)
        
    async def connect(self):
        """Connect to IBKR TWS API via WebSocket"""
        try:
            self.logger.info(f"Connecting to IBKR TWS at {self.ibkr_config.host}:{self.ibkr_config.port}")
            
            # Create WebSocket URI
            ws_uri = f"ws://{self.ibkr_config.host}:{self.ibkr_config.port}/v1/api/ws"
            
            # Connect with timeout
            self.websocket = await asyncio.wait_for(
                websockets.connect(
                    ws_uri,
                    max_size=self.ibkr_config.max_message_size,
                    ping_interval=self.ibkr_config.heartbeat_interval,
                    ping_timeout=10
                ),
                timeout=self.ibkr_config.connection_timeout
            )
            
            self.connected = True
            self.connection_start_time = datetime.now(timezone.utc)
            
            # Start background tasks
            asyncio.create_task(self._message_handler())
            asyncio.create_task(self._heartbeat_task())
            
            self.logger.info("Connected to IBKR TWS WebSocket")
            await self._notify_connection_status("CONNECTED")
            
        except asyncio.TimeoutError:
            self.logger.error("Connection timeout to IBKR TWS")
            raise ConnectionError("Connection timeout")
        except Exception as e:
            self.logger.error(f"Failed to connect to IBKR TWS: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from IBKR TWS API"""
        self.connected = False
        
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                self.logger.error(f"Error closing WebSocket: {e}")
            finally:
                self.websocket = None
                
        await self._notify_connection_status("DISCONNECTED")
        self.logger.info("Disconnected from IBKR TWS")
    
    async def wait_connected(self):
        """Wait for connection to be established"""
        while not self.connected:
            await asyncio.sleep(0.1)
    
    async def subscribe_symbols(self, symbols: List[str]):
        """Subscribe to real-time data for symbols"""
        if not self.connected:
            raise ConnectionError("Not connected to IBKR TWS")
        
        new_symbols = set(symbols) - self.subscribed_symbols
        if not new_symbols:
            return
            
        self.logger.info(f"Subscribing to {len(new_symbols)} new symbols: {new_symbols}")
        
        for symbol in new_symbols:
            try:
                # Send subscription request to IBKR TWS
                subscription_request = {
                    "topic": "marketdata",
                    "symbol": symbol,
                    "fields": ["BID", "ASK", "BID_SIZE", "ASK_SIZE", "LAST", "VOLUME"],
                    "snapshot": False
                }
                
                await self.websocket.send(json.dumps(subscription_request))
                self.subscribed_symbols.add(symbol)
                
            except Exception as e:
                self.logger.error(f"Error subscribing to {symbol}: {e}")
    
    async def unsubscribe_symbols(self, symbols: List[str]):
        """Unsubscribe from real-time data for symbols"""
        if not self.connected:
            return
            
        symbols_to_remove = set(symbols) & self.subscribed_symbols
        if not symbols_to_remove:
            return
            
        self.logger.info(f"Unsubscribing from {len(symbols_to_remove)} symbols: {symbols_to_remove}")
        
        for symbol in symbols_to_remove:
            try:
                # Send unsubscription request to IBKR TWS
                unsubscription_request = {
                    "topic": "marketdata",
                    "symbol": symbol,
                    "action": "unsubscribe"
                }
                
                await self.websocket.send(json.dumps(unsubscription_request))
                self.subscribed_symbols.remove(symbol)
                
            except Exception as e:
                self.logger.error(f"Error unsubscribing from {symbol}: {e}")
    
    async def _message_handler(self):
        """Handle incoming WebSocket messages"""
        try:
            async for message in self.websocket:
                await self._process_message(message)
                
        except ConnectionClosed:
            self.logger.warning("IBKR WebSocket connection closed")
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
            if 'topic' in data:
                await self._handle_market_data_message(data)
            elif 'error' in data:
                await self._handle_error_message(data)
            elif 'heartbeat' in data:
                self.last_heartbeat = datetime.now(timezone.utc)
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON message: {e}")
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            await self._handle_error(e)
    
    async def _handle_market_data_message(self, data: Dict[str, Any]):
        """Handle market data message from IBKR"""
        try:
            symbol = data.get('symbol', '')
            topic = data.get('topic', '')
            
            if topic == 'marketdata':
                await self._process_tick_data(data, symbol)
            elif topic == 'marketdepth':
                await self._process_order_book_update(data, symbol)
                
        except Exception as e:
            self.logger.error(f"Error handling market data message: {e}")
    
    async def _process_tick_data(self, data: Dict[str, Any], symbol: str):
        """Process tick data from IBKR"""
        try:
            # Extract tick data fields
            bid = float(data.get('BID', 0))
            ask = float(data.get('ASK', 0))
            bid_size = int(data.get('BID_SIZE', 0))
            ask_size = int(data.get('ASK_SIZE', 0))
            last_price = float(data.get('LAST', 0))
            last_size = int(data.get('LAST_SIZE', 0))
            volume = int(data.get('VOLUME', 0))
            
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
                broker='interactive_brokers',
                exchange='IBKR',
                sequence_number=data.get('sequence', None)
            )
            
            # Update OHLC if available
            if 'OPEN' in data:
                tick_data.open = float(data['OPEN'])
            if 'HIGH' in data:
                tick_data.high = float(data['HIGH'])
            if 'LOW' in data:
                tick_data.low = float(data['LOW'])
            if 'CLOSE' in data:
                tick_data.close = float(data['CLOSE'])
            
            # Publish tick event
            event = TickEvent(
                event_type=TickEventType.TICK,
                symbol=symbol,
                broker='interactive_brokers',
                timestamp=tick_data.timestamp,
                data={'tick_data': tick_data.to_dict()}
            )
            
            # Notify handlers
            await self._notify_tick_handlers(tick_data)
            
        except Exception as e:
            self.logger.error(f"Error processing tick data for {symbol}: {e}")
    
    async def _process_order_book_update(self, data: Dict[str, Any], symbol: str):
        """Process order book update from IBKR"""
        try:
            side = data.get('side', '').upper()
            price = float(data.get('price', 0))
            size = int(data.get('size', 0))
            update_type = data.get('action', 'UPDATE')
            
            # Create price level update
            level_update = PriceLevelUpdate(
                symbol=symbol,
                side=side,
                price=price,
                size=size,
                timestamp=datetime.now(timezone.utc),
                broker='interactive_brokers',
                update_type=update_type,
                sequence_number=data.get('sequence', None)
            )
            
            # Publish order book event
            event = TickEvent(
                event_type=TickEventType.ORDER_BOOK_UPDATE,
                symbol=symbol,
                broker='interactive_brokers',
                timestamp=level_update.timestamp,
                data={'level_update': level_update.to_dict()}
            )
            
            # Notify handlers
            await self._notify_tick_handlers(level_update)
            
        except Exception as e:
            self.logger.error(f"Error processing order book update for {symbol}: {e}")
    
    async def _handle_error_message(self, data: Dict[str, Any]):
        """Handle error message from IBKR"""
        error_message = data.get('error', 'Unknown error')
        self.logger.error(f"IBKR error: {error_message}")
        
        error_event = TickEvent(
            event_type=TickEventType.ERROR,
            symbol="",
            broker='interactive_brokers',
            timestamp=datetime.now(timezone.utc),
            data={'error': error_message, 'raw_data': data}
        )
        
        await self._notify_tick_handlers(error_event)
    
    async def _heartbeat_task(self):
        """Send periodic heartbeat to maintain connection"""
        while self.connected:
            try:
                if self.websocket:
                    heartbeat = {
                        "topic": "heartbeat",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    await self.websocket.send(json.dumps(heartbeat))
                    
                await asyncio.sleep(self.ibkr_config.heartbeat_interval)
                
            except Exception as e:
                self.logger.error(f"Error in heartbeat task: {e}")
                break
    
    async def _notify_connection_status(self, status: str):
        """Notify connection status change"""
        for handler in self.connection_handlers:
            try:
                await handler('ibkr', status)
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
            'symbols': list(self.subscribed_symbols)
        }
    
    def is_connected(self) -> bool:
        """Check if stream is connected"""
        return self.connected
    
    @property
    def broker_name(self) -> str:
        """Get broker name"""
        return 'IBKR'
    
    def parse_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a raw message from IBKR stream into normalized format"""
        return {
            'symbol': message.get('ticker', ''),
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