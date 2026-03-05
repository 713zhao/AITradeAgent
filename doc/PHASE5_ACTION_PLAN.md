# Phase 5 Action Plan: Approval Workflow & Manual Override
**Week 8 (Days 1-5)**
**Status**: Planned
**Created**: 4 Mar 2026

---

## Phase 5 Overview

**Objective**: Implement manual approval workflow for trades, allowing human intervention via Telegram bot.

**Inputs**: RISK_CHECK_PASSED events from Phase 4
**Outputs**: APPROVAL_REQUESTED → (APPROVAL_APPROVED / APPROVAL_REJECTED / APPROVAL_TIMEOUT) → execution

**Key Components**:
- Approval request queue (track pending approvals)
- Telegram bot integration (send approval requests, receive responses)
- Timeout handling (auto-reject if not approved within X seconds)
- Audit trail (log all approval decisions)

---

## Task Breakdown (5 Days)

### DAY 1: Approval System Core

#### Task 5.1: Approval Manager (`finance_service/approval/approval_manager.py`)
- Queue pending approvals (trading decisions awaiting human approval)
- Track approval requests with timeout
- Methods: request_approval(), approve(), reject(), check_timeouts()
- Checklist:
  - [ ] File created (200 lines)
  - [ ] Queue implemented
  - [ ] Timeout logic

#### Task 5.2: Telegram Bot Integration (`finance_service/integrations/telegram_bot.py`)
- Connect to existing Telegram bot
- Send approval requests: "Symbol AAPL, qty 100, price $150. Approve?"
- Receive inline keyboard responses (Approve/Reject)
- Checklist:
  - [ ] File created (250 lines)
  - [ ] Bot initialized
  - [ ] Message formatting

### DAY 2: Request/Response Flow

#### Task 5.3: Telegram Message Handler
- Parse approval responses from user
- Link response to pending approval request
- Update status in queue
- Checklist:
  - [ ] Handler created (120 lines)
  - [ ] Button callbacks working
  - [ ] State management

#### Task 5.4: Timeout Detection
- Run periodic check for expired approvals
- Auto-reject if > 5 min old without response
- Emit APPROVAL_TIMEOUT event
- Checklist:
  - [ ] File created (80 lines)
  - [ ] Scheduled task with APScheduler
  - [ ] Timeout event emission

### DAY 3: Audit & Logging

#### Task 5.5: Approval Audit Logger
- Log all approval requests and decisions
- Store in SQLite approval_log table
- Include timestamps, user decision, latency
- Checklist:
  - [ ] File created (100 lines)
  - [ ] Database table updated
  - [ ] Queries for approval history

#### Task 5.6: Approval Configuration
- Approval thresholds (require approval for trades >X risk %)
- Auto-approve low-risk trades
- Approval timeout duration
- Checklist:
  - [ ] Config section in finance.yaml
  - [ ] Threshold definitions

### DAY 4: Integration & Tests

#### Task 5.7: Phase Integration
- Subscribe to RISK_CHECK_PASSED
- Create approval request
- Send Telegram message
- Wait for response
- Emit APPROVAL_APPROVED / REJECTED / TIMEOUT
- Checklist:
  - [ ] Event listener active
  - [ ] Full workflow tested
  - [ ] Edge cases handled

#### Task 5.8: Unit Tests
- Approval manager tests (10 tests)
- Telegram integration tests (8 tests)
- Timeout tests (4 tests)
- Integration tests (4 tests)
- Checklist:
  - [ ] 26 tests created
  - [ ] All passing
  - [ ] Mock bot responses

### DAY 5: Documentation

#### Task 5.9: Completion Report
- Approval workflow diagrams
- Telegram bot setup instructions
- Approval request message examples
- Timeout handling details
- Checklist:
  - [ ] PHASE5_COMPLETION_REPORT.md created

---

## Success Criteria

- [ ] Approval requests queued and tracked
- [ ] Telegram messages sent correctly
- [ ] User responses processed accurately
- [ ] Timeouts auto-handled
- [ ] Audit trail comprehensive
- [ ] Event flow: RISK_CHECK_PASSED → APPROVAL_REQUESTED → (APPROVED/REJECTED/TIMEOUT)
- [ ] 26/26 tests passing

---

## Configuration Example

```yaml
approval:
  require_approval: true
  min_approval_amount: 1000        # Approval required if notional > $1000
  approval_timeout_sec: 300        # 5 min timeout
  auto_approve_low_risk: true      # Skip approval for <0.1% risk trades
  telegram_bot_token: "${TELEGRAM_TOKEN}"
  telegram_chat_id: "${TELEGRAM_CHAT_ID}"
```

---

## Dependencies

- ✅ Phase 4: Risk checks
- ✅ EventBus: for approval events
- ✅ Telegram: existing bot configured

