"""Unit tests for finance service components"""
import pytest
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from finance_service.tools.indicator_tools import IndicatorTools
from finance_service.tools.risk_tools import RiskTools
from finance_service.sim.portfolio import Portfolio
from finance_service.core.models import Position


class TestIndicators:
    """Test technical indicator calculations"""
    
    def test_rsi_calculation(self):
        """Test RSI calculation"""
        prices = [44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
                  45.89, 46.03, 45.61, 46.28, 46.00, 46.00, 46.00, 46.00, 46.13, 46.12]
        
        rsi = IndicatorTools.calc_rsi(prices, 14)
        
        assert len(rsi) > 0
        assert all(0 <= r <= 100 for r in rsi)
        assert isinstance(rsi[-1], float)
    
    def test_sma_calculation(self):
        """Test SMA calculation"""
        prices = list(range(100, 120))
        
        sma = IndicatorTools.calc_sma(prices, 5)
        
        assert len(sma) == len(prices) - 5 + 1
        assert sma[-1] == pytest.approx(118, abs=0.1)
    
    def test_atr_calculation(self):
        """Test ATR calculation"""
        highs = [105, 106, 105.5, 106.5, 107, 106.8]
        lows = [100, 101, 100.5, 101.5, 102, 101.8]
        closes = [102, 103, 102.5, 103.5, 104, 103.8]
        
        atr = IndicatorTools.calc_atr(highs, lows, closes, 3)
        
        assert len(atr) > 0
        assert all(a > 0 for a in atr)
    
    def test_macd_calculation(self):
        """Test MACD calculation"""
        prices = list(range(100, 150))
        
        macd = IndicatorTools.calc_macd(prices, 12, 26, 9)
        
        assert "macd" in macd
        assert "signal" in macd
        assert "histogram" in macd
        assert len(macd["macd"]) > 0


class TestRisk:
    """Test risk management calculations"""
    
    def test_position_sizing(self):
        """Test position size calculation"""
        result = RiskTools.calc_position_size(
            symbol="AAPL",
            current_price=150.0,
            atr=2.0,
            portfolio_equity=100000,
            risk_budget_pct=0.01
        )
        
        assert result["shares"] > 0
        assert result["cost"] == result["shares"] * result["entry_price"]
        assert result["stop_loss"] < result["entry_price"]
    
    def test_trade_validation_buy(self):
        """Test buy trade validation"""
        positions = {}
        result = RiskTools.validate_trade(
            symbol="AAPL",
            action="BUY",
            qty=10,
            price=150.0,
            portfolio_equity=100000,
            existing_positions=positions
        )
        
        assert result["valid"] is True
        assert result["position_pct"] == 0.015  # 10 * 150 / 100000
    
    def test_trade_validation_oversized(self):
        """Test validation rejects oversized position"""
        positions = {}
        result = RiskTools.validate_trade(
            symbol="AAPL",
            action="BUY",
            qty=1000,
            price=150.0,
            portfolio_equity=100000,
            existing_positions=positions
        )
        
        assert result["valid"] is False
        assert len(result["errors"]) > 0


class TestPortfolio:
    """Test portfolio simulation"""
    
    def test_portfolio_initialization(self):
        """Test portfolio creation"""
        portfolio = Portfolio(initial_cash=50000)
        
        assert portfolio.cash == 50000
        assert portfolio.total_value == 50000
        assert len(portfolio.positions) == 0
    
    def test_portfolio_buy(self):
        """Test buy operation"""
        portfolio = Portfolio(initial_cash=100000)
        
        success, msg = portfolio.buy("AAPL", 10, 150.0)
        
        assert success is True
        assert "AAPL" in portfolio.positions
        assert portfolio.positions["AAPL"].qty == 10
        assert portfolio.cash < 100000
    
    def test_portfolio_sell(self):
        """Test sell operation"""
        portfolio = Portfolio(initial_cash=100000)
        
        # Buy first
        portfolio.buy("AAPL", 10, 150.0)
        initial_cash = portfolio.cash
        
        # Sell
        success, msg = portfolio.sell("AAPL", 5, 160.0)
        
        assert success is True
        assert portfolio.positions["AAPL"].qty == 5
        assert portfolio.cash > initial_cash
        assert portfolio.realized_pnl > 0  # Made profit
    
    def test_portfolio_state_json(self):
        """Test portfolio state serialization"""
        portfolio = Portfolio(initial_cash=100000)
        portfolio.buy("AAPL", 10, 150.0)
        portfolio.positions["AAPL"].current_price = 155.0
        
        state = portfolio.get_state()
        
        assert "cash" in state
        assert "equity" in state
        assert "total_value" in state
        assert "positions" in state
        assert "AAPL" in state["positions"]
        assert state["positions"]["AAPL"]["unrealized_pnl"] > 0


class TestModels:
    """Test data models"""
    
    def test_position_model(self):
        """Test Position model"""
        pos = Position(
            symbol="AAPL",
            qty=10,
            avg_cost=150.0,
            current_price=160.0
        )
        
        assert pos.market_value == 1600
        assert pos.cost_basis == 1500
        assert pos.unrealized_pnl == 100
        assert pos.unrealized_pnl_pct == pytest.approx(6.67, abs=0.1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
