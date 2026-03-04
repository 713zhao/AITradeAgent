"""
Phase 6.1: Live Trading Integration Tests

Tests for broker integrations including:
- Paper trading broker
- Order placement and management
- Position tracking
- Account management
- Slippage simulation
- Order fill processing
"""

import pytest
from datetime import datetime, timedelta
from finance_service.brokers import (
    PaperBroker,
    OrderRequest,
    OrderStatus,
    OrderSide,
    OrderType,
)


class TestPaperBrokerBasics:
    """Test basic paper broker functionality"""
    
    @pytest.fixture
    def broker(self):
        """Create a paper broker instance"""
        return PaperBroker(initial_cash=100000.0, slippage_bps=1.0)
    
    def test_broker_initialization(self, broker):
        """Test broker initializes correctly"""
        assert broker.broker_name == "Paper"
        assert broker.paper_trading is True
        assert broker.cash == 100000.0
        assert broker.initial_cash == 100000.0
        assert broker.slippage_bps > 0
        print("✅ Broker initialized correctly")
    
    def test_get_account(self, broker):
        """Test getting account information"""
        account = broker.get_account()
        
        assert account.account_number == "PAPER_001"
        assert account.cash == 100000.0
        assert account.buying_power > account.cash  # Margin
        assert account.total_equity == 100000.0
        assert account.is_margin is True
        assert account.can_daytrade is True
        print("✅ Account information correct")
    
    def test_get_cash(self, broker):
        """Test getting available cash"""
        assert broker.get_cash() == 100000.0
    
    def test_get_buying_power(self, broker):
        """Test getting buying power"""
        bp = broker.get_buying_power()
        assert bp == 100000.0 * 4  # 4x margin
        print(f"✅ Buying power: ${bp:,.2f}")
    
    def test_account_value(self, broker):
        """Test account value calculation"""
        value = broker.get_account_value()
        assert value == 100000.0
    
    def test_no_positions_initially(self, broker):
        """Test there are no positions initially"""
        positions = broker.get_positions()
        assert len(positions) == 0
        print("✅ No positions initially")


