# Phase 7 Action Plan: Backtesting & Performance Analysis
**Week 10 (Days 1-5)**
**Status**: Planned
**Created**: 4 Mar 2026

---

## Phase 7 Overview

**Objective**: Implement historical backtesting engine to validate strategy performance over past data.

**Inputs**: Historical OHLCV data (Years 1-3 of data)
**Outputs**: Backtest report with metrics (Sharpe, Max DD, Win Rate, Profit Factor)

**Key Components**:
- Backtest runner (replay historical data, trigger signals)
- Portfolio simulator (track P&L through time)
- Metrics calculator (Sharpe ratio, Sortino, max drawdown, win rate)
- Trade analyzer (open/close times, holding periods, P&L per trade)

---

## Task Breakdown (5 Days)

### DAY 1: Backtest Engine Core

#### Task 7.1: Backtest Runner (`finance_service/backtest/backtest_engine.py`)
- Load historical OHLCV data
- Iterate through dates sequentially
- Call indicator calculator for each date
- Call strategy evaluator
- Call portfolio simulator (execute trades)
- Checklist:
  - [ ] File created (300 lines)
  - [ ] Date iteration loop
  - [ ] Component orchestration

#### Task 7.2: Portfolio Simulator (`finance_service/backtest/portfolio_simulator.py`)
- Track cash, positions, equity through time
- Execute trades at historical prices
- Calculate P&L continuously
- Methods: open_position(), close_position(), get_equity(), get_drawdown()
- Checklist:
  - [ ] File created (200 lines)
  - [ ] Trade execution logic
  - [ ] Equity calculations

### DAY 2: Metrics & Analysis

#### Task 7.3: Metrics Calculator (`finance_service/backtest/metrics.py`)
- Calculate key metrics from backtest results:
  - Total Return %
  - Annual Return %
  - Sharpe Ratio
  - Sortino Ratio
  - Max Drawdown %
  - Win Rate %
  - Profit Factor
  - Average Trade Duration
  - Consecutive Wins/Losses
- Checklist:
  - [ ] File created (250 lines)
  - [ ] Formula verification
  - [ ] Edge case handling

#### Task 7.4: Trade Analysis
- Analyze each trade individually
- Calculate holding period, P&L, P&L %
- Group by symbol, entry signal, time of day
- Checklist:
  - [ ] File created (150 lines)
  - [ ] Trade statistics
  - [ ] Grouping queries

### DAY 3: Report Generation

#### Task 7.5: Backtest Report Generator (`finance_service/backtest/report_generator.py`)
- Produce HTML/PDF report with:
  - Summary metrics table
  - Equity curve chart
  - Drawdown chart
  - Monthly returns heatmap
  - Win/loss distribution
  - Trade list table
- Checklist:
  - [ ] File created (200 lines)
  - [ ] Report HTML generation
  - [ ] Chart generation (matplotlib/plotly)

#### Task 7.6: Configuration
- Backtest date range
- Initial capital
- Symbols to backtest
- Strategy parameters to test (parameter sweep)
- Checklist:
  - [ ] Config section in finance.yaml
  - [ ] Parameter sweep definitions

### DAY 4: Integration & Tests

#### Task 7.7: Backtest CLI
- Command: `python -m finance_service.backtest.run --start 2022-01-01 --end 2024-12-31 --symbols AAPL,TSLA,NVDA`
- Outputs: Report to `backtest_reports/` directory
- Logs results to database
- Checklist:
  - [ ] CLI script created
  - [ ] Argument parsing
  - [ ] Report output

#### Task 7.8: Unit Tests
- Backtest engine tests (8 tests)
- Portfolio simulator tests (10 tests)
- Metrics calculation tests (12 tests)
- Report generation tests (4 tests)
- End-to-end backtest tests (3 tests)
- Checklist:
  - [ ] 37 tests created
  - [ ] All passing
  - [ ] Coverage >85%

### DAY 5: Documentation

#### Task 7.9: Completion Report
- Backtest methodology
- Assumptions and limitations
- Sample backtest report walkthrough
- How to run backtests
- Checklist:
  - [ ] PHASE7_COMPLETION_REPORT.md created

---

## Success Criteria

- [ ] Backtest engine runs without errors
- [ ] Portfolio simulation accurate
- [ ] All metrics calculated correctly
- [ ] Reports generated (HTML + charts)
- [ ] Parameter sweeps working
- [ ] Historical data integrity verified
- [ ] 37/37 tests passing

---

## Configuration Example

```yaml
backtest:
  start_date: "2022-01-01"
  end_date: "2024-12-31"
  initial_capital: 100000
  symbols: ["AAPL", "TSLA", "NVDA", "MSFT", "GOOGL"]
  parameter_sweeps:
    rsi_period: [12, 14, 16]
    sma_period: [20, 50, 100]
```

---

## Dependencies

- ✅ Phase 1: Historical data fetching
- ✅ Phase 2: Indicator calculations & strategies
- ✅ Phase 3: Portfolio tracking

