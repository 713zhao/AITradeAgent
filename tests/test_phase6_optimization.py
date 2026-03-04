"""
Phase 6.5: Order Optimization Tests

Comprehensive tests for execution algorithms, best execution, and smart routing.
"""

import pytest
from datetime import datetime, timedelta
from finance_service.execution import (
    ExecutionAlgorithm,
    ExecutionConfig,
    ExecutionAnalysis,
    ExecutionQualityMetrics,
    BestExecutionChecker,
    SmartOrderRouter,
    TWAPAlgorithm,
    VWAPAlgorithm,
    IcebergAlgorithm,
    ArrivalPriceAlgorithm,
    OrderOptimizer,
    OptimizationManager,
)
from finance_service.brokers import PaperBroker


class TestExecutionAlgorithms:
    """Test execution algorithm implementations."""
    
    @pytest.fixture
    def config_twap(self):
        """Create TWAP configuration."""
        return ExecutionConfig(algorithm=ExecutionAlgorithm.TWAP, time_window_minutes=5)
    
    @pytest.fixture
    def config_vwap(self):
        """Create VWAP configuration."""
        return ExecutionConfig(algorithm=ExecutionAlgorithm.VWAP, time_window_minutes=5)
    
    @pytest.fixture
    def config_iceberg(self):
        """Create Iceberg configuration."""
        return ExecutionConfig(
            algorithm=ExecutionAlgorithm.ICEBERG,
            iceberg_chunk_size=100
        )
    
    def test_twap_generates_slices(self, config_twap):
        """TWAP generates equal-sized time slices."""
        algo = TWAPAlgorithm(config_twap)
        
        slices = algo.generate_slices(
            order_id="ORDER_001",
            symbol="AAPL",
            side="BUY",
            quantity=100,
            current_price=150.0,
            market_data={}
        )
        
        assert len(slices) > 0
        assert len(slices) <= 20  # Max 20 slices
        
        # Check all slices have equal quantity (rough)
        qty_per_slice = slices[0].quantity
        for slice_ in slices[1:]:
            assert abs(slice_.quantity - qty_per_slice) < 1.0
    
    def test_vwap_generates_volume_weighted_slices(self, config_vwap):
        """VWAP generates slices weighted by volume profile."""
        algo = VWAPAlgorithm(config_vwap)
        
        slices = algo.generate_slices(
            order_id="ORDER_002",
            symbol="AAPL",
            side="BUY",
            quantity=1000,
            current_price=150.0,
            market_data={"volume_profile": [0.1, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.15]}
        )
        
        assert len(slices) == 10
        
        # Earlier and later slices should be larger (higher volume)
        assert slices[0].quantity > slices[1].quantity  # Higher at open
        assert slices[-1].quantity > slices[-2].quantity  # Higher at close
    
    def test_iceberg_hides_order(self, config_iceberg):
        """Iceberg algorithm hides large orders."""
        algo = IcebergAlgorithm(config_iceberg)
        
        slices = algo.generate_slices(
            order_id="ORDER_003",
            symbol="AAPL",
            side="BUY",
            quantity=1000,
            current_price=150.0,
            market_data={}
        )
        
        # Should split into multiple chunks
        assert len(slices) > 1
        
        # Each chunk <= configured size
        for slice_ in slices[:-1]:
            assert slice_.quantity == config_iceberg.iceberg_chunk_size
    
    def test_arrival_price_algorithm(self):
        """Arrival price algorithm targets submission price."""
        config = ExecutionConfig(
            algorithm=ExecutionAlgorithm.ARRIVAL_PRICE,
            time_window_minutes=5
        )
        
        algo = ArrivalPriceAlgorithm(config)
        
        target_price = 150.0
        slices = algo.generate_slices(
            order_id="ORDER_004",
            symbol="AAPL",
            side="BUY",
            quantity=100,
            current_price=target_price,
            market_data={}
        )
        
        # All slices should target the arrival price
        for slice_ in slices:
            assert slice_.target_price == target_price


class TestExecutionAnalysis:
    """Test execution quality analysis."""
    
    def test_slippage_calculation(self):
        """Slippage calculated correctly."""
        analysis = ExecutionAnalysis(
            order_id="ORD_001",
            symbol="AAPL",
            side="BUY",
            total_quantity=100,
            target_price=150.0,
            arrival_price=150.0,
            total_filled_price=150.5,
            created_at=datetime.utcnow(),
            submitted_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            total_time_seconds=60,
        )
        
        # Calculate metrics with sample fill
        analysis.calculate_metrics([(150.5, 100)])
        
        # For BUY, slippage = (filled - target) / target * 10000
        # = (150.5 - 150.0) / 150.0 * 10000 = 33.33 bps
        assert abs(analysis.implementation_shortfall_bps - 33.33) < 0.5
    
    def test_execution_efficiency(self):
        """Efficiency ratio calculated correctly."""
        analysis = ExecutionAnalysis(
            order_id="ORD_002",
            symbol="TSLA",
            side="BUY",
            total_quantity=50,
            target_price=200.0,
            arrival_price=200.0,
            total_filled_price=199.5,
            created_at=datetime.utcnow(),
            submitted_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            total_time_seconds=120,
        )
        
        # Better than target = 100% efficiency (or higher)
        analysis.calculate_metrics([(199.5, 50)])
        assert analysis.efficiency_ratio >= 50.0  # At least half