class TestOrderPlacement:
    """Test order placement and management"""
    
    @pytest.fixture
    def broker(self):
        """Create broker with stock quotes"""
        broker = PaperBroker()
        broker.set_quote("AAPL", bid=149.5, ask=150.5, last=150.0)
        broker.set_quote("MSFT", bid=299.0, ask=300.5, last=299.75)
        broker.set_quote("GOOGL", bid=139.0, ask=141.0, last=140.0)
        return broker
    
    def test_place_market_buy_order(self, broker):
        """Test placing a market BUY order"""
        order_req = OrderRequest(
            order_id="ORDER_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        
        order = broker.place_order(order_req)
        
        assert order.order_id == "ORDER_001"
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.quantity == 10
        assert order.status == OrderStatus.SUBMITTED
        assert order.filled_quantity == 0  # Not filled yet
        print(f"✅ Market BUY order placed: {order.order_id}")
    
    def test_place_market_sell_order(self, broker):
        """Test placing a market SELL order"""
        # First add a position
        order_req_buy = OrderRequest(
            order_id="BUY_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        broker.place_order(order_req_buy)
        broker.process_fills()
        
        # Then sell
        order_req_sell = OrderRequest(
            order_id="SELL_001",
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        order = broker.place_order(order_req_sell)
        
        assert order.side == OrderSide.SELL
        assert order.status == OrderStatus.SUBMITTED
        print(f"✅ Market SELL order placed: {order.order_id}")
    
    def test_place_limit_order(self, broker):
        """Test placing a limit order"""
        order_req = OrderRequest(
            order_id="LIMIT_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=5,
            order_type=OrderType.LIMIT,
            price=149.0,  # Below market
        )
        
        order = broker.place_order(order_req)
        
        assert order.order_type == OrderType.LIMIT
        assert order.quantity == 5
        print(f"✅ Limit order placed: {order.order_id}")
    
    def test_order_validation(self, broker):
        """Test order validation"""
        # Invalid: zero quantity
        with pytest.raises(ValueError):
            OrderRequest(
                order_id="INVALID",
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=0,
                order_type=OrderType.MARKET,
            )
        
        # Invalid: limit order without price
        with pytest.raises(ValueError):
            OrderRequest(
                order_id="INVALID2",
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=10,
                order_type=OrderType.LIMIT,
            )
        
        print("✅ Order validation working")


class TestOrderFills:
    """Test order fill processing"""
    
    @pytest.fixture
    def broker(self):
        """Create broker with quotes"""
        broker = PaperBroker(fill_delay_seconds=0)  # Instant fills for testing
        broker.set_quote("AAPL", bid=149.5, ask=150.5)
        return broker
    
    def test_order_fill_simple(self, broker):
        """Test simple order fill"""
        order_req = OrderRequest(
            order_id="FILL_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        
        order = broker.place_order(order_req)
        assert order.status == OrderStatus.SUBMITTED
        
        # Process fills
        broker.process_fills()
        order = broker.get_order("FILL_001")
        
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 10
        assert order.avg_fill_price > 0
        print(f"✅ Order filled at ${order.avg_fill_price:.2f}")
    
    def test_order_fill_updates_cash(self, broker):
        """Test that fills update cash correctly"""
        initial_cash = broker.cash
        
        order_req = OrderRequest(
            order_id="CASH_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        
        broker.place_order(order_req)
        broker.process_fills()
        
        # Cash should be reduced
        assert broker.cash < initial_cash
        cost = initial_cash - broker.cash
        print(f"✅ Cash reduced by ${cost:,.2f}")
    
    def test_buy_creates_position(self, broker):
        """Test that BUY orders create positions"""
        order_req = OrderRequest(
            order_id="POS_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        
        broker.place_order(order_req)
        broker.process_fills()
        
        position = broker.get_position("AAPL")
        assert position is not None
        assert position.quantity == 10
        assert position.side == "long"
        print(f"✅ Position created: {position.quantity} shares")
    
    def test_sell_closes_position(self, broker):
        """Test that SELL orders reduce/close positions"""
        # Buy first
        buy_req = OrderRequest(
            order_id="BUY_SL",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        broker.place_order(buy_req)
        broker.process_fills()
        
        position = broker.get_position("AAPL")
        assert position.quantity == 10
        
        # Sell
        sell_req = OrderRequest(
            order_id="SELL_SL",
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        broker.place_order(sell_req)
        broker.process_fills()
        
        position = broker.get_position("AAPL")
        assert position is None  # Position closed
        print("✅ Position closed")


class TestSlippage:
    """Test slippage simulation"""
    
    @pytest.fixture
    def broker(self):
        """Create broker with 1 bps slippage"""
        return PaperBroker(slippage_bps=1.0, fill_delay_seconds=0)  # Instant fills
    
    def test_buy_slippage(self, broker):
        """Test slippage on BUY orders"""
        bid = 149.5
        ask = 150.5
        broker.set_quote("AAPL", bid=bid, ask=ask)
        
        order_req = OrderRequest(
            order_id="SLIP_BUY",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        
        broker.place_order(order_req)
        broker.process_fills()
        
        order = broker.get_order("SLIP_BUY")
        # Fill should be at ask + slippage
        assert order.avg_fill_price > ask
        print(f"✅ BUY slippage: ask=${ask}, filled=${order.avg_fill_price:.4f}")
    
    def test_sell_slippage(self, broker):
        """Test slippage on SELL orders"""
        bid = 149.5
        ask = 150.5
        broker.set_quote("AAPL", bid=bid, ask=ask)
        
        # Buy first
        buy_req = OrderRequest(
            order_id="BUY_SLP2",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        broker.place_order(buy_req)
        broker.process_fills()
        
        # Sell
        sell_req = OrderRequest(
            order_id="SELL_SLP",
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        broker.place_order(sell_req)
        broker.process_fills()
        
        order = broker.get_order("SELL_SLP")
        # Fill should be at bid - slippage
        assert order.avg_fill_price < bid
        print(f"✅ SELL slippage: bid=${bid}, filled=${order.avg_fill_price:.4f}")


class TestPositionManagement:
    """Test position tracking and management"""
    
    @pytest.fixture
    def broker(self):
        """Create broker with positions"""
        broker = PaperBroker(fill_delay_seconds=0)  # Instant fills
        broker.set_quote("AAPL", bid=149.5, ask=150.5)
        broker.set_quote("MSFT", bid=299.0, ask=300.5)
        broker.set_quote("GOOGL", bid=139.0, ask=141.0)
        return broker
    
    def test_multiple_positions(self, broker):
        """Test tracking multiple positions"""
        # Buy AAPL
        order_req1 = OrderRequest(
            order_id="MULTI_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        broker.place_order(order_req1)
        broker.process_fills()
        
        # Buy MSFT
        order_req2 = OrderRequest(
            order_id="MULTI_002",
            symbol="MSFT",
            side=OrderSide.BUY,
            quantity=5,
            order_type=OrderType.MARKET,
        )
        broker.place_order(order_req2)
        broker.process_fills()
        
        # Check positions
        positions = broker.get_positions()
        assert len(positions) == 2
        assert "AAPL" in positions
        assert "MSFT" in positions
        print(f"✅ Multiple positions: {len(positions)}")
    
    def test_average_cost_calculation(self, broker):
        """Test weighted average cost calculation"""
        # Buy 10 at 150
        buy1 = OrderRequest(
            order_id="AVG_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        broker.place_order(buy1)
        broker.process_fills()
        
        pos1 = broker.get_position("AAPL")
        cost1 = pos1.entry_price
        
        # Buy 10 more (likely at slightly different price due to market movement)
        broker.set_quote("AAPL", bid=150.5, ask=151.5)
        buy2 = OrderRequest(
            order_id="AVG_002",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        broker.place_order(buy2)
        broker.process_fills()
        
        pos2 = broker.get_position("AAPL")
        # Should have 20 shares with weighted average cost
        assert pos2.quantity == 20
        assert pos2.entry_price > 0
        print(f"✅ Average cost: {pos2.entry_price:.2f}")
    
    def test_close_position(self, broker):
        """Test closing a position"""
        # Create position
        buy = OrderRequest(
            order_id="CLOSE_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        broker.place_order(buy)
        broker.process_fills()
        
        assert "AAPL" in broker.get_positions()
        
        # Close position
        close_order = broker.close_position("AAPL")
        broker.process_fills()
        
        assert "AAPL" not in broker.get_positions()
        print("✅ Position closed successfully")


class TestOrderManagement:
    """Test order query and cancellation"""
    
    @pytest.fixture
    def broker(self):
        """Create broker"""
        broker = PaperBroker(fill_delay_seconds=10.0)  # Long delay for cancellation
        broker.set_quote("AAPL", bid=149.5, ask=150.5)
        return broker
    
    def test_get_order(self, broker):
        """Test retrieving an order"""
        order_req = OrderRequest(
            order_id="GET_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        created = broker.place_order(order_req)
        
        retrieved = broker.get_order("GET_001")
        assert retrieved is not None
        assert retrieved.order_id == created.order_id
        print("✅ Order retrieved")
    
    def test_get_orders_filtered(self, broker):
        """Test getting orders filtered by status"""
        # Place order (will be SUBMITTED)
        order_req = OrderRequest(
            order_id="FILT_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        broker.place_order(order_req)
        
        # Get submitted orders
        submitted = broker.get_orders(OrderStatus.SUBMITTED)
        assert len(submitted) >= 1
        print(f"✅ Found {len(submitted)} submitted orders")
    
    def test_cancel_order(self, broker):
        """Test cancelling an order"""
        order_req = OrderRequest(
            order_id="CANCEL_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        broker.place_order(order_req)
        
        # Cancel before it fills
        cancelled = broker.cancel_order("CANCEL_001")
        assert cancelled.status == OrderStatus.CANCELLED
        print("✅ Order cancelled")
    
    def test_cannot_cancel_filled_order(self, broker):
        """Test that filled orders cannot be cancelled"""
        broker.fill_delay_seconds = 0  # Make it instant fill
        order_req = OrderRequest(
            order_id="CANCEL_FILLED",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        broker.place_order(order_req)
        broker.process_fills()
        
        # Try to cancel filled order
        with pytest.raises(ValueError):
            broker.cancel_order("CANCEL_FILLED")
        
        print("✅ Cannot cancel filled order")


class TestAccountState:
    """Test account state management"""
    
    @pytest.fixture
    def broker(self):
        """Create broker"""
        broker = PaperBroker(initial_cash=100000.0, fill_delay_seconds=0)
        broker.set_quote("AAPL", bid=149.5, ask=150.5)
        return broker
    
    def test_cash_tracking(self, broker):
        """Test cash is properly tracked"""
        initial_cash = broker.cash
        
        # Place buy order
        order_req = OrderRequest(
            order_id="CASH_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        broker.place_order(order_req)
        broker.process_fills()
        
        # Cash should be reduced
        spent = initial_cash - broker.cash
        assert spent > 0
        print(f"✅ Cash tracking: spent ${spent:,.2f}")
    
    def test_account_value_includes_positions(self, broker):
        """Test account value includes position values"""
        initial_value = broker.get_account_value()
        
        # Buy position
        order_req = OrderRequest(
            order_id="VAL_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        broker.place_order(order_req)
        broker.process_fills()
        
        # Account value should remain roughly same (position + remaining cash)
        final_value = broker.get_account_value()
        # Allow for slippage (5 bps on ask price ~2.5% of transaction)
        assert abs(final_value - initial_value) < 50.0  # Within $50 due to slippage
        print(f"✅ Account value tracking: ${final_value:,.2f}")
    
    def test_reset_broker(self, broker):
        """Test resetting broker to initial state"""
        # Create some activity
        order_req = OrderRequest(
            order_id="RESET_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        broker.place_order(order_req)
        broker.process_fills()
        
        assert len(broker.get_positions()) > 0
        
        # Reset
        broker.reset()
        
        assert broker.cash == 100000.0
        assert len(broker.get_positions()) == 0
        assert len(broker.orders) == 0
        assert len(broker.filled_trades) == 0
        print("✅ Broker reset to initial state")


class TestFilledTrades:
    """Test tracking filled trades"""
    
    @pytest.fixture
    def broker(self):
        """Create broker"""
        broker = PaperBroker(fill_delay_seconds=0)  # Instant fills
        broker.set_quote("AAPL", bid=149.5, ask=150.5)
        broker.set_quote("MSFT", bid=299.0, ask=300.5)
        return broker
    
    def test_filled_trades_recorded(self, broker):
        """Test that filled trades are recorded"""
        # Place and fill order
        order_req = OrderRequest(
            order_id="TRADE_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        broker.place_order(order_req)
        broker.process_fills()
        
        trades = broker.get_filled_trades()
        assert len(trades) == 1
        assert trades[0]["symbol"] == "AAPL"
        assert trades[0]["quantity"] == 10
        print(f"✅ Filled trade recorded: {trades[0]}")
    
    def test_multiple_fills_tracked(self, broker):
        """Test multiple fills are tracked"""
        # Trade 1
        req1 = OrderRequest(
            order_id="TRK_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
        )
        broker.place_order(req1)
        broker.process_fills()
        
        # Trade 2
        req2 = OrderRequest(
            order_id="TRK_002",
            symbol="MSFT",
            side=OrderSide.BUY,
            quantity=5,
            order_type=OrderType.MARKET,
        )
        broker.place_order(req2)
        broker.process_fills()
        
        trades = broker.get_filled_trades()
        assert len(trades) == 2
        print(f"✅ {len(trades)} trades tracked")
