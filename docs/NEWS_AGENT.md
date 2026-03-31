# NewsAgent - Specification & Design

**Agent ID:** `news_agent`  
**File:** `finance_service/agents/news_agent.py`  
**Status:** ✅ Production-ready  
**Version:** 3.0  
**Last Updated:** 2026-03-31

---

## Overview

NewsAgent fetches real news articles for a given symbol, runs VADER sentiment analysis, and identifies concrete catalysts (earnings beats, analyst upgrades, product launches, etc.). It is integrated into the main trading pipeline and its output is consumed by StrategyAgent and surfaced in pre-execution Telegram notifications.

Results are cached per-symbol for 60 minutes in a local SQLite database, protecting against API quota exhaustion during bulk scans across 50+ watchlist symbols.

**Key Responsibility:** Provide qualitative, text-based signals to complement technical analysis.

---

## Data Sources

| Priority | Provider | Endpoint / Method | Auth | Notes |
|----------|----------|-------------------|------|-------|
| 1 | **Alpha Vantage** | `NEWS_SENTIMENT` REST | API key | Per-ticker sentiment scores included; auto-falls back on rate-limit or empty |
| 2 | **Finnhub** | `company-news` REST | API key | 3-day lookback, up to 20 articles |
| 3 | **Yahoo Finance** | `yfinance.Ticker.news` | None | No key, no daily quota; always available as last resort |

API keys are read from environment variables with hardcoded fallback values:
```
ALPHAVANTAGE_API_KEY   (default: configured in code)
FINNHUB_API_KEY        (default: configured in code)
```

---

## Caching

News payloads are cached per-symbol in `finance_service/storage/news_cache.sqlite`.

| Property | Value |
|----------|-------|
| Storage | SQLite (`_NewsCache` class) |
| TTL | 60 minutes per symbol |
| Scope | Per-symbol |
| Thread safety | `threading.Lock` around all DB writes |
| Behaviour on hit | Returns stored payload, skips all API calls |
| Behaviour on miss / expired | Runs full fetch pipeline |

**Why cache?** With 50+ symbols in the watchlist and multiple pipeline runs per day, uncached fetches would exhaust Finnhub's free tier within a single scan session. The 1-hour TTL keeps sentiment reasonably fresh for intraday trading decisions.

---

## Design

```
                    ┌─────────────────────────────────────┐
                    │  NewsAgent.run(symbol)              │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼─────────────────────┐
                    │  _NewsCache.get(symbol)            │
                    │  HIT → return cached payload       │
                    │  MISS → continue                   │
                    └──────────────┬─────────────────────┘
                                   │
                    ┌──────────────▼─────────────────────┐
                    │  _fetch_news(symbol)               │
                    │  1. Alpha Vantage (48h window)     │
                    │  2. Finnhub (3-day window)         │
                    │  3. Yahoo Finance (no limit)       │
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
                    │  _NewsCache.set(symbol, payload)   │
                    └──────────────┬─────────────────────┘
                                   │
                    ┌──────────────▼─────────────────────┐
                    │  Publish NEWS_FETCH_COMPLETE event │
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
- `status`: `"success"` (errors are caught and degraded gracefully — returns neutral/empty payload)
- `payload`:

| Key | Type | Description |
|-----|------|-------------|
| `symbol` | `str` | Input symbol |
| `news_count` | `int` | Number of articles fetched |
| `sentiment_score` | `float` | Aggregate sentiment −1.0 to +1.0 |
| `sentiment_label` | `str` | `"bullish"` / `"neutral"` / `"bearish"` |
| `catalysts` | `List[str]` | Detected catalyst names (sorted alphabetically) |
| `sentiment` | `Dict` | Legacy key for StrategyAgent backward compatibility |

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

Keyword scan across 11 patterns (case-insensitive, matched against headline + summary):

| Catalyst | Example Keywords |
|----------|-----------------|
| earnings beat | "beat", "earnings beat", "surpassed earnings", "topped estimate" |
| earnings miss | "missed earnings", "below estimate", "disappointing earnings" |
| analyst upgrade | "upgrade", "raised price target", "outperform", "buy rating" |
| analyst downgrade | "downgrade", "underperform", "sell rating", "reduced target" |
| merger/acquisition | "acqui", "merger", "takeover", "buyout" |
| product launch | "launch", "new product", "unveiled", "announced product" |
| regulatory approval | "fda approv", "approved by", "regulatory clearance" |
| guidance raised | "raised guidance", "raised outlook", "raised forecast" |
| guidance lowered | "lowered guidance", "cut guidance", "reduced forecast" |
| insider buying | "insider buy", "executive purchase", "director bought" |
| short squeeze | "short squeeze", "short interest", "squeeze" |

If no keyword matches, a generic fallback is applied based on the aggregate sentiment magnitude:

| Sentiment Score | Fallback Catalyst |
|-----------------|-------------------|
| ≥ +0.5 | `strong positive sentiment` |
| ≥ +0.3 | `positive news flow` |
| ≤ −0.5 | `strong negative sentiment` |
| ≤ −0.3 | `negative news flow` |

---

## Source Details

### AlphaVantage (`_fetch_alphavantage`)
- Endpoint: `https://www.alphavantage.co/query?function=NEWS_SENTIMENT`
- 48-hour lookback window; articles older than 48h are filtered out
- HK ticker suffix stripped: `0966.HK` → `0966`
- Detects rate-limit responses (`"Information"` / `"Note"` keys) and returns `[]`

