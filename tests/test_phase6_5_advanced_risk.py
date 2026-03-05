"""
Phase 6.5: Advanced Risk Management Testing

Comprehensive testing for real-time portfolio risk monitoring, dynamic position sizing,
advanced stop-loss mechanisms, cross-broker risk analysis, and compliance monitoring.

Test Coverage:
- Real-time VaR and drawdown calculations
- Dynamic position sizing algorithms
- Advanced stop-loss mechanisms
- Cross-broker correlation analysis
- Regulatory compliance checking
- Risk alerts and notifications
"""

import pytest
import asyncio
import numpy as np
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any
import time

# Import or mock the risk management components
from finance_service.risk.real_time_risk_monitor import RealTimeRiskMonitor
from finance_service.risk.dynamic_position_sizer import DynamicPositionSizer
from finance_service.risk.advanced_stop_loss_manager import AdvancedStopLossManager
from finance_service.risk.cross_broker_risk_analyzer import CrossBrokerRiskAnalyzer
from finance_service.risk.compliance_monitor import ComplianceMonitor


@dataclass
class TestPortfolioData:
    """Test portfolio data for risk testing"""
    symbol: str
    position_size: int
    entry_price: float
    current_price: float
    broker: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def unrealized_pnl(self) -> float:
        return (self.current_price - self.entry_price) * self.position_size
    
    @property
    def unrealized_pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return ((self.current_price - self.entry_price) / self.entry_price) * 100


@dataclass
class TestMarketData:
    """Test market data for risk calculations"""
    symbol: str
    price: float
    bid: float
    ask: float
    volume: int
    volatility: float
    correlation: Dict[str, float] = field(default_factory=dict)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def event_manager():
    """Mock event manager"""
    return Mock()


@pytest.fixture
def risk_config():
    """Risk management configuration"""
    return {
        'real_time': {
            'enabled': True,
            'update_frequency': 100,  # ms
            'var_confidence_levels': [0.95, 0.99],
            'max_portfolio_var': 0.05,
        },
        'position_sizing': {
            'method': 'KELLY',
            'max_position_size': 0.10,
            'volatility_lookback': 20,
            'correlation_lookback': 60,
        },
        'stop_loss': {
            'trailing_stop_enabled': True,
            'volatility_stop_enabled': True,
            'time_based_exit_enabled': True,
            'max_holding_period': 30,
        },
        'compliance': {
            'max_leverage': 2.0,
            'position_limits': {
                'AAPL': 1000,
                'TSLA': 500,
            },
            'sector_limits': {
                'TECHNOLOGY': 0.30,
                'ENERGY': 0.20,
            }
        }
    }


@pytest.fixture
def real_time_risk_monitor(risk_config, event_manager):
    """Real-time risk monitor instance"""
    return RealTimeRiskMonitor(risk_config, event_manager)


@pytest.fixture
def dynamic_position_sizer(risk_config, event_manager):
    """Dynamic position sizer instance"""
    return DynamicPositionSizer(risk_config, event_manager)


@pytest.fixture
def advanced_stop_loss_manager(risk_config, event_manager):
    """Advanced stop loss manager instance"""
    return AdvancedStopLossManager(risk_config, event_manager)


@pytest.fixture
def cross_broker_risk_analyzer(risk_config, event_manager):
    """Cross-broker risk analyzer instance"""
    return CrossBrokerRiskAnalyzer(risk_config, event_manager)


@pytest.fixture
def compliance_monitor(risk_config, event_manager):
    """Compliance monitor instance"""
    return ComplianceMonitor(risk_config, event_manager)


# ============================================================================
# TestRealTimeRiskMonitor
# ============================================================================

