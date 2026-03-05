# Phase 3 Action Plan: Portfolio & Position Management
**Week 6 (Days 1-5)**
**Status**: Planned
**Created**: 4 Mar 2026

---

## Phase 3 Overview

**Objective**: Implement portfolio tracking, position management, trade record keeping, and portfolio snapshot calculations.

**Inputs**: DECISION_MADE events from Phase 2 (decision JSON with symbol/quantity/SL/TP)
**Outputs**: Portfolio state, TRADE_OPENED / TRADE_CLOSED events, equity snapshots

**Key Components**:
- Portfolio state manager (cash, positions, equity tracking)
- Trade entry/exit recordkeeping
- Position aggregation (quantity, average cost)
- Equity snapshot history (for drawdown, Sharpe ratio calculations)

---

## Task Breakdown (5 Days)

### DAY 1: Portfolio Manager Core

#### Task 3.1: Portfolio Manager (`finance_service/portfolio/portfolio_manager.py`)
- Manage cash balance, positions dict, equity snapshots
- Methods: open_position(), close_position(), get_equity(), get_max_drawdown()
- Integration: Listen to DECISION_MADE, emit TRADE_OPENED/CLOSED
- Checklist:
  - [ ] File created (250 lines)
  - [ ] Position tracking working
  - [ ] Cash management
  - [ ] Event integration

#### Task 3.2: Trade Repository (`finance_service/storage/trades_repo.py`)
- SQLite CRUD for trades table
- Store: symbol, side, qty, price, executed_time, reason, SL, TP
- Checklist:
  - [ ] File created (150 lines)
  - [ ] Insert/query working
  - [ ] Indexes on symbol + timestamp

### DAY 2-3: Database & Persistence

#### Task 3.3: Update Database Schema
- Enhance trades table with SL/TP columns
- Add position_snapshots table for point-in-time tracking
- Checklist:
  - [ ] Schema updated
  - [ ] Migration script created
  - [ ] Indexes optimized

#### Task 3.4: Equity Calculator
- Calculate daily/hourly equity from positions + cash
- Track max drawdown over rolling windows
- Checklist:
  - [ ] File created (120 lines)
  - [ ] Equity calculation correct
  - [ ] Drawdown logic verified

### DAY 4: Integration & Tests

#### Task 3.5: Phase 2 Integration
- Subscribe to DECISION_MADE events
- Create trades in portfolio
- Emit TRADE_OPENED/TRADE_CLOSED
- Checklist:
  - [ ] Event listener active
  - [ ] Trade creation working
  - [ ] Events emitted

#### Task 3.6: Unit Tests
- Portfolio manager tests (10 tests)
- Trade repository tests (8 tests)
- Integration tests (3 tests)
- Checklist:
  - [ ] 21 tests created
  - [ ] All passing
  - [ ] Coverage >85%

### DAY 5: Documentation

#### Task 3.7: Completion Report
- Document portfolio structure
- Equity calculation examples
- Configuration for position sizing
- Checklist:
  - [ ] PHASE3_COMPLETION_REPORT.md created

---

## Success Criteria

- [ ] Portfolio state persisted and recoverable
- [ ] All trades recorded with full details
- [ ] Equity snapshots calculated correctly
- [ ] Event flow: DECISION_MADE → TRADE_OPENED → position tracked
- [ ] 21/21 tests passing
- [ ] Drawdown calculation accurate

---

## Dependencies

- ✅ Phase 2: DECISION_MADE events with symbol/qty/price
- ✅ EventBus: for subscribing/publishing
- ✅ SQLite: for trade persistence

