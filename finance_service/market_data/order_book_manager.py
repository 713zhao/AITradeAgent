"""
Order Book Manager

Manages Level 2 order book data across multiple brokers, maintains
real-time order book state, and provides market depth analysis.

Features:
- Level 2 order book maintenance
- Real-time book updates from multiple sources
- Market depth calculation
- Liquidity analysis
- Cross-broker book aggregation
- Performance optimization
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
import bisect
import time

from .tick_data import (
    TickData, OrderBookLevel, OrderBookSnapshot, PriceLevelUpdate,
    TickEvent, TickEventType
)


@dataclass
class OrderBookSymbol:
    """Order book state for a single symbol"""
    symbol: str
    
    # Order book levels
    bid_levels: List[OrderBookLevel] = field(default_factory=list)
    ask_levels: List[OrderBookLevel] = field(default_factory=list)
    
    # Book state
    last_update: Optional[datetime] = None
    sequence_number: Optional[int] = None
    
    # Metrics
    total_bid_size: int = 0
    total_ask_size: int = 0
    best_bid: float = 0.0
    best_ask: float = 0.0
    spread: float = 0.0
    spread_bps: float = 0.0
    
    # Level counts
    bid_level_count: int = 0
    ask_level_count: int = 0
    
    # Book quality
    book_freshness: float = 1.0
    data_sources: Set[str] = field(default_factory=set)
    
    def __post_init__(self):
        """Update derived metrics after initialization"""
        self._recalculate_metrics()
    
    @property
    def bids(self) -> List[OrderBookLevel]:
        """Alias for bid_levels for test compatibility"""
        return self.bid_levels
    
    @property
    def asks(self) -> List[OrderBookLevel]:
        """Alias for ask_levels for test compatibility"""
        return self.ask_levels
    
    def _recalculate_metrics(self):
        """Recalculate all derived metrics"""
        # Sort levels by price
        self.bid_levels.sort(key=lambda x: x.price, reverse=True)
        self.ask_levels.sort(key=lambda x: x.price)
        
        # Calculate totals
        self.total_bid_size = sum(level.size for level in self.bid_levels)
        self.total_ask_size = sum(level.size for level in self.ask_levels)
        
        # Best bid/ask
        self.best_bid = max(level.price for level in self.bid_levels) if self.bid_levels else 0.0
        self.best_ask = min(level.price for level in self.ask_levels) if self.ask_levels else 0.0
        
        # Spread
        if self.best_bid > 0 and self.best_ask > 0:
            self.spread = self.best_ask - self.best_bid
            if self.best_bid > 0:
                self.spread_bps = (self.spread / self.best_bid) * 10000
                
        # Level counts
        self.bid_level_count = len(self.bid_levels)
        self.ask_level_count = len(self.ask_levels)
        
        # Update freshness
        if self.last_update:
            age = (datetime.now(timezone.utc) - self.last_update).total_seconds()
            self.book_freshness = max(0.0, 1.0 - (age / 10.0))  # Decay over 10 seconds
    
    def get_snapshot(self, broker: Optional[str] = None) -> OrderBookSnapshot:
        """Get order book snapshot"""
        # Filter by broker if specified
        bid_levels = self.bid_levels if broker is None else [l for l in self.bid_levels if l.broker == broker]
        ask_levels = self.ask_levels if broker is None else [l for l in self.ask_levels if l.broker == broker]
        
        return OrderBookSnapshot(
            symbol=self.symbol,
            timestamp=datetime.now(timezone.utc),
            broker=broker or "AGGREGATED",
            bid_levels=bid_levels,
            ask_levels=ask_levels,
            total_bid_size=self.total_bid_size,
            total_ask_size=self.total_ask_size,
            best_bid=self.best_bid,
            best_ask=self.best_ask,
            spread=self.spread,
            spread_bps=self.spread_bps,
            bid_level_count=self.bid_level_count,
            ask_level_count=self.ask_level_count,
            sequence_number=self.sequence_number,
            last_update=self.last_update
        )
    
    def get_depth_at_price(self, price: float, side: str) -> int:
        """Get cumulative depth at or better than specified price"""
        if side.upper() == 'BID':
            return sum(level.size for level in self.bid_levels if level.price >= price)
        else:
            return sum(level.size for level in self.ask_levels if level.price <= price)
    
    def get_price_for_size(self, size: int, side: str) -> Optional[float]:
        """Get price needed to execute specified size"""
        if side.upper() == 'BID':
            cumulative_size = 0
            for level in self.bid_levels:
                cumulative_size += level.size
                if cumulative_size >= size:
                    return level.price
        else:
            cumulative_size = 0
            for level in self.ask_levels:
                cumulative_size += level.size
                if cumulative_size >= size:
                    return level.price
        return None
    
    def update_level(self, level_update: PriceLevelUpdate):
        """Update a single price level"""
        try:
            # Find existing level
            levels = self.bid_levels if level_update.side.upper() == 'BID' else self.ask_levels
            
            # Remove existing level at this price
            levels[:] = [l for l in levels if l.price != level_update.price]
            
            # Add new level if size > 0
            if level_update.size > 0:
                new_level = OrderBookLevel(
                    price=level_update.price,
                    size=level_update.size,
                    side=level_update.side.upper(),
                    timestamp=level_update.timestamp,
                    broker=level_update.broker,
                    exchange=None
                )
                
                # Insert in sorted order
                if level_update.side.upper() == 'BID':
                    bisect.insort(levels, new_level, key=lambda x: x.price)
                else:
                    bisect.insort(levels, new_level, key=lambda x: x.price)
            
            # Update metadata
            self.last_update = level_update.timestamp
            if level_update.sequence_number:
                self.sequence_number = level_update.sequence_number
            
            # Track data sources
            self.data_sources.add(level_update.broker)
            
            # Recalculate metrics
            self._recalculate_metrics()
            
        except Exception as e:
            logging.error(f"Error updating level for {self.symbol}: {e}")


@dataclass
class OrderBookConfig:
    """Configuration for order book manager"""
    max_symbols: int = 1000
    max_levels_per_side: int = 20
    update_threshold: float = 0.01  # 1% price change threshold
    snapshot_interval: int = 60  # seconds
    cleanup_interval: int = 300  # seconds
    max_book_age: int = 60  # seconds before cleanup


class OrderBookManager:
    """
    Manages Level 2 order book data across multiple brokers.
    
    Maintains real-time order book state, provides market depth analysis,
    and supports cross-broker book aggregation.
    """
    
    def __init__(self, config: Dict[str, Any], event_manager):
        self.config = config
        self.event_manager = event_manager
        
        # Order book configuration
        book_config = config.get('order_book', {})
        self.book_config = OrderBookConfig(
            max_symbols=book_config.get('max_symbols', 1000),
            max_levels_per_side=book_config.get('max_levels_per_side', 20),
            update_threshold=book_config.get('update_threshold', 0.01),
            snapshot_interval=book_config.get('snapshot_interval', 60),
            cleanup_interval=book_config.get('cleanup_interval', 300),
            max_book_age=book_config.get('max_book_age', 60)
        )
        
        # Order book state
        self.symbol_books: Dict[str, OrderBookSymbol] = {}
        self.subscription_count: Dict[str, int] = defaultdict(int)
        
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
        """Start the order book manager"""
        if self.running:
            return
            
        self.running = True
        self.logger.info("Starting Order Book Manager")
        
        # Start background tasks
        self._tasks.append(asyncio.create_task(self._cleanup_task()))
        self._tasks.append(asyncio.create_task(self._metrics_task()))
        
        self.logger.info("Order Book Manager started")
    
    async def stop(self):
        """Stop the order book manager"""
        if not self.running:
            return
            
        self.running = False
        self.logger.info("Stopping Order Book Manager")
        
        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
                
        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            
        self.logger.info("Order Book Manager stopped")
    
    async def subscribe_symbol(self, symbol: str):
        """Subscribe to order book updates for a symbol"""
        if symbol not in self.symbol_books:
            self.symbol_books[symbol] = OrderBookSymbol(symbol=symbol)
            
        self.subscription_count[symbol] += 1
        self.logger.info(f"Subscribed to order book for {symbol} (count: {self.subscription_count[symbol]})")
    
    async def unsubscribe_symbol(self, symbol: str):
        """Unsubscribe from order book updates for a symbol"""
        if self.subscription_count[symbol] > 0:
            self.subscription_count[symbol] -= 1
            
        if self.subscription_count[symbol] == 0 and symbol in self.symbol_books:
            # Remove the book if no more subscribers
            del self.symbol_books[symbol]
            del self.subscription_count[symbol]
            
            self.logger.info(f"Unsubscribed from order book for {symbol}")
    
    async def update_order_book(self, level_update: PriceLevelUpdate):
        """Update order book with a price level change"""
        start_time = time.time()
        
        try:
            # Get or create symbol book
            symbol_book = self.symbol_books.get(level_update.symbol)
            if not symbol_book:
                # Only update if we have subscribers
                if level_update.symbol in self.subscription_count:
                    symbol_book = OrderBookSymbol(symbol=level_update.symbol)
                    self.symbol_books[level_update.symbol] = symbol_book
                else:
                    return  # No subscribers, ignore update
            
            # Update the level
            symbol_book.update_level(level_update)
            
            # Update metrics
            self.update_count += 1
            processing_time = (time.time() - start_time) * 1000  # Convert to ms
            self.processing_latency_ms.append(processing_time)
            
            # Publish update event
            event = TickEvent(
                event_type=TickEventType.ORDER_BOOK_UPDATE,
                symbol=level_update.symbol,
                broker=level_update.broker,
                timestamp=level_update.timestamp,
                data={
                    'level_update': level_update.to_dict(),
                    'book_snapshot': symbol_book.get_snapshot().to_dict()
                }
            )
            
            if self.event_manager:
                await self.event_manager.publish('order_book_update', event.to_dict())
                
        except Exception as e:
            self.logger.error(f"Error updating order book for {level_update.symbol}: {e}")
    
    async def get_order_book(self, symbol: str, broker: Optional[str] = None) -> Optional[OrderBookSnapshot]:
        """Get current order book snapshot for a symbol"""
        symbol_book = self.symbol_books.get(symbol)
        if not symbol_book:
            return None
            
        return symbol_book.get_snapshot(broker)
    
    async def get_aggregated_order_book(self, symbol: str) -> OrderBookSnapshot:
        """Get aggregated order book across all brokers"""
        symbol_book = self.symbol_books.get(symbol)
        if not symbol_book:
            return OrderBookSnapshot(symbol=symbol, timestamp=datetime.now(timezone.utc), broker="NONE")
            
        # Aggregate levels from all brokers
        bid_levels = []
        ask_levels = []
        
        # Group by price level across brokers
        price_levels = defaultdict(lambda: {'bid_size': 0, 'ask_size': 0, 'brokers': set()})
        
        for level in symbol_book.bid_levels:
            price_levels[level.price]['bid_size'] += level.size
            price_levels[level.price]['brokers'].add(level.broker)
            
        for level in symbol_book.ask_levels:
            price_levels[level.price]['ask_size'] += level.size
            price_levels[level.price]['brokers'].add(level.broker)
        
        # Create aggregated levels
        for price, data in price_levels.items():
            if data['bid_size'] > 0:
                bid_levels.append(OrderBookLevel(
                    price=price,
                    size=data['bid_size'],
                    side='BID',
                    timestamp=datetime.now(timezone.utc),
                    broker='AGGREGATED',
                    exchange=None
                ))
                
            if data['ask_size'] > 0:
                ask_levels.append(OrderBookLevel(
                    price=price,
                    size=data['ask_size'],
                    side='ASK',
                    timestamp=datetime.now(timezone.utc),
                    broker='AGGREGATED',
                    exchange=None
                ))
        
        # Sort and limit levels
        bid_levels.sort(key=lambda x: x.price, reverse=True)
        ask_levels.sort(key=lambda x: x.price)
        
        bid_levels = bid_levels[:self.book_config.max_levels_per_side]
        ask_levels = ask_levels[:self.book_config.max_levels_per_side]
        
        # Create aggregated book
        aggregated_book = OrderBookSymbol(symbol=symbol)
        aggregated_book.bid_levels = bid_levels
        aggregated_book.ask_levels = ask_levels
        aggregated_book._recalculate_metrics()
        
        return aggregated_book.get_snapshot(broker="AGGREGATED")
    
    async def get_market_depth(self, symbol: str, price_levels: List[float]) -> Dict[str, Any]:
        """Get market depth at specified price levels"""
        symbol_book = self.symbol_books.get(symbol)
        if not symbol_book:
            return {}
        
        depth_analysis = {}
        
        for price in price_levels:
            # Bid depth at this price
            bid_depth = symbol_book.get_depth_at_price(price, 'BID')
            
            # Ask depth at this price
            ask_depth = symbol_book.get_depth_at_price(price, 'ASK')
            
            # Price needed for certain sizes
            price_for_1000 = symbol_book.get_price_for_size(1000, 'ASK')
            price_for_10000 = symbol_book.get_price_for_size(10000, 'ASK')
            
            depth_analysis[f"${price}"] = {
                'bid_depth': bid_depth,
                'ask_depth': ask_depth,
                'price_for_1000_shares': price_for_1000,
                'price_for_10000_shares': price_for_10000,
                'total_bid_size': symbol_book.total_bid_size,
                'total_ask_size': symbol_book.total_ask_size,
                'best_bid': symbol_book.best_bid,
                'best_ask': symbol_book.best_ask,
                'spread': symbol_book.spread,
                'spread_bps': symbol_book.spread_bps
            }
        
        return depth_analysis
    
    async def _cleanup_task(self):
        """Background task to cleanup old order book data"""
        while self.running:
            try:
                current_time = datetime.now(timezone.utc)
                
                # Remove old books
                symbols_to_remove = []
                for symbol, book in self.symbol_books.items():
                    if (book.last_update and 
                        (current_time - book.last_update).total_seconds() > self.book_config.max_book_age and
                        self.subscription_count[symbol] == 0):
                        symbols_to_remove.append(symbol)
                
                for symbol in symbols_to_remove:
                    del self.symbol_books[symbol]
                    del self.subscription_count[symbol]
                    self.logger.debug(f"Cleaned up order book for {symbol}")
                
                await asyncio.sleep(self.book_config.cleanup_interval)
                
            except Exception as e:
                self.logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(60)
    
    async def _metrics_task(self):
        """Background task to track metrics"""
        while self.running:
            try:
                # Update metrics every 5 seconds
                await asyncio.sleep(5)
                
                # Log periodic metrics
                if self.update_count > 0:
                    avg_latency = sum(self.processing_latency_ms) / len(self.processing_latency_ms) if self.processing_latency_ms else 0
                    
                    self.logger.info(
                        f"Order Book Metrics: {len(self.symbol_books)} symbols, "
                        f"{self.update_count} updates, "
                        f"{avg_latency:.2f}ms avg latency"
                    )
                    
                    self.update_count = 0
                
            except Exception as e:
                self.logger.error(f"Error in metrics task: {e}")
                await asyncio.sleep(10)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get order book manager metrics"""
        avg_latency = sum(self.processing_latency_ms) / len(self.processing_latency_ms) if self.processing_latency_ms else 0
        
        return {
            'active_symbols': len(self.symbol_books),
            'total_subscriptions': sum(self.subscription_count.values()),
            'average_latency_ms': avg_latency,
            'updates_processed': self.update_count,
            'last_update_time': self.last_update_time,
            'active_brokers': set(),
            'book_freshness': 1.0
        }
    
    def get_symbols(self) -> List[str]:
        """Get list of active symbols"""
        return list(self.symbol_books.keys())
    
    def get_book_quality(self, symbol: str) -> Dict[str, Any]:
        """Get order book quality metrics for a symbol"""
        symbol_book = self.symbol_books.get(symbol)
        if not symbol_book:
            return {}
        
        return {
            'book_freshness': symbol_book.book_freshness,
            'data_sources_count': len(symbol_book.data_sources),
            'bid_levels': symbol_book.bid_level_count,
            'ask_levels': symbol_book.ask_level_count,
            'total_bid_size': symbol_book.total_bid_size,
            'total_ask_size': symbol_book.total_ask_size,
            'spread_bps': symbol_book.spread_bps,
            'best_bid': symbol_book.best_bid,
            'best_ask': symbol_book.best_ask,
            'last_update': symbol_book.last_update.isoformat() if symbol_book.last_update else None
        }
    
    @property
    def books(self) -> Dict[str, Any]:
        """Alias for symbol_books for test compatibility"""
        return self.symbol_books
    
    def add_order_book(self, symbol: str) -> bool:
        """Add an order book for a symbol"""
        if symbol in self.symbol_books:
            self.logger.warning(f"Order book for {symbol} already exists")
            return False
        
        self.symbol_books[symbol] = OrderBookSymbol(symbol=symbol)
        self.logger.debug(f"Added order book for {symbol}")
        return True
    
    def update_bid_level(self, symbol: str, price: float, size: int, broker: str) -> None:
        """Update a bid level in the order book"""
        if symbol not in self.symbol_books:
            self.add_order_book(symbol)
        
        book = self.symbol_books[symbol]
        
        # Create new level
        level = OrderBookLevel(
            price=price,
            size=size,
            side='BID',
            timestamp=datetime.now(timezone.utc),
            broker=broker
        )
        
        # Find position in bid levels (sorted descending by price)
        position = None
        for i, existing_level in enumerate(book.bid_levels):
            if existing_level.price < price:
                position = i
                break
            elif existing_level.price == price and existing_level.broker == broker:
                # Update existing level
                book.bid_levels[i] = level
                return
        
        if position is None:
            book.bid_levels.append(level)
        else:
            book.bid_levels.insert(position, level)
        
        # Keep only max_levels_per_side
        if len(book.bid_levels) > self.book_config.max_levels_per_side:
            book.bid_levels = book.bid_levels[:self.book_config.max_levels_per_side]
        
        self.update_count += 1
    
    def update_ask_level(self, symbol: str, price: float, size: int, broker: str) -> None:
        """Update an ask level in the order book"""
        if symbol not in self.symbol_books:
            self.add_order_book(symbol)
        
        book = self.symbol_books[symbol]
        
        # Create new level
        level = OrderBookLevel(
            price=price,
            size=size,
            side='ASK',
            timestamp=datetime.now(timezone.utc),
            broker=broker
        )
        
        # Find position in ask levels (sorted ascending by price)
        position = None
        for i, existing_level in enumerate(book.ask_levels):
            if existing_level.price > price:
                position = i
                break
            elif existing_level.price == price and existing_level.broker == broker:
                # Update existing level
                book.ask_levels[i] = level
                return
        
        if position is None:
            book.ask_levels.append(level)
        else:
            book.ask_levels.insert(position, level)
        
        # Keep only max_levels_per_side
        if len(book.ask_levels) > self.book_config.max_levels_per_side:
            book.ask_levels = book.ask_levels[:self.book_config.max_levels_per_side]
        
        self.update_count += 1
    
    def get_order_book(self, symbol: str) -> OrderBookSymbol:
        """Get the order book for a symbol"""
        return self.symbol_books.get(symbol)
    
    def get_best_bid_ask(self, symbol: str) -> Tuple[Optional[OrderBookLevel], Optional[OrderBookLevel]]:
        """Get the best bid and ask levels"""
        book = self.symbol_books.get(symbol)
        if not book:
            return None, None
        
        best_bid = book.bid_levels[0] if book.bid_levels else None
        best_ask = book.ask_levels[0] if book.ask_levels else None
        
        return best_bid, best_ask
    
    def get_market_depth(self, symbol: str) -> Dict[str, Any]:
        """Get market depth analysis"""
        book = self.symbol_books.get(symbol)
        if not book:
            return {}
        
        bid_depth = sum(level.size for level in book.bid_levels)
        ask_depth = sum(level.size for level in book.ask_levels)
        
        spread = 0.0
        if book.bid_levels and book.ask_levels:
            spread = book.ask_levels[0].price - book.bid_levels[0].price
        
        return {
            'symbol': symbol,
            'bid_depth': bid_depth,
            'ask_depth': ask_depth,
            'total_volume': bid_depth + ask_depth,
            'spread': spread,
            'bid_levels_count': len(book.bid_levels),
            'ask_levels_count': len(book.ask_levels),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def get_liquidity(self, symbol: str) -> Dict[str, Any]:
        """Get liquidity metrics"""
        depth = self.get_market_depth(symbol)
        
        return {
            'symbol': symbol,
            'total_liquidity': depth.get('total_volume', 0),
            'bid_liquidity': depth.get('bid_depth', 0),
            'ask_liquidity': depth.get('ask_depth', 0),
            'spread': depth.get('spread', 0),
            'bid_level_count': len(self.symbol_books.get(symbol, OrderBookSymbol(symbol=symbol)).bid_levels),
            'ask_level_count': len(self.symbol_books.get(symbol, OrderBookSymbol(symbol=symbol)).ask_levels)
        }
    
    def calculate_liquidity(self, symbol: str) -> Dict[str, Any]:
        """Calculate liquidity score and metrics"""
        book = self.symbol_books.get(symbol)
        if not book:
            return {
                'liquidity_score': 0.0,
                'bid_liquidity': 0,
                'ask_liquidity': 0,
                'spread': 0.0,
                'bid_level_count': 0,
                'ask_level_count': 0
            }
        
        bid_liquidity = sum(level.size for level in book.bid_levels)
        ask_liquidity = sum(level.size for level in book.ask_levels)
        total_liquidity = bid_liquidity + ask_liquidity
        
        # Calculate liquidity score (0.0 to 1.0)
        # Based on total volume and spread
        spread_penalty = min(book.spread / (book.best_bid + 0.01), 0.5)  # Max 0.5 penalty
        liquidity_score = min(1.0, total_liquidity / 100000.0) * max(0.0, 1.0 - spread_penalty)
        
        return {
            'liquidity_score': liquidity_score,
            'bid_liquidity': bid_liquidity,
            'ask_liquidity': ask_liquidity,
            'spread': book.spread,
            'bid_level_count': len(book.bid_levels),
            'ask_level_count': len(book.ask_levels),
            'total_liquidity': total_liquidity,
            'best_bid': book.best_bid,
            'best_ask': book.best_ask
        }