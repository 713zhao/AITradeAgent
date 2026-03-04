"""
Tests for Phase 6.2: Advanced Order Types

Tests trailing stops, OCO orders, bracket orders, and iceberg orders.
"""

import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import sys
import os

# Add the finance_service to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'finance_service'))

from brokers.advanced_orders.trailing_stop import (
    TrailingStopOrder, TrailingStopManager, TrailingType, TrailingStopState
)
from brokers.advanced_orders.oco_manager import (
    OCOManager, OCOGroup, OCOGroupStatus, create_profit_target_stop_loss_oco
)
from brokers.advanced_orders.bracket_orders import (
    BracketOrder, BracketManager, BracketStatus
)
from brokers.advanced_orders.iceberg_orders import (
    IcebergOrder, IcebergManager, IcebergStatus, DisclosureType
)
from brokers.advanced_orders.advanced_order_manager import (
    AdvancedOrderManager, AdvancedOrderEvent, AdvancedOrderEventData
)
from brokers.base_broker import OrderRequest, OrderSide, OrderType


class TestTrailingStopOrder:
    """Test TrailingStopOrder functionality."""
    
    def test_trailing_stop_creation(self):
        """Test creating a trailing stop order."""
        order = TrailingStopOrder(
            order_id="TS_001",
            symbol="AAPL",
            side="SELL",
            quantity=100,
            initial_stop_price=150.0,
            trailing_type=TrailingType.DISTANCE,
            trailing_amount=2.0,
            current_stop_price=150.0,
            state=TrailingStopState.ACTIVE
        )
        
        assert order.order_id == "TS_001"
        assert order.symbol == "AAPL"
        assert order.side == "SELL"
        assert order.quantity == 100
        assert order.initial_stop_price == 150.0
        assert order.trailing_type == TrailingType.DISTANCE
        assert order.trailing_amount == 2.0
        assert order.current_stop_price == 150.0
        assert order.state == TrailingStopState.ACTIVE
        assert order.highest_price == 150.0
        assert order.is_active()
    
    def test_sell_trailing_stop_updates(self):
        """Test SELL trailing stop price updates."""
        order = TrailingStopOrder(
            order_id="TS_001",
            symbol="AAPL",
            side="SELL",
            quantity=100,
            initial_stop_price=150.0,
            trailing_type=TrailingType.DISTANCE,
            trailing_amount=2.0,
            current_stop_price=150.0,
            state=TrailingStopState.ACTIVE
        )
        
        # Price increases to 155, stop should move to 153
        result = order.update(155.0)
        assert result['new_stop_price'] == 153.0
        assert result['stop_price_updated'] is True
        assert order.current_stop_price == 153.0
        assert order.highest_price == 155.0
        
        # Price decreases to 154, stop should stay at 153
        result = order.update(154.0)
        assert result['new_stop_price'] is None
        assert result['stop_price_updated'] is False
        assert order.current_stop_price == 153.0
        
        # Price drops to stop level, should trigger
        result = order.update(153.0)
        assert result['triggered'] is True
        assert order.state == TrailingStopState.TRIGGERED
    
    def test_buy_trailing_stop_updates(self):
        """Test BUY trailing stop price updates."""
        order = TrailingStopOrder(
            order_id="TS_001",
            symbol="AAPL",
            side="BUY",
            quantity=100,
            initial_stop_price=150.0,
            trailing_type=TrailingType.DISTANCE,
            trailing_amount=2.0,
            current_stop_price=150.0,
            state=TrailingStopState.ACTIVE
        )
        
        # Price decreases to 145, stop should move to 147
        result = order.update(145.0)
        assert result['new_stop_price'] == 147.0
        assert result['stop_price_updated'] is True
        assert order.current_stop_price == 147.0
        assert order.lowest_price == 145.0
        
        # Price increases to 146, stop should stay at 147
        result = order.update(146.0)
        assert result['new_stop_price'] is None
        assert result['stop_price_updated'] is False
        assert order.current_stop_price == 147.0
        
        # Price rises to stop level, should trigger
        result = order.update(147.0)
        assert result['triggered'] is True
        assert order.state == TrailingStopState.TRIGGERED
    
    def test_percentage_trailing_stop(self):
        """Test percentage-based trailing stops."""
        order = TrailingStopOrder(
            order_id="TS_001",
            symbol="AAPL",
            side="SELL",
            quantity=100,
            initial_stop_price=150.0,
            trailing_type=TrailingType.PERCENTAGE,
            trailing_amount=2.0,  # 2%
            current_stop_price=150.0,
            state=TrailingStopState.ACTIVE
        )
        
        # Price increases to 155 (3.33% gain), stop should move to 151.9 (155 * 0.98)
        result = order.update(155.0)
        expected_stop = 155.0 * 0.98  # 151.9
        assert abs(result['new_stop_price'] - expected_stop) < 0.01
        assert result['stop_price_updated'] is True
    
    def test_trailing_stop_fill(self):
        """Test filling a triggered trailing stop."""
        order = TrailingStopOrder(
            order_id="TS_001",
            symbol="AAPL",
            side="SELL",
            quantity=100,
            initial_stop_price=150.0,
            trailing_type=TrailingType.DISTANCE,
            trailing_amount=2.0,
            current_stop_price=153.0,
            state=TrailingStopState.TRIGGERED
        )
        
        order.fill(152.5, 100)
        
        assert order.state == TrailingStopState.FILLED
        assert order.filled_at is not None
        assert order.metadata['fill_price'] == 152.5
        assert order.metadata['fill_quantity'] == 100


