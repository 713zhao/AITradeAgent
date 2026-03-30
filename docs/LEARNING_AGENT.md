# LearningAgent - Specification & Design

**Agent ID:** `learning_agent`  
**File:** `finance_service/agents/learning_agent.py`  
**Status:** 🚧 Placeholder / Future Feature  
**Version:** 1.0  
**Last Updated:** 2026-03-29

---

## Overview

LearningAgent monitors trade outcomes and overall portfolio performance to identify improvement opportunities. It is intended to analyze win rates, profit factors, drawdown causes, and potentially adapt strategy parameters or flag underperforming strategies. Currently a **stub** with placeholder logic.

**Key Responsibility:** Extract insights from executed trades and feed them back into strategy optimization.

---

## Design Philosophy

```
                    ┌─────────────────────────────────┐
                    │  EXECUTION_COMPLETE event        │
                    │  payload: execution_result       │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  LearningAgent.run(execution_   │
                    │                    report)      │
                    │  - Record trade outcome        │
                    │  - Update metrics (win rate,   │
                    │    avg win/loss, max drawdown) │
                    │  - Detect regime changes       │
                    └──────────────┬─────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  LEARNING_COMPLETE event        │
                    │  payload: {metrics, insights,  │
                    │            suggestions}         │
                    └─────────────────────────────────┘
```

---

## Input Parameters

### `run(execution_report: AgentReport) -> Optional[AgentReport]`

- `execution_report`: `AgentReport` from ExecutionAgent with `execution_result` in payload.

Returns `AgentReport` with:
```python
{
    "learning_output": {
        "trade_symbol": "NVDA",
        "trade_action": "BUY",
        "trade_status": "FILLED",
        "performance_metrics": {
            "pnl": 0.0,  # realized P&L when position closed
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0
        },
        "lessons_learned": "Trade executed successfully (mock)"
    }
}
```

---

## Current Implementation

- Skeleton class with `run()` method.
- Extracts `execution_details` from payload.
- Publishes `LEARNING_COMPLETE` event with static mock data.
- Real learning logic is TODO:
  - Store trade in a performance database.
  - Compute rolling metrics (win rate, average win/loss, expectancy).
  - Compare realized vs. expected confidence.
  - Suggest parameter tweaks (e.g., adjust RSI threshold if too many false signals).
  - Possibly inform `StrategyAgent` to weight strategies differently.

---

## Configuration (YAML)

Not implemented yet. Possible future config:

```yaml
finance:
  learning_agent:
    enabled: true
    metrics_window: 100  # trades to consider
    retention_days: 365
    auto_adjust_strategy_weights: true
```

---

## Event Flow Integration

```
TRADE_EXECUTED
    ↓ (orchestrator routes)
LearningAgent.run(execution_report)
    ↓
Publish LEARNING_COMPLETE
    ↓
Orchestrator could adjust strategy selection or alert user
```

---

## Testing

Not yet implemented. Planned tests: `tests/test_learning_agent.py` would:
- Simulate sequence of trades
- Verify metrics calculation
- Check suggestions plausibility

---

## Notes

- LearningAgent is **optional** in the current pipeline; it does not affect trade execution.
- It could be extended to include machine‑learning models for regime detection or error analysis.
- Interaction with `StrategyAgent` could be a closed‑loop optimization: learning agent proposes parameter updates, orchestrator applies them after validation.

---

**Summary:** LearningAgent is a future enhancement for adaptive improvement. Presently a no‑op stub that logs trade outcomes for later development.
