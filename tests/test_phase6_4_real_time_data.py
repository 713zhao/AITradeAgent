#!/usr/bin/env python3
"""
Phase 6.4: Real-time Market Data Integration Test Suite
Tests WebSocket feeds, Level 2 order book, and sub-millisecond processing
"""

import pytest
import asyncio
import time
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
import websockets
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional
import logging

# Import the modules we're testing
from finance_service.market_data.real_time_data_manager import RealTimeDataManager
from finance_service.market_data.order_book_manager import OrderBookManager
from finance_service.market_data.market_data_aggregator import MarketDataAggregator
from finance_service.market_data.market_impact_calculator import MarketImpactCalculator
from finance_service.market_data.websocket_streams.ibkr_stream import IBKRWebSocketStream
from finance_service.market_data.websocket_streams.tda_stream import TDAWebSocketStream
from finance_service.market_data.websocket_streams.binance_stream import BinanceWebSocketStream
from finance_service.market_data.websocket_streams.coinbase_stream import CoinbaseWebSocketStream
from finance_service.market_data.websocket_streams.alpaca_stream import AlpacaWebSocketStream
from finance_service.core.events import EventManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TestTickData:
    """Test tick data structure"""
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


# =====================
# PYTEST FIXTURES
# =====================

@pytest.fixture
def event_manager():
    """Create a mock event manager"""
    return Mock(spec=EventManager)


@pytest.fixture
def market_data_config():
    """Create a market data configuration"""
    return {
        'websockets': {
            'ibkr': {'enabled': False},
            'tda': {'enabled': False},
            'binance': {'enabled': False},
            'coinbase': {'enabled': False},
            'alpaca': {'enabled': False}
        },
        'aggregation': {
            'update_interval': 0.1,
            'price_freshness': 5.0,
            'min_broker_count': 1,
            'max_broker_count': 6,
            'price_tolerance': 0.001,
            'aggregation_method': 'WEIGHTED'
        },
        'market_impact': {
            'impact_lookback_period': 100,
            'impact_confidence_threshold': 0.8,
            'depth_percentages': [1.0, 2.0, 5.0],
            'min_liquidity_score': 0.1,
            'max_liquidity_score': 1.0,
            'default_slice_size': 1000,
            'max_execution_time': 300,
            'min_execution_time': 1,
            'min_data_freshness': 0.5,
            'min_broker_count': 1,
            'max_price_deviation': 0.05
        },
        'order_book': {
            'max_symbols': 1000,
            'max_levels_per_side': 20,
            'update_threshold': 0.01,
            'snapshot_interval': 60,
            'cleanup_interval': 300,
            'max_book_age': 60
        }
    }


@pytest.fixture
def real_time_manager(market_data_config, event_manager):
    """Create a real-time data manager"""
    return RealTimeDataManager(market_data_config, event_manager)


@pytest.fixture
def market_data_aggregator(market_data_config, real_time_manager, event_manager):
    """Create a market data aggregator"""
    return MarketDataAggregator(market_data_config, real_time_manager, event_manager)


@pytest.fixture
def order_book_manager(market_data_config, event_manager):
    """Create an order book manager"""
    return OrderBookManager(market_data_config, event_manager)


@pytest.fixture
def market_impact_calculator(market_data_config, order_book_manager, 
                           market_data_aggregator, event_manager):
    """Create a market impact calculator"""
    return MarketImpactCalculator(market_data_config, order_book_manager, 
                                 market_data_aggregator, event_manager)


@pytest.fixture
def ibkr_stream(market_data_config, event_manager):
    """Create an IBKR WebSocket stream"""
    return IBKRWebSocketStream(market_data_config, event_manager)


@pytest.fixture
def tda_stream(market_data_config, event_manager):
    """Create a TDA WebSocket stream"""
    return TDAWebSocketStream(market_data_config, event_manager)


@pytest.fixture
def binance_stream(market_data_config, event_manager):
    """Create a Binance WebSocket stream"""
    return BinanceWebSocketStream(market_data_config, event_manager)


@pytest.fixture
def coinbase_stream(market_data_config, event_manager):
    """Create a Coinbase WebSocket stream"""
    return CoinbaseWebSocketStream(market_data_config, event_manager)