class TestTrailingStopManager:
    """Test TrailingStopManager functionality."""
    
    def test_manager_operations(self):
        """Test basic manager operations."""
        manager = TrailingStopManager()
        
        # Create a trailing stop order
        order = TrailingStopOrder(
            order_id="TS_001",
            symbol="AAPL",
            side="SELL",
            quantity=100,
            initial_stop_price=150.0,
            trailing_type=TrailingType.DISTANCE,
            trailing_amount=2.0,
            current_stop_price=150.0,
            state=TrailingStopState.ACTIVE
        )
        
        manager.add_order(order)
        assert len(manager.orders) == 1
        assert manager.get_order("TS_001") == order
        
        # Get orders by symbol
        orders = manager.get_orders_by_symbol("AAPL")
        assert len(orders) == 1
        assert orders[0] == order
        
        # Get active orders
        active = manager.get_active_orders()
        assert len(active) == 1
        assert active[0] == order
        
        # Update all orders for a symbol
        results = manager.update_all("AAPL", 155.0)
        assert len(results) == 1
        assert results[0]['symbol'] == "AAPL"
        
        # Remove order
        removed = manager.remove_order("TS_001")
        assert removed == order
        assert len(manager.orders) == 0
    
    def test_trigger_orders(self):
        """Test triggering orders."""
        manager = TrailingStopManager()
        
        # Create an order that should trigger
        order = TrailingStopOrder(
            order_id="TS_001",
            symbol="AAPL",
            side="SELL",
            quantity=100,
            initial_stop_price=150.0,
            trailing_type=TrailingType.DISTANCE,
            trailing_amount=2.0,
            current_stop_price=153.0,
            state=TrailingStopState.ACTIVE
        )
        
        manager.add_order(order)
        
        # Trigger the order
        triggered = manager.trigger_orders("AAPL", 153.0)
        assert len(triggered) == 1
        assert triggered[0] == "TS_001"
        assert order.state == TrailingStopState.TRIGGERED


