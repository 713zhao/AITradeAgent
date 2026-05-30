# MarketScannerAgent - Specification & Design

**Agent ID:** `market_scanner_agent`  
**File:** `finance_service/agents/market_scanner_agent.py`  
**Status:** ✅ Production-ready, 3-tier architecture  
**Version:** 2.1  
**Last Updated:** 2026-05-30

---

## Overview

MarketScannerAgent implements a **3-tier scanning architecture** that separates discovery from price monitoring:

| Tier | Purpose | Frequency | Method |
|------|---------|-----------|--------|
| **Tier 1: Discovery** | Full universe scan → rank → build watchlist | Daily | `run()` |
| **Tier 2: Price Monitor** | Lightweight quote refresh for watchlist + held positions | Every 15 min | `refresh_watchlist_prices()` |
| **Tier 3: Exit Monitor** | Check held positions for stops/degradation | Every 5 min | (ExitAgent) |

---

## Architecture Diagram

```
                        ┌──────────────────────────────────┐
                        │     SchedulerAgent               │
                        │                                  │
                        │  ┌── Daily ──────────────────┐   │
                        │  │ MARKET_SCAN_TRIGGER       │   │
                        │  │ (Tier 1: Discovery)       │   │
                        │  └───────────────────────────┘   │
                        │                                  │
                        │  ┌── Every 15 min ───────────┐   │
                        │  │ PRICE_MONITOR_TRIGGER     │   │
                        │  │ (Tier 2: Price Refresh)   │   │
                        │  └───────────────────────────┘   │
                        │                                  │
                        │  ┌── Every 5 min ────────────┐   │
                        │  │ EXIT_CHECK_TRIGGER        │   │
                        │  │ (Tier 3: Exit Agent)      │   │
                        │  └───────────────────────────┘   │
                        └──────────────────────────────────┘
                                     │
          ┌───────────────────────────┼────────────────────────┐
          │                           │                        │
          ▼                           ▼                        ▼
   ┌──────────────┐          ┌────────────────┐       ┌──────────────┐
   │  Tier 1:     │          │  Tier 2:       │       │  Tier 3:     │
   │  Discovery   │          │  Price Monitor │       │  Exit Agent  │
   │  scanner.run │          │  refresh_watch │       │  exit.run()  │
   │              │          │  list_prices() │       │              │
   │  →MARKET_    │          │  →PRICE_       │       │  →exits      │
   │   SCANNED    │          │   REFRESH_     │       │  →degraded   │
   │              │          │   COMPLETE     │       │              │
   └──────────────┘          └────────────────┘       └──────────────┘
```

---

## Symbol Universe (config/finance.yaml)

The scanner operates on **100 symbols across 5 themes** (20 per theme):

| Theme | Count | Examples |
|-------|-------|---------|
| AI & Machine Learning | 20 | NVDA, MSFT, GOOG, META, AMD, PLTR, ... |
| Semiconductor | 20 | TSM, AVGO, QCOM, INTC, MU, LRCX, ... |
| Cloud & SaaS | 20 | CRM, SNOW, NOW, DDOG, NET, ZS, ... |
| Mega Cap & Blue Chip | 20 | AAPL, AMZN, JPM, V, JNJ, PG, ... |
| Hong Kong | 20 | 9988.HK, 0700.HK, 1810.HK, 9618.HK, ... |

### Scanner Configuration

```yaml
finance:
  scanner:
    discovery_top_n_per_theme: 10    # Keep top 10 per theme after ranking
    price_monitor_top_n: 50          # Max symbols for price monitoring
    price_monitor_interval_minutes: 15
    discovery_interval: daily
```

---

## Tier 1: Discovery Scan — `run()`

### Trigger
`MARKET_SCAN_TRIGGER` event from SchedulerAgent (daily)

### Scan Flow

```
Universe symbols (100)
  → Liquidity filter (min avg daily volume)
    → Downtrend filter  ← hard exclude before scoring
      → Composite scoring (5 components)
        → Top N per theme (downtrend-excluded stocks never appear)
          → Watchlist (≤ 50 symbols)
```

