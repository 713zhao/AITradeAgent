"""Phase 5: Trade Execution & Monitoring
Phase 6.5: Order Optimization
"""

from finance_service.execution.execution_engine import ExecutionEngine
from finance_service.execution.trade_monitor import TradeMonitor
from finance_service.execution.performance_reporter import PerformanceReporter

# Phase 6.5: Order Optimization
from finance_service.execution.order_optimization import (
    ExecutionAlgorithm,
    ExecutionConfig,
    ExecutionSlice,
    ExecutionAnalysis,
    ExecutionQualityMetrics,
    BestExecutionChecker,
    SmartOrderRouter,
)
from finance_service.execution.execution_algorithms import (
    BaseAlgorithm,
    TWAPAlgorithm,
    VWAPAlgorithm,
    IcebergAlgorithm,
    ArrivalPriceAlgorithm,
    AlgorithmFactory,
)
from finance_service.execution.order_optimizer import (
    OrderOptimizer,
    OptimizationManager,
)

__all__ = [
    # Phase 5
    "ExecutionEngine",
    "TradeMonitor", 
    "PerformanceReporter",
    # Phase 6.5
    "ExecutionAlgorithm",
    "ExecutionConfig",
    "ExecutionSlice",
    "ExecutionAnalysis",
    "ExecutionQualityMetrics",
    "BestExecutionChecker",
    "SmartOrderRouter",
    "BaseAlgorithm",
    "TWAPAlgorithm",
    "VWAPAlgorithm",
    "IcebergAlgorithm",
    "ArrivalPriceAlgorithm",
    "AlgorithmFactory",
    "OrderOptimizer",
    "OptimizationManager",
]
