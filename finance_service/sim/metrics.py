"""Portfolio performance metrics"""
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
from .portfolio import Portfolio

class Metrics:
    """Calculate trading metrics and statistics"""
    
    @staticmethod
    def calc_returns(snapshots: List) -> Dict[str, float]:
        """Calculate returns from portfolio snapshots"""
        if not snapshots or len(snapshots) < 2:
            return {
                "total_return_pct": 0.0,
                "cagr": 0.0,
                "volatility": 0.0,
            }
        
        starting_value = snapshots[0].total_value
        ending_value = snapshots[-1].total_value
        total_return = (ending_value - starting_value) / starting_value if starting_value > 0 else 0
        
        # Volatility
        values = [s.total_value for s in snapshots]
        daily_returns = np.diff(values) / np.array(values[:-1])
        volatility = np.std(daily_returns) * np.sqrt(252) if len(daily_returns) > 1 else 0
        
        # CAGR (simplified)
        days = (snapshots[-1].timestamp - snapshots[0].timestamp).days
        years = max(days / 365, 1)
        cagr = (pow(ending_value / starting_value, 1 / years) - 1) if starting_value > 0 else 0
        
        return {
            "total_return_pct": round(total_return * 100, 2),
            "cagr": round(cagr * 100, 2),
            "volatility": round(volatility * 100, 2),
        }
    
    @staticmethod
    def calc_drawdown(snapshots: List) -> Dict[str, float]:
        """Calculate max and current drawdown"""
        if not snapshots:
            return {
                "max_drawdown_pct": 0.0,
                "current_drawdown_pct": 0.0,
            }
        
        values = [s.total_value for s in snapshots]
        current = values[-1]
        peak = values[0]
        max_dd = 0.0
        
        for val in values:
            if val > peak:
                peak = val
            dd = (peak - val) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        current_dd = (peak - current) / peak if peak > 0 else 0
        
        return {
            "max_drawdown_pct": round(max_dd * 100, 2),
            "current_drawdown_pct": round(current_dd * 100, 2),
        }
    
    @staticmethod
    def calc_sharpe(portfolio: Portfolio, risk_free_rate: float = 0.02) -> Dict[str, float]:
        """Calculate Sharpe ratio"""
        if not portfolio.snapshots or len(portfolio.snapshots) < 2:
            return {"sharpe_ratio": 0.0}
        
        values = np.array([s.total_value for s in portfolio.snapshots])
        returns = np.diff(values) / values[:-1]
        
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        annual_return = mean_return * 252
        annual_std = std_return * np.sqrt(252)
        
        sharpe = (annual_return - risk_free_rate) / annual_std if annual_std > 0 else 0
        
        return {"sharpe_ratio": round(sharpe, 2)}
    
    @staticmethod
    def calc_win_rate(trades: List) -> Dict[str, float]:
        """Calculate win rate from trades"""
        if not trades:
            return {
                "win_rate_pct": 0.0,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
            }
        
        # Group by symbol/action
        wins = 0
        total = 0
        
        for trade in trades:
            if hasattr(trade, 'pnl') and trade.pnl > 0:
                wins += 1
            total += 1
        
        win_rate = (wins / total * 100) if total > 0 else 0
        
        return {
            "win_rate_pct": round(win_rate, 2),
            "total_trades": total,
            "winning_trades": wins,
            "losing_trades": total - wins,
        }
    
    @staticmethod
    def summary(portfolio: Portfolio) -> Dict:
        """Generate comprehensive metrics summary"""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "portfolio": portfolio.get_state(),
            "returns": Metrics.calc_returns(portfolio.snapshots),
            "drawdown": Metrics.calc_drawdown(portfolio.snapshots),
            "sharpe": Metrics.calc_sharpe(portfolio),
            "trades": Metrics.calc_win_rate(portfolio.trades),
        }
