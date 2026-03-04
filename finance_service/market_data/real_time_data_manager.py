"""
Real-time Market Data Manager

Central hub for all real-time market data feeds, WebSocket connections,
and data distribution across the trading system.

Features:
- Multi-broker WebSocket connection management
- Real-time data routing and distribution
- Performance monitoring and metrics
- Event-driven architecture
- Automatic reconnection and failover
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import time
from collections import defaultdict, deque

from .tick_data import TickData, TickEvent, TickEventType
from .websocket_streams.ibkr_stream import IBKRWebSocketStream
from .websocket_streams.tda_stream import TDAWebSocketStream  
from .websocket_streams.binance_stream import BinanceWebSocketStream
from .websocket_streams.coinbase_stream import CoinbaseWebSocketStream
from .websocket_streams.alpaca_stream import AlpacaWebSocketStream


class DataSourceStatus(Enum):
    """Status of a market data source"""
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"
    RECONNECTING = "RECONNECTING"


@dataclass
class DataSource:
    """Market data source configuration and status"""
    name: str
    broker: str
    stream_class: type
    status: DataSourceStatus = DataSourceStatus.DISCONNECTED
    last_update: Optional[datetime] = None
    error_count: int = 0
    max_errors: int = 5
    reconnect_attempts: int = 0
    max_reconnect_attempts: int = 10
    subscribed_symbols: Set[str] = field(default_factory=set)
    connection: Optional[Any] = None
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RealTimeMetrics:
    """Real-time data processing metrics"""
    total_ticks_processed: int = 0
    ticks_per_second: float = 0.0
    average_latency_ms: float = 0.0
    active_connections: int = 0
    memory_usage_mb: float = 0.0
    error_rate: float = 0.0
    last_update: Optional[datetime] = None


class RealTimeDataManager:
    """
    Central manager for all real-time market data feeds.
    
    Manages WebSocket connections to multiple brokers, processes
    real-time data, and distributes it to subscribers.
    """
    
    def __init__(self, config: Dict[str, Any], event_manager):
        self.config = config
        self.event_manager = event_manager
        
        # Logging
        self.logger = logging.getLogger(__name__)
        
        # Data sources configuration
        self.data_sources: Dict[str, DataSource] = {}
        self._initialize_data_sources()
        
        # Data storage
        self.tick_data_buffer: deque = deque(maxlen=10000)
        self.symbol_subscribers: Dict[str, Set[Callable]] = defaultdict(set)
        self.broker_subscribers: Dict[str, Set[Callable]] = defaultdict(set)
        
        # Metrics and monitoring
        self.metrics = RealTimeMetrics()
        self.start_time = time.time()
        self.last_metrics_update = time.time()
        
        # Control flags
        self.running = False
        self._tasks: List[asyncio.Task] = []
        
    def _initialize_data_sources(self):
        """Initialize data sources for each supported broker"""
        stream_configs = self.config.get('websockets', {})
        
        # IBKR WebSocket Stream
        if stream_configs.get('ibkr', {}).get('enabled', False):
            self.data_sources['ibkr'] = DataSource(
                name='ibkr',
                broker='interactive_brokers',
                stream_class=IBKRWebSocketStream
            )
            
        # TDA WebSocket Stream  
        if stream_configs.get('tda', {}).get('enabled', False):
            self.data_sources['tda'] = DataSource(
                name='tda',
                broker='td_ameritrade',
                stream_class=TDAWebSocketStream
            )
            
        # Binance WebSocket Stream
        if stream_configs.get('binance', {}).get('enabled', False):
            self.data_sources['binance'] = DataSource(
                name='binance',
                broker='binance',
                stream_class=BinanceWebSocketStream
            )
            
        # Coinbase WebSocket Stream
        if stream_configs.get('coinbase', {}).get('enabled', False):
            self.data_sources['coinbase'] = DataSource(
                name='coinbase',
                broker='coinbase',
                stream_class=CoinbaseWebSocketStream
            )
            
        # Alpaca WebSocket Stream
        if stream_configs.get('alpaca', {}).get('enabled', False):
            self.data_sources['alpaca'] = DataSource(
                name='alpaca',
                broker='alpaca',
                stream_class=AlpacaWebSocketStream
            )
            
        self.logger.info(f"Initialized {len(self.data_sources)} data sources")
    
    async def start(self):
        """Start all data sources and begin processing"""
        if self.running:
            return
            
        self.running = True
        self.logger.info("Starting Real-time Data Manager")
        
        # Start metrics monitoring task
        self._tasks.append(asyncio.create_task(self._metrics_monitoring_task()))
        
        # Start data source tasks
        for source_name, source in self.data_sources.items():
            self._tasks.append(asyncio.create_task(self._manage_source(source_name)))
            
        # Start data distribution task
        self._tasks.append(asyncio.create_task(self._data_distribution_task()))
        
        self.logger.info("Real-time Data Manager started successfully")
    
    async def stop(self):
        """Stop all data sources and cleanup"""
        if not self.running:
            return
            
        self.running = False
        self.logger.info("Stopping Real-time Data Manager")
        
        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
                
        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            
        # Close all connections
        for source in self.data_sources.values():
            if source.connection and hasattr(source.connection, 'close'):
                await source.connection.close()
                
        self.logger.info("Real-time Data Manager stopped")
    
    async def _manage_source(self, source_name: str):
        """Manage a single data source with reconnection logic"""
        source = self.data_sources[source_name]
        source_config = self.config.get('websockets', {}).get(source_name, {})
        
        while self.running:
            try:
                # Create and connect stream
                source.status = DataSourceStatus.CONNECTING
                stream = source.stream_class(source_config, self.event_manager)
                
                # Subscribe to stream events
                stream.add_tick_handler(self._handle_tick_data)
                stream.add_connection_handler(self._handle_connection_event)
                
                # Connect and start streaming
                await stream.connect()
                source.connection = stream
                source.status = DataSourceStatus.CONNECTED
                source.reconnect_attempts = 0
                source.error_count = 0
                
                self.logger.info(f"Connected to {source_name} data stream")
                
                # Subscribe to configured symbols
                if source.subscribed_symbols:
                    await stream.subscribe_symbols(list(source.subscribed_symbols))
                    
                # Keep connection alive
                await stream.wait_connected()
                
            except Exception as e:
                source.error_count += 1
                source.status = DataSourceStatus.ERROR
                
                self.logger.error(f"Error with {source_name} stream: {e}")
                
                # Check if we should reconnect
                if (source.error_count < source.max_errors and 
                    source.reconnect_attempts < source.max_reconnect_attempts):
                    
                    source.status = DataSourceStatus.RECONNECTING
                    source.reconnect_attempts += 1
                    
                    # Exponential backoff
                    delay = min(2 ** source.reconnect_attempts, 60)
                    self.logger.info(f"Reconnecting to {source_name} in {delay}s (attempt {source.reconnect_attempts})")
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(f"Max retries reached for {source_name}, stopping")
                    break
                    
            finally:
                if source.connection:
                    try:
                        await source.connection.close()
                    except Exception as e:
                        self.logger.error(f"Error closing {source_name} connection: {e}")
                    source.connection = None
    
    async def _handle_tick_data(self, tick_data: TickData):
        """Handle incoming tick data from any source"""
        try:
            # Add to buffer
            self.tick_data_buffer.append(tick_data)
            
            # Update metrics
            self.metrics.total_ticks_processed += 1
            self.metrics.last_update = datetime.now(timezone.utc)
            
            # Find subscribers for this symbol
            if tick_data.symbol in self.symbol_subscribers:
                for callback in self.symbol_subscribers[tick_data.symbol]:
                    try:
                        await callback(tick_data)
                    except Exception as e:
                        self.logger.error(f"Error in symbol subscriber callback: {e}")
                        
            # Find subscribers for this broker
            if tick_data.broker in self.broker_subscribers:
                for callback in self.broker_subscribers[tick_data.broker]:
                    try:
                        await callback(tick_data)
                    except Exception as e:
                        self.logger.error(f"Error in broker subscriber callback: {e}")
                        
        except Exception as e:
            self.logger.error(f"Error handling tick data: {e}")
    
    async def _handle_connection_event(self, source_name: str, status: DataSourceStatus):
        """Handle connection status changes"""
        source = self.data_sources.get(source_name)
        if source:
            old_status = source.status
            source.status = status
            source.last_update = datetime.now(timezone.utc)
            
            self.logger.info(f"{source_name} connection status changed: {old_status.value} -> {status.value}")
            
            # Publish connection event
            event = TickEvent(
                event_type=TickEventType.CONNECTION_STATUS_CHANGED,
                symbol="",
                broker=source.broker,
                timestamp=datetime.now(timezone.utc),
                data={
                    'source': source_name,
                    'old_status': old_status.value,
                    'new_status': status.value
                }
            )
            
            # Notify subscribers
            await self._publish_event(event)
    
    async def _data_distribution_task(self):
        """Task to distribute data to subscribers"""
        while self.running:
            try:
                # Process any pending data distribution
                # This could include batch processing, aggregation, etc.
                await asyncio.sleep(0.1)  # 10 Hz processing
                
            except Exception as e:
                self.logger.error(f"Error in data distribution task: {e}")
                await asyncio.sleep(1)
    
    async def _metrics_monitoring_task(self):
        """Task to monitor and update metrics"""
        while self.running:
            try:
                current_time = time.time()
                
                # Calculate ticks per second
                if current_time - self.last_metrics_update >= 1.0:
                    elapsed = current_time - self.last_metrics_update
                    
                    # Count ticks in buffer (approximate)
                    ticks_in_window = len([t for t in self.tick_data_buffer 
                                         if t.timestamp.timestamp() > current_time - elapsed])
                    
                    self.metrics.ticks_per_second = ticks_in_window / elapsed
                    self.metrics.active_connections = sum(1 for s in self.data_sources.values() 
                                                         if s.status == DataSourceStatus.CONNECTED)
                    
                    # Calculate error rate
                    total_errors = sum(s.error_count for s in self.data_sources.values())
                    total_attempts = sum(s.error_count + 1 for s in self.data_sources.values())
                    self.metrics.error_rate = total_errors / max(total_attempts, 1)
                    
                    self.last_metrics_update = current_time
                    
                await asyncio.sleep(1.0)  # Update every second
                
            except Exception as e:
                self.logger.error(f"Error in metrics monitoring: {e}")
                await asyncio.sleep(5)
    
    async def _publish_event(self, event: TickEvent):
        """Publish an event to the event manager"""
        try:
            if self.event_manager:
                await self.event_manager.publish(event.event_type.value, event.data)
        except Exception as e:
            self.logger.error(f"Error publishing event: {e}")
    
    # Public API methods
    
    async def subscribe_symbol(self, symbol: str, callback: Callable[[TickData], None]):
        """Subscribe to tick data for a specific symbol"""
        self.symbol_subscribers[symbol].add(callback)
        
        # Subscribe to symbol on all connected sources
        for source in self.data_sources.values():
            if source.status == DataSourceStatus.CONNECTED and source.connection:
                try:
                    await source.connection.subscribe_symbols([symbol])
                    source.subscribed_symbols.add(symbol)
                except Exception as e:
                    self.logger.error(f"Error subscribing to {symbol} on {source.name}: {e}")
    
    async def unsubscribe_symbol(self, symbol: str, callback: Callable[[TickData], None]):
        """Unsubscribe from tick data for a specific symbol"""
        self.symbol_subscribers[symbol].discard(callback)
        
        # If no more subscribers, unsubscribe from sources
        if not self.symbol_subscribers[symbol]:
            for source in self.data_sources.values():
                if source.connection:
                    try:
                        await source.connection.unsubscribe_symbols([symbol])
                        source.subscribed_symbols.discard(symbol)
                    except Exception as e:
                        self.logger.error(f"Error unsubscribing from {symbol} on {source.name}: {e}")
    
    async def subscribe_broker(self, broker: str, callback: Callable[[TickData], None]):
        """Subscribe to all tick data from a specific broker"""
        self.broker_subscribers[broker].add(callback)
    
    async def unsubscribe_broker(self, broker: str, callback: Callable[[TickData], None]):
        """Unsubscribe from all tick data from a specific broker"""
        self.broker_subscribers[broker].discard(callback)
    
    async def get_tick_data(self, symbol: str, broker: Optional[str] = None) -> Optional[TickData]:
        """Get the most recent tick data for a symbol"""
        # Look backwards through buffer for matching tick
        for tick in reversed(self.tick_data_buffer):
            if tick.symbol == symbol and (broker is None or tick.broker == broker):
                return tick
        return None
    
    async def get_best_bid_ask(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get the best bid/ask across all brokers for a symbol"""
        best_bid = None
        best_ask = None
        best_bid_broker = None
        best_ask_broker = None
        
        for tick in reversed(self.tick_data_buffer):
            if tick.symbol == symbol:
                if best_bid is None or tick.bid > best_bid:
                    best_bid = tick.bid
                    best_bid_broker = tick.broker
                if best_ask is None or tick.ask < best_ask:
                    best_ask = tick.ask
                    best_ask_broker = tick.broker
                    
        if best_bid is not None and best_ask is not None:
            return {
                'bid': best_bid,
                'ask': best_ask,
                'bid_broker': best_bid_broker,
                'ask_broker': best_ask_broker,
                'spread': best_ask - best_bid,
                'spread_bps': ((best_ask - best_bid) / ((best_ask + best_bid) / 2)) * 10000
            }
        return None
    
    def get_metrics(self) -> RealTimeMetrics:
        """Get current real-time metrics"""
        return self.metrics
    
    def get_connection_status(self) -> Dict[str, Dict[str, Any]]:
        """Get connection status for all data sources"""
        status = {}
        for name, source in self.data_sources.items():
            status[name] = {
                'status': source.status.value,
                'last_update': source.last_update.isoformat() if source.last_update else None,
                'subscribed_symbols': list(source.subscribed_symbols),
                'error_count': source.error_count,
                'reconnect_attempts': source.reconnect_attempts,
                'metrics': source.metrics
            }
        return status
    
    def get_subscribed_symbols(self) -> Set[str]:
        """Get all currently subscribed symbols"""
        return set(self.symbol_subscribers.keys())
    
    def get_active_brokers(self) -> List[str]:
        """Get list of brokers with active connections"""
        return [name for name, source in self.data_sources.items() 
                if source.status == DataSourceStatus.CONNECTED]
    
    def add_stream(self, broker_name: str, stream) -> bool:
        """Add a WebSocket stream for a broker"""
        if broker_name in self.data_sources:
            self.logger.warning(f"Stream for {broker_name} already exists")
            return False
        
        self.data_sources[broker_name] = stream
        self.logger.info(f"Added stream for {broker_name}")
        return True
    
    def remove_stream(self, broker_name: str) -> bool:
        """Remove a WebSocket stream for a broker"""
        if broker_name not in self.data_sources:
            self.logger.warning(f"Stream for {broker_name} not found")
            return False
        
        del self.data_sources[broker_name]
        self.logger.info(f"Removed stream for {broker_name}")
        return True
    
    def subscribe(self, symbol: str, callback: Callable) -> None:
        """Subscribe a callback to symbol data updates"""
        self.symbol_subscribers[symbol].add(callback)
        self.logger.debug(f"Added subscriber for {symbol}")
    
    def unsubscribe(self, symbol: str, callback: Callable) -> None:
        """Unsubscribe a callback from symbol data updates"""
        if symbol in self.symbol_subscribers:
            self.symbol_subscribers[symbol].discard(callback)
            self.logger.debug(f"Removed subscriber for {symbol}")
    
    def route_data(self, tick_data: Any) -> None:
        """Route tick data to all subscribers"""
        # Store in buffer for metrics
        self.tick_data_buffer.append(tick_data)
        
        # Update metrics
        self.metrics.total_ticks_processed += 1
        
        # Get symbol from tick data
        symbol = getattr(tick_data, 'symbol', None)
        if not symbol:
            return
        
        # Notify symbol subscribers
        for callback in self.symbol_subscribers.get(symbol, set()):
            try:
                callback(tick_data)
            except Exception as e:
                self.logger.error(f"Error in symbol subscriber for {symbol}: {e}")
        
        # Notify broker subscribers
        broker = getattr(tick_data, 'broker', None)
        if broker:
            for callback in self.broker_subscribers.get(broker, set()):
                try:
                    callback(tick_data)
                except Exception as e:
                    self.logger.error(f"Error in broker subscriber for {broker}: {e}")
    
    @property
    def update_count(self) -> int:
        """Get total number of updates processed"""
        return self.metrics.total_ticks_processed if self.metrics else 0