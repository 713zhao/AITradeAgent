# SymbolSelectorAgent

**File:** `finance_service/agents/symbol_selector_agent.py`  
**Agent ID:** `symbol_selector_agent`  
**Goal:** Rank candidate stocks using LLM synthesis of technical, fundamental, sentiment, and regime context.

---

## Overview

`SymbolSelectorAgent` receives a list of candidate symbols from the market scanner and ranks them using an LLM. It aggregates data from multiple agents (technical indicators, news sentiment, macro regime) into a structured prompt and requests a JSON ranking response from the LLM.

The output is a ranked watchlist of 5–10 symbols with scores, rationale, and position size suggestions.

---

## Data Model

### `CandidateData` (per symbol input)

| Field | Type | Description |
|---|---|---|
| `symbol` | str | Ticker symbol |
| `theme` | str | Market theme (e.g. AI, energy, biotech) |
| `technical_indicators` | dict | RSI, MACD, Bollinger Bands, etc. |
| `price_action` | dict | Returns over 1d/5d/20d/60d, ATR |
| `fundamentals` | dict or None | EPS growth, P/E ratio, revenue growth |
| `news_sentiment` | dict | VADER sentiment score, label, catalysts, article count |
| `liquidity_metrics` | dict | Volume, ADV, market cap |
| `risk_metrics` | dict | Beta, volatility, max drawdown |

---

## LLM Scoring Dimensions

Each symbol is scored 0–10 on 5 dimensions (×2 = total 0–100):

| Dimension | What It Evaluates |
|---|---|
| `technical` | Trend alignment, momentum indicators, breakout quality |
| `catalyst` | News flow, earnings, sector catalysts |
| `fundamental` | EPS growth, valuation, balance sheet quality |
| `risk_adjusted` | Volatility-adjusted return potential, stop distance |
| `regime_fit` | Alignment with current market regime (risk-on/off, VIX level) |

---

## LLM Output Schema

```json
{
  "rankings": [
    {
      "symbol": "NVDA",
      "total_score": 85,
      "breakdown": {
        "technical": 9,
        "catalyst": 8,
        "fundamental": 9,
        "risk_adjusted": 8,
        "regime_fit": 9
      },
      "rationale": "Strong technical uptrend, AI news flow, solid earnings.",
      "position_size_pct": 2.0,
      "suggested_stop_pct": 8.0
    }
  ],
  "summary": "Top candidates show momentum aligned with AI theme. Market bullish."
}
```

### Output Constraints

| Field | Constraint |
|---|---|
| `total_score` | 0–100 (sum of 5 dimension scores × 2) |
| `position_size_pct` | 0.5–2.0 |
| `suggested_stop_pct` | 5–15 |
| `rationale` | ≤ 80 characters |
| `summary` | ≤ 120 characters |
| Minimum rankings returned | Top 5 symbols |

---

## Market Context Used in LLM Prompt

The prompt includes full market context from:

- **`MarketRegimeAgent`**: `risk_on`, `momentum_favoring`, `volatility_regime`, `trend_strength`, regime summary
- **`MacroNewsAgent`**: `macro_sentiment_score`, `macro_catalysts`, `risk_events`

Example market context block:

```
MARKET REGIME:
- Risk regime: ON (risk-on environment)
- Momentum: FAVORABLE
- Volatility: normal
- Trend strength: moderate
- Summary: Risk-on regime: SP500 vs SMA200: 1.2%; VIX normal at 18.4

MACRO ENVIRONMENT:
- Macro sentiment: 0.11 (positive)
- Key catalysts: Federal Reserve, inflation, tariff
- Active risk events: (none)
```

---

## Agent Payload (AgentReport)

```python
report.payload = {
    "rankings": [...],          # list of ranked symbol dicts
    "rejected": [...],          # symbols not ranked (scores too low)
    "market_context": {...},    # MarketRegime + MacroNews context
    "llm_summary": "...",      # LLM-generated summary string
    "tokens_used": 12795,       # LLM token usage for this scan
    "timestamp": "2026-04-04T..."
}
```

---

## Telegram Notification Format

```
🏆 LLM Symbol Rankings (5 selected / 50 candidates)

1. NVDA  ⭐85  (T:9 C:8 F:9 R:8 M:9)  pos:2.0%  stop:8%
   Strong technical uptrend, AI news flow, solid earnings.

2. MSFT  ⭐82  (T:8 C:9 F:8 R:8 M:9)  pos:1.8%  stop:7%
   ...

📊 Top candidates show momentum aligned with AI theme.
💰 Tokens used: 12,795
```

---

## Configuration

### `config/finance.yaml`

```yaml
symbol_selector:
  enabled: true
  max_candidates: 50
  top_n: 10

llm:
  enabled: true
  provider: openrouter
  model: openai/gpt-4o-mini
  max_tokens: 12000
  temperature: 0.3
```

### Environment Variables

| Variable | Description |
|---|---|
| `LLM_PROVIDER` | e.g. `openrouter`, `google` |
| `OPENROUTER_API_KEY` | API key for OpenRouter gateway |
| `GOOGLE_API_KEY` | API key for direct Google Gemini |
| `TA_QUICK_THINK_MODEL` | Fast/cheap model (default for SymbolSelector) |
| `TA_DEEP_THINK_MODEL` | Slow/capable model (override) |

---

## Graceful Degradation

| Failure Condition | Behavior |
|---|---|
| `symbol_selector.enabled = false` | Returns empty rankings, no LLM call |
| `MarketRegimeAgent` unavailable | Uses neutral regime context |
| `MacroNewsAgent` unavailable | Uses `macro_sentiment_score = 0.0` |
| LLM API error | Returns empty rankings, logs error |
| LLM returns invalid JSON | Attempts regex cleanup; falls back to empty |
| Fewer than 3 candidates provided | Skips LLM, returns empty rankings |

---

## Related Agents

- **`MarketRegimeAgent`** — provides regime context for LLM prompt
- **`MacroNewsAgent`** — provides macro news context for LLM prompt
- **`MarketScannerAgent`** — provides the initial list of candidate symbols
- **`RankingAgent`** — downstream technical ranker (receives SymbolSelector's output as pre-filtered watchlist)
