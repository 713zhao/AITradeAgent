"""
Phase 3 Portfolio Management - Comprehensive Test Suite

Tests for:
- Portfolio data models (Position, Trade, Portfolio)
- Trade repository CRUD operations
- Portfolio manager position/trade management
- Equity calculator metrics
- Phase 2→3 integration (DECISION_MADE → trade execution)
"""

import pytest
from datetime import datetime, timedelta
from finance_service.portfolio.models import (
    Position, Trade, Portfolio, TradeStatus
)
from finance_service.portfolio.trade_repository import TradeRepository
from finance_service.portfolio.portfolio_manager import PortfolioManager
from finance_service.portfolio.equity_calculator import EquityCalculator


# =====================
# FIXTURES
# =====================

@pytest.fixture
def trade_repository():
    """Create fresh trade repository."""
    return TradeRepository()


@pytest.fixture
def portfolio_manager():
    """Create portfolio manager with standard initial cash."""
    return PortfolioManager(initial_cash=100000.0)


@pytest.fixture
def equity_calculator():
    """Create equity calculator."""
    return EquityCalculator()


@pytest.fixture
def sample_decision():
    """Sample decision from Phase 2."""
    return {
        "symbol": "AAPL",
        "decision": "BUY",
        "confidence": 0.75,
        "signals": {"rsi": "oversold", "macd": "bullish"},
        "stop_loss": 150.0,
        "take_profit": 165.0,
        "reason": "RSI oversold + MACD bullish"
    }


# =====================
# POSITION TESTS
# =====================

class TestPositionModel:
    """Test Position data model."""
    
    def test_position_initialization(self):
        """Test creating a position."""
        pos = Position(symbol="AAPL", quantity=10, avg_cost=150.0, current_price=155.0)
        assert pos.symbol == "AAPL"
        assert pos.quantity == 10
        assert pos.avg_cost == 150.0
        assert pos.current_price == 155.0
    
    def test_position_market_value(self):
        """Test position market value calculation."""
        pos = Position(symbol="AAPL", quantity=10, avg_cost=150.0, current_price=155.0)
        assert pos.market_value() == 1550.0  # 10 * 155
    
    def test_position_cost_basis(self):
        """Test position cost basis calculation."""
        pos = Position(symbol="AAPL", quantity=10, avg_cost=150.0, current_price=155.0)
        assert pos.cost_basis() == 1500.0  # 10 * 150
    
    def test_position_unrealized_pnl(self):
        """Test unrealized P&L calculation."""
        pos = Position(symbol="AAPL", quantity=10, avg_cost=150.0, current_price=155.0)
        assert pos.unrealized_pnl() == 50.0  # (155 - 150) * 10
    
    def test_position_unrealized_pnl_pct(self):
        """Test unrealized P&L percentage."""
        pos = Position(symbol="AAPL", quantity=10, avg_cost=150.0, current_price=155.0)
        assert pos.unrealized_pnl_pct() == pytest.approx(3.333, abs=0.01)  # 50/1500 * 100
    
    def test_position_loss(self):
        """Test position with loss."""
        pos = Position(symbol="AAPL", quantity=10, avg_cost=150.0, current_price=145.0)
        assert pos.unrealized_pnl() == -50.0
        assert pos.unrealized_pnl_pct() == pytest.approx(-3.333, abs=0.01)
    
    def test_position_to_dict(self):
        """Test position serialization."""
        pos = Position(symbol="AAPL", quantity=10, avg_cost=150.0, current_price=155.0)
        d = pos.to_dict()
        assert d["symbol"] == "AAPL"
        assert d["quantity"] == 10
        assert d["unrealized_pnl"] == 50.0


# =====================
# TRADE TESTS
# =====================

