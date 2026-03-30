# ExecutionAgent - Specification & Design

**Agent ID:** `execution_agent`  
**File:** `finance_service/agents/execution_agent.py`  
**Status:** ✅ Production-ready (paper trading)  
**Version:** 2.0  
**Last Updated:** 2026-03-29

---

## Overview

ExecutionAgent converts an **approved trade proposal** into an executed trade. In paper trading mode, it simulates the fill; in live mode, it would route to a broker API (e.g., Alpaca, Interactive Brokers). It is responsible for creating a unique `trade_id`, capturing fill details, and emitting a `TRADE_EXECUTED` event.

**Key Responsibility:** Fulfill trades and publish execution results.

---

## Design Philosophy

```
                    ┌─────────────────────────────────┐
                    │  RISK_COMPLETE (APPROVED) event  │
                    │  payload: {decision, proposal,   │
                    │            position_size}        │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  ExecutionAgent.run(decision)   │
                    │  - Build order                 │
                    │  - Submit to broker (or mock)  │
                    │  - Receive fill                │
                    │  - Build execution_result      │
                    └──────────────┬─────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  TRADE_EXECUTED event           │
                    │  payload: execution_result      │
                    └─────────────────────────────────┘
```

---

## Input Parameters

### `run(approval_report: AgentReport) -> AgentReport`

- `approval_report`: An `AgentReport` from RiskAgent whose `payload` includes:
  - `trade_proposals`: list of original proposals (usually single)
  - `risk_assessments`: list of corresponding risk results
  - `all_passed`: bool
  - `any_approval_required`: bool

Returns an `AgentReport` with:
- `payload` containing `execution_result`:

```python
{
    "trade_id": "trade_NVDA_1743262800.123456",
    "symbol": "NVDA",
    "action": "BUY",
    "quantity": 10,
    "filled_price": 150.27,
    "commission": 0.0,
    "status": "FILLED",
    "order_id": "SIM_001",
    "timestamp": "2026-03-29T09:15:00"
}
```

---

## Execution Modes

| Mode | Behavior |
|------|----------|
| **Paper** (current) | Immediately returns a FILLED execution result with `filled_price` = proposal `target_price`. No network call. |
| **Live (planned)** | Would submit order via broker SDK, poll for fill, handle partials, errors, cancellations. |

---

## Process Flow

1. Extract the first `trade_proposal` from `approval_report.payload`.
2. Validate required fields (`symbol`, `action`, `quantity`, `price`).
3. Generate unique `trade_id` using symbol + timestamp.
4. Build `execution_result` dict.
5. Publish `TRADE_EXECUTED` event with `Event(data=asdict(AgentReport(...)))`.
6. Return `AgentReport(status="success", payload={execution_result})`.

If any error occurs:
- Return `AgentReport(status="error", message=error_string)`.

---

## Configuration (finance.yaml)

```yaml
finance:
  execution_agent:
    mode: "paper"  # or "live"
    paper_commission_per_share: 0.0
    paper_latency_ms: 0
    live:
      broker: "alpaca"  # or "ibkr", "tradier"
      api_key: ""
      secret_key: ""
      paper_trading: true  # use broker's paper endpoint
```

(Not yet implemented; placeholder in `__init__`.)

---

## Error Handling

- Missing proposal fields → `AgentReport(status="error")`.
- Broker errors (in live mode) would be caught and returned as error; Orchestrator logs and continues.

---

## Event Flow Integration

```
RISK_COMPLETE (decision=APPROVED)
    ↓
ExecutionAgent.run(approval_report)
    ↓
Publish TRADE_EXECUTED event
    ↓
PortfolioAgent updates positions
HealthAgent sends Telegram notification (if enabled)
```

---

## Testing

Test suite: `tests/test_execution_agent.py` tests the paper execution path.

Run:
```bash
cd /home/eric/.openclaw/workspace/AITradeAgent
source venv/bin/activate
python -m pytest tests/test_execution_agent.py -v
```

---

## Notes

- ExecutionAgent is **stateless**; it does not track open orders.
- The `order_id` is currently a simple mock; a real implementation would store broker order IDs.
- Commission handling: configurable per-share or per-order; currently zero.
- PortfolioAgent is the sole writer to the trade repository.

---

**Summary:** ExecutionAgent is the final step before portfolio update. In paper mode it's trivial; the design accommodates live trading by isolating broker logic in `YfinanceProvider`‑style provider classes.
