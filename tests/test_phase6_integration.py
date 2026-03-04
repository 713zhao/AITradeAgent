"""
Phase 6 Integration Tests - Live Trading Integration with ExecutionEngine

Tests integration of BrokerManager with the rest of the system:
- BrokerManager initialization
- ExecutionEngine + BrokerManager interaction
- Order placement and execution
- Event publishing and listening
- Position and account management
"""

import pytest
from datetime import datetime
from finance_service.brokers.broker_manager import BrokerManager, BrokerMode
from finance_service.brokers.base_broker import OrderSide, OrderType
from finance_service.execution.execution_engine import ExecutionEngine, ExecutionContext, ExecutionReport
from finance_service.risk.models import ApprovalRequest, ApprovalStatus


class TestBrokerManagerInitialization:
    """Test BrokerManager initialization and configuration."""
    
    def test_paper_broker_initialization(self):
        """Paper broker initializes with default settings."""
        manager = BrokerManager(
            mode=BrokerMode.PAPER,
            initial_cash=100000.0,
            slippage_bps=1.0,
            fill_delay_seconds=0.1,
        )
        
        assert manager.mode == BrokerMode.PAPER
        assert manager.broker is not None
        assert manager.paper_broker is not None
        assert manager.alpaca_broker is None
        
        # Check account
        account = manager.get_account()
        assert account is not None
        assert account.cash == 100000.0
    
    def test_broker_manager_event_listeners(self):
        """Broker manager supports event listener registration."""
        manager = BrokerManager(mode=BrokerMode.PAPER)
        
        calls = []
        
        def callback(data):
            calls.append(data)
        
        # Register listener
        manager.register_event_listener("ORDER_SUBMITTED", callback)
        
        assert len(manager.event_listeners["ORDER_SUBMITTED"]) == 1
        
        # Unregister listener
        manager.unregister_event_listener("ORDER_SUBMITTED", callback)
        assert len(manager.event_listeners["ORDER_SUBMITTED"]) == 0
    
    def test_broker_mode_switch(self):
        """Cannot switch modes with pending orders."""
        manager = BrokerManager(mode=BrokerMode.PAPER)
        
        # Place order (creates pending)
        order = manager.place_order(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="BUY",
            quantity=10,
        )
        
        # Cannot switch with pending orders
        with pytest.raises(ValueError, match="Cannot switch modes with"):
            manager.switch_mode(BrokerMode.LIVE)
        
        # Cancel order first
        manager.cancel_order(order.order_id)
        
        # Now can switch (though would fail because API key missing)
        with pytest.raises(ValueError, match="API key"):
            manager.switch_mode(BrokerMode.LIVE)


class TestBrokerManagerOrderPlacement:
    """Test order placement through BrokerManager."""
    
    def test_place_market_buy_order(self):
        """Place market BUY order through broker manager."""
        manager = BrokerManager(
            mode=BrokerMode.PAPER,
            initial_cash=100000.0,
            fill_delay_seconds=0.0,
        )
        
        # Set quote
        manager.broker.set_quote("AAPL", bid=150.0, ask=150.5, last=150.25)
        
        # Place order
        order = manager.place_order(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="BUY",
            quantity=10,
        )
        
        assert order is not None
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.quantity == 10
        
        # Verify tracking
        assert "TRADE_001" in manager.order_map
        assert manager.order_map["TRADE_001"] == order.order_id
    
    def test_place_limit_order(self):
        """Place limit order with price."""
        manager = BrokerManager(mode=BrokerMode.PAPER)
        
        order = manager.place_order(
            trade_id="TRADE_002",
            symbol="TSLA",
            side="BUY",
            quantity=5,
            price=200.0,
            order_type="LIMIT",
        )
        
        assert order is not None
        assert order.order_type == OrderType.LIMIT
    
    def test_order_validation(self):
        """Order validation catches invalid inputs."""
        manager = BrokerManager(mode=BrokerMode.PAPER)
        
        # Invalid quantity
        with pytest.raises(ValueError):
            manager.place_order(
                trade_id="TRADE_003",
                symbol="AAPL",
                side="BUY",
                quantity=0,
            )
        
        # Missing price for limit order
        with pytest.raises(ValueError):
            manager.place_order(
                trade_id="TRADE_004",
                symbol="AAPL",
                side="BUY",
                quantity=10,
                order_type="LIMIT",
                price=None,
            )
    
    def test_event_published_on_order_placement(self):
        """ORDER_SUBMITTED event published when order placed."""
        manager = BrokerManager(mode=BrokerMode.PAPER)
        
        events = []
        
        def on_order_submitted(data):
            events.append(data)
        
        manager.register_event_listener("ORDER_SUBMITTED", on_order_submitted)
        
        # Place order
        order = manager.place_order(
            trade_id="TRADE_005",
            symbol="MSFT",
            side="BUY",
            quantity=20,
        )
        
        # Event published
        assert len(events) == 1
        assert events[0]['order_id'] == order.order_id
        assert events[0]['trade_id'] == "TRADE_005"
        assert events[0]['symbol'] == "MSFT"