class TestOCOGroup:
    """Test OCOGroup functionality."""
    
    def test_oco_group_creation(self):
        """Test creating an OCO group."""
        # Create orders for OCO group
        orders = [
            OrderRequest(
                order_id="ORDER_001",
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=100,
                order_type=OrderType.LIMIT,
                price=155.0,
                time_in_force="gtc"
            ),
            OrderRequest(
                order_id="ORDER_002",
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=100,
                order_type=OrderType.LIMIT,
                price=145.0,
                time_in_force="gtc"
            )
        ]
        
        group = OCOGroup(group_id="OCO_001", orders=orders)
        
        assert group.group_id == "OCO_001"
        assert len(group.orders) == 2
        assert group.status == OCOGroupStatus.ACTIVE
        assert group.is_active()
    
    def test_oco_group_trigger(self):
        """Test triggering OCO group."""
        orders = [
            OrderRequest(
                order_id="ORDER_001",
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=100,
                order_type=OrderType.LIMIT,
                price=155.0,
                time_in_force="gtc"
            ),
            OrderRequest(
                order_id="ORDER_002",
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=100,
                order_type=OrderType.LIMIT,
                price=145.0,
                time_in_force="gtc"
            )
        ]
        
        group = OCOGroup(group_id="OCO_001", orders=orders)
        
        # Trigger with first order
        group.trigger("ORDER_001")
        
        assert group.status == OCOGroupStatus.PARTIAL
        assert group.filled_order_id == "ORDER_001"
        assert group.filled_order_side == "SELL"
        
        # Get orders to cancel (should be ORDER_002)
        to_cancel = group.get_orders_to_cancel()
        assert len(to_cancel) == 1
        assert "ORDER_002" in to_cancel
        assert "ORDER_001" not in to_cancel
    
    def test_oco_group_validation(self):
        """Test OCO group validation."""
        # Valid group
        valid_orders = [
            OrderRequest(
                order_id="ORDER_001",
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=100,
                order_type=OrderType.LIMIT,
                price=155.0,
                time_in_force="gtc"
            ),
            OrderRequest(
                order_id="ORDER_002",
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=100,
                order_type=OrderType.LIMIT,
                price=145.0,
                time_in_force="gtc"
            )
        ]
        
        group = OCOGroup(group_id="OCO_001", orders=valid_orders)
        errors = group.validate_group()
        assert len(errors) == 0
        
        # Invalid group - only one order
        invalid_group = OCOGroup(group_id="OCO_002", orders=[valid_orders[0]])
        errors = invalid_group.validate_group()
        assert len(errors) == 1
        assert "must have at least 2 orders" in errors[0]


class TestOCOManager:
    """Test OCOManager functionality."""
    
    def test_manager_operations(self):
        """Test basic manager operations."""
        manager = OCOManager()
        
        # Create orders
        orders = [
            OrderRequest(
                order_id="ORDER_001",
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=100,
                order_type=OrderType.LIMIT,
                price=155.0,
                time_in_force="gtc"
            ),
            OrderRequest(
                order_id="ORDER_002",
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=100,
                order_type=OrderType.LIMIT,
                price=145.0,
                time_in_force="gtc"
            )
        ]
        
        # Create group
        group_id = manager.create_group(orders)
        assert len(manager.groups) == 1
        assert manager.order_to_group["ORDER_001"] == group_id
        assert manager.order_to_group["ORDER_002"] == group_id
        
        # Get group
        group = manager.get_group(group_id)
        assert group is not None
        assert len(group.orders) == 2
        
        # Trigger group
        triggered_id = manager.trigger_group("ORDER_001")
        assert triggered_id == group_id
        
        # Get orders to cancel
        to_cancel = manager.get_orders_to_cancel("ORDER_001")
        assert "ORDER_002" in to_cancel
        assert "ORDER_001" not in to_cancel
    
    def test_helper_functions(self):
        """Test helper functions for common OCO patterns."""
        # Test profit target/stop loss OCO
        orders = create_profit_target_stop_loss_oco(
            symbol="AAPL",
            quantity=100,
            entry_price=150.0,
            profit_target_pct=5.0,
            stop_loss_pct=-3.0
        )
        
        assert len(orders) == 2
        profit_order = orders[0]
        stop_order = orders[1]
        
        # Verify prices
        expected_profit = 150.0 * 1.05  # 157.5
        expected_stop = 150.0 * 0.97   # 145.5
        
        assert abs(profit_order.price - expected_profit) < 0.01
        assert abs(stop_order.price - expected_stop) < 0.01
        
        # Verify metadata
        assert profit_order.metadata['order_purpose'] == 'profit_target'
        assert stop_order.metadata['order_purpose'] == 'stop_loss'


