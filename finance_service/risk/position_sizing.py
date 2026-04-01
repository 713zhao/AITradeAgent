"""Position sizing algorithms.

Provides multiple ways to determine position size based on risk budget, volatility,
and portfolio constraints.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
from dataclasses import dataclass

from finance_service.risk.portfolio_risk import PortfolioRisk

logger = logging.getLogger(__name__)


@dataclass
class PositionSizingContext:
    """Context for position sizing decision"""
    portfolio_risk: PortfolioRisk
    signal: Dict[str, Any]  # {'action': 'BUY'|'SELL', 'confidence': 0-1, 'price': float}
    risk_budget_pct: float  # Max loss per trade as % of equity (e.g., 0.01 = 1%)
    current_equity: float
    stop_loss_price: Optional[float] = None  # Required for risk-based sizing


class PositionSizer(ABC):
    """Abstract base for position sizing strategies"""

    @abstractmethod
    def calculate(self, context: PositionSizingContext) -> float:
        """
        Calculate position size in shares (notional = shares * price).

        Args:
            context: Sizing context with portfolio state, signal, risk budget

        Returns:
            Number of shares (rounded down to integer)
        """
        pass

    def _validate_sizing(self, shares: float, price: float, context: PositionSizingContext) -> float:
        """Apply common validation and adjustments"""
        if shares <= 0 or price <= 0:
            return 0.0

        # Ensure at least 1 share if sizing > 0
        shares = max(int(shares), 1)

        # Check against max position size limit
        position_value = shares * price
        max_allowed = context.portfolio_risk.total_equity * 0.10  # default 10% limit
        if position_value > max_allowed:
            shares = int(max_allowed / price)

        return shares


class EqualRiskPositionSizer(PositionSizer):
    """Risk-based sizing: same dollar risk per trade (Kelly-inspired).

    Position size = risk_budget / (stop_loss_distance per share).

    Example: Equity $100k, risk_budget 1% = $1k max loss. Stop distance $2/share => 500 shares.
    """
    def calculate(self, context: PositionSizingContext) -> float:
        if context.signal['action'] not in ('BUY', 'SELL'):
            return 0.0

        price = context.signal['price']
        stop_loss = context.stop_loss_price

        if stop_loss is None:
            # Fallback to 2% stop if not provided
            if context.signal['action'] == 'BUY':
                stop_loss = price * 0.98
            else:
                stop_loss = price * 1.02

        risk_per_share = abs(price - stop_loss)
        if risk_per_share <= 0:
            logger.warning("Invalid risk_per_share; defaulting to 1 share")
            return 1

        risk_budget_usd = context.current_equity * context.risk_budget_pct
        shares = int(risk_budget_usd / risk_per_share)

        # Apply validation
        shares = self._validate_sizing(shares, price, context)
        logger.debug(f"EqualRisk: equity=${context.current_equity:,.0f}, risk_budget=${risk_budget_usd:.0f}, "
                     f"price=${price:.2f}, stop=${stop_loss:.2f}, risk_per_share=${risk_per_share:.2f} => {shares} shares")
        return shares


class VolatilityAdjustedPositionSizer(PositionSizer):
    """Adjust position size inversely to recent volatility.

    Higher volatility → smaller position.
    Uses ATR or realized volatility from recent data.
    """
    def __init__(self, lookback_days: int = 20, target_volatility: float = 0.20):
        self.lookback_days = lookback_days
        self.target_volatility = target_volatility  # annualized

    def calculate(self, context: PositionSizingContext) -> float:
        if context.signal['action'] not in ('BUY', 'SELL'):
            return 0.0

        price = context.signal['price']

        # Estimate annualized volatility for the symbol (simple historical)
        # This would normally come from AnalysisAgent indicators
        volatility = self._estimate_volatility(context)
        if volatility == 0:
            volatility = 0.20  # fallback

        # Scale position: vol_adjustment = target_vol / actual_vol
        vol_adjustment = self.target_volatility / volatility

        # Base sizing: equal risk (1% of equity)
        base_shares = EqualRiskPositionSizer().calculate(context)

        # Apply volatility adjustment
        adjusted_shares = int(base_shares * vol_adjustment)

        shares = self._validate_sizing(adjusted_shares, price, context)
        logger.debug(f"VolatilityAdjusted: vol={volatility:.1%}, adjustment={vol_adjustment:.2f}x, shares={shares}")
        return shares

    def _estimate_volatility(self, context: PositionSizingContext) -> float:
        """Estimate annualized volatility for the signal symbol"""
        # Placeholder: In real implementation, fetch from indicators or historical data
        # For now, return a default
        return 0.25  # 25% annualized vol


class EqualWeightPositionSizer(PositionSizer):
    """Equal weight across all positions.

    Splits allowed capital equally among Nmax concurrent positions.
    """
    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent

    def calculate(self, context: PositionSizingContext) -> float:
        if context.signal['action'] not in ('BUY', 'SELL'):
            return 0.0

        price = context.signal['price']

        # Determine how many positions we already have
        current_positions = len([p for p in context.portfolio_risk.positions.keys()
                                if p not in ('__cash__',)])
        remaining_slots = max(1, self.max_concurrent - current_positions)

        # Allocate equal portion of allowed capital
        allowed_capital = context.current_equity * 0.95  # keep 5% dry powder
        allocation_per_position = allowed_capital / remaining_slots

        # Then within that allocation, use risk-based sizing? Or just full allocation?
        # Simple: buy as many shares as fit in the allocation
        shares = int(allocation_per_position / price)

        shares = self._validate_sizing(shares, price, context)
        logger.debug(f"EqualWeight: remaining_slots={remaining_slots}, allocation=${allocation_per_position:.0f}, shares={shares}")
        return shares


class PositionSizerFactory:
    """Factory to create position sizers from config"""

    SIZERS = {
        'equal_risk': EqualRiskPositionSizer,
        'volatility_adjusted': VolatilityAdjustedPositionSizer,
        'equal_weight': EqualWeightPositionSizer,
    }

    @classmethod
    def create(cls, method: str, **kwargs) -> PositionSizer:
        sizer_class = cls.SIZERS.get(method)
        if not sizer_class:
            raise ValueError(f"Unknown position sizer: {method}. Options: {list(cls.SIZERS.keys())}")
        return sizer_class(**kwargs)