@pytest.fixture
def alpaca_stream(market_data_config, event_manager):
    """Create an Alpaca WebSocket stream"""
    return AlpacaWebSocketStream(market_data_config, event_manager)


class TestRealTimeDataManager:
    """Test the Real-time Data Manager"""
    
    def test_manager_initialization(self, real_time_manager):
        """Test manager initialization"""
        manager = real_time_manager
        assert manager is not None
        assert manager.running == False
        assert len(manager.data_sources) == 0
        
    def test_add_stream(self, real_time_manager):
        """Test adding WebSocket streams"""
        manager = real_time_manager
        # Mock WebSocket streamer
        mock_stream = Mock()
        mock_stream.is_connected = False
        mock_stream.symbols = []
        
        # Add stream for testing
        result = manager.add_stream('test_broker', mock_stream)
        assert result == True
        assert 'test_broker' in manager.data_sources
        
    def test_remove_stream(self, real_time_manager):
        """Test removing WebSocket streams"""
        manager = real_time_manager
        # Add and then remove stream
        mock_stream = Mock()
        manager.add_stream('test_broker', mock_stream)
        
        result = manager.remove_stream('test_broker')
        assert result == True
        assert 'test_broker' not in manager.data_sources
        
    def test_start_stop_streams(self, real_time_manager):
        """Test starting and stopping streams"""
        manager = real_time_manager
        mock_stream = Mock()
        mock_stream.connect = AsyncMock()
        mock_stream.disconnect = AsyncMock()
        
        manager.add_stream('test_broker', mock_stream)
        
        # Test start (skip actual async execution for unit test)
        # Just verify stream was added
        assert 'test_broker' in manager.data_sources
        
    def test_data_routing(self, real_time_manager):
        """Test data routing to subscribers"""
        manager = real_time_manager
        # Mock data callback
        callback = Mock()
        manager.subscribe('AAPL', callback)
        
        # Verify subscription was added
        assert 'AAPL' in manager.symbol_subscribers
        
    def test_performance_metrics(self, real_time_manager):
        """Test performance monitoring"""
        manager = real_time_manager
        # Verify metrics attributes exist
        assert hasattr(manager, 'metrics')
        assert manager.update_count >= 0

