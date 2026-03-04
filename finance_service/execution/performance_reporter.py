"""
Performance Reporter - Phase 5: Generate performance metrics and reports

Responsibilities:
- Calculate performance metrics (Sharpe, Sortino, drawdown)
- Generate performance reports
- Track key performance indicators
- Monthly/daily performance summaries
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import statistics


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics."""
    
    # Basic metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    # P&L
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    
    # Returns
    total_return_pct: float = 0.0
    annual_return_pct: float = 0.0
    monthly_return_pct: float = 0.0
    
    # Risk metrics
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    profit_factor: float = 0.0
    
    # Trade statistics
    avg_win: float = 0.0
    avg_loss: float = 0.0
    win_rate: float = 0.0
    
    # Timing
    avg_trade_duration: float = 0.0  # Hours
    win_rate_consecutive: float = 0.0
    
    def to_dict(self) -> Dict:
        """Serialize metrics."""
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "gross_pnl": self.gross_pnl,
            "net_pnl": self.net_pnl,
            "total_return_pct": self.total_return_pct,
            "annual_return_pct": self.annual_return_pct,
            "monthly_return_pct": self.monthly_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "profit_factor": self.profit_factor,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "win_rate": self.win_rate,
            "avg_trade_duration_hours": self.avg_trade_duration,
            "consecutive_win_rate": self.win_rate_consecutive,
        }


@dataclass
class PerformanceReport:
    """Complete performance report."""
    
    report_id: str
    generated_at: datetime = field(default_factory=datetime.utcnow)
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    
    # Metrics
    metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    
    # Portfolio state
    starting_equity: float = 0.0
    ending_equity: float = 0.0
    peak_equity: float = 0.0
    
    # Breakdown by symbol
    symbol_performance: Dict[str, Dict] = field(default_factory=dict)
    
    # Monthly breakdown
    monthly_returns: Dict[str, float] = field(default_factory=dict)
    
    # Notes
    notes: str = ""
    
    def to_dict(self) -> Dict:
        """Serialize report."""
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at.isoformat(),
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "metrics": self.metrics.to_dict(),
            "starting_equity": self.starting_equity,
            "ending_equity": self.ending_equity,
            "peak_equity": self.peak_equity,
            "symbol_performance": self.symbol_performance,
            "monthly_returns": self.monthly_returns,
            "notes": self.notes,
        }