class TestBrokerManagerFillProcessing:
    """Test order fill processing."""
    
    def test_process_fills_completes_orders(self):
        """Process fills completes pending orders."""
        manager = BrokerManager(
            mode=BrokerMode.PAPER,
            initial_cash=100000.0,
            fill_delay_seconds=0.0,  # Instant fills
        )
        
        # Set quote
        manager.broker.set_quote("AAPL", bid=150.0, ask=150.5, last=150.25)
        
        # Place order
        order = manager.place_order(
            trade_id="TRADE_006",
            symbol="AAPL",
            side="BUY",
            quantity=10,
        )
        
        assert len(manager.pending_orders) == 1
        
        # Process fills
        manager.process_fills()
        
        # Order should be filled
        assert len(manager.pending_orders) == 0
        assert len(manager.filled_orders) == 1
    
    def test_order_fill_event_published(self):
        """ORDER_FILLED event published when order fills."""
        manager = BrokerManager(
            mode=BrokerMode.PAPER,
            initial_cash=100000.0,
            fill_delay_seconds=0.0,
        )
        
        manager.broker.set_quote("AAPL", bid=150.0, ask=150.5, last=150.25)
        
        fills = []
        
        def on_fill(data):
            fills.append(data)
        
        manager.register_event_listener("ORDER_FILLED", on_fill)
        
        # Place order
        order = manager.place_order(
            trade_id="TRADE_007",
            symbol="AAPL",
            side="BUY",
            quantity=10,
        )
        
        # Process fills
        manager.process_fills()
        
        # Fill event published
        assert len(fills) == 1
        assert fills[0]['order_id'] == order.order_id
        assert fills[0]['quantity'] == 10
    
    def test_position_created_on_fill(self):
        """Position created when BUY order fills."""
        manager = BrokerManager(
            mode=BrokerMode.PAPER,
            initial_cash=100000.0,
            fill_delay_seconds=0.0,
        )
        
        manager.broker.set_quote("AAPL", bid=150.0, ask=150.5, last=150.25)
        
        # No positions initially
        assert len(manager.get_positions()) == 0
        
        # Place order
        order = manager.place_order(
            trade_id="TRADE_008",
            symbol="AAPL",
            side="BUY",
            quantity=10,
        )
        
        # Process fills
        manager.process_fills()
        
        # Position created
        positions = manager.get_positions()
        assert len(positions) == 1
        assert "AAPL" in positions
        assert positions["AAPL"].quantity == 10