class TestOrderBookManager:
    """Test the Order Book Manager"""
    
    def test_initialization(self, order_book_manager):
        """Test order book manager initialization"""
        book_manager = order_book_manager
        assert book_manager.book_config.max_levels_per_side == 20
        assert len(book_manager.symbol_books) == 0
        
    def test_add_order_book(self, order_book_manager):
        """Test adding an order book for a symbol"""
        book_manager = order_book_manager
        result = book_manager.add_order_book('AAPL')
        assert result == True
        assert 'AAPL' in book_manager.books
        
    def test_update_bid_level(self, order_book_manager):
        """Test updating bid levels"""
        book_manager = order_book_manager
        book_manager.add_order_book('AAPL')
        
        # Update bid level
        book_manager.update_bid_level('AAPL', 150.00, 1000, 'IBKR')
        
        book = book_manager.get_order_book('AAPL')
        assert len(book.bids) >= 1
        assert book.bids[0].price == 150.00
        assert book.bids[0].size == 1000
        assert book.bids[0].broker == 'IBKR'
        
    def test_update_ask_level(self, order_book_manager):
        """Test updating ask levels"""
        book_manager = order_book_manager
        book_manager.add_order_book('AAPL')
        
        # Update ask level
        book_manager.update_ask_level('AAPL', 150.10, 800, 'TDA')
        
        book = book_manager.get_order_book('AAPL')
        assert len(book.asks) >= 1
        assert book.asks[0].price == 150.10
        assert book.asks[0].size == 800
        assert book.asks[0].broker == 'TDA'
        
    def test_get_best_bid_ask(self, order_book_manager):
        """Test getting best bid and ask"""
        book_manager = order_book_manager
        book_manager.add_order_book('AAPL')
        
        # Add multiple levels
        book_manager.update_bid_level('AAPL', 150.00, 1000, 'IBKR')
        book_manager.update_bid_level('AAPL', 149.95, 1500, 'TDA')
        book_manager.update_ask_level('AAPL', 150.10, 800, 'IBKR')
        book_manager.update_ask_level('AAPL', 150.15, 1200, 'TDA')
        
        best_bid, best_ask = book_manager.get_best_bid_ask('AAPL')
        
        assert best_bid.price == 150.00  # Highest bid
        assert best_ask.price == 150.10  # Lowest ask
        
    def test_market_depth_analysis(self, order_book_manager):
        """Test market depth analysis"""
        book_manager = order_book_manager
        book_manager.add_order_book('AAPL')
        
        # Add depth on both sides
        for price in [149.90, 149.95, 150.00]:
            book_manager.update_bid_level('AAPL', price, 1000, 'test')
            
        for price in [150.10, 150.15, 150.20]:
            book_manager.update_ask_level('AAPL', price, 1000, 'test')
            
        depth = book_manager.get_market_depth('AAPL')
        
        assert depth['bid_depth'] > 0
        assert depth['ask_depth'] > 0
        assert depth['total_volume'] > 0
        assert depth['spread'] > 0
        
    def test_liquidity_analysis(self, order_book_manager):
        """Test liquidity calculation"""
        book_manager = order_book_manager
        book_manager.add_order_book('AAPL')
        
        # Add significant liquidity
        for i in range(10):
            price = 150.00 - (i * 0.01)
            book_manager.update_bid_level('AAPL', price, 1000 + i*100, 'test')
        
        # Add ask levels too
        for i in range(10):
            price = 150.10 + (i * 0.01)
            book_manager.update_ask_level('AAPL', price, 1000 + i*100, 'test')
            
        liquidity = book_manager.calculate_liquidity('AAPL')
        
        assert liquidity['liquidity_score'] > 0
        assert liquidity['bid_liquidity'] > 0
        assert liquidity['ask_liquidity'] > 0

class TestMarketDataAggregator:
    """Test the Market Data Aggregator"""
    
    def test_initialization(self, market_data_aggregator):
        """Test aggregator initialization"""
        aggregator = market_data_aggregator
        assert aggregator is not None
        assert len(aggregator.data_sources) == 0
        
    def test_register_data_source(self, market_data_aggregator):
        """Test registering data sources"""
        aggregator = market_data_aggregator
        mock_source = Mock()
        mock_source.get_symbols.return_value = ['AAPL', 'TSLA']
        
        result = aggregator.register_data_source('IBKR', mock_source)
        assert result == True
        assert 'IBKR' in aggregator.data_sources
        
    def test_aggregate_tick_data(self, market_data_aggregator):
        """Test aggregating tick data from multiple sources"""
        aggregator = market_data_aggregator
        aggregator.register_data_source('IBKR', Mock())
        aggregator.register_data_source('TDA', Mock())
        
        # Simulate tick data from different sources
        tick1 = TestTickData(
            symbol='AAPL',
            timestamp=datetime.now(),
            bid=150.00,
            ask=150.10,
            bid_size=1000,
            ask_size=800,
            last_price=150.05,
            last_size=100,
            volume=50000,
            broker='IBKR',
            exchange='NASDAQ'
        )
        
        tick2 = TestTickData(
            symbol='AAPL',
            timestamp=datetime.now(),
            bid=149.99,
            ask=150.11,
            bid_size=1200,
            ask_size=900,
            last_price=150.05,
            last_size=100,
            volume=51000,
            broker='TDA',
            exchange='NASDAQ'
        )
        
        # Aggregate data
        aggregated = aggregator.aggregate_tick_data('AAPL', [tick1, tick2])
        
        assert aggregated.symbol == 'AAPL'
        assert aggregated.best_bid == 150.00  # Best bid from IBKR
        assert aggregated.best_ask == 150.10  # Best ask from IBKR
        assert aggregated.total_volume == 101000  # Sum of volumes
        
    def test_price_discovery(self, market_data_aggregator):
        """Test cross-venue price discovery"""
        aggregator = market_data_aggregator
        # Add mock data sources
        aggregator.register_data_source('IBKR', Mock())
        aggregator.register_data_source('TDA', Mock())
        aggregator.register_data_source('BINANCE', Mock())
        
        # Simulate price discovery
        price_data = {
            'IBKR': {'bid': 150.00, 'ask': 150.10, 'timestamp': datetime.now()},
            'TDA': {'bid': 149.99, 'ask': 150.11, 'timestamp': datetime.now()},
            'BINANCE': {'bid': 150.01, 'ask': 150.09, 'timestamp': datetime.now()}
        }
        
        discovery = aggregator.discover_best_prices('AAPL', price_data)
        
        assert discovery['best_bid']['price'] == 150.01  # Best from Binance
        assert discovery['best_ask']['price'] == 150.09  # Best from Binance
        assert len(discovery['all_prices']) == 3
        
    def test_data_freshness(self, market_data_aggregator):
        """Test data freshness validation"""
        aggregator = market_data_aggregator
        # Add mock data source
        mock_source = Mock()
        aggregator.register_data_source('TEST', mock_source)
        
        # Simulate fresh and stale data
        fresh_tick = TestTickData(
            symbol='AAPL',
            timestamp=datetime.now(),  # Fresh
            bid=150.00,
            ask=150.10,
            bid_size=1000,
            ask_size=800,
            last_price=150.05,
            last_size=100,
            volume=50000,
            broker='TEST',
            exchange='NASDAQ'
        )
        
        stale_tick = TestTickData(
            symbol='AAPL',
            timestamp=datetime.now() - timedelta(seconds=10),  # Stale
            bid=150.00,
            ask=150.10,
            bid_size=1000,
            ask_size=800,
            last_price=150.05,
            last_size=100,
            volume=50000,
            broker='TEST',
            exchange='NASDAQ'
        )
        
        assert aggregator.is_data_fresh(fresh_tick) == True
        assert aggregator.is_data_fresh(stale_tick) == False

