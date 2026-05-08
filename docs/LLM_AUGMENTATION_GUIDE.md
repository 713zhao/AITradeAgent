# LLM Augmentation Guide

**Version:** 1.0  
**Last Updated:** 2026-04-01  
**Status:** Planned (Phase 1)

---

## Overview

AITradeAgent now supports optional LLM-powered modules that enhance decision-making while maintaining deterministic rule-based trading as the default. All LLM features are toggleable via configuration and incur API costs when enabled.

---

## Configuration

Enable LLM modules in `config/config.yaml` under the `llm` section.

### Provider Setup

```yaml
llm:
  provider: "openrouter"  # openrouter, openai, anthropic, ollama
  api_key_env: "OPENROUTER_API_KEY"  # Env var name containing API key
  base_url: "https://openrouter.ai/api/v1"  # Optional; defaults per provider
  model: "anthropic/claude-3.7-sonnet"  # Default model for all modules
  temperature: 0.3
  max_retries: 3
  timeout: 30  # seconds
```

### Module Enablement

```yaml
llm:
  modules:
    market_regime:
      enabled: true
      model: "anthropic/claude-3.7-sonnet"  # Optional; falls back to default
      temperature: 0.2
      prompt_template: "prompts/regime_classifier.md"  # Optional custom prompt

    news_sentiment:
      enabled: false  # Default off
      model: "openai/gpt-4.1-mini"
      temperature: 0.4

    anomaly_explanation:
      enabled: true
      model: "openrouter/auto"  # Use OpenRouter auto-select

    adaptive_tuning:
      enabled: false
      schedule: "0 6 * * 1"  # Cron: Mondays 6 AM
      auto_apply: false  # Require manual approval if true
```

---

## Available Modules

### 1. Market Regime Classifier

**Agent:** `RegimeAgent`  
**Event:** `MARKET_REGIME_UPDATED`

#### Purpose

Classifies the current market environment to help strategies adapt.

#### Regimes

- `trending_bullish` — Price above major MAs, positive momentum
- `trending_bearish` — Price below major MAs, negative momentum
- `range_bound` — Sideways consolidation, low directional bias
- `high_volatility` — ATR > 2x normal, large price swings
- `low_volatility` — ATR < 0.5x normal, quiet market
- `mixed` — Unclear or transition state

#### Inputs

- Last 30 days of daily OHLCV
- Current indicator snapshot (RSI, MACD, SMA 50/200, ATR)
- Recent VIX (if available)

#### Output

```json
{
  "regime": "trending_bullish",
  "confidence": 0.87,
  "description": "Uptrend with price above 50/200 SMA, MACD positive, RSI 65",
  "timestamp": "2026-04-01T10:30:00Z"
}
```

#### Strategy Integration

`StrategyAgent` reads latest regime and adjusts:

- **Trending Bullish:** Favor long positions, lower RSI oversold threshold to 25, raise confidence threshold to 0.85
- **Range-Bound:** Use mean-reversion rules (BB +/-2), tighten stops
- **High Volatility:** Reduce position size by 50%, widen stops

---

### 2. News Sentiment Interpreter

**Agent:** `NewsAgent` (enhanced)  
**Event:** `NEWS_ANALYSIS_COMPLETE`

#### Purpose

Go beyond simple sentiment scores to extract actionable narratives.

#### Inputs

- Top 10 recent headlines (from yfinance or other sources)
- Article summaries (if available)
- Symbol-specific news filters

#### Output

```json
{
  "sentiment_score": 0.62,
  "narratives": [
    "AI chip demand surge",
    "New product launch expected"
  ],
  "catalysts": [
    "Earnings in 3 days (expected beat)",
    "Analyst upgrade from MS"
  ],
  "risk_factors": [
    "Competition concerns",
    "Supply chain disruption risk"
  ],
  "source": "news",
  "timestamp": "2026-04-01T10:30:00Z"
}
```

#### Usage

- Triggers more aggressive entries when strong positive catalysts + sentiment > 0.7
- Reduces position size or skips if risk factors dominate
- Adds narrative text to Telegram alerts

---

### 3. Anomaly Explanation Engine

**Agent:** `AnalysisAgent` (augmented)  
**Event:** `ANALYSIS_COMPLETE` (enriched)

#### Purpose

When technical indicators show unusual patterns, generate plausible explanations.

#### Anomaly Patterns

- RSI < 20 with price > 200-SMA (oversold in uptrend)
- MACD histogram divergence while price makes new high
- Volume spike without price movement (accumulation/distribution?)
- Gap-up with no news

#### Output

Enhanced `IndicatorsSnapshot` includes:

```json
{
  "anomaly_flags": ["oversold_in_uptrend"],
  "anomaly_explanation": "Strong buying opportunity: despite RSI dipping to 18, price holds above 200 SMA, suggesting institutional accumulation during pullback. MACD remains positive, confirming bullish momentum intact."
}
```

---

### 4. Adaptive Rule Tuner

**Agent:** `LearningAgent` (extended)  
**Schedule:** Weekly (configurable)

