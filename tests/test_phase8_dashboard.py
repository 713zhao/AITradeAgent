"""
Phase 8 Dashboard Tests

Comprehensive test suite for Streamlit UI dashboard and API integration.
Tests: 19 total covering API clients, data formatting, and integration.
"""

import pytest
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from typing import Dict, Any
import json


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_api_response():
    """Mock API response data"""
    return {
        'status': 'success',
        'data': {
            'total_value': 105000.00,
            'equity': 55000.00,
            'cash': 50000.00,
            'buying_power': 60000.00,
            'return_pct': 5.00,
            'daily_pnl': 2000.00,
            'daily_return_pct': 1.50,
            'positions_count': 3,
            'orders_count': 2,
            'alerts_count': 1
        }
    }


@pytest.fixture
def sample_positions_data():
    """Sample positions data"""
    return [
        {
            'symbol': 'AAPL',
            'quantity': 100,
            'avg_cost': 150.00,
            'current_price': 160.00,
            'market_value': 16000.00,
            'unrealized_pnl': 1000.00,
            'unrealized_pnl_pct': 6.67,
            'weight': 0.30,
            'sector': 'TECHNOLOGY',
            'broker': 'IBKR'
        },
        {
            'symbol': 'MSFT',
            'quantity': 50,
            'avg_cost': 300.00,
            'current_price': 310.00,
            'market_value': 15500.00,
            'unrealized_pnl': 500.00,
            'unrealized_pnl_pct': 3.33,
            'weight': 0.29,
            'sector': 'TECHNOLOGY',
            'broker': 'ALPACA'
        },
        {
            'symbol': 'GLD',
            'quantity': 200,
            'avg_cost': 175.00,
            'current_price': 180.00,
            'market_value': 36000.00,
            'unrealized_pnl': 1000.00,
            'unrealized_pnl_pct': 2.86,
            'weight': 0.41,
            'sector': 'COMMODITIES',
            'broker': 'KRAKEN'
        }
    ]


@pytest.fixture
def sample_trades_data():
    """Sample trades data"""
    return [
        {
            'trade_id': 'TR001',
            'symbol': 'AAPL',
            'side': 'BUY',
            'quantity': 100,
            'entry_price': 150.00,
            'exit_price': 160.00,
            'pnl': 1000.00,
            'pnl_pct': 6.67,
            'duration_seconds': 3600,
            'timestamp': '2026-03-04T10:00:00Z',
            'status': 'CLOSED'
        },
        {
            'trade_id': 'TR002',
            'symbol': 'MSFT',
            'side': 'SELL',
            'quantity': 50,
            'entry_price': 310.00,
            'exit_price': 305.00,
            'pnl': 250.00,
            'pnl_pct': 1.61,
            'duration_seconds': 7200,
            'timestamp': '2026-03-04T12:00:00Z',
            'status': 'CLOSED'
        },
        {
            'trade_id': 'TR003',
            'symbol': 'GLD',
            'side': 'BUY',
            'quantity': 200,
            'entry_price': 175.00,
            'exit_price': 170.00,
            'pnl': -1000.00,
            'pnl_pct': -2.86,
            'duration_seconds': 1800,
            'timestamp': '2026-03-04T14:00:00Z',
            'status': 'CLOSED'
        }
    ]


@pytest.fixture
def sample_performance_metrics():
    """Sample performance metrics"""
    return {
        'sharpe_ratio': 1.45,
        'sortino_ratio': 1.78,
        'calmar_ratio': 2.10,
        'max_drawdown_pct': 5.25,
        'current_drawdown_pct': 1.80,
        'var_95_pct': 2.50,
        'volatility_pct': 12.30,
        'beta': 0.85,
        'win_rate_pct': 62.5,
        'profit_factor': 2.15,
        'total_trades': 24,
        'winning_trades': 15,
        'losing_trades': 9,
        'avg_win': 250.00,
        'avg_loss': -150.00,
        'expectancy': 95.00
    }


@pytest.fixture
def sample_system_status():
    """Sample system status"""
    return {
        'is_running': True,
        'is_paused': False,
        'uptime_seconds': 86400,
        'orders_today': 12,
        'error_count': 0,
        'avg_fill_time_ms': 150.5,
        'api_latency_ms': 45.2,
        'memory_mb': 256.5,
        'cpu_percent': 12.3,
        'brokers': {
            'IBKR': {
                'connected': True,
                'cash': 50000.00,
                'positions': 10,
                'last_update': '2026-03-04T15:30:00Z'
            },
            'ALPACA': {
                'connected': True,
                'cash': 30000.00,
                'positions': 5,
                'last_update': '2026-03-04T15:29:55Z'
            }
        }
    }


# ============================================================================
# TEST CLASSES
# ============================================================================

