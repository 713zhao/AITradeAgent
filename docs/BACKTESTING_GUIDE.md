# Backtesting Guide

**Version:** 1.0  
**Last Updated:** 2026-04-01  
**Status:** Planned (Phase 2)

---

## Introduction

The Backtesting Engine allows you to validate trading strategies on historical data before risking real capital. It supports vectorized backtests, walk-forward analysis, parameter optimization, and comprehensive performance reporting.

---

## Quick Start

### Single Backtest

```bash
python3 run_backtest.py \
  --strategy rule_based \
  --start 2023-01-01 \
  --end 2024-12-31 \
  --symbols AAPL,MSFT,NVDA,GOOGL,AMZN \
  --initial-capital 100000
```

Output:

```
[INFO] Loading data for 5 symbols...
[INFO] Running backtest from 2023-01-01 to 2024-12-31 (504 trading days)
[INFO] Signals generated: 142
[INFO] Trades executed: 138 (win rate: 58.0%)
[INFO] Final portfolio value: $127,450.32 (CAGR: 12.8%)
[INFO] Sharpe ratio: 1.42, Max drawdown: -8.5%
[INFO] Report saved to: storage/backtest_results/backtest_20260401_103052.pdf
```

### Walk-Forward Analysis

```bash
python3 run_backtest.py \
  --wfa \
  --window 504 \  # 2 years training window
  --step 63 \    # 3 months reoptimization step
  --symbols SPY \
  --optimize-params config/optimization_grid.yaml
```

Performs rolling-window optimization and out-of-sample testing.

---

## Architecture

```
finance_service/backtesting/
├── engine.py           # Core vectorized backtest runner
├── walk_forward.py     # Walk-forward analysis orchestrator
├── metrics.py          # Performance metrics calculations
├── benchmarks.py       # Benchmark comparison (SPY, buy-and-hold)
├── reporter.py         # PDF/HTML report generation
├── slippage.py         # Slippage and commission models
└── data_loader.py      # Historical data caching and loading
```

---

## Backtest Engine (`engine.py`)

### Core Class: `BacktestEngine`

```python
from finance_service.backtesting.engine import BacktestEngine
from finance_service.backtesting.data_loader import load_data

# Load data
data = load_data(symbols=["AAPL", "MSFT"], start="2023-01-01", end="2024-12-31")

# Initialize engine
engine = BacktestEngine(
    initial_capital=100000,
    commission=0.0005,  # 5 bps per trade
    slippage=0.0002,    # 2 bps market impact
    max_position_size_pct=10.0,  # 10% per position
)

# Run backtest
results = engine.run(data, strategy)

# Access results
portfolio_history = results.portfolio_history  # DataFrame indexed by date
trades = results.trades                         # List of Trade objects
metrics = results.metrics                       # dict of performance metrics
```

### Vectorized Signal Generation

Strategies implement `generate_signals(data: DataFrame) -> DataFrame`:

```python
def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
    """
    Vectorized: compute signals for all timestamps at once.
    Returns DataFrame with columns:
    - signal: -1 (sell), 0 (hold), 1 (buy)
    - confidence: 0.0-1.0
    - stop_loss: price level
    - take_profit: price level
    """
    df = data.copy()
    df['signal'] = 0
    df['confidence'] = 0.0

    # Example: RSI oversold bounce
    rsi = ta.rsi(df['close'], length=14)
    df.loc[rsi < 30, 'signal'] = 1
    df.loc[rsi < 30, 'confidence'] = 0.7

    # SMA crossover
    sma_fast = ta.sma(df['close'], length=20)
    sma_slow = ta.sma(df['close'], length=50)
    df.loc[(sma_fast > sma_slow) & (sma_fast.shift(1) <= sma_slow.shift(1)), 'signal'] = 1
    df.loc[(sma_fast < sma_slow) & (sma_fast.shift(1) >= sma_slow.shift(1)), 'signal'] = -1

    return df[['signal', 'confidence', 'stop_loss', 'take_profit']]
```

### Position Sizing

The engine respects risk limits:

- Max position size (percentage of portfolio)
- Stop-loss-based sizing: if stop distance = 5%, and risk budget = 1% of portfolio, then position size = 20% of portfolio

