"""
Phase 5 Execution & Monitoring - Comprehensive Test Suite

Tests for:
- Execution engine (approve/reject/execute)
- Trade monitor (SL/TP tracking)
- Performance reporter (metrics generation)
- Phase 4→5 integration
"""

import pytest
from datetime import datetime, timedelta
from finance_service.execution.execution_engine import (
    ExecutionEngine, ExecutionContext, ExecutionReport, ExecutionType
)
from finance_service.execution.trade_monitor import (
    TradeMonitor, TradeMonitorRecord, TradeState
)
from finance_service.execution.performance_reporter import (
    PerformanceReporter, PerformanceReport, PerformanceMetrics
)
from finance_service.risk.models import ApprovalRequest, ApprovalStatus


# =====================
# EXECUTION ENGINE TESTS
# =====================

class TestExecutionEngine:
    """Test execution engine operations."""
    
    def test_create_execution_context(self):
        """Test creating execution context."""
        engine = ExecutionEngine()
        
        risk_assessment = {
            "approval_required": False,
            "risk_score": 25.0,
            "violated_limits": [],
        }
        
        context = engine.create_execution_context(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="BUY",
            quantity=10,
            target_price=150.0,
            confidence=0.85,
            risk_assessment=risk_assessment
        )
        
        assert context.trade_id == "TRADE_001"
        assert context.symbol == "AAPL"
        assert context.quantity == 10
        assert not context.approval_required
    
    def test_approve_and_execute_auto(self):
        """Test auto-approval and execution."""
        engine = ExecutionEngine()
        
        context = engine.create_execution_context(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="BUY",
            quantity=10,
            target_price=150.0,
            confidence=0.90,
            risk_assessment={"approval_required": False, "risk_score": 15.0}
        )
        
        report = engine.approve_and_execute("TRADE_001")
        
        assert report.status == "EXECUTED"
        assert report.execution_type == ExecutionType.AUTO_APPROVAL
        assert report.filled_price == 150.0
        assert report.filled_quantity == 10
    
    def test_approve_with_manual_approval(self):
        """Test manual approval and execution."""
        engine = ExecutionEngine()
        
        # Create approval request
        approval_req = ApprovalRequest(
            request_id="APPROVAL_001",
            trade_id="TRADE_001",
            symbol="AAPL",
            status=ApprovalStatus.APPROVED,
            approval_notes="Risk manager approved"
        )
        
        context = engine.create_execution_context(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="BUY",
            quantity=10,
            target_price=150.0,
            confidence=0.70,
            risk_assessment={"approval_required": True, "risk_score": 60.0}
        )
        
        report = engine.approve_and_execute(
            "TRADE_001",
            approval_request=approval_req,
            approved_by="risk_manager"
        )
        
        assert report.status == "EXECUTED"
        assert report.execution_type == ExecutionType.MANUAL_APPROVAL
        assert report.approval_request_id == "APPROVAL_001"
    
    def test_reject_execution(self):
        """Test rejection of execution."""
        engine = ExecutionEngine()
        
        approval_req = ApprovalRequest(
            request_id="APPROVAL_001",
            trade_id="TRADE_001",
            symbol="AAPL",
            status=ApprovalStatus.REJECTED,
            decision_reason="Position size too large"
        )
        
        context = engine.create_execution_context(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="BUY",
            quantity=100,  # Oversized
            target_price=150.0,
            confidence=0.80,
            risk_assessment={"approval_required": True, "risk_score": 85.0}
        )
        
        report = engine.reject_execution(
            "TRADE_001",
            approval_request=approval_req,
            reason="Position size too large"
        )
        
        assert report.status == "REJECTED"
        assert report.execution_type == ExecutionType.REJECTED
    
    def test_handle_expired_request(self):
        """Test handling of expired approval request."""
        engine = ExecutionEngine()
        
        context = engine.create_execution_context(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="BUY",
            quantity=10,
            target_price=150.0,
            confidence=0.70,
            risk_assessment={"approval_required": True}
        )
        
        report = engine.handle_expired_request("TRADE_001")
        
        assert report.status == "REJECTED"
        assert report.execution_type == ExecutionType.TIMEOUT
        assert "expired" in report.reason.lower()
    
    def test_get_execution_stats(self):
        """Test execution statistics."""
        engine = ExecutionEngine()
        
        # Create and execute multiple trades
        for i in range(3):
            engine.create_execution_context(
                trade_id=f"TRADE_{i:03d}",
                symbol="AAPL",
                side="BUY",
                quantity=10,
                target_price=150.0,
                confidence=0.80 + (i * 0.05),
                risk_assessment={"approval_required": i == 0}
            )
        
        # Execute first two (one auto, one manual)
        engine.approve_and_execute("TRADE_000")
        
        approval = ApprovalRequest(
            request_id="APP_001",
            trade_id="TRADE_001",
            symbol="AAPL",
            status=ApprovalStatus.APPROVED
        )
        engine.approve_and_execute("TRADE_001", approval_request=approval)
        
        # Get stats
        stats = engine.get_execution_stats()
        
        assert stats["total_executions"] == 2
        assert stats["executed_count"] == 2
        assert stats["auto_approval_count"] == 1
        assert stats["manual_approval_count"] == 1