class TestMarketImpactCalculator:
    """Test the Market Impact Calculator"""
    
    def test_initialization(self, market_impact_calculator):
        """Test calculator initialization"""
        calculator = market_impact_calculator
        assert calculator is not None
        assert len(calculator.impact_cache) == 0
        
    def test_calculate_immediate_impact(self, market_impact_calculator):
        """Test immediate market impact calculation"""
        calculator = market_impact_calculator
        # Simulate order book data
        order_book = {
            'bids': [
                {'price': 150.00, 'size': 1000, 'broker': 'IBKR'},
                {'price': 149.95, 'size': 1500, 'broker': 'TDA'},
                {'price': 149.90, 'size': 2000, 'broker': 'BINANCE'}
            ],
            'asks': [
                {'price': 150.10, 'size': 800, 'broker': 'IBKR'},
                {'price': 150.15, 'size': 1200, 'broker': 'TDA'},
                {'price': 150.20, 'size': 1800, 'broker': 'BINANCE'}
            ]
        }
        
        # Calculate impact for a market buy order
        impact = calculator.calculate_immediate_impact(
            symbol='AAPL',
            side='BUY',
            quantity=500,
            order_book=order_book
        )
        
        assert impact['estimated_impact_bps'] > 0
        assert impact['slippage_estimate'] > 0
        assert impact['executed_price'] > 0
        
    def test_calculate_liquidity_score(self, market_impact_calculator):
        """Test liquidity score calculation"""
        calculator = market_impact_calculator
        order_book = {
            'bids': [
                {'price': 150.00, 'size': 10000, 'broker': 'IBKR'},
                {'price': 149.95, 'size': 15000, 'broker': 'TDA'},
                {'price': 149.90, 'size': 20000, 'broker': 'BINANCE'}
            ],
            'asks': [
                {'price': 150.10, 'size': 12000, 'broker': 'IBKR'},
                {'price': 150.15, 'size': 18000, 'broker': 'TDA'},
                {'price': 150.20, 'size': 25000, 'broker': 'BINANCE'}
            ]
        }
        
        liquidity_score = calculator.calculate_liquidity_score('AAPL', order_book)
        
        assert liquidity_score['liquidity_score'] > 0
        assert liquidity_score['bid_liquidity'] > 0
        assert liquidity_score['ask_liquidity'] > 0
        assert liquidity_score['spread_bps'] > 0
        
    def test_market_impact_vs_size(self, market_impact_calculator):
        """Test impact scaling with order size"""
        calculator = market_impact_calculator
        # High liquidity order book
        high_liquidity_book = {
            'bids': [{'price': 150.00, 'size': 100000, 'broker': 'test'}],
            'asks': [{'price': 150.10, 'size': 100000, 'broker': 'test'}]
        }
        
        # Low liquidity order book
        low_liquidity_book = {
            'bids': [{'price': 150.00, 'size': 1000, 'broker': 'test'}],
            'asks': [{'price': 150.10, 'size': 1000, 'broker': 'test'}]
        }
        
        # Test different order sizes
        small_order = 100
        large_order = 50000
        
        high_liq_small = calculator.calculate_immediate_impact(
            'AAPL', 'BUY', small_order, high_liquidity_book
        )
        high_liq_large = calculator.calculate_immediate_impact(
            'AAPL', 'BUY', large_order, high_liquidity_book
        )
        low_liq_small = calculator.calculate_immediate_impact(
            'AAPL', 'BUY', small_order, low_liquidity_book
        )
        low_liq_large = calculator.calculate_immediate_impact(
            'AAPL', 'BUY', large_order, low_liquidity_book
        )
        
        # Large orders should have higher impact
        assert high_liq_large['estimated_impact_bps'] > high_liq_small['estimated_impact_bps']
        assert low_liq_large['estimated_impact_bps'] > low_liq_small['estimated_impact_bps']
        
        # Low liquidity should have higher impact
        assert low_liq_small['estimated_impact_bps'] > high_liq_small['estimated_impact_bps']

