"""
Real-time Market Data Module

Provides comprehensive real-time market data capabilities including:
- WebSocket data streams from multiple brokers
- Level 2 order book management
- Market data aggregation and price discovery
- Market impact calculation and analysis
- High-performance data processing

Supported Features:
- Interactive Brokers, TD Ameritrade, Binance, Coinbase Pro, Alpaca
- Real-time tick data and order book updates
- Cross-broker price aggregation
- Market impact and liquidity analysis
- Sub-millisecond data processing
"""

from .tick_data import (
    TickData,
    OrderBookLevel,
    OrderBookSnapshot,
    TickEvent,
    TickEventType,
    MarketImpactMetrics,
    PriceLevelUpdate,
)

from .real_time_data_manager import (
    RealTimeDataManager,
    DataSource,
    DataSourceStatus,
    RealTimeMetrics,
)

from .order_book_manager import (
    OrderBookManager,
    OrderBookSymbol,
    OrderBookConfig,
)

from .market_data_aggregator import (
    MarketDataAggregator,
    AggregatedPrice,
    AggregationConfig,
)

from .market_impact_calculator import (
    MarketImpactCalculator,
    ImpactCalculation,
    LiquidityAnalysis,
    MarketImpactConfig,
)

# WebSocket stream imports
from .websocket_streams.ibkr_stream import IBKRWebSocketStream
from .websocket_streams.tda_stream import TDAWebSocketStream
from .websocket_streams.binance_stream import BinanceWebSocketStream
from .websocket_streams.coinbase_stream import CoinbaseWebSocketStream
from .websocket_streams.alpaca_stream import AlpacaWebSocketStream

__all__ = [
    # Core data structures
    "TickData",
    "OrderBookLevel", 
    "OrderBookSnapshot",
    "TickEvent",
    "TickEventType",
    "MarketImpactMetrics",
    "PriceLevelUpdate",
    
    # Real-time data management
    "RealTimeDataManager",
    "DataSource",
    "DataSourceStatus", 
    "RealTimeMetrics",
    
    # Order book management
    "OrderBookManager",
    "OrderBookSymbol",
    "OrderBookConfig",
    
    # Data aggregation
    "MarketDataAggregator",
    "AggregatedPrice",
    "AggregationConfig",
    
    # Market impact analysis
    "MarketImpactCalculator",
    "ImpactCalculation",
    "LiquidityAnalysis",
    "MarketImpactConfig",
    
    # WebSocket streams
    "IBKRWebSocketStream",
    "TDAWebSocketStream",
    "BinanceWebSocketStream",
    "CoinbaseWebSocketStream",
    "AlpacaWebSocketStream",
]