class TestTradeModel:
    """Test Trade data model."""
    
    def test_trade_initialization(self):
        """Test creating a trade."""
        trade = Trade(
            trade_id="TRADE_000001",
            task_id="TASK_001",
            symbol="AAPL",
            side="BUY",
            quantity=10,
            price=150.0,
        )
        assert trade.trade_id == "TRADE_000001"
        assert trade.symbol == "AAPL"
        assert trade.side == "BUY"
        assert trade.status == TradeStatus.PENDING
    
    def test_trade_fill_percentage(self):
        """Test trade fill percentage."""
        trade = Trade(
            trade_id="TRADE_000001",
            task_id="TASK_001",
            symbol="AAPL",
            side="BUY",
            quantity=10,
            price=150.0,
            filled_quantity=7,
            status=TradeStatus.PARTIALLY_FILLED,
        )
        assert trade.fill_percentage() == 70.0
    
    def test_trade_is_filled(self):
        """Test is_filled check."""
        trade_pending = Trade(
            trade_id="TRADE_000001",
            task_id="TASK_001",
            symbol="AAPL",
            side="BUY",
            quantity=10,
            price=150.0,
            status=TradeStatus.PENDING,
        )
        assert not trade_pending.is_filled()
        
        trade_filled = Trade(
            trade_id="TRADE_000002",
            task_id="TASK_002",
            symbol="AAPL",
            side="BUY",
            quantity=10,
            price=150.0,
            status=TradeStatus.FILLED,
            filled_quantity=10,
        )
        assert trade_filled.is_filled()
    
    def test_trade_to_dict(self):
        """Test trade serialization."""
        trade = Trade(
            trade_id="TRADE_000001",
            task_id="TASK_001",
            symbol="AAPL",
            side="BUY",
            quantity=10,
            price=150.0,
            confidence=0.75,
        )
        d = trade.to_dict()
        assert d["trade_id"] == "TRADE_000001"
        assert d["symbol"] == "AAPL"
        assert d["confidence"] == 0.75


# =====================
# TRADE REPOSITORY TESTS
# =====================

class TestTradeRepository:
    """Test trade repository CRUD operations."""
    
    def test_create_trade(self, trade_repository):
        """Test creating a trade."""
        trade = trade_repository.create_trade(
            task_id="TASK_001",
            symbol="AAPL",
            side="BUY",
            quantity=10,
            price=150.0,
            decision={"decision": "BUY"},
            confidence=0.75,
        )
        assert trade.trade_id.startswith("TRADE_")
        assert trade.symbol == "AAPL"
        assert len(trade_repository.trades) == 1
    
    def test_get_trade(self, trade_repository):
        """Test retrieving a trade."""
        trade = trade_repository.create_trade(
            task_id="TASK_001",
            symbol="AAPL",
            side="BUY",
            quantity=10,
            price=150.0,
            decision={},
            confidence=0.75,
        )
        retrieved = trade_repository.get_trade(trade.trade_id)
        assert retrieved == trade
    
    def test_get_trades_by_symbol(self, trade_repository):
        """Test filtering trades by symbol."""
        trade_repository.create_trade(
            task_id="TASK_001", symbol="AAPL", side="BUY",
            quantity=10, price=150.0, decision={}, confidence=0.75
        )
        trade_repository.create_trade(
            task_id="TASK_002", symbol="MSFT", side="BUY",
            quantity=5, price=300.0, decision={}, confidence=0.80
        )
        
        aapl_trades = trade_repository.get_trades_by_symbol("AAPL")
        assert len(aapl_trades) == 1
        assert aapl_trades[0].symbol == "AAPL"
    
    def test_update_trade_status(self, trade_repository):
        """Test updating trade status."""
        trade = trade_repository.create_trade(
            task_id="TASK_001",
            symbol="AAPL",
            side="BUY",
            quantity=10,
            price=150.0,
            decision={},
            confidence=0.75,
        )
        
        updated = trade_repository.update_trade_status(
            trade.trade_id,
            TradeStatus.FILLED,
            filled_quantity=10,
            executed_by="system"
        )
        assert updated.status == TradeStatus.FILLED
        assert updated.filled_quantity == 10
        assert updated.executed_by == "system"
    
    def test_create_position(self, trade_repository):
        """Test creating a position."""
        pos = trade_repository.create_position(
            symbol="AAPL",
            quantity=10,
            avg_cost=150.0,
        )
        assert pos.symbol == "AAPL"
        assert pos.quantity == 10
        assert pos.avg_cost == 150.0
        assert "AAPL" in trade_repository.positions
    
    def test_update_position(self, trade_repository):
        """Test updating position."""
        trade_repository.create_position(symbol="AAPL", quantity=10, avg_cost=150.0)
        updated = trade_repository.update_position(
            "AAPL",
            quantity=15,
            current_price=155.0
        )
        assert updated.quantity == 15
        assert updated.current_price == 155.0
    
    def test_close_position(self, trade_repository):
        """Test closing a position."""
        trade_repository.create_position(symbol="AAPL", quantity=10, avg_cost=150.0)
        closed = trade_repository.close_position("AAPL")
        assert closed is not None
        assert "AAPL" not in trade_repository.positions


