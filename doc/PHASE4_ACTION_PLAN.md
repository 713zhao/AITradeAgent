# Phase 4 Action Plan: Risk Management & Position Limits
**Week 7 (Days 1-5)**
**Status**: Planned
**Created**: 4 Mar 2026

---

## Phase 4 Overview

**Objective**: Implement real-time risk monitoring, position sizing limits, drawdown alerts, and correlation checks.

**Inputs**: TRADE_OPENED, PORTFOLIO_UPDATED from Phase 3
**Outputs**: RISK_CHECK_PASSED / RISK_CHECK_FAILED events, alerts

**Key Components**:
- Max position size per symbol (% of portfolio)
- Max sector exposure (cluster check)
- Max account leverage (total notional exposure)
- Drawdown circuit breaker (pause trading if >X% loss)
- Correlation filter (don't hold highly correlated symbols)
- Daily loss limit (stop trading after -X% day)

---

## Task Breakdown (5 Days)

### DAY 1: Risk Engine Core

#### Task 4.1: Risk Manager (`finance_service/risk/risk_manager.py`)
- Load risk config from finance.yaml
- Check position size limits
- Check sector concentration
- Check max drawdown
- Methods: validate_trade(), check_daily_loss(), get_risk_status()
- Checklist:
  - [ ] File created (280 lines)
  - [ ] All risk checks implemented
  - [ ] Integration with EventBus

#### Task 4.2: Risk Configuration (finance.yaml update)
- max_position_size_pct: per symbol cap
- max_sector_exposure_pct: per industry
- max_account_leverage: total notional / equity
- max_drawdown_pct: circuit breaker threshold
- daily_loss_limit_pct: stop trading threshold
- Checklist:
  - [ ] Config section added
  - [ ] Documented with examples

### DAY 2: Limit Enforcement

#### Task 4.3: Position Size Validator
- Calculate position size needed for SL
- Cap to max % of portfolio
- Round to tradeable lot size
- Checklist:
  - [ ] File created (100 lines)
  - [ ] Position sizing correct
  - [ ] Loss per trade limited to max_risk_pct

#### Task 4.4: Correlation Checker
- Track symbol cross-correlations (from price data)
- Block trades if adding correlated position
- Checklist:
  - [ ] File created (120 lines)
  - [ ] Correlation calculation
  - [ ] Block logic

### DAY 3: Circuit Breakers

#### Task 4.5: Drawdown Monitor
- Track running max equity
- Calculate current drawdown %
- Emit RISK_ALERT if threshold exceeded
- Checklist:
  - [ ] File created (100 lines)
  - [ ] Real-time drawdown calculation
  - [ ] Alert emission

#### Task 4.6: Daily Loss Tracker
- Track P&L for current day
- Stop new trades if loss > limit
- Reset at market open
- Checklist:
  - [ ] File created (80 lines)
  - [ ] Daily P&L calculation
  - [ ] Reset logic

### DAY 4: Integration & Tests

#### Task 4.7: Phase Integration
- Subscribe to TRADE_OPENED events
- Run risk checks before allowing trade
- Emit RISK_CHECK_PASSED / RISK_CHECK_FAILED
- Checklist:
  - [ ] Event listener active
  - [ ] Risk checks gating trades
  - [ ] Events emitted

#### Task 4.8: Unit Tests
- Risk manager tests (12 tests)
- Position sizing tests (6 tests)
- Correlation tests (4 tests)
- Integration tests (5 tests)
- Checklist:
  - [ ] 27 tests created
  - [ ] All passing
  - [ ] Coverage >85%

### DAY 5: Documentation

#### Task 4.9: Completion Report
- Risk management architecture
- Example thresholds and rationale
- Alert escalation procedures
- Checklist:
  - [ ] PHASE4_COMPLETION_REPORT.md created

---

## Success Criteria

- [ ] Position size capped per config
- [ ] Sector concentration monitored
- [ ] Drawdown circuit breaker working
- [ ] Daily loss limit enforced
- [ ] Correlation filter active
- [ ] Event flow: DECISION_MADE → RISK_CHECK → (PASSED/FAILED)
- [ ] 27/27 tests passing

---

## Configuration Example

```yaml
risk:
  max_position_size_pct: 5          # Max 5% per symbol
  max_sector_exposure_pct: 15       # Max 15% per sector
  max_account_leverage: 2.0         # 2x exposure
  max_drawdown_pct: 20              # Stop trading at -20%
  daily_loss_limit_pct: 5           # Stop trading if -5% daily
  min_correlation_distance: 0.7     # Block if corr > 0.7
```

---

## Dependencies

- ✅ Phase 1: Equity calculations
- ✅ Phase 3: Portfolio state
- ✅ EventBus: for risk events