---

## Metrics (`metrics.py`)

Calculated automatically:

### Return Metrics
- **Total Return**: (final_value / initial_capital) - 1
- **CAGR**: Compound Annual Growth Rate
- **Annualized Volatility**: Std dev of daily returns × √252

### Risk-Adjusted
- **Sharpe Ratio**: (mean daily return - rf) / std_daily × √252
- **Sortino Ratio**: (mean return - rf) / std_down_deviation
- **Calmar Ratio**: CAGR / max_drawdown

### Drawdown
- **Max Drawdown**: Largest peak-to-trough decline
- **Max Drawdown Duration**: Days to recover
- **Current Drawdown**: From peak to today

### Trade Statistics
- **Total Trades**
- **Win Rate**: % of trades with gross profit > 0
- **Avg Win / Avg Loss**: Mean profit of winning vs losing trades
- **Profit Factor**: Gross profits / gross losses
- **Expectancy**: (win_rate × avg_win) - (loss_rate × avg_loss)
- **Holding Period**: Mean days per trade

---

## Reporting (`reporter.py`)

Generates PDF reports with:

1. Equity curve with underwater drawdown subplot
2. Monthly returns heatmap (calendar view)
3. Rolling Sharpe ratio (6-month)
4. Benchmark comparison (SPY, buy-and-hold)
5. Top 10 trades table
6. Strategy performance by regime (trending vs range)
7. Correlation matrix of returns (if portfolio of symbols)

```bash
python3 run_backtest.py ... --report-format pdf
# Also supports: html (interactive with plotly)
```

---

## Walk-Forward Analysis (`walk_forward.py`)

### What is WFA?

Repeatedly train/optimize strategy on an expanding window, then test on the next out-of-sample period. Measures robustness.

### Usage

```python
from finance_service.backtesting.walk_forward import WalkForwardAnalyzer

analyzer = WalkForwardAnalyzer(
    data=data,
    strategy=MyStrategy(),
    train_window=504,   # 2 years (504 trading days)
    test_window=63,     # 3 months out-of-sample
    step=63,            # Step forward by 3 months each iteration
    optimization_params=param_grid,  # Grid search per training window
)

results = analyzer.run()

# Aggregated OOS performance
print(f"OOS Sharpe: {results.aggregate_metrics['sharpe_ratio']:.2f}")
print(f"WFA consistency: {results.win_rate_in_oos:.1%} of periods profitable")
```

### Output Files

- `storage/backtest_results/wfa_summary.json` — aggregated metrics
- `storage/backtest_results/wfa_rollinger_metrics.csv` — metrics per rolling window
- Plot: rolling Sharpe, rolling max drawdown

---

## Optimization (`optimize_parameters.py`)

### Grid Search

Define a YAML grid:

```yaml
# config/optimization_grid.yaml
strategy:
  rsi_oversold: [20, 25, 30, 35]
  rsi_overbought: [70, 75, 80]
  sma_fast: [10, 20, 30]
  sma_slow: [50, 100, 200]
  confidence_threshold: [0.7, 0.8, 0.9]
```

Run:

```bash
python3 run_backtest.py --optimize --param-file config/optimization_grid.yaml --metric sharpe_ratio
```

Tests all combinations (3×4×3×3×3 = 324 runs) and returns top 10 parameter sets.

### Bayesian Optimization (Optuna)

For continuous parameters or expensive evaluations:

```python
import optuna

def objective(trial):
    params = {
        "rsi_oversold": trial.suggest_int(15, 35),
        "sma_fast": trial.suggest_categorical([10, 15, 20, 25, 30]),
        "confidence_threshold": trial.suggest_float(0.65, 0.95),
    }
    results = engine.run(data, MyStrategy(**params))
    return results.metrics['sharpe_ratio']

study = optuna.create_study(direction='maximize')
study.optimize(objective, n_trials=100)
print(study.best_params)
```

---

## Data Caching

Historical data is cached in `storage/backtest_cache/` as parquet files:

- Key: `{symbol}_{interval}_{start}_{end}.parquet`
- TTL: 7 days (configurable)
- Automatic refresh on cache miss

