"""Vectorized backtesting engine.

This module provides a fast, vectorized backtester that applies trading signals
to historical data and tracks portfolio evolution over time.

Key Design:
- Vectorized operations on pandas DataFrames for performance
- Supports multi-symbol portfolios
- Handles position sizing, stop-loss, take-profit
- Configurable slippage and commission models
- Produces trade list, equity curve, and performance metrics
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Individual trade record"""
    trade_id: int
    symbol: str
    entry_date: pd.Timestamp
    exit_date: Optional[pd.Timestamp]
    side: int  # 1=LONG, -1=SHORT (currently only LONG)
    quantity: float
    entry_price: float
    exit_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    pnl: float  # realized P&L (USD)
    pnl_pct: float  # % return
    exit_reason: str  # "signal", "stop_loss", "take_profit", "end_of_data"
    metadata: Dict[str, Any]


@dataclass
class BacktestResults:
    """Complete backtest results"""
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_pct: float
    portfolio_history: pd.DataFrame  # daily equity, cash, positions
    trades: List[Trade]
    metrics: Dict[str, float]  # Sharpe, Sortino, max DD, etc.
    benchmark: Optional[pd.Series] = None  # benchmark equity curve
    strategy_name: str = ""


class BacktestEngine:
    """Vectorized backtesting engine for trading strategies.

    Args:
        initial_capital: Starting cash
        commission: Commission per trade (fraction, e.g., 0.0005 = 5 bps)
        slippage: Slippage per trade (fraction of price)
        max_position_size_pct: Max allocation per position (0-1)
        allow_short_selling: If True, allow short positions
        cooldown_period: Minimum bars between trades for same symbol (avoid churn)
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission: float = 0.0005,
        slippage: float = 0.0002,
        max_position_size_pct: float = 0.10,
        allow_short_selling: bool = False,
        cooldown_period: int = 1,
    ):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.max_position_size_pct = max_position_size_pct
        self.allow_short_selling = allow_short_selling
        self.cooldown_period = cooldown_period
        self._trade_counter = 0

    def run(
        self,
        data: pd.DataFrame,
        strategy: "BacktestableStrategy",
        benchmark_data: Optional[pd.DataFrame] = None,
    ) -> BacktestResults:
        """
        Run backtest over historical data.

        Args:
            data: Multi-index or wide DataFrame with OHLCV data.
                  Must have columns: 'open', 'high', 'low', 'close', 'volume'
                  Index should be datetime (can be MultiIndex with symbol)
            strategy: BacktestableStrategy instance that generates signals
            benchmark_data: Optional benchmark data (e.g., SPY) for comparison

        Returns:
            BacktestResults with portfolio history, trades, metrics
        """
        logger.info(f"Starting backtest: {len(data)} bars, capital=${self.initial_capital:,.2f}")

        # Prepare data
        if isinstance(data.index, pd.MultiIndex):
            # Multi-symbol: index levels (date, symbol)
            dates = data.index.get_level_values(0).unique()
            symbols = data.index.get_level_values(1).unique()
            is_multi = True
        else:
            # Single symbol: index is date
            dates = data.index
            symbols = [None]  # placeholder
            is_multi = False

        # Initialize portfolio tracking
        portfolio = pd.DataFrame(index=dates, columns=[
            'cash', 'equity', 'position_value', ' realized_pnl', 'unrealized_pnl'
        ])
        portfolio.iloc[0] = {
            'cash': self.initial_capital,
            'equity': self.initial_capital,
            'position_value': 0.0,
            'realized_pnl': 0.0,
            'unrealized_pnl': 0.0,
        }

        # Track open positions: dict {(symbol): Position}
        open_positions: Dict[Optional[str], Dict] = {}
        # Track cooldown: dict {(symbol): last_trade_bar_index}
        cooldown_expiry: Dict[Optional[str], int] = {}

        trades: List[Trade] = []
        self._trade_counter = 0

        # Main loop over time
        for i, date in enumerate(dates):
            # Get current bar data for all symbols
            if is_multi:
                current_bars = data.loc[date]  # DataFrame with symbol as index
            else:
                current_bars = data.loc[date:date]  # Single row DataFrame

            # 1. Generate signals for this bar (vectorized per symbol)
            signals = strategy.generate_signals(data.iloc[:i+1])  # pass history up to now

            # 2. Process existing positions: check exits (stop-loss, take-profit)
            positions_to_exit = []
            for sym, pos in open_positions.items():
                # Get current price for this symbol
                if is_multi:
                    if sym not in current_bars.index:
                        continue
                    bar = current_bars.loc[sym]
                else:
                    bar = current_bars.iloc[0]
                price = bar['close']

                # Check stop-loss
                if pos['stop_loss'] and ((pos['side'] == 1 and price <= pos['stop_loss']) or
                                         (pos['side'] == -1 and price >= pos['stop_loss'])):
                    positions_to_exit.append((sym, price, 'stop_loss'))
                    continue
                # Check take-profit
                if pos['take_profit'] and ((pos['side'] == 1 and price >= pos['take_profit']) or
                                           (pos['side'] == -1 and price <= pos['take_profit'])):
                    positions_to_exit.append((sym, price, 'take_profit'))
                    continue
                # Update unrealized P&L
                pos['unrealized_pnl'] = (price - pos['entry_price']) * pos['side'] * pos['quantity']

            # Execute exits
            for sym, exit_price, reason in positions_to_exit:
                pos = open_positions.pop(sym)
                trade = self._create_trade_from_position(pos, exit_price, date, reason)
                trades.append(trade)
                # Update cooldown
                cooldown_expiry[sym] = i + self.cooldown_period

            # 3. Process new signals (entries)
            for idx, signal in signals.iterrows():
                # Determine symbol
                if is_multi:
                    sym = idx[1] if isinstance(idx, tuple) else idx
                else:
                    sym = None

                # Check cooldown
                if cooldown_expiry.get(sym, 0) > i:
                    continue

                # Check if already in position
                if sym in open_positions:
                    continue

                signal_val = signal['signal']
                if signal_val == 0:
                    continue  # no trade

                # Get price
                if is_multi:
                    bar = current_bars.loc[sym]
                else:
                    bar = current_bars.iloc[0]
                price = bar['close']

                # Apply slippage
                if signal_val == 1:  # LONG
                    execution_price = price * (1 + self.slippage)
                else:  # SHORT
                    execution_price = price * (1 - self.slippage)
                    if not self.allow_short_selling:
                        continue  # skip short

                # Position sizing
                portfolio_value = portfolio.at[date, 'equity']
                position_value_limit = portfolio_value * self.max_position_size_pct
                qty = position_value_limit / execution_price
                qty = int(qty) if qty >= 1 else 0
                if qty == 0:
                    continue

                # Commission
                commission_cost = execution_price * qty * self.commission
                if commission_cost > portfolio.at[date, 'cash']:
                    continue  # insufficient cash

                # Open position
                open_positions[sym] = {
                    'symbol': sym,
                    'entry_date': date,
                    'side': signal_val,
                    'quantity': qty,
                    'entry_price': execution_price,
                    'stop_loss': signal.get('stop_loss'),
                    'take_profit': signal.get('take_profit'),
                    'unrealized_pnl': 0.0,
                }
                # Deduct cash for purchase (simple: full price * qty)
                portfolio.at[date, 'cash'] -= (execution_price * qty + commission_cost)
                cooldown_expiry[sym] = i + self.cooldown_period

            # 4. Mark to market and compute portfolio equity
            position_value = 0.0
            unrealized_pnl = 0.0
            for sym, pos in open_positions.items():
                if is_multi:
                    if sym not in current_bars.index:
                        continue
                    bar = current_bars.loc[sym]
                else:
                    bar = current_bars.iloc[0]
                price = bar['close']
                if pos['side'] == 1:
                    pos['unrealized_pnl'] = (price - pos['entry_price']) * pos['quantity']
                else:
                    pos['unrealized_pnl'] = (pos['entry_price'] - price) * pos['quantity']
                unrealized_pnl += pos['unrealized_pnl']
                position_value += price * pos['quantity']

            portfolio.at[date, 'position_value'] = position_value
            portfolio.at[date, 'cash'] = portfolio.at[date, 'cash']  # unchanged (except from trades)
            portfolio.at[date, 'unrealized_pnl'] = unrealized_pnl
            portfolio.at[date, 'realized_pnl'] = portfolio.at[date, 'realized_pnl']  # accumulate from exits
            portfolio.at[date, 'equity'] = portfolio.at[date, 'cash'] + position_value

        # Close all open positions at end (market order)
        end_date = dates[-1]
        for sym, pos in open_positions.items():
            if is_multi:
                bar = data.loc[(end_date, sym)] if (end_date, sym) in data.index else None
                if bar is None:
                    continue
                exit_price = bar['close']
            else:
                exit_price = data.loc[end_date, 'close']
            trade = self._create_trade_from_position(pos, exit_price, end_date, 'end_of_data')
            trades.append(trade)

        # Build benchmark if provided
        bench_equity = None
        if benchmark_data is not None:
            bench_returns = benchmark_data['close'].pct_change().fillna(0)
            bench_equity = self.initial_capital * (1 + bench_returns).cumprod()

        # Compute metrics
        metrics = self._compute_metrics(portfolio, trades)

        results = BacktestResults(
            initial_capital=self.initial_capital,
            final_capital=portfolio['equity'].iloc[-1],
            total_return=portfolio['equity'].iloc[-1] - self.initial_capital,
            total_return_pct=(portfolio['equity'].iloc[-1] / self.initial_capital) - 1,
            portfolio_history=portfolio,
            trades=trades,
            metrics=metrics,
            benchmark=bench_equity,
            strategy_name=strategy.__class__.__name__,
        )

        logger.info(f"Backtest complete: {len(trades)} trades, final equity=${results.final_capital:,.2f}")
        return results

    def _create_trade_from_position(self, pos: Dict, exit_price: float, exit_date: pd.Timestamp, reason: str) -> Trade:
        """Create Trade record from closed position"""
        self._trade_counter += 1
        pnl = 0.0
        if pos['side'] == 1:
            pnl = (exit_price - pos['entry_price']) * pos['quantity']
        else:
            pnl = (pos['entry_price'] - exit_price) * pos['quantity']
        # Deduct commission on exit
        exit_commission = exit_price * pos['quantity'] * self.commission
        pnl -= exit_commission

        pnl_pct = pnl / (pos['entry_price'] * pos['quantity'])

        return Trade(
            trade_id=self._trade_counter,
            symbol=pos['symbol'],
            entry_date=pos['entry_date'],
            exit_date=exit_date,
            side=pos['side'],
            quantity=pos['quantity'],
            entry_price=pos['entry_price'],
            exit_price=exit_price,
            stop_loss=pos.get('stop_loss'),
            take_profit=pos.get('take_profit'),
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason=reason,
            metadata={},
        )

    def _compute_metrics(self, portfolio: pd.DataFrame, trades: List[Trade]) -> Dict[str, float]:
        """Compute performance metrics"""
        equity = portfolio['equity']
        returns = equity.pct_change().dropna()

        # Basic returns
        total_return = (equity.iloc[-1] / equity.iloc[0]) - 1
        annual_factor = 252  # trading days per year
        years = len(returns) / annual_factor
        cagr = (1 + total_return) ** (1 / max(years, 1e-6)) - 1

        # Volatility
        annual_vol = returns.std() * np.sqrt(annual_factor)

        # Sharpe (assume 0% risk-free for now)
        sharpe = (returns.mean() / returns.std()) * np.sqrt(annual_factor) if returns.std() > 0 else 0.0

        # Sortino (downside deviation)
        downside = returns[returns < 0]
        downside_std = downside.std() if len(downside) > 0 else 0.0
        sortino = (returns.mean() / downside_std) * np.sqrt(annual_factor) if downside_std > 0 else 0.0

        # Max drawdown
        running_max = equity.expanding().max()
        drawdown = (equity - running_max) / running_max
        max_dd = drawdown.min()
        max_dd_duration = self._max_drawdown_duration(drawdown)

        # Calmar
        calmar = cagr / abs(max_dd) if max_dd != 0 else 0.0

        # Trade statistics
        if trades:
            win_trades = [t for t in trades if t.pnl > 0]
            lose_trades = [t for t in trades if t.pnl <= 0]
            win_rate = len(win_trades) / len(trades)
            avg_win = np.mean([t.pnl for t in win_trades]) if win_trades else 0.0
            avg_loss = np.mean([t.pnl for t in lose_trades]) if lose_trades else 0.0
            profit_factor = sum(t.pnl for t in win_trades) / abs(sum(t.pnl for t in lose_trades)) if lose_trades else np.inf
            expectancy = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))
            avg_holding_period = np.mean([(t.exit_date - t.entry_date).days for t in trades])
        else:
            win_rate = avg_win = avg_loss = profit_factor = expectancy = avg_holding_period = 0.0

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
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "avg_holding_period_days": avg_holding_period,
            "total_trades": len(trades),
        }

    @staticmethod
    def _max_drawdown_duration(drawdown: pd.Series) -> int:
        """Calculate maximum drawdown duration in days"""
        underwater = drawdown < 0
        if not underwater.any():
            return 0
        # Find longest consecutive underwater period
        underwater_series = underwater.astype(int)
        groups = (underwater_series != underwater_series.shift()).cumsum()
        durations = underwater_series.groupby(groups).sum()
        return int(durations.max()) if len(durations) > 0 else 0