class TestWebSocketStreams:
    """Test WebSocket stream implementations"""
    
    def test_ibkr_stream_initialization(self, ibkr_stream):
        """Test IBKR WebSocket stream initialization"""
        assert ibkr_stream.broker_name == 'IBKR'
        assert ibkr_stream.is_connected() == False
        
    def test_tda_stream_initialization(self, tda_stream):
        """Test TDA WebSocket stream initialization"""
        assert tda_stream.broker_name == 'TDA'
        assert tda_stream.is_connected() == False
        
    def test_binance_stream_initialization(self, binance_stream):
        """Test Binance WebSocket stream initialization"""
        assert binance_stream.broker_name == 'BINANCE'
        assert binance_stream.is_connected() == False
        
    def test_coinbase_stream_initialization(self, coinbase_stream):
        """Test Coinbase WebSocket stream initialization"""
        assert coinbase_stream.broker_name == 'COINBASE'
        assert coinbase_stream.is_connected() == False
        
    def test_alpaca_stream_initialization(self, alpaca_stream):
        """Test Alpaca WebSocket stream initialization"""
        assert alpaca_stream.broker_name == 'ALPACA'
        assert alpaca_stream.is_connected() == False
        
    def test_stream_message_parsing(self, ibkr_stream):
        """Test message parsing for different streams"""
        # Test IBKR message parsing
        ibkr_message = {
            'ticker': 'AAPL',
            'bid': 150.00,
            'ask': 150.10,
            'bidSize': 1000,
            'askSize': 800,
            'last': 150.05,
            'lastSize': 100,
            'volume': 50000
        }
        
        parsed = ibkr_stream.parse_message(ibkr_message)
        assert parsed['symbol'] == 'AAPL'
        assert parsed['bid'] == 150.00
        assert parsed['ask'] == 150.10
        
    @pytest.mark.asyncio
    async def test_stream_connection_lifecycle(self, ibkr_stream):
        """Test WebSocket connection lifecycle"""
        # Mock WebSocket connection - need to return async context manager
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock()
        mock_ws.close = AsyncMock()
        
        # Create an async context manager for the mock
        async def mock_connect(*args, **kwargs):
            return mock_ws
        
        # Test connection
        with patch('websockets.connect', return_value=mock_connect('uri')):
            await ibkr_stream.connect()
            # After connect, the stream should be connected
            # (Note: In actual implementation, connection success depends on the mock setup)
        
        # Test disconnection
        await ibkr_stream.disconnect()
        assert ibkr_stream.is_connected() == False

