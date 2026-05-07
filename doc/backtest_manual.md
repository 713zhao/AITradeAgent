# AITradeAgent Backtest User Manual

The `AITradeAgent` system provides a fully independent backtest environment used to simulate trading strategies against historical data. This document outlines how backtests operate, how to run them automatically or manually, and how to view the results.

## Overview
Backtests run in an isolated environment and store data solely in `finance_service/storage/backtest.sqlite`. Running a backtest does **not** affect your live trading capital, live orders, or active positions (`portfolio.sqlite`).

The backtest results are used by the **Hourly Portfolio Report** to display the `🔍 Assessment` and `🔧 Recommended Actions` section. This provides a baseline projection of how your active strategy is expected to perform in current market conditions.

---

## 1. Automated Execution (Cron)
A background script has been set up to automatically run a 1-year trailing backtest for all symbols defined in your `finance.yaml` universe.

* **Schedule:** Every Sunday at Midnight (`0 0 * * 0`).
* **Script Location:** `scripts/run_weekly_backtest.sh`
* **Log Output:** `logs/weekly_backtest.log`

This guarantees that the strategic baseline displayed in your Hourly Report is regularly updated to reflect shifting market regimes (e.g., transitioning from a bull market to a sideways market).

---

## 2. Manual Execution
You can manually run a backtest at any time using the `backtest.py` tool.

**Usage:**
```bash
source venv/bin/activate
python -m finance_service.tools.backtest \
    --symbols AAPL MSFT NVDA \
    --start-date 2025-01-01 \
    --end-date 2026-05-01 \
    --strategy sma50_trend_regime
```

**Parameters:**
* `--symbols`: A space-separated list of ticker symbols to include in the simulation.
* `--start-date` / `--end-date`: The date range formatted as `YYYY-MM-DD`.
* `--strategy`: The specific strategy from `config/finance.yaml` you want to simulate (defaults to the first strategy if omitted).
* `--capital`: (Optional) Initial starting cash (defaults to $100,000).

---

## 3. Viewing Results
While the Hourly Report automatically scrapes the latest assessment metrics, you can use built-in terminal scripts to view deeper statistics about the backtest runs.

**View Latest Backtest Summary:**
```bash
source venv/bin/activate
python scripts/get_latest_backtest.py
```
*Outputs the total return, CAGR, Max Drawdown, Sharpe ratio, and total executed trades of the most recent backtest.*

**View Database Structure/Raw Data:**
```bash
source venv/bin/activate
python scripts/show_finance_backtest.py
# OR
python scripts/describe_backtest.py
```
