# Phase 8 Action Plan: Web UI & Monitoring Dashboard
**Week 11 (Days 1-5)**
**Status**: Planned
**Created**: 4 Mar 2026

---

## Phase 8 Overview

**Objective**: Build Streamlit web dashboard for real-time monitoring, portfolio visualization, and system control.

**Components**:
- Real-time portfolio dashboard (equity curve, positions, P&L)
- Risk dashboard (drawdown, exposure, concentration)
- Trade history viewer (searchable, filterable)
- Backtest report viewer
- System controls (pause/resume trading, reload config, test alerts)

---

## Task Breakdown (5 Days)

### DAY 1: Dashboard Framework

#### Task 8.1: Main Streamlit App (`finance_service/ui/dashboard.py`)
- Home page layout with key metrics
- Navigation sidebar to other pages
- Real-time data refresh (5-10sec intervals)
- Checklist:
  - [ ] File created (200 lines)
  - [ ] Layout designed
  - [ ] Data refresh working

#### Task 8.2: Portfolio Page (`finance_service/ui/pages/portfolio.py`)
- Display current positions (symbol, qty, avg cost, current price, P&L, %)
- Cash balance and total equity
- Equity curve (last 30 days)
- Asset allocation pie chart
- Checklist:
  - [ ] Page created (180 lines)
  - [ ] Tables and charts
  - [ ] Real-time updates

### DAY 2: Risk & Performance

#### Task 8.3: Risk Dashboard (`finance_service/ui/pages/risk.py`)
- Max drawdown chart (historical)
- Current drawdown % (with circle indicator)
- Sector concentration bar chart
- Correlation heatmap (current holdings)
- Risk alerts table
- Checklist:
  - [ ] Page created (200 lines)
  - [ ] Charts and heatmaps
  - [ ] Alert integration

#### Task 8.4: Performance Page (`finance_service/ui/pages/performance.py`)
- Daily returns chart
- Monthly returns heatmap
- Win rate gauge
- Profit factor gauge
- Trade P&L distribution histogram
- Checklist:
  - [ ] Page created (180 lines)
  - [ ] Charts created
  - [ ] Metrics displayed

### DAY 3: Data Viewers

#### Task 8.5: Trade History Page (`finance_service/ui/pages/trades.py`)
- Sortable table of all trades (date, symbol, qty, entry price, exit price, P&L, duration)
- Filters: date range, symbol, side (long/short)
- Export to CSV button
- Checklist:
  - [ ] Page created (180 lines)
  - [ ] Table with sorting/filtering
  - [ ] Export functionality

#### Task 8.6: Backtest Reports Page (`finance_service/ui/pages/backtest_reports.py`)
- List of historical backtest runs
- Display selected report metrics
- Compare two backtests side-by-side
- Download report PDF
- Checklist:
  - [ ] Page created (150 lines)
  - [ ] Report list and viewer
  - [ ] Comparison functionality

### DAY 4: System Control & Alerts

#### Task 8.7: System Control Page (`finance_service/ui/pages/system_control.py`)
- Pause/resume live trading toggle
- Reload configuration button
- Current system status (running/paused)
- Alert test button (send test Telegram message)
- View recent logs (last 100 entries)
- Checklist:
  - [ ] Page created (150 lines)
  - [ ] Control buttons
  - [ ] Status display
  - [ ] Log viewer

#### Task 8.8: API Integration
- Streamlit app queries Flask backend for data
- REST endpoints for dashboard data:
  - GET /api/dashboard/summary
  - GET /api/dashboard/positions
  - GET /api/dashboard/equity_history
  - POST /api/system/pause
  - POST /api/system/resume
- Checklist:
  - [ ] Flask endpoints created (8 endpoints)
  - [ ] Streamlit integration
  - [ ] Data formatting

### DAY 5: Documentation & Deployment

#### Task 8.9: Deployment & Documentation
- Streamlit requirements (streamlit, plotly, pandas)
- Docker container for Streamlit app
- Docker compose with Flask + Streamlit
- User guide for dashboard pages
- Checklist:
  - [ ] Dockerfile created
  - [ ] docker-compose.yml updated
  - [ ] README created

#### Task 8.10: Unit Tests
- API endpoint tests (10 tests)
- Data formatting tests (5 tests)
- Dashboard integration tests (4 tests)
- Checklist:
  - [ ] 19 tests created
  - [ ] All passing

---

## Success Criteria

- [ ] Dashboard loads and displays real-time data
- [ ] All 6 pages working (portfolio, risk, performance, trades, backtest, system)
- [ ] Charts render correctly
- [ ] Filters and sorting work
- [ ] System controls functional
- [ ] API endpoints responsive
- [ ] 19/19 tests passing
- [ ] Runnable with: `streamlit run finance_service/ui/dashboard.py`

---

## Dashboard Pages Summary

| Page | Purpose | Key Metrics |
|------|---------|-------------|
| Portfolio | Holdings & allocation | Equity, positions, allocation |
| Risk | Risk monitoring | Drawdown, concentration, alerts |
| Performance | Strategy P&L | Returns, Sharpe, win rate |
| Trades | Trade history | Entry/exit, duration, P&L |
| Backtest | Historical tests | Backtest results, comparison |
| System | Controls & logs | Pause/resume, reload, logs |

---

## Architecture

```
Streamlit UI (Port 8501)
    ↑
Flask REST API (Port 5000)
    ↑
SQLite Database
    ├─ Positions
    ├─ Trades
    ├─ Equity snapshots
    └─ Backtest results
```

---

## Dependencies

- ✅ Phase 3-7: All data and calculations
- Streamlit, Plotly, Pandas
- Flask REST endpoints