class TestRealTimeRiskMonitor:
    """Test real-time portfolio risk monitoring"""
    
    def test_monitor_initialization(self, real_time_risk_monitor):
        """Test risk monitor initialization"""
        assert real_time_risk_monitor is not None
        assert real_time_risk_monitor.config is not None
        assert real_time_risk_monitor.event_manager is not None
        assert hasattr(real_time_risk_monitor, 'portfolio')
        assert hasattr(real_time_risk_monitor, 'risk_metrics')
    
    def test_add_position_to_portfolio(self, real_time_risk_monitor):
        """Test adding positions to portfolio"""
        position = TestPortfolioData(
            symbol='AAPL',
            position_size=100,
            entry_price=150.00,
            current_price=150.50,
            broker='IBKR'
        )
        
        real_time_risk_monitor.add_position(position)
        assert real_time_risk_monitor.get_position('AAPL') is not None
        assert real_time_risk_monitor.get_position('AAPL')['size'] == 100
    
    def test_calculate_var(self, real_time_risk_monitor):
        """Test Value at Risk calculation"""
        # Add test portfolio
        positions = [
            TestPortfolioData('AAPL', 100, 150.00, 150.50, 'IBKR'),
            TestPortfolioData('TSLA', 50, 250.00, 255.00, 'TDA'),
        ]
        for pos in positions:
            real_time_risk_monitor.add_position(pos)
        
        # Calculate VaR
        var_metrics = real_time_risk_monitor.calculate_var()
        assert var_metrics is not None
        assert 'var_95' in var_metrics
        assert 'var_99' in var_metrics
        assert var_metrics['var_95'] >= 0
        assert var_metrics['var_99'] >= 0
    
    def test_calculate_drawdown(self, real_time_risk_monitor):
        """Test portfolio drawdown calculation"""
        # Add positions
        position = TestPortfolioData(
            symbol='AAPL',
            position_size=100,
            entry_price=150.00,
            current_price=148.50,  # 1% loss
            broker='IBKR'
        )
        real_time_risk_monitor.add_position(position)
        
        # Calculate drawdown
        portfolio_value = real_time_risk_monitor.get_portfolio_value()
        unrealized_loss = real_time_risk_monitor.get_unrealized_pnl()
        
        assert portfolio_value > 0
        assert unrealized_loss < 0  # Should show loss
    
    def test_portfolio_exposure_monitoring(self, real_time_risk_monitor):
        """Test portfolio exposure tracking"""
        positions = [
            TestPortfolioData('AAPL', 100, 150.00, 150.50, 'IBKR'),
            TestPortfolioData('TSLA', 50, 250.00, 255.00, 'TDA'),
            TestPortfolioData('MSFT', 75, 300.00, 302.00, 'IBKR'),
        ]
        for pos in positions:
            real_time_risk_monitor.add_position(pos)
        
        # Check positions
        total_exposure = real_time_risk_monitor.get_total_exposure()
        assert total_exposure > 0
        
        # Check by broker
        exposures = real_time_risk_monitor.get_exposure_by_broker()
        assert 'IBKR' in exposures
        assert 'TDA' in exposures


# ============================================================================
# TestDynamicPositionSizer
# ============================================================================

class TestDynamicPositionSizer:
    """Test dynamic position sizing algorithms"""
    
    def test_sizer_initialization(self, dynamic_position_sizer):
        """Test position sizer initialization"""
        assert dynamic_position_sizer is not None
        assert dynamic_position_sizer.config is not None
        assert dynamic_position_sizer.event_manager is not None
    
    def test_kelly_criterion_sizing(self, dynamic_position_sizer):
        """Test Kelly Criterion position sizing"""
        market_data = TestMarketData(
            symbol='AAPL',
            price=150.00,
            bid=149.95,
            ask=150.05,
            volume=1000000,
            volatility=0.25
        )
        
        sizing = dynamic_position_sizer.calculate_kelly_size(
            symbol='AAPL',
            win_rate=0.55,
            win_loss_ratio=1.2,
            volatility=0.25
        )
        
        assert sizing is not None
        assert 'kelly_fraction' in sizing
        assert sizing['kelly_fraction'] > 0
        assert sizing['kelly_fraction'] <= 0.25  # Kelly usually recommends < 25%
    
    def test_volatility_adjusted_sizing(self, dynamic_position_sizer):
        """Test volatility-adjusted position sizing"""
        sizing = dynamic_position_sizer.calculate_volatility_adjusted_size(
            symbol='AAPL',
            portfolio_value=100000,
            target_risk_pct=0.02,  # 2% risk per trade
            volatility=0.25
        )
        
        assert sizing is not None
        assert sizing['position_size'] > 0
    
    def test_risk_parity_allocation(self, dynamic_position_sizer):
        """Test risk parity position allocation"""
        symbols = ['AAPL', 'TSLA', 'MSFT']
        volatilities = {'AAPL': 0.20, 'TSLA': 0.35, 'MSFT': 0.22}
        portfolio_value = 100000
        
        allocations = dynamic_position_sizer.calculate_risk_parity_allocation(
            symbols=symbols,
            volatilities=volatilities,
            portfolio_value=portfolio_value,
            target_risk=0.02
        )
        
        assert allocations is not None
        assert len(allocations) == 3
        for symbol in symbols:
            assert symbol in allocations
            assert allocations[symbol] > 0
    
    def test_correlation_adjusted_sizing(self, dynamic_position_sizer):
        """Test correlation-adjusted position sizing"""
        correlation_matrix = np.array([
            [1.0, 0.3, 0.4],
            [0.3, 1.0, 0.2],
            [0.4, 0.2, 1.0]
        ])
        
        sizing = dynamic_position_sizer.calculate_correlation_adjusted_size(
            symbol='AAPL',
            portfolio_symbols=['AAPL', 'TSLA', 'MSFT'],
            correlation_matrix=correlation_matrix,
            portfolio_value=100000
        )
        
        assert sizing is not None
        assert sizing['position_size'] > 0


