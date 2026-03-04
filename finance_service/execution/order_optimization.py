"""
Order Optimization Framework - Phase 6.5

Advanced execution strategies:
- Execution algorithms (TWAP, VWAP, ICEBERG)
- Smart order routing (multi-venue)
- Best execution checking
- Partial fill aggregation
- Slippage analysis and optimization
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ExecutionAlgorithm(Enum):
    """Execution algorithm types."""
    MARKET = "market"          # Execute immediately
    TWAP = "twap"              # Time-Weighted Average Price
    VWAP = "vwap"              # Volume-Weighted Average Price
    ICEBERG = "iceberg"        # Hide full order quantity
    ARRIVAL_PRICE = "arrival"  # Match arrival price
    IMPLEMENTATION_SHORTFALL = "impl_shortfall"  # Minimize shortfall


@dataclass
class ExecutionConfig:
    """Configuration for order execution."""
    algorithm: ExecutionAlgorithm
    
    # Algorithm parameters
    time_window_minutes: int = 5          # Time to spread execution
    iceberg_chunk_size: int = 0           # Chunk size for iceberg (0 = auto)
    max_participation_rate: float = 0.2   # Max % of market volume
    target_arrival_price: Optional[float] = None  # For arrival price algo
    
    # Execution limits
    max_acceptable_slippage_bps: float = 5.0  # 5 basis points
    max_acceptable_slippage_pct: float = 0.5   # 0.5%
    max_execution_time_seconds: int = 300  # 5 minutes
    
    # Broker preferences
    preferred_brokers: List[str] = field(default_factory=list)  # e.g., ["paper", "alpaca"]
    diversify_venues: bool = False  # Split across multiple venues
    
    def to_dict(self) -> Dict:
        """Serialize configuration."""
        return {
            "algorithm": self.algorithm.value,
            "time_window_minutes": self.time_window_minutes,
            "iceberg_chunk_size": self.iceberg_chunk_size,
            "max_participation_rate": self.max_participation_rate,
            "max_acceptable_slippage_bps": self.max_acceptable_slippage_bps,
            "max_execution_time_seconds": self.max_execution_time_seconds,
        }


@dataclass
class ExecutionSlice:
    """Single execution slice (child order)."""
    slice_id: str
    parent_order_id: str
    symbol: str
    side: str  # BUY or SELL
    quantity: float
    target_price: float
    estimated_arrival_price: float
    
    # Execution tracking
    submitted_at: datetime
    scheduled_at: datetime
    executed_at: Optional[datetime] = None
    
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    execution_cost: float = 0.0
    
    # Status
    status: str = "PENDING"  # PENDING, SUBMITTED, FILLED, CANCELLED
    broker: Optional[str] = None
    broker_order_id: Optional[str] = None
    
    def get_execution_price(self) -> float:
        """Get actual execution price."""
        return self.filled_price if self.filled_quantity > 0 else self.target_price
    
    def get_slippage_bps(self) -> float:
        """Calculate slippage in basis points."""
        if not self.filled_quantity or not self.target_price:
            return 0.0
        
        actual = self.filled_price
        target = self.target_price
        
        # For BUY: slippage = (actual - target) / target * 10000
        # For SELL: slippage = (target - actual) / target * 10000
        if self.side == "BUY":
            slippage = (actual - target) / target * 10000
        else:
            slippage = (target - actual) / target * 10000
        
        return max(0.0, slippage)  # Only positive slippage counts
    
    def to_dict(self) -> Dict:
        """Serialize execution slice."""
        return {
            "slice_id": self.slice_id,
            "parent_order_id": self.parent_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "target_price": self.target_price,
            "filled_quantity": self.filled_quantity,
            "filled_price": self.filled_price,
            "status": self.status,
            "slippage_bps": self.get_slippage_bps(),
        }


@dataclass
class ExecutionAnalysis:
    """Analysis of execution quality."""
    order_id: str
    symbol: str
    side: str
    total_quantity: float
    
    # Execution details
    target_price: float  # Entry price when decision made
    arrival_price: float  # Market price at order submission
    total_filled_price: float  # Weighted avg of all fills
    
    # Timing
    created_at: datetime
    submitted_at: datetime
    completed_at: datetime
    total_time_seconds: float
    
    # Costs
    target_cost: float = 0.0  # What we expected to pay
    actual_cost: float = 0.0  # What we actually paid
    execution_cost: float = 0.0  # Difference
    
    # Slippage analysis
    arrival_slippage_bps: float = 0.0  # vs arrival price
    implementation_shortfall_bps: float = 0.0  # vs target price
    
    # Execution efficiency
    efficiency_ratio: float = 0.0  # 0-100%, higher is better
    market_impact_bps: float = 0.0  # Estimated market impact
    
    # Partial fills
    num_fills: int = 0
    largest_fill: float = 0.0
    smallest_fill: float = 0.0
    
    def calculate_metrics(self, fills: List[Tuple[float, float]]):
        """Calculate execution metrics from fill history.
        
        Args:
            fills: List of (price, quantity) tuples
        """
        if not fills:
            return
        
        self.num_fills = len(fills)
        
        # Calculate weighted average fill price
        total_qty = sum(qty for _, qty in fills)
        total_value = sum(price * qty for price, qty in fills)
        self.total_filled_price = total_value / total_qty if total_qty > 0 else 0.0
        
        # Calculate min/max fills
        fill_qtys = [qty for _, qty in fills]
        self.largest_fill = max(fill_qtys) if fill_qtys else 0.0
        self.smallest_fill = min(fill_qtys) if fill_qtys else 0.0
        
        # Actual cost
        self.actual_cost = total_value
        
        # Target cost (what we expected at decision time)
        self.target_cost = self.total_quantity * self.target_price
        
        # Execution cost (difference)
        self.execution_cost = self.actual_cost - self.target_cost
        
        # Slippage calculations
        if self.target_price > 0:
            # Implementation shortfall: vs decision price
            if self.side == "BUY":
                self.implementation_shortfall_bps = (
                    (self.total_filled_price - self.target_price) / self.target_price * 10000
                )
            else:
                self.implementation_shortfall_bps = (
                    (self.target_price - self.total_filled_price) / self.target_price * 10000
                )
        
        if self.arrival_price > 0:
            # Arrival slippage: vs order submission price
            if self.side == "BUY":
                self.arrival_slippage_bps = (
                    (self.total_filled_price - self.arrival_price) / self.arrival_price * 10000
                )
            else:
                self.arrival_slippage_bps = (
                    (self.arrival_price - self.total_filled_price) / self.arrival_price * 10000
                )
        
        # Calculate efficiency ratio
        # How much better/worse did we execute vs target?
        if self.implementation_shortfall_bps <= 0:
            # Negative or zero shortfall = we got better than or equal to target = high efficiency
            self.efficiency_ratio = 100.0
        else:
            # Positive shortfall = we got worse than target
            # Efficiency decreases based on how much worse (max 100%)
            self.efficiency_ratio = max(0.0, 100.0 - (self.implementation_shortfall_bps * 2.0))
    
    def to_dict(self) -> Dict:
        """Serialize analysis."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "total_quantity": self.total_quantity,
            "target_price": self.target_price,
            "arrival_price": self.arrival_price,
            "total_filled_price": self.total_filled_price,
            "execution_cost": self.execution_cost,
            "execution_cost_pct": (self.execution_cost / self.target_cost * 100) if self.target_cost else 0.0,
            "arrival_slippage_bps": self.arrival_slippage_bps,
            "implementation_shortfall_bps": self.implementation_shortfall_bps,
            "efficiency_ratio": self.efficiency_ratio,
            "num_fills": self.num_fills,
            "total_time_seconds": self.total_time_seconds,
        }


