"""Basic sanity tests for backtesting engine."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from finance_service.backtesting import BacktestEngine, RuleStrategyBacktest, load_data
from finance_service.backtesting.metrics import calculate_metrics


class TestBacktestEngine:
    """Test core backtesting engine"""

    def test_simple_buy_and_hold(self):
        """Test single-symbol buy-and-hold scenario"""
        # Create synthetic data
        dates = pd.date_range("2023-01-01", periods=100, freq="D")
        prices = np.linspace(100, 110, 100) + np.random.randn(100) * 0.5
        data = pd.DataFrame({
            'open': prices * 0.99,
            'high': prices * 1.02,
            'low': prices * 0.98,
            'close': prices,
            'volume': np.random.randint(100000, 1000000, 100),
        }, index=dates)

        # Buy and hold strategy (simple: all bars signal=1)
        class BuyHold:
            def generate_signals(self, data):
                df = pd.DataFrame({
                    'signal': 1,
                    'confidence': 1.0,
                    'stop_loss': None,
                    'take_profit': None,
                }, index=data.index)
                return df

        engine = BacktestEngine(initial_capital=10000, commission=0.0, slippage=0.0)
        results = engine.run(data, BuyHold())

        assert results.final_capital > 9000  # at least not huge loss (no slippage)
        assert len(results.trades) == 1  # one open and one close at end
        assert results.metrics['total_trades'] == 1

    def test_short_trading_disabled(self):
        """Test that short signals are ignored if short selling disabled"""
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        prices = np.linspace(100, 90, 10)
        data = pd.DataFrame({
            'close': prices,
            'open': prices,
            'high': prices,
            'low': prices,
            'volume': 1,
        }, index=dates)

        class ShortOnly:
            def generate_signals(self, data):
                return pd.DataFrame({
                    'signal': -1,  # always sell short
                    'confidence': 1.0,
                    'stop_loss': None,
                    'take_profit': None,
                }, index=data.index)

        engine = BacktestEngine(initial_capital=10000, allow_short_selling=False)
        results = engine.run(data, ShortOnly())

        # Should have no trades because shorts are filtered
        assert len(results.trades) == 0

    def test_position_sizing_limit(self):
        """Test max position size limit"""
        dates = pd.date_range("2023-01-01", periods=5, freq="D")
        prices = np.array([10.0, 10.1, 10.2, 10.3, 10.4])
        data = pd.DataFrame({
            'close': prices,
            'open': prices,
            'high': prices,
            'low': prices,
            'volume': 1,
        }, index=dates)

        class AlwaysBuy:
            def generate_signals(self, data):
                return pd.DataFrame({
                    'signal': 1,
                    'confidence': 1.0,
                    'stop_loss': 9.0,
                    'take_profit': 11.0,
                }, index=data.index)

        # Very small max position (1%) should limit shares
        engine = BacktestEngine(initial_capital=10000, max_position_size_pct=0.01)
        results = engine.run(data, AlwaysBuy())

        # Should have 1 trade (buy on first bar, hold til end)
        assert len(results.trades) == 1
        trade = results.trades[0]
        expected_max = (10000 * 0.01) / prices[0]  # ~10 shares
        assert trade.quantity <= expected_max + 1  # allow rounding

    def test_stop_loss_execution(self):
        """Test that stop-loss exits trigger correctly"""
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        prices = np.array([100, 101, 102, 103, 104, 103, 102, 101, 100, 99])
        data = pd.DataFrame({
            'close': prices,
            'open': prices * 0.99,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'volume': 1,
        }, index=dates)

        class BuyOnce:
            def __init__(self):
                self.first = True
            def generate_signals(self, data):
                if self.first and len(data) > 1:
                    self.first = False
                    return pd.DataFrame({
                        'signal': 1,
                        'confidence': 1.0,
                        'stop_loss': 101.0,  # stop below day 2 close
                        'take_profit': None,
                    }, index=data.index)
                else:
                    return pd.DataFrame({
                        'signal': 0,
                        'confidence': 0.0,
                        'stop_loss': None,
                        'take_profit': None,
                    }, index=data.index)

        engine = BacktestEngine()
        results = engine.run(data, BuyOnce())
        # Should exit at bar where price <= stop_loss
        assert len(results.trades) == 1
        trade = results.trades[0]
        assert trade.exit_reason == 'stop_loss'
        assert trade.exit_price <= 101.0


class TestMetrics:
    """Test performance metrics calculations"""

    def test_sharpe_calculation(self):
        """Simple Sharpe ratio test"""
        equity = pd.Series([10000, 10100, 10200, 10150, 10250])
        trades = pd.DataFrame({'pnl': [100, 50, -25]})
        metrics = calculate_metrics(equity, trades)
        assert 'sharpe_ratio' in metrics
        assert metrics['total_trades'] == len(trades)

    def test_drawdown_duration(self):
        """Test max drawdown duration"""
        equity = pd.Series([100, 90, 80, 90, 100])
        returns = equity.pct_change().dropna()
        # Use engine internal method
        from finance_service.backtesting.engine import BacktestEngine
        dd = (equity - equity.expanding().max()) / equity.expanding().max()
        duration = BacktestEngine._max_drawdown_duration(dd)
        assert duration >= 1  # at least 1 period underwater