### Process
1. **Per-theme scanning**: For each theme, fetch OHLCV data for all symbols
2. **Liquidity filtering**: Remove symbols below minimum volume threshold (e.g., average daily volume)
3. **Downtrend filtering**: Run a hard exclude check. Downtrending stocks are disqualified (score forced to 0.0, excluded from watchlist).
4. **Composite ranking**: Score remaining symbols using 5-factor model
5. **Top-N selection**: Select top `discovery_top_n_per_theme` per theme (downtrend-excluded stocks never appear)
6. **Watchlist construction**: Merge results into unified watchlist with ratings
7. **Event publication**: Publish `MARKET_SCANNED` with rated symbols

---

## Downtrend Filter (Hard Exclude)

A stock is **disqualified** (score forced to 0.0, excluded from watchlist) if **either** condition is true:

| Condition | Threshold | Rationale |
|---|---|---|
| Price < SMA50 | — | Medium-term downtrend confirmed |
| 3-month return | < −10% | Significant capital deterioration |

**Why this matters for a momentum strategy:**
Entry rules (RSI > 55, MACD > 0) require confirmed upward momentum. Feeding them downtrending stocks produces contradictory signals — the entry rules reject most, but occasionally trigger a buy into a falling knife (as happened with 0175.HK Geely, which fell 14.6% post-entry while the scanner kept rating it rank 3 in the HK theme).

**Trade-off:** Strict. A stock briefly below SMA50 on a normal dip is excluded until it recovers. In a broad bear market, fewer stocks pass and the watchlist shrinks — this is intentional.

---

## 5-Factor Composite Scoring

```
Composite = Technical(30%) + Momentum(20%) + Value(20%) + Trend(20%) + Liquidity(10%)
```

### 1. Technical Score (30%)

Short-term price momentum: 5-day average vs 20-day average.

```
score = clamp(0.5 + (SMA5 − SMA20) / SMA20 × 5,  0, 1)
```

| Example | Score |
|---|---|
| +2% above 20d avg | 0.60 |
| +10% above 20d avg | 1.00 |
| Flat (0%) | 0.50 |

### 2. Momentum Score (20%)

Volume acceleration — confirms buying conviction:

```
score = clamp((recent_5d_vol / avg_20d_vol − 0.5) / 1.5,  0, 1)
```

Volume 2× average → ~0.83. Elevated volume on up-moves is a strong signal.

### 3. Value Score (20%)

PE ratio only (falls back to 0.5 if unavailable):

```
score = clamp(1.0 − (PE − 10) / 30,  0, 1)
```

PE = 10 → 1.0; PE = 40 → 0.0. **Known limitation:** penalises high-growth tech stocks with elevated PE.

### 4. Trend Score (20%)

SMA alignment score — price position relative to key moving averages:

| Condition | Adjustment |
|---|---|
| Base | 0.50 |
| Price > SMA20 | +0.20 |
| Price > SMA50 | +0.20 |
| SMA50 > SMA200 (golden cross) | +0.10 |
| SMA50 < SMA200 (death cross) | −0.20 |

> Since the downtrend filter already excludes `price < SMA50`, the +0.20 for SMA50 alignment almost always triggers for stocks that reach scoring. The effective differentiator is the golden/death cross (+0.10 / −0.20) and SMA20 alignment (+0.20).

### 5. Liquidity Score (10%)

```
score = clamp(avg_daily_volume / 100_000_000,  0, 1)
```

Returns 0.5 for volumes below 10M (not penalised, not rewarded).

---

## Is This Strategy Good? — Assessment

**Yes, for a momentum/trend-following strategy.** The system's entry rules (RSI > 55, MACD > 0) are designed to confirm existing upward momentum, not to catch bottoms. Feeding them downtrending stocks is an internal contradiction.

**Known weaknesses that remain:**

| Issue | Impact |
|---|---|
| PE-only value signal | Growth stocks (PE > 40) are unfairly penalised |
| Volume momentum ignores direction | High sell-off volume scores well |
| SMA50 filter has no band | A stock 0.5% below SMA50 on a 1-day dip is excluded |
| No fundamental quality screen | Technically strong but fundamentally weak stocks can rank high |
| Fixed theme lists | Misses breakout stocks not in any configured theme |

