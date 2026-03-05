"""
Real-Time Risk Monitor

Continuous portfolio risk assessment with VaR, drawdown tracking,
and exposure monitoring across all active positions.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
import numpy as np


@dataclass
class RiskMetrics:
    """Portfolio risk metrics"""
    timestamp: datetime
    portfolio_value: float
    var_95: float
    var_99: float
    expected_shortfall: float
    current_drawdown: float
    max_drawdown: float
    total_exposure: float
    number_positions: int


class RealTimeRiskMonitor:
    """
    Real-time portfolio risk monitoring system.
    
    Continuously monitors portfolio risk metrics including VaR, drawdown,
    exposure limits, and generates alerts on risk threshold breaches.
    """
    
    def __init__(self, config: Dict[str, Any], event_manager):
        self.config = config
        self.event_manager = event_manager
        self.logger = logging.getLogger(__name__)
        
        # Risk configuration
        self.risk_config = config.get('real_time', {})
        
        # Portfolio state
        self.portfolio: Dict[str, Any] = {}
        self.position_history: deque = deque(maxlen=1000)
        self.risk_metrics: Optional[RiskMetrics] = None
        
        # Risk tracking
        self.peak_portfolio_value = 0.0
        self.risk_alerts: List[Dict[str, Any]] = []
        self.update_count = 0
        self.last_update_time = time.time()
    
    def add_position(self, position: Any) -> None:
        """Add or update a position in the portfolio"""
        self.portfolio[position.symbol] = {
            'symbol': position.symbol,
            'size': position.position_size,
            'entry_price': position.entry_price,
            'current_price': position.current_price,
            'broker': position.broker,
            'timestamp': position.timestamp or datetime.now(timezone.utc),
            'value': position.position_size * position.current_price,
            'unrealized_pnl': (position.current_price - position.entry_price) * position.position_size,
        }
        self.position_history.append(position)
        self.logger.debug(f"Added position: {position.symbol} ({position.position_size})")
    
    def remove_position(self, symbol: str) -> None:
        """Remove a position from the portfolio"""
        if symbol in self.portfolio:
            del self.portfolio[symbol]
            self.logger.debug(f"Removed position: {symbol}")
    
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get a specific position"""
        return self.portfolio.get(symbol)
    
    def get_portfolio_value(self) -> float:
        """Get total portfolio value"""
        return sum(pos['value'] for pos in self.portfolio.values())
    
    def get_unrealized_pnl(self) -> float:
        """Get total unrealized P&L"""
        return sum(pos['unrealized_pnl'] for pos in self.portfolio.values())
    
    def get_total_exposure(self) -> float:
        """Get total portfolio exposure"""
        return self.get_portfolio_value()
    
    def get_exposure_by_broker(self) -> Dict[str, float]:
        """Get exposure breakdown by broker"""
        exposures = defaultdict(float)
        for pos in self.portfolio.values():
            exposures[pos['broker']] += pos['value']
        return dict(exposures)
    
    def calculate_var(self) -> Dict[str, float]:
        """Calculate Value at Risk"""
        if not self.portfolio:
            return {'var_95': 0.0, 'var_99': 0.0, 'expected_shortfall': 0.0}
        
        # Simple historical VaR calculation
        returns = []
        for pos in self.position_history:
            if pos.entry_price > 0:
                ret = (pos.current_price - pos.entry_price) / pos.entry_price
                returns.append(ret)
        
        if not returns or len(returns) < 2:
            return {
                'var_95': 0.0,
                'var_99': 0.0,
                'expected_shortfall': 0.0
            }
        
        returns = np.array(returns)
        portfolio_val = self.get_portfolio_value()
        
        # Calculate percentiles (VaR)
        var_95 = np.percentile(returns, 5) * portfolio_val  # 5th percentile = 95% VaR
        var_99 = np.percentile(returns, 1) * portfolio_val  # 1st percentile = 99% VaR
        
        # Expected Shortfall (average of worst returns)
        worst_returns = returns[returns <= np.percentile(returns, 5)]
        expected_shortfall = np.mean(worst_returns) * portfolio_val if len(worst_returns) > 0 else var_95
        
        return {
            'var_95': abs(var_95),
            'var_99': abs(var_99),
            'expected_shortfall': abs(expected_shortfall),
            'confidence_level': 0.95,
            'methodology': 'HISTORICAL'
        }
    
    def track_drawdown(self) -> Dict[str, float]:
        """Track portfolio drawdown"""
        current_value = self.get_portfolio_value()
        
        if current_value > self.peak_portfolio_value:
            self.peak_portfolio_value = current_value
        
        current_drawdown = (current_value - self.peak_portfolio_value) / self.peak_portfolio_value if self.peak_portfolio_value > 0 else 0.0
        
        return {
            'current_drawdown': abs(current_drawdown),
            'drawdown_pct': abs(current_drawdown) * 100,
            'peak_value': self.peak_portfolio_value,
            'current_value': current_value,
        }
    
    def check_risk_thresholds(self, max_portfolio_drawdown_pct: float = 0.05) -> List[Dict[str, Any]]:
        """Check risk thresholds and generate alerts"""
        alerts = []
        
        # Check drawdown
        drawdown_info = self.track_drawdown()
        if drawdown_info['drawdown_pct'] > (max_portfolio_drawdown_pct * 100):
            alerts.append({
                'alert_type': 'DRAWDOWN_LIMIT_EXCEEDED',
                'severity': 'HIGH',
                'drawdown_pct': drawdown_info['drawdown_pct'],
                'threshold': max_portfolio_drawdown_pct * 100,
                'timestamp': datetime.now(timezone.utc),
            })
        
        # Check VaR
        var_metrics = self.calculate_var()
        max_var = self.risk_config.get('max_portfolio_var', 0.05)
        if var_metrics['var_95'] > (max_var * self.get_portfolio_value()):
            alerts.append({
                'alert_type': 'VAR_LIMIT_EXCEEDED',
                'severity': 'MEDIUM',
                'var_95': var_metrics['var_95'],
                'threshold': max_var,
                'timestamp': datetime.now(timezone.utc),
            })
        
        # Store alerts
        self.risk_alerts.extend(alerts)
        for alert in alerts:
            self.logger.warning(f"Risk alert: {alert['alert_type']}")
        
        return alerts
    
    def update_metrics(self) -> RiskMetrics:
        """Update all risk metrics"""
        drawdown_info = self.track_drawdown()
        var_metrics = self.calculate_var()
        
        self.risk_metrics = RiskMetrics(
            timestamp=datetime.now(timezone.utc),
            portfolio_value=self.get_portfolio_value(),
            var_95=var_metrics['var_95'],
            var_99=var_metrics['var_99'],
            expected_shortfall=var_metrics.get('expected_shortfall', 0.0),
            current_drawdown=drawdown_info['current_drawdown'],
            max_drawdown=drawdown_info['drawdown_pct'] / 100,
            total_exposure=self.get_total_exposure(),
            number_positions=len(self.portfolio)
        )
        
        self.update_count += 1
        self.last_update_time = time.time()
        
        return self.risk_metrics
    
    def get_risk_report(self) -> Dict[str, Any]:
        """Get comprehensive risk report"""
        self.update_metrics()
        
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'portfolio_value': self.get_portfolio_value(),
            'unrealized_pnl': self.get_unrealized_pnl(),
            'total_exposure': self.get_total_exposure(),
            'number_positions': len(self.portfolio),
            'risk_metrics': {
                'var_95': self.risk_metrics.var_95 if self.risk_metrics else 0.0,
                'var_99': self.risk_metrics.var_99 if self.risk_metrics else 0.0,
                'expected_shortfall': self.risk_metrics.expected_shortfall if self.risk_metrics else 0.0,
                'current_drawdown': self.risk_metrics.current_drawdown if self.risk_metrics else 0.0,
                'max_drawdown': self.risk_metrics.max_drawdown if self.risk_metrics else 0.0,
            },
            'exposure_by_broker': self.get_exposure_by_broker(),
            'recent_alerts': self.risk_alerts[-10:] if self.risk_alerts else [],
        }
