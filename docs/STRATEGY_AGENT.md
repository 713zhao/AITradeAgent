# StrategyAgent - Specification & Design

**Agent ID:** `strategy_agent`  
**File:** `finance_service/agents/strategy_agent.py`  
**Status:** 🏗️ Strategy Implementations Vary  
**Version:** 2.0  
**Last Updated:** 2026-03-29

---

## Overview

StrategyAgent converts technical indicators into actionable **BUY trade proposals**. It evaluates entry rules from the active strategy, computes ATR-based stop/take-profit levels, and sizes the position.

**Key Responsibility:** Produce BUY `TradeProposal` objects with `stop_loss_price` attached. SELL decisions are handled exclusively by `ExitAgent` — StrategyAgent's `run()` method never generates SELL proposals.

**Secondary role:** StrategyAgent hosts `RuleStrategy` (loaded from `finance.yaml`), which contains both entry and exit rules. `ExitAgent` borrows `strategy_agent.rule_strategy` to re-evaluate held positions against exit rules during strategic degradation checks (Mode 2). See `docs/EXIT_AGENT.md` for the full connection.

---

## Design Philosophy

```
                    ┌─────────────────────────────────┐
                    │  ANALYSIS_COMPLETE event         │
                    │  payload: IndicatorsSnapshot     │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  StrategyAgent.run(indicators_snapshot) │
                    │  - Evaluate each registered    │
                    │    strategy                    │
                    │  - Combine proposals (ensemble│
                    │    or top-1)                   │
                    │  - Compute position size       │
                    └──────────────┬─────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  STRATEGY_COMPLETE event        │
                    │  payload: [TradeProposal, ...] │
                    └─────────────────────────────────┘
```

---

## Input Parameters

### `run(indicators_snapshot: IndicatorsSnapshot, symbol: str) -> AgentReport`

- `indicators_snapshot`: `IndicatorsSnapshot` object (from AnalysisAgent)
- `symbol`: symbol string (for context)

Returns `AgentReport` with `payload`:
```python
{
    "symbol": "NVDA",
    "proposals": [
        {
            "strategy": "sma20_trend",
            "action": "BUY",
            "confidence": 0.95,
            "price": 150.25,
            "quantity": 10,
            "type": "market",
            "reason": "Price above SMA20"
        },
        ...
    ],
    "best_proposal": {...},  # highest confidence
    "ensemble_signal": "BUY"  # if ensemble method used
}
```

---

## Strategy Implementations

### Rule-Based (Current)
- **sma20_trend**: Simple trend following. BUY if `price > sma_20`, SELL if `price < sma_20`, else WAIT. Very simple but high CAGR in backtest (47.4%).
- **sma50_trend_regime**: Uses SMA50 with regime filter (regime_score > 0.5 for long).
- Other strategies exist (value_quality_news, momentum_lenient) but underperform.

### Ensemble (Planned)
- Weighted vote among N strategies based on backtest Sharpe.
- Or pick top-1 performer over recent out-of-sample period.

---

## Position Sizing

Simple position sizing formula applied to the chosen proposal:
```
quantity = floor( (portfolio_equity * max_position_size_pct) / price )
```
- `max_position_size_pct` from config (default 1.0% of equity)
- Always integer shares (floor)

---

## Configuration (finance.yaml)

```yaml
finance:
  strategy_agent:
    mode: "ensemble"  # or "top1"
    enabled_strategies: ["sma20_trend", "sma50_trend_regime"]
    max_position_size_pct: 0.01   # 1% of portfolio
    confidence_threshold: 0.9     # below this, require approval or skip
    cooldown_period_minutes: 60   # min time between trades in same symbol
    regime_filter_enabled: true
```

---

## Event Flow Integration

```
ANALYSIS_COMPLETE
    ↓
StrategyAgent.run(indicators_snapshot, symbol)
    ↓
STRATEGY_COMPLETE published
    ↓
Orchestrator forwards to RiskAgent
```

---

## Methods

- `_evaluate_strategy(strategy_name, indicators_snapshot) -> Dict` – evaluate a single strategy
- `_combine_proposals(proposals: List[Dict]) -> Dict` – ensemble or top-1 selection
- `_calculate_position_size(price: float, portfolio_equity: float) -> int` – sizing rule

---

## Error Handling

- Missing indicators cause strategy to skip or return WAIT with low confidence.
- Exceptions are caught and reported in `AgentReport(status="error")`.

---

## Testing

Test suite: `tests/test_strategy_agent.py` covers:
- sma20_trend basic cases (above, below, equal)
- sma50_trend_regime with regime variations
- Position sizing calculations
- Ensemble selection logic

Run:
```bash
cd /home/eric/.openclaw/workspace/AITradeAgent
source venv/bin/activate
python -m pytest tests/test_strategy_agent.py -v
```

---

## Notes

- StrategyAgent is designed to be pluggable: new strategies can be added as classes implementing `evaluate(indicators_snapshot) -> proposal`.
- Backtest results are used to rank strategies; the orchestrator may adjust `enabled_strategies` based on performance.
- Confidence reflects strategy certainty (e.g., distance from threshold, regime alignment).

---

**Summary:** StrategyAgent is the decision engine. It turns indicators into concrete BUY/SELL proposals with size and confidence, ready for risk validation.