class ExecutionQualityMetrics:
    """Tracks execution quality metrics across multiple oders."""
    
    def __init__(self):
        """Initialize metrics tracker."""
        self.analyses: Dict[str, ExecutionAnalysis] = {}
        self.created_at = datetime.utcnow()
    
    def add_analysis(self, analysis: ExecutionAnalysis):
        """Add execution analysis."""
        self.analyses[analysis.order_id] = analysis
        logger.info(
            f"Execution analysis: {analysis.symbol} {analysis.side} "
            f"slippage={analysis.implementation_shortfall_bps:.2f}bps "
            f"efficiency={analysis.efficiency_ratio:.1f}%"
        )
    
    def get_analysis(self, order_id: str) -> Optional[ExecutionAnalysis]:
        """Get analysis by order ID."""
        return self.analyses.get(order_id)
    
    def get_average_slippage_bps(self) -> float:
        """Get average slippage across all orders."""
        if not self.analyses:
            return 0.0
        
        total_slippage = sum(a.implementation_shortfall_bps for a in self.analyses.values())
        return total_slippage / len(self.analyses)
    
    def get_efficiency_metrics(self) -> Dict:
        """Get overall efficiency metrics."""
        if not self.analyses:
            return {
                "total_orders": 0,
                "avg_slippage_bps": 0.0,
                "avg_efficiency": 0.0,
                "best_executed": None,
                "worst_executed": None,
            }
        
        analyses = list(self.analyses.values())
        
        return {
            "total_orders": len(analyses),
            "avg_slippage_bps": self.get_average_slippage_bps(),
            "avg_efficiency": sum(a.efficiency_ratio for a in analyses) / len(analyses),
            "best_executed": min(analyses, key=lambda a: a.execution_cost).order_id,
            "worst_executed": max(analyses, key=lambda a: a.execution_cost).order_id,
            "total_execution_cost": sum(a.execution_cost for a in analyses),
        }
    
    def to_dict(self) -> Dict:
        """Serialize metrics."""
        return {
            "analyses": {oid: a.to_dict() for oid, a in self.analyses.items()},
            "metrics": self.get_efficiency_metrics(),
        }


