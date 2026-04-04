# Exit Strategies Analysis & Configuration

## Study Results

Backtest comparing three exit strategies on 20 tech/AI symbols over 2023‑2024:

| Strategy          | Avg P&L per trade | Win Rate | Avg Holding (days) | Max Win |
|-------------------|-------------------|----------|--------------------|---------|
| Fixed % (1.5/3%)  | +0.43%            | 42.9%    | 2.64               | +3.0%   |
| ATR‑based (2×/4×) | +2.75%            | 48.3%    | 16.88              | +37.7%  |
| Partial Trail (2% partial, 1.5×ATR trail) | +15.06% | 33.8% | 11.02 | +561%   |

**Key findings:**
- Fixed % yields smallest gains and quick exits; not suitable for trend‑following.
- ATR‑based provides the best balance: solid average profit, moderate win rate, holds through normal volatility.
- Partial trail produces highest average but very low win rate and high variance; requires strong risk tolerance.

## Recommended Configuration

Set in `config/finance.yaml` under `risk:`:

```yaml
risk:
  exit_strategy: "atr"            # "atr" (recommended) or "partial_trail"
  atr_multiplier_sl: 2.0          # ATR stop multiplier
  atr_multiplier_tp: 4.0          # ATR take multiplier (used by atr strategy)
  partial_target_pct: 0.02        # 2% profit target for partial_trail
  trail_stop_multiplier: 1.5     # ATR multiplier for trail in partial_trail (currently not trailing live)
  stop_loss_default_pct: 1.5       # used only if exit_strategy == "fixed_pct"
  take_profit_default_pct: 3.0     # used only if exit_strategy == "fixed_pct"
```

- **ATR mode** (default): Uses stop‑loss and take‑profit values calculated by `StrategyAgent` (2×ATR stop, 4×ATR take) on each trade. These are stored in the position and checked by `ExitAgent`.
- **Partial Trail mode (simplified):** Uses ATR stop from position and an additional partial take‑profit at `entry × (1 + partial_target_pct)`. When that price is reached, the position is sold in full (simplified; true 50% partial + trail is a future enhancement).

## Implementation Notes

- `StrategyAgent` already computes `stop_loss_price` and `take_profit_price` based on ATR and includes them in `TradeProposal`.
- `PortfolioAgent.handle_trade_executed` now persists these values to both `Trade` and `Position` objects.
- `ExitAgent._check_reactive_exits()` reads the configured strategy and applies the corresponding rules:
  - For `atr`: compares `current_price` against stored `stop_loss_price` and `take_profit_price`.
  - For `partial_trail`: compares `current_price` against stored stop and computed partial target.
- Positions are updated in real‑time by `MarketScannerAgent.refresh_watchlist_prices` during market hours.

## Future Enhancements

- **True partial exit**: sell 50% at partial target, move stop to breakeven, trail remainder.
- **Dynamic ATR stops**: periodically recompute ATR and tighten stops as price moves favorably.
- **Momentum‑based exits**: exit when RSI > 70 and MACD histogram turns negative.
- **Time stop**: exit if position held > N days without significant progress.

## How to Change Strategy

Edit `config/finance.yaml`:

```bash
# Change to partial_trail
risk:
  exit_strategy: "partial_trail"
  partial_target_pct: 0.02
```

Then restart the finance service for changes to take effect:

```bash
pkill -f run_finance_service.py
nohup ./venv/bin/python run_finance_service.py > finance_service.out 2>&1 &
```

Monitor logs to confirm:

```bash
tail -f finance_service.out | grep ExitAgent
```

---

**Created:** 2026‑04‑04  
**Skill:** `skills/exit/` – reusable exit logic for backtests and live trading.