class TestBracketOrder:
    """Test BracketOrder functionality."""
    
    def test_bracket_creation(self):
        """Test creating a bracket order."""
        bracket = BracketOrder(
            bracket_id="BRACKET_001",
            symbol="AAPL",
            quantity=100,
            entry_price=150.0,
            profit_target_price=157.5,  # 5% profit
            stop_loss_price=145.5,      # 3% loss
            entry_side="BUY"
        )
        
        assert bracket.bracket_id == "BRACKET_001"
        assert bracket.symbol == "AAPL"
        assert bracket.quantity == 100
        assert bracket.entry_price == 150.0
        assert bracket.profit_target_price == 157.5
        assert bracket.stop_loss_price == 145.5
        assert bracket.status == BracketStatus.PENDING
        assert bracket.is_entry_pending()
    
    def test_bracket_entry_order(self):
        """Test creating entry order for bracket."""
        bracket = BracketOrder(
            bracket_id="BRACKET_001",
            symbol="AAPL",
            quantity=100,
            entry_price=150.0,
            profit_target_price=157.5,
            stop_loss_price=145.5,
            entry_side="BUY"
        )
        
        entry_order = bracket.create_entry_order()
        
        assert entry_order.symbol == "AAPL"
        assert entry_order.side == OrderSide.BUY
        assert entry_order.quantity == 100
        assert entry_order.price == 150.0
        assert entry_order.metadata['bracket_id'] == "BRACKET_001"
        assert entry_order.metadata['order_purpose'] == 'entry'
        assert entry_order.metadata['bracket_entry'] is True
    
    def test_bracket_exit_orders(self):
        """Test creating exit orders for bracket."""
        bracket = BracketOrder(
            bracket_id="BRACKET_001",
            symbol="AAPL",
            quantity=100,
            entry_price=150.0,
            profit_target_price=157.5,
            stop_loss_price=145.5,
            entry_side="BUY"
        )
        
        exit_orders = bracket.create_exit_orders()
        
        assert len(exit_orders) == 2
        
        # Find profit target and stop loss orders
        profit_order = next((o for o in exit_orders if o.metadata['order_purpose'] == 'profit_target'), None)
        stop_order = next((o for o in exit_orders if o.metadata['order_purpose'] == 'stop_loss'), None)
        
        assert profit_order is not None
        assert stop_order is not None
        assert profit_order.price == 157.5
        assert stop_order.price == 145.5
        assert profit_order.side == OrderSide.SELL
        assert stop_order.side == OrderSide.SELL
    
    def test_bracket_entry_fill(self):
        """Test handling entry order fill."""
        bracket = BracketOrder(
            bracket_id="BRACKET_001",
            symbol="AAPL",
            quantity=100,
            entry_price=150.0,
            profit_target_price=157.5,
            stop_loss_price=145.5,
            entry_side="BUY"
        )
        
        # Place entry order
        bracket.entry_order_id = "ENTRY_001"
        bracket.status = BracketStatus.ACTIVE
        
        # Handle entry fill
        exit_orders = bracket.on_entry_filled(150.0, 100)
        
        assert bracket.status == BracketStatus.ENTRY_FILLED
        assert bracket.entry_filled_at is not None
        assert len(exit_orders) == 2
        assert bracket.metadata['entry_fill_price'] == 150.0
        assert bracket.metadata['entry_fill_quantity'] == 100
    
    def test_bracket_risk_reward_calculation(self):
        """Test risk-reward calculation."""
        bracket = BracketOrder(
            bracket_id="BRACKET_001",
            symbol="AAPL",
            quantity=100,
            entry_price=150.0,
            profit_target_price=157.5,
            stop_loss_price=145.5,
            entry_side="BUY"
        )
        
        metrics = bracket.calculate_risk_reward()
        
        # For BUY order: profit = (157.5 - 150.0) * 100 = 750
        # Loss = (150.0 - 145.5) * 100 = 450
        expected_profit = (157.5 - 150.0) * 100  # 750
        expected_loss = (150.0 - 145.5) * 100    # 450
        
        assert abs(metrics['profit_amount'] - expected_profit) < 0.01
        assert abs(metrics['loss_amount'] - expected_loss) < 0.01
        assert metrics['profit_pct'] == 5.0
        assert metrics['loss_pct'] == 3.0
        assert abs(metrics['risk_reward_ratio'] - (expected_profit / expected_loss)) < 0.01