# =====================
# PORTFOLIO MANAGER TESTS
# =====================

class TestPortfolioManager:
    """Test portfolio manager operations."""
    
    def test_execute_buy(self, portfolio_manager):
        """Test executing a BUY trade."""
        trade = portfolio_manager.execute_buy(
            task_id="TASK_001",
            symbol="AAPL",
            quantity=10,
            price=150.0,
            decision={"decision": "BUY"},
            confidence=0.75,
            stop_loss=145.0,
            take_profit=160.0,
            reason="RSI oversold"
        )
        
        assert trade.side == "BUY"
        assert trade.symbol == "AAPL"
        assert portfolio_manager.get_position("AAPL") is not None
    
    def test_execute_sell(self, portfolio_manager):
        """Test executing a SELL trade."""
        # First buy
        portfolio_manager.execute_buy(
            task_id="TASK_001",
            symbol="AAPL",
            quantity=10,
            price=150.0,
            decision={},
            confidence=0.75
        )
        
        # Then sell
        trade = portfolio_manager.execute_sell(
            task_id="TASK_002",
            symbol="AAPL",
            quantity=10,
            price=155.0,
            decision={},
            confidence=0.75,
            reason="Take profit"
        )
        
        assert trade.side == "SELL"
        assert portfolio_manager.get_position("AAPL") is None
    
    def test_fill_trade(self, portfolio_manager):
        """Test filling a trade."""
        trade = portfolio_manager.execute_buy(
            task_id="TASK_001",
            symbol="AAPL",
            quantity=10,
            price=150.0,
            decision={},
            confidence=0.75
        )
        
        filled = portfolio_manager.fill_trade(trade.trade_id)
        assert filled.status == TradeStatus.FILLED
        assert filled.filled_quantity == 10
    
    def test_cancel_trade(self, portfolio_manager):
        """Test cancelling a trade."""
        trade = portfolio_manager.execute_buy(
            task_id="TASK_001",
            symbol="AAPL",
            quantity=10,
            price=150.0,
            decision={},
            confidence=0.75
        )
        
        cancelled = portfolio_manager.cancel_trade(trade.trade_id, reason="User cancelled")
        assert cancelled.status == TradeStatus.CANCELLED
        assert cancelled.error_reason == "User cancelled"
    
    def test_get_portfolio(self, portfolio_manager):
        """Test getting portfolio state."""
        portfolio_manager.execute_buy(
            task_id="TASK_001",
            symbol="AAPL",
            quantity=10,
            price=150.0,
            decision={},
            confidence=0.75
        )
        
        portfolio = portfolio_manager.get_portfolio()
        assert portfolio.initial_cash == 100000.0
        assert portfolio.position_count() == 1
    
    def test_get_position_pnl(self, portfolio_manager):
        """Test position-level P&L calculation."""
        portfolio_manager.execute_buy(
            task_id="TASK_001",
            symbol="AAPL",
            quantity=10,
            price=150.0,
            decision={},
            confidence=0.75
        )
        
        # Update price (simulating market movement)
        portfolio_manager.update_position_price("AAPL", 155.0)
        
        pnl, pnl_pct = portfolio_manager.get_position_pnl("AAPL")
        assert pnl == 50.0
        assert pnl_pct == pytest.approx(3.333, abs=0.01)
    
    def test_get_equity_metrics(self, portfolio_manager):
        """Test getting equity metrics."""
        portfolio_manager.execute_buy(
            task_id="TASK_001",
            symbol="AAPL",
            quantity=10,
            price=150.0,
            decision={},
            confidence=0.75
        )
        
        metrics = portfolio_manager.get_equity_metrics()
        assert "total_equity" in metrics
        assert "total_return_pct" in metrics
        assert "position_count" in metrics


