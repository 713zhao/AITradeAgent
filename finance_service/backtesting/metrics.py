"""Performance metrics calculations for backtest results.

Provides functions to compute Sharpe, Sortino, Calmar, max drawdown,
profit factor, win rate, and more.
"""
import numpy as np
import pandas as pd
from typing import Dict, Any

def calculate_metrics(
    equity: pd.Series,
    trades: pd.DataFrame,
    risk_free_rate: float = 0.0,
    annual_factor: int = 252,
) -> Dict[str, float]:
    """
    Calculate comprehensive performance metrics.

    Args:
        equity: Portfolio equity curve (daily)
        trades: DataFrame with trade records (must have 'pnl' column)
        risk_free_rate: Annual risk-free rate (default 0)
        annual_factor: Number of trading periods per year (252 for daily)

    Returns:
        Dict of metric names to values
    """
    returns = equity.pct_change().dropna()
    if len(returns) == 0:
        return {}

    # Annualized return
    total_return = (equity.iloc[-1] / equity.iloc[0]) - 1
    years = len(returns) / annual_factor
    cagr = (1 + total_return) ** (1 / max(years, 1e-6)) - 1

    # Volatility
    annual_vol = returns.std() * np.sqrt(annual_factor)

    # Sharpe Ratio
    excess_returns = returns - (risk_free_rate / annual_factor)
    sharpe = (excess_returns.mean() / returns.std()) * np.sqrt(annual_factor) if returns.std() > 0 else 0.0

    # Sortino Ratio (downside deviation)
    downside_returns = returns[returns < 0]
    downside_std = downside_returns.std() if len(downside_returns) > 0 else 0.0
    sortino = (returns.mean() / downside_std) * np.sqrt(annual_factor) if downside_std > 0 else 0.0

    # Max Drawdown
    running_max = equity.expanding().max()
    drawdown = (equity - running_max) / running_max
    max_dd = drawdown.min()
    max_dd_duration = _max_drawdown_duration(drawdown)

    # Calmar Ratio
    calmar = cagr / abs(max_dd) if max_dd != 0 else 0.0

    # Trade metrics
    if len(trades) > 0:
        wins = trades[trades['pnl'] > 0]
        losses = trades[trades['pnl'] <= 0]
        win_rate = len(wins) / len(trades)
        avg_win = wins['pnl'].mean() if len(wins) > 0 else 0.0
        avg_loss = losses['pnl'].mean() if len(losses) > 0 else 0.0
        gross_profit = wins['pnl'].sum()
        gross_loss = abs(losses['pnl'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss)))
        avg_holding = (trades['exit_date'] - trades['entry_date']).dt.days.mean()
    else:
        win_rate = avg_win = avg_loss = profit_factor = expectancy = avg_holding = 0.0
        gross_profit = gross_loss = 0.0

    return {
        "total_return_pct": total_return,
        "cagr": cagr,
        "annual_volatility": annual_vol,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "max_drawdown": max_dd,
        "max_drawdown_duration_days": max_dd_duration,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "avg_holding_period_days": avg_holding,
        "total_trades": len(trades),
    }


def _max_drawdown_duration(drawdown: pd.Series) -> int:
    """Calculate maximum drawdown duration in periods"""
    underwater = drawdown < 0
    if not underwater.any():
        return 0
    # Longest consecutive underwater period
    underwater_int = underwater.astype(int)
    groups = (underwater_int != underwater_int.shift()).cumsum()
    durations = underwater_int.groupby(groups).sum()
    return int(durations.max()) if len(durations) > 0 else 0


def monthly_returns_heatmap(equity: pd.Series) -> pd.DataFrame:
    """Generate monthly returns heatmap DataFrame"""
    returns = equity.resample('M').last().pct_change().dropna()
    returns.index = returns.index.to_period('M')
    # Pivot to years x months
    heatmap = returns.groupby([returns.index.year, returns.index.month]).first().unstack()
    heatmap.columns = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    return heatmap