class BestExecutionChecker:
    """Validates execution against best execution standards."""
    
    def __init__(self, benchmark_threshold_bps: float = 5.0):
        """
        Initialize best execution checker.
        
        Args:
            benchmark_threshold_bps: Slippage threshold (basis points)
        """
        self.benchmark_threshold_bps = benchmark_threshold_bps
        self.execution_count = 0
        self.violations = []
    
    def check_execution(
        self,
        analysis: ExecutionAnalysis,
        market_conditions: Dict
    ) -> Dict:
        """
        Check if execution meets best execution standards.
        
        Args:
            analysis: Execution analysis to check
            market_conditions: Market data (bid, ask, volume, volatility)
            
        Returns:
            Dict with compliance status and violations
        """
        self.execution_count += 1
        violations = []
        warnings = []
        
        # Check 1: Execution price quality
        arrival_slippage = abs(analysis.arrival_slippage_bps)
        if arrival_slippage > self.benchmark_threshold_bps:
            violations.append({
                "type": "SLIPPAGE_VIOLATION",
                "slippage_bps": arrival_slippage,
                "threshold_bps": self.benchmark_threshold_bps,
                "message": f"Slippage {arrival_slippage:.2f}bps exceeds threshold {self.benchmark_threshold_bps:.2f}bps"
            })
        
        # Check 2: Execution timing
        if analysis.total_time_seconds > 300:  # 5 minute limit
            warnings.append({
                "type": "TIMING_WARNING",
                "execution_time": analysis.total_time_seconds,
                "message": f"Execution took {analysis.total_time_seconds:.0f}s"
            })
        
        # Check 3: Market impact
        participation_rate = analysis.total_quantity / market_conditions.get("market_volume", 1e10)
        if participation_rate > 0.1:  # > 10% of typical volume
            warnings.append({
                "type": "MARKET_IMPACT",
                "participation_rate": participation_rate,
                "message": f"High market participation rate: {participation_rate:.1%}"
            })
        
        # Check 4: Volatility conditions
        if market_conditions.get("volatility_pct", 0) > 5.0:
            warnings.append({
                "type": "VOLATILITY_WARNING",
                "volatility": market_conditions.get("volatility_pct"),
                "message": "High volatility detected"
            })
        
        # Overall compliance
        is_compliant = len(violations) == 0
        
        if violations:
            self.violations.extend(violations)
            logger.warning(f"Best execution violations for {analysis.order_id}: {len(violations)}")
        
        return {
            "order_id": analysis.order_id,
            "compliant": is_compliant,
            "violations": violations,
            "warnings": warnings,
            "efficiency": analysis.efficiency_ratio,
            "arrival_slippage_bps": analysis.arrival_slippage_bps,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    def get_compliance_summary(self) -> Dict:
        """Get overall compliance summary."""
        if self.execution_count == 0:
            return {
                "total_executed": 0,
                "compliance_rate": 100.0,
                "violations_count": 0,
            }
        
        return {
            "total_executed": self.execution_count,
            "compliance_rate": (self.execution_count - len(self.violations)) / self.execution_count * 100,
            "violations_count": len(self.violations),
            "violations": self.violations[-10:],  # Last 10 violations
        }


class SmartOrderRouter:
    """Routes orders to best broker/venue based on conditions."""
    
    def __init__(self, brokers: Dict[str, any]):
        """
        Initialize router.
        
        Args:
            brokers: Dict mapping broker name to broker instance
                    e.g., {"paper": paper_broker, "alpaca": alpaca_broker}
        """
        self.brokers = brokers
        self.routing_history: List[Dict] = []
    
    def select_broker(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        market_data: Dict
    ) -> Tuple[str, Dict]:
        """
        Select best broker for order.
        
        Args:
            symbol: Stock symbol
            side: BUY or SELL
            quantity: Order quantity
            price: Target price
            market_data: Market info (spreads, liquidity, fees)
            
        Returns:
            Tuple of (broker_name, selection_metadata)
        """
        scores = {}
        
        for broker_name, broker in self.brokers.items():
            try:
                # Check if broker available
                if not broker or not hasattr(broker, 'get_cash'):
                    continue
                
                # Score broker
                score = self._score_broker(
                    broker_name, broker,
                    symbol, side, quantity, price,
                    market_data
                )
                scores[broker_name] = score
            
            except Exception as e:
                logger.warning(f"Could not score {broker_name}: {e}")
        
        if not scores:
            raise ValueError("No available brokers for order")
        
        # Select highest score
        best_broker = max(scores.items(), key=lambda x: x[1]["total_score"])
        
        metadata = {
            "selected_broker": best_broker[0],
            "score": best_broker[1],
            "all_scores": scores,
            "selected_at": datetime.utcnow().isoformat(),
        }
        
        self.routing_history.append(metadata)
        
        logger.info(f"Routed {symbol} to {best_broker[0]} (score: {best_broker[1]['total_score']:.2f})")
        
        return best_broker[0], metadata
    
    def _score_broker(
        self,
        broker_name: str,
        broker,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        market_data: Dict
    ) -> Dict:
        """Score a broker for the given order."""
        scores = {}
        
        # Score 1: Liquidity (availability of funds)
        try:
            buying_power = broker.get_buying_power()
            needed = quantity * price * 1.1  # 10% buffer for slippage
            liquidity_ok = buying_power >= needed
            scores["liquidity"] = 10.0 if liquidity_ok else 0.0
        except:
            scores["liquidity"] = 0.0
        
        # Score 2: Spread
        bid = market_data.get("bid", price * 0.999)
        ask = market_data.get("ask", price * 1.001)
        spread_bps = (ask - bid) / bid * 10000
        scores["spread"] = max(0, 10.0 - spread_bps)  # Tighter spread = higher score
        
        # Score 3: Slippage history
        avg_slippage = market_data.get("avg_slippage_bps", 1.0)
        scores["slippage"] = max(0, 10.0 - avg_slippage)
        
        # Score 4: Settlement time
        # Paper = instant (10), Alpaca = 1-2s (8)
        settlement_score = 10.0 if "paper" in broker_name.lower() else 8.0
        scores["settlement"] = settlement_score
        
        # Score 5: Fees
        estimated_fee = (quantity * price) * 0.001  # Rough estimate
        scores["fees"] = max(0, 10.0 - (estimated_fee / (quantity * price) * 100))
        
        # Total score (weighted)
        total_score = (
            scores["liquidity"] * 0.25 +
            scores["spread"] * 0.25 +
            scores["slippage"] * 0.25 +
            scores["settlement"] * 0.15 +
            scores["fees"] * 0.10
        )
        
        scores["total_score"] = total_score
        
        return scores
    
    def get_routing_stats(self) -> Dict:
        """Get routing statistics."""
        if not self.routing_history:
            return {"total_routed": 0}
        
        broker_counts = {}
        for route in self.routing_history:
            broker = route.get("selected_broker")
            broker_counts[broker] = broker_counts.get(broker, 0) + 1
        
        return {
            "total_routed": len(self.routing_history),
            "broker_distribution": broker_counts,
            "last_route": self.routing_history[-1] if self.routing_history else None,
        }
