# RiskAgent - Specification & Design

**Agent ID:** `risk_agent`  
**File:** `finance_service/agents/risk_agent.py`  
**Status:** ✅ Production-ready, actively used  
**Version:** 2.0  
**Last Updated:** 2026-03-29

---

## Overview

RiskAgent validates trade proposals against portfolio risk limits and policy. It is the **gatekeeper** that prevents oversized positions, exceeding drawdown limits, or violating concentration rules. It may also require manual approval for low‑confidence or high‑risk proposals.

**Key Responsibility:** Ensure every trade proposal complies with configured risk constraints and return a final decision.

---

## Design Philosophy

```
                    ┌─────────────────────────────────┐
                    │  STRATEGY_COMPLETE event         │
                    │  payload: [TradeProposal]        │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  RiskAgent.run(proposal)        │
                    │  - Load current portfolio       │
                    │  - Check position size limit    │
                    │  - Check sector exposure        │
                    │  - Check drawdown, daily loss   │
                    │  - Validate confidence threshold│
                    │  - Apply cooldown               │
                    └──────────────┬─────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  RISK_COMPLETE event            │
                    │  payload: {decision,            │
                    │            requires_approval,   │
                    │            position_size}       │
                    └─────────────────────────────────┘
```

---

## Input Parameters

### `run(trade_proposal: TradeProposal, portfolio_state: Optional[Dict] = None) -> AgentReport`

- `trade_proposal`: `TradeProposal` object from StrategyAgent.
- `portfolio_state`: Optional current portfolio metrics (equity, open positions, drawdown, etc.). If `None`, agent fetches from PortfolioAgent.

Returns `AgentReport` with `payload`:

```python
{
    "decision": "APPROVED",           # or "REJECTED", "REQUIRES_APPROVAL"
    "position_size": 10,              # final validated quantity (may be reduced)
    "reasons": ["position_limit", "confidence"],
    "requires_approval": False,
    "portfolio_snapshot": {...}
}
```

---

## Risk Checks

| Check Type | Description | Config |
|------------|-------------|--------|
| `position_size` | Single position as % of portfolio | `max_position_size_pct` |
| `sector_exposure` | Max exposure per sector (not implemented) | `max_sector_exposure_pct` |
| `portfolio_leverage` | Total long+short leverage | `max_portfolio_leverage` |
| `drawdown_limit` | Maximum allowed drawdown from peak | `max_drawdown_pct` |
| `daily_loss_limit` | Max daily P&L loss | `max_daily_loss_pct` |
| `correlation_check` | Avoid adding highly correlated positions (planned) | – |
| `cooldown` | Minimum time between same-symbol trades | `cooldown_period_minutes` |
| `confidence_threshold` | Proposals below threshold need approval | `confidence_threshold` |

Checks are evaluated in order; first violation can reject or require approval based on severity.

---

## Decision Logic

1. **Fetch portfolio snapshot** (equity, positions, drawdown, daily P&L).
2. **Compute proposed position value** and check `position_size` limit.
3. **Check drawdown** against `drawdown_critical_pct` (hard block) and `drawdown_warning_pct` (may trigger approval).
4. **Check daily loss** against `daily_loss_limit` (block).
5. **Check confidence**: if `proposal.confidence < confidence_threshold`, mark `requires_approval`.
6. **Check cooldown**: if last trade for this symbol was too recent, reject or require approval.
7. **Return**:
   - `decision: "APPROVED"` with possibly reduced `position_size`.
   - `decision: "REQUIRES_APPROVAL"` if confidence low or other soft limits.
   - `decision: "REJECTED"` for hard violations.

---

## Configuration (finance.yaml)

```yaml
finance:
  risk:
    enabled: true
    max_position_size_pct: 0.01        # 1% of portfolio per position
    max_sector_exposure_pct: 0.20      # 20% max per sector
    max_portfolio_leverage: 1.0        # no leverage
    max_drawdown_pct: 20.0             # critical drawdown limit
    max_daily_loss_pct: 5.0            # daily loss limit
    confidence_threshold: 0.90         # below this requires approval
    cooldown_period_minutes: 60        # same-symbol cooldown
    approval_required_until: "18:00"   # time window for manual approvals
```

---

## Approval Flow

If `requires_approval=True`, the proposal is:
- Not auto-executed.
- Sent to the `ApprovalGate` agent (separate tool) which may solicit human approval via Telegram.
- Upon approval, the proposal is re-routed to ExecutionAgent.

Currently `auto_execute=false` in config, so all proposals require manual approval regardless.

---

## Event Flow Integration

```
STRATEGY_COMPLETE
    ↓
RiskAgent.run(trade_proposal)
    ↓
RISK_COMPLETE published
    ↓
If decision=APPROVED and auto_execute=true:
    └─ ExecutionAgent.run(decision)
    └─ TRADE_EXECUTED → PortfolioAgent → HealthAgent → Telegram
If decision=REQUIRES_APPROVAL:
    └─ ApprovalGate handles
```

---

## Testing

Test suite: `tests/test_risk_agent.py` covers:
- Position size limit enforcement
- Drawdown blocking
- Confidence thresholds
- Cooldown logic
- Portfolio snapshot handling

Run:
```bash
cd /home/eric/.openclaw/workspace/AITradeAgent
source venv/bin/activate
python -m pytest tests/test_risk_agent.py -v
```

---

## Notes

- RiskAgent is designed to be **stateless** regarding past decisions except for cooldown timestamps (which are retrieved from portfolio/trade history).
- The `PortfolioAgent` is the source of truth for current positions and cash; RiskAgent queries it for metrics.
- Hard limits (`position_size`, `drawdown`, `daily_loss`) return `REJECTED`; soft limits (`confidence`, `cooldown`) may return `REQUIRES_APPROVAL`.
- The agent is used in both paper and live trading modes.

---

**Summary:** RiskAgent is the safety net. It ensures every trade proposal respects portfolio-level risk parameters before execution.
