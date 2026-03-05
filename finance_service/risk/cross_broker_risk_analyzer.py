"""
Cross-Broker Risk Analyzer

Portfolio correlation analysis, concentration risk assessment,
and cross-broker exposure monitoring.
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Any
from collections import defaultdict


class CrossBrokerRiskAnalyzer:
    """
    Cross-broker risk analysis system.
    
    Analyzes portfolio risk across multiple brokers including:
    - Correlation matrix calculation
    - Concentration risk assessment
    - Cross-broker exposure limits
    - Diversification scoring
    """
    
    def __init__(self, config: Dict[str, Any], event_manager):
        self.config = config
        self.event_manager = event_manager
        self.logger = logging.getLogger(__name__)
    
    def calculate_correlation_matrix(self, symbols: List[str], 
                                    price_data: Dict[str, List[float]]) -> np.ndarray:
        """
        Calculate correlation matrix from price data.
        
        Args:
            symbols: List of symbols
            price_data: Dict mapping symbol to list of prices
            
        Returns:
            Correlation matrix (n x n)
        """
        if not symbols or not price_data:
            return np.array([])
        
        # Convert prices to returns
        returns_list = []
        
        for symbol in symbols:
            prices = np.array(price_data.get(symbol, []))
            if len(prices) > 1:
                # Calculate log returns
                returns = np.log(prices[1:] / prices[:-1])
                returns_list.append(returns)
            else:
                # If only one price, use zero returns
                returns_list.append(np.zeros(len(returns_list[0]) if returns_list else 1))
        
        # Ensure all return series have same length
        min_length = min(len(r) for r in returns_list) if returns_list else 0
        if min_length > 0:
            returns_list = [r[:min_length] for r in returns_list]
        
        # Create matrix of returns
        returns_matrix = np.array(returns_list)
        
        # Calculate correlation
        if returns_matrix.shape[0] > 0 and returns_matrix.shape[1] > 0:
            correlation = np.corrcoef(returns_matrix)
        else:
            correlation = np.eye(len(symbols))
        
        # Ensure NaN values are replaced with zero
        correlation = np.nan_to_num(correlation, nan=0.0)
        
        self.logger.debug(f"Calculated {len(symbols)}-symbol correlation matrix")
        
        return correlation
    
    def assess_concentration_risk(self, positions: Dict[str, Dict[str, float]],
                                 portfolio_value: float) -> Dict[str, Any]:
        """
        Assess portfolio concentration risk.
        
        Args:
            positions: Dict mapping symbol to position details (size, value, broker)
            portfolio_value: Total portfolio value
            
        Returns:
            Concentration risk metrics
        """
        if not positions or portfolio_value <= 0:
            return {
                'herfindahl_index': 0.0,
                'max_position_pct': 0.0,
                'concentration_level': 'NONE',
            }
        
        # Calculate position weights
        weights = []
        max_position = 0
        max_symbol = None
        
        for symbol, pos_data in positions.items():
            value = pos_data.get('value', 0)
            weight = value / portfolio_value if portfolio_value > 0 else 0
            weights.append(weight)
            
            if weight > max_position:
                max_position = weight
                max_symbol = symbol
        
        # Calculate Herfindahl index (concentration measure)
        # HI = sum(weights^2)  Range: [1/N, 1]
        # 0: Equal weight, 1: Single position
        herfindahl_index = np.sum(np.array(weights) ** 2)
        
        # Determine concentration level
        avg_weight = 1 / len(positions) if positions else 0
        if herfindahl_index < avg_weight + 0.1:
            concentration_level = 'LOW'
        elif herfindahl_index < avg_weight + 0.2:
            concentration_level = 'MODERATE'
        else:
            concentration_level = 'HIGH'
        
        return {
            'herfindahl_index': herfindahl_index,
            'max_position_pct': max_position * 100,
            'max_position_symbol': max_symbol,
            'concentration_level': concentration_level,
            'number_positions': len(positions),
            'average_position_pct': (1 / len(positions) * 100) if positions else 0,
        }
    
    def check_exposure_limits(self, exposures: Dict[str, float],
                             portfolio_value: float,
                             max_broker_exposure_pct: float = 0.70) -> Dict[str, Any]:
        """
        Check if broker exposures exceed limits.
        
        Args:
            exposures: Dict mapping broker to exposure amount
            portfolio_value: Total portfolio value
            max_broker_exposure_pct: Maximum single broker exposure (default 70%)
            
        Returns:
            Exposure limit check results
        """
        if not exposures or portfolio_value <= 0:
            return {'within_limits': True, 'violations': []}
        
        violations = []
        broker_percentages = {}
        
        for broker, exposure in exposures.items():
            exposure_pct = exposure / portfolio_value
            broker_percentages[broker] = exposure_pct
            
            if exposure_pct > max_broker_exposure_pct:
                violations.append({
                    'broker': broker,
                    'exposure': exposure,
                    'exposure_pct': exposure_pct * 100,
                    'limit_pct': max_broker_exposure_pct * 100,
                    'violation_amount': exposure - (portfolio_value * max_broker_exposure_pct),
                })
        
        return {
            'within_limits': len(violations) == 0,
            'violations': violations,
            'broker_exposures': {
                b: {'amount': e, 'pct': broker_percentages[b] * 100}
                for b, e in exposures.items()
            },
        }
    
    def calculate_diversification_score(self, positions: Dict[str, Dict[str, Any]],
                                       portfolio_value: float) -> Dict[str, Any]:
        """
        Calculate portfolio diversification score.
        
        Considers both sector and broker diversification.
        Score ranges from 0 (no diversification) to 1.0 (perfect diversification)
        """
        if not positions or portfolio_value <= 0:
            return {'score': 0.0, 'components': {}}
        
        # Sector diversification
        sector_exposure = defaultdict(float)
        broker_exposure = defaultdict(float)
        
        for symbol, pos_data in positions.items():
            value = pos_data.get('value', 0)
            sector = pos_data.get('sector', 'UNKNOWN')
            broker = pos_data.get('broker', 'UNKNOWN')
            
            sector_exposure[sector] += value
            broker_exposure[broker] += value
        
        # Calculate entropy for sector diversification (0 to 1)
        sector_weights = np.array(list(sector_exposure.values())) / portfolio_value
        sector_entropy = -np.sum(sector_weights * np.log(sector_weights + 1e-10)) / np.log(len(sector_exposure))
        sector_score = min(1.0, sector_entropy)
        
        # Calculate entropy for broker diversification
        broker_weights = np.array(list(broker_exposure.values())) / portfolio_value
        broker_entropy = -np.sum(broker_weights * np.log(broker_weights + 1e-10)) / np.log(len(broker_exposure))
        broker_score = min(1.0, broker_entropy)
        
        # Combined score (70% sector, 30% broker)
        combined_score = (sector_score * 0.7) + (broker_score * 0.3)
        
        return {
            'score': combined_score,
            'components': {
                'sector_diversification': sector_score,
                'broker_diversification': broker_score,
                'sector_count': len(sector_exposure),
                'broker_count': len(broker_exposure),
            },
            'sector_breakdown': {
                sector: {
                    'amount': exposure,
                    'pct': (exposure / portfolio_value * 100) if portfolio_value > 0 else 0
                }
                for sector, exposure in sector_exposure.items()
            },
            'broker_breakdown': {
                broker: {
                    'amount': exposure,
                    'pct': (exposure / portfolio_value * 100) if portfolio_value > 0 else 0
                }
                for broker, exposure in broker_exposure.items()
            },
        }
    
    def get_correlation_for_symbol(self, symbol: str, symbols: List[str],
                                  correlation_matrix: np.ndarray) -> Dict[str, float]:
        """
        Get correlation of a symbol with all other symbols.
        """
        try:
            idx = symbols.index(symbol)
            correlations = {}
            
            for i, other_symbol in enumerate(symbols):
                if i != idx:
                    correlations[other_symbol] = correlation_matrix[idx, i]
            
            return correlations
        except (ValueError, IndexError):
            return {}
    
    def identify_portfolio_risks(self, positions: Dict[str, Dict[str, Any]],
                                portfolio_value: float,
                                correlation_matrix: np.ndarray = None) -> Dict[str, Any]:
        """
        Identify key portfolio risks.
        """
        risks = {
            'concentration_risk': self.assess_concentration_risk(positions, portfolio_value),
            'diversification_score': self.calculate_diversification_score(positions, portfolio_value),
            'identified_risks': [],
        }
        
        # Check for concentration risk
        concentration = risks['concentration_risk']
        if concentration['concentration_level'] == 'HIGH':
            risks['identified_risks'].append({
                'type': 'CONCENTRATION',
                'severity': 'HIGH',
                'message': f"Largest position is {concentration['max_position_pct']:.1f}% of portfolio",
                'max_position': concentration['max_position_symbol'],
                'max_position_pct': concentration['max_position_pct'],
            })
        
        # Check for low diversification
        div_score = risks['diversification_score']
        if div_score['score'] < 0.3:
            risks['identified_risks'].append({
                'type': 'LOW_DIVERSIFICATION',
                'severity': 'MEDIUM',
                'message': f"Portfolio diversification score is only {div_score['score']:.2f}",
                'diversification_score': div_score['score'],
            })
        
        return risks