#### Purpose

Review recent trade performance and suggest rule parameter tweaks.

#### Process

1. Fetch last 200 closed trades
2. Group by rule that triggered (e.g., `rsi_oversold`, `sma20_cross`)
3. Compute win rate, average P&L, Sharpe by rule
4. Prompt LLM:

```
You are a trading strategy optimizer. Given the following rule performance:

- rsi_oversold (threshold=30): 45% win rate, avg P&L = -$50
- macd_bullish_cross: 62% win rate, avg P&L = +$120
...

Suggest parameter adjustments to improve overall performance. Consider:
- Adjusting RSI threshold to 28 or 32?
- Adding confirmation requirement (e.g., volume > avg)?
- Disabling underperforming rules?

Output JSON:
{
  "adjustments": [
    {
      "rule_name": "rsi_oversold",
      "parameter": "threshold",
      "old_value": 30,
      "suggested_value": 28,
      "rationale": "Win rate improves at lower RSI thresholds; 28 captures deeper oversold"
    }
  ]
}
```

#### Safety

- `adaptive_tuning.auto_apply: false` (default) — suggestions logged, require manual config edit
- Never modify strategy without human review
- All changes tracked in `memory/adaptive_tuning_history.md`

---

## Prompt Templates

Customize prompts by placing `.md` files in `config/prompts/` and referencing them in YAML:

```yaml
llm:
  modules:
    market_regime:
      prompt_template: "prompts/regime_classifier_v2.md"
```

**regime_classifier.md template:**

```
Analyze the following market data for {symbol} and classify the current regime.

## OHLCV (last 30 days)
{ohlcv_table}

## Current Indicators
- RSI: {rsi}
- MACD: {macd} (histogram: {macd_hist})
- SMA 50: {sma_50}, SMA 200: {sma_200}
- ATR: {atr}
- Price vs SMA200: {price_vs_sma200_pct:.1f}%

## Regimes
- trending_bullish: Price > SMA200 & SMA50 > SMA200 & MACD > 0
- trending_bearish: Price < SMA200 & SMA50 < SMA200 & MACD < 0
- range_bound: Price oscillating between support/resistance, low ATR
- high_volatility: ATR > 2× 90-day average ATR
- low_volatility: ATR < 0.5× 90-day average ATR

Output JSON:
{
  "regime": "one of the above",
  "confidence": 0.0-1.0,
  "description": "one-sentence rationale"
}
```

---

## Cost Management

### Default: Disabled

All LLM modules are `enabled: false` by default. User must explicitly enable.

### Rate Limiting

Add per-module rate limits:

```yaml
llm:
  rate_limit:
    requests_per_minute: 30
    tokens_per_minute: 10000
```

### Caching

LLM responses cached in Redis or SQLite (24h TTL for regime, 1h for news).

---

## Error Handling

- LLM API down → fall back to deterministic rules (log warning)
- Timeout → use cached previous result or defaults
- Malformed JSON response → retry with stricter JSON mode (if provider supports)

---

## Monitoring

Add metrics:

- `llm_requests_total{module, status}`
- `llm_latency_seconds{module}`
- `llm_cost_estimate_total` (based on token count × provider pricing)

View in Grafana dashboard `dashboards/llm_monitoring.json`.

---

## Testing

Mock LLM responses in tests:

```python
from unittest.mock import MagicMock

mock_llm = MagicMock()
mock_llm.invoke.return_value = {"regime": "trending_bullish", "confidence": 0.9}

# Patch LLM client factory
@patch("finance_service.llm.factory.create_llm_client")
def test_regime_agent(mock_factory):
    mock_factory.return_value.get_llm.return_value = mock_llm
    # ... test agent
```

---

## Future Enhancements

- Local LLM support (Llama 3.3 via Ollama) for zero-cost inference
- Multi-modal: Screenshot chart analysis (Claude 3.7 Sonnet vision)
- Reinforcement learning fine-tuning on trade outcomes
- Sentiment aggregation from Discord/Telegram communities (with ethical sourcing)

---

## Conclusion

LLM augmentation makes AITradeAgent smarter, but the core remains deterministic. Toggle features on/off to match your risk tolerance and budget.

---

## Telegram LLM Integration (May 2026)

### Overview

Three LLM-powered features are now integrated into Telegram trade notifications:

1. **Market Environment Classification** - Real-time market regime display
2. **Anomaly Detection** - Trade setup anomalies with explanations
3. **Strategy Suggestions** - LLM-generated trading recommendations

### Scope: Pre-Execution Notifications Only

These features appear **exclusively** in the "⚡ Trade About to Execute" message sent before trade execution.

**They do NOT appear in:**
- Hourly Portfolio Reports (equity/P&L metrics only)
- Daily Summaries (trade history)
- Trade Executed notifications (fill details)
- Error Alerts (error information)
- Telegram commands (/start, /status, /portfolio)

### Message Type Reference

