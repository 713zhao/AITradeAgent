# Data Store Architecture Design

## Problem Statement

Current system suffers from:
- **Duplicated fetching**: Each agent fetches data independently, causing redundant network calls
- **No caching coordination**: Multiple agents may fetch same symbol concurrently
- **Inconsistent data**: Different agents may see different prices at slightly different times
- **Hard to monitor**: No central view of data freshness and fetch health

## Proposed Architecture

### Central Data Store (SQLite)

A single store holds OHLCV time-series data for all symbols.

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS ohlcv (
    symbol TEXT NOT NULL,
    timestamp DATE NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    source TEXT,  -- e.g., 'yfinance', 'openbb'
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, timestamp)
);
CREATE INDEX idx_ohlcv_symbol ON ohlcv(symbol);
CREATE INDEX idx_ohlcv_timestamp ON ohlcv(timestamp);
```

### DataAgent as Producer

DataAgent runs two scheduled tasks:

1. **Market Scan Producer** (every 30min)
   - Fetches latest OHLCV for all candidate symbols (universe from config)
   - Batch fetches via provider (single network call)
   - Upserts into DataStore (ON CONFLICT REPLACE)
   - Logs summary

2. **Portfolio Price Producer** (every 5min)
   - Fetches latest OHLCV for current portfolio positions only
   - Batch fetches via provider
   - Upserts into DataStore
   - Logs summary

### Consumers Read from DataStore

All other agents (MarketScanner, StrategyAgent, PortfolioAgent, etc.) read required data from DataStore instead of calling DataAgent.run().

**Consumer interface:**
```python
class DataStore:
    def get_latest(symbol: str, lookback_days: int = 30) -> pd.DataFrame:
        # Returns most recent rows for symbol, up to lookback_days
```

**PortfolioAgent change:**
- Remove `update_prices_from_data_agent()` network fetch
- Instead: `DataStore.get_latest(symbol, 1)` to get current close
- Much faster (local SQLite), no network, no locking

**MarketScanner change:**
- Query DataStore for all candidate symbols' latest data
- Compute indicators locally from stored bars

### Health Monitoring

HealthAgent checks:
- Last fetch timestamp per producer (scan vs portfolio)
- Symbols missing recent data (>2x interval)
- DataStore size and query latency
- Alerts to Telegram if:
  - Freshness gap > interval + 10%
  - Fetch failures in last N runs
  - DataStore > 100MB or >1000 queries/hour (rate monitoring)

### Implementation Phases

**Phase 1: Create DataStore component**
- File: `finance_service/data/data_store.py`
- Methods: `upsert_ohlcv(df, symbol)`, `get_latest(symbol, days)`, `get_multi(symbols, days)`
- Use SQLite with pandas

**Phase 2: Refactor DataAgent to populate DataStore**
- Keep existing provider calls
- Replace per-symbol loops with batch `provider.fetch_ohlcv(symbols, ...)`
- Write results to DataStore
- Log stats (symbols fetched, time taken)

**Phase 3: Update PortfolioAgent**
- Remove network fetch code
- Read current prices from DataStore (latest close)
- Keep fallback to DataAgent.run() if DataStore missing data

**Phase 4: Update MarketScanner**
- Read candidate data from DataStore
- Skip calling DataAgent for price data

**Phase 5: HealthAgent integration**
- Check DataStore freshness
- Send Telegram alerts

**Phase 6: Testing and validation**
- End-to-end tests
- Performance benchmarks
- Failover scenarios

## Benefits

- **~60% reduction in network calls** (batch instead of per-symbol)
- **Instant PortfolioAgent updates** (local DB read <1ms)
- **Consistent data** across all agents
- **Simpler monitoring** (single data source health)
- **Lower latency** (no provider calls for state queries)

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| DataStore corruption | WAL mode, backup on startup |
| Partial fetch failures | Retry logic, per-symbol error capture |
| Memory growth | Periodic cleanup (keep 2 years daily) |
| Migration complexity | Gradual rollout with fallback to existing |

## Estimated Effort

- 2–3 days for implementation and testing
- Low risk: fallback paths to existing DataAgent behavior

## Next Step

Create branch `data-store-architecture` and start Phase 1.

---

**Author:** Trade Master  
**Date:** 2026-04-01  
**Status:** Proposed