# ============================================================================
# TestAdvancedStopLossManager
# ============================================================================

class TestAdvancedStopLossManager:
    """Test advanced stop-loss mechanisms"""
    
    def test_stop_loss_manager_initialization(self, advanced_stop_loss_manager):
        """Test stop loss manager initialization"""
        assert advanced_stop_loss_manager is not None
        assert advanced_stop_loss_manager.config is not None
        assert advanced_stop_loss_manager.event_manager is not None
    
    def test_trailing_stop_creation(self, advanced_stop_loss_manager):
        """Test trailing stop order creation"""
        stop = advanced_stop_loss_manager.create_trailing_stop(
            symbol='AAPL',
            entry_price=150.00,
            trailing_amount=5.00
        )
        
        assert stop is not None
        assert stop['symbol'] == 'AAPL'
        assert stop['stop_type'] == 'TRAILING'
        assert stop['trailing_amount'] == 5.00
    
    def test_volatility_based_stop(self, advanced_stop_loss_manager):
        """Test volatility-based stop loss"""
        stop = advanced_stop_loss_manager.create_volatility_stop(
            symbol='AAPL',
            entry_price=150.00,
            volatility=0.25,
            stops_atr=2.0
        )
        
        assert stop is not None
        assert stop['symbol'] == 'AAPL'
        assert stop['stop_type'] == 'VOLATILITY'
        assert 'stop_price' in stop
        assert stop['stop_price'] < 150.00
    
    def test_time_based_exit(self, advanced_stop_loss_manager):
        """Test time-based exit creation"""
        entry_time = datetime.now(timezone.utc)
        exit_config = advanced_stop_loss_manager.create_time_based_exit(
            symbol='AAPL',
            entry_time=entry_time,
            max_holding_hours=24
        )
        
        assert exit_config is not None
        assert exit_config['symbol'] == 'AAPL'
        assert exit_config['exit_type'] == 'TIME_BASED'
        assert exit_config['max_holding_hours'] == 24
    
    def test_update_trailing_stop(self, advanced_stop_loss_manager):
        """Test updating trailing stop as price moves"""
        # Create a stop directly as a StopLossOrder object
        from finance_service.risk.advanced_stop_loss_manager import StopLossOrder
        stop = StopLossOrder(
            symbol='AAPL',
            stop_type='TRAILING',
            entry_price=150.00,
            stop_price=145.00,
            current_price=150.00,
            trailing_amount=5.00,
        )
        
        # Price moves up to 155
        updated_stop = advanced_stop_loss_manager.update_trailing_stop(
            stop=stop,
            current_price=155.00
        )
        
        assert updated_stop['stop_price'] == 150.00  # 155 - 5
    
    def test_multi_timeframe_stop_coordination(self, advanced_stop_loss_manager):
        """Test coordination of stops across timeframes"""
        stops = advanced_stop_loss_manager.create_multi_timeframe_stops(
            symbol='AAPL',
            entry_price=150.00,
            timeframes=['1H', '4H', '1D'],
            stop_loss_pcts=[0.02, 0.03, 0.05]
        )
        
        assert len(stops) == 3
        for stop in stops:
            assert stop['symbol'] == 'AAPL'
            assert 'stop_price' in stop