Data sources: yfinance (default), OpenBB.

---

## Integration with Rules

Your existing `RuleStrategy` can be backtested with minimal wrapping:

```python
# finance_service/backtesting/rule_backtest_adapter.py

class RuleStrategyBacktest(BacktestableStrategy):
    def __init__(self, rules_config: List[Dict], position_sizer=None):
        self.rules_strategy = RuleStrategy(rules_config)
        self.position_sizer = position_sizer or EqualRiskPositionSizer()

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        # Apply rules to each row (can be vectorized if rules allow)
        signals = []
        for i in range(len(data)):
            row = data.iloc[i]
            indicators = IndicatorsSnapshot.from_row(row)  # adapt
            decision = self.rules_strategy.evaluate(indicators)
            signals.append({
                'signal': 1 if decision['decision']=='BUY' else -1 if decision['decision']=='SELL' else 0,
                'confidence': decision['confidence'],
                'stop_loss': decision.get('stop_loss'),
                'take_profit': decision.get('take_profit'),
            })
        return pd.DataFrame(signals, index=data.index)
```

---

## Best Practices

1. **Out-of-Sample Testing:** Never evaluate strategy on same period used for optimization. Use WFA.
2. **Look-Ahead Bias:** Ensure indicators use only past data (e.g., `rolling().mean().shift(1)`).
3. **Survivorship Bias:** Include delisted symbols if testing broad universe. Hard to source; use survivorship-bias-free datasets if available.
4. **Slippage & Commission:** Always model realistic transaction costs (5-10 bps for large caps, higher for small caps).
5. **Benchmark:** Compare against SPY or QQQ, not just absolute returns.
6. **Parameter Stability:** Prefer strategies with stable parameters across time; avoid overfitting to recent regime.
7. **Regime Analysis:** Report performance separately for trending vs range-bound periods.

---

## Command-Line Reference

```bash
python3 run_backtest.py [OPTIONS]

Options:
  --strategy STRATEGY          rule_based, ml_model, custom (default: rule_based)
  --start DATE                 Backtest start date (YYYY-MM-DD)
  --end DATE                   Backtest end date (YYYY-MM-DD)
  --symbols SYMBOLS            Comma-separated list (e.g., AAPL,MSFT)
  --initial-capital AMOUNT     Starting cash (default: 100000)
  --commission BPS             Commission in bps (1bp = 0.01%) (default: 5)
  --slippage BPS               Slippage in bps (default: 2)
  --max-position-pct PCT       Max position size % (default: 10)
  --report-format FORMAT       pdf, html (default: pdf)
  --output-dir PATH            Directory for reports (default: storage/backtest_results)
  --optimize                   Run grid search optimization
  --param-file PATH            YAML file with parameter grid
  --metric METRIC              Metric to maximize during optimization (sharpe, sortino, calmar, total_return)
  --wfa                        Enable walk-forward analysis
  --window DAYS                Training window for WFA (default: 504)
  --step DAYS                  Step size for WFA (default: 63)
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| No trades generated | Signal threshold too high | Lower `confidence_threshold` or inspect signals with `--debug` |
| Too many trades (churning) | Rules too sensitive | Add confirmation requirement (e.g., volume above average) |
| Equity curve looks jagged | No position sizing smoothing | Use `EqualRiskPositionSizer` instead of fixed qty |
| `NaN` in metrics | Insufficient data after start | Extend `start` earlier or reduce indicator lookback |

---

## Future Enhancements

- Monte Carlo simulation (bootstrapped returns)
- Transaction cost analysis (market impact model)
- Portfolio backtesting with multi-symbol rebalancing
- Live paper trading replay (replay historical bars to validate engine)
- Optimization constraints (max turnover, max trades per day)

---

## References

- [Backtrader](https://www.backtrader.com/) — alternative backtesting framework
- [VectorBT](https://github.com/polakowo/vectorbt) — vectorized, GPU-accelerated
- [QuantConnect Lean](https://github.com/QuantConnect/Lean) — institutional-grade

---

**Next Steps:** Implement `engine.py` with vectorized execution, then integrate with rule strategies and produce your first PDF report.
