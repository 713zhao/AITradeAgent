# ExitAgent

**Agent ID:** `exit_agent`
**File:** `finance_service/agents/exit_agent.py`
**Triggered by:** `EXIT_CHECK_TRIGGER` event (every 5 minutes, market hours only)

---

## What it does

ExitAgent runs two complementary checks on every open position:

| Mode | Name | How it works |
|---|---|---|
| 1 | Reactive exits | Compares `current_price` to `stop_loss_price` / `take_profit_price` stored on the Position at entry |
| 2 | Strategic degradation | Re-evaluates fresh indicators against the active strategy's exit rules via `StrategyAgent.rule_strategy` |

Both modes run on every 5-minute cycle (`perform_strategy_check=True` in the orchestrator call). Positions in closed markets are filtered out before checking.

---

## Data flow

```
SCHEDULER → EXIT_CHECK_TRIGGER
    ↓
Orchestrator.handle_exit_check()
    → PortfolioAgent.get_detailed_portfolio_state()   # get open positions
    → filter by market hours (US / HK)
    ↓
ExitAgent.run(positions, perform_strategy_check=True)
    ↓
    ├── _check_reactive_exits()        → reactive_exits list
    └── _check_strategic_degradation() → degraded_positions list
    ↓
AgentReport.payload {
    "reactive_exits":      [...],  # ← orchestrator reads this key
    "degraded_positions":  [...],
    "exits_count":         N,
    "degraded_count":      N
}
    ↓
Orchestrator publishes TRADE_EXECUTED for each reactive exit
Orchestrator publishes POSITION_DEGRADED for each degraded position
    ↓
PortfolioAgent removes position, HealthAgent sends Telegram notification
```

---

## Mode 1: Reactive Exits

Uses prices stored on the `Position` object at the time of the BUY trade. These are computed by `StrategyAgent` at entry and never change after that.

**ATR mode (default, recommended):**
```
stop_loss_price  = entry_price − (ATR × 2.0)   ← set by StrategyAgent.run()
take_profit_price = entry_price + (ATR × 4.0)
```

**Fallback** (when position has no stored stops, e.g. manual entry):
```
stop_loss_price  = entry_price × (1 − stop_loss_default_pct / 100)
take_profit_price = entry_price × (1 + take_profit_default_pct / 100)
```

The `Lo` column in the hourly Telegram portfolio report shows `stop_loss_price`. A `⚠` flag appears when `current_price < stop_loss_price`.

**Guard rule:** A position is skipped only if `current_price` or `quantity` is missing. `entry_price` is only required when no explicit stop/take prices are stored.

---

## Mode 2: Strategic Degradation

Re-fetches data, re-runs `AnalysisAgent`, then calls `strategy_agent.rule_strategy.evaluate_exit(indicators_snapshot)` to check whether the active strategy's exit rules have triggered on fresh data.

Exit rules come from the active strategy in `config/finance.yaml` (e.g. `sma50_trend_regime`). Typical rules: price below SMA20, RSI above 75, regime score below 30.

> **Known limitation:** Mode 2 requires the `AnalysisAgent` to return a proper `IndicatorsSnapshot` object in `payload["indicators_snapshot"]`. If the payload contains a plain dict (as in some test mocks), the mode silently no-ops because `dict` has no `.indicators` attribute.

---

## Connection to StrategyAgent

StrategyAgent serves ExitAgent in two ways:

**At entry time (BUY flow):**
```
StrategyAgent.run()
  → evaluates entry rules
  → computes stop_loss_price = current_price − (ATR × 2)
  → returns TradeProposal(stop_loss_price=...)
      ↓
PortfolioAgent stores stop_loss_price on Position object
      ↓
ExitAgent reads it every 5 min for Mode 1 reactive check
```

**While holding (Mode 2):**
```
ExitAgent._check_strategic_degradation()
  → calls strategy_agent.rule_strategy.evaluate_exit(indicators_snapshot)
  → same exit rules from finance.yaml, evaluated against fresh live indicators
```

---

## Exit Strategy Comparison

Backtest on 20 tech/AI symbols, 2023–2024:

| Strategy | Avg P&L/trade | Win Rate | Avg hold (days) | Notes |
|---|---|---|---|---|
| Fixed % (1.5/3%) | +0.43% | 42.9% | 2.6 | Exits too fast, leaves money on table |
| **ATR (2×/4×)** | **+2.75%** | **48.3%** | **16.9** | **Recommended** |
| Partial Trail (2%, 1.5×ATR) | +15.06% | 33.8% | 11.0 | High variance — loses 2 in 3 trades |

ATR is the recommended mode. Partial trail's average is skewed by rare large wins; it loses more often than it wins.

---

## Configuration

```yaml
# config/finance.yaml — risk section
risk:
  exit_strategy: "atr"            # "atr" | "fixed_pct" | "partial_trail"
  stop_loss_default_pct: 10.0     # fallback only — whole-number percent (10.0 = 10%)
  take_profit_default_pct: 20.0   # fallback only — whole-number percent
  atr_multiplier_sl: 2.0          # ATR stop multiplier (used by StrategyAgent at entry)
  atr_multiplier_tp: 4.0          # ATR take multiplier
  partial_target_pct: 0.02        # for partial_trail mode
  trail_stop_multiplier: 1.5      # for partial_trail mode
```

Restart after config changes:
```bash
pkill -f run_finance_service.py && sleep 2 && ./start.sh
tail -f logs/finance_service_restart.log | grep -i "exit\|stop\|profit"
```

---

## ATR Example

Buy **MRVL** at **$150.00**, ATR = **$8.00**:

| Level | Calculation | Price |
|---|---|---|
| Stop loss | $150 − (2.0 × $8) | **$134.00** |
| Take profit | $150 + (4.0 × $8) | **$182.00** |

Stops are **fixed at entry** — they do not trail. Dynamic trailing is a planned future enhancement.

---

## Currency Handling

Stop/take-profit comparisons are always in native currency:
- HK stocks (`.HK`): `avg_cost` and `current_price` both in HKD — comparison stays in HKD
- US stocks: both in USD

FX conversion (`Position._fx`, ~7.78 HKD/USD) applies only to USD-normalised P&L and position sizing, not to stop-price comparisons.

---

## Tests

`tests/test_exit_agent.py` — **23 tests, all passing**

```bash
source venv/bin/activate
python -m pytest tests/test_exit_agent.py -v
```

---

## Bug History

| Date | Bug | Fix |
|---|---|---|
| 2026-03-31 | `IndicatorsSnapshot` lacked `.get()` method → crash in strategic re-analysis | Added `.get()` method |
| 2026-05-28 | `Position.to_dict()` did not include `stop_loss_price`/`take_profit_price` → ExitAgent always saw `None` | Added fields to `to_dict()` |
| 2026-05-28 | Fallback percentages not divided by 100 → computed stop was negative, never triggered | Divide by 100 in ExitAgent |
| 2026-06-03 | Orchestrator read `"exits"` key; ExitAgent returns `"reactive_exits"` → exits detected but never executed | Fixed key in `handle_exit_check` |
| 2026-06-03 | Guard required `entry_price` even when `stop_loss_price` was explicitly set → positions silently skipped | Guard now only requires `entry_price` when no explicit stops are stored |

---

## Future Enhancements

- **Trailing stops:** Track peak price since entry, raise `stop_loss_price` as position profits
- **True partial exit:** Sell 50% at partial target, move stop to breakeven, trail remainder
- **Time stop:** Exit if position held > N days without progress
- **Dynamic ATR:** Periodically recompute ATR and tighten stops on profitable positions
