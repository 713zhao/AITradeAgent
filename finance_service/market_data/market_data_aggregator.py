"""
Market Data Aggregator

Aggregates market data across multiple brokers, performs price discovery,
and provides consolidated real-time market data.

Features:
- Cross-broker data aggregation
- Best bid/ask discovery
- Price consolidation and validation
- Data quality scoring
- Real-time price updates
- Market data caching
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Any, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
import statistics
import time

from .tick_data import TickData, TickEvent, TickEventType, OrderBookLevel
from .real_time_data_manager import RealTimeDataManager


@dataclass
class AggregatedPrice:
    """Aggregated price data from multiple sources"""
    symbol: str
    timestamp: datetime
    broker_count: int
    
    # Price levels
    best_bid: float
    best_ask: float
    bid_brokers: Set[str]
    ask_brokers: Set[str]
    
    # Aggregated bid/ask sizes
    aggregated_bid_size: int
    aggregated_ask_size: int
    
    # Price statistics
    bid_prices: List[float] = field(default_factory=list)
    ask_prices: List[float] = field(default_factory=list)
    
    # Volume metrics
    total_volume: int = 0
    
    # Quality metrics
    price_consistency: float = 1.0
    data_freshness: float = 1.0
    broker_diversity: float = 1.0
    
    def get_spread(self) -> float:
        """Get aggregated bid-ask spread"""
        return self.best_ask - self.best_bid
    
    def get_spread_bps(self) -> float:
        """Get spread in basis points"""
        if self.best_bid == 0:
            return 0.0
        return ((self.best_ask - self.best_bid) / self.best_bid) * 10000
    
    def get_price_disagreement(self) -> float:
        """Get price disagreement between brokers (0-1 scale)"""
        if len(self.bid_prices) <= 1:
            return 0.0
        
        # Calculate coefficient of variation
        if self.bid_prices:
            bid_cv = statistics.stdev(self.bid_prices) / statistics.mean(self.bid_prices) if statistics.mean(self.bid_prices) > 0 else 0
        else:
            bid_cv = 0
            
        if self.ask_prices:
            ask_cv = statistics.stdev(self.ask_prices) / statistics.mean(self.ask_prices) if statistics.mean(self.ask_prices) > 0 else 0
        else:
            ask_cv = 0
        
        return max(bid_cv, ask_cv)
    
    def update_quality_metrics(self):
        """Update data quality metrics"""
        # Price consistency (inverse of disagreement)
        self.price_consistency = 1.0 - self.get_price_disagreement()
        
        # Broker diversity (normalized by max expected brokers)
        self.broker_diversity = min(1.0, self.broker_count / 6.0)  # 6 brokers max
        
        # Data freshness (1 if recent, 0 if stale)
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        self.data_freshness = max(0.0, 1.0 - (age / 5.0))  # Decay over 5 seconds


@dataclass
class AggregationConfig:
    """Configuration for market data aggregation"""
    update_interval: float = 0.1  # 100ms
    price_freshness: float = 5.0  # 5 seconds
    min_broker_count: int = 1
    max_broker_count: int = 6
    price_tolerance: float = 0.001  # 0.1% price tolerance
    aggregation_method: str = "WEIGHTED"  # "WEIGHTED", "SIMPLE", "BEST"


class MarketDataAggregator:
    """
    Aggregates market data across multiple brokers.
    
    Collects real-time data from multiple sources, performs price discovery,
    and provides consolidated market data to the trading system.
    """
    
    def __init__(self, config: Dict[str, Any], real_time_manager: RealTimeDataManager, event_manager):
        self.config = config
        self.real_time_manager = real_time_manager
        self.event_manager = event_manager
        
        # Aggregation configuration
        agg_config = config.get('aggregation', {})
        self.agg_config = AggregationConfig(
            update_interval=agg_config.get('update_interval', 0.1),
            price_freshness=agg_config.get('price_freshness', 5.0),
            min_broker_count=agg_config.get('min_broker_count', 1),
            max_broker_count=agg_config.get('max_broker_count', 6),
            price_tolerance=agg_config.get('price_tolerance', 0.001),
            aggregation_method=agg_config.get('aggregation_method', 'WEIGHTED')
        )
        
        # Data sources registry
        self.data_sources: Dict[str, Any] = {}
        
        # Aggregated data storage
        self.aggregated_prices: Dict[str, AggregatedPrice] = {}
        self.tick_buffer: deque = deque(maxlen=10000)
        
        # Subscription management
        self.subscribed_symbols: Set[str] = set()
        self.symbol_subscribers: Dict[str, Set[Callable]] = defaultdict(set)
        
        # Performance tracking
        self.update_count = 0
        self.last_update_time = time.time()
        self.processing_latency_ms = deque(maxlen=1000)
        
        # Control flags
        self.running = False
        self._tasks: List[asyncio.Task] = []
        
        # Logging
        self.logger = logging.getLogger(__name__)
        
    async def start(self):
        """Start the market data aggregator"""
        if self.running:
            return
            
        self.running = True
        self.logger.info("Starting Market Data Aggregator")
        
        # Subscribe to real-time data manager for tick data
        await self.real_time_manager.subscribe_broker('all', self._handle_tick_data)
        
        # Start background tasks
        self._tasks.append(asyncio.create_task(self._aggregation_task()))
        self._tasks.append(asyncio.create_task(self._cleanup_task()))
        self._tasks.append(asyncio.create_task(self._metrics_task()))
        
        self.logger.info("Market Data Aggregator started")
    
    async def stop(self):
        """Stop the market data aggregator"""
        if not self.running:
            return
            
        self.running = False
        self.logger.info("Stopping Market Data Aggregator")
        
        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
                
        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            
        self.logger.info("Market Data Aggregator stopped")
    
    async def subscribe_symbol(self, symbol: str, callback: Optional[Callable[[AggregatedPrice], None]] = None):
        """Subscribe to aggregated data for a symbol"""
        if symbol not in self.subscribed_symbols:
            self.subscribed_symbols.add(symbol)
            await self.real_time_manager.subscribe_symbol(symbol, self._handle_tick_data)
            
            self.logger.info(f"Subscribed to aggregated data for {symbol}")
        
        if callback:
            self.symbol_subscribers[symbol].add(callback)
    
    async def unsubscribe_symbol(self, symbol: str, callback: Optional[Callable] = None):
        """Unsubscribe from aggregated data for a symbol"""
        if callback:
            self.symbol_subscribers[symbol].discard(callback)
        
        if not self.symbol_subscribers[symbol] and symbol in self.subscribed_symbols:
            self.subscribed_symbols.remove(symbol)
            await self.real_time_manager.unsubscribe_symbol(symbol, self._handle_tick_data)
            
            self.logger.info(f"Unsubscribed from aggregated data for {symbol}")
    
    async def _handle_tick_data(self, tick_data: TickData):
        """Handle incoming tick data from real-time manager"""
        try:
            # Add to buffer
            self.tick_buffer.append(tick_data)
            
            # Update aggregated price
            await self._update_aggregated_price(tick_data)
            
        except Exception as e:
            self.logger.error(f"Error handling tick data: {e}")
    
    async def _update_aggregated_price(self, tick_data: TickData):
        """Update aggregated price for a symbol"""
        try:
            symbol = tick_data.symbol
            
            # Get or create aggregated price
            if symbol not in self.aggregated_prices:
                self.aggregated_prices[symbol] = AggregatedPrice(
                    symbol=symbol,
                    timestamp=datetime.now(timezone.utc),
                    broker_count=0,
                    best_bid=0.0,
                    best_ask=float('inf'),
                    bid_brokers=set(),
                    ask_brokers=set(),
                    aggregated_bid_size=0,
                    aggregated_ask_size=0,
                    bid_prices=[],
                    ask_prices=[]
                )
            
            aggregated = self.aggregated_prices[symbol]
            
            # Update based on aggregation method
            if self.agg_config.aggregation_method == "WEIGHTED":
                await self._update_weighted_aggregation(aggregated, tick_data)
            elif self.agg_config.aggregation_method == "BEST":
                await self._update_best_price_aggregation(aggregated, tick_data)
            else:
                await self._update_simple_aggregation(aggregated, tick_data)
            
            # Update quality metrics
            aggregated.timestamp = datetime.now(timezone.utc)
            aggregated.update_quality_metrics()
            
            # Notify subscribers
            await self._notify_symbol_subscribers(symbol, aggregated)
            
        except Exception as e:
            self.logger.error(f"Error updating aggregated price for {tick_data.symbol}: {e}")
    
    async def _update_weighted_aggregation(self, aggregated: AggregatedPrice, tick_data: TickData):
        """Update aggregated price using weighted method"""
        # Weight by data freshness and broker reliability
        weight = 1.0  # Could be based on data freshness, broker quality, etc.
        
        # Update bid prices
        if tick_data.bid > 0:
            # Remove old price from this broker if exists
            aggregated.bid_prices = [p for p in aggregated.bid_prices if p not in aggregated.bid_prices or 
                                   aggregated.bid_prices.index(p) != list(aggregated.bid_prices).index(tick_data.bid)]
            
            # Add new price
            aggregated.bid_prices.append(tick_data.bid)
            aggregated.bid_brokers.add(tick_data.broker)
            aggregated.aggregated_bid_size += tick_data.bid_size
            
            # Keep only most recent data
            if len(aggregated.bid_prices) > self.agg_config.max_broker_count:
                aggregated.bid_prices.pop(0)
        
        # Update ask prices
        if tick_data.ask > 0:
            # Remove old price from this broker if exists
            aggregated.ask_prices = [p for p in aggregated.ask_prices if p not in aggregated.ask_prices or 
                                   aggregated.ask_prices.index(p) != list(aggregated.ask_prices).index(tick_data.ask)]
            
            # Add new price
            aggregated.ask_prices.append(tick_data.ask)
            aggregated.ask_brokers.add(tick_data.broker)
            aggregated.aggregated_ask_size += tick_data.ask_size
            
            # Keep only most recent data
            if len(aggregated.ask_prices) > self.agg_config.max_broker_count:
                aggregated.ask_prices.pop(0)
        
        # Calculate best bid/ask
        if aggregated.bid_prices:
            aggregated.best_bid = max(aggregated.bid_prices)
        if aggregated.ask_prices:
            aggregated.best_ask = min(aggregated.ask_prices)
        
        # Update broker count
        aggregated.broker_count = len(aggregated.bid_brokers.union(aggregated.ask_brokers))
    
    async def _update_best_price_aggregation(self, aggregated: AggregatedPrice, tick_data: TickData):
        """Update aggregated price using best price method"""
        # Only use the best prices, ignore others
        if tick_data.bid > aggregated.best_bid:
            aggregated.best_bid = tick_data.bid
            aggregated.bid_brokers = {tick_data.broker}
            aggregated.aggregated_bid_size = tick_data.bid_size
        
        if tick_data.ask < aggregated.best_ask:
            aggregated.best_ask = tick_data.ask
            aggregated.ask_brokers = {tick_data.broker}
            aggregated.aggregated_ask_size = tick_data.ask_size
        
        # Update broker count
        aggregated.broker_count = len(aggregated.bid_brokers.union(aggregated.ask_brokers))
    
    async def _update_simple_aggregation(self, aggregated: AggregatedPrice, tick_data: TickData):
        """Update aggregated price using simple average method"""
        # Simple price tracking per broker
        if tick_data.bid > 0:
            aggregated.bid_prices.append(tick_data.bid)
            aggregated.bid_brokers.add(tick_data.broker)
            aggregated.aggregated_bid_size += tick_data.bid_size
        
        if tick_data.ask > 0:
            aggregated.ask_prices.append(tick_data.ask)
            aggregated.ask_brokers.add(tick_data.broker)
            aggregated.aggregated_ask_size += tick_data.ask_size
        
        # Calculate simple averages
        if aggregated.bid_prices:
            aggregated.best_bid = statistics.mean(aggregated.bid_prices)
        if aggregated.ask_prices:
            aggregated.best_ask = statistics.mean(aggregated.ask_prices)
        
        # Update broker count
        aggregated.broker_count = len(aggregated.bid_brokers.union(aggregated.ask_brokers))
    
    async def _notify_symbol_subscribers(self, symbol: str, aggregated: AggregatedPrice):
        """Notify all subscribers for a symbol"""
        for callback in self.symbol_subscribers[symbol]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(aggregated)
                else:
                    callback(aggregated)
            except Exception as e:
                self.logger.error(f"Error notifying subscriber for {symbol}: {e}")
    
    async def _aggregation_task(self):
        """Background task for data aggregation"""
        while self.running:
            try:
                start_time = time.time()
                
                # Clean up stale data
                cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=self.agg_config.price_freshness)
                
                symbols_to_remove = []
                for symbol, aggregated in self.aggregated_prices.items():
                    if aggregated.timestamp < cutoff_time and symbol not in self.subscribed_symbols:
                        symbols_to_remove.append(symbol)
                
                for symbol in symbols_to_remove:
                    del self.aggregated_prices[symbol]
                
                # Update metrics
                processing_time = (time.time() - start_time) * 1000
                self.processing_latency_ms.append(processing_time)
                self.update_count += 1
                
                await asyncio.sleep(self.agg_config.update_interval)
                
            except Exception as e:
                self.logger.error(f"Error in aggregation task: {e}")
                await asyncio.sleep(1)
    
    async def _cleanup_task(self):
        """Background task to cleanup old data"""
        while self.running:
            try:
                # Cleanup every 30 seconds
                await asyncio.sleep(30)
                
                # Remove old entries from tick buffer
                cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=60)
                
                while self.tick_buffer and self.tick_buffer[0].timestamp < cutoff_time:
                    self.tick_buffer.popleft()
                
            except Exception as e:
                self.logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(60)
    
    async def _metrics_task(self):
        """Background task to track metrics"""
        while self.running:
            try:
                # Update metrics every 10 seconds
                await asyncio.sleep(10)
                
                # Log periodic metrics
                if self.update_count > 0:
                    avg_latency = sum(self.processing_latency_ms) / len(self.processing_latency_ms) if self.processing_latency_ms else 0
                    
                    self.logger.info(
                        f"Aggregator Metrics: {len(self.aggregated_prices)} symbols, "
                        f"{self.update_count} updates, "
                        f"{avg_latency:.2f}ms avg latency"
                    )
                    
                    self.update_count = 0
                
            except Exception as e:
                self.logger.error(f"Error in metrics task: {e}")
                await asyncio.sleep(20)
    
    # Public API methods
    
    async def get_aggregated_price(self, symbol: str) -> Optional[AggregatedPrice]:
        """Get current aggregated price for a symbol"""
        return self.aggregated_prices.get(symbol)
    
    async def get_best_bid_ask(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get best bid/ask across all brokers"""
        aggregated = self.aggregated_prices.get(symbol)
        if not aggregated:
            return None
        
        return {
            'symbol': symbol,
            'best_bid': aggregated.best_bid,
            'best_ask': aggregated.best_ask,
            'bid_brokers': list(aggregated.bid_brokers),
            'ask_brokers': list(aggregated.ask_brokers),
            'spread': aggregated.get_spread(),
            'spread_bps': aggregated.get_spread_bps(),
            'broker_count': aggregated.broker_count,
            'price_consistency': aggregated.price_consistency,
            'data_freshness': aggregated.data_freshness,
            'timestamp': aggregated.timestamp.isoformat()
        }
    
    async def get_symbol_list(self) -> List[str]:
        """Get list of symbols with aggregated data"""
        return list(self.aggregated_prices.keys())
    
    async def get_aggregated_data_summary(self) -> Dict[str, Any]:
        """Get summary of all aggregated data"""
        summary = {
            'total_symbols': len(self.aggregated_prices),
            'total_brokers': 0,
            'average_spread_bps': 0.0,
            'data_freshness_score': 0.0,
            'symbols': []
        }
        
        if self.aggregated_prices:
            total_spread_bps = 0
            total_freshness = 0
            all_brokers = set()
            
            for symbol, aggregated in self.aggregated_prices.items():
                total_spread_bps += aggregated.get_spread_bps()
                total_freshness += aggregated.data_freshness
                all_brokers.update(aggregated.bid_brokers.union(aggregated.ask_brokers))
                
                summary['symbols'].append({
                    'symbol': symbol,
                    'best_bid': aggregated.best_bid,
                    'best_ask': aggregated.best_ask,
                    'spread_bps': aggregated.get_spread_bps(),
                    'broker_count': aggregated.broker_count,
                    'data_freshness': aggregated.data_freshness
                })
            
            summary['total_brokers'] = len(all_brokers)
            summary['average_spread_bps'] = total_spread_bps / len(self.aggregated_prices)
            summary['data_freshness_score'] = total_freshness / len(self.aggregated_prices)
        
        return summary
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get aggregator performance metrics"""
        avg_latency = sum(self.processing_latency_ms) / len(self.processing_latency_ms) if self.processing_latency_ms else 0
        
        return {
            'active_symbols': len(self.aggregated_prices),
            'subscribed_symbols': len(self.subscribed_symbols),
            'average_latency_ms': avg_latency,
            'updates_processed': self.update_count,
            'last_update_time': self.last_update_time,
            'buffer_size': len(self.tick_buffer),
            'aggregation_method': self.agg_config.aggregation_method
        }
    
    def register_data_source(self, source_name: str, source: Any) -> bool:
        """Register a data source with the aggregator"""
        if source_name in self.data_sources:
            self.logger.warning(f"Data source {source_name} already registered")
            return False
        
        self.data_sources[source_name] = source
        self.logger.info(f"Registered data source: {source_name}")
        return True
    
    def aggregate_tick_data(self, symbol: str, ticks: List[Any]) -> AggregatedPrice:
        """Aggregate tick data from multiple sources"""
        if not ticks:
            return None
        
        # Calculate aggregated metrics
        bids = [tick.bid for tick in ticks if hasattr(tick, 'bid') and tick.bid]
        asks = [tick.ask for tick in ticks if hasattr(tick, 'ask') and tick.ask]
        bid_sizes = [tick.bid_size for tick in ticks if hasattr(tick, 'bid_size')]
        ask_sizes = [tick.ask_size for tick in ticks if hasattr(tick, 'ask_size')]
        volumes = [tick.volume for tick in ticks if hasattr(tick, 'volume')]
        
        best_bid = max(bids) if bids else 0.0
        best_ask = min(asks) if asks else 0.0
        total_volume = sum(volumes) if volumes else 0
        total_bid_size = sum(bid_sizes) if bid_sizes else 0
        total_ask_size = sum(ask_sizes) if ask_sizes else 0
        
        # Get brokers for each side
        bid_brokers = set()
        ask_brokers = set()
        for tick in ticks:
            if hasattr(tick, 'broker') and hasattr(tick, 'bid') and tick.bid:
                bid_brokers.add(tick.broker)
            if hasattr(tick, 'broker') and hasattr(tick, 'ask') and tick.ask:
                ask_brokers.add(tick.broker)
        
        broker_count = len(set(tick.broker for tick in ticks if hasattr(tick, 'broker')))
        
        # Create aggregated price
        agg_price = AggregatedPrice(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            broker_count=broker_count,
            best_bid=best_bid,
            best_ask=best_ask,
            bid_brokers=bid_brokers,
            ask_brokers=ask_brokers,
            aggregated_bid_size=total_bid_size,
            aggregated_ask_size=total_ask_size,
            bid_prices=bids,
            ask_prices=asks,
            total_volume=total_volume,
            price_consistency=1.0,
            data_freshness=1.0,
            broker_diversity=min(1.0, broker_count / 6.0)
        )
        
        self.update_count += 1
        return agg_price
    
    def discover_best_prices(self, symbol: str, price_data: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Discover best prices across venues"""
        best_bid = None
        best_bid_price = -1.0
        best_ask = None
        best_ask_price = float('inf')
        all_prices = []
        
        for source, data in price_data.items():
            if isinstance(data, dict):
                bid_price = data.get('bid', 0.0)
                ask_price = data.get('ask', 0.0)
                
                if bid_price > best_bid_price:
                    best_bid_price = bid_price
                    best_bid = {'source': source, 'price': bid_price, 'timestamp': data.get('timestamp')}
                
                if ask_price < best_ask_price and ask_price > 0:
                    best_ask_price = ask_price
                    best_ask = {'source': source, 'price': ask_price, 'timestamp': data.get('timestamp')}
                
                all_prices.append({
                    'source': source,
                    'bid': bid_price,
                    'ask': ask_price,
                    'timestamp': data.get('timestamp')
                })
        
        return {
            'symbol': symbol,
            'best_bid': best_bid,
            'best_ask': best_ask,
            'all_prices': all_prices,
            'discovery_time': datetime.now(timezone.utc).isoformat()
        }
    
    def is_data_fresh(self, tick: Any, max_age_seconds: float = 5.0) -> bool:
        """Check if tick data is fresh"""
        if not hasattr(tick, 'timestamp'):
            return False
        
        if not tick.timestamp:
            return False
        
        # Handle both naive and aware datetimes
        tick_time = tick.timestamp
        if tick_time.tzinfo is None:
            # Naive datetime - use naive now
            current_time = datetime.now()
        else:
            # Aware datetime - use aware now
            current_time = datetime.now(timezone.utc)
        
        age = (current_time - tick_time).total_seconds()
        is_fresh = age <= max_age_seconds
        
        return is_fresh