# ============================================================================
# TestCrossBrokerRiskAnalyzer
# ============================================================================

class TestCrossBrokerRiskAnalyzer:
    """Test cross-broker risk analysis"""
    
    def test_analyzer_initialization(self, cross_broker_risk_analyzer):
        """Test cross-broker analyzer initialization"""
        assert cross_broker_risk_analyzer is not None
        assert cross_broker_risk_analyzer.config is not None
        assert cross_broker_risk_analyzer.event_manager is not None
    
    def test_correlation_matrix_calculation(self, cross_broker_risk_analyzer):
        """Test correlation matrix calculation across brokers"""
        price_data = {
            'AAPL': [150.0, 150.5, 151.0, 150.8, 151.2],
            'TSLA': [250.0, 251.0, 249.5, 250.5, 252.0],
            'MSFT': [300.0, 301.0, 302.0, 301.5, 303.0],
        }
        
        correlation = cross_broker_risk_analyzer.calculate_correlation_matrix(
            symbols=list(price_data.keys()),
            price_data=price_data
        )
        
        assert correlation is not None
        assert correlation.shape == (3, 3)
        assert np.allclose(np.diag(correlation), 1.0)  # Diagonal should be 1.0
    
    def test_concentration_risk_assessment(self, cross_broker_risk_analyzer):
        """Test portfolio concentration risk"""
        positions = {
            'AAPL': {'size': 100, 'value': 15000, 'broker': 'IBKR'},
            'TSLA': {'size': 50, 'value': 12500, 'broker': 'TDA'},
            'MSFT': {'size': 75, 'value': 22500, 'broker': 'IBKR'},
        }
        
        concentration = cross_broker_risk_analyzer.assess_concentration_risk(
            positions=positions,
            portfolio_value=50000
        )
        
        assert concentration is not None
        assert 'herfindahl_index' in concentration
        assert 'max_position_pct' in concentration
    
    def test_cross_broker_exposure_limits(self, cross_broker_risk_analyzer):
        """Test cross-broker exposure limit checking"""
        exposures = {
            'IBKR': 35000,
            'TDA': 12500,
            'BINANCE': 5000,
        }
        
        limit_check = cross_broker_risk_analyzer.check_exposure_limits(
            exposures=exposures,
            portfolio_value=50000,
            max_broker_exposure_pct=0.70
        )
        
        assert limit_check is not None
        assert 'within_limits' in limit_check
    
    def test_diversification_scoring(self, cross_broker_risk_analyzer):
        """Test portfolio diversification scoring"""
        positions = {
            'AAPL': {'value': 10000, 'sector': 'TECHNOLOGY', 'broker': 'IBKR'},
            'TSLA': {'value': 10000, 'sector': 'TECHNOLOGY', 'broker': 'TDA'},
            'XOM': {'value': 10000, 'sector': 'ENERGY', 'broker': 'IBKR'},
            'JPM': {'value': 10000, 'sector': 'FINANCE', 'broker': 'TDA'},
            'BAC': {'value': 10000, 'sector': 'FINANCE', 'broker': 'IBKR'},
        }
        
        diversification = cross_broker_risk_analyzer.calculate_diversification_score(
            positions=positions,
            portfolio_value=50000
        )
        
        assert diversification is not None
        assert 'score' in diversification
        assert 0 <= diversification['score'] <= 1.0


# ============================================================================
# TestComplianceMonitor
# ============================================================================

