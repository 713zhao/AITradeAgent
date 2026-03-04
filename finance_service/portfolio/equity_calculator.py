"""
Equity Calculator

Calculates and tracks portfolio equity, returns, and risk metrics.
"""

from typing import Dict, List, Tuple, Any
from datetime import datetime
import logging

from .models import Portfolio, Position

logger = logging.getLogger(__name__)


class EquityCalculator:
    """
    Calculates portfolio and position equity metrics.
    
    Provides:
    - Equity snapshots (historical equity values)
    - Return calculations (absolute and percentage)
    - Drawdown and max drawdown metrics
    - Risk-adjusted returns (Sharpe ratio, Sortino ratio)
    """
    
    def __init__(self):
        """Initialize calculator with historical snapshots."""
        self.snapshots: List[Dict[str, Any]] = []
    
    def snapshot_equity(self, portfolio: Portfolio) -> Dict[str, Any]:
        """
        Create an equity snapshot at current time.
        
        Args:
            portfolio: Current Portfolio state
        
        Returns:
            Snapshot dict with equity metrics
        """
        snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "initial_cash": portfolio.initial_cash,
            "current_cash": portfolio.current_cash,
            "gross_position_value": portfolio.gross_position_value(),
            "net_position_value": portfolio.net_position_value(),
            "total_equity": portfolio.total_equity(),
            "unrealized_pnl": portfolio.unrealized_pnl(),
            "realized_pnl": portfolio.realized_pnl(),
            "total_pnl": portfolio.total_pnl(),
            "total_return_pct": portfolio.total_return_pct(),
            "position_count": portfolio.position_count(),
            "trade_count": portfolio.trade_count(),
            "win_rate": portfolio.win_rate(),
            "drawdown_pct": portfolio.drawdown_pct(),
        }
        
        self.snapshots.append(snapshot)
        return snapshot
    
    def calculate_return(self, start_value: float, end_value: float) -> float:
        """
        Calculate absolute return.
        
        Args:
            start_value: Starting capital
            end_value: Ending capital
        
        Returns:
            Absolute return (end - start)
        """
        return end_value - start_value
    
    def calculate_return_pct(self, start_value: float, end_value: float) -> float:
        """
        Calculate percentage return.
        
        Args:
            start_value: Starting capital
            end_value: Ending capital
        
        Returns:
            Percentage return: (end - start) / start * 100
        """
        if start_value == 0:
            return 0.0
        return ((end_value - start_value) / start_value) * 100
    
    def calculate_max_drawdown(self) -> Tuple[float, int, int]:
        """
        Calculate maximum drawdown from historical snapshots.
        
        Returns:
            Tuple of (max_drawdown_pct, peak_index, trough_index)
        """
        if not self.snapshots:
            return 0.0, 0, 0
        
        equities = [s["total_equity"] for s in self.snapshots]
        peak = equities[0]
        max_dd = 0.0
        peak_idx = 0
        trough_idx = 0
        
        for i, equity in enumerate(equities):
            if equity > peak:
                peak = equity
                peak_idx = i
            
            drawdown = (peak - equity) / peak * 100 if peak > 0 else 0
            if drawdown > max_dd:
                max_dd = drawdown
                trough_idx = i
        
        return max_dd, peak_idx, trough_idx
    
    def calculate_sharpe_ratio(
        self,
        returns: List[float],
        risk_free_rate: float = 0.02,
    ) -> float:
        """
        Calculate Sharpe ratio (annualized risk-adjusted return).
        
        Args:
            returns: List of periodic returns (as decimals, e.g., 0.05 = 5%)
            risk_free_rate: Risk-free rate (default 2% annual)
        
        Returns:
            Sharpe ratio (return / volatility)
        """
        if not returns or len(returns) < 2:
            return 0.0
        
        import statistics
        
        # Calculate average return
        avg_return = statistics.mean(returns)
        
        # Calculate standard deviation (volatility)
        if len(returns) == 1:
            return 0.0
        
        volatility = statistics.stdev(returns)
        if volatility == 0:
            return 0.0
        
        # Annualize (assume 252 trading days)
        annual_return = avg_return * 252
        annual_volatility = volatility * (252 ** 0.5)
        
        # Sharpe = (return - risk_free_rate) / volatility
        sharpe = (annual_return - risk_free_rate) / annual_volatility
        return sharpe
    
    def calculate_sortino_ratio(
        self,
        returns: List[float],
        risk_free_rate: float = 0.02,
    ) -> float:
        """
        Calculate Sortino ratio (downside risk-adjusted return).
        
        Only penalizes downside volatility (losses), not upside.
        
        Args:
            returns: List of periodic returns (as decimals)
            risk_free_rate: Risk-free rate (default 2% annual)
        
        Returns:
            Sortino ratio
        """
        if not returns or len(returns) < 2:
            return 0.0
        
        # Calculate average return
        avg_return = sum(returns) / len(returns)
        
        # Calculate downside deviation (only negative returns)
        downside_returns = [r for r in returns if r < 0]
        if not downside_returns:
            # No losses, perfect Sortino
            return float('inf')
        
        downside_variance = sum(r ** 2 for r in downside_returns) / len(returns)
        downside_dev = downside_variance ** 0.5
        
        if downside_dev == 0:
            return float('inf')
        
        # Annualize
        annual_return = avg_return * 252
        annual_downside = downside_dev * (252 ** 0.5)
        
        # Sortino = (return - risk_free_rate) / downside_risk
        sortino = (annual_return - risk_free_rate) / annual_downside
        return sortino
    
    def calculate_win_loss_ratio(self, wins: float, losses: float) -> float:
        """
        Calculate win/loss ratio.
        
        Args:
            wins: Number of winning trades
            losses: Number of losing trades
        
        Returns:
            Ratio wins / losses (inf if no losses)
        """
        if losses == 0:
            return float('inf') if wins > 0 else 0.0
        return wins / losses
    
    def calculate_profit_factor(
        self,
        gross_profit: float,
        gross_loss: float,
    ) -> float:
        """
        Calculate profit factor (gross profit / gross loss).
        
        Values > 1.0 indicate profitability.
        
        Args:
            gross_profit: Sum of all winning trades
            gross_loss: Sum of all losing trades (as positive)
        
        Returns:
            Profit factor
        """
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        return gross_profit / gross_loss
    
    def calculate_recovery_factor(self) -> float:
        """
        Calculate recovery factor (net profit / max drawdown).
        
        Higher is better. Indicates how quickly the system recovers from drawdowns.
        
        Returns:
            Recovery factor (inf if no drawdown)
        """
        if not self.snapshots:
            return 0.0
        
        first = self.snapshots[0]
        last = self.snapshots[-1]
        
        net_profit = last["total_pnl"]
        max_dd, _, _ = self.calculate_max_drawdown()
        
        if max_dd == 0:
            return float('inf') if net_profit > 0 else 0.0
        
        return net_profit / max_dd
    
    def get_metrics_summary(self, portfolio: Portfolio) -> Dict[str, Any]:
        """
        Get comprehensive equity metrics summary.
        
        Args:
            portfolio: Current Portfolio state
        
        Returns:
            Dict with all calculated metrics
        """
        metrics = {
            "equity_metrics": {
                "initial": portfolio.initial_cash,
                "current": portfolio.total_equity(),
                "absolute_return": self.calculate_return(
                    portfolio.initial_cash,
                    portfolio.total_equity(),
                ),
                "return_pct": portfolio.total_return_pct(),
                "unrealized_pnl": portfolio.unrealized_pnl(),
                "realized_pnl": portfolio.realized_pnl(),
                "drawdown_pct": portfolio.drawdown_pct(),
            },
            "position_metrics": {
                "count": portfolio.position_count(),
                "gross_value": portfolio.gross_position_value(),
                "net_value": portfolio.net_position_value(),
                "cash": portfolio.current_cash,
            },
            "trade_metrics": {
                "total_trades": portfolio.trade_count(),
                "win_rate": portfolio.win_rate(),
            },
        }
        
        # Add historical metrics if snapshots available
        if len(self.snapshots) > 1:
            max_dd, _, _ = self.calculate_max_drawdown()
            metrics["historical_metrics"] = {
                "max_drawdown": max_dd,
                "snapshots_count": len(self.snapshots),
            }
        
        return metrics
    
    def clear_snapshots(self) -> None:
        """Clear all historical snapshots."""
        self.snapshots.clear()
