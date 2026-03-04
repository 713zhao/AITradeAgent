"""
Market Impact Calculator

Calculates real-time market impact, slippage estimates, and liquidity metrics
for order execution planning and risk management.

Features:
- Real-time market impact estimation
- Liquidity analysis and scoring
- Slippage calculation
- Market depth metrics
- Execution cost analysis
- Cross-broker impact comparison
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
import math
import statistics

from .tick_data import TickData, MarketImpactMetrics, OrderBookSnapshot
from .order_book_manager import OrderBookManager
from .market_data_aggregator import MarketDataAggregator


@dataclass
class ImpactCalculation:
    """Market impact calculation for a specific order"""
    symbol: str
    side: str  # 'BUY' or 'SELL'
    order_size: int
    
    # Impact estimates
    estimated_impact_bps: float
    slippage_estimate: float
    market_impact_score: float
    
    # Liquidity metrics
    liquidity_score: float
    depth_at_1pct: float
    depth_at_2pct: float
    depth_at_5pct: float
    effective_spread: float
    spread_bps: float
    
    # Market microstructure
    price_level_count: int
    average_level_size: float
    order_book_quality: float
    
    # Confidence metrics
    data_freshness: float
    broker_reliability: float
    calculation_quality: float
    
    # Additional analysis
    optimal_execution_time: Optional[int] = None  # seconds
    recommended_slice_size: Optional[int] = None
    risk_adjusted_impact: Optional[float] = None


@dataclass
class LiquidityAnalysis:
    """Liquidity analysis for a symbol"""
    symbol: str
    timestamp: datetime
    
    # Liquidity scores (0-1)
    overall_liquidity: float
    bid_liquidity: float
    ask_liquidity: float
    volume_liquidity: float
    
    # Depth metrics
    total_depth_value: float
    average_level_depth: float
    depth_concentration: float
    top_level_dominance: float
    
    # Spread metrics
    spread_score: float
    effective_spread: float
    quoted_spread: float
    
    # Volatility-adjusted metrics
    liquidity_stability: float
    market_impact_resistance: float


@dataclass
class MarketImpactConfig:
    """Configuration for market impact calculations"""
    # Impact calculation parameters
    impact_lookback_period: int = 100  # Number of levels to analyze
    impact_confidence_threshold: float = 0.8  # Minimum confidence for calculations
    
    # Liquidity analysis parameters
    depth_percentages: List[float] = field(default_factory=lambda: [1.0, 2.0, 5.0])
    min_liquidity_score: float = 0.1
    max_liquidity_score: float = 1.0
    
    # Execution parameters
    default_slice_size: int = 1000
    max_execution_time: int = 300  # 5 minutes
    min_execution_time: int = 1    # 1 second
    
    # Quality thresholds
    min_data_freshness: float = 0.5
    min_broker_count: int = 1
    max_price_deviation: float = 0.05  # 5% max price deviation between brokers


class MarketImpactCalculator:
    """
    Calculates real-time market impact and liquidity metrics.
    
    Analyzes order book depth, market conditions, and historical patterns
    to estimate execution costs and optimal trading strategies.
    """
    
    def __init__(self, config: Dict[str, Any], order_book_manager: OrderBookManager, 
                 market_data_aggregator: MarketDataAggregator, event_manager):
        self.config = config
        self.order_book_manager = order_book_manager
        self.market_data_aggregator = market_data_aggregator
        self.event_manager = event_manager
        
        # Impact calculation configuration
        impact_config = config.get('market_impact', {})
        self.impact_config = MarketImpactConfig(
            impact_lookback_period=impact_config.get('impact_lookback_period', 100),
            impact_confidence_threshold=impact_config.get('impact_confidence_threshold', 0.8),
            depth_percentages=impact_config.get('depth_percentages', [1.0, 2.0, 5.0]),
            min_liquidity_score=impact_config.get('min_liquidity_score', 0.1),
            max_liquidity_score=impact_config.get('max_liquidity_score', 1.0),
            default_slice_size=impact_config.get('default_slice_size', 1000),
            max_execution_time=impact_config.get('max_execution_time', 300),
            min_execution_time=impact_config.get('min_execution_time', 1),
            min_data_freshness=impact_config.get('min_data_freshness', 0.5),
            min_broker_count=impact_config.get('min_broker_count', 1),
            max_price_deviation=impact_config.get('max_price_deviation', 0.05)
        )
        
        # Cached calculations
        self.impact_cache: Dict[str, ImpactCalculation] = {}
        self.liquidity_cache: Dict[str, LiquidityAnalysis] = {}
        
        # Historical data for pattern analysis
        self.impact_history: deque = deque(maxlen=1000)
        self.price_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # Performance tracking
        self.calculation_count = 0
        self.average_calculation_time = 0.0
        self.cache_hit_rate = 0.0
        
        # Control flags
        self.running = False
        self._tasks: List[asyncio.Task] = []
        
        # Logging
        self.logger = logging.getLogger(__name__)
        
    async def start(self):
        """Start the market impact calculator"""
        if self.running:
            return
            
        self.running = True
        self.logger.info("Starting Market Impact Calculator")
        
        # Start background tasks
        self._tasks.append(asyncio.create_task(self._cache_cleanup_task()))
        self._tasks.append(asyncio.create_task(self._metrics_task()))
        
        self.logger.info("Market Impact Calculator started")
    
    async def stop(self):
        """Stop the market impact calculator"""
        if not self.running:
            return
            
        self.running = False
        self.logger.info("Stopping Market Impact Calculator")
        
        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
                
        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            
        self.logger.info("Market Impact Calculator stopped")
    
    async def calculate_impact(self, symbol: str, side: str, order_size: int) -> Optional[ImpactCalculation]:
        """Calculate market impact for a proposed order"""
        start_time = datetime.now()
        
        try:
            # Check cache first
            cache_key = f"{symbol}_{side}_{order_size}"
            if cache_key in self.impact_cache:
                cached = self.impact_cache[cache_key]
                # Check if cache is still valid (within 1 second)
                if (datetime.now(timezone.utc) - cached.timestamp).total_seconds() < 1.0:
                    self.cache_hit_rate = (self.cache_hit_rate * self.calculation_count + 1) / (self.calculation_count + 1)
                    return cached
            
            # Get order book data
            order_book = await self.order_book_manager.get_aggregated_order_book(symbol)
            if not order_book:
                self.logger.warning(f"No order book data available for {symbol}")
                return None
            
            # Get market data
            aggregated_price = await self.market_data_aggregator.get_aggregated_price(symbol)
            if not aggregated_price:
                self.logger.warning(f"No market data available for {symbol}")
                return None
            
            # Perform impact calculation
            impact_calc = await self._perform_impact_calculation(
                symbol, side, order_size, order_book, aggregated_price
            )
            
            # Cache the result
            self.impact_cache[cache_key] = impact_calc
            
            # Update metrics
            calculation_time = (datetime.now() - start_time).total_seconds() * 1000
            self._update_performance_metrics(calculation_time)
            
            return impact_calc
            
        except Exception as e:
            self.logger.error(f"Error calculating impact for {symbol}: {e}")
            return None
    
    async def _perform_impact_calculation(self, symbol: str, side: str, order_size: int,
                                        order_book: OrderBookSnapshot, 
                                        aggregated_price) -> ImpactCalculation:
        """Perform the actual impact calculation"""
        
        # Determine price levels to analyze
        mid_price = (order_book.best_bid + order_book.best_ask) / 2
        if mid_price == 0:
            mid_price = aggregated_price.get_mid_price() if hasattr(aggregated_price, 'get_mid_price') else 1.0
        
        # Calculate depth at different percentage moves
        depth_analysis = await self._calculate_depth_analysis(symbol, order_book, mid_price)
        
        # Calculate market impact
        impact_bps = await self._estimate_market_impact_bps(
            symbol, side, order_size, order_book, mid_price, depth_analysis
        )
        
        # Calculate slippage
        slippage = await self._estimate_slippage(
            symbol, side, order_size, order_book, mid_price, impact_bps
        )
        
        # Calculate liquidity score
        liquidity_score = self._calculate_liquidity_score(order_book, depth_analysis)
        
        # Calculate market impact score
        market_impact_score = self._calculate_market_impact_score(impact_bps, liquidity_score)
        
        # Calculate effective spread
        effective_spread = self._calculate_effective_spread(order_book, impact_bps)
        
        # Calculate confidence metrics
        data_freshness = self._assess_data_freshness(order_book)
        broker_reliability = self._assess_broker_reliability(symbol)
        calculation_quality = self._assess_calculation_quality(data_freshness, broker_reliability)
        
        # Calculate optimal execution parameters
        optimal_slice_size = self._calculate_optimal_slice_size(order_size, liquidity_score)
        optimal_execution_time = self._calculate_optimal_execution_time(order_size, liquidity_score)
        
        # Create impact calculation
        impact_calc = ImpactCalculation(
            symbol=symbol,
            side=side,
            order_size=order_size,
            estimated_impact_bps=impact_bps,
            slippage_estimate=slippage,
            market_impact_score=market_impact_score,
            liquidity_score=liquidity_score,
            depth_at_1pct=depth_analysis['depth_at_1pct'],
            depth_at_2pct=depth_analysis['depth_at_2pct'],
            depth_at_5pct=depth_analysis['depth_at_5pct'],
            effective_spread=effective_spread,
            spread_bps=order_book.spread_bps,
            price_level_count=order_book.bid_level_count + order_book.ask_level_count,
            average_level_size=depth_analysis['average_level_size'],
            order_book_quality=self._assess_order_book_quality(order_book),
            data_freshness=data_freshness,
            broker_reliability=broker_reliability,
            calculation_quality=calculation_quality,
            optimal_execution_time=optimal_execution_time,
            recommended_slice_size=optimal_slice_size,
            risk_adjusted_impact=impact_bps * calculation_quality
        )
        
        return impact_calc
    
    async def _calculate_depth_analysis(self, symbol: str, order_book: OrderBookSnapshot, 
                                      mid_price: float) -> Dict[str, float]:
        """Calculate depth analysis at different price levels"""
        
        depth_analysis = {}
        
        for pct in self.impact_config.depth_percentages:
            # Calculate price levels
            price_move = mid_price * (pct / 100.0)
            
            if order_book.best_bid > 0:
                bid_price = order_book.best_bid - price_move if "BUY" in str(symbol) or True else order_book.best_bid
                bid_depth = order_book.get_depth_at_price(bid_price, 'BID')
            else:
                bid_depth = 0
                
            if order_book.best_ask > 0:
                ask_price = order_book.best_ask + price_move if "SELL" in str(symbol) or True else order_book.best_ask
                ask_depth = order_book.get_depth_at_price(ask_price, 'ASK')
            else:
                ask_depth = 0
            
            depth_analysis[f'depth_at_{pct}pct'] = min(bid_depth, ask_depth)
        
        # Calculate average level size
        all_levels = order_book.bid_levels + order_book.ask_levels
        if all_levels:
            depth_analysis['average_level_size'] = statistics.mean([level.size for level in all_levels])
        else:
            depth_analysis['average_level_size'] = 0
        
        return depth_analysis
    
    async def _estimate_market_impact_bps(self, symbol: str, side: str, order_size: int,
                                        order_book: OrderBookSnapshot, mid_price: float,
                                        depth_analysis: Dict[str, float]) -> float:
        """Estimate market impact in basis points"""
        
        # Base impact from order size relative to available liquidity
        available_liquidity = min(depth_analysis['depth_at_1pct'], order_size * 2)
        if available_liquidity == 0:
            return 50.0  # High impact if no liquidity
        
        size_ratio = min(1.0, order_size / available_liquidity)
        
        # Impact increases exponentially with size ratio
        base_impact = 2.0  # 2 bps base impact
        impact_multiplier = math.exp(size_ratio * 2) - 1
        
        # Adjust for spread (wider spreads = higher impact)
        spread_adjustment = order_book.spread_bps / 10.0  # Normalize to reasonable range
        
        # Adjust for level count (more levels = lower impact)
        level_adjustment = max(0.5, 1.0 - (order_book.bid_level_count + order_book.ask_level_count) / 20.0)
        
        # Calculate final impact
        estimated_impact = base_impact * impact_multiplier * (1 + spread_adjustment) * level_adjustment
        
        # Cap at reasonable maximum
        return min(estimated_impact, 100.0)  # Max 100 bps = 1%
    
    async def _estimate_slippage(self, symbol: str, side: str, order_size: int,
                               order_book: OrderBookSnapshot, mid_price: float,
                               impact_bps: float) -> float:
        """Estimate slippage for the order"""
        
        # Slippage is typically a percentage of market impact
        slippage_ratio = 0.7  # 70% of impact typically becomes slippage
        
        # Adjust based on order book quality
        quality_factor = self._assess_order_book_quality(order_book)
        
        # Calculate slippage
        slippage = impact_bps * slippage_ratio * (2 - quality_factor)  # Lower quality = higher slippage
        
        return slippage
    
    def _calculate_liquidity_score(self, order_book: OrderBookSnapshot, 
                                 depth_analysis: Dict[str, float]) -> float:
        """Calculate overall liquidity score (0-1)"""
        
        # Depth score (how much liquidity is available)
        depth_score = min(1.0, depth_analysis['depth_at_1pct'] / 10000)  # Normalize to 10K shares
        
        # Spread score (tighter spreads = higher score)
        spread_score = max(0.0, 1.0 - (order_book.spread_bps / 20.0))  # 20 bps = 0 score
        
        # Level count score (more levels = higher score)
        total_levels = order_book.bid_level_count + order_book.ask_level_count
        level_score = min(1.0, total_levels / 10.0)  # 10 levels = full score
        
        # Combine scores
        liquidity_score = (depth_score * 0.4 + spread_score * 0.4 + level_score * 0.2)
        
        return max(self.impact_config.min_liquidity_score, 
                  min(self.impact_config.max_liquidity_score, liquidity_score))
    
    def _calculate_market_impact_score(self, impact_bps: float, liquidity_score: float) -> float:
        """Calculate market impact score (0-1, higher is better)"""
        
        # Convert impact bps to score (lower impact = higher score)
        impact_score = max(0.0, 1.0 - (impact_bps / 50.0))  # 50 bps = 0 score
        
        # Combine with liquidity score
        return (impact_score * 0.6 + liquidity_score * 0.4)
    
    def _calculate_effective_spread(self, order_book: OrderBookSnapshot, impact_bps: float) -> float:
        """Calculate effective spread (quoted spread + impact)"""
        
        # Effective spread = quoted spread + estimated market impact
        return order_book.spread + (order_book.best_bid * impact_bps / 10000)
    
    def _assess_data_freshness(self, order_book: OrderBookSnapshot) -> float:
        """Assess freshness of order book data"""
        
        if not order_book.last_update:
            return 0.0
        
        age = (datetime.now(timezone.utc) - order_book.last_update).total_seconds()
        
        # Fresh if less than 1 second old
        if age < 1.0:
            return 1.0
        # Decay over 10 seconds
        return max(0.0, 1.0 - (age / 10.0))
    
    def _assess_broker_reliability(self, symbol: str) -> float:
        """Assess reliability of broker data sources"""
        
        # For now, assume high reliability if we have data
        # In production, this could be based on historical accuracy, latency, etc.
        return 0.9
    
    def _assess_calculation_quality(self, data_freshness: float, broker_reliability: float) -> float:
        """Assess overall quality of impact calculation"""
        
        return (data_freshness * 0.6 + broker_reliability * 0.4)
    
    def _assess_order_book_quality(self, order_book: OrderBookSnapshot) -> float:
        """Assess quality of order book data"""
        
        quality_factors = []
        
        # Level count factor
        total_levels = order_book.bid_level_count + order_book.ask_level_count
        level_factor = min(1.0, total_levels / 10.0)
        quality_factors.append(level_factor)
        
        # Spread factor (tighter spreads = better quality)
        spread_factor = max(0.0, 1.0 - (order_book.spread_bps / 50.0))
        quality_factors.append(spread_factor)
        
        # Balance factor (similar bid/ask levels = better quality)
        balance_factor = 1.0 - abs(order_book.bid_level_count - order_book.ask_level_count) / 10.0
        quality_factors.append(max(0.0, balance_factor))
        
        return statistics.mean(quality_factors)
    
    def _calculate_optimal_slice_size(self, order_size: int, liquidity_score: float) -> int:
        """Calculate optimal slice size for execution"""
        
        # Base slice size
        base_slice = self.impact_config.default_slice_size
        
        # Adjust for liquidity
        liquidity_multiplier = 1.0 + (1.0 - liquidity_score)  # Lower liquidity = larger slices
        
        # Calculate optimal slice
        optimal_slice = int(base_slice * liquidity_multiplier)
        
        # Ensure reasonable bounds
        return max(100, min(optimal_slice, order_size))
    
    def _calculate_optimal_execution_time(self, order_size: int, liquidity_score: float) -> int:
        """Calculate optimal execution time in seconds"""
        
        # Base time
        base_time = 10  # 10 seconds
        
        # Adjust for order size (larger orders need more time)
        size_factor = math.log10(max(order_size, 100))  # Logarithmic scaling
        
        # Adjust for liquidity (lower liquidity = more time)
        liquidity_factor = 1.0 + (1.0 - liquidity_score)
        
        # Calculate optimal time
        optimal_time = int(base_time * size_factor * liquidity_factor)
        
        # Ensure reasonable bounds
        return max(self.impact_config.min_execution_time, 
                  min(optimal_time, self.impact_config.max_execution_time))
    
    async def get_liquidity_analysis(self, symbol: str) -> Optional[LiquidityAnalysis]:
        """Get comprehensive liquidity analysis for a symbol"""
        
        try:
            # Check cache
            if symbol in self.liquidity_cache:
                cached = self.liquidity_cache[symbol]
                if (datetime.now(timezone.utc) - cached.timestamp).total_seconds() < 5.0:
                    return cached
            
            # Get order book data
            order_book = await self.order_book_manager.get_aggregated_order_book(symbol)
            if not order_book:
                return None
            
            # Perform liquidity analysis
            liquidity_analysis = await self._perform_liquidity_analysis(symbol, order_book)
            
            # Cache result
            self.liquidity_cache[symbol] = liquidity_analysis
            
            return liquidity_analysis
            
        except Exception as e:
            self.logger.error(f"Error analyzing liquidity for {symbol}: {e}")
            return None
    
    async def _perform_liquidity_analysis(self, symbol: str, order_book: OrderBookSnapshot) -> LiquidityAnalysis:
        """Perform comprehensive liquidity analysis"""
        
        # Calculate various liquidity scores
        bid_liquidity = self._calculate_side_liquidity(order_book.bid_levels, order_book.best_bid)
        ask_liquidity = self._calculate_side_liquidity(order_book.ask_levels, order_book.best_ask)
        
        # Overall liquidity
        overall_liquidity = (bid_liquidity + ask_liquidity) / 2
        
        # Volume-based liquidity (simplified)
        volume_liquidity = min(1.0, (order_book.total_bid_size + order_book.total_ask_size) / 50000)
        
        # Depth metrics
        total_depth_value = (order_book.total_bid_size + order_book.total_ask_size) * order_book.best_bid
        average_level_depth = (order_book.total_bid_size + order_book.total_ask_size) / max(1, order_book.bid_level_count + order_book.ask_level_count)
        
        # Depth concentration (how much liquidity is in top levels)
        top_levels = 3
        top_bid_size = sum(level.size for level in order_book.bid_levels[:top_levels])
        top_ask_size = sum(level.size for level in order_book.ask_levels[:top_levels])
        top_level_dominance = (top_bid_size + top_ask_size) / max(1, order_book.total_bid_size + order_book.total_ask_size)
        
        # Spread metrics
        spread_score = max(0.0, 1.0 - (order_book.spread_bps / 25.0))  # 25 bps = 0 score
        effective_spread = order_book.spread
        quoted_spread = order_book.spread
        
        # Volatility-adjusted metrics
        liquidity_stability = 0.8  # Simplified - could be based on historical volatility
        market_impact_resistance = overall_liquidity * (1 - order_book.spread_bps / 100.0)
        
        return LiquidityAnalysis(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            overall_liquidity=overall_liquidity,
            bid_liquidity=bid_liquidity,
            ask_liquidity=ask_liquidity,
            volume_liquidity=volume_liquidity,
            total_depth_value=total_depth_value,
            average_level_depth=average_level_depth,
            depth_concentration=top_level_dominance,
            top_level_dominance=top_level_dominance,
            spread_score=spread_score,
            effective_spread=effective_spread,
            quoted_spread=quoted_spread,
            liquidity_stability=liquidity_stability,
            market_impact_resistance=market_impact_resistance
        )
    
    def _calculate_side_liquidity(self, levels: List, reference_price: float) -> float:
        """Calculate liquidity score for one side of the order book"""
        
        if not levels or reference_price == 0:
            return 0.0
        
        # Calculate depth at different price levels
        total_size = sum(level.size for level in levels)
        
        # Normalize by reference price and expected size
        normalized_depth = (total_size * reference_price) / 100000  # Normalize to $100K
        
        return min(1.0, normalized_depth / 10.0)  # 10 = full score
    
    def _update_performance_metrics(self, calculation_time_ms: float):
        """Update performance tracking metrics"""
        
        self.calculation_count += 1
        
        # Update average calculation time
        self.average_calculation_time = (
            (self.average_calculation_time * (self.calculation_count - 1) + calculation_time_ms) / 
            self.calculation_count
        )
        
        # Update cache hit rate
        self.cache_hit_rate = (self.cache_hit_rate * (self.calculation_count - 1) + 0) / self.calculation_count
    
    async def _cache_cleanup_task(self):
        """Background task to cleanup expired cache entries"""
        while self.running:
            try:
                await asyncio.sleep(30)  # Cleanup every 30 seconds
                
                current_time = datetime.now(timezone.utc)
                
                # Clean impact cache
                expired_keys = []
                for key, calc in self.impact_cache.items():
                    if (current_time - calc.timestamp).total_seconds() > 5.0:
                        expired_keys.append(key)
                
                for key in expired_keys:
                    del self.impact_cache[key]
                
                # Clean liquidity cache
                expired_liquidity = []
                for symbol, analysis in self.liquidity_cache.items():
                    if (current_time - analysis.timestamp).total_seconds() > 60.0:
                        expired_liquidity.append(symbol)
                
                for symbol in expired_liquidity:
                    del self.liquidity_cache[symbol]
                
            except Exception as e:
                self.logger.error(f"Error in cache cleanup task: {e}")
                await asyncio.sleep(60)
    
    async def _metrics_task(self):
        """Background task to track metrics"""
        while self.running:
            try:
                await asyncio.sleep(60)  # Log metrics every minute
                
                self.logger.info(
                    f"Impact Calculator Metrics: {self.calculation_count} calculations, "
                    f"{self.average_calculation_time:.2f}ms avg time, "
                    f"{len(self.impact_cache)} cached impacts, "
                    f"{len(self.liquidity_cache)} cached liquidity analyses"
                )
                
            except Exception as e:
                self.logger.error(f"Error in metrics task: {e}")
                await asyncio.sleep(120)
    
    # Public API methods
    
    async def get_impact_metrics(self, symbol: str) -> Optional[MarketImpactMetrics]:
        """Get market impact metrics for a symbol"""
        
        try:
            # Get latest impact calculation
            cache_key = f"{symbol}_BUY_{self.impact_config.default_slice_size}"
            impact_calc = self.impact_cache.get(cache_key)
            
            if not impact_calc:
                # Calculate if not cached
                impact_calc = await self.calculate_impact(symbol, 'BUY', self.impact_config.default_slice_size)
            
            if not impact_calc:
                return None
            
            # Convert to MarketImpactMetrics
            return MarketImpactMetrics(
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                broker='AGGREGATED',
                estimated_impact_bps=impact_calc.estimated_impact_bps,
                liquidity_score=impact_calc.liquidity_score,
                slippage_estimate=impact_calc.slippage_estimate,
                market_impact_score=impact_calc.market_impact_score,
                depth_at_1pct=impact_calc.depth_at_1pct,
                depth_at_2pct=impact_calc.depth_at_2pct,
                depth_at_5pct=impact_calc.depth_at_5pct,
                effective_spread=impact_calc.effective_spread,
                spread_bps=impact_calc.spread_bps,
                price_level_count=impact_calc.price_level_count,
                average_level_size=impact_calc.average_level_size,
                data_freshness=impact_calc.data_freshness,
                broker_reliability=impact_calc.broker_reliability,
                calculation_quality=impact_calc.calculation_quality
            )
            
        except Exception as e:
            self.logger.error(f"Error getting impact metrics for {symbol}: {e}")
            return None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get calculator performance metrics"""
        
        return {
            'calculations_performed': self.calculation_count,
            'average_calculation_time_ms': self.average_calculation_time,
            'cache_hit_rate': self.cache_hit_rate,
            'cached_impacts': len(self.impact_cache),
            'cached_liquidity_analyses': len(self.liquidity_cache),
            'impact_history_size': len(self.impact_history)
        }
    
    def calculate_immediate_impact(self, symbol: str, side: str, quantity: int, order_book: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate immediate market impact for an order"""
        # Extract bid/ask data from order book dict
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        
        # Calculate best bid/ask
        best_bid = max((item['price'] for item in bids), default=0.0) if bids else 0.0
        best_ask = min((item['price'] for item in asks), default=0.0) if asks else 0.0
        
        # Calculate spread in basis points
        spread = best_ask - best_bid if best_bid > 0 else 0.0
        spread_bps = (spread / best_bid * 10000) if best_bid > 0 else 0.0
        
        # Calculate total liquidity
        relevant_side = asks if side == 'BUY' else bids
        available_liquidity = sum([item['size'] for item in relevant_side]) if relevant_side else 0
        
        # Calculate impact based on quantity vs liquidity
        # Simple formula: impact bps = base_spread + (quantity / liquidity) * impact_factor
        impact_factor = 100  # Adjust this for different impact models
        liquidity_impact = (quantity / max(available_liquidity, 1)) * impact_factor if available_liquidity > 0 else 0
        
        total_impact_bps = spread_bps + liquidity_impact
        
        # Calculate executed price
        if side == 'BUY':
            executed_price = best_ask * (1 + total_impact_bps / 10000)
        else:
            executed_price = best_bid * (1 - total_impact_bps / 10000)
        
        # Calculate slippage
        slippage = abs(executed_price - (best_ask if side == 'BUY' else best_bid))
        
        return {
            'estimated_impact_bps': total_impact_bps,
            'slippage_estimate': slippage,
            'executed_price': executed_price,
            'spread_bps': spread_bps,
            'liquidity_impact_bps': liquidity_impact,
            'available_liquidity': available_liquidity,
            'best_bid': best_bid,
            'best_ask': best_ask
        }
    
    def calculate_liquidity_score(self, symbol: str, order_book: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate liquidity metrics for an order book"""
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        
        # Calculate bid/ask liquidity
        bid_liquidity = sum([item['size'] for item in bids]) if bids else 0
        ask_liquidity = sum([item['size'] for item in asks]) if asks else 0
        total_liquidity = bid_liquidity + ask_liquidity
        
        # Calculate best bid/ask
        best_bid = max((item['price'] for item in bids), default=0.0) if bids else 0.0
        best_ask = min((item['price'] for item in asks), default=0.0) if asks else 0.0
        
        # Calculate spread in basis points
        spread = best_ask - best_bid if best_bid > 0 else 0.0
        spread_bps = (spread / best_bid * 10000) if best_bid > 0 else 0.0
        
        # Calculate liquidity score (0-1)
        # Based on total liquidity and spread
        # Higher liquidity = higher score, lower spread = higher score
        max_liquidity = 1000000  # Normalize to 1M units
        liquidity_ratio = min(total_liquidity / max_liquidity, 1.0)
        spread_penalty = min(spread_bps / 100, 1.0)  # Spread penalty max 1.0
        
        liquidity_score = liquidity_ratio * (1.0 - spread_penalty * 0.5)
        
        return {
            'liquidity_score': liquidity_score,
            'bid_liquidity': bid_liquidity,
            'ask_liquidity': ask_liquidity,
            'total_liquidity': total_liquidity,
            'spread_bps': spread_bps,
            'best_bid': best_bid,
            'best_ask': best_ask,
            'bid_levels': len(bids),
            'ask_levels': len(asks)
        }