class TestComplianceMonitor:
    """Test regulatory compliance monitoring"""
    
    def test_compliance_monitor_initialization(self, compliance_monitor):
        """Test compliance monitor initialization"""
        assert compliance_monitor is not None
        assert compliance_monitor.config is not None
        assert compliance_monitor.event_manager is not None
    
    def test_position_limit_checking(self, compliance_monitor):
        """Test position limit compliance"""
        position = {'symbol': 'AAPL', 'size': 800}
        
        compliance = compliance_monitor.check_position_limit(
            position=position,
            position_limits={'AAPL': 1000, 'TSLA': 500}
        )
        
        assert compliance is not None
        assert compliance['compliant'] == True
        assert compliance['symbol'] == 'AAPL'
    
    def test_position_limit_breach(self, compliance_monitor):
        """Test position limit breach detection"""
        position = {'symbol': 'TSLA', 'size': 600}
        
        compliance = compliance_monitor.check_position_limit(
            position=position,
            position_limits={'AAPL': 1000, 'TSLA': 500}
        )
        
        assert compliance['compliant'] == False
        assert compliance['violation'] == 'POSITION_LIMIT_EXCEEDED'
    
    def test_leverage_limit_checking(self, compliance_monitor):
        """Test leverage limit compliance"""
        leverage = compliance_monitor.check_leverage(
            total_exposure=150000,
            account_value=100000,
            max_leverage=2.0
        )
        
        assert leverage is not None
        assert 'current_leverage' in leverage
        assert leverage['current_leverage'] == 1.5
        assert leverage['compliant'] == True
    
    def test_leverage_breach(self, compliance_monitor):
        """Test leverage limit breach"""
        leverage = compliance_monitor.check_leverage(
            total_exposure=250000,
            account_value=100000,
            max_leverage=2.0
        )
        
        assert leverage['current_leverage'] == 2.5
        assert leverage['compliant'] == False
    
    def test_sector_limit_checking(self, compliance_monitor):
        """Test sector concentration limit"""
        positions = {
            'AAPL': {'value': 10000, 'sector': 'TECHNOLOGY'},
            'MSFT': {'value': 10000, 'sector': 'TECHNOLOGY'},
            'TSLA': {'value': 5000, 'sector': 'TECHNOLOGY'},
        }
        
        sector_check = compliance_monitor.check_sector_limits(
            positions=positions,
            portfolio_value=50000,
            sector_limits={'TECHNOLOGY': 0.50}  # 50% max
        )
        
        assert sector_check is not None
        assert 'TECHNOLOGY' in sector_check
        assert abs(sector_check['TECHNOLOGY']['pct'] - 50.0) < 0.1  # Check percentage
        assert sector_check['TECHNOLOGY']['compliant'] == True
    
    def test_audit_trail_logging(self, compliance_monitor):
        """Test compliance audit trail"""
        compliance_monitor.log_compliance_event(
            event_type='POSITION_ADDED',
            symbol='AAPL',
            size=100,
            compliance_status='COMPLIANT'
        )
        
        audit_trail = compliance_monitor.get_audit_trail()
        assert len(audit_trail) > 0
        assert audit_trail[-1]['event_type'] == 'POSITION_ADDED'


# ============================================================================
# TestRiskIntegration
# ============================================================================

