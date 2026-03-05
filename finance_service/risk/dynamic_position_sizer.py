"""
Dynamic Position Sizer

Intelligent position sizing algorithms including Kelly Criterion,
volatility-adjusted sizing, risk parity allocation, and correlation-based adjustments.
"""

import logging
import numpy as np
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class PositionSizingResult:
    """Position sizing calculation result"""
    symbol: str
    position_size: int
    kelly_fraction: float
    volatility_adjustment: float
    correlation_adjustment: float
    reasoning: str
    calculation_method: str


class DynamicPositionSizer:
    """
    Dynamic position sizing system.
    
    Provides multiple position sizing algorithms including Kelly Criterion,
    volatility adjustment, risk parity allocation, and correlation-based sizing.
    """
    
    def __init__(self, config: Dict[str, Any], event_manager):
        self.config = config
        self.event_manager = event_manager
        self.logger = logging.getLogger(__name__)
        
        # Position sizing configuration
        self.sizing_config = config.get('position_sizing', {})
        self.method = self.sizing_config.get('method', 'KELLY')
        self.max_position_size = self.sizing_config.get('max_position_size', 0.10)
    
    def calculate_kelly_size(self, symbol: str, win_rate: float, win_loss_ratio: float, 
                           volatility: float) -> Dict[str, Any]:
        """
        Calculate position size using Kelly Criterion.
        
        Kelly Formula: f = (p * b - q) / b
        where:
        - p = probability of win
        - q = probability of loss (1 - p)
        - b = win/loss ratio
        - f = fraction of capital to risk
        """
        if win_rate <= 0 or win_rate >= 1:
            return {'kelly_fraction': 0.0, 'error': 'Invalid win rate'}
        
        p = win_rate
        q = 1 - p
        b = win_loss_ratio
        
        # Standard Kelly formula
        kelly_fraction = (p * b - q) / b
        
        # Apply safety limit (use fractional Kelly: 0.25 of full Kelly)
        kelly_fraction = max(0, min(kelly_fraction, 0.25))
        
        # Apply maximum position size limit
        kelly_fraction = min(kelly_fraction, self.max_position_size)
        
        return {
            'symbol': symbol,
            'kelly_fraction': kelly_fraction,
            'win_rate': win_rate,
            'win_loss_ratio': win_loss_ratio,
            'volatility': volatility,
            'calculation_method': 'KELLY',
            'reasoning': f'Kelly: f = ({p:.3f} * {b:.2f} - {q:.3f}) / {b:.2f} = {kelly_fraction:.4f}'
        }
    
    def calculate_volatility_adjusted_size(self, symbol: str, portfolio_value: float,
                                         target_risk_pct: float, volatility: float) -> Dict[str, Any]:
        """
        Calculate volatility-adjusted position size.
        
        Size = (Portfolio * Risk%) / (Price Change)
        where Price Change = Portfolio Value * Volatility
        """
        if volatility <= 0:
            return {'position_size': 0, 'error': 'Invalid volatility'}
        
        # Risk in dollars
        risk_dollars = portfolio_value * target_risk_pct
        
        # Expected price move (1 standard deviation)
        price_move_pct = volatility / np.sqrt(252)  # Annualized to daily
        
        # Position size adjusted for volatility
        position_size = int(risk_dollars / (portfolio_value * price_move_pct))
        
        # Apply maximum position size limit
        max_position = int(portfolio_value * self.max_position_size)
        position_size = min(position_size, max_position)
        
        return {
            'symbol': symbol,
            'position_size': position_size,
            'portfolio_value': portfolio_value,
            'target_risk_pct': target_risk_pct,
            'volatility': volatility,
            'risk_dollars': risk_dollars,
            'price_move_pct': price_move_pct,
            'calculation_method': 'VOLATILITY_ADJUSTED',
        }
    
    def calculate_risk_parity_allocation(self, symbols: List[str], volatilities: Dict[str, float],
                                        portfolio_value: float, target_risk: float) -> Dict[str, int]:
        """
        Allocate positions using Risk Parity method.
        
        Each position contributes equal risk to portfolio.
        """
        if not symbols or not volatilities:
            return {}
        
        allocations = {}
        
        # Calculate inverse volatility weights
        inv_vols = {}
        total_inv_vol = 0
        
        for symbol in symbols:
            vol = volatilities.get(symbol, 0.20)
            if vol > 0:
                inv_vol = 1.0 / vol
                inv_vols[symbol] = inv_vol
                total_inv_vol += inv_vol
        
        if total_inv_vol == 0:
            # Equal weight if all volatilities are zero
            equal_weight = 1.0 / len(symbols)
            return {sym: int(portfolio_value * equal_weight * target_risk / 100) for sym in symbols}
        
        # Allocate based on inverse volatility (low vol = higher allocation)
        for symbol in symbols:
            weight = inv_vols.get(symbol, 0) / total_inv_vol
            position_size = int(portfolio_value * weight * target_risk / 100)
            allocations[symbol] = position_size
        
        return allocations
    
    def calculate_correlation_adjusted_size(self, symbol: str, portfolio_symbols: List[str],
                                           correlation_matrix: np.ndarray, 
                                           portfolio_value: float) -> Dict[str, Any]:
        """
        Adjust position size based on portfolio correlation.
        
        High correlation with existing positions reduces size.
        Low correlation increases size.
        """
        if symbol not in portfolio_symbols:
            portfolio_symbols = portfolio_symbols + [symbol]
        
        # Find symbol index
        try:
            symbol_idx = portfolio_symbols.index(symbol)
        except ValueError:
            return {'position_size': int(portfolio_value * self.max_position_size)}
        
        # Calculate average correlation with existing positions
        correlations = correlation_matrix[symbol_idx, :]
        avg_correlation = np.mean(correlations[correlations != 1.0])  # Exclude self-correlation
        
        # Adjust position size based on correlation
        # High correlation (close to 1.0) -> reduce size
        # Low correlation (close to 0.0) -> increase size
        correlation_adjustment = 1.0 - abs(avg_correlation)
        
        base_size = portfolio_value * self.max_position_size
        adjusted_size = int(base_size * correlation_adjustment)
        
        return {
            'symbol': symbol,
            'position_size': adjusted_size,
            'average_correlation': avg_correlation,
            'correlation_adjustment': correlation_adjustment,
            'base_size': base_size,
            'calculation_method': 'CORRELATION_ADJUSTED',
        }
    
    def calculate_combined_sizing(self, symbol: str, portfolio_value: float,
                                 win_rate: float, win_loss_ratio: float,
                                 volatility: float, correlations: Dict[str, float]) -> PositionSizingResult:
        """
        Calculate position size using multiple methods and combine results.
        """
        # Kelly Criterion
        kelly_result = self.calculate_kelly_size(symbol, win_rate, win_loss_ratio, volatility)
        kelly_size = kelly_result['kelly_fraction']
        
        # Volatility-adjusted
        vol_result = self.calculate_volatility_adjusted_size(
            symbol, portfolio_value, 0.02, volatility
        )
        vol_size = vol_result['position_size']
        
        # Apply correlation adjustment
        avg_correlation = np.mean(list(correlations.values())) if correlations else 0.5
        corr_adjustment = 1.0 - abs(avg_correlation)
        
        # Combined size (average of methods)
        combined_fraction = (kelly_size + corr_adjustment) / 2
        final_size = int(portfolio_value * combined_fraction)
        final_size = min(final_size, int(portfolio_value * self.max_position_size))
        
        return PositionSizingResult(
            symbol=symbol,
            position_size=final_size,
            kelly_fraction=kelly_size,
            volatility_adjustment=vol_result.get('volatility', 0.0),
            correlation_adjustment=corr_adjustment,
            reasoning=f'Kelly: {kelly_size:.4f}, Vol Adj: {corr_adjustment:.4f}, Combined: {combined_fraction:.4f}',
            calculation_method='COMBINED'
        )
