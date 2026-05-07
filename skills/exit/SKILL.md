# Exit Strategy Skill

A reusable component for evaluating and executing exit strategies (stop‑loss, take‑profit, trailing, time‑based) during backtesting and live trading.

## Purpose

Provides a consistent framework to:
- Compute dynamic stop‑loss and take‑profit levels based on price and volatility
- Simulate exits in historical backtests
- Execute live exits through the `ExitAgent`

## Included Strategies

- **Fixed %** – static stop and take distances (e.g., 1.5% / 3%)
- **ATR‑based** – stop = entry ± multiplier × ATR(14)
- **Partial Trail** – sell portion at target, trail remainder
- **Time Stop** – exit after N days if target not hit
- **Combined** – mix of the above with priority rules

## Usage

### In Backtests

```python
from skills.exit import ExitStrategy, ExitResult

# Prepare arrays: entry_price, high, low, close, atr
result: ExitResult = ExitStrategy.fixed_pct(entry_price, future_high, future_low, sl_pct=0.015, tp_pct=0.03)
result: ExitResult = ExitStrategy.atr(entry_price, entry_idx, high, low, close, atr, future_indices, mult_sl=2.0, mult_tp=4.0)
result: ExitResult = ExitStrategy.partial_trail(entry_price, entry_idx, high, low, close, atr, future_indices, partial_pct=0.02, trail_mult=1.5)
```

`ExitResult` contains:
- `exit_price`, `exit_day`, `reason`, `pnl_pct`

### In Live Trading

The `ExitAgent` already uses this skill. To add new strategies:
1. Add method to `ExitStrategy` class
2. Call from `ExitAgent._check_reactive_exits` when iterating positions

## Configuration

Parameters can be tuned via `config/finance.yaml` under `risk/`:
- `stop_loss_default_pct`
- `take_profit_default_pct`
- `atr_multiplier_sl`
- `atr_multiplier_tp`
- `partial_target_pct`
- `trail_stop_multiplier`

## Future Enhancements

- RSI/MACD based strategic exits
- Volatility‑adjusted position sizing linked to exits
- Machine‑learning exit predictor (train on historical outcomes)

---

Keep this skill updated as we refine exit methods. Backtest study outputs will guide parameter choices.