class TestBestExecutionChecker:
    """Test best execution compliance checking."""
    
    def test_compliance_check_violation(self):
        """Slippage violation detected."""
        checker = BestExecutionChecker(benchmark_threshold_bps=3.0)
        
        analysis = ExecutionAnalysis(
            order_id="ORD_003",
            symbol="AAPL",
            side="BUY",
            total_quantity=100,
            target_price=150.0,
            arrival_price=150.0,
            total_filled_price=151.0,
            created_at=datetime.utcnow(),
            submitted_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            total_time_seconds=30,
        )
        
        analysis.calculate_metrics([(151.0, 100)])
        
        result = checker.check_execution(analysis, {"bid": 150.5, "ask": 150.7})
        
        # 66.67 bps slippage > 3 bps threshold
        assert not result["compliant"]
        assert len(result["violations"]) > 0
    
    def test_compliance_summary(self):
        """Compliance summary tracks violations."""
        checker = BestExecutionChecker(benchmark_threshold_bps=5.0)
        
        # First execution (no violations)
        analysis1 = ExecutionAnalysis(
            order_id="ORD_004",
            symbol="MSFT",
            side="BUY",
            total_quantity=100,
            target_price=300.0,
            arrival_price=300.0,
            total_filled_price=300.1,
            created_at=datetime.utcnow(),
            submitted_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            total_time_seconds=30,
        )
        
        analysis1.calculate_metrics([(300.1, 100)])
        checker.check_execution(analysis1, {"bid": 300.0, "ask": 300.5})
        
        summary = checker.get_compliance_summary()
        assert summary["total_executed"] == 1
        assert summary["compliance_rate"] == 100.0


class TestSmartOrderRouter:
    """Test intelligent broker selection."""
    
    def test_broker_selection(self):
        """Smart router selects best broker."""
        paper_broker = PaperBroker(initial_cash=100000.0)
        brokers = {"paper": paper_broker}
        
        router = SmartOrderRouter(brokers)
        
        selected_broker, metadata = router.select_broker(
            symbol="AAPL",
            side="BUY",
            quantity=10,
            price=150.0,
            market_data={
                "bid": 149.9,
                "ask": 150.1,
                "market_volume": 10000000,
                "avg_slippage_bps": 1.0,
            }
        )
        
        assert selected_broker == "paper"
        assert metadata["selected_broker"] == "paper"
        assert "score" in metadata
    
    def test_routing_stats(self):
        """Router tracks routing statistics."""
        paper_broker = PaperBroker(initial_cash=100000.0)
        brokers = {"paper": paper_broker}
        
        router = SmartOrderRouter(brokers)
        
        # Route multiple orders
        for i in range(3):
            router.select_broker(
                symbol="AAPL",
                side="BUY",
                quantity=10,
                price=150.0,
                market_data={}
            )
        
        stats = router.get_routing_stats()
        assert stats["total_routed"] == 3
        assert stats["broker_distribution"]["paper"] == 3


class TestExecutionQualityMetrics:
    """Test execution quality tracking."""
    
    def test_metrics_tracking(self):
        """Metrics tracked across multiple orders."""
        metrics = ExecutionQualityMetrics()
        
        # Add first analysis
        analysis1 = ExecutionAnalysis(
            order_id="ORD_005",
            symbol="AAPL",
            side="BUY",
            total_quantity=100,
            target_price=150.0,
            arrival_price=150.0,
            total_filled_price=150.5,
            created_at=datetime.utcnow(),
            submitted_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            total_time_seconds=60,
        )
        analysis1.calculate_metrics([(150.5, 100)])
        
        metrics.add_analysis(analysis1)
        assert len(metrics.analyses) == 1
        
        # Add second analysis
        analysis2 = ExecutionAnalysis(
            order_id="ORD_006",
            symbol="AAPL",
            side="SELL",
            total_quantity=100,
            target_price=151.0,
            arrival_price=151.0,
            total_filled_price=150.9,
            created_at=datetime.utcnow(),
            submitted_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            total_time_seconds=45,
        )
        analysis2.calculate_metrics([(150.9, 100)])
        
        metrics.add_analysis(analysis2)
        assert len(metrics.analyses) == 2
        
        # Get summary
        summary = metrics.get_efficiency_metrics()
        assert summary["total_orders"] == 2


