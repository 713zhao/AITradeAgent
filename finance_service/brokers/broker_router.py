"""
Broker Router

This module provides intelligent order routing across multiple brokers,
supporting various routing strategies, dynamic broker selection, and performance optimization.

Key Features:
- Intelligent order routing strategies
- Dynamic broker selection based on performance
- Load balancing across brokers
- Failover and redundancy handling
- Real-time market data integration
- Performance monitoring and optimization

Author: PicotradeAgent
Version: 6.3.0
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import statistics

from finance_service.brokers.multi_broker_manager import (
    BrokerType, RoutingStrategy, AssetClass, BrokerHealthStatus, BrokerCapability
)
from finance_service.brokers.base_broker import BaseBroker, OrderResult, MarketData
from finance_service.core.data_types import OrderRequest


class RoutingDecision(str, Enum):
    """Routing decision outcomes"""
    ROUTED = "ROUTED"
    FAILED = "FAILED"
    RETRY = "RETRY"
    FALLBACK = "FALLBACK"


@dataclass
class RoutingMetrics:
    """Routing performance metrics"""
    total_orders: int = 0
    successful_orders: int = 0
    failed_orders: int = 0
    avg_latency_ms: float = 0.0
    best_latency_ms: float = float('inf')
    worst_latency_ms: float = 0.0
    avg_slippage_bps: float = 0.0
    total_slippage_bps: float = 0.0
    price_improvement_count: int = 0
    last_updated: datetime = field(default_factory=datetime.now)
    
    @property
    def success_rate(self) -> float:
        if self.total_orders == 0:
            return 0.0
        return self.successful_orders / self.total_orders
    
    @property
    def avg_price_improvement_bps(self) -> float:
        if self.price_improvement_count == 0:
            return 0.0
        return self.total_slippage_bps / self.price_improvement_count


@dataclass
class BrokerPerformance:
    """Broker performance tracking"""
    broker_type: BrokerType
    routing_metrics: RoutingMetrics = field(default_factory=RoutingMetrics)
    order_times: List[float] = field(default_factory=list)
    latency_history: List[float] = field(default_factory=list)
    error_history: List[str] = field(default_factory=list)
    price_history: Dict[str, float] = field(default_factory=dict)  # symbol -> price
    last_order_time: Optional[datetime] = None
    consecutive_errors: int = 0
    total_volume_traded: float = 0.0
    
    def update_latency(self, latency_ms: float):
        """Update latency metrics"""
        self.latency_history.append(latency_ms)
        # Keep only recent history
        if len(self.latency_history) > 100:
            self.latency_history = self.latency_history[-50:]
        
        # Update routing metrics
        metrics = self.routing_metrics
        metrics.avg_latency_ms = statistics.mean(self.latency_history)
        metrics.best_latency_ms = min(self.latency_history)
        metrics.worst_latency_ms = max(self.latency_history)
    
    def record_order(self, success: bool, latency_ms: float, error: Optional[str] = None):
        """Record order execution"""
        self.order_times.append(time.time())
        self.last_order_time = datetime.now()
        
        # Update metrics
        metrics = self.routing_metrics
        metrics.total_orders += 1
        
        if success:
            metrics.successful_orders += 1
            self.consecutive_errors = 0
            self.update_latency(latency_ms)
        else:
            metrics.failed_orders += 1
            self.consecutive_errors += 1
            if error:
                self.error_history.append(error)
                # Keep only recent errors
                if len(self.error_history) > 20:
                    self.error_history = self.error_history[-10:]
        
        # Keep only recent order times
        if len(self.order_times) > 1000:
            self.order_times = self.order_times[-500:]
    
    def is_overloaded(self) -> bool:
        """Check if broker is overloaded"""
        if not self.order_times:
            return False
        
        # Check orders in last minute
        recent_orders = [
            t for t in self.order_times 
            if time.time() - t < 60
        ]
        
        # If more than 30 orders in last minute, consider overloaded
        return len(recent_orders) > 30
    
    def get_reliability_score(self) -> float:
        """Calculate reliability score (0.0 to 1.0)"""
        metrics = self.routing_metrics
        if metrics.total_orders == 0:
            return 1.0
        
        # Base score on success rate
        success_score = metrics.success_rate
        
        # Penalize for consecutive errors
        error_penalty = min(self.consecutive_errors * 0.1, 0.5)
        
        # Penalize for high latency
        latency_penalty = 0.0
        if metrics.avg_latency_ms > 1000:  # > 1 second
            latency_penalty = min((metrics.avg_latency_ms - 1000) / 4000, 0.3)
        
        return max(0.0, success_score - error_penalty - latency_penalty)


@dataclass
class MarketDataSnapshot:
    """Market data snapshot for routing decisions"""
    symbol: str
    bid: float
    ask: float
    last: float
    volume: int
    timestamp: datetime
    source_broker: BrokerType
    
    @property
    def mid_price(self) -> float:
        return (self.bid + self.ask) / 2
    
    @property
    def spread_bps(self) -> float:
        if self.mid_price == 0:
            return 0
        return ((self.ask - self.bid) / self.mid_price) * 10000


@dataclass
class RoutingRequest:
    """Routing request"""
    order_request: OrderRequest
    preferred_brokers: List[BrokerType] = field(default_factory=list)
    max_latency_ms: float = 1000.0
    min_reliability_score: float = 0.8
    require_price_improvement: bool = False
    max_slippage_bps: float = 10.0  # 10 basis points = 0.1%
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.order_request.symbol,
            "side": self.order_request.side.value,
            "quantity": self.order_request.quantity,
            "order_type": self.order_request.order_type.value,
            "preferred_brokers": [b.value for b in self.preferred_brokers],
            "max_latency_ms": self.max_latency_ms,
            "min_reliability_score": self.min_reliability_score,
            "require_price_improvement": self.require_price_improvement,
            "max_slippage_bps": self.max_slippage_bps
        }


@dataclass
class RoutingResult:
    """Routing result"""
    decision: RoutingDecision
    selected_broker: Optional[BrokerType] = None
    order_result: Optional[OrderResult] = None
    latency_ms: float = 0.0
    price_improvement_bps: float = 0.0
    reasoning: str = ""
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "selected_broker": self.selected_broker.value if self.selected_broker else None,
            "order_id": self.order_result.order_id if self.order_result else None,
            "success": self.order_result.success if self.order_result else False,
            "latency_ms": self.latency_ms,
            "price_improvement_bps": self.price_improvement_bps,
            "reasoning": self.reasoning,
            "alternatives": self.alternatives,
            "timestamp": self.timestamp.isoformat()
        }


class BrokerRouter:
    """
    Broker Router
    
    Provides intelligent order routing across multiple brokers with performance optimization,
    load balancing, and dynamic broker selection based on real-time conditions.
    """
    
    def __init__(self, event_manager):
        self.event_manager = event_manager
        self.logger = logging.getLogger(f"{__name__}.BrokerRouter")
        
        # Broker management
        self.brokers: Dict[BrokerType, BaseBroker] = {}
        self.broker_capabilities: Dict[BrokerType, BrokerCapability] = {}
        self.broker_performance: Dict[BrokerType, BrokerPerformance] = {}
        
        # Market data cache
        self.market_data_cache: Dict[str, Dict[BrokerType, MarketDataSnapshot]] = {}
        
        # Routing configuration
        self.routing_strategy: RoutingStrategy = RoutingStrategy.BEST_PRICE
        self.max_concurrent_orders: int = 100
        self.order_timeout: float = 30.0
        
        # Performance tracking
        self.routing_history: List[RoutingResult] = []
        self.total_routed_orders: int = 0
        self.successful_routes: int = 0
        
        # Threading
        self.executor = ThreadPoolExecutor(max_workers=3)
        self._shutdown_event = asyncio.Event()
        
        # Performance optimization
        self._routing_cache: Dict[str, BrokerType] = {}
        self._cache_ttl_seconds: int = 30
        
        self.logger.info("Broker Router initialized")
    
    def register_broker(self, broker_type: BrokerType, broker: BaseBroker, capability: BrokerCapability):
        """Register a broker with the router"""
        try:
            self.brokers[broker_type] = broker
            self.broker_capabilities[broker_type] = capability
            self.broker_performance[broker_type] = BrokerPerformance(broker_type=broker_type)
            
            self.logger.info(f"Registered broker: {broker_type.value}")
            
        except Exception as e:
            self.logger.error(f"Error registering broker {broker_type.value}: {e}")
    
    def unregister_broker(self, broker_type: BrokerType):
        """Unregister a broker"""
        try:
            if broker_type in self.brokers:
                del self.brokers[broker_type]
            if broker_type in self.broker_capabilities:
                del self.broker_capabilities[broker_type]
            if broker_type in self.broker_performance:
                del self.broker_performance[broker_type]
            if broker_type in self.market_data_cache:
                del self.market_data_cache[broker_type]
            
            self.logger.info(f"Unregistered broker: {broker_type.value}")
            
        except Exception as e:
            self.logger.error(f"Error unregistering broker {broker_type.value}: {e}")
    
    async def route_order(self, routing_request: RoutingRequest) -> RoutingResult:
        """
        Route an order to the best broker
        
        Args:
            routing_request: Routing request with order and preferences
            
        Returns:
            RoutingResult: Routing result with decision and broker selection
        """
        try:
            start_time = time.time()
            symbol = routing_request.order_request.symbol
            
            self.logger.info(f"Routing order: {symbol} {routing_request.order_request.side.value}")
            
            # Check routing cache first
            cache_key = self._get_cache_key(routing_request)
            if cache_key in self._routing_cache:
                cached_broker = self._routing_cache[cache_key]
                if await self._is_broker_suitable(cached_broker, routing_request):
                    self.logger.debug(f"Using cached broker selection: {cached_broker.value}")
                    return await self._execute_routing(routing_request, cached_broker, start_time)
            
            # Get suitable brokers
            suitable_brokers = await self._get_suitable_brokers(routing_request)
            
            if not suitable_brokers:
                self.logger.warning(f"No suitable brokers found for {symbol}")
                return RoutingResult(
                    decision=RoutingDecision.FAILED,
                    reasoning="No suitable brokers available",
                    timestamp=datetime.now()
                )
            
            # Select best broker based on strategy
            selected_broker = await self._select_best_broker(suitable_brokers, routing_request)
            
            if not selected_broker:
                self.logger.warning(f"Could not select broker for {symbol}")
                return RoutingResult(
                    decision=RoutingDecision.FAILED,
                    reasoning="Could not select suitable broker",
                    timestamp=datetime.now()
                )
            
            # Execute routing
            result = await self._execute_routing(routing_request, selected_broker, start_time)
            
            # Update cache
            if result.decision == RoutingDecision.ROUTED:
                self._routing_cache[cache_key] = selected_broker
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error routing order: {e}")
            return RoutingResult(
                decision=RoutingDecision.FAILED,
                reasoning=f"Routing error: {e}",
                timestamp=datetime.now()
            )
    
    async def _execute_routing(self, routing_request: RoutingRequest, 
                             broker_type: BrokerType, start_time: float) -> RoutingResult:
        """Execute the actual routing to selected broker"""
        try:
            broker = self.brokers[broker_type]
            
            # Execute order
            order_result = await broker.place_order(routing_request.order_request)
            
            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000
            
            # Record performance
            performance = self.broker_performance[broker_type]
            success = order_result.success if order_result else False
            performance.record_order(success, latency_ms, order_result.error_message if order_result else "Unknown error")
            
            # Calculate price improvement if possible
            price_improvement_bps = 0.0
            if success and routing_request.order_request.limit_price:
                price_improvement_bps = await self._calculate_price_improvement(
                    routing_request.order_request.symbol, broker_type, routing_request.order_request
                )
            
            # Create result
            result = RoutingResult(
                decision=RoutingDecision.ROUTED if success else RoutingDecision.FAILED,
                selected_broker=broker_type,
                order_result=order_result,
                latency_ms=latency_ms,
                price_improvement_bps=price_improvement_bps,
                reasoning=f"Routed to {broker_type.value}",
                timestamp=datetime.now()
            )
            
            # Update statistics
            self.total_routed_orders += 1
            if success:
                self.successful_routes += 1
            
            # Add to history
            self.routing_history.append(result)
            if len(self.routing_history) > 1000:
                self.routing_history = self.routing_history[-500:]
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error executing routing: {e}")
            return RoutingResult(
                decision=RoutingDecision.FAILED,
                selected_broker=broker_type,
                reasoning=f"Execution error: {e}",
                timestamp=datetime.now()
            )
    
    async def _get_suitable_brokers(self, routing_request: RoutingRequest) -> List[BrokerType]:
        """Get list of suitable brokers for the routing request"""
        suitable_brokers = []
        symbol = routing_request.order_request.symbol
        
        for broker_type, broker in self.brokers.items():
            try:
                # Check if broker is connected
                if not broker.is_connected():
                    continue
                
                # Check capabilities
                capability = self.broker_capabilities[broker_type]
                
                # Check if broker supports the asset class
                asset_class = self._determine_asset_class(symbol)
                if asset_class not in capability.asset_classes:
                    continue
                
                # Check if broker supports the order type
                if routing_request.order_request.order_type not in capability.order_types:
                    continue
                
                # Check performance
                performance = self.broker_performance[broker_type]
                
                # Check reliability score
                reliability_score = performance.get_reliability_score()
                if reliability_score < routing_request.min_reliability_score:
                    continue
                
                # Check if not overloaded
                if performance.is_overloaded():
                    continue
                
                # Check latency
                if capability.latency_ms > routing_request.max_latency_ms:
                    continue
                
                # Check preferred brokers
                if routing_request.preferred_brokers and broker_type not in routing_request.preferred_brokers:
                    continue
                
                # Check order size limits
                if routing_request.order_request.quantity > capability.max_order_size:
                    continue
                
                if routing_request.order_request.quantity < capability.min_order_size:
                    continue
                
                suitable_brokers.append(broker_type)
                
            except Exception as e:
                self.logger.error(f"Error checking broker suitability for {broker_type.value}: {e}")
                continue
        
        return suitable_brokers
    
    async def _select_best_broker(self, suitable_brokers: List[BrokerType], 
                                routing_request: RoutingRequest) -> Optional[BrokerType]:
        """Select the best broker from suitable options"""
        if not suitable_brokers:
            return None
        
        if len(suitable_brokers) == 1:
            return suitable_brokers[0]
        
        # Apply routing strategy
        if self.routing_strategy == RoutingStrategy.BEST_PRICE:
            return await self._select_best_price_broker(suitable_brokers, routing_request)
        elif self.routing_strategy == RoutingStrategy.LEAST_LOAD:
            return self._select_least_loaded_broker(suitable_brokers)
        elif self.routing_strategy == RoutingStrategy.ROUND_ROBIN:
            return self._select_round_robin_broker(suitable_brokers)
        elif self.routing_strategy == RoutingStrategy.PREFERRED:
            return self._select_preferred_broker(suitable_brokers, routing_request)
        else:
            # Default to best reliability
            return self._select_most_reliable_broker(suitable_brokers)
    
    async def _select_best_price_broker(self, brokers: List[BrokerType], 
                                      routing_request: RoutingRequest) -> Optional[BrokerType]:
        """Select broker with best price"""
        symbol = routing_request.order_request.symbol
        best_broker = None
        best_score = float('-inf')
        
        for broker_type in brokers:
            try:
                score = await self._calculate_price_score(broker_type, symbol, routing_request)
                if score > best_score:
                    best_score = score
                    best_broker = broker_type
            except Exception as e:
                self.logger.error(f"Error calculating price score for {broker_type.value}: {e}")
                continue
        
        return best_broker
    
    def _select_least_loaded_broker(self, brokers: List[BrokerType]) -> BrokerType:
        """Select broker with least load"""
        return min(brokers, key=lambda b: self.broker_performance[b].routing_metrics.total_orders)
    
    def _select_round_robin_broker(self, brokers: List[BrokerType]) -> BrokerType:
        """Select broker using round-robin"""
        # Simple round-robin based on total orders
        return min(brokers, key=lambda b: self.broker_performance[b].last_order_time or datetime.min)
    
    def _select_preferred_broker(self, brokers: List[BrokerType], 
                               routing_request: RoutingRequest) -> Optional[BrokerType]:
        """Select preferred broker"""
        # Check if any preferred brokers are available
        for preferred in routing_request.preferred_brokers:
            if preferred in brokers:
                return preferred
        
        # Otherwise, select most reliable
        return self._select_most_reliable_broker(brokers)
    
    def _select_most_reliable_broker(self, brokers: List[BrokerType]) -> BrokerType:
        """Select most reliable broker"""
        return max(brokers, key=lambda b: self.broker_performance[b].get_reliability_score())
    
    async def _calculate_price_score(self, broker_type: BrokerType, symbol: str, 
                                   routing_request: RoutingRequest) -> float:
        """Calculate price score for broker"""
        try:
            # Get market data from broker
            broker = self.brokers[broker_type]
            if symbol not in broker.market_data_cache:
                return 0.0
            
            data = broker.market_data_cache[symbol]
            if data.bid <= 0 or data.ask <= 0:
                return 0.0
            
            # Calculate score based on spread and price level
            mid_price = (data.bid + data.ask) / 2
            spread_bps = ((data.ask - data.bid) / mid_price) * 10000
            
            # Lower spread = higher score
            spread_score = max(0, 10 - spread_bps / 10)  # Scale spread to 0-10
            
            # Price level preference (prefer prices closer to mid)
            if routing_request.order_request.limit_price:
                price_diff = abs(routing_request.order_request.limit_price - mid_price)
                price_score = max(0, 10 - price_diff / mid_price * 1000)
            else:
                price_score = 5.0  # Neutral score for market orders
            
            # Performance score
            performance = self.broker_performance[broker_type]
            perf_score = performance.get_reliability_score() * 10
            
            total_score = spread_score + price_score + perf_score
            return total_score
            
        except Exception as e:
            self.logger.error(f"Error calculating price score for {broker_type.value}: {e}")
            return 0.0
    
    async def _calculate_price_improvement(self, symbol: str, broker_type: BrokerType, 
                                         order_request: OrderRequest) -> float:
        """Calculate price improvement in basis points"""
        try:
            if not order_request.limit_price:
                return 0.0
            
            broker = self.brokers[broker_type]
            if symbol not in broker.market_data_cache:
                return 0.0
            
            data = broker.market_data_cache[symbol]
            mid_price = (data.bid + data.ask) / 2
            
            if mid_price == 0:
                return 0.0
            
            # Calculate improvement based on order side
            if order_request.side.value.upper() == "BUY":
                # For buy orders, improvement if limit price > market price
                improvement = (order_request.limit_price - mid_price) / mid_price
            else:
                # For sell orders, improvement if limit price < market price
                improvement = (mid_price - order_request.limit_price) / mid_price
            
            # Convert to basis points
            return improvement * 10000
            
        except Exception as e:
            self.logger.error(f"Error calculating price improvement: {e}")
            return 0.0
    
    def _determine_asset_class(self, symbol: str) -> AssetClass:
        """Determine asset class from symbol"""
        symbol_upper = symbol.upper()
        
        # Crypto detection
        crypto_symbols = ['BTC', 'ETH', 'LTC', 'XRP', 'ADA', 'DOT', 'USDT', 'USDC']
        if any(crypto in symbol_upper for crypto in crypto_symbols) or '_' in symbol:
            return AssetClass.CRYPTO
        
        # Options detection
        if len(symbol_upper) > 4 and any(c in symbol_upper for c in ['C', 'P']):
            return AssetClass.OPTION
        
        # Futures detection
        futures_symbols = ['ES', 'NQ', 'YM', 'RTY', 'CL', 'GC', 'SI']
        if any(future in symbol_upper for future in futures_symbols):
            return AssetClass.FUTURE
        
        # Default to stocks
        return AssetClass.STOCK
    
    def _get_cache_key(self, routing_request: RoutingRequest) -> str:
        """Generate cache key for routing request"""
        return f"{routing_request.order_request.symbol}_{routing_request.order_request.side.value}_{routing_request.order_request.quantity}_{routing_request.order_request.order_type.value}"
    
    async def _is_broker_suitable(self, broker_type: BrokerType, routing_request: RoutingRequest) -> bool:
        """Check if cached broker is still suitable"""
        try:
            if broker_type not in self.brokers:
                return False
            
            broker = self.brokers[broker_type]
            if not broker.is_connected():
                return False
            
            # Check recent performance
            performance = self.broker_performance[broker_type]
            if performance.consecutive_errors > 3:
                return False
            
            # Check if broker is overloaded
            if performance.is_overloaded():
                return False
            
            return True
            
        except Exception:
            return False
    
    async def update_market_data(self, symbol: str, broker_type: BrokerType, market_data: MarketData):
        """Update market data cache"""
        try:
            if symbol not in self.market_data_cache:
                self.market_data_cache[symbol] = {}
            
            self.market_data_cache[symbol][broker_type] = MarketDataSnapshot(
                symbol=symbol,
                bid=market_data.bid,
                ask=market_data.ask,
                last=market_data.last,
                volume=market_data.volume,
                timestamp=market_data.timestamp,
                source_broker=broker_type
            )
            
            # Clean old data
            cutoff_time = datetime.now() - timedelta(seconds=300)
            for sym in list(self.market_data_cache.keys()):
                for btype in list(self.market_data_cache[sym].keys()):
                    if self.market_data_cache[sym][btype].timestamp < cutoff_time:
                        del self.market_data_cache[sym][btype]
                
                if not self.market_data_cache[sym]:
                    del self.market_data_cache[sym]
            
        except Exception as e:
            self.logger.error(f"Error updating market data cache: {e}")
    
    def get_routing_performance(self) -> Dict[str, Any]:
        """Get routing performance statistics"""
        return {
            "total_routed_orders": self.total_routed_orders,
            "successful_routes": self.successful_routes,
            "success_rate": self.successful_routes / self.total_routed_orders if self.total_routed_orders > 0 else 0.0,
            "broker_performance": {
                broker_type.value: {
                    "total_orders": perf.routing_metrics.total_orders,
                    "success_rate": perf.routing_metrics.success_rate,
                    "avg_latency_ms": perf.routing_metrics.avg_latency_ms,
                    "reliability_score": perf.get_reliability_score(),
                    "consecutive_errors": perf.consecutive_errors,
                    "is_overloaded": perf.is_overloaded()
                }
                for broker_type, perf in self.broker_performance.items()
            },
            "routing_strategy": self.routing_strategy.value,
            "recent_routes": len([r for r in self.routing_history if (datetime.now() - r.timestamp).total_seconds() < 3600]),
            "cache_size": len(self._routing_cache)
        }
    
    def get_recent_routes(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent routing decisions"""
        return [result.to_dict() for result in self.routing_history[-limit:]]
    
    def set_routing_strategy(self, strategy: RoutingStrategy):
        """Set routing strategy"""
        self.routing_strategy = strategy
        self.logger.info(f"Routing strategy set to: {strategy.value}")
    
    async def close(self):
        """Close the router"""
        self._shutdown_event.set()
        self.logger.info("Broker Router closed")