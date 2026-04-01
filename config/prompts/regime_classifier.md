# Market Regime Classifier Prompt

Analyze the following market data for {symbol} and classify the current regime.

## OHLCV Summary (last 30 days)

- Current Price: ${close:.2f}
- 50-Day SMA: ${sma_50:.2f}
- 200-Day SMA: ${sma_200:.2f}
- Price vs SMA200: {price_vs_sma200_pct:.1f}%
- Trend: {"Bullish (SMA50 > SMA200)" if trend_up else "Bearish (SMA50 < SMA200)" if trend_down else "Neutral"}

## Technical Indicators

- RSI: {rsi:.1f}
- MACD: {macd:.4f} (histogram: {macd_hist:.4f})
- ATR: ${atr:.2f}
- ATR Ratio (vs 90-day avg): {atr_ratio:.2f}x
- Volume vs 20-day avg: {volume_ratio:.1f}x

## Regime Definitions

- **trending_bullish**: Price > SMA200 & SMA50 > SMA200 & MACD > 0
- **trending_bearish**: Price < SMA200 & SMA50 < SMA200 & MACD < 0
- **range_bound**: Price oscillating between support/resistance; low ATR (<0.5x avg)
- **high_volatility**: ATR > 2× normal average; wide price swings
- **low_volatility**: ATR < 0.5× normal average; tight consolidation
- **mixed**: Unclear or transitioning signals

## Instructions

1. Compare the provided metrics against the regime definitions.
2. Select the **single most likely** regime.
3. Assign confidence (0.0-1.0) based on evidence strength.
4. Write a one-sentence rationale citing specific numbers.

## Output Format (JSON only)

```json
{
  "regime": "one of the regime names above",
  "confidence": 0.87,
  "description": "Concise rationale with numbers"
}
```

Do not include any other text. Output valid JSON only.
