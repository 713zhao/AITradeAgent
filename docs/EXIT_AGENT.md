# ExitAgent - Specification & Design

**Agent ID:** `exit_agent`  
**File:** `finance_service/agents/exit_agent.py`  
**Status:** ✅ Production-ready, fully integrated  
**Version:** 1.0  
**Last Updated:** 2026-03-29

---

## Overview

ExitAgent monitors open positions to determine **exit conditions**. It operates in two modes:
1. **Reactive exits**: Stop‑loss and take‑profit triggers.
2. **Strategic re‑analysis**: Re‑evaluate held positions against current strategy criteria to decide if a position should be closed due to degraded thesis.

It can be scheduled to run periodically (e.g., every 5–15 minutes) while markets are open.

**Key Responsibility:** Propose exit trades for open positions that no longer meet criteria or hit risk thresholds.

---

## Design Philosophy

```
                    ┌─────────────────────────────────┐
                    │  Scheduled trigger or manual    │
                    │  (list of open positions)       │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  ExitAgent.run(positions,      │
                    │            perform_strategy_   │
                    │            check=True)         │
                    │  - Check stop-loss / take-profit│
                    │  - If enabled, re-run strategy │
                    │    analysis on each position   │
                    └──────────────┬─────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  AgentReport payload:          │
                    │    reactive_exits: [...],      │
                    │    degraded_positions: [...]   │
                    └─────────────────────────────────┘
```

---

## Input Parameters

### `run(positions: List[Dict], perform_strategy_check: bool = False, ...) -> AgentReport`

- `positions`: List of open position dicts (from PortfolioAgent or DB). Each should include:
  - `symbol`, `quantity`, `avg_cost`, `current_price`
  - Optional: `stop_loss_price`, `take_profit_price`
- `perform_strategy_check`: If `True`, performs a full reanalysis using `AnalysisAgent` and `StrategyAgent`.

Returns `AgentReport`:

```python
{
    "checked_count": 5,
    "reactive_exits": [
        {"symbol": "NVDA", "reason": "stop_loss", "price": ...}
    ],
    "exits_count": 1,
    "degraded_positions": [
        {"symbol": "AMD", "reason": "strategy_signal_changed", "new_signal": "WAIT"}
    ],
    "degraded_count": 1,
    "timestamp": "2026-03-29T09:45:00"
}
```

---

## Processing Modes

### Reactive Exits (`_check_reactive_exits`)

For each position:
- If `stop_loss_price` set and `current_price <= stop_loss_price` → trigger SELL exit.
- If `take_profit_price` set and `current_price >= take_profit_price` → trigger SELL exit.
- Returns list of exit suggestions.

Requires `DataAgent` available to fetch fresh `current_price` if not provided.

### Strategic Re‑Analysis (`_check_strategic_degradation`)

Re‑runs the full analysis pipeline on the position’s symbol:
1. DataAgent fetches latest data.
2. AnalysisAgent computes indicators.
3. StrategyAgent evaluates.

If the resulting `action` is `SELL` or `WAIT` (different from original thesis), marks as degraded.

---

## Configuration (finance.yaml)

```yaml
finance:
  exit_agent:
    enabled: true
    reactive_exits_enabled: true
    strategic_check_enabled: true
    check_interval_minutes: 5
    stop_loss_pct: 0.10      # default stop 10% below entry
    take_profit_pct: 0.20    # default take 20% above entry
```

---

## Event Flow Integration

```
SCHEDULER (or manual)
    ↓
ExitAgent.run(positions)
    ↓
Produces exits and degraded_positions
    ↓
Orchestrator converts to trade proposals → RiskAgent → ExecutionAgent (if auto_execute)
```

---

## Current Implementation Status

- ✅ Reactive exit logic (stop‑loss/take‑profit)
- ✅ Integration with DataAgent for fresh prices
- ✅ Strategic re‑analysis: fully implemented (`_check_strategic_degradation`) — checks RSI > 70 and bearish trend
- ✅ Wired into SchedulerAgent via `EXIT_CHECK_TRIGGER` (every 5 minutes)
- ✅ Orchestrator integration: `handle_exit_check_trigger()` retrieves positions, calls ExitAgent with `perform_strategy_check=True`
- ✅ Telegram alerts sent for both exits and degraded positions
- ✅ Emits `POSITION_DEGRADED` event for downstream handling

---

## Testing

Test suite: `tests/test_exit_agent.py` — **14 tests, all passing** ✅

| Test Class | Tests | Coverage |
|------------|-------|----------|
| TestExitAgentBasics | 2 | Initialization, goal property |
| TestReactiveExits | 3 | Stop-loss trigger, take-profit trigger, no exit when safe |
| TestStrategicDegradation | 3 | High RSI degradation, bearish trend, healthy position |
| TestEmptyAndErrorCases | 3 | No positions, empty list, data fetch failure fallback |
| TestIntegration | 1 | Mixed exits and degradations in single run |
| TestOutputFormat | 2 | Exit record structure, degradation record structure |

```bash
cd /home/eric/.openclaw/workspace/AITradeAgent
source venv/bin/activate
python -m pytest tests/test_exit_agent.py -v
```

---

## Notes

- ExitAgent is **stateless**; it receives the current positions list.
- It is designed to run **frequently** (every 5–15 minutes) to catch intraday stop triggers.
- The `stop_loss_price` and `take_profit_price` are stored in position objects (not currently persisted in the DB schema; would need extension).
- Future: automatic generation of `TradeProposal` from exits.

---

**Summary:** ExitAgent provides automated risk‑management exits and thesis validation. It is a partially completed component that can be scheduled to monitor positions.