class TestBracketManager:
    """Test BracketManager functionality."""
    
    def test_manager_operations(self):
        """Test basic manager operations."""
        manager = BracketManager()
        
        # Create bracket with percentages
        bracket_id = manager.create_bracket(
            symbol="AAPL",
            quantity=100,
            entry_price=150.0,
            profit_target_pct=5.0,
            stop_loss_pct=3.0,
            entry_side="BUY"
        )
        
        assert len(manager.brackets) == 1
        bracket = manager.get_bracket(bracket_id)
        assert bracket is not None
        assert bracket.profit_target_price == 157.5
        assert bracket.stop_loss_price == 145.5
        
        # Place entry order
        entry_order = manager.place_entry_order(bracket_id)
        assert entry_order is not None
        assert entry_order.symbol == "AAPL"
        assert entry_order.side == OrderSide.BUY
        
        # Handle entry fill
        exit_orders = manager.on_entry_filled(entry_order.order_id, 150.0, 100)
        assert len(exit_orders) == 2
        
        # Handle exit fill
        completed_bracket_id = manager.on_exit_filled(exit_orders[0].order_id, 157.5, 100)
        assert completed_bracket_id == bracket_id


class TestIcebergOrder:
    """Test IcebergOrder functionality."""
    
    def test_iceberg_creation(self):
        """Test creating an iceberg order."""
        order = IcebergOrder(
            iceberg_id="ICEBERG_001",
            parent_order_id="PARENT_001",
            symbol="AAPL",
            side="BUY",
            total_quantity=1000,
            displayed_quantity=100,
            disclosure_type=DisclosureType.TIME_BASED,
            disclosure_interval_seconds=60,
            order_type="limit",
            price=150.0
        )
        
        assert order.iceberg_id == "ICEBERG_001"
        assert order.symbol == "AAPL"
        assert order.total_quantity == 1000
        assert order.displayed_quantity == 100
        assert order.hidden_quantity == 900
        assert order.status == IcebergStatus.ACTIVE
        assert order.is_active()
    
    def test_iceberg_child_order_creation(self):
        """Test creating child orders."""
        order = IcebergOrder(
            iceberg_id="ICEBERG_001",
            parent_order_id="PARENT_001",
            symbol="AAPL",
            side="BUY",
            total_quantity=1000,
            displayed_quantity=100,
            disclosure_type=DisclosureType.TIME_BASED,
            disclosure_interval_seconds=60,
            order_type="limit",
            price=150.0
        )
        
        child_order = order.create_child_order()
        
        assert child_order is not None
        assert child_order.symbol == "AAPL"
        assert child_order.side == OrderSide.BUY
        assert child_order.quantity == 100
        assert child_order.price == 150.0
        assert child_order.metadata['iceberg_id'] == "ICEBERG_001"
        assert child_order.metadata['child_order'] is True
        assert len(order.child_orders) == 1
        assert len(order.active_child_orders) == 1
    
    def test_iceberg_child_fill(self):
        """Test handling child order fills."""
        order = IcebergOrder(
            iceberg_id="ICEBERG_001",
            parent_order_id="PARENT_001",
            symbol="AAPL",
            side="BUY",
            total_quantity=1000,
            displayed_quantity=100,
            disclosure_type=DisclosureType.TIME_BASED,
            disclosure_interval_seconds=60,
            order_type="limit",
            price=150.0
        )
        
        # Create child order
        child_order = order.create_child_order()
        child_order_id = child_order.order_id
        
        # Fill the child order
        new_child = order.on_child_fill(child_order_id, 150.0, 100)
        
        assert order.filled_quantity == 100
        assert order.displayed_quantity == 0
        assert order.hidden_quantity == 800
        assert child_order_id not in order.active_child_orders
        assert new_child is not None  # Should create new child order
        assert new_child.quantity == 100
    
    def test_iceberg_disclosure_timing(self):
        """Test disclosure timing logic."""
        # Test time-based disclosure
        order = IcebergOrder(
            iceberg_id="ICEBERG_001",
            parent_order_id="PARENT_001",
            symbol="AAPL",
            side="BUY",
            total_quantity=1000,
            displayed_quantity=100,
            disclosure_type=DisclosureType.TIME_BASED,
            disclosure_interval_seconds=60,
            order_type="limit",
            price=150.0
        )
        
        # First disclosure should be allowed
        assert order.should_disclose() is True
        
        # Set last disclosed time to now
        order.last_disclosed_at = datetime.utcnow()
        
        # Should not disclose immediately
        assert order.should_disclose() is False
        
        # Test fill-based disclosure
        order_fill = IcebergOrder(
            iceberg_id="ICEBERG_002",
            parent_order_id="PARENT_002",
            symbol="AAPL",
            side="BUY",
            total_quantity=1000,
            displayed_quantity=100,
            disclosure_type=DisclosureType.FILL_BASED,
            disclosure_fill_threshold=0.8,
            order_type="limit",
            price=150.0
        )
        
        # Fill most of the displayed quantity
        order_fill.displayed_quantity = 20  # Only 20 left of 100
        
        # Should trigger disclosure (80% filled)
        assert order_fill.should_disclose() is True
    
    def test_iceberg_completion(self):
        """Test iceberg order completion."""
        order = IcebergOrder(
            iceberg_id="ICEBERG_001",
            parent_order_id="PARENT_001",
            symbol="AAPL",
            side="BUY",
            total_quantity=100,
            displayed_quantity=100,
            disclosure_type=DisclosureType.TIME_BASED,
            disclosure_interval_seconds=60,
            order_type="limit",
            price=150.0
        )
        
        # Fill the entire order
        order.on_child_fill("CHILD_001", 150.0, 100)
        
        assert order.status == IcebergStatus.COMPLETED
        assert order.filled_quantity == 100
        assert order.completed_at is not None
        assert not order.is_active()


