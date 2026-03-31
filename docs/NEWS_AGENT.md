# NewsAgent - Specification & Design

**Agent ID:** `news_agent`  
**File:** `finance_service/agents/news_agent.py`  
**Status:** ⚙️ Placeholder / In Development  
**Version:** 1.0  
**Last Updated:** 2026-03-29

---

## Overview

NewsAgent monitors recent news for a given symbol, performs sentiment analysis, and identifies potential catalysts that could impact price movement. It is designed to integrate with external news APIs (e.g., Finnhub, Alpha Vantage, NewsAPI) or proprietary feeds.

**Key Responsibility:** Provide qualitative, text-based signals to complement technical analysis.

---

## Design Philosophy

```
                    ┌─────────────────────────────────────┐
                    │  NEWS_FETCH_REQUEST (per symbol)    │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼─────────────────────┐
                    │  NewsAgent.run(symbol)             │
                    │  - Fetch recent news (last 24-48h)│
                    │  - Perform sentiment analysis     │
                    │  - Identify catalysts             │
                    └──────────────┬─────────────────────┘
                                   │
                    ┌──────────────▼─────────────────────┐
                    │  NEWS_FETCH_COMPLETE event         │
                    │  payload: {                        │
                    │    symbol,                         │
                    │    news_count,                     │
                    │    sentiment: {symbol: score},     │
                    │    catalysts: [...]                │
                    │  }                                 │
                    └───────────────────────────────────┘
```

---

## Input Parameters

### `run(symbol: str) -> Optional[AgentReport]`

| Parameter | Type | Description |
|-----------|------|-------------|
| `symbol` | `str` | Ticker symbol to fetch news for |

Returns `AgentReport` with:
- `agent_id`: `"news_agent"`
- `status`: `"success"` (or `"error"` on failure)
- `message`: summary
- `payload`:
  - `symbol`: symbol
  - `news_count`: number of articles retrieved
  - `sentiment`: dict mapping symbol → `{"overall_sentiment": float, "summary": str}`
  - `catalysts`: list of catalyst dicts `{type, description}`

---

## Internal Processing Steps

1. **Fetch News** (`_fetch_news(symbols: List[str])`)
   - Placeholder implementation; needs real API integration.
   - Current behavior: returns empty list if no providers configured.
2. **Sentiment Analysis** (`_analyze_sentiment(news_data)`)
   - Placeholder; should assign sentiment scores and summaries.
3. **Catalyst Identification** (`_identify_catalysts(sentiment_results)`)
   - Placeholder; should produce list of catalysts (e.g., earnings, FDA approval, M&A).

---

## Configuration (finance.yaml)

```yaml
finance:
  news:
    enabled: true
    provider: "finnhub"  # or "alphavantage", "newsapi"
    api_key: ""          # provider-specific API key
    max_articles: 20
    lookback_hours: 48
    sentiment_model: "textblob"  # or "vader", custom
```

(Configuration keys are not yet implemented in code.)

---

## Event Flow Integration

```
AnalysisAgent or Orchestrator triggers NEWS_FETCH_REQUEST
    ↓
NewsAgent.run(symbol)
    ↓
Publish NEWS_FETCH_COMPLETE event
    ↓
Orchestrator collects news together with DataAgent and AnalysisAgent results
    ↓
StrategyAgent may factor news into its decision
```

---

## Current Implementation Status

- ✅ Skeleton: `run()` method, event publishing
- ✅ Placeholder methods `_fetch_news`, `_analyze_sentiment`, `_identify_catalysts`
- ⚠️ **Needs integration:** Real news API and sentiment engine
- ⚠️ **Needs config:** Read provider and API key from `YAMLConfigEngine`
- ⚠️ **Needs testing:** No dedicated tests yet

---

## Integration Example

```python
# Orchestrator snippet
news_report = await news_agent.run(symbol="NVDA")
if news_report.status == "success":
    sentiment = news_report.payload["sentiment"]["NVDA"]["overall_sentiment"]
    catalysts = news_report.payload["catalysts"]
    # These could influence strategy confidence or trigger special handling
```

---

## Testing

No test suite yet. Planned: `tests/test_news_agent.py` covering:
- Fetch with mock API
- Sentiment analysis correctness
- Catalyst detection rules
- Event payload structure

---

## Summary

NewsAgent is a **stub** awaiting implementation. It will enrich the pipeline with qualitative data. Priority: integrate a news provider (Finnhub recommended) and a lightweight sentiment library (TextBlob/VADER).