class TestDashboardAPIClient:
    """Test DashboardAPI client methods"""
    
    def test_get_overview_success(self, mock_api_response):
        """Test successful get_overview API call"""
        from finance_service.ui.dashboard import DashboardAPI
        
        with patch('requests.get') as mock_get:
            mock_get.return_value.json.return_value = mock_api_response
            mock_get.return_value.status_code = 200
            
            api = DashboardAPI("http://localhost:5000")
            result = api.get_overview()
            
            assert result is not None
            assert result['total_value'] == 105000.00
            assert result['positions_count'] == 3
    
    def test_get_overview_api_error(self):
        """Test get_overview with API error"""
        from finance_service.ui.dashboard import DashboardAPI
        
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("Connection error")
            
            api = DashboardAPI("http://localhost:5000")
            result = api.get_overview()
            
            assert result is None
    
    def test_get_positions_success(self, sample_positions_data):
        """Test successful get_positions API call"""
        from finance_service.ui.dashboard import DashboardAPI
        
        with patch('requests.get') as mock_get:
            mock_get.return_value.json.return_value = {
                'status': 'success',
                'data': sample_positions_data
            }
            mock_get.return_value.status_code = 200
            
            api = DashboardAPI("http://localhost:5000")
            result = api.get_positions()
            
            assert isinstance(result, pd.DataFrame)
            assert len(result) == 3
            assert 'symbol' in result.columns
    
    def test_get_positions_empty(self):
        """Test get_positions with no positions"""
        from finance_service.ui.dashboard import DashboardAPI
        
        with patch('requests.get') as mock_get:
            mock_get.return_value.json.return_value = {
                'status': 'success',
                'data': []
            }
            mock_get.return_value.status_code = 200
            
            api = DashboardAPI("http://localhost:5000")
            result = api.get_positions()
            
            assert isinstance(result, pd.DataFrame)
            assert len(result) == 0
    
    def test_get_performance_metrics(self, sample_performance_metrics):
        """Test get_performance API call"""
        from finance_service.ui.dashboard import DashboardAPI
        
        with patch('requests.get') as mock_get:
            mock_get.return_value.json.return_value = {
                'status': 'success',
                'data': sample_performance_metrics
            }
            mock_get.return_value.status_code = 200
            
            api = DashboardAPI("http://localhost:5000")
            result = api.get_performance()
            
            assert result is not None
            assert result['sharpe_ratio'] == 1.45
            assert result['win_rate_pct'] == 62.5


class TestPortfolioPageAPI:
    """Test Portfolio page API client"""
    
    def test_portfolio_snapshot_retrieval(self, mock_api_response):
        """Test portfolio snapshot retrieval"""
        from finance_service.ui.pages.portfolio import PortfolioAPI
        
        with patch('requests.get') as mock_get:
            mock_get.return_value.json.return_value = mock_api_response
            mock_get.return_value.status_code = 200
            
            result = PortfolioAPI.get_portfolio_snapshot()
            
            assert result is not None
            assert result['total_value'] == 105000.00
            assert result['equity'] == 55000.00
    
    def test_portfolio_history_with_timestamp(self):
        """Test portfolio history data includes timestamp"""
        from finance_service.ui.pages.portfolio import PortfolioAPI
        
        history_data = [
            {
                'timestamp': '2026-03-04T10:00:00Z',
                'portfolio_value': 103000.00
            },
            {
                'timestamp': '2026-03-04T11:00:00Z',
                'portfolio_value': 104000.00
            }
        ]
        
        with patch('requests.get') as mock_get:
            mock_get.return_value.json.return_value = {
                'status': 'success',
                'data': history_data
            }
            mock_get.return_value.status_code = 200
            
            result = PortfolioAPI.get_portfolio_history()
            
            assert isinstance(result, pd.DataFrame)
            assert 'timestamp' in result.columns
            assert len(result) == 2


class TestRiskPageAPI:
    """Test Risk dashboard page API client"""
    
    def test_risk_metrics_retrieval(self, sample_performance_metrics):
        """Test risk metrics retrieval"""
        from finance_service.ui.pages.risk import RiskAPI
        
        with patch('requests.get') as mock_get:
            mock_get.return_value.json.return_value = {
                'status': 'success',
                'data': sample_performance_metrics
            }
            mock_get.return_value.status_code = 200
            
            result = RiskAPI.get_risk_metrics()
            
            assert result is not None
            assert result['var_95_pct'] == 2.50
            assert result['volatility_pct'] == 12.30
    
    def test_alerts_retrieval(self):
        """Test alerts retrieval"""
        from finance_service.ui.pages.risk import RiskAPI
        
        alerts_data = [
            {
                'alert_type': 'DRAWDOWN_LIMIT_EXCEEDED',
                'severity': 'HIGH',
                'message': 'Portfolio drawdown exceeded 5%'
            }
        ]
        
        with patch('requests.get') as mock_get:
            mock_get.return_value.json.return_value = {
                'status': 'success',
                'data': alerts_data
            }
            mock_get.return_value.status_code = 200
            
            result = RiskAPI.get_alerts()
            
            assert isinstance(result, pd.DataFrame)
            assert len(result) == 1
            assert result.iloc[0]['alert_type'] == 'DRAWDOWN_LIMIT_EXCEEDED'


