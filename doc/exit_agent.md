# AITradeAgent Exit Strategy & Trailing Stops

This document explains the mathematical exit logic and safety nets managed by the `ExitAgent`. The system utilizes a multi-tiered approach designed around the philosophy: *"Cut losers short, let winners run."*

## 1. The Exit Rules (Strategic Exits)
When a stock is acquired, the agent monitors it against the rules defined in your active strategy (`config/finance.yaml` -> `sma50_trend_regime`).

**The current rules dictate a stock must be sold if:**
1. **Trend Break:** The price crashes beneath its 20-day Simple Moving Average (`sma_20`). *(Note: This was upgraded from `sma_50` to secure profits much faster during explosive breakouts).*
2. **Market Regime Crash:** The overall macroeconomic environment (`regime_score`) falls below `30.0`.
3. **Overbought Take-Profit:** The RSI (Relative Strength Index) surges above `75.0` indicating extreme, unsustainable buying pressure.

If any of these conditions are met, the agent automatically executes a market sell.

## 2. Trailing Stops (The Invisible Safety Net)
Waiting for a stock to crash through a moving average can sometimes forfeit too much profit (e.g., dropping from $172 down to $150). To prevent this, the `ExitAgent` runs a secondary risk management layer using **ATR Trailing Stops**.

* **What is ATR?** The Average True Range (ATR) measures exactly how wildly a stock swings on a normal day.
* **How the Net works:** The system tracks the absolute highest peak price the stock has ever reached since you bought it. It then multiplies the ATR by `2.0` to calculate a "safe distance". The stop-loss line is dragged up right behind the peak by this distance.

### Example Calculation
Assume you bought **MRVL** and it surges aggressively upward.
1. The stock hits a new all-time high (Peak): **$172.15**
2. The agent calculates the current ATR: **$8.98**
3. It multiplies the ATR to find the Safe Distance: `2.0 * $8.98` = **$17.97**
4. It sets the invisible sell trigger: `$172.15 - $17.97` = **$154.18**

As long as the stock stays above `$154.18`, the agent will continue to HOLD the position and let the profits accumulate. 
* If the stock goes up to $200, the safety net is dragged up to ~$182. 
* If the stock reverses and crashes through the safety net, the agent immediately executes a market sell, successfully locking in the profits before the crash reaches the moving average baseline.
