"""Risk management tools"""
from typing import Dict, Any, Optional
import logging
from ..core.config import Config
from ..core.models import Position

logger = logging.getLogger(__name__)

class RiskTools:
    """Risk validation and position sizing"""
    
    @staticmethod
    def calc_position_size(symbol: str, current_price: float, atr: Optional[float] = None,
                          portfolio_equity: float = 100000,
                          risk_budget_pct: float = 0.01,
                          multiplier: float = 2.0) -> Dict[str, Any]:
        """
        Calculate position size based on ATR and risk budget
        
        Args:
            symbol: Ticker symbol
            current_price: Current price
            atr: Average True Range (optional)
            portfolio_equity: Total portfolio equity
            risk_budget_pct: Risk budget as % of equity
            multiplier: ATR multiplier for stop loss
        
        Returns:
            dict with 'shares', 'cost', 'stop_loss', 'risk_amount'
        """
        if atr is None:
            atr = current_price * 0.05  # Default to 5% of price
        
        # Risk per trade in dollars
        risk_amount = portfolio_equity * risk_budget_pct
        
        # Stop loss in dollars per share
        stop_loss_distance = atr * multiplier
        stop_loss_price = current_price - stop_loss_distance
        
        # Number of shares
        if stop_loss_distance > 0:
            shares = risk_amount / stop_loss_distance
        else:
            shares = 0
        
        return {
            "symbol": symbol,
            "shares": round(shares, 2),
            "cost": round(shares * current_price, 2),
            "entry_price": current_price,
            "stop_loss": round(stop_loss_price, 2),
            "risk_amount": round(risk_amount, 2),
            "atr": atr,
        }
    
    @staticmethod
    def validate_trade(symbol: str, action: str, qty: float, price: float,
                      portfolio_equity: float, existing_positions: Dict[str, Position],
                      policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Validate a proposed trade against risk policies
        
        Args:
            symbol: Ticker symbol
            action: 'BUY' or 'SELL'
            qty: Quantity of shares
            price: Price per share
            portfolio_equity: Current portfolio equity
            existing_positions: Dict of existing positions
            policy: Risk policy overrides
        
        Returns:
            dict with 'valid', 'errors', 'warnings'
        """
        if policy is None:
            policy = {
                "max_position_size": Config.MAX_POSITION_SIZE,
                "max_exposure": Config.MAX_EXPOSURE,
                "max_daily_loss": Config.MAX_DAILY_LOSS,
            }
        
        errors = []
        warnings = []
        
        # Check position size / portfolio
        trade_value = qty * price
        position_pct = trade_value / portfolio_equity if portfolio_equity > 0 else 0
        
        if position_pct > policy.get("max_position_size", 0.20):
            errors.append(
                f"Position size {position_pct:.1%} exceeds max {policy.get('max_position_size', 0.20):.1%}"
            )
        
        # Check total exposure
        total_exposure_value = sum(int(p.market_value) for p in existing_positions.values())
        if action == "BUY":
            total_exposure_value += trade_value
        
        total_exposure_pct = total_exposure_value / portfolio_equity if portfolio_equity > 0 else 0
        
        if total_exposure_pct > policy.get("max_exposure", 0.90):
            warnings.append(
                f"Total exposure {total_exposure_pct:.1%} near/over max {policy.get('max_exposure', 0.90):.1%}"
            )
        
        # Check if symbol already has position
        if action == "BUY" and symbol in existing_positions:
            warnings.append(f"Already hold {existing_positions[symbol].qty} shares of {symbol}")
        
        if action == "SELL":
            if symbol not in existing_positions:
                errors.append(f"Cannot sell {symbol}: no position held")
            elif qty > existing_positions[symbol].qty:
                errors.append(
                    f"Cannot sell {qty} of {symbol}: only hold {existing_positions[symbol].qty}"
                )
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "trade_value": trade_value,
            "position_pct": position_pct,
            "total_exposure_pct": total_exposure_pct,
        }
    
    @staticmethod
    def calc_max_loss(entry_price: float, stop_loss_price: float, qty: float) -> float:
        """Calculate maximum potential loss for a position"""
        return abs((entry_price - stop_loss_price) * qty)
