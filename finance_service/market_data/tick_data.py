"""
Tick Data Structures and Events

Defines the core data structures for real-time market data including
tick data, order book levels, and event types.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


class TickEventType(Enum):
    """Types of real-time market data events"""
    TICK = "TICK"
    ORDER_BOOK_UPDATE = "ORDER_BOOK_UPDATE"
    TRADE = "TRADE"
    CONNECTION_STATUS_CHANGED = "CONNECTION_STATUS_CHANGED"
    SUBSCRIPTION_STATUS_CHANGED = "SUBSCRIPTION_STATUS_CHANGED"
    ERROR = "ERROR"
    HEARTBEAT = "HEARTBEAT"


@dataclass
class TickData:
    """
    Real-time tick data for a symbol from a specific broker.
    
    Contains the latest price information, bid/ask, volume,
    and metadata for a trading symbol.
    """
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    last_price: float
    last_size: int
    volume: int
    broker: str
    exchange: str
    
    # Additional market data
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    vwap: Optional[float] = None  # Volume-weighted average price
    
    # Market microstructure
    bid_count: Optional[int] = None  # Number of bid levels
    ask_count: Optional[int] = None  # Number of ask levels
    
    # Time and sequence
    sequence_number: Optional[int] = None
    trading_session: Optional[str] = None  # 'PRE_MARKET', 'REGULAR', 'AFTER_HOURS'
    
    def get_spread(self) -> float:
        """Get bid-ask spread"""
        return self.ask - self.bid
    
    def get_spread_bps(self) -> float:
        """Get bid-ask spread in basis points"""
        if self.bid == 0:
            return 0.0
        return ((self.ask - self.bid) / self.bid) * 10000
    
    def get_mid_price(self) -> float:
        """Get mid-price (average of bid and ask)"""
        return (self.bid + self.ask) / 2
    
    def is_fresh(self, max_age_seconds: int = 5) -> bool:
        """Check if tick data is fresh (within max_age_seconds)"""
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return age <= max_age_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'bid': self.bid,
            'ask': self.ask,
            'bid_size': self.bid_size,
            'ask_size': self.ask_size,
            'last_price': self.last_price,
            'last_size': self.last_size,
            'volume': self.volume,
            'broker': self.broker,
            'exchange': self.exchange,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'vwap': self.vwap,
            'bid_count': self.bid_count,
            'ask_count': self.ask_count,
            'sequence_number': self.sequence_number,
            'trading_session': self.trading_session,
            'spread': self.get_spread(),
            'spread_bps': self.get_spread_bps(),
            'mid_price': self.get_mid_price(),
            'is_fresh': self.is_fresh()
        }


@dataclass
class OrderBookLevel:
    """
    Single level in the order book.
    
    Represents a bid or ask level with price, size, and metadata.
    """
    price: float
    size: int
    side: str  # 'BID' or 'ASK'
    timestamp: datetime
    broker: str
    exchange: Optional[str] = None
    
    # Additional metadata
    order_count: Optional[int] = None  # Number of orders at this level
    sequence_number: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'price': self.price,
            'size': self.size,
            'side': self.side,
            'timestamp': self.timestamp.isoformat(),
            'broker': self.broker,
            'exchange': self.exchange,
            'order_count': self.order_count,
            'sequence_number': self.sequence_number
        }


@dataclass
class OrderBookSnapshot:
    """
    Complete order book snapshot for a symbol.
    
    Contains bid and ask levels, total depth, and metadata.
    """
    symbol: str
    timestamp: datetime
    broker: str
    exchange: Optional[str] = None
    
    # Order book levels
    bid_levels: list[OrderBookLevel] = None
    ask_levels: list[OrderBookLevel] = None
    
    # Calculated metrics
    total_bid_size: int = 0
    total_ask_size: int = 0
    best_bid: float = 0.0
    best_ask: float = 0.0
    spread: float = 0.0
    spread_bps: float = 0.0
    
    # Level counts
    bid_level_count: int = 0
    ask_level_count: int = 0
    
    # Sequence information
    sequence_number: Optional[int] = None
    last_update: Optional[datetime] = None
    
    def __post_init__(self):
        """Calculate derived metrics after initialization"""
        if self.bid_levels is None:
            self.bid_levels = []
        if self.ask_levels is None:
            self.ask_levels = []
            
        # Calculate totals
        self.total_bid_size = sum(level.size for level in self.bid_levels)
        self.total_ask_size = sum(level.size for level in self.ask_levels)
        
        # Best bid/ask
        if self.bid_levels:
            self.best_bid = max(level.price for level in self.bid_levels)
        if self.ask_levels:
            self.best_ask = min(level.price for level in self.ask_levels)
            
        # Spread
        if self.best_bid > 0 and self.best_ask > 0:
            self.spread = self.best_ask - self.best_bid
            if self.best_bid > 0:
                self.spread_bps = (self.spread / self.best_bid) * 10000
                
        # Level counts
        self.bid_level_count = len(self.bid_levels)
        self.ask_level_count = len(self.ask_levels)
        
        self.last_update = self.timestamp
    
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
            for level in sorted(self.bid_levels, key=lambda x: x.price, reverse=True):
                cumulative_size += level.size
                if cumulative_size >= size:
                    return level.price
        else:
            cumulative_size = 0
            for level in sorted(self.ask_levels, key=lambda x: x.price):
                cumulative_size += level.size
                if cumulative_size >= size:
                    return level.price
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'broker': self.broker,
            'exchange': self.exchange,
            'bid_levels': [level.to_dict() for level in self.bid_levels],
            'ask_levels': [level.to_dict() for level in self.ask_levels],
            'total_bid_size': self.total_bid_size,
            'total_ask_size': self.total_ask_size,
            'best_bid': self.best_bid,
            'best_ask': self.best_ask,
            'spread': self.spread,
            'spread_bps': self.spread_bps,
            'bid_level_count': self.bid_level_count,
            'ask_level_count': self.ask_level_count,
            'sequence_number': self.sequence_number,
            'last_update': self.last_update.isoformat() if self.last_update else None
        }


@dataclass
class TickEvent:
    """
    Real-time market data event.
    
    Represents any kind of real-time market data event including
    tick data, order book updates, trades, and system events.
    """
    event_type: TickEventType
    symbol: str
    broker: str
    timestamp: datetime
    data: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'event_type': self.event_type.value,
            'symbol': self.symbol,
            'broker': self.broker,
            'timestamp': self.timestamp.isoformat(),
            'data': self.data
        }


@dataclass
class MarketImpactMetrics:
    """
    Real-time market impact assessment for a symbol.
    
    Calculated metrics for estimating market impact, slippage,
    and liquidity characteristics.
    """
    symbol: str
    timestamp: datetime
    broker: str
    
    # Impact estimates
    estimated_impact_bps: float
    liquidity_score: float
    slippage_estimate: float
    market_impact_score: float
    
    # Liquidity metrics
    depth_at_1pct: float
    depth_at_2pct: float
    depth_at_5pct: float
    effective_spread: float
    
    # Market microstructure
    spread_bps: float
    price_level_count: int
    average_level_size: float
    
    # Confidence and quality
    data_freshness: float  # 0-1 score
    broker_reliability: float  # 0-1 score
    calculation_quality: float  # 0-1 score
    
    def get_impact_category(self) -> str:
        """Get market impact category"""
        if self.estimated_impact_bps <= 1:
            return "LOW"
        elif self.estimated_impact_bps <= 5:
            return "MEDIUM"
        elif self.estimated_impact_bps <= 15:
            return "HIGH"
        else:
            return "VERY_HIGH"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'broker': self.broker,
            'estimated_impact_bps': self.estimated_impact_bps,
            'liquidity_score': self.liquidity_score,
            'slippage_estimate': self.slippage_estimate,
            'market_impact_score': self.market_impact_score,
            'depth_at_1pct': self.depth_at_1pct,
            'depth_at_2pct': self.depth_at_2pct,
            'depth_at_5pct': self.depth_at_5pct,
            'effective_spread': self.effective_spread,
            'spread_bps': self.spread_bps,
            'price_level_count': self.price_level_count,
            'average_level_size': self.average_level_size,
            'data_freshness': self.data_freshness,
            'broker_reliability': self.broker_reliability,
            'calculation_quality': self.calculation_quality,
            'impact_category': self.get_impact_category()
        }


@dataclass
class PriceLevelUpdate:
    """
    Update to a single price level in the order book.
    
    Used for incremental order book updates.
    """
    symbol: str
    side: str  # 'BID' or 'ASK'
    price: float
    size: int
    timestamp: datetime
    broker: str
    
    # Update type
    update_type: str  # 'INSERT', 'UPDATE', 'DELETE', 'CLEAR'
    sequence_number: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'symbol': self.symbol,
            'side': self.side,
            'price': self.price,
            'size': self.size,
            'timestamp': self.timestamp.isoformat(),
            'broker': self.broker,
            'update_type': self.update_type,
            'sequence_number': self.sequence_number
        }