**Potential improvements (not yet implemented):**
- Replace PE-only value score with PEG ratio or revenue growth rate
- Add direction-aware volume (up-day volume vs down-day volume ratio)
- Soften SMA50 filter to SMA50 × 0.97 (3% tolerance band)
- Add a fundamental quality gate (e.g. positive revenue growth, debt/equity < 2)
- Allow dynamic theme list additions

---

## Discovery Output Payload

```python
{
    "agent_id": "market_scanner_agent",
    "status": "opportunity",
    "message": "Tier 1 discovery: 50 symbols across 5 themes",
    "payload": {
        "symbols": ["NVDA", "TSM", "MSFT", ...],       # Flat list
        "rated_symbols": [                               # Detailed ratings
            {"symbol": "NVDA", "theme": "ai_ml", "rating": 0.85, "rank": 1},
            {"symbol": "TSM", "theme": "semiconductor", "rating": 0.82, "rank": 1},
            ...
        ],
        "themes_scanned": ["ai_ml", "semiconductor", "cloud_saas", "mega_cap", "hong_kong"],
        "top_n_per_theme": 10,
        "discovery_timestamp": "2026-03-30T09:00:00"
    }
}
```

### Internal State

After discovery, the agent stores:
- `_watchlist`: List of dicts `{symbol, theme, rating, rank}`
- `_watchlist_symbols`: Set of symbol strings for quick lookup
- `_last_discovery`: Timestamp of last successful discovery

---

## Tier 2: Price Monitor — `refresh_watchlist_prices()`

### Trigger
`PRICE_MONITOR_TRIGGER` event from SchedulerAgent (every 15 min)

### Process
1. **Merge symbols**: Combine watchlist symbols + held positions
2. **Batch fetch**: Use `_fetch_quick_quote()` for lightweight price data
3. **Rate limiting**: Batch size 20, 1-second delay between batches
4. **Publish**: `PRICE_REFRESH_COMPLETE` event with fresh prices

### Price Monitor Output

```python
{
    "agent_id": "market_scanner_agent",
    "status": "success",
    "message": "Tier 2 price refresh: 55 symbols updated",
    "payload": {
        "prices": {
            "NVDA": {"price": 950.00, "volume": 50000000, "change_pct": 2.3},
            "TSM": {"price": 180.50, "volume": 25000000, "change_pct": -0.5},
            ...
        },
        "watchlist_count": 50,
        "held_count": 5,
        "total_refreshed": 55,
        "timestamp": "2026-03-30T09:15:00"
    }
}
```

### Lightweight Quote Fetch

`_fetch_quick_quote(symbol)` uses `yfinance.Ticker.fast_info` for minimal API overhead:
- Returns: `(price, volume, change_pct)` tuple
- Falls back to `_extract_latest_price()` from history if fast_info fails

---

## Tier 3: Exit Monitor (Delegated to ExitAgent)

See [EXIT_AGENT.md](EXIT_AGENT.md). ExitAgent runs every 5 min via `EXIT_CHECK_TRIGGER`.

---

## Accessor Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_watchlist()` | `List[Dict]` | Full watchlist with ratings |
| `get_watchlist_symbols()` | `Set[str]` | Set of symbol strings |

---

## Error Handling

- **Per-symbol failures**: Caught and logged; other symbols continue
- **Empty results**: Returns `AgentReport(status="no_data")` if no symbols pass filters
- **Rate limiting**: 20-symbol batches with 1-second delays
- **Retry**: Exponential backoff on yfinance failures (built into data layer)

---

## Event Flow

### Daily Discovery Flow
```
SchedulerAgent (daily)
  → MARKET_SCAN_TRIGGER
    → Orchestrator.handle_market_scan_trigger()
      → MarketScannerAgent.run()
        → Per-theme: fetch → filter → rank → top N
        → Build watchlist, publish MARKET_SCANNED
          → Orchestrator.handle_market_scanned()
            → Per-symbol: DataAgent → NewsAgent → AnalysisAgent
              → StrategyAgent → RiskAgent → ExecutionAgent
```