| Message | Schedule | Contains LLM? | Purpose |
|---------|----------|---------------|---------|
| Trade About to Execute | On signal | ✅ YES | Decision support before trade |
| Hourly Portfolio Report | Hourly | ❌ NO | Performance monitoring |
| Daily Summary | Daily | ❌ NO | Trade review |
| Trade Executed | Post-fill | ❌ NO | Execution confirmation |
| Error Alert | On error | ❌ NO | Error notification |
| Bot Commands | On request | ❌ NO | Manual status queries |

### Features Detail

#### 1. Market Environment Classification

**Location**: Pre-execution notifications  
**Format**: `📍 Market Context: 🟢 Risk-On | 📉 Vol: Low | VIX: 18.5`

**Shows:**
- Risk status: 🟢 Risk-On or 🔴 Risk-Off
- Volatility level: 📈 High / ➡️ Normal / 📉 Low
- Current VIX value

**Data source**: `market_regime_agent.run()` with caching

#### 2. Anomaly Detection

**Location**: Pre-execution notifications (only if anomaly detected)  
**Format**: `⚠️ Alert: RSI > 85 (overbought condition)`

**Detects:**
- Extreme RSI: > 85 (overbought) or < 15 (oversold)
- Volume spikes: Current volume > 2.5x SMA
- MACD divergence: Price vs MACD direction mismatch

**Performance**: <1ms (threshold-based detection)

#### 3. LLM Strategy Suggestions

**Location**: Pre-execution notifications (if LLM available)  
**Format**: `💡 Suggestion: Reduce size due to overbought condition...`

**Generated using:**
- Market regime context
- Technical indicators (RSI, MACD, Bollinger Bands)
- Trade rationale and confidence
- Symbol information

**LLM Config:**
- Model: Google Gemini (gemini-2.5-flash)
- Temperature: 0.3 (deterministic)
- Max length: 200 characters
- Cache: Disabled (fresh per trade)

### Implementation

Files involved:
- `finance_service/agents/telegram_llm_enhancement.py` - Core functions (242 lines)
  - `detect_trade_anomalies()` - Anomaly detection logic
  - `generate_trade_suggestion()` - LLM suggestion generation
  - `format_market_regime_display()` - Market regime formatting
  
- `finance_service/agents/telegram_agent.py` - Message formatting (+45 lines)
  - Added parameters: `market_regime`, `anomaly_explanation`, `trade_suggestion`
  - Message sections: 📍 Market Context, ⚠️ Alert, 💡 Suggestion

- `finance_service/app.py` - Data gathering (+50 lines, 2 locations)
  - Lines ~541-590: Pre-execution trade notification (primary)
  - Lines ~803-820: Tier2 intraday entry (secondary)
  - Gets market regime, detects anomalies, generates suggestions

### Example Output

```
⚡ Trade About to Execute

Symbol: AAPL
Action: 🟢 BUY
Quantity: 10.0000 shares
Entry Price: $150.2500
Stop Loss: $148.5000 (-1.1%)
Confidence: 87.5%

Portfolio: Cash: $2,500.00 | Positions: $47,500.00 | Equity: $50,000.00

📊 Technical Indicators
  • RSI: 72.5 — Overbought region
  • MACD: +0.0125 — Bullish
  • BB Position: 78%

📰 News
  📈 Sentiment: Bullish (+0.65)
  🗞 Catalysts: earnings, analyst_upgrade

📍 Market Context
  🟢 Risk-On | 📉 Vol: Low | VIX: 18.5

⚠️ Alert
  RSI > 85 (overbought condition)

💡 Suggestion
  Strong technicals with risk-on environment confirms bullish bias.
  Consider smaller size given overbought reading.

📋 Reason to Buy
  • Strong momentum and technical setup
  • Positive news catalyst support
  • Risk/reward favorable at current levels
```

### Configuration

No additional configuration needed - features are built-in and automatic.

Optional customization:
- Anomaly thresholds in `telegram_llm_enhancement.py` (lines 50-70)
- LLM model/temperature in `config/finance.yaml` (existing LLM section)
- Enable/disable via parameter passing (set to None to disable)

### Error Handling

All LLM enhancements are non-blocking:
- LLM unavailable → notification sent without suggestions
- Market regime unavailable → notification sent without regime display
- Anomaly detection fails → proceeds with notification
- LLM timeout → falls back to basic notification

Errors logged at debug level, no trade interruption.

### Performance

- Market Regime lookup: ~200ms (uses cache)
- Anomaly Detection: <1ms (threshold checks)
- LLM Suggestion: ~2-3 seconds
- Total overhead: <3 seconds (non-blocking, parallel processing)

### Monitoring

Check logs for LLM enhancement status:
```bash
journalctl --user -u aitrade-heartbeat.service -f | grep -E "LLM|market_regime|anomaly"
```

Monitor Telegram notifications to verify:
- 📍 Market Context appears
- ⚠️ Alerts show when anomalies detected
- 💡 Suggestions appear when trading

### Next Steps

- Monitor live trade notifications for LLM insights
- Adjust anomaly thresholds if too many/too few alerts
- Consider LLM suggestion feedback for model tuning
- Track which suggestions correlate with profitable trades