# =====================
# PORTFOLIO TESTS
# =====================

class TestPortfolioModel:
    """Test Portfolio data model and calculations."""
    
    def test_portfolio_initialization(self):
        """Test creating a portfolio."""
        portfolio = Portfolio(initial_cash=100000.0)
        assert portfolio.initial_cash == 100000.0
        assert portfolio.current_cash == 100000.0
        assert portfolio.total_equity() == 100000.0
    
    def test_portfolio_total_equity(self):
        """Test portfolio total equity calculation."""
        portfolio = Portfolio(initial_cash=100000.0, current_cash=90000.0)
        pos = Position(symbol="AAPL", quantity=10, avg_cost=150.0, current_price=155.0)
        portfolio.positions["AAPL"] = pos
        
        # Total = cash + position value
        expected = 90000.0 + 1550.0  # 10 * 155
        assert portfolio.total_equity() == expected
    
    def test_portfolio_unrealized_pnl(self):
        """Test portfolio unrealized P&L."""
        portfolio = Portfolio(initial_cash=100000.0)
        pos = Position(symbol="AAPL", quantity=10, avg_cost=150.0, current_price=155.0)
        portfolio.positions["AAPL"] = pos
        
        assert portfolio.unrealized_pnl() == 50.0
    
    def test_portfolio_total_return_pct(self):
        """Test portfolio total return percentage."""
        portfolio = Portfolio(initial_cash=100000.0, current_cash=100000.0)
        pos = Position(symbol="AAPL", quantity=10, avg_cost=150.0, current_price=155.0)
        portfolio.positions["AAPL"] = pos
        
        # +$50 P&L on $100,000 initial = 0.05%
        expected_return = (50.0 / 100000.0) * 100
        assert portfolio.total_return_pct() == pytest.approx(expected_return, abs=0.001)
    
    def test_portfolio_drawdown(self):
        """Test portfolio drawdown calculation."""
        portfolio = Portfolio(initial_cash=100000.0, current_cash=95000.0)
        pos = Position(symbol="AAPL", quantity=10, avg_cost=150.0, current_price=145.0)
        portfolio.positions["AAPL"] = pos
        
        # Equity = 95000 + 1450 = 96450
        # Drawdown from 100000 = 3550/100000 = 3.55%
        expected_dd = ((100000 - 96450) / 100000) * 100
        assert portfolio.drawdown_pct() == pytest.approx(expected_dd, abs=0.01)
    
    def test_portfolio_to_dict(self):
        """Test portfolio serialization."""
        portfolio = Portfolio(initial_cash=100000.0)
        d = portfolio.to_dict()
        assert d["initial_cash"] == 100000.0
        assert "total_equity" in d
        assert "unrealized_pnl" in d


# =====================
# EQUITY CALCULATOR TESTS
# =====================

class TestEquityCalculator:
    """Test equity calculation and risk metrics."""
    
    def test_snapshot_equity(self, equity_calculator):
        """Test creating equity snapshot."""
        portfolio = Portfolio(initial_cash=100000.0)
        snapshot = equity_calculator.snapshot_equity(portfolio)
        
        assert snapshot["initial_cash"] == 100000.0
        assert snapshot["total_equity"] == 100000.0
        assert len(equity_calculator.snapshots) == 1
    
    def test_calculate_return(self, equity_calculator):
        """Test return calculation."""
        ret = equity_calculator.calculate_return(100000.0, 105000.0)
        assert ret == 5000.0
    
    def test_calculate_return_pct(self, equity_calculator):
        """Test return percentage calculation."""
        ret_pct = equity_calculator.calculate_return_pct(100000.0, 105000.0)
        assert ret_pct == 5.0
    
    def test_calculate_max_drawdown(self, equity_calculator):
        """Test max drawdown calculation."""
        portfolio1 = Portfolio(initial_cash=100000.0)
        equity_calculator.snapshot_equity(portfolio1)
        
        portfolio2 = Portfolio(initial_cash=100000.0, current_cash=90000.0)
        equity_calculator.snapshot_equity(portfolio2)
        
        portfolio3 = Portfolio(initial_cash=100000.0, current_cash=92000.0)
        equity_calculator.snapshot_equity(portfolio3)
        
        max_dd, peak_idx, trough_idx = equity_calculator.calculate_max_drawdown()
        assert max_dd > 0
        assert peak_idx < trough_idx
    
    def test_calculate_sharpe_ratio(self, equity_calculator):
        """Test Sharpe ratio calculation."""
        returns = [0.01, 0.02, -0.01, 0.015, 0.025]
        sharpe = equity_calculator.calculate_sharpe_ratio(returns)
        assert isinstance(sharpe, float)
    
    def test_calculate_sortino_ratio(self, equity_calculator):
        """Test Sortino ratio calculation."""
        returns = [0.01, 0.02, -0.01, 0.015, 0.025]
        sortino = equity_calculator.calculate_sortino_ratio(returns)
        assert isinstance(sortino, float)
    
    def test_calculate_profit_factor(self, equity_calculator):
        """Test profit factor calculation."""
        pf = equity_calculator.calculate_profit_factor(gross_profit=5000.0, gross_loss=1000.0)
        assert pf == 5.0  # 5000/1000


