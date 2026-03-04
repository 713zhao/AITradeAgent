"""Analytics engine for advanced metrics and analysis."""

import logging
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    """
    Advanced analytics engine for performance analysis.
    
    Calculates sharpe ratio, max drawdown, VAR, and other metrics.
    """
    
    def __init__(self, risk_free_rate: float = 0.02):
        """
        Initialize analytics engine.
        
        Args:
            risk_free_rate: Annual risk-free rate (default 2%)
        """
        self.risk_free_rate = risk_free_rate
        self.daily_returns: List[float] = []
        self.snapshots: Dict[datetime, float] = {}
    
    def add_daily_return(self, date: datetime, return_pct: float):
        """Add daily return for analysis."""
        self.daily_returns.append(return_pct)
        self.snapshots[date] = return_pct
    
    def calculate_sharpe_ratio(self, period_days: int = 252) -> float:
        """
        Calculate Sharpe ratio.
        
        Args:
            period_days: Trading days for annualization (default 252)
            
        Returns:
            Sharpe ratio (excess return per unit of volatility)
        """
        if not self.daily_returns or len(self.daily_returns) < 2:
            return 0.0
        
        try:
            # Annual return
            total_return = sum(self.daily_returns)
            annual_return = (total_return / len(self.daily_returns)) * period_days
            
            # Volatility
            variance = statistics.variance(self.daily_returns) if len(self.daily_returns) > 1 else 0
            std_dev = statistics.stdev(self.daily_returns) if variance > 0 else 0
            annual_volatility = std_dev * (period_days ** 0.5)
            
            # Risk-free rate component
            excess_return = annual_return - self.risk_free_rate
            
            if annual_volatility == 0:
                return 0.0
            
            return excess_return / annual_volatility
        except Exception as e:
            logger.error(f"Error calculating Sharpe ratio: {e}")
            return 0.0
    
    def calculate_max_drawdown(self) -> Tuple[float, datetime, datetime]:
        """
        Calculate maximum drawdown from peak to trough.
        
        Returns:
            Tuple of (max_drawdown%, peak_date, trough_date)
        """
        if not self.snapshots or len(self.snapshots) < 2:
            return (0.0, datetime.now(), datetime.now())
        
        try:
            sorted_dates = sorted(self.snapshots.keys())
            max_drawdown = 0.0
            peak_date = sorted_dates[0]
            trough_date = sorted_dates[0]
            peak_value = self.snapshots[sorted_dates[0]]
            
            for date in sorted_dates[1:]:
                current_value = self.snapshots[date]
                
                # Update peak
                if current_value > peak_value:
                    peak_value = current_value
                    peak_date = date
                
                # Calculate drawdown
                drawdown = (peak_value - current_value) / peak_value * 100
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                    trough_date = date
            
            return (max_drawdown, peak_date, trough_date)
        except Exception as e:
            logger.error(f"Error calculating max drawdown: {e}")
            return (0.0, datetime.now(), datetime.now())
    
    def calculate_sortino_ratio(self, period_days: int = 252) -> float:
        """
        Calculate Sortino ratio (penalizes downside volatility only).
        
        Args:
            period_days: Trading days for annualization
            
        Returns:
            Sortino ratio
        """
        if not self.daily_returns or len(self.daily_returns) < 2:
            return 0.0
        
        try:
            # Upside return
            total_return = sum(self.daily_returns)
            annual_return = (total_return / len(self.daily_returns)) * period_days
            
            # Downside deviation (only negative returns)
            downside_returns = [r for r in self.daily_returns if r < 0]
            if not downside_returns:
                return 0.0  # No downside = infinite sortino
            
            downside_variance = sum(r ** 2 for r in downside_returns) / len(downside_returns)
            downside_std = downside_variance ** 0.5
            annual_downside_std = downside_std * (period_days ** 0.5)
            
            excess_return = annual_return - self.risk_free_rate
            
            if annual_downside_std == 0:
                return 0.0
            
            return excess_return / annual_downside_std
        except Exception as e:
            logger.error(f"Error calculating Sortino ratio: {e}")
            return 0.0
    
    def calculate_calmar_ratio(self) -> float:
        """
        Calculate Calmar ratio (return / max drawdown).
        
        Returns:
            Calmar ratio
        """
        try:
            max_dd, _, _ = self.calculate_max_drawdown()
            if max_dd == 0:
                return 0.0
            
            total_return = sum(self.daily_returns)
            annual_return = (total_return / len(self.daily_returns) * 252) if self.daily_returns else 0
            
            return annual_return / max_dd if max_dd > 0 else 0.0
        except Exception as e:
            logger.error(f"Error calculating Calmar ratio: {e}")
            return 0.0
    
    def calculate_value_at_risk(self, confidence: float = 0.95) -> float:
        """
        Calculate Value-at-Risk (VaR) at given confidence level.
        
        Args:
            confidence: Confidence level (0.95 = 95%)
            
        Returns:
            VaR (worst expected loss at confidence level)
        """
        if not self.daily_returns or len(self.daily_returns) < 10:
            return 0.0
        
        try:
            sorted_returns = sorted(self.daily_returns)
            index = int(len(sorted_returns) * (1 - confidence))
            return sorted_returns[index]
        except Exception as e:
            logger.error(f"Error calculating VaR: {e}")
            return 0.0
    
    def calculate_conditional_var(self, confidence: float = 0.95) -> float:
        """
        Calculate Conditional VaR (average of losses beyond VaR).
        
        Args:
            confidence: Confidence level (0.95 = 95%)
            
        Returns:
            CVaR (average loss in worst (1-confidence) of cases)
        """
        if not self.daily_returns or len(self.daily_returns) < 10:
            return 0.0
        
        try:
            var = self.calculate_value_at_risk(confidence)
            worse_returns = [r for r in self.daily_returns if r <= var]
            if not worse_returns:
                return var
            return statistics.mean(worse_returns)
        except Exception as e:
            logger.error(f"Error calculating CVaR: {e}")
            return 0.0
    
    def calculate_win_rate(self, trades: List[Dict]) -> float:
        """
        Calculate win rate from trade history.
        
        Args:
            trades: List of trade dictionaries with 'pnl' key
            
        Returns:
            Win rate (0-100%)
        """
        if not trades:
            return 0.0
        
        try:
            winning_trades = len([t for t in trades if t.get('pnl', 0) > 0])
            return (winning_trades / len(trades) * 100) if trades else 0.0
        except Exception as e:
            logger.error(f"Error calculating win rate: {e}")
            return 0.0
    
    def calculate_profit_factor(self, trades: List[Dict]) -> float:
        """
        Calculate profit factor (gross profit / gross loss).
        
        Args:
            trades: List of trade dictionaries with 'pnl' key
            
        Returns:
            Profit factor (ratio of winning $ to losing $)
        """
        if not trades:
            return 0.0
        
        try:
            gross_profit = sum(max(0, t.get('pnl', 0)) for t in trades)
            gross_loss = abs(sum(min(0, t.get('pnl', 0)) for t in trades))
            
            return gross_profit / gross_loss if gross_loss > 0 else 0.0
        except Exception as e:
            logger.error(f"Error calculating profit factor: {e}")
            return 0.0
    
    def calculate_expectancy(self, trades: List[Dict]) -> float:
        """
        Calculate expectancy (average profit per trade).
        
        Args:
            trades: List of trade dictionaries with 'pnl' key
            
        Returns:
            Average PnL per trade
        """
        if not trades:
            return 0.0
        
        try:
            total_pnl = sum(t.get('pnl', 0) for t in trades)
            return total_pnl / len(trades) if trades else 0.0
        except Exception as e:
            logger.error(f"Error calculating expectancy: {e}")
            return 0.0
    
    def analyze_performance_period(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, float]:
        """
        Analyze performance for a specific period.
        
        Args:
            start_date: Period start
            end_date: Period end
            
        Returns:
            Dictionary with analysis metrics
        """
        period_returns = [
            v for k, v in self.snapshots.items()
            if start_date <= k <= end_date
        ]
        
        if not period_returns:
            return {}
        
        try:
            return {
                "total_return": sum(period_returns),
                "avg_return": statistics.mean(period_returns),
                "volatility": statistics.stdev(period_returns) if len(period_returns) > 1 else 0,
                "best_day": max(period_returns),
                "worst_day": min(period_returns),
                "positive_days": len([r for r in period_returns if r > 0]),
                "negative_days": len([r for r in period_returns if r < 0]),
            }
        except Exception as e:
            logger.error(f"Error analyzing period: {e}")
            return {}
    
    def calculate_correlation(self, returns_a: List[float], returns_b: List[float]) -> float:
        """
        Calculate correlation between two return series.
        
        Args:
            returns_a: First series of returns
            returns_b: Second series of returns
            
        Returns:
            Correlation coefficient (-1 to 1)
        """
        if len(returns_a) != len(returns_b) or len(returns_a) < 2:
            return 0.0
        
        try:
            if len(returns_a) < 2:
                return 0.0
            
            mean_a = statistics.mean(returns_a)
            mean_b = statistics.mean(returns_b)
            
            numerator = sum((a - mean_a) * (b - mean_b) for a, b in zip(returns_a, returns_b))
            
            variance_a = sum((a - mean_a) ** 2 for a in returns_a)
            variance_b = sum((b - mean_b) ** 2 for b in returns_b)
            
            denominator = (variance_a * variance_b) ** 0.5
            
            return numerator / denominator if denominator > 0 else 0.0
        except Exception as e:
            logger.error(f"Error calculating correlation: {e}")
            return 0.0
    
    def reset(self):
        """Reset analytics data."""
        self.daily_returns.clear()
        self.snapshots.clear()
        logger.info("Analytics engine reset")
