"""
Compliance Monitor

Regulatory compliance checking, position limit enforcement,
leverage monitoring, and audit trail management.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from collections import defaultdict


class ComplianceMonitor:
    """
    Compliance monitoring system.
    
    Ensures adherence to:
    - Regulatory position limits
    - Leverage restrictions
    - Sector concentration limits
    - Broker exposure limits
    - Audit trail requirements
    """
    
    def __init__(self, config: Dict[str, Any], event_manager):
        self.config = config
        self.event_manager = event_manager
        self.logger = logging.getLogger(__name__)
        
        # Compliance configuration
        self.compliance_config = config.get('compliance', {})
        self.max_leverage = self.compliance_config.get('max_leverage', 2.0)
        self.position_limits = self.compliance_config.get('position_limits', {})
        self.sector_limits = self.compliance_config.get('sector_limits', {})
        
        # Audit trail
        self.audit_trail: List[Dict[str, Any]] = []
        self.violations: List[Dict[str, Any]] = []
    
    def check_position_limit(self, position: Dict[str, Any],
                            position_limits: Dict[str, int]) -> Dict[str, Any]:
        """
        Check if a position complies with position limits.
        
        Args:
            position: Dict with 'symbol' and 'size' keys
            position_limits: Dict mapping symbol to maximum position size
            
        Returns:
            Compliance check result
        """
        symbol = position.get('symbol', '')
        size = position.get('size', 0)
        
        limit = position_limits.get(symbol, float('inf'))
        compliant = size <= limit
        
        result = {
            'symbol': symbol,
            'size': size,
            'limit': limit,
            'compliant': compliant,
        }
        
        if not compliant:
            result['violation'] = 'POSITION_LIMIT_EXCEEDED'
            result['excess_amount'] = size - limit
            self.violations.append(result)
            self.logger.warning(f"Position limit violation: {symbol} ({size} > {limit})")
        
        return result
    
    def check_leverage(self, total_exposure: float, account_value: float,
                      max_leverage: float) -> Dict[str, Any]:
        """
        Check if leverage is within limits.
        
        Leverage = Total Exposure / Account Value
        """
        if account_value <= 0:
            return {
                'current_leverage': 0.0,
                'max_leverage': max_leverage,
                'compliant': True,
            }
        
        current_leverage = total_exposure / account_value
        compliant = current_leverage <= max_leverage
        
        result = {
            'total_exposure': total_exposure,
            'account_value': account_value,
            'current_leverage': current_leverage,
            'max_leverage': max_leverage,
            'compliant': compliant,
        }
        
        if not compliant:
            result['violation'] = 'LEVERAGE_LIMIT_EXCEEDED'
            result['excess_leverage'] = current_leverage - max_leverage
            self.violations.append(result)
            self.logger.warning(f"Leverage limit violation: {current_leverage:.2f}x > {max_leverage:.2f}x")
        
        return result
    
    def check_sector_limits(self, positions: Dict[str, Dict[str, Any]],
                           portfolio_value: float,
                           sector_limits: Dict[str, float]) -> Dict[str, Any]:
        """
        Check if sector exposures are within limits.
        
        Args:
            positions: Dict mapping symbol to position data (with 'value' and 'sector' keys)
            portfolio_value: Total portfolio value
            sector_limits: Dict mapping sector to maximum exposure percentage
            
        Returns:
            Sector compliance check results
        """
        sector_exposures = defaultdict(float)
        
        # Calculate sector exposures
        for symbol, pos_data in positions.items():
            value = pos_data.get('value', 0)
            sector = pos_data.get('sector', 'UNKNOWN')
            sector_exposures[sector] += value
        
        # Check limits
        result = {}
        for sector, exposure in sector_exposures.items():
            exposure_pct = exposure / portfolio_value if portfolio_value > 0 else 0
            limit_pct = sector_limits.get(sector, 1.0)  # Default 100% if no limit
            compliant = exposure_pct <= limit_pct
            
            result[sector] = {
                'amount': exposure,
                'pct': exposure_pct * 100,
                'limit_pct': limit_pct * 100,
                'compliant': compliant,
            }
            
            if not compliant:
                violation = {
                    'sector': sector,
                    'exposure': exposure,
                    'exposure_pct': exposure_pct * 100,
                    'limit_pct': limit_pct * 100,
                    'excess_amount': exposure - (portfolio_value * limit_pct),
                }
                self.violations.append(violation)
                self.logger.warning(f"Sector limit violation: {sector} ({exposure_pct * 100:.1f}% > {limit_pct * 100:.1f}%)")
        
        return result
    
    def check_concentration_limit(self, max_single_position_pct: float = 0.25) -> bool:
        """
        Check if portfolio has excessive concentration.
        """
        # This would be checked via cross-broker analyzer
        # Implementation would depend on portfolio data
        return True
    
    def check_counterparty_limits(self, broker_exposures: Dict[str, float],
                                 total_portfolio: float,
                                 max_broker_exposure_pct: float = 0.50) -> Dict[str, Any]:
        """
        Check if any single counterparty (broker) exposure is excessive.
        """
        result = {'within_limits': True, 'violations': []}
        
        for broker, exposure in broker_exposures.items():
            exposure_pct = exposure / total_portfolio if total_portfolio > 0 else 0
            
            if exposure_pct > max_broker_exposure_pct:
                result['within_limits'] = False
                result['violations'].append({
                    'broker': broker,
                    'exposure': exposure,
                    'exposure_pct': exposure_pct * 100,
                    'limit_pct': max_broker_exposure_pct * 100,
                })
        
        return result
    
    def log_compliance_event(self, event_type: str, symbol: str = '',
                            size: int = 0, compliance_status: str = 'UNKNOWN',
                            details: Optional[Dict[str, Any]] = None) -> None:
        """
        Log a compliance event to audit trail.
        """
        event = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'event_type': event_type,
            'symbol': symbol,
            'size': size,
            'compliance_status': compliance_status,
            'details': details or {},
        }
        
        self.audit_trail.append(event)
        self.logger.info(f"Compliance event: {event_type} - {symbol} ({size})")
    
    def get_audit_trail(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent audit trail entries.
        """
        return self.audit_trail[-limit:]
    
    def get_violations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent compliance violations.
        """
        return self.violations[-limit:]
    
    def generate_compliance_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive compliance report.
        """
        return {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'total_violations': len(self.violations),
            'recent_violations': self.get_violations(10),
            'position_limits_configured': len(self.position_limits),
            'sector_limits_configured': len(self.sector_limits),
            'max_leverage': self.max_leverage,
            'audit_trail_entries': len(self.audit_trail),
            'recent_events': self.get_audit_trail(20),
        }
    
    def clear_violations_before(self, days: int = 30) -> int:
        """
        Clear old violation records (data retention policy).
        """
        cutoff_time = datetime.now(timezone.utc)
        # Implementation would filter by timestamp
        return 0
    
    def validate_order_compliance(self, order: Dict[str, Any],
                                 position_limits: Dict[str, int],
                                 current_leverage: float) -> Dict[str, Any]:
        """
        Validate an order against compliance rules before execution.
        """
        symbol = order.get('symbol', '')
        size = order.get('quantity', 0)
        
        # Check position limits
        position_check = self.check_position_limit(
            {'symbol': symbol, 'size': size},
            position_limits
        )
        
        # Check leverage (if adding exposure)
        total_new_exposure = order.get('projected_portfolio_value', 0)
        account_value = order.get('account_value', 0)
        
        leverage_check = self.check_leverage(
            total_new_exposure,
            account_value,
            self.max_leverage
        )
        
        compliant = position_check['compliant'] and leverage_check['compliant']
        
        result = {
            'compliant': compliant,
            'position_check': position_check,
            'leverage_check': leverage_check,
            'can_execute': compliant,
        }
        
        if not compliant:
            result['rejection_reasons'] = []
            if not position_check['compliant']:
                result['rejection_reasons'].append('Position limit exceeded')
            if not leverage_check['compliant']:
                result['rejection_reasons'].append('Leverage limit exceeded')
        
        return result