# =====================
# TRADE MONITOR TESTS
# =====================

class TestTradeMonitor:
    """Test trade monitoring."""
    
    def test_add_trade_to_monitor(self):
        """Test adding trade to monitor."""
        monitor = TradeMonitor()
        
        record = monitor.add_trade(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="BUY",
            entry_price=150.0,
            entry_quantity=10,
            stop_loss=145.0,
            take_profit=160.0
        )
        
        assert record.trade_id == "TRADE_001"
        assert record.state == TradeState.OPEN
    
    def test_sl_trigger_long_position(self):
        """Test stop-loss trigger for long position."""
        monitor = TradeMonitor()
        
        monitor.add_trade(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="BUY",
            entry_price=150.0,
            entry_quantity=10,
            stop_loss=145.0,
            take_profit=160.0
        )
        
        # Price drops to SL
        trigger = monitor.update_price("TRADE_001", 144.5)
        
        assert trigger is not None
        assert trigger["trigger_type"] == "sl_hit"
        assert "TRADE_001" not in monitor.open_trades
        assert "TRADE_001" in monitor.closed_trades
    
    def test_tp_trigger_long_position(self):
        """Test take-profit trigger for long position."""
        monitor = TradeMonitor()
        
        monitor.add_trade(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="BUY",
            entry_price=150.0,
            entry_quantity=10,
            stop_loss=145.0,
            take_profit=160.0
        )
        
        # Price rises to TP
        trigger = monitor.update_price("TRADE_001", 160.5)
        
        assert trigger is not None
        assert trigger["trigger_type"] == "tp_hit"
        assert trigger["pnl"] == 100.0  # (160 - 150) * 10
    
    def test_sl_trigger_short_position(self):
        """Test stop-loss trigger for short position."""
        monitor = TradeMonitor()
        
        monitor.add_trade(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="SELL",
            entry_price=150.0,
            entry_quantity=10,
            stop_loss=155.0,  # Above entry for short
            take_profit=140.0  # Below entry for short
        )
        
        # Price rises to SL
        trigger = monitor.update_price("TRADE_001", 155.5)
        
        assert trigger is not None
        assert trigger["trigger_type"] == "sl_hit"
    
    def test_tp_trigger_short_position(self):
        """Test take-profit trigger for short position."""
        monitor = TradeMonitor()
        
        monitor.add_trade(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="SELL",
            entry_price=150.0,
            entry_quantity=10,
            stop_loss=155.0,
            take_profit=140.0
        )
        
        # Price drops to TP
        trigger = monitor.update_price("TRADE_001", 139.5)
        
        assert trigger is not None
        assert trigger["trigger_type"] == "tp_hit"
        assert trigger["pnl"] == 100.0  # (150 - 140) * 10
    
    def test_price_update_without_trigger(self):
        """Test price update that doesn't trigger SL/TP."""
        monitor = TradeMonitor()
        
        monitor.add_trade(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="BUY",
            entry_price=150.0,
            entry_quantity=10,
            stop_loss=145.0,
            take_profit=160.0
        )
        
        # Price moves but doesn't hit SL/TP
        trigger = monitor.update_price("TRADE_001", 152.0)
        
        assert trigger is None
        assert "TRADE_001" in monitor.open_trades
        assert "TRADE_001" not in monitor.closed_trades
    
    def test_portfolio_stats(self):
        """Test portfolio statistics from monitor."""
        monitor = TradeMonitor()
        
        # Add multiple trades with mixed results
        monitor.add_trade("TRADE_001", "AAPL", "BUY", 150.0, 10, 145.0, 160.0)
        monitor.add_trade("TRADE_002", "MSFT", "SELL", 300.0, 5, 310.0, 290.0)
        
        # Trigger TP on first (winner)
        monitor.update_price("TRADE_001", 161.0)
        
        # Trigger SL on second (loser)
        monitor.update_price("TRADE_002", 310.5)
        
        stats = monitor.get_portfolio_stats()
        
        assert stats["closed_position_count"] == 2
        assert stats["winning_closed"] == 1
        assert stats["losing_closed"] == 1
        assert stats["tp_hits"] == 1
        assert stats["sl_hits"] == 1


# =====================
# PERFORMANCE REPORTER TESTS
# =====================