class TestPerformancePageAPI:
    """Test Performance page API client"""
    
    def test_performance_metrics_calculation(self, sample_trades_data):
        """Test performance metrics from trades"""
        from finance_service.ui.pages.performance import PerformanceAPI
        
        with patch('requests.get') as mock_get:
            mock_get.return_value.json.return_value = {
                'status': 'success',
                'data': sample_trades_data
            }
            mock_get.return_value.status_code = 200
            
            result = PerformanceAPI.get_trades()
            
            assert isinstance(result, pd.DataFrame)
            assert len(result) == 3
            assert 'pnl' in result.columns
    
    def test_win_rate_calculation(self):
        """Test win rate calculation from trades"""
        trades_data = [
            {'pnl': 100, 'pnl_pct': 5.0},  # Win
            {'pnl': -50, 'pnl_pct': -2.5},  # Loss
            {'pnl': 200, 'pnl_pct': 10.0},  # Win
        ]
        
        df = pd.DataFrame(trades_data)
        wins = (df['pnl'] > 0).sum()
        win_rate = (wins / len(df)) * 100
        
        assert win_rate == 66.67


class TestTradesPageAPI:
    """Test Trade History page API client"""
    
    def test_trades_list_with_filters(self, sample_trades_data):
        """Test trades list retrieval with filters"""
        from finance_service.ui.pages.trades import TradesAPI
        
        with patch('requests.get') as mock_get:
            mock_get.return_value.json.return_value = {
                'status': 'success',
                'data': sample_trades_data
            }
            mock_get.return_value.status_code = 200
            
            result = TradesAPI.get_trades(limit=100)
            
            assert isinstance(result, pd.DataFrame)
            assert len(result) == 3
    
    def test_trades_filtering_by_symbol(self, sample_trades_data):
        """Test trades filtering by symbol"""
        df = pd.DataFrame(sample_trades_data)
        filtered = df[df['symbol'] == 'AAPL']
        
        assert len(filtered) == 1
        assert filtered.iloc[0]['symbol'] == 'AAPL'
    
    def test_trades_filtering_by_pnl(self, sample_trades_data):
        """Test trades filtering by minimum P&L"""
        df = pd.DataFrame(sample_trades_data)
        filtered = df[df['pnl'] >= 500]
        
        assert len(filtered) == 1
        assert all(filtered['pnl'] >= 500)


class TestBacktestPageAPI:
    """Test Backtest Reports page API client"""
    
    def test_backtest_list_retrieval(self):
        """Test backtest list retrieval"""
        from finance_service.ui.pages.backtest import BacktestAPI
        
        backtests = BacktestAPI.get_backtest_list()
        
        assert isinstance(backtests, pd.DataFrame)
        assert len(backtests) >= 1
        assert 'backtest_id' in backtests.columns
        assert 'total_return' in backtests.columns
    
    def test_backtest_details_retrieval(self):
        """Test backtest details retrieval"""
        from finance_service.ui.pages.backtest import BacktestAPI
        
        details = BacktestAPI.get_backtest_details('BT001')
        
        assert details is not None
        assert 'sharpe_ratio' in details
        assert 'total_return' in details
        assert 'max_drawdown' in details


