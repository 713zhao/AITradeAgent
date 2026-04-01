# Backtesting Engine Package

Vectorized backtesting framework for AITradeAgent strategies.

## Architecture

```
finance_service/backtesting/
├── __init__.py           # Exports: BacktestEngine, BacktestResults, ...
├── engine.py             # Core: BacktestEngine class (vectorized execution)
├── data_loader.py        # Historical data loading with caching
├── metrics.py            # Performance metrics calculations
├── walk_forward.py       # Walk-forward analysis orchestrator
├── benchmarks.py         # Benchmark strategies (SPY, buy-and-hold)
├── reporter.py           # PDF/HTML report generation
├── slippage.py           # Slippage and commission models
├── strategies/           # Strategy adapters
│   ├── __init__.py
│   ├── base.py           # BacktestableStrategy abstract base
│   └── rule_adapter.py   # RuleStrategy → BacktestableStrategy wrapper
└── plots.py              # Chart generation (equity curve, drawdown, heatmap)
```

## Usage

```python
from finance_service.backtesting import BacktestEngine, load_data
from finance_service.backtesting.strategies import RuleStrategyBacktest

# Load historical data
data = load_data(symbols=["AAPL", "MSFT"], start="2023-01-01", end="2024-12-31")

# Initialize strategy
rules_config = [...]  # from config/rules.yaml
strategy = RuleStrategyBacktest(rules_config)

# Run backtest
engine = BacktestEngine(
    initial_capital=100000,
    commission=0.0005,  # 5 bps
    slippage=0.0002,
    max_position_size_pct=10.0,
)
results = engine.run(data, strategy)

# Access results
print(f"Sharpe: {results.metrics['sharpe_ratio']:.2f}")
print(f"Max DD: {results.metrics['max_drawdown']:.2%}")
print(f"Total Return: {results.metrics['total_return']:.2%}")

# Generate report
from finance_service.backtesting.reporter import generate_pdf_report
generate_pdf_report(results, output_path="storage/backtest_results/report.pdf")
```

## CLI

```bash
python3 run_backtest.py --strategy rule_based --start 2023-01-01 --end 2024-12-31 --symbols AAPL,MSFT
```

---

See individual module docstrings for details.