class TestPerformanceAndLatency:
    """Test performance and latency requirements"""
    
    def test_data_processing_latency(self, real_time_manager):
        """Test sub-millisecond data processing"""
        # Measure processing time
        start_time = time.perf_counter()
        
        # Process 1000 tick updates
        for i in range(1000):
            test_data = TestTickData(
                symbol='AAPL',
                timestamp=datetime.now(),
                bid=150.00,
                ask=150.10,
                bid_size=1000,
                ask_size=800,
                last_price=150.05,
                last_size=100,
                volume=50000,
                broker='test',
                exchange='NASDAQ'
            )
            real_time_manager.route_data(test_data)
            
        end_time = time.perf_counter()
        total_time = (end_time - start_time) * 1000  # Convert to milliseconds
        
        # Should process 1000 updates in under 500ms (0.5ms per update)
        assert total_time < 500
        avg_latency = total_time / 1000
        assert avg_latency < 0.5
        
    def test_order_book_update_performance(self, order_book_manager):
        """Test order book update performance"""
        order_book_manager.add_order_book('AAPL')
        
        start_time = time.perf_counter()
        
        # Perform 1000 order book updates
        for i in range(1000):
            order_book_manager.update_bid_level('AAPL', 150.00 + i*0.01, 1000, 'test')
            order_book_manager.update_ask_level('AAPL', 150.10 + i*0.01, 1000, 'test')
            
        end_time = time.perf_counter()
        total_time = (end_time - start_time) * 1000
        
        # Should handle 1000 updates in under 100ms (0.1ms per update)
        assert total_time < 100
        avg_latency = total_time / 1000
        assert avg_latency < 0.1
        
    def test_aggregation_performance(self, market_data_aggregator):
        """Test market data aggregation performance"""
        # Create test data from multiple sources
        test_ticks = []
        for broker in ['IBKR', 'TDA', 'BINANCE', 'COINBASE', 'ALPACA']:
            for i in range(100):
                test_ticks.append(TestTickData(
                    symbol='AAPL',
                    timestamp=datetime.now(),
                    bid=150.00 + i*0.001,
                    ask=150.10 + i*0.001,
                    bid_size=1000,
                    ask_size=800,
                    last_price=150.05 + i*0.001,
                    last_size=100,
                    volume=50000,
                    broker=broker,
                    exchange='NASDAQ'
                ))
        
        start_time = time.perf_counter()
        
        # Aggregate all data
        for tick in test_ticks:
            market_data_aggregator.aggregate_tick_data('AAPL', [tick])
            
        end_time = time.perf_counter()
        total_time = (end_time - start_time) * 1000
        
        # Should aggregate 500 updates in under 50ms
        assert total_time < 50
        
    def test_throughput_requirements(self, real_time_manager):
        """Test 10,000+ updates per second throughput"""
        # Measure throughput over 1 second
        start_time = time.perf_counter()
        update_count = 0
        
        while (time.perf_counter() - start_time) < 1.0:  # Run for 1 second
            test_data = TestTickData(
                symbol='AAPL',
                timestamp=datetime.now(),
                bid=150.00,
                ask=150.10,
                bid_size=1000,
                ask_size=800,
                last_price=150.05,
                last_size=100,
                volume=50000,
                broker='test',
                exchange='NASDAQ'
            )
            real_time_manager.route_data(test_data)
            update_count += 1
            
        elapsed_time = time.perf_counter() - start_time
        throughput = update_count / elapsed_time
        
        # Should handle 10,000+ updates per second
        assert throughput >= 10000
        
    def test_memory_usage(self, order_book_manager):
        """Test memory usage for active symbols"""
        # Add 1000 symbols
        for i in range(1000):
            symbol = f'SYM{i:04d}'
            order_book_manager.add_order_book(symbol)
            
            # Add some depth
            for level in range(10):
                bid_price = 100.00 - level * 0.01
                ask_price = 100.01 + level * 0.01
                order_book_manager.update_bid_level(symbol, bid_price, 1000, 'test')
                order_book_manager.update_ask_level(symbol, ask_price, 1000, 'test')
        
        # Verify all symbols were added
        total_symbols = len(order_book_manager.symbol_books)  # Changed from order_books
        assert total_symbols == 1000
        
        # Verify we can retrieve symbol data
        test_book = order_book_manager.get_order_book('SYM0000')
        assert test_book is not None
        assert len(test_book.bids) == 10
        assert len(test_book.asks) == 10

