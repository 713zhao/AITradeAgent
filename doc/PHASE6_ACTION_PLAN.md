# Phase 6 Action Plan: Trade Execution Engine
**Week 9 (Days 1-5)**
**Status**: Planned
**Created**: 4 Mar 2026

---

## Phase 6 Overview

**Objective**: Implement paper trading execution engine (no real trades, simulated fills).

**Inputs**: APPROVAL_APPROVED events from Phase 5
**Outputs**: EXECUTION_STARTED → EXECUTION_COMPLETE events, filled trades

**Key Components**:
- Order manager (track orders, fills, rejections)
- Simulated execution (fill at market price, add slippage)
- Order state machine (pending → filled → closed)
- Execution reporting (ExecutionReport with fill price, time, slippage)

---

## Task Breakdown (5 Days)

### DAY 1: Order & Execution Core

#### Task 6.1: Order Manager (`finance_service/execution/order_manager.py`)
- Create order from decision
- Track order state (pending, filled, rejected, closed)
- Methods: create_order(), fill_order(), get_fill_price(), mark_closed()
- Checklist:
  - [ ] File created (250 lines)
  - [ ] Order states defined
  - [ ] State transitions

#### Task 6.2: execution Engine (`finance_service/execution/execution_engine.py`)
- Subscribe to APPROVAL_APPROVED
- Create order immediately
- Simulate fill at close price + slippage
- Generate ExecutionReport
- Checklist:
  - [ ] File created (200 lines)
  - [ ] Simulated fill logic
  - [ ] Slippage calculation

### DAY 2: Fill Simulation & Reporting

#### Task 6.3: Slippage Simulator
-Add slippage to execution price:
  - Entry: +0.01% to +0.05% (adverse)
  - Exit: -0.01% to -0.05% (adverse)
- Methods: calculate_slippage(), get_fill_price()
- Checklist:
  - [ ] File created (100 lines)
  - [ ] Realistic slippage values
  - [ ] Direction-aware (long vs short)

#### Task 6.4: Execution Reporter
- Generate ExecutionReport with:
  - Order ID, symbol, qty, entry price, fill price, slippage
  - Timestamp, execution time
  - Reason and signals that triggered
- Store in SQLite
- Checklist:
  - [ ] File created (120 lines)
  - [ ] Report data complete
  - [ ] Database persistence

### DAY 3: Order State Management

#### Task 6.5: Order State Machine
- Pending → Filled → Closed (at exit)
- Pending → Rejected (if conditions not met)
- Track status transitions with timestamps
- Checklist:
  - [ ] File created (80 lines)
  - [ ] State diagram implemented
  - [ ] Transition validation

#### Task 6.6: Order Tracking Database
- Update SQLite orders table
- Add: state, fill_price, fill_time, slippage, execution_report
- Indexes on symbolic, state, timestamp
- Checklist:
  - [ ] Schema updated
  - [ ] Indexes created
  - [ ] Queries tested

### DAY 4: Integration & Tests

#### Task 6.7: Phase Integration
- Subscribe to APPROVAL_APPROVED
- Create and fill order
- Update portfolio (via Phase 3)
- Emit EXECUTION_STARTED → EXECUTION_COMPLETE
- Checklist:
  - [ ] Event listener active
  - [ ] Full workflow tested
  - [ ] Position updates correct

#### Task 6.8: Unit Tests
- Order manager tests (10 tests)
- Execution engine tests (8 tests)
- Slippage tests (5 tests)
- State machine tests (4 tests)
- Integration tests (4 tests)
- Checklist:
  - [ ] 31 tests created
  - [ ] All passing
  - [ ] Coverage >85%

### DAY 5: Documentation

#### Task 6.9: Completion Report
- Paper trading justification
- Slippage model details
- ExecutionReport examples
- Order tracking examples
- Checklist:
  - [ ] PHASE6_COMPLETION_REPORT.md created

---

## Success Criteria

- [ ] Orders created and tracked
- [ ] Fills simulated realistically with slippage
- [ ] ExecutionReports generated and stored
- [ ] Portfolio updated on fill
- [ ] Order complete workflow: APPROVAL_APPROVED → EXECUTION_COMPLETE
- [ ] 31/31 tests passing

---

## Configuration Example

```yaml
execution:
  mode: "paper"  # Never change this without careful review
  fill_strategy: "at_close"  # at_close, at_open, or mid
  slippage_bps: 3            # 3 basis points slippage
  slippage_randomness: 0.5   # 0-50% variation
  execution_delay_ms: 100    # Simulated execution delay
```

---

## Dependencies

- ✅ Phase 5: Approval workflow
- ✅ Phase 3: Portfolio state
- ✅ EventBus: for execution events