class TestPerformanceReporter:
    """Test performance reporting."""
    
    def test_create_performance_report(self):
        """Test creating a performance report."""
        reporter = PerformanceReporter()
        
        trades = [
            {"symbol": "AAPL", "realized_pnl": 100.0},
            {"symbol": "MSFT", "realized_pnl": -50.0},
            {"symbol": "AAPL", "realized_pnl": 75.0},
        ]
        
        report = reporter.create_performance_report(
            report_id="REPORT_001",
            starting_equity=100000.0,
            ending_equity=100125.0,
            trades=trades
        )
        
        assert report.report_id == "REPORT_001"
        assert report.metrics.total_trades == 3
        assert report.metrics.winning_trades == 2
        assert report.metrics.losing_trades == 1
    
    def test_win_rate_calculation(self):
        """Test win rate calculation."""
        reporter = PerformanceReporter()
        
        trades = [
            {"realized_pnl": 100.0},
            {"realized_pnl": -50.0},
            {"realized_pnl": 200.0},
        ]
        
        report = reporter.create_performance_report(
            report_id="REPORT_001",
            starting_equity=100000.0,
            ending_equity=100250.0,
            trades=trades
        )
        
        assert report.metrics.win_rate == pytest.approx(2/3, abs=0.01)
    
    def test_profit_factor_calculation(self):
        """Test profit factor calculation."""
        reporter = PerformanceReporter()
        
        trades = [
            {"realized_pnl": 100.0},
            {"realized_pnl": 100.0},
            {"realized_pnl": -50.0},
        ]
        
        report = reporter.create_performance_report(
            report_id="REPORT_001",
            starting_equity=100000.0,
            ending_equity=100150.0,
            trades=trades
        )
        
        # Total wins = 200, total losses = 50
        assert report.metrics.profit_factor == pytest.approx(4.0, abs=0.1)
    
    def test_symbol_breakdown(self):
        """Test symbol-level performance breakdown."""
        reporter = PerformanceReporter()
        
        trades = [
            {"symbol": "AAPL", "realized_pnl": 100.0},
            {"symbol": "AAPL", "realized_pnl": -50.0},
            {"symbol": "MSFT", "realized_pnl": 200.0},
        ]
        
        report = reporter.create_performance_report(
            report_id="REPORT_001",
            starting_equity=100000.0,
            ending_equity=100250.0,
            trades=trades
        )
        
        assert "AAPL" in report.symbol_performance
        assert "MSFT" in report.symbol_performance
        
        aapl_stats = report.symbol_performance["AAPL"]
        assert aapl_stats["trade_count"] == 2
        assert aapl_stats["winning_trades"] == 1
        assert aapl_stats["losing_trades"] == 1
    
    def test_max_drawdown_calculation(self):
        """Test maximum drawdown calculation."""
        reporter = PerformanceReporter()
        
        # Simulate equity curve
        reporter.equity_curve = [100000, 105000, 110000, 100000, 95000, 98000]
        
        max_dd = reporter.calculate_max_drawdown()
        
        # From peak of 110000 to trough of 95000
        expected_dd = (110000 - 95000) / 110000 * 100
        assert max_dd == pytest.approx(expected_dd, abs=1.0)
    
    def test_add_daily_return(self):
        """Test recording daily returns."""
        reporter = PerformanceReporter()
        
        reporter.add_daily_return(500.0, 100000.0)  # 0.5% return
        reporter.add_daily_return(-250.0, 100000.0)  # -0.25% return
        
        assert len(reporter.daily_returns) == 2
        assert reporter.daily_returns[0] == pytest.approx(0.005, abs=0.0001)
        assert reporter.daily_returns[1] == pytest.approx(-0.0025, abs=0.0001)


# =====================
# INTEGRATION TESTS
# =====================

class TestPhase5Integration:
    """Test Phase 4→5 integration."""
    
    def test_full_approval_to_execution_flow(self):
        """Test complete approval and execution flow."""
        engine = ExecutionEngine()
        monitor = TradeMonitor()
        
        # Step 1: Create execution context (from risk check)
        context = engine.create_execution_context(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="BUY",
            quantity=10,
            target_price=150.0,
            confidence=0.80,
            risk_assessment={
                "approval_required": False,
                "risk_score": 35.0,
                "violated_limits": []
            }
        )
        
        # Step 2: Auto-execute (no approval needed)
        exec_report = engine.approve_and_execute("TRADE_001")
        assert exec_report.status == "EXECUTED"
        
        # Step 3: Add to monitor
        monitor.add_trade(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="BUY",
            entry_price=150.0,
            entry_quantity=10,
            stop_loss=145.0,
            take_profit=160.0
        )
        
        # Step 4: Monitor execution and TP hit
        monitor.update_price("TRADE_001", 150.5)  # No trigger
        assert "TRADE_001" in monitor.open_trades
        
        monitor.update_price("TRADE_001", 161.0)  # TP hit
        assert "TRADE_001" in monitor.closed_trades
    
    def test_rejection_flow(self):
        """Test rejection and cleanup flow."""
        engine = ExecutionEngine()
        
        # Create rejection scenario
        approval_req = ApprovalRequest(
            request_id="APPROVAL_001",
            trade_id="TRADE_001",
            symbol="AAPL",
            status=ApprovalStatus.REJECTED,
            decision_reason="Risk limit exceeded"
        )
        
        context = engine.create_execution_context(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="BUY",
            quantity=100,
            target_price=150.0,
            confidence=0.70,
            risk_assessment={"approval_required": True, "risk_score": 90.0}
        )
        
        # Reject execution
        report = engine.reject_execution(
            "TRADE_001",
            approval_request=approval_req,
            reason="Violation of concentration limit"
        )
        
        assert report.status == "REJECTED"
        assert report.execution_type == ExecutionType.REJECTED
        assert "TRADE_001" not in engine.pending_executions