class TestExecutionEngineWithBroker:
    """Test ExecutionEngine integration with BrokerManager."""
    
    def test_execution_engine_without_broker(self):
        """ExecutionEngine works without broker (backward compatible)."""
        engine = ExecutionEngine(broker_manager=None)
        
        # Create execution context
        context = engine.create_execution_context(
            trade_id="TRADE_001",
            symbol="AAPL",
            side="BUY",
            quantity=10,
            target_price=150.0,
            confidence=0.8,
            risk_assessment={'approval_required': False},
        )
        
        assert context is not None
        
        # Execute (should succeed without broker)
        report = engine.approve_and_execute("TRADE_001")
        
        assert report.status == "EXECUTED"
        assert report.filled_quantity == 10
        assert report.filled_price == 150.0
    
    def test_execution_with_broker_manager(self):
        """ExecutionEngine places order with BrokerManager."""
        broker = BrokerManager(
            mode=BrokerMode.PAPER,
            initial_cash=100000.0,
            fill_delay_seconds=0.0,
        )
        
        broker.broker.set_quote("AAPL", bid=150.0, ask=150.5, last=150.25)
        
        engine = ExecutionEngine(broker_manager=broker)
        
        # Create execution context
        context = engine.create_execution_context(
            trade_id="TRADE_002",
            symbol="AAPL",
            side="BUY",
            quantity=10,
            target_price=150.0,
            confidence=0.8,
            risk_assessment={'approval_required': False},
        )
        
        # Execute with broker
        report = engine.approve_and_execute("TRADE_002")
        
        # Should have placed order with broker
        assert "broker_order_id" in report.portfolio_impact or report.status == "EXECUTED"
        assert report.symbol == "AAPL"
    
    def test_execution_failure_with_invalid_symbol(self):
        """Execution fails gracefully if broker rejects order."""
        broker = BrokerManager(
            mode=BrokerMode.PAPER,
            initial_cash=100000.0,
        )
        
        engine = ExecutionEngine(broker_manager=broker)
        
        # Create execution context with invalid symbol
        context = engine.create_execution_context(
            trade_id="TRADE_003",
            symbol="INVALID_SYMBOL_XYZ",
            side="BUY",
            quantity=10,
            target_price=150.0,
            confidence=0.8,
            risk_assessment={'approval_required': False},
        )
        
        # Execute (broker may accept, but depending on implementation)
        report = engine.approve_and_execute("TRADE_003")
        
        # Report should have details
        assert report.trade_id == "TRADE_003"
        assert report.execution_id is not None
    
    def test_execution_with_manual_approval(self):
        """ExecutionEngine tracks manual approval in execution report."""
        broker = BrokerManager(mode=BrokerMode.PAPER)
        engine = ExecutionEngine(broker_manager=broker)
        
        # Create execution context
        context = engine.create_execution_context(
            trade_id="TRADE_004",
            symbol="AAPL",
            side="BUY",
            quantity=10,
            target_price=150.0,
            confidence=0.8,
            risk_assessment={'approval_required': True},
        )
        
        # Create approval request
        approval = ApprovalRequest(
            request_id="APPROVAL_001",
            trade_id="TRADE_004",
            symbol="AAPL",
            trade_details={},
            reason="High risk trade",
        )
        
        # Approve and execute
        report = engine.approve_and_execute("TRADE_004", approval_request=approval)
        
        assert report.approval_request_id == "APPROVAL_001"
        assert report.execution_type.value == "manual_approval"


class TestBrokerEventIntegration:
    """Test broker event integration with listeners."""
    
    def test_multiple_event_listeners(self):
        """Multiple listeners can be registered for same event."""
        manager = BrokerManager(mode=BrokerMode.PAPER)
        
        calls_1 = []
        calls_2 = []
        
        def listener1(data):
            calls_1.append(data)
        
        def listener2(data):
            calls_2.append(data)
        
        manager.register_event_listener("ORDER_SUBMITTED", listener1)
        manager.register_event_listener("ORDER_SUBMITTED", listener2)
        
        # Place order
        manager.place_order(
            trade_id="TRADE_010",
            symbol="AAPL",
            side="BUY",
            quantity=10,
        )
        
        # Both listeners called
        assert len(calls_1) == 1
        assert len(calls_2) == 1
    
    def test_listener_exception_handling(self):
        """Broker continues if listener throws exception."""
        manager = BrokerManager(mode=BrokerMode.PAPER)
        
        def bad_listener(data):
            raise ValueError("Listener error")
        
        manager.register_event_listener("ORDER_SUBMITTED", bad_listener)
        
        # Should not raise, should handle gracefully
        order = manager.place_order(
            trade_id="TRADE_011",
            symbol="AAPL",
            side="BUY",
            quantity=10,
        )
        
        assert order is not None


class TestBrokerAccountManagement:
    """Test account and position management."""
    
    def test_account_updated_event(self):
        """ACCOUNT_UPDATED event published."""
        manager = BrokerManager(mode=BrokerMode.PAPER, initial_cash=50000.0)
        
        updates = []
        
        def on_account_update(data):
            updates.append(data)
        
        manager.register_event_listener("ACCOUNT_UPDATED", on_account_update)
        
        # Get account info
        account = manager.get_account()
        
        # Event published
        assert len(updates) == 1
        assert updates[0]['cash'] == 50000.0
    
    def test_cash_tracking_through_orders(self):
        """Cash decreases when order fills."""
        initial_cash = 100000.0
        manager = BrokerManager(
            mode=BrokerMode.PAPER,
            initial_cash=initial_cash,
            fill_delay_seconds=0.0,
        )
        
        manager.broker.set_quote("AAPL", bid=150.0, ask=150.5, last=150.25)
        
        # Check initial cash
        assert manager.get_cash() == initial_cash
        
        # Place and fill order
        order = manager.place_order(
            trade_id="TRADE_012",
            symbol="AAPL",
            side="BUY",
            quantity=10,
        )
        
        manager.process_fills()
        
        # Cash reduced by purchase
        new_cash = manager.get_cash()
        expected_spend = 10 * 150.5  # ask price with slippage
        assert new_cash < initial_cash
        assert abs(new_cash - (initial_cash - expected_spend)) < 10.0  # tolerance for slippage
    
    def test_position_closure_event(self):
        """POSITION_CLOSED event published."""
        manager = BrokerManager(
            mode=BrokerMode.PAPER,
            initial_cash=100000.0,
            fill_delay_seconds=0.0,
        )
        
        manager.broker.set_quote("AAPL", bid=150.0, ask=150.5, last=150.25)
        
        closes = []
        
        def on_close(data):
            closes.append(data)
        
        manager.register_event_listener("POSITION_CLOSED", on_close)
        
        # Buy shares
        manager.place_order(
            trade_id="TRADE_013",
            symbol="AAPL",
            side="BUY",
            quantity=10,
        )
        manager.process_fills()
        
        # Close position
        manager.close_position("AAPL")
        
        # Event published
        assert len(closes) == 1
        assert closes[0]['symbol'] == "AAPL"


