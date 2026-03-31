# NewsAgent - Specification & Design

**Agent ID:** `news_agent`  
**File:** `finance_service/agents/news_agent.py`  
**Status:** ✅ Production-ready  
**Version:** 2.0  
**Last Updated:** 2026-03-31

---

## Overview

NewsAgent fetches real news articles for a given symbol, runs VADER sentiment analysis, and identifies concrete catalysts (earnings beats, analyst upgrades, product launches, etc.). It is integrated into the main trading pipeline and its output is consumed by StrategyAgent and surfaced in pre-execution Telegram notifications.

**Key Responsibility:** Provide qualitative, text-based signals to complement technical analysis.

---

## Data Sources

| Priority | Provider | Endpoint | Notes |
|----------|----------|----------|-------|
| Primary | **Alpha Vantage** | `NEWS_SENTIMENT` | Per-ticker sentiment scores included; falls back if rate-limited or no articles |
| Fallback | **Finnhub** | `company-news` | 3-day lookback, up to 20 articles |

API keys are read from environment variables with hardcoded fallback values:
```
ALPHAVANTAGE_API_KEY   (default: configured in code)
FINNHUB_API_KEY        (default: configured in code)
```

---

## Design Philosophy

```
                    ┌─────────────────────────────────────┐
                    │  NewsAgent.run(symbol)              │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼─────────────────────┐
                    │  _fetch_news(symbol)               │
                    │  1. Try Alpha Vantage (48h window) │
                    │  2. Fallback: Finnhub (3-day)      │
                    └──────────────┬─────────────────────┘
                                   │
                    ┌──────────────▼─────────────────────┐
                    │  _analyze_sentiment(articles)      │
                    │  VADER compound score per article  │
                    │  Merged with AV score if present   │
                    │  Aggregate: mean of all articles   │
                    └──────────────┬─────────────────────┘
                                   │
                    ┌──────────────▼─────────────────────┐
                    │  _identify_catalysts(articles)     │
                    │  Keyword scan across 11 patterns   │
                    └──────────────┬─────────────────────┘
                                   │
                    ┌──────────────▼─────────────────────┐
                    │  NEWS_FETCH_COMPLETE event         │
                    │  payload: {                        │
                    │    symbol,                         │
                    │    news_count,                     │
                    │    sentiment_score,   ← float      │
                    │    sentiment_label,   ← str        │
                    │    catalysts,         ← List[str]  │
                    │    sentiment: {legacy key}         │
                    │  }                                 │
                    └───────────────────────────────────┘
```

---

## Input Parameters

### `run(symbol: str) -> Optional[AgentReport]`

| Parameter | Type | Description |
|-----------|------|-------------|
| `symbol` | `str` | Ticker symbol (US: `NVDA`; HK: `0966.HK`) |

Returns `AgentReport` with:
- `status`: `"success"` (errors are caught and degraded gracefully — empty result)
- `payload`:

| Key | Type | Description |
|-----|------|-------------|
| `symbol` | `str` | Input symbol |
| `news_count` | `int` | Number of articles fetched |
| `sentiment_score` | `float` | Aggregate sentiment −1.0 to +1.0 |
| `sentiment_label` | `str` | `"bullish"` / `"neutral"` / `"bearish"` |
| `catalysts` | `List[str]` | Detected catalyst names |
| `sentiment` | `Dict` | Legacy key for backward compatibility |

---

## Sentiment Analysis

Library: **VADER** (`vaderSentiment>=3.3.2`) — purely rule-based, no model download required.

**Per-article score:**
- VADER compound score computed from `headline + summary` text
- If Alpha Vantage provides its own `ticker_sentiment_score`, it is averaged 50/50 with VADER

**Aggregate:**
```
article_scores = [merged_score for each article]
aggregate = mean(article_scores), clamped to [−1.0, +1.0]
```

**Labels:**
| Range | Label |
|-------|-------|
| `>= +0.3` | bullish |
| `<= −0.3` | bearish |
| otherwise | neutral |

---

## Catalyst Detection

Keyword scan across 11 patterns:

| Catalyst | Example Keywords |
|----------|-----------------|
| earnings beat | "beat", "earnings beat", "surpassed estimates" |
| earnings miss | "missed earnings", "below estimate" |
| analyst upgrade | "upgrade", "raised price target", "outperform" |
| analyst downgrade | "downgrade", "underperform", "sell rating" |
| merger/acquisition | "acqui", "merger", "takeover", "buyout" |
| product launch | "launch", "new product", "unveiled" |
| regulatory approval | "fda approv", "approved by", "regulatory clearance" |
| guidance raised | "raised guidance", "raised outlook" |
| guidance lowered | "lowered guidance", "cut guidance" |
| insider buying | "insider buy", "executive purchase" |
| short squeeze | "short squeeze", "short interest" |

If no keyword matches, a generic fallback is used based solely on sentiment magnitude.

---

## Configuration

API keys are set via environment variables (`.env`):
```
ALPHAVANTAGE_API_KEY=your_key_here
FINNHUB_API_KEY=your_key_here
```

Optional `finance.yaml` section (currently read but not yet enforced):
```yaml
finance:
  news:
    enabled: true
    max_articles: 20
    lookback_hours: 48
```

---

## Event Flow Integration

```
Orchestrator after DATA_FETCH_COMPLETE
    ↓
NewsAgent.run(symbol)  [runs in parallel with AnalysisAgent]
    ↓
Publishes NEWS_FETCH_COMPLETE event
    ↓
Orchestrator buffers result; triggers StrategyAgent when both
NEWS_FETCH_COMPLETE + ANALYSIS_COMPLETE are ready for the same symbol
```

---

## Integration Example

```python
news_report = await news_agent.run(symbol="NVDA")
if news_report.status == "success":
    score = news_report.payload["sentiment_score"]      # e.g. +0.42
    label = news_report.payload["sentiment_label"]      # "bullish"
    cats  = news_report.payload["catalysts"]            # ["analyst upgrade"]
```

---

## Dependencies

- `vaderSentiment>=3.3.2` — VADER sentiment library
- `aiohttp>=3.8` — async HTTP (already in requirements.txt)

---

## Testing

Test suite: planned at `tests/test_news_agent.py`. Coverage targets:
- AlphaVantage fetch + fallback to Finnhub
- VADER sentiment scoring correctness
- Catalyst keyword matching
- Graceful handling of API errors / timeouts