class TestRiskIntegration:
    """Test integration of all risk components"""
    
    def test_end_to_end_risk_workflow(self, real_time_risk_monitor, dynamic_position_sizer, 
                                      compliance_monitor):
        """Test complete risk management workflow"""
        # 1. Add position
        position = TestPortfolioData(
            symbol='AAPL',
            position_size=100,
            entry_price=150.00,
            current_price=150.50,
            broker='IBKR'
        )
        real_time_risk_monitor.add_position(position)
        
        # 2. Check compliance
        compliance = compliance_monitor.check_position_limit(
            position={'symbol': 'AAPL', 'size': 100},
            position_limits={'AAPL': 1000}
        )
        assert compliance['compliant'] == True
        
        # 3. Calculate position size for next trade
        sizing = dynamic_position_sizer.calculate_volatility_adjusted_size(
            symbol='TSLA',
            portfolio_value=100000,
            target_risk_pct=0.02,
            volatility=0.30
        )
        assert sizing['position_size'] > 0
        
        # 4. Check risk metrics
        var_metrics = real_time_risk_monitor.calculate_var()
        assert var_metrics is not None
    
    def test_risk_alert_generation(self, real_time_risk_monitor):
        """Test risk alert generation on threshold breach"""
        # Add losing position
        position = TestPortfolioData(
            symbol='AAPL',
            position_size=100,
            entry_price=150.00,
            current_price=140.00,  # 10% loss
            broker='IBKR'
        )
        
        # Set peak value first (simulating previous high of entry price)
        real_time_risk_monitor.peak_portfolio_value = position.position_size * position.entry_price
        
        # Now add position with lower current price
        real_time_risk_monitor.add_position(position)
        
        # Check for drawdown alerts (10% loss > 5% threshold)
        alerts = real_time_risk_monitor.check_risk_thresholds(
            max_portfolio_drawdown_pct=0.05  # 5% max
        )
        
        assert len(alerts) > 0
        assert 'DRAWDOWN_LIMIT_EXCEEDED' in [a['alert_type'] for a in alerts]
    
    def test_multi_broker_risk_aggregation(self, real_time_risk_monitor, 
                                          cross_broker_risk_analyzer):
        """Test risk aggregation across multiple brokers"""
        # Add positions from different brokers
        positions = [
            TestPortfolioData('AAPL', 100, 150.00, 150.50, 'IBKR'),
            TestPortfolioData('TSLA', 50, 250.00, 255.00, 'TDA'),
            TestPortfolioData('MSFT', 75, 300.00, 305.00, 'BINANCE'),
        ]
        
        for pos in positions:
            real_time_risk_monitor.add_position(pos)
        
        # Aggregate risk by broker
        broker_exposures = real_time_risk_monitor.get_exposure_by_broker()
        assert len(broker_exposures) >= 1  # At least one broker should have exposure
        
        # Calculate diversification
        total_value = sum(p.position_size * p.current_price for p in positions)
        diversification = cross_broker_risk_analyzer.calculate_diversification_score(
            positions={p.symbol: {
                'value': p.position_size * p.current_price,
                'broker': p.broker
            } for p in positions},
            portfolio_value=total_value if total_value > 0 else 1
        )
        assert diversification is not None
        assert 'score' in diversification


# ============================================================================
# Performance Tests
# ============================================================================

class TestRiskPerformance:
    """Test risk calculation performance"""
    
    def test_var_calculation_latency(self, real_time_risk_monitor):
        """Test VaR calculation meets latency requirement (<2ms)"""
        # Add test positions
        for i in range(50):
            position = TestPortfolioData(
                symbol=f'TEST{i}',
                position_size=100,
                entry_price=100.0,
                current_price=100.5,
                broker='IBKR'
            )
            real_time_risk_monitor.add_position(position)
        
        # Measure calculation time
        start = time.perf_counter()
        var_metrics = real_time_risk_monitor.calculate_var()
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        # Should complete in <2ms
        assert elapsed_ms < 2.0
        assert var_metrics is not None
    
    def test_correlation_calculation_performance(self, cross_broker_risk_analyzer):
        """Test correlation matrix calculation performance"""
        symbols = [f'SYM{i}' for i in range(100)]
        price_data = {sym: [100.0 + i*0.1 for i in range(60)] for sym in symbols}
        
        start = time.perf_counter()
        correlation = cross_broker_risk_analyzer.calculate_correlation_matrix(
            symbols=symbols,
            price_data=price_data
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        # Should complete in <10ms
        assert elapsed_ms < 10.0
        assert correlation is not None
    
    def test_position_sizing_throughput(self, dynamic_position_sizer):
        """Test position sizing throughput (1000+ calculations/sec)"""
        symbols = [f'SYM{i}' for i in range(100)]
        
        start = time.perf_counter()
        calculations = 0
        
        for symbol in symbols:
            for _ in range(10):  # 1000 total calculations
                sizing = dynamic_position_sizer.calculate_kelly_size(
                    symbol=symbol,
                    win_rate=0.55,
                    win_loss_ratio=1.2,
                    volatility=0.25
                )
                calculations += 1
        
        elapsed = time.perf_counter() - start
        throughput = calculations / elapsed
        
        # Should handle 1000+ per second
        assert throughput >= 1000


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