### Finnhub (`_fetch_finnhub`)
- Endpoint: `https://finnhub.io/api/v1/company-news`
- 3-day window (`from` / `to` query params)
- Caps response at 20 articles
- Returns `[]` on non-list response (e.g. `{"error": ...}`)

### Yahoo Finance (`_fetch_yahoo`)
- Uses `yfinance.Ticker(symbol).news` — no API key, no daily quota
- Runs in a thread executor (`loop.run_in_executor`) to avoid blocking the async event loop
- Caps response at 20 articles
- Skips articles with an empty `title`
- Handles both dict `provider` (`{"displayName": "..."}`) and plain string `provider`

---

## Configuration

API keys are set via environment variables (`.env`):
```
ALPHAVANTAGE_API_KEY=your_key_here
FINNHUB_API_KEY=your_key_here
```

Optional `finance.yaml` section (for future enforcement):
```yaml
finance:
  news:
    enabled: true
    max_articles: 20
    lookback_hours: 48
    cache_ttl_minutes: 60
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

| Package | Version | Purpose |
|---------|---------|---------|
| `vaderSentiment` | `>=3.3.2` | Sentiment scoring (rule-based, no model download) |
| `aiohttp` | `>=3.8` | Async HTTP for AlphaVantage + Finnhub |
| `yfinance` | latest | Yahoo Finance news (already in requirements.txt) |

---

## Testing

Test suite: `tests/test_news_agent.py` — **67 tests, all passing**.

| Class | Coverage |
|-------|----------|
| `TestNewsCache` | CRUD, TTL expiry, multi-symbol, directory creation |
| `TestSentimentAnalysis` | Empty input, bullish/bearish scoring, AV blending, clamping, label boundaries |
| `TestCatalystDetection` | All 11 patterns, summary-field matching, fallback tiers, sort order |
| `TestFetchAlphaVantage` | Success, 48h filtering, `Information`/`Note` rate-limit keys, HTTP errors, timeout, HK suffix stripping |
| `TestFetchFinnhub` | Mapping, 20-article cap, non-list response, HTTP error, timeout |
| `TestFetchYahoo` | Mapping, 20-article cap, empty title skip, executor error, empty list, string provider |
| `TestFetchPipeline` | Source priority (AV → FH → YF), all-empty fallback |
| `TestNewsAgentRun` | Empty symbol, success report, cache write, cache read, event publish, legacy key, neutral on zero articles |