### 15-Min Price Refresh Flow
```
SchedulerAgent (every 15 min)
  → PRICE_MONITOR_TRIGGER
    → Orchestrator.handle_price_monitor()
      → market_scanner_agent.refresh_watchlist_prices(held_symbols)
        → Batch quote fetch for watchlist + held
        → Publish PRICE_REFRESH_COMPLETE
```

---

## Configuration Reference

| Config Key | Default | Description |
|-----------|---------|-------------|
| `scanner.discovery_top_n_per_theme` | 10 | Symbols to keep per theme after ranking |
| `scanner.price_monitor_top_n` | 50 | Max symbols for price monitoring |
| `scanner.price_monitor_interval_minutes` | 15 | Price refresh interval |
| `scanner.discovery_interval` | daily | How often to run full discovery |
| `universe.themes` | (per theme) | Symbol universe per theme |

---

## Recent Fixes

### 2026-05-30 Fixes
- **Downtrend Filter Bug (Trend Score Market-Cap Proxy):** Previously `_calc_trend_score(fundamentals)` measured **market cap size**, not price trend. Large-cap stocks in confirmed downtrends (e.g. Geely 0175.HK at −14.6%) received full trend scores of 1.0, allowing them into the watchlist despite months of falling prices. Fixed by having `_calc_trend_score(prices)` measure SMA stack alignment, and adding the separate `_is_downtrend(prices)` hard filter to eliminate downtrending stocks before scoring.
- **Top N Selection Bug:** `ranked[:top_n]` was selecting the top-N from all scored stocks, including downtrend-filtered stocks with score 0.0. If a theme had fewer than N clean candidates, downtrend stocks would fill the remaining slots. Fixed by filtering to `score > 0.0` before slicing.
- **Scoring Near-0.5 Fallback Bug:** `_extract_prices` and `_extract_volumes` iterated `df_dict.values()` looking for row-major records `{"close": 22.05}`. But `df.to_dict()` returns **column-major** format `{"close": {0: 22.05, 1: 21.9, ...}}`. Every iteration saw a dict with integer keys, `"close" in record` was always `False`, and both methods returned empty lists. As a result, all scoring sub-functions fell back to `0.5`, the downtrend filter never triggered, and every stock in every scan had a score near `0.5` regardless of actual price behaviour. Fixed by reading the column directly via `df_dict.get("close")`.

### 2026-03-31 Fixes
- **Ranking now uses real data:** Previously `run()` was called without `data_agent`, causing all ratings to default to 0.5. Fixed orchestrator to pass `data_agent=self.data_agent`. Watchlist now shows differentiated 0-1 composite scores.
- **Event bus timeout increased:** Timeout for `MARKET_SCAN_TRIGGER` raised from 60s to 300s to allow full 100-symbol scan to complete without giving up.
- **Concurrent scanning improvement:** Data fetches run in parallel across symbols; ranking is sequential but now uses cached data when available, reducing total runtime.

*(Note: For scans triggered outside market hours, the orchestrator still enforces market hours check (skips if both US and HK closed). This can be temporarily disabled for debugging.)*

---

## Testing

```bash
cd /home/eric/.openclaw/workspace/AITradeAgent
source venv/bin/activate
python -m pytest tests/test_market_scanner_agent.py -v
```

---

## Summary

MarketScannerAgent v2.1 implements a 3-tier architecture:
- **Daily discovery** ranks 100 symbols using 5-factor composite scoring (Technical, Momentum, Value, Trend, Liquidity) and applies a strict downtrend filter, selecting top 10 per theme
- **15-min price monitor** provides lightweight quote refresh for the watchlist + held positions
- **5-min exit monitor** (delegated to ExitAgent) checks positions for stop-loss and strategic degradation

This separation eliminates redundant full-pipeline runs, reducing API calls by ~90% during intraday monitoring while maintaining comprehensive daily discovery.