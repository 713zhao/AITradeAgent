"""
Order Optimizer - Orchestrator for execution optimization

Coordinates execution algorithms, best execution checking, and smart routing.
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, Optional, List, Callable, Tuple

from .order_optimization import (
    ExecutionAlgorithm,
    ExecutionConfig,
    ExecutionSlice,
    ExecutionAnalysis,
    ExecutionQualityMetrics,
    BestExecutionChecker,
    SmartOrderRouter,
)
from .execution_algorithms import AlgorithmFactory, BaseAlgorithm

logger = logging.getLogger(__name__)


class OrderOptimizer:
    """
    Order Execution Optimizer.
    
    Orchestrates execution algorithms, best execution, and smart routing.
    """
    
    def __init__(
        self,
        brokers: Dict[str, any],
        benchmark_threshold_bps: float = 5.0
    ):
        """
        Initialize order optimizer.
        
        Args:
            brokers: Dict of available brokers {name: broker_instance}
            benchmark_threshold_bps: Best execution threshold
        """
        self.brokers = brokers
        self.algorithms: Dict[str, BaseAlgorithm] = {}
        self.active_orders: Dict[str, Dict] = {}  # order_id -> execution context
        
        # Optimization components
        self.best_exec_checker = BestExecutionChecker(benchmark_threshold_bps)
        self.smart_router = SmartOrderRouter(brokers)
        self.quality_metrics = ExecutionQualityMetrics()
        
        # Event callbacks
        self.on_slice_ready: Optional[Callable] = None  # (order_id, slice) -> None
        self.on_order_completed: Optional[Callable] = None  # (order_id, analysis) -> None
    
    def optimize_order(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        quantity: float,
        current_price: float,
        config: ExecutionConfig,
        market_data: Dict
    ) -> str:
        """
        Optimize order execution.
        
        Args:
            trade_id: Trade ID
            symbol: Stock symbol
            side: BUY or SELL
            quantity: Number of shares
            current_price: Current market price (arrival price)
            config: Execution configuration with algorithm choice
            market_data: Market data (volume, volatility, liquidity, etc.)
            
        Returns:
            Order ID for optimization tracking
        """
        order_id = f"OPT_{trade_id}_{uuid.uuid4().hex[:8]}"
        arrival_price = current_price
        
        # Select broker using smart routing
        selected_broker, routing_meta = self.smart_router.select_broker(
            symbol, side, quantity, current_price, market_data
        )
        
        # Create execution algorithm
        algorithm = AlgorithmFactory.create_algorithm(config)
        
        # Generate slices
        slices = algorithm.generate_slices(
            order_id, symbol, side, quantity, current_price, market_data
        )
        
        # Store order context
        self.active_orders[order_id] = {
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "target_price": current_price,
            "arrival_price": arrival_price,
            "algorithm": algorithm,
            "config": config,
            "selected_broker": selected_broker,
            "routing_meta": routing_meta,
            "slices": slices,
            "fills": [],
            "created_at": datetime.utcnow(),
        }
        
        self.algorithms[order_id] = algorithm
        
        logger.info(
            f"Optimized order {order_id}: {symbol} {side} {quantity:.0f} shares "
            f"using {config.algorithm.value} via {selected_broker}"
        )
        
        return order_id
    
    def get_next_slices(self, order_id: str, current_time: datetime = None) -> List[ExecutionSlice]:
        """Get slices ready for execution."""
        if current_time is None:
            current_time = datetime.utcnow()
        
        if order_id not in self.active_orders:
            return []
        
        order_ctx = self.active_orders[order_id]
        algorithm = order_ctx["algorithm"]
        
        # Check if algorithm wants to adjust slices
        if algorithm.should_adjust_slices({}):
            algorithm.adjust_slices({})
        
        # Get ready slices
        ready_slices = []
        for slice_ in algorithm.slices:
            if slice_.status == "PENDING" and slice_.scheduled_at <= current_time:
                ready_slices.append(slice_)
        
        return ready_slices
    
    def record_slice_fill(
        self,
        order_id: str,
        slice_id: str,
        filled_qty: float,
        fill_price: float,
        broker_order_id: str,
        broker: str
    ):
        """Record fill for a slice."""
        if order_id not in self.active_orders:
            logger.warning(f"Unknown order: {order_id}")
            return
        
        order_ctx = self.active_orders[order_id]
        algorithm = order_ctx["algorithm"]
        
        # Mark slice as filled
        algorithm.mark_slice_filled(slice_id, filled_qty, fill_price)
        
        # Record fill
        order_ctx["fills"].append({
            "slice_id": slice_id,
            "filled_qty": filled_qty,
            "fill_price": fill_price,
            "broker_order_id": broker_order_id,
            "broker": broker,
            "filled_at": datetime.utcnow(),
        })
        
        logger.info(
            f"Slice filled: {order_id}/{slice_id} "
            f"{filled_qty:.0f} @ ${fill_price:.2f}"
        )
        
        # Check if order complete
        if self._is_order_complete(order_id):
            self._finalize_order(order_id)
    
    def _is_order_complete(self, order_id: str) -> bool:
        """Check if order execution is complete."""
        if order_id not in self.active_orders:
            return False
        
        order_ctx = self.active_orders[order_id]
        algorithm = order_ctx["algorithm"]
        
        # All slices filled?
        total_filled = algorithm.get_total_filled()
        target_qty = order_ctx["quantity"]
        
        return total_filled >= target_qty * 0.99  # 99% fill threshold
    
    def _finalize_order(self, order_id: str):
        """Finalize order execution and analyze quality."""
        if order_id not in self.active_orders:
            return
        
        order_ctx = self.active_orders[order_id]
        algorithm = order_ctx["algorithm"]
        fills = order_ctx["fills"]
        
        # Create analysis
        analysis = ExecutionAnalysis(
            order_id=order_id,
            symbol=order_ctx["symbol"],
            side=order_ctx["side"],
            total_quantity=order_ctx["quantity"],
            target_price=order_ctx["target_price"],
            arrival_price=order_ctx["arrival_price"],
            total_filled_price=algorithm.get_average_price(),
            created_at=order_ctx["created_at"],
            submitted_at=order_ctx["created_at"],
            completed_at=datetime.utcnow(),
            total_time_seconds=(datetime.utcnow() - order_ctx["created_at"]).total_seconds(),
        )
        
        # Calculate metrics from fill history
        fill_history = [(f["fill_price"], f["filled_qty"]) for f in fills]
        analysis.calculate_metrics(fill_history)
        
        # Check best execution
        compliance = self.best_exec_checker.check_execution(analysis, {})
        
        # Record metrics
        self.quality_metrics.add_analysis(analysis)
        
        logger.info(
            f"Order completed: {order_id} "
            f"avg_fill=${analysis.total_filled_price:.2f} "
            f"shortfall={analysis.implementation_shortfall_bps:.2f}bps "
            f"efficiency={analysis.efficiency_ratio:.1f}%"
        )
        
        # Callback
        if self.on_order_completed:
            self.on_order_completed(order_id, analysis)
    
    def cancel_order(self, order_id: str) -> Dict:
        """Cancel order optimization."""
        if order_id not in self.active_orders:
            return {"error": "Order not found"}
        
        order_ctx = self.active_orders[order_id]
        algorithm = order_ctx["algorithm"]
        
        # Cancel pending slices
        cancelled_count = 0
        for slice_ in algorithm.slices:
            if slice_.status == "PENDING":
                slice_.status = "CANCELLED"
                cancelled_count += 1
        
        logger.info(f"Cancelled {cancelled_count} pending slices for {order_id}")
        
        return {
            "order_id": order_id,
            "cancelled": cancelled_count,
            "status": "cancelled"
        }
    
    def get_order_status(self, order_id: str) -> Optional[Dict]:
        """Get order execution status."""
        if order_id not in self.active_orders:
            return None
        
        order_ctx = self.active_orders[order_id]
        algorithm = order_ctx["algorithm"]
        
        total_filled = algorithm.get_total_filled()
        total_qty = order_ctx["quantity"]
        progress_pct = (total_filled / total_qty * 100) if total_qty > 0 else 0.0
        
        return {
            "order_id": order_id,
            "trade_id": order_ctx["trade_id"],
            "symbol": order_ctx["symbol"],
            "side": order_ctx["side"],
            "total_quantity": total_qty,
            "filled_quantity": total_filled,
            "fill_progress": progress_pct,
            "fills_count": len(order_ctx["fills"]),
            "slices_total": len(algorithm.slices),
            "slices_pending": sum(1 for s in algorithm.slices if s.status == "PENDING"),
            "slices_filled": sum(1 for s in algorithm.slices if s.status == "FILLED"),
            "algorithm": order_ctx["config"].algorithm.value,
            "broker": order_ctx["selected_broker"],
            "created_at": order_ctx["created_at"].isoformat(),
            "elapsed_seconds": (datetime.utcnow() - order_ctx["created_at"]).total_seconds(),
        }
    
    def get_all_order_statuses(self) -> List[Dict]:
        """Get status for all active orders."""
        return [
            self.get_order_status(oid)
            for oid in self.active_orders.keys()
        ]
    
    def get_execution_metrics(self) -> Dict:
        """Get overall execution quality metrics."""
        return self.quality_metrics.get_efficiency_metrics()
    
    def get_best_execution_report(self) -> Dict:
        """Get best execution compliance report."""
        return self.best_exec_checker.get_compliance_summary()
    
    def get_smart_routing_report(self) -> Dict:
        """Get smart routing statistics."""
        return self.smart_router.get_routing_stats()
    
    def get_performance_summary(self) -> Dict:
        """Get overall performance summary."""
        return {
            "execution_metrics": self.get_execution_metrics(),
            "best_execution": self.get_best_execution_report(),
            "smart_routing": self.get_smart_routing_report(),
            "active_orders": len(self.active_orders),
            "total_algorithms_used": len(self.algorithms),
            "quality_metrics": self.quality_metrics.to_dict(),
        }


class OptimizationManager:
    """
    High-level manager for order optimization across portfolio.
    
    Coordinates multi-order optimization with constraints.
    """
    
    def __init__(self, brokers: Dict[str, any]):
        """Initialize optimization manager."""
        self.optimizer = OrderOptimizer(brokers)
        self.order_constraints: Dict[str, Dict] = {}
        self.market_impact_models: Dict[str, Callable] = {}
    
    def add_constraint(
        self,
        symbol: str,
        max_daily_volume_pct: float = 5.0,
        max_single_order_pct: float = 1.0
    ):
        """Add trading constraint for symbol."""
        self.order_constraints[symbol] = {
            "max_daily_volume_pct": max_daily_volume_pct,
            "max_single_order_pct": max_single_order_pct,
        }
    
    def check_constraint(
        self,
        symbol: str,
        quantity: float,
        market_volume: float
    ) -> Tuple[bool, str]:
        """
        Check if order respects constraints.
        
        Args:
            symbol: Stock symbol
            quantity: Order quantity
            market_volume: Daily market volume
            
        Returns:
            Tuple of (is_ok, reason)
        """
        if symbol not in self.order_constraints:
            return True, ""
        
        constraint = self.order_constraints[symbol]
        order_pct = (quantity / market_volume) * 100
        
        # Check single order constraint
        if order_pct > constraint["max_single_order_pct"]:
            return False, (
                f"Order {order_pct:.2f}% > max {constraint['max_single_order_pct']}%"
            )
        
        return True, ""
    
    def optimize_portfolio_orders(
        self,
        orders: List[Dict],
        market_data: Dict
    ) -> List[str]:
        """
        Optimize multiple orders considering market impact.
        
        Args:
            orders: List of order dicts {trade_id, symbol, side, quantity, current_price}
            market_data: Market data dict
            
        Returns:
            List of optimization order IDs
        """
        order_ids = []
        
        for order in orders:
            symbol = order["symbol"]
            quantity = order["quantity"]
            market_volume = market_data.get(f"{symbol}_volume", quantity * 100)
            
            # Check constraint
            ok, reason = self.check_constraint(symbol, quantity, market_volume)
            if not ok:
                logger.warning(f"Order violates constraint: {reason}")
                continue
            
            # Create default config if not provided
            config = order.get("config")
            if not config:
                config = ExecutionConfig(algorithm=ExecutionAlgorithm.TWAP)
            
            # Optimize order
            opt_id = self.optimizer.optimize_order(
                trade_id=order["trade_id"],
                symbol=symbol,
                side=order["side"],
                quantity=quantity,
                current_price=order["current_price"],
                config=config,
                market_data=market_data,
            )
            
            order_ids.append(opt_id)
        
        logger.info(f"Optimized {len(order_ids)} portfolio orders")
        
        return order_ids
