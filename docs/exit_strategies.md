# Exit Strategies Analysis & Configuration

## Study Results

Backtest comparing three exit strategies on 20 tech/AI symbols over 2023‑2024:

| Strategy                                    | Avg P&L per trade | Win Rate | Avg Holding (days) | Max Win |
|---------------------------------------------|-------------------|----------|--------------------|---------|
| Fixed % (1.5/3%)                            | +0.43%            | 42.9%    | 2.64               | +3.0%   |
| ATR‑based (2×/4×)                           | +2.75%            | 48.3%    | 16.88              | +37.7%  |
| Partial Trail (2% partial, 1.5×ATR trail)   | +15.06%           | 33.8%    | 11.02              | +561%   |

**Key findings:**
- Fixed % yields smallest gains and quick exits; not suitable for trend‑following.
- ATR‑based provides the best balance: solid average profit, moderate win rate, holds through normal volatility.
- Partial trail produces highest average but very low win rate and high variance; requires strong risk tolerance.

## Recommended Configuration

Set in `config/finance.yaml` under `risk:`:

```yaml
risk:
  exit_strategy: "atr"            # "atr" (recommended) or "partial_trail"
  atr_multiplier_sl: 2.0          # ATR stop multiplier (applied by StrategyAgent at entry)
  atr_multiplier_tp: 4.0          # ATR take multiplier (applied by StrategyAgent at entry)
  partial_target_pct: 0.02        # 2% profit target for partial_trail
  trail_stop_multiplier: 1.5      # ATR multiplier for trail in partial_trail
  stop_loss_default_pct: 10.0     # fallback only — used when ATR stop was not stored at entry
  take_profit_default_pct: 20.0   # fallback only — used when ATR take was not stored at entry
```

- **ATR mode** (default): Uses `stop_loss_price` and `take_profit_price` values calculated by
  `StrategyAgent` at entry (2×ATR stop, 4×ATR take). These are stored on the `Position` object
  and checked by `ExitAgent` every 5 minutes during market hours.
- **Partial Trail mode (simplified):** Uses ATR stop from position and an additional partial
  take‑profit at `entry × (1 + partial_target_pct)`. Full position exits when price is reached
  (true 50% partial + trail is a future enhancement).
- **Fallback (any mode):** If a position has no stored `stop_loss_price` / `take_profit_price`
  (e.g. positions entered before fix or migrated from older versions), `ExitAgent` uses
  `stop_loss_default_pct` and `take_profit_default_pct` as percentage thresholds.
  Values are stored in config as whole percentages (e.g. `10.0` = 10%) and divided by 100
  in code — **do not store as decimals**.

## Currency Handling

Exit comparisons are always in native currency:
- HK stocks (`.HK`): `avg_cost` and `current_price` are both in HKD → comparison is in HKD ✓
- US stocks: both in USD → comparison is in USD ✓

FX conversion (`Position._fx` using ~7.78 HKD/USD) is applied only for USD-normalised P&L
reporting and position sizing, **not** for stop/take-profit price comparisons.

## Implementation Notes

- `StrategyAgent` computes `stop_loss_price` and `take_profit_price` based on ATR and includes
  them in `TradeProposal`.
- `PortfolioAgent.handle_trade_executed` persists these values to both `Trade` and `Position`.
- `Position.to_dict()` now includes `stop_loss_price` and `take_profit_price` (bug fixed 2026-05-28).
- `ExitAgent._check_reactive_exits()` reads the configured strategy and applies the rules:
  - For `atr`: compares `current_price` against stored `stop_loss_price` / `take_profit_price`.
    Falls back to `stop_loss_default_pct` / `take_profit_default_pct` if not stored.
  - For `partial_trail`: compares against stored stop and computed partial target.
- Market-hours filtering: HK positions are only evaluated when HK market is open (09:30–16:00 HKT);
  US positions only when US market is open (09:30–16:00 ET).

## Bug Fixes (2026-05-28)

Two bugs prevented exits from ever firing:

1. **`Position.to_dict()` missing stop/take fields** — `stop_loss_price` and `take_profit_price`
   were stored on the `Position` object but not serialised, so `ExitAgent` always saw `None` and
   always fell through to the fallback.

2. **Fallback percentages not divided by 100** — Config stores `1.5` meaning 1.5%, but code used
   the raw value as a multiplier, giving `stop = entry × (1 − 1.5) = negative`. Neither stop nor
   take-profit could ever trigger. Fixed by dividing config value by 100 in `ExitAgent`.

## Future Enhancements

- **True partial exit**: sell 50% at partial target, move stop to breakeven, trail remainder.
- **Dynamic ATR stops**: periodically recompute ATR and tighten stops as price moves favourably.
- **Momentum‑based exits**: exit when RSI > 70 and MACD histogram turns negative.
- **Time stop**: exit if position held > N days without significant progress.

## How to Change Strategy

Edit `config/finance.yaml`:

```yaml
risk:
  exit_strategy: "atr"          # or "partial_trail" or "fixed_pct"
  stop_loss_default_pct: 10.0   # whole-number percent; 10.0 = 10%
  take_profit_default_pct: 20.0
```

Then restart:

```bash
pkill -f run_finance_service.py && sleep 2 && ./start.sh
```

Monitor:

```bash
tail -f logs/finance_service_restart.log | grep -i "exit\|stop\|profit"
```

---

**Created:** 2026‑04‑04 | **Updated:** 2026‑05-28
**Skill:** `skills/exit/` — reusable exit logic for backtests and live trading.