class TestSystemControlPageAPI:
    """Test System Control page API client"""
    
    def test_system_status_retrieval(self, sample_system_status):
        """Test system status retrieval"""
        from finance_service.ui.pages.system_control import SystemAPI
        
        with patch('requests.get') as mock_get:
            mock_get.return_value.json.return_value = {
                'status': 'success',
                'data': sample_system_status
            }
            mock_get.return_value.status_code = 200
            
            result = SystemAPI.get_system_status()
            
            assert result is not None
            assert result['is_running'] is True
            assert result['is_paused'] is False
    
    def test_pause_trading_success(self):
        """Test pause trading API call"""
        from finance_service.ui.pages.system_control import SystemAPI
        
        with patch('requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            
            result = SystemAPI.pause_trading()
            
            assert result is True
    
    def test_resume_trading_success(self):
        """Test resume trading API call"""
        from finance_service.ui.pages.system_control import SystemAPI
        
        with patch('requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            
            result = SystemAPI.resume_trading()
            
            assert result is True
    
    def test_reload_config_success(self):
        """Test reload config API call"""
        from finance_service.ui.pages.system_control import SystemAPI
        
        with patch('requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            
            result = SystemAPI.reload_config()
            
            assert result is True
    
    def test_send_test_alert_success(self):
        """Test test alert API call"""
        from finance_service.ui.pages.system_control import SystemAPI
        
        with patch('requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            
            result = SystemAPI.send_test_alert()
            
            assert result is True


class TestDataFormatting:
    """Test data formatting and preparation"""
    
    def test_currency_formatting(self):
        """Test currency formatting"""
        value = 1234.56
        formatted = f"${value:,.2f}"
        
        assert formatted == "$1,234.56"
    
    def test_percentage_formatting(self):
        """Test percentage formatting"""
        value = 0.0667
        formatted = f"{value:.2%}"
        
        assert formatted == "6.67%"
    
    def test_date_formatting(self):
        """Test date/time formatting"""
        timestamp = '2026-03-04T15:30:00Z'
        dt = pd.to_datetime(timestamp)
        formatted = dt.strftime('%H:%M:%S')
        
        assert '15:30:00' in formatted
    
    def test_dataframe_column_formatting(self, sample_positions_data):
        """Test DataFrame column formatting"""
        df = pd.DataFrame(sample_positions_data)
        
        # Format price columns
        df['current_price'] = df['current_price'].apply(lambda x: f"${x:,.2f}")
        df['unrealized_pnl_pct'] = df['unrealized_pnl_pct'].apply(lambda x: f"{x:.2f}%")
        
        assert df.iloc[0]['current_price'] == "$160.00"
        assert df.iloc[0]['unrealized_pnl_pct'] == "6.67%"


class TestChartDataGeneration:
    """Test chart data generation and preparation"""
    
    def test_equity_curve_data_preparation(self):
        """Test equity curve data preparation"""
        history = [
            {'timestamp': '2026-03-01T10:00:00Z', 'portfolio_value': 100000.00},
            {'timestamp': '2026-03-02T10:00:00Z', 'portfolio_value': 102000.00},
            {'timestamp': '2026-03-03T10:00:00Z', 'portfolio_value': 101500.00},
            {'timestamp': '2026-03-04T10:00:00Z', 'portfolio_value': 105000.00},
        ]
        
        df = pd.DataFrame(history)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        assert len(df) == 4
        assert df['portfolio_value'].max() == 105000.00
        assert df['portfolio_value'].min() == 100000.00
    
    def test_allocation_data_preparation(self, sample_positions_data):
        """Test position allocation data for pie chart"""
        df = pd.DataFrame(sample_positions_data)
        alloc = df[['symbol', 'market_value']]
        
        assert len(alloc) == 3
        assert alloc['market_value'].sum() == 67500.00
    
    def test_sector_grouping(self, sample_positions_data):
        """Test sector grouping for analysis"""
        df = pd.DataFrame(sample_positions_data)
        sector_exposure = df.groupby('sector')['market_value'].sum()
        
        assert 'TECHNOLOGY' in sector_exposure.index
        assert 'COMMODITIES' in sector_exposure.index


class TestIntegrationScenarios:
    """Integration tests for complete workflows"""
    
    def test_dashboard_full_load_workflow(self, mock_api_response, sample_positions_data, sample_performance_metrics):
        """Test full dashboard load workflow"""
        from finance_service.ui.dashboard import DashboardAPI
        
        with patch('requests.get') as mock_get:
            # Mock multiple API calls
            def side_effect(*args, **kwargs):
                response = Mock()
                if 'overview' in args[0]:
                    response.json.return_value = mock_api_response
                elif 'positions' in args[0]:
                    response.json.return_value = {'status': 'success', 'data': sample_positions_data}
                elif 'performance' in args[0]:
                    response.json.return_value = {'status': 'success', 'data': sample_performance_metrics}
                response.status_code = 200
                return response
            
            mock_get.side_effect = side_effect
            
            api = DashboardAPI("http://localhost:5000")
            overview = api.get_overview()
            positions = api.get_positions()
            perf = api.get_performance()
            
            assert overview is not None
            assert isinstance(positions, pd.DataFrame)
            assert perf is not None
    
    def test_portfolio_analysis_workflow(self, sample_positions_data):
        """Test portfolio analysis workflow"""
        df = pd.DataFrame(sample_positions_data)
        
        total_value = df['market_value'].sum()
        df['weight'] = (df['market_value'] / total_value) * 100
        
        assert df['weight'].sum() > 99  # Allow for rounding
        assert all(df['weight'] > 0)


# ============================================================================
# EXECUTION
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
