"""
Coinbase WebSocket Stream

Real-time market data streaming for Coinbase Pro cryptocurrency exchange.
Handles WebSocket connections, data parsing, and event publishing.

Features:
- Coinbase Pro WebSocket API integration
- Real-time tick data streaming
- Level 2 order book data
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
class CoinbaseStreamConfig:
    """Configuration for Coinbase WebSocket stream"""
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    api_passphrase: Optional[str] = None
    base_url: str = "https://api.pro.coinbase.com"
    stream_url: str = "wss://ws-feed.pro.coinbase.com"
    reconnect_attempts: int = 5
    heartbeat_interval: int = 30
    connection_timeout: int = 10


class CoinbaseWebSocketStream:
    """
    WebSocket stream for Coinbase Pro market data.
    
    Connects to Coinbase Pro WebSocket API and streams real-time
    cryptocurrency market data and order book updates.
    """
    
    def __init__(self, config: Dict[str, Any], event_manager):
        self.config = config
        self.event_manager = event_manager
        
        # Stream configuration
        coinbase_config = config.get('coinbase', {})
        self.coinbase_config = CoinbaseStreamConfig(
            api_key=coinbase_config.get('api_key'),
            api_secret=coinbase_config.get('api_secret'),
            api_passphrase=coinbase_config.get('api_passphrase'),
            base_url=coinbase_config.get('base_url', 'https://api.pro.coinbase.com'),
            stream_url=coinbase_config.get('stream_url', 'wss://ws-feed.pro.coinbase.com'),
            reconnect_attempts=coinbase_config.get('reconnect_attempts', 5),
            heartbeat_interval=coinbase_config.get('heartbeat_interval', 30)
        )
        
        # Connection state
        self.websocket = None
        self.connected = False
        self.subscribed_channels: set[str] = set()
        self.subscribed_products: set[str] = set()
        
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
        """Connect to Coinbase Pro WebSocket"""
        try:
            self.logger.info(f"Connecting to Coinbase Pro WebSocket at {self.coinbase_config.stream_url}")
            
            # Connect to WebSocket
            self.websocket = await asyncio.wait_for(
                websockets.connect(
                    self.coinbase_config.stream_url,
                    ping_interval=self.coinbase_config.heartbeat_interval,
                    ping_timeout=10
                ),
                timeout=self.coinbase_config.connection_timeout
            )
            
            self.connected = True
            self.connection_start_time = datetime.now(timezone.utc)
            
            # Start background tasks
            asyncio.create_task(self._message_handler())
            asyncio.create_task(self._heartbeat_task())
            
            self.logger.info("Connected to Coinbase Pro WebSocket")
            await self._notify_connection_status("CONNECTED")
            
        except asyncio.TimeoutError:
            self.logger.error("Connection timeout to Coinbase Pro")
            raise ConnectionError("Connection timeout")
        except Exception as e:
            self.logger.error(f"Failed to connect to Coinbase Pro: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from Coinbase Pro WebSocket"""
        self.connected = False
        
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                self.logger.error(f"Error closing WebSocket: {e}")
            finally:
                self.websocket = None
                
        await self._notify_connection_status("DISCONNECTED")
        self.logger.info("Disconnected from Coinbase Pro")
    
    async def wait_connected(self):
        """Wait for connection to be established"""
        while not self.connected:
            await asyncio.sleep(0.1)
    
    async def subscribe_symbols(self, symbols: List[str]):
        """Subscribe to real-time data for symbols"""
        if not self.connected:
            raise ConnectionError("Not connected to Coinbase Pro")
        
        new_symbols = set(symbols)
        
        # Convert symbols to Coinbase format (e.g., BTC-USD)
        coinbase_symbols = []
        for symbol in new_symbols:
            # Convert common formats to Coinbase format
            if '-' not in symbol:
                # Handle formats like BTCUSD -> BTC-USD
                if len(symbol) >= 6:
                    coinbase_symbol = symbol[:-3] + '-' + symbol[-3:]
                else:
                    coinbase_symbol = symbol
            else:
                coinbase_symbol = symbol.upper()
            coinbase_symbols.append(coinbase_symbol)
        
        self.logger.info(f"Subscribing to {len(new_symbols)} symbols: {new_symbols}")
        
        try:
            # Subscribe to ticker channel
            ticker_subscription = {
                "type": "subscribe",
                "product_ids": coinbase_symbols,
                "channels": ["ticker"]
            }
            
            await self.websocket.send(json.dumps(ticker_subscription))
            self.subscribed_channels.add("ticker")
            self.subscribed_products.update(coinbase_symbols)
            
            # Subscribe to level 2 order book
            level2_subscription = {
                "type": "subscribe",
                "product_ids": coinbase_symbols,
                "channels": ["level2"]
            }
            
            await self.websocket.send(json.dumps(level2_subscription))
            self.subscribed_channels.add("level2")
            
        except Exception as e:
            self.logger.error(f"Error subscribing to symbols: {e}")
            raise
    
    async def unsubscribe_symbols(self, symbols: List[str]):
        """Unsubscribe from real-time data for symbols"""
        if not self.connected:
            return
            
        symbols_to_remove = set(symbols)
        
        self.logger.info(f"Unsubscribing from {len(symbols_to_remove)} symbols: {symbols_to_remove}")
        
        try:
            # Convert symbols to Coinbase format
            coinbase_symbols = []
            for symbol in symbols_to_remove:
                if '-' not in symbol:
                    if len(symbol) >= 6:
                        coinbase_symbol = symbol[:-3] + '-' + symbol[-3:]
                    else:
                        coinbase_symbol = symbol
                else:
                    coinbase_symbol = symbol.upper()
                coinbase_symbols.append(coinbase_symbol)
            
            # Unsubscribe from ticker channel
            ticker_unsubscription = {
                "type": "unsubscribe",
                "product_ids": coinbase_symbols,
                "channels": ["ticker"]
            }
            
            await self.websocket.send(json.dumps(ticker_unsubscription))
            
            # Unsubscribe from level 2 channel
            level2_unsubscription = {
                "type": "unsubscribe",
                "product_ids": coinbase_symbols,
                "channels": ["level2"]
            }
            
            await self.websocket.send(json.dumps(level2_unsubscription))
            
            # Update tracking
            self.subscribed_products -= set(coinbase_symbols)
            
        except Exception as e:
            self.logger.error(f"Error unsubscribing from symbols: {e}")
    
    async def _message_handler(self):
        """Handle incoming WebSocket messages"""
        try:
            async for message in self.websocket:
                await self._process_message(message)
                
        except ConnectionClosed:
            self.logger.warning("Coinbase WebSocket connection closed")
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
            message_type = data.get('type', '')
            
            if message_type == 'ticker':
                await self._process_ticker_message(data)
            elif message_type == 'l2update':
                await self._process_l2update_message(data)
            elif message_type == 'snapshot':
                await self._process_snapshot_message(data)
            elif message_type == 'error':
                await self._process_error_message(data)
            elif message_type == 'subscriptions':
                await self._process_subscription_message(data)
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON message: {e}")
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            await self._handle_error(e)
    
    async def _process_ticker_message(self, data: Dict[str, Any]):
        """Process ticker message from Coinbase"""
        try:
            product_id = data.get('product_id', '')
            symbol = product_id.replace('-', '')  # Convert BTC-USD -> BTCUSD
            
            # Extract tick data fields
            bid = float(data.get('best_bid', 0))
            ask = float(data.get('best_ask', 0))
            bid_size = 0  # Not available in ticker
            ask_size = 0  # Not available in ticker
            last_price = float(data.get('price', 0))
            last_size = float(data.get('last_size', 0))
            volume = float(data.get('volume_24h', 0))
            
            # Create TickData object
            tick_data = TickData(
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                bid=bid,
                ask=ask,
                bid_size=bid_size,
                ask_size=ask_size,
                last_price=last_price,
                last_size=int(last_size),
                volume=int(volume),
                broker='coinbase',
                exchange='COINBASE',
                sequence_number=int(data.get('sequence', 0)) if data.get('sequence') else None
            )
            
            # Update OHLC if available
            if 'open_24h' in data:
                tick_data.open = float(data['open_24h'])
            if 'high_24h' in data:
                tick_data.high = float(data['high_24h'])
            if 'low_24h' in data:
                tick_data.low = float(data['low_24h'])
            if 'price' in data:
                tick_data.close = float(data['price'])
            
            # Notify handlers
            await self._notify_tick_handlers(tick_data)
            
        except Exception as e:
            self.logger.error(f"Error processing ticker message: {e}")
    
    async def _process_l2update_message(self, data: Dict[str, Any]):
        """Process level 2 update message from Coinbase"""
        try:
            product_id = data.get('product_id', '')
            symbol = product_id.replace('-', '')
            
            # Process changes array
            changes = data.get('changes', [])
            for change in changes:
                side = change[0].upper()  # 'buy' or 'sell'
                price = float(change[1])
                size = float(change[2])
                
                level_update = PriceLevelUpdate(
                    symbol=symbol,
                    side=side,
                    price=price,
                    size=int(size * 1000000),  # Convert to integer shares
                    timestamp=datetime.now(timezone.utc),
                    broker='coinbase',
                    update_type='UPDATE',
                    sequence_number=int(data.get('sequence', 0)) if data.get('sequence') else None
                )
                
                await self._notify_tick_handlers(level_update)
                
        except Exception as e:
            self.logger.error(f"Error processing L2 update message: {e}")
    
    async def _process_snapshot_message(self, data: Dict[str, Any]):
        """Process snapshot message (initial order book state)"""
        try:
            product_id = data.get('product_id', '')
            symbol = product_id.replace('-', '')
            
            # Process bids
            bids = data.get('bids', [])
            for bid in bids:
                price = float(bid[0])
                size = float(bid[1])
                
                level_update = PriceLevelUpdate(
                    symbol=symbol,
                    side='BID',
                    price=price,
                    size=int(size * 1000000),
                    timestamp=datetime.now(timezone.utc),
                    broker='coinbase',
                    update_type='SNAPSHOT',
                    sequence_number=int(data.get('sequence', 0)) if data.get('sequence') else None
                )
                
                await self._notify_tick_handlers(level_update)
            
            # Process asks
            asks = data.get('asks', [])
            for ask in asks:
                price = float(ask[0])
                size = float(ask[1])
                
                level_update = PriceLevelUpdate(
                    symbol=symbol,
                    side='ASK',
                    price=price,
                    size=int(size * 1000000),
                    timestamp=datetime.now(timezone.utc),
                    broker='coinbase',
                    update_type='SNAPSHOT',
                    sequence_number=int(data.get('sequence', 0)) if data.get('sequence') else None
                )
                
                await self._notify_tick_handlers(level_update)
                
        except Exception as e:
            self.logger.error(f"Error processing snapshot message: {e}")
    
    async def _process_error_message(self, data: Dict[str, Any]):
        """Process error message from Coinbase"""
        error_message = data.get('message', 'Unknown error')
        self.logger.error(f"Coinbase error: {error_message}")
        
        error_event = TickEvent(
            event_type=TickEventType.ERROR,
            symbol="",
            broker='coinbase',
            timestamp=datetime.now(timezone.utc),
            data={'error': error_message, 'raw_data': data}
        )
        
        await self._notify_tick_handlers(error_event)
    
    async def _process_subscription_message(self, data: Dict[str, Any]):
        """Process subscription confirmation message"""
        channels = data.get('channels', [])
        self.logger.info(f"Subscribed to channels: {channels}")
    
    async def _heartbeat_task(self):
        """Send periodic heartbeat to maintain connection"""
        while self.connected:
            try:
                if self.websocket:
                    # Coinbase doesn't require explicit heartbeat
                    # Connection is maintained by ping/pong
                    pass
                    
                await asyncio.sleep(self.coinbase_config.heartbeat_interval)
                
            except Exception as e:
                self.logger.error(f"Error in heartbeat task: {e}")
                break
    
    async def _notify_connection_status(self, status: str):
        """Notify connection status change"""
        for handler in self.connection_handlers:
            try:
                await handler('coinbase', status)
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
            'subscribed_channels': list(self.subscribed_channels),
            'subscribed_products': list(self.subscribed_products),
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            'connection_uptime_seconds': uptime,
            'total_subscriptions': len(self.subscribed_channels) * len(self.subscribed_products)
        }
    
    def is_connected(self) -> bool:
        """Check if stream is connected"""
        return self.connected
    
    @property
    def broker_name(self) -> str:
        """Get broker name"""
        return 'COINBASE'
    
    def parse_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a raw message from Coinbase stream into normalized format"""
        return {
            'symbol': message.get('product_id', ''),
            'bid': float(message.get('best_bid', 0.0)),
            'ask': float(message.get('best_ask', 0.0)),
            'bid_size': float(message.get('best_bid_size', 0)),
            'ask_size': float(message.get('best_ask_size', 0)),
            'last_price': float(message.get('price', 0.0)),
            'last_size': float(message.get('last_size', 0)),
            'volume': float(message.get('volume_24h', 0)),
            'timestamp': message.get('time')
        }
    
    async def close(self):
        """Close the WebSocket connection"""
        await self.disconnect()