# MacroNewsAgent

**File:** `finance_service/agents/macro_news_agent.py`  
**Agent ID:** `macro_news_agent`  
**Goal:** Provide macroeconomic context and risk event awareness for trading decisions.

---

## Overview

`MacroNewsAgent` fetches broad-market financial news from Yahoo Finance (via SPY, QQQ, DIA tickers) and filters/classifies articles for macro relevance. It computes aggregate sentiment and extracts catalysts/risk events, which are passed to `SymbolSelectorAgent` for regime-aware ranking.

---

## Data Model

### `MacroNewsItem`

| Field | Type | Description |
|---|---|---|
| `headline` | str | Article headline |
| `source` | str | Publisher name |
| `published_at` | str | ISO 8601 timestamp |
| `sentiment` | float | VADER compound score (−1 to +1) |
| `category` | str | Macro theme (see categories below) |
| `impact_tags` | List[str] | Asset class impact tags |
| `urgency` | str | `"high"` / `"medium"` / `"low"` |

### `MacroNewsReport` (output)

| Field | Type | Description |
|---|---|---|
| `macro_news` | List[dict] | Filtered & analyzed articles as dicts |
| `macro_sentiment_score` | float | Average VADER sentiment across articles |
| `macro_catalysts` | List[str] | Top catalyst keywords from headlines |
| `risk_events` | List[str] | Articles with urgency=high |
| `timestamp` | str | ISO timestamp of report generation |

---

## News Categories

| Category | Key Keywords |
|---|---|
| `monetary_policy` | fed, interest rate, FOMC, yield, ECB, central bank |
| `geopolitical` | war, election, trade, sanction, conflict |
| `economic_data` | CPI, NFP, GDP, unemployment, inflation |
| `regulatory` | SEC, regulation, compliance, law |
| `sector_rotation` | tech, energy, financial, healthcare, rotation |
| `other` | (fallback) |

---

## Impact Tags

Articles are tagged for affected asset classes:

| Tag | Keywords |
|---|---|
| `rates` | rate hike, rate cut, yield |
| `inflation` | inflation, CPI, prices |
| `dollar` | dollar, USD, DXY |
| `stocks` | stock, equity, market |
| `crypto` | bitcoin, crypto, ethereum |
| `commodities` | oil, gold, commodity |

---

## Urgency Classification

| Age of Article | Urgency |
|---|---|
| < 6 hours | `"high"` |
| 6–24 hours | `"medium"` |
| > 24 hours | `"low"` |

---

## Macro Relevance Filter

Articles are kept only if their headline + summary matches at least one keyword from a 17-pattern macro keyword list including: fed, FOMC, CPI, NFP, GDP, ECB, BOJ, tariff, geopolitical, election, SEC, oil, treasury, yield curve, unemployment, supply chain, chip shortage.

---

## Data Sources

- **SPY** (S&P 500 ETF), **QQQ** (NASDAQ ETF), **DIA** (Dow ETF)
- News fetched via `yfinance` ticker news API
- Articles deduplicated by headline across the 3 ETF feeds

---

## Caching

- **SQLite cache:** 6-hour TTL (configurable)
- Cache path: `finance_service/storage/macro_news_cache.sqlite`
- Reuses `_NewsCache` infrastructure from `NewsAgent`

---

## Configuration (`config/finance.yaml`)

```yaml
macro_news_agent:
  cache_ttl_minutes: 360   # 6 hours
  cache_path: "finance_service/storage/macro_news_cache.sqlite"
  lookback_hours: 24
  max_articles: 30
```

---

## Usage

```python
agent = MacroNewsAgent(config_engine)
report = await agent.run()
print(report.payload["macro_sentiment_score"])      # e.g. 0.107
print(report.payload["macro_catalysts"][:3])         # top keywords
print(len(report.payload["macro_news"]))             # filtered article count
```

---

## yfinance API Compatibility

yfinance changed its news API format. Both old and new formats are supported:

| Format | Structure |
|---|---|
| Old (legacy) | `{"title": ..., "providerPublishTime": ..., "link": ...}` |
| New (current) | `{"id": ..., "content": {"title": ..., "pubDate": ..., "provider": {"displayName": ...}, "canonicalUrl": {"url": ...}}}` |

---

## Known Issues / Notes

| Issue | Status | Details |
|---|---|---|
| yfinance news API format change | ✅ Fixed | Dual-format parser handles both old and new structures |
| VADER not installed | Graceful | Returns sentiment=0.0 without VADER; log warning emitted |
| No direct macro news API | Design choice | Uses ETF ticker feeds (SPY/QQQ/DIA) as proxy for broad market news |

---

## Related Agents

- **`SymbolSelectorAgent`** — consumes macro sentiment + catalysts for LLM prompt
- **`MarketRegimeAgent`** — provides complementary index-based regime context
- **`NewsAgent`** — symbol-specific news (different from this agent's scope)