class TestIcebergManager:
    """Test IcebergManager functionality."""
    
    def test_manager_operations(self):
        """Test basic manager operations."""
        manager = IcebergManager()
        
        # Create iceberg
        iceberg_id = manager.create_iceberg(
            symbol="AAPL",
            side="BUY",
            total_quantity=1000,
            displayed_quantity=100,
            disclosure_type=DisclosureType.TIME_BASED,
            disclosure_interval_seconds=60
        )
        
        assert len(manager.icebergs) == 1
        iceberg = manager.get_iceberg(iceberg_id)
        assert iceberg is not None
        assert iceberg.total_quantity == 1000
        assert iceberg.displayed_quantity == 100
        
        # Place first child order
        child_order = manager.place_first_child_order(iceberg_id)
        assert child_order is not None
        assert child_order.symbol == "AAPL"
        assert child_order.quantity == 100
        
        # Handle child fill
        new_child = manager.on_child_fill(child_order.order_id, 150.0, 100)
        assert new_child is not None
        assert new_child.quantity == 100


class TestAdvancedOrderManager:
    """Test AdvancedOrderManager integration."""
    
    def test_manager_initialization(self):
        """Test advanced order manager initialization."""
        manager = AdvancedOrderManager()
        
        assert manager.trailing_stop_manager is not None
        assert manager.oco_manager is not None
        assert manager.bracket_manager is not None
        assert manager.iceberg_manager is not None
        assert len(manager.event_listeners) == 0
        assert len(manager.order_mappings) == 0
    
    def test_event_system(self):
        """Test event system functionality."""
        manager = AdvancedOrderManager()
        
        # Track events
        events = []
        
        def event_callback(event_data):
            events.append(event_data)
        
        # Register listener
        manager.register_event_listener(AdvancedOrderEvent.TRAILING_STOP_CREATED, event_callback)
        
        # Create trailing stop (should trigger event)
        order_id = manager.create_trailing_stop(
            symbol="AAPL",
            side="SELL",
            quantity=100,
            initial_stop_price=150.0,
            trailing_type="distance",
            trailing_amount=2.0
        )
        
        # Check event was published
        assert len(events) == 1
        event_data = events[0]
        assert 'trailing_stop' in event_data
    
    def test_trailing_stop_integration(self):
        """Test trailing stop integration."""
        manager = AdvancedOrderManager()
        
        # Create trailing stop
        order_id = manager.create_trailing_stop(
            symbol="AAPL",
            side="SELL",
            quantity=100,
            initial_stop_price=150.0,
            trailing_type="distance",
            trailing_amount=2.0
        )
        
        # Update trailing stop
        results = manager.update_trailing_stop("AAPL", 155.0)
        assert len(results) == 1
        assert results[0]['symbol'] == "AAPL"
        assert results[0]['new_stop_price'] == 153.0
        
        # Trigger trailing stops
        triggered = manager.trigger_trailing_stops("AAPL", 153.0)
        assert len(triggered) == 1
        assert triggered[0] == order_id
    
    def test_oco_integration(self):
        """Test OCO integration."""
        manager = AdvancedOrderManager()
        
        # Create OCO orders
        orders = [
            OrderRequest(
                order_id="ORDER_001",
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=100,
                order_type=OrderType.LIMIT,
                price=155.0,
                time_in_force="gtc"
            ),
            OrderRequest(
                order_id="ORDER_002",
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=100,
                order_type=OrderType.LIMIT,
                price=145.0,
                time_in_force="gtc"
            )
        ]
        
        # Create OCO group
        group_id = manager.create_oco_group(orders)
        
        # Trigger group
        triggered_group = manager.trigger_oco_group("ORDER_001")
        assert triggered_group == group_id
        
        # Get orders to cancel
        to_cancel = manager.get_oco_cancellations("ORDER_001")
        assert "ORDER_002" in to_cancel
    
    def test_bracket_integration(self):
        """Test bracket integration."""
        manager = AdvancedOrderManager()
        
        # Create bracket
        bracket_id = manager.create_bracket(
            symbol="AAPL",
            quantity=100,
            entry_price=150.0,
            profit_target_pct=5.0,
            stop_loss_pct=3.0
        )
        
        # Place entry order
        entry_order = manager.place_bracket_entry(bracket_id)
        assert entry_order is not None
        
        # Handle entry fill
        exit_orders = manager.on_bracket_entry_filled(entry_order.order_id, 150.0, 100)
        assert len(exit_orders) == 2
    
    def test_iceberg_integration(self):
        """Test iceberg integration."""
        manager = AdvancedOrderManager()
        
        # Create iceberg
        iceberg_id = manager.create_iceberg(
            symbol="AAPL",
            side="BUY",
            total_quantity=1000,
            displayed_quantity=100,
            disclosure_type="time",
            disclosure_interval=60
        )
        
        # Place first child
        child_order = manager.place_iceberg_first_child(iceberg_id)
        assert child_order is not None
        
        # Handle child fill
        new_child = manager.on_iceberg_child_fill(child_order.order_id, 150.0, 100)
        assert new_child is not None
    
    def test_order_info_and_cancellation(self):
        """Test order info and cancellation."""
        manager = AdvancedOrderManager()
        
        # Create trailing stop
        order_id = manager.create_trailing_stop(
            symbol="AAPL",
            side="SELL",
            quantity=100,
            initial_stop_price=150.0,
            trailing_type="distance",
            trailing_amount=2.0
        )
        
        # Get order info
        info = manager.get_order_info(order_id)
        assert info is not None
        assert info['type'] == 'trailing_stop'
        assert info['symbol'] == "AAPL"
        
        # Cancel order (trailing stops don't have child orders)
        cancelled = manager.cancel_advanced_order(order_id)
        assert isinstance(cancelled, list)
    
    def test_status_summary(self):
        """Test status summary."""
        manager = AdvancedOrderManager()
        
        # Create various orders
        ts_id = manager.create_trailing_stop(
            symbol="AAPL",
            side="SELL",
            quantity=100,
            initial_stop_price=150.0,
            trailing_type="distance",
            trailing_amount=2.0
        )
        
        iceberg_id = manager.create_iceberg(
            symbol="AAPL",
            side="BUY",
            total_quantity=1000,
            displayed_quantity=100,
            disclosure_type="time",
            disclosure_interval=60
        )
        
        # Get status summary
        summary = manager.get_status_summary()
        
        assert 'trailing_stops' in summary
        assert 'oco_groups' in summary
        assert 'brackets' in summary
        assert 'icebergs' in summary
        assert 'total_advanced_orders' in summary
        assert summary['total_advanced_orders'] >= 2


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])