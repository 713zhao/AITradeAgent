# MarketScannerAgent - Specification & Design

**Agent ID:** `market_scanner_agent`  
**File:** `finance_service/agents/market_scanner_agent.py`  
**Status:** ✅ Production-ready, 3-tier architecture  
**Version:** 2.0  
**Last Updated:** 2026-03-30

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

### Process
1. **Per-theme scanning**: For each theme, fetch OHLCV data for all symbols
2. **Liquidity filtering**: Remove symbols below minimum volume threshold
3. **Composite ranking**: Score each symbol using 5-factor model
4. **Top-N selection**: Select top `discovery_top_n_per_theme` per theme
5. **Watchlist construction**: Merge results into unified watchlist with ratings
6. **Event publication**: Publish `MARKET_SCANNED` with rated symbols

### 5-Factor Composite Scoring

| Factor | Weight | Description |
|--------|--------|-------------|
| Technical | 30% | RSI, MACD, Bollinger position |
| Momentum | 20% | 5-day vs 20-day returns, acceleration |
| Value | 20% | Distance from 52-week range |
| Trend | 20% | SMA50/SMA200 alignment, price vs SMA |
| Liquidity | 10% | Volume vs 20-day average |

### Discovery Output Payload

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
| `investment_themes.*.symbols` | (per theme) | Symbol universe per theme |

---

## Testing

```bash
cd /home/eric/.openclaw/workspace/AITradeAgent
source venv/bin/activate
python -m pytest tests/test_market_scanner_agent.py -v
```

---

## Summary

MarketScannerAgent v2.0 implements a 3-tier architecture:
- **Daily discovery** ranks 100 symbols using 5-factor composite scoring, selecting top 10 per theme
- **15-min price monitor** provides lightweight quote refresh for the watchlist + held positions
- **5-min exit monitor** (delegated to ExitAgent) checks positions for stop-loss and strategic degradation

This separation eliminates redundant full-pipeline runs, reducing API calls by ~90% during intraday monitoring while maintaining comprehensive daily discovery.