class TestOrderOptimizer:
    """Test order optimizer orchestration."""
    
    @pytest.fixture
    def optimizer(self):
        """Create optimizer with paper broker."""
        paper_broker = PaperBroker(initial_cash=100000.0, fill_delay_seconds=0.0)
        brokers = {"paper": paper_broker}
        return OrderOptimizer(brokers)
    
    def test_optimize_order(self, optimizer):
        """Optimize order creates optimization request."""
        config = ExecutionConfig(algorithm=ExecutionAlgorithm.TWAP)
        
        opt_id = optimizer.optimize_order(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="BUY",
            quantity=100,
            current_price=150.0,
            config=config,
            market_data={}
        )
        
        assert opt_id is not None
        assert opt_id.startswith("OPT_")
    
    def test_get_order_status(self, optimizer):
        """Get status of optimized order."""
        config = ExecutionConfig(algorithm=ExecutionAlgorithm.TWAP)
        
        opt_id = optimizer.optimize_order(
            trade_id="TRADE_002",
            symbol="AAPL",
            side="BUY",
            quantity=100,
            current_price=150.0,
            config=config,
            market_data={}
        )
        
        status = optimizer.get_order_status(opt_id)
        
        assert status is not None
        assert status["symbol"] == "AAPL"
        assert status["filled_quantity"] == 0.0
        assert status["fill_progress"] == 0.0
    
    def test_next_slices(self, optimizer):
        """Get ready slices for execution."""
        config = ExecutionConfig(algorithm=ExecutionAlgorithm.TWAP, time_window_minutes=1)
        
        opt_id = optimizer.optimize_order(
            trade_id="TRADE_003",
            symbol="AAPL",
            side="BUY",
            quantity=100,
            current_price=150.0,
            config=config,
            market_data={}
        )
        
        # Get slices ready for execution
        slices = optimizer.get_next_slices(opt_id, datetime.utcnow())
        
        # Should have at least one slice ready immediately
        assert len(slices) > 0


class TestOptimizationManager:
    """Test portfolio-level optimization manager."""
    
    @pytest.fixture
    def manager(self):
        """Create manager with paper broker."""
        paper_broker = PaperBroker(initial_cash=100000.0)
        brokers = {"paper": paper_broker}
        return OptimizationManager(brokers)
    
    def test_add_constraint(self, manager):
        """Add trading constraints."""
        manager.add_constraint("AAPL", max_daily_volume_pct=5.0)
        
        assert "AAPL" in manager.order_constraints
    
    def test_check_constraint(self, manager):
        """Check order against constraints."""
        manager.add_constraint("AAPL", max_single_order_pct=1.0)
        
        # Order = 1% of volume, should pass
        ok, reason = manager.check_constraint("AAPL", 10000, 1000000)
        assert ok
        
        # Order = 2% of volume, should fail
        ok, reason = manager.check_constraint("AAPL", 20000, 1000000)
        assert not ok
    
    def test_optimize_portfolio_orders(self, manager):
        """Optimize multiple portfolio orders."""
        manager.add_constraint("AAPL", max_single_order_pct=2.0)
        
        orders = [
            {
                "trade_id": "TRADE_004",
                "symbol": "AAPL",
                "side": "BUY",
                "quantity": 10000,
                "current_price": 150.0,
            },
            {
                "trade_id": "TRADE_005",
                "symbol": "AAPL",
                "side": "SELL",
                "quantity": 5000,
                "current_price": 151.0,
            }
        ]
        
        opt_ids = manager.optimize_portfolio_orders(orders, {"AAPL_volume": 1000000})
        
        assert len(opt_ids) > 0


class TestIntegrationOptimization:
    """Integration tests for complete optimization flow."""
    
    def test_twap_execution_flow(self):
        """Complete TWAP execution flow."""
        paper_broker = PaperBroker(initial_cash=100000.0, fill_delay_seconds=0.0)
        paper_broker.set_quote("AAPL", bid=149.9, ask=150.1, last=150.0)
        
        brokers = {"paper": paper_broker}
        optimizer = OrderOptimizer(brokers)
        
        # Configure TWAP
        config = ExecutionConfig(
            algorithm=ExecutionAlgorithm.TWAP,
            time_window_minutes=1,
        )
        
        # Optimize order
        opt_id = optimizer.optimize_order(
            trade_id="TRADE_006",
            symbol="AAPL",
            side="BUY",
            quantity=100,
            current_price=150.0,
            config=config,
            market_data={},
        )
        
        # Should have slices ready
        status = optimizer.get_order_status(opt_id)
        assert status["slices_total"] > 0
        
        # Get performance
        perf = optimizer.get_performance_summary()
        assert "execution_metrics" in perf
        assert "smart_routing" in perf

    def test_best_execution_tracking(self):
        """Best execution compliance tracking."""
        paper_broker = PaperBroker(initial_cash=100000.0, fill_delay_seconds=0.0)
        paper_broker.set_quote("MSFT", bid=300.0, ask=300.5, last=300.2)
        
        brokers = {"paper": paper_broker}
        optimizer = OrderOptimizer(brokers, benchmark_threshold_bps=5.0)
        
        config = ExecutionConfig(algorithm=ExecutionAlgorithm.TWAP)
        
        # Place 5 orders
        for i in range(5):
            optimizer.optimize_order(
                trade_id=f"TRADE_{i:03d}",
                symbol="MSFT",
                side="BUY",
                quantity=50,
                current_price=300.0,
                config=config,
                market_data={},
            )
        
        # Get best execution report
        report = optimizer.get_best_execution_report()
        assert "total_executed" in report


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
