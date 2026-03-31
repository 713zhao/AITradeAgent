# DataAgent - Specification & Design

**Agent ID:** `data_agent`  
**File:** `finance_service/agents/data_agent.py`  
**Status:** ✅ Production-ready, actively used  
**Version:** 2.0  
**Last Updated:** 2026-03-29

---

## Overview

DataAgent is the **data backbone** of the trading system. It fetches, caches, and normalizes market data (OHLCV) and optionally fundamental data. It provides a reliable, rate-limited interface to Yahoo Finance (and potentially other providers) and shields downstream agents from API volatility.

**Key Responsibility:** Ensure fresh, consistent market data is available for analysis and strategy.

---

## Design Philosophy

```
                    ┌───────────────────────────────────┐
                    │  Downstream Agents (Analysis,      │
                    │  Strategy, etc.) request data     │
                    └──────────────┬────────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  DataAgent.run(symbol, ...)     │
                    │  - Check cache                 │
                    │  - If miss/stale → fetch       │
                    │  - Store in cache              │
                    │  - Return DataFrame            │
                    └──────────────┬─────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  YfinanceProvider              │
                    │  (rate-limited batch fetch)    │
                    └────────────────────────────────┘
```

---

## Input Parameters

### `run(symbol: str, interval: str = "1d", start_date=None, end_date=None, use_cache=True, refresh_all=False, emit_events=True) -> AgentReport`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | `str` | required | Ticker symbol (e.g., `"NVDA"`, `"0700.HK"`) |
| `interval` | `str` | `"1d"` | Data interval (`"1d"`, `"1h"`, `"5m"`, etc.) |
| `start_date` | `date` or `None` | `None` | Start date; if `None`, uses default lookback (60d for non-daily, 365d for daily) |
| `end_date` | `date` or `None` | `None` | End date; defaults to today |
| `use_cache` | `bool` | `True` | Enable cache lookup |
| `refresh_all` | `bool` | `False` | Bypass cache and force fresh fetch |
| `emit_events` | `bool` | `True` | Publish `DATA_FETCH_COMPLETE` event |

Returns an `AgentReport` whose `payload` contains:
- `dataframe`: `pd.DataFrame` with columns `Open`, `High`, `Low`, `Close`, `Volume` (index = date)
- `symbol`: symbol
- `interval`: interval
- `source`: provider name (e.g., `"yfinance"`)
- `start_date`, `end_date`: actual range
- `is_fresh`: bool (True if freshly fetched)
- `cache_hit`: bool (True if served from cache)

---

## Caching Deep Dive

### Cache Backend
SQLite database at `storage/cache.sqlite` with table `data_cache`:
```sql
CREATE TABLE data_cache (
    cache_key TEXT PRIMARY KEY,
    data BLOB,  -- compressed pickle of DataFrame
    expires_at TIMESTAMP
);
```

### Cache Key
`{symbol}:{interval}:{start_date}:{end_date}`

### TTL (Time-to-Live)
- Default: **60 minutes** (configurable via `data/cache_ttl_minutes`)
- Weekend TTL: **60 min** (configurable via `data/cache_ttl_weekend`)
- Market hours TTL: **5 min** (configurable via `data/cache_ttl_market_hours`)
Dynamic TTL determined by `_get_dynamic_cache_ttl()` based on current time and market status.

### Cache Invalidation
- Expiration check on read: if `expires_at < now`, entry is considered stale and will be re-fetched.
- `refresh_all=True` bypasses cache and overwrites existing entry with fresh data.
- No automatic purge; old entries remain until overwritten or expired reads skip them.

### Rate Limiting & Retry
`YfinanceProvider` uses `tenacity` with exponential backoff:
- Batch size: `batch_size` (default 10)
- Batch delay: `batch_delay_sec` (default 0.5)
- Request jitter: adds randomness to avoid thundering herd
- Max retries: `api_retries` (default 3)
- Timeout: `api_timeout_sec` (default 30)

---

## Configuration (finance.yaml)

```yaml
finance:
  data:
    batch_size: 10
    batch_delay_sec: 0.5
    request_jitter_sec: 0.5
    backoff:
      initial_wait_sec: 1
      max_wait_sec: 30
      multiplier: 2.0
    api_retries: 3
    api_timeout_sec: 30
    cache_ttl_minutes: 60    # default TTL
    cache_ttl_market_hours: 5   # during US market hours
    cache_ttl_weekend: 60       # weekend

  fundamentals:
    enabled: true
    providers: ["yfinance"]
    alphavantage_api_key: ""   # optional
```

---

## Event Flow Integration

```
DATA_FETCH_REQUEST (orchestrator)
    ↓
DataAgent.run(symbol, interval, start_date, end_date, ...)
    ↓
Check cache → if miss/stale:
    └─ YfinanceProvider.download(symbols, ...)
        └─ Batch fetch with rate limiting
    ↓
Store in cache (with TTL)
    ↓
Return AgentReport(payload={dataframe, ...})
    ↓
If emit_events=True:
    └─ Publish DATA_FETCH_COMPLETE event
        (payload includes dataframe in serialized form)
```

---

## Methods & Utilities

### Query Methods
- `get_cached_data(symbol, interval, start_date, end_date) -> Optional[pd.DataFrame]` – manual cache lookup
- `clear_cache(symbol=None) -> int` – remove cache entries; if symbol is `None`, clears all

---

## Error Handling

- Fetch failures are logged and re-raised; orchestrator catches and continues with other symbols.
- Empty DataFrames are considered a failure.
- Cache corruption (pickle errors) leads to deletion of the bad entry and a fresh fetch.

---

## Testing

Test suite: `tests/test_data_agent.py`

Run:
```bash
cd /home/eric/.openclaw/workspace/AITradeAgent
source venv/bin/activate
python -m pytest tests/test_data_agent.py -v
```

---

## Notes

- DataAgent is instantiated by the orchestrator in `app.py` and shared across agents.
- The provider can be swapped (e.g., to Alpha Vantage) by config; currently only YfinanceProvider is implemented.
- Fundamental data fetching is optional and uses `FundamentalsFetcher` if enabled.
- The cache persists across service restarts, improving startup latency.

---

**Summary:** DataAgent provides a robust, rate-limited, cached data layer. It is the single source of truth for OHLCV data and is used by MarketScannerAgent for liquidity filtering and ranking, and by AnalysisAgent for indicator computation.