class PerformanceReporter:
    """
    Generate performance reports and metrics.
    
    Tracks:
    - Trade performance (wins/losses)
    - Portfolio metrics (Sharpe, Sortino, drawdown)
    - Monthly/daily breakdown
    - Symbol-level performance
    """
    
    def __init__(self):
        """Initialize performance reporter."""
        self.reports: Dict[str, PerformanceReport] = {}
        self.daily_returns: List[float] = []
        self.trade_results: List[float] = []
        self.equity_curve: List[float] = []
    
    def create_performance_report(
        self,
        report_id: str,
        starting_equity: float,
        ending_equity: float,
        trades: List[Dict],
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> PerformanceReport:
        """
        Generate performance report.
        
        Args:
            report_id: Report identifier
            starting_equity: Initial capital
            ending_equity: Final capital
            trades: List of closed trade dicts with realized_pnl
            period_start: Report period start
            period_end: Report period end
            
        Returns:
            PerformanceReport with full metrics
        """
        report = PerformanceReport(
            report_id=report_id,
            starting_equity=starting_equity,
            ending_equity=ending_equity,
            period_start=period_start,
            period_end=period_end,
        )
        
        # Calculate metrics from trades
        if trades:
            metrics = self._calculate_metrics(starting_equity, ending_equity, trades)
            report.metrics = metrics
            
            # Symbol breakdown
            symbol_trades = {}
            for trade in trades:
                symbol = trade.get("symbol", "UNKNOWN")
                if symbol not in symbol_trades:
                    symbol_trades[symbol] = []
                symbol_trades[symbol].append(trade)
            
            for symbol, symbol_trade_list in symbol_trades.items():
                report.symbol_performance[symbol] = self._symbol_stats(symbol_trade_list)
            
            # Update peak equity
            report.peak_equity = max(
                starting_equity,
                ending_equity,
                report.peak_equity
            )
        
        self.reports[report_id] = report
        return report
    
    def _calculate_metrics(
        self,
        starting_equity: float,
        ending_equity: float,
        trades: List[Dict]
    ) -> PerformanceMetrics:
        """Calculate performance metrics from trades."""
        metrics = PerformanceMetrics()
        
        # Count and PnL
        pnl_values = []
        trade_durations = []
        
        for trade in trades:
            pnl = trade.get("realized_pnl", 0.0)
            pnl_values.append(pnl)
            
            if pnl > 0:
                metrics.winning_trades += 1
                metrics.avg_win += pnl
            elif pnl < 0:
                metrics.losing_trades += 1
                metrics.avg_loss += pnl
            
            # Duration (if available)
            entry_time = trade.get("entry_time")
            exit_time = trade.get("exit_time")
            if entry_time and exit_time:
                duration = (exit_time - entry_time).total_seconds() / 3600  # Hours
                trade_durations.append(duration)
        
        metrics.total_trades = len(trades)
        metrics.gross_pnl = sum(pnl_values)
        metrics.net_pnl = ending_equity - starting_equity
        
        # Average win/loss
        if metrics.winning_trades > 0:
            metrics.avg_win = metrics.avg_win / metrics.winning_trades
        if metrics.losing_trades > 0:
            metrics.avg_loss = metrics.avg_loss / metrics.losing_trades
        
        # Win rate
        if metrics.total_trades > 0:
            metrics.win_rate = metrics.winning_trades / metrics.total_trades
        
        # Profit factor
        total_wins = sum(p for p in pnl_values if p > 0)
        total_losses = abs(sum(p for p in pnl_values if p < 0))
        if total_losses > 0:
            metrics.profit_factor = total_wins / total_losses
        
        # Returns
        if starting_equity > 0:
            metrics.total_return_pct = (ending_equity - starting_equity) / starting_equity * 100
        
        # Average trade duration
        if trade_durations:
            metrics.avg_trade_duration = statistics.mean(trade_durations)
        
        # Sharpe ratio (simplified: daily returns)
        if self.daily_returns and len(self.daily_returns) > 1:
            mean_return = statistics.mean(self.daily_returns)
            stdev = statistics.stdev(self.daily_returns)
            if stdev > 0:
                # Annualized Sharpe ratio (252 trading days)
                metrics.sharpe_ratio = (mean_return * 252 / stdev) if stdev > 0 else 0.0
        
        # Sortino ratio (downside deviation)
        if self.daily_returns:
            downside_returns = [r for r in self.daily_returns if r < 0]
            if downside_returns:
                mean_return = statistics.mean(self.daily_returns)
                downside_stdev = statistics.stdev(downside_returns)
                if downside_stdev > 0:
                    metrics.sortino_ratio = (mean_return * 252 / downside_stdev)
        
        return metrics
    
    def _symbol_stats(self, symbol_trades: List[Dict]) -> Dict:
        """Calculate stats for a single symbol."""
        pnl_values = [t.get("realized_pnl", 0.0) for t in symbol_trades]
        winning = len([p for p in pnl_values if p > 0])
        losing = len([p for p in pnl_values if p < 0])
        
        return {
            "trade_count": len(symbol_trades),
            "winning_trades": winning,
            "losing_trades": losing,
            "win_rate": winning / len(symbol_trades) if symbol_trades else 0.0,
            "total_pnl": sum(pnl_values),
            "avg_pnl": sum(pnl_values) / len(symbol_trades) if symbol_trades else 0.0,
        }
    
    def get_report(self, report_id: str) -> Optional[PerformanceReport]:
        """Get report by ID."""
        return self.reports.get(report_id)
    
    def get_reports(self) -> List[PerformanceReport]:
        """Get all reports."""
        return list(self.reports.values())
    
    def add_daily_return(self, daily_pnl: float, starting_equity: float) -> None:
        """Record daily return for Sharpe/Sortino calculation."""
        if starting_equity > 0:
            daily_return = daily_pnl / starting_equity
            self.daily_returns.append(daily_return)
    
    def add_trade_result(self, pnl: float) -> None:
        """Record individual trade result."""
        self.trade_results.append(pnl)
    
    def add_equity_snapshot(self, equity: float) -> None:
        """Record equity value for drawdown calculation."""
        self.equity_curve.append(equity)
    
    def calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown from equity curve."""
        if len(self.equity_curve) < 2:
            return 0.0
        
        max_equity = self.equity_curve[0]
        max_drawdown = 0.0
        
        for equity in self.equity_curve:
            if equity > max_equity:
                max_equity = equity
            
            drawdown = (max_equity - equity) / max_equity if max_equity > 0 else 0.0
            max_drawdown = max(max_drawdown, drawdown)
        
        return max_drawdown * 100  # Percentage
    
    def generate_monthly_summary(
        self,
        start_date: datetime,
        end_date: datetime,
        monthly_pnl: Dict[str, float]
    ) -> Dict:
        """
        Generate monthly performance summary.
        
        Args:
            start_date: Period start
            end_date: Period end
            monthly_pnl: Dict of {month: pnl}
            
        Returns:
            Monthly summary dict
        """
        best_month = max(monthly_pnl.values()) if monthly_pnl else 0.0
        worst_month = min(monthly_pnl.values()) if monthly_pnl else 0.0
        avg_month = sum(monthly_pnl.values()) / len(monthly_pnl) if monthly_pnl else 0.0
        
        return {
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "monthly_returns": monthly_pnl,
            "best_month": best_month,
            "worst_month": worst_month,
            "avg_monthly_return": avg_month,
        }