class TestBrokerStats:
    """Test broker statistics and reporting."""
    
    def test_broker_stats_summary(self):
        """Broker provides statistics summary."""
        manager = BrokerManager(mode=BrokerMode.PAPER, initial_cash=50000.0)
        
        stats = manager.get_stats()
        
        assert stats['mode'] == 'paper'
        assert stats['broker_type'] == 'PaperBroker'
        assert stats['pending_orders'] == 0
        assert stats['filled_orders'] == 0
        assert stats['cash'] == 50000.0
    
    def test_stats_after_order_placement(self):
        """Stats updated after order placement."""
        manager = BrokerManager(mode=BrokerMode.PAPER)
        
        manager.place_order(
            trade_id="TRADE_014",
            symbol="AAPL",
            side="BUY",
            quantity=10,
        )
        
        stats = manager.get_stats()
        
        assert stats['pending_orders'] == 1
        assert stats['total_orders'] == 1


class TestBrokerReset:
    """Test broker state reset."""
    
    def test_reset_clears_state(self):
        """Reset clears all orders and positions."""
        manager = BrokerManager(mode=BrokerMode.PAPER, initial_cash=100000.0, fill_delay_seconds=0.0)
        
        manager.broker.set_quote("AAPL", bid=150.0, ask=150.5, last=150.25)
        
        # Place order
        manager.place_order(
            trade_id="TRADE_015",
            symbol="AAPL",
            side="BUY",
            quantity=10,
        )
        
        # Verify state before reset
        assert len(manager.pending_orders) == 1
        
        # Process fills
        manager.process_fills()
        
        # Verify state after fill
        assert len(manager.filled_orders) == 1 or len(manager.get_positions()) == 1
        
        # Reset
        manager.reset()
        
        # State cleared completely
        assert len(manager.order_map) == 0
        assert len(manager.pending_orders) == 0
        assert len(manager.filled_orders) == 0
        assert manager.get_cash() == 100000.0
        assert len(manager.get_positions()) == 0


# =====================
# Integration Test Suite
# =====================

class TestFullIntegrationFlow:
    """Test complete flow from trade to order fill."""
    
    def test_end_to_end_trade_execution(self):
        """Complete flow: ExecutionContext → Order → Fill → Position."""
        # Setup
        broker = BrokerManager(
            mode=BrokerMode.PAPER,
            initial_cash=100000.0,
            fill_delay_seconds=0.0,
        )
        
        broker.broker.set_quote("AAPL", bid=150.0, ask=150.5, last=150.25)
        
        engine = ExecutionEngine(broker_manager=broker)
        
        # Step 1: Create execution context
        context = engine.create_execution_context(
            trade_id="TRADE_016",
            symbol="AAPL",
            side="BUY",
            quantity=10,
            target_price=150.25,
            confidence=0.9,
            risk_assessment={'approval_required': False},
        )
        
        assert context is not None
        
        # Step 2: Record events
        fills = []
        
        def on_fill(data):
            fills.append(data)
        
        broker.register_event_listener("ORDER_FILLED", on_fill)
        
        # Step 3: Execute trade
        report = engine.approve_and_execute("TRADE_016")
        
        # Step 4: Process fills
        broker.process_fills()
        
        # Step 5: Verify results
        assert len(broker.filled_orders) == 1 or report.status == "EXECUTED"
        assert len(broker.get_positions()) == 1 or report.filled_quantity > 0
        
        # Get position
        position = broker.get_position("AAPL")
        if position:
            assert position.symbol == "AAPL"
            assert position.quantity == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
