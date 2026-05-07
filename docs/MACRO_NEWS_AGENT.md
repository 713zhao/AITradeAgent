# MacroNewsAgent

**File:** `finance_service/agents/macro_news_agent.py`  
**Agent ID:** `macro_news_agent`  
**Goal:** Provide macroeconomic context and risk event awareness for trading decisions.

---

## Overview

`MacroNewsAgent` fetches broad-market financial news from Yahoo Finance and filters/classifies articles for macro relevance. It supports **dual-market news analysis**: 

- **US Market**: News via SPY (S&P 500 ETF), QQQ (NASDAQ ETF), DIA (Dow ETF)
- **Hong Kong Market**: News via 2800.HK (Tracker Fund), 2823.HK (iShares Hang Seng ETF), 2822.HK (iShares China Large-Cap ETF)

Regional reports are generated independently, with US-specific and HK-specific filters (HK filter includes HKMA, Hang Seng, PBOC, RMB, HKD, currency peg keywords). Aggregate sentiment and catalysts/risk events are extracted per market and passed to `SymbolSelectorAgent` for market-specific regime-aware ranking.

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
| `us_macro_news` | List[dict] | Filtered & analyzed US articles |
| `us_sentiment_score` | float | Average VADER sentiment (US sources) |
| `hk_macro_news` | List[dict] | Filtered & analyzed HK articles |
| `hk_sentiment_score` | float | Average VADER sentiment (HK sources) |
| `macro_catalysts` | List[str] | Top catalyst keywords from all headlines |
| `risk_events` | List[str] | Articles with urgency=high (combined) |
| `timestamp` | str | ISO timestamp of report generation |

---

## News Categories

### US Categories

| Category | Key Keywords |
|---|---|
| `monetary_policy` | fed, interest rate, FOMC, yield, ECB, central bank |
| `geopolitical` | war, election, trade, sanction, conflict |
| `economic_data` | CPI, NFP, GDP, unemployment, inflation |
| `regulatory` | SEC, regulation, compliance, law |
| `sector_rotation` | tech, energy, financial, healthcare, rotation |
| `other` | (fallback) |

### HK/China Categories

| Category | Key Keywords |
|---|---|
| `monetary_policy` | HKMA, rate, yield, PBOC, interest |
| `hk_china` | Hang Seng, Hong Kong, RMB, HKD, currency peg, China policy |
| `geopolitical` | US-China trade, tariff, sanctions, tech restriction |
| `economic_data` | China GDP, manufacturing, property, PMI |
| `regulatory` | HKMA, SFC, China regulation |
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

### US News Sources

- **SPY** (S&P 500 ETF), **QQQ** (NASDAQ ETF), **DIA** (Dow ETF)
- News fetched via `yfinance` ticker news API
- Articles deduplicated by headline across the 3 US feeds

### HK News Sources

- **2800.HK** (Tracker Fund of Hong Kong), **2823.HK** (iShares Hang Seng ETF), **2822.HK** (iShares China Large-Cap ETF)
- News fetched via `yfinance` ticker news API
- Articles deduplicated by headline across the 3 HK/China feeds

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

## Agent Report Structure

The output `AgentReport.payload` contains regional sentiment scores:

```json
{
  "us_macro_news": [...],
  "us_sentiment_score": 0.12,
  "hk_macro_news": [...],
  "hk_sentiment_score": 0.05,
  "macro_catalysts": ["Fed", "China inflation", "chip shortage"],
  "risk_events": ["...high urgency article..."],
  "timestamp": "2026-04-04T..."
}
```

`SymbolSelectorAgent` selects per-market sentiment via:
- `macro_sentiment_score = payload["hk_sentiment_score"]` for HK market
- `macro_sentiment_score = payload["us_sentiment_score"]` for US market

---## Related Agents

- **`SymbolSelectorAgent`** — consumes per-market macro sentiment (us/hk_sentiment_score) + catalysts for LLM prompt
- **`MarketRegimeAgent`** — provides complementary regional index-based regime context (regime_us / regime_hk)
- **`NewsAgent`** — symbol-specific news (different from this agent's scope)
