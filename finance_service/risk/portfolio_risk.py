"""Portfolio risk calculations.

Provides portfolio-level risk metrics:
- Correlation matrix of returns
- Sector exposure tracking
- Portfolio volatility (annualized)
- VaR (Value-at-Risk) and Expected Shortfall
- Concentration risk
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class PortfolioRisk:
    """Portfolio risk snapshot"""
    total_equity: float
    total_position_value: float
    cash: float
    positions: Dict[str, Dict]  # symbol -> {quantity, avg_cost, current_price, market_value}
    correlation_matrix: Optional[pd.DataFrame] = None
    portfolio_volatility_annual: float = 0.0
    var_95: float = 0.0  # Daily VaR at 95%
    expected_shortfall_95: float = 0.0
    sector_exposure: Dict[str, float] = None  # sector -> $ exposure
    max_single_position_pct: float = 0.0
    herfindahl_index: float = 0.0  # Concentration measure (0-1)

    def to_dict(self) -> Dict:
        """Convert to dict for JSON serialization"""
        return {
            'total_equity': self.total_equity,
            'total_position_value': self.total_position_value,
            'cash': self.cash,
            'positions': self.positions,
            'portfolio_volatility_annual': self.portfolio_volatility_annual,
            'var_95': self.var_95,
            'expected_shortfall_95': self.expected_shortfall_95,
            'sector_exposure': self.sector_exposure or {},
            'max_single_position_pct': self.max_single_position_pct,
            'herfindahl_index': self.herfindahl_index,
        }


class PortfolioRiskCalculator:
    """Calculates portfolio-level risk metrics."""

    def __init__(self, lookback_days: int = 63, confidence_level: float = 0.95):
        self.lookback_days = lookback_days
        self.confidence_level = confidence_level

    def calculate(self, positions: Dict[str, Dict], historical_data: Optional[pd.DataFrame] = None) -> PortfolioRisk:
        """
        Calculate portfolio risk metrics.

        Args:
            positions: Dict of current positions {symbol: {quantity, avg_cost, current_price}}
            historical_data: Optional MultiIndex DataFrame with OHLCV for correlation/VaR calculations

        Returns:
            PortfolioRisk object with all metrics
        """
        # Basic portfolio composition
        total_equity = 0.0
        total_position_value = 0.0
        cash = positions.get('__cash__', 0.0)  # cash stored separately

        position_values = {}
        for symbol, pos in positions.items():
            if symbol == '__cash__':
                continue
            market_value = pos['quantity'] * pos['current_price']
            position_values[symbol] = market_value
            total_position_value += market_value

        total_equity = cash + total_position_value

        # Max single position concentration
        max_single_pct = 0.0
        if total_equity > 0:
            max_single_pct = max((pv / total_equity for pv in position_values.values()), default=0.0)

        # Sector exposure (placeholder: return empty dict until we have sector mapping)
        sector_exposure = {}

        # Herfindahl-Hirschman Index (HHI) for concentration
        if total_equity > 0:
            weights = [pv / total_equity for pv in position_values.values()]
            hhi = sum(w ** 2 for w in weights)
        else:
            hhi = 0.0

        # Portfolio volatility and VaR if historical data provided
        portfolio_vol = 0.0
        var_95 = 0.0
        es_95 = 0.0
        corr_matrix = None

        if historical_data is not None and len(position_values) > 0:
            # Compute daily returns for each symbol
            returns = historical_data.groupby(level='symbol')['close'].pct_change().dropna()
            if len(returns) > 0:
                # Align symbols with current positions
                symbols_in_portfolio = list(position_values.keys())
                returns = returns[symbols_in_portfolio].dropna(axis=1, how='all')

                if len(returns.columns) > 0:
                    # Correlation matrix (latest window)
                    corr_matrix = returns.tail(self.lookback_days).corr()

                    # Portfolio weights based on current market value
                    weights = np.array([position_values[s] / total_equity for s in returns.columns])
                    # Portfolio daily returns (historical)
                    port_returns = (returns.tail(self.lookback_days) * weights).sum(axis=1)

                    # Annualized volatility
                    portfolio_vol = port_returns.std() * np.sqrt(252)

                    # VaR (Historical Simulation)
                    var_95 = np.percentile(port_returns, (1 - self.confidence_level) * 100)
                    es_95 = port_returns[port_returns <= var_95].mean() if (port_returns <= var_95).any() else var_95

        risk = PortfolioRisk(
            total_equity=total_equity,
            total_position_value=total_position_value,
            cash=cash,
            positions=positions,
            correlation_matrix=corr_matrix,
            portfolio_volatility_annual=portfolio_vol,
            var_95=abs(var_95) * total_equity,  # dollar VaR
            expected_shortfall_95=abs(es_95) * total_equity,
            sector_exposure=sector_exposure,
            max_single_position_pct=max_single_pct,
            herfindahl_index=hhi,
        )
        return risk