# =====================
# INTEGRATION TESTS
# =====================

class TestPhase3Integration:
    """Test Phase 2→3 integration."""
    
    def test_decision_to_trade_flow(self, portfolio_manager, sample_decision):
        """Test full flow: Decision → Trade → Position."""
        # Simulate Phase 2 decision
        symbol = sample_decision["symbol"]
        
        # Execute trade based on decision
        trade = portfolio_manager.execute_buy(
            task_id="PHASE2_TASK_001",
            symbol=symbol,
            quantity=10,
            price=155.0,
            decision=sample_decision,
            confidence=sample_decision["confidence"],
            stop_loss=sample_decision["stop_loss"],
            take_profit=sample_decision["take_profit"],
            reason=sample_decision["reason"]
        )
        
        # Fill trade
        portfolio_manager.fill_trade(trade.trade_id)
        
        # Verify position created
        position = portfolio_manager.get_position(symbol)
        assert position is not None
        assert position.quantity == 10
        
        # Get portfolio state
        portfolio = portfolio_manager.get_portfolio()
        assert portfolio.position_count() == 1
    
    def test_multiple_positions(self, portfolio_manager):
        """Test portfolio with multiple positions."""
        # Buy AAPL
        portfolio_manager.execute_buy(
            task_id="TASK_001",
            symbol="AAPL",
            quantity=10,
            price=150.0,
            decision={},
            confidence=0.75
        )
        
        # Buy MSFT
        portfolio_manager.execute_buy(
            task_id="TASK_002",
            symbol="MSFT",
            quantity=5,
            price=300.0,
            decision={},
            confidence=0.80
        )
        
        portfolio = portfolio_manager.get_portfolio()
        assert portfolio.position_count() == 2
        
        # Update prices
        portfolio_manager.update_position_price("AAPL", 155.0)
        portfolio_manager.update_position_price("MSFT", 310.0)
        
        # Check combined P&L
        aapl_pnl, _ = portfolio_manager.get_position_pnl("AAPL")
        msft_pnl, _ = portfolio_manager.get_position_pnl("MSFT")
        
        assert aapl_pnl == 50.0  # (155-150)*10
        assert msft_pnl == 50.0  # (310-300)*5
    
    def test_portfolio_persistence(self, portfolio_manager):
        """Test portfolio state persists across operations."""
        # Execute multiple trades
        for i in range(3):
            portfolio_manager.execute_buy(
                task_id=f"TASK_{i:03d}",
                symbol=f"STOCK_{i}",
                quantity=10,
                price=100.0 + i,
                decision={},
                confidence=0.75
            )
        
        # Verify all positions exist
        portfolio = portfolio_manager.get_portfolio()
        assert portfolio.position_count() == 3
        assert portfolio.trade_count() == 3
        
        # Portfolio state persists - compare positions by symbol
        positions = portfolio_manager.get_positions()
        assert len(positions) == 3
        for pos in positions:
            assert pos.symbol in portfolio.positions