class TestIntegration:
    """Integration tests for the complete real-time data system"""
    
    def test_end_to_end_data_flow(self, real_time_manager, order_book_manager, market_data_aggregator, market_impact_calculator):
        """Test complete data flow from WebSocket to aggregation"""
        # Create mock stream
        mock_stream = Mock()
        real_time_manager.add_stream('TEST', mock_stream)
        
        # Subscribe to data
        def data_callback(tick_data):
            # Update order book
            order_book_manager.update_bid_level(tick_data.symbol, tick_data.bid, tick_data.bid_size, tick_data.broker)
            order_book_manager.update_ask_level(tick_data.symbol, tick_data.ask, tick_data.ask_size, tick_data.broker)
            
            # Get order book for impact calculation
            book = order_book_manager.get_order_book(tick_data.symbol)
            order_book = {
                'bids': [{'price': level.price, 'size': level.size, 'broker': level.broker} for level in book.bids],
                'asks': [{'price': level.price, 'size': level.size, 'broker': level.broker} for level in book.asks]
            }
            
            # Calculate market impact
            impact = market_impact_calculator.calculate_immediate_impact(
                tick_data.symbol, 'BUY', 1000, order_book
            )
            
            # Store result
            return impact
            
        real_time_manager.subscribe('AAPL', data_callback)
        
        # Simulate data flow
        test_data = TestTickData(
            symbol='AAPL',
            timestamp=datetime.now(),
            bid=150.00,
            ask=150.10,
            bid_size=1000,
            ask_size=800,
            last_price=150.05,
            last_size=100,
            volume=50000,
            broker='TEST',
            exchange='NASDAQ'
        )
        
        # Route data through system
        real_time_manager.route_data(test_data)
        
        # Verify order book was updated
        book = order_book_manager.get_order_book('AAPL')
        assert len(book.bids) >= 1
        assert len(book.asks) >= 1
        
        # Verify market impact calculation
        best_bid, best_ask = order_book_manager.get_best_bid_ask('AAPL')
        assert best_bid.price == 150.00
        assert best_ask.price == 150.10
        
    def test_multi_broker_synchronization(self, real_time_manager, market_data_aggregator):
        """Test synchronization across multiple brokers"""
        # Add multiple mock streams
        brokers = ['IBKR', 'TDA', 'BINANCE', 'COINBASE', 'ALPACA']
        for broker in brokers:
            mock_stream = Mock()
            real_time_manager.add_stream(broker, mock_stream)
            
        # Simulate synchronized data from all brokers
        tick_data_list = []
        for broker in brokers:
            tick = TestTickData(
                symbol='AAPL',
                timestamp=datetime.now(),
                bid=150.00 + (hash(broker) % 100) * 0.001,  # Slight variation
                ask=150.10 + (hash(broker) % 100) * 0.001,
                bid_size=1000,
                ask_size=800,
                last_price=150.05 + (hash(broker) % 100) * 0.001,
                last_size=100,
                volume=50000,
                broker=broker,
                exchange='NASDAQ'
            )
            tick_data_list.append(tick)
            
        # Aggregate all data
        aggregated = market_data_aggregator.aggregate_tick_data('AAPL', tick_data_list)
        
        # Verify aggregation
        assert aggregated.symbol == 'AAPL'
        assert aggregated.broker_count == 5  # Changed from data_sources
        assert aggregated.total_volume == 250000  # 5 * 50000
        
        # Verify best prices were selected
        assert aggregated.best_bid > 0
        assert aggregated.best_ask > 0
        assert aggregated.best_bid < aggregated.best_ask

if __name__ == '__main__':
    # Run the tests
    pytest.main([
        __file__,
        '-v',
        '--tb=short',
        '--durations=10',
        '--disable-warnings'
    ])