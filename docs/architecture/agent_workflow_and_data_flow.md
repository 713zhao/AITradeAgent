# AiTradeAgent Architecture & Data Flow

**Version:** 2026-03-29  
**Status:** Operational  
**Service:** Finance (port 8801)

---

## Table of Contents
1. [Agent Overview](#agent-overview)
2. [Complete Signal Generation Sequence](#complete-signal-generation-sequence)
3. [Data Retrieval & Caching Deep Dive](#data-retrieval--caching-deep-dive)
4. [Agent Schedule Summary](#agent-schedule-summary)
5. [Outputs and Events](#outputs-and-events)
6. [Key Points](#key-points)

---

## Agent Overview

| Agent | Role | Trigger | Frequency |
|-------|------|---------|-----------|
| **SchedulerAgent** | Publishes scheduled triggers (market scan, data refresh, health check, daily report) | Starts at service boot | Continuous loop |
| **MarketScannerAgent** | Produces list of candidate symbols to analyze | `MARKET_SCAN_TRIGGER` event | Every 15 minutes (scheduled) |
| **DataAgent** | Fetches OHLCV data for a symbol | `DATA_FETCH_REQUEST` (per symbol) | On-demand, per symbol |
| **NewsAgent** | Fetches and analyzes recent news, sentiment, catalysts | `NEWS_FETCH_REQUEST` (per symbol) | On-demand, per symbol |
| **AnalysisAgent** | Calculates technical indicators (RSI, MACD, SMA/EMA, Bollinger, Stochastic, regime score) | `ANALYSIS_REQUEST` (per symbol) | On-demand, per symbol |
| **StrategyAgent** | Applies trading rules to produce trade proposals (BUY/SELL/WAIT) with position sizing | `STRATEGY_REQUEST` (per symbol) | On-demand, per symbol |
| **RiskAgent** | Validates proposals against risk policy (position limits, stop-loss, confidence thresholds) | `RISK_ASSESSMENT_REQUEST` (per proposal) | On-demand, per trade proposal |
| **ExecutionAgent** | Simulates (paper) or sends trade to broker | `EXECUTE_TRADE_REQUEST` (per approved proposal) | On-demand, per approved trade |
| **PortfolioAgent** | Maintains positions, cash, P&L; persists trades | `TRADE_EXECUTED`, `GET_PORTFOLIO_STATE` | On trade event + on request |
| **HealthAgent** | Monitors system health; sends Telegram alerts on issues, trade notifications | `HEALTH_CHECK_TRIGGER`, `TRADE_EXECUTED` | Every 4 hours (scheduled) + trade events |
| **TelegramAgent** | Handles incoming Telegram commands and sends messages | Internal; started at boot | Continuous polling (PTB `run_polling`) |
| **Orchestrator** | Coordinates everything; subscribes to events and invokes handlers | All events via EventBus | Continuous |

---

## Complete Signal Generation Sequence

### Trigger Flow (Scheduled)
1. **SchedulerAgent** publishes `MARKET_SCAN_TRIGGER` event every 15 minutes.
2. **Orchestrator.handle_market_scan_trigger** checks if US or HK market is open; if closed, it exits early (no scan on weekends/after hours).
3. **MarketScannerAgent.run()** reads `config/finance.yaml` universe themes, compiles symbol list, ranks (currently by theme order unless `min_liquidity` set), truncates to `universe.limit` (default 10), and publishes `MARKET_SCANNED` event:

```python
{
  "agent_id": "market_scanner_agent",
  "status": "opportunity",  # or "success"
  "message": "Discovered N promising symbols.",
  "payload": {
    "symbols": ["0700.HK", "0941.HK", ...],
    "count": N
  },
  "timestamp": datetime
}
```

### Per-Symbol Pipeline (Parallel)
For each symbol in the scanned list, orchestrator spawns parallel tasks via event bus:

4. **DataAgent.run(symbol)** fetches OHLCV data (1d interval, lookback = 365 days by default). Returns `dataframe` in payload.
5. **NewsAgent.run(symbol)** fetches recent news (if enabled) and produces sentiment/catalysts.
6. **AnalysisAgent.run(data_payload)** computes technical indicators on the DataFrame and returns `IndicatorsSnapshot` (current price + all indicator signals).
7. **StrategyAgent.run(indicators_snapshot)** applies the configured strategy rules (e.g., `sma20_trend`). Returns a list of **trade proposals**: `{action, confidence, price, quantity, type}` (BUY/SELL/WAIT).
8. **RiskAgent.run(proposal)** validates the proposal: position size limits, confidence threshold (default >0.9), portfolio risk, cooldown. Returns modified proposal with `decision`, `requires_approval`, and position sizing.
9. **ExecutionAgent.run(decision)** either:
   - If `auto_execute=true` and `decision` is BUY/SELL → immediately executes simulated trade and returns `execution_result`.
   - If `auto_execute=false` (current) → does not execute; decision is recorded but no trade occurs.
10. **PortfolioAgent.run(TRADE_EXECUTED)** (if execution happened) updates positions and cash, persists trade to `storage/portfolio.sqlite`, and emits portfolio state changes.
11. **HealthAgent** (via orchestrator handler) sends a Telegram notification of the trade (if Telegram enabled).

All steps 4–11 run concurrently per symbol, limited by the number of symbols from the scan (typically 10 on schedule).

---

## Data Retrieval & Caching Deep Dive

### Data Sources
- **Primary:** Yahoo Finance (`yfinance`) via `YfinanceProvider`
- **Alternate:** Alpha Vantage (optional, requires API key)
- **News:** Not implemented yet (placeholder)

### DataAgent.run(symbol, ...) Flow
1. Accepts parameters: `symbol`, `interval` (default "1d"), `start_date`, `end_date`, `use_cache` (default True), `refresh_all` (default False).
2. Checks `DataCache` (SQLite in `storage/cache.sqlite`) for a fresh entry:
   - Cache key: `{symbol}:{interval}:{start_date}:{end_date}`
   - TTL: 60 minutes (configurable)
3. If cache hit and not expired → return cached DataFrame.
4. If cache miss or expired:
   - Calls `YfinanceProvider.fetch_ohlcv(symbols, start, end, interval)`.
   - Batch fetch: up to `batch_size` (20) symbols per HTTP request.
   - Parses response into `pd.DataFrame` with columns: `Open`, `High`, `Low`, `Close`, `Volume` (MultiIndex if multiple symbols).
   - Stores result in cache with expiration timestamp.
5. Returns `AgentReport` with `dataframe` in `payload`.

### What Gets Saved in Cache?
- **Raw OHLCV data** exactly as returned by yfinance (parsed DataFrame).
- Stored as **compressed binary** (via `pickle` + `zlib`) in the `data_cache` table:
  ```sql
  CREATE TABLE data_cache (
      cache_key TEXT PRIMARY KEY,
      data BLOB,
      expires_at TIMESTAMP
  )
  ```
- The cache survives service restarts.
- Each symbol/interval/date range combination is cached separately.

### Cache Invalidation
- TTL-based: entries older than 60 minutes are considered stale and will be re-fetched.
- Manual refresh: setting `refresh_all=True` bypasses cache and overwrites entries.
- No automatic invalidation on market hours; relies on TTL.

### Data Flow Example
```
DataAgent.run("NVDA")
  ├─ Check cache for "NVDA:1d:2025-02-22:2026-03-29"
  ├─ If miss → YfinanceProvider.download(["NVDA"], start, end, "1d")
  ├─ Parse into DataFrame (index=date, columns=OHLCV)
  ├─ Serialize + compress → store in data_cache with expires_at = now + 60min
  └─ Return AgentReport(payload={"dataframe": df})
```

---

## Agent Schedule Summary

| Event | Scheduler Interval | Description |
|-------|--------------------|-------------|
| `MARKET_SCAN_TRIGGER` | Every 15 minutes | Starts the symbol scanning pipeline |
| `DATA_REFRESH_TRIGGER` | Every 30 minutes | Placeholder; not currently used |
| `HEALTH_CHECK_TRIGGER` | Every 4 hours | Runs HealthAgent diagnostics |
| `DAILY_REPORT_TRIGGER` | Once per day at 00:00 | Generates and sends daily summary |

---

## Outputs and Events

### Event Flow (simplified)
```
MARKET_SCAN_TRIGGER
  → MarketScannerAgent → MARKET_SCANNED {symbols}
    → For each symbol:
        DATA_FETCH_REQUEST → DataAgent → DATA_FETCH_COMPLETE {dataframe}
        NEWS_FETCH_REQUEST → NewsAgent → NEWS_FETCH_COMPLETE {sentiment}
        ANALYSIS_REQUEST → AnalysisAgent → ANALYSIS_COMPLETE {IndicatorsSnapshot}
        STRATEGY_REQUEST → StrategyAgent → STRATEGY_COMPLETE {proposals}
        RISK_ASSESSMENT_REQUEST → RiskAgent → RISK_COMPLETE {decision}
        EXECUTE_TRADE_REQUEST? → ExecutionAgent → EXECUTION_COMPLETE {result}
          → TRADE_EXECUTED → PortfolioAgent → PORTFOLIO_UPDATE
            → HealthAgent → Telegram notification (if enabled)
```

### Key Payloads

- **IndicatorsSnapshot** (from AnalysisAgent):
  ```python
  IndicatorsSnapshot(
      symbol="NVDA",
      timestamp=datetime,
      indicators={
          'rsi': IndicatorResult(name='rsi', value=42.65, signal=SignalType.HOLD, ...),
          'macd': IndicatorResult(...),
          'sma_20': IndicatorResult(...),
          'sma_50': IndicatorResult(...),
          'sma_200': IndicatorResult(...),
          'ema_12': IndicatorResult(...),
          'ema_26': IndicatorResult(...),
          'atr': IndicatorResult(...),
          'bb': IndicatorResult(...),
          'stoch': IndicatorResult(...),
          'regime_score': IndicatorResult(...)
      },
      current_price=493.40
  )
  ```

- **Trade Proposal** (from StrategyAgent):
  ```python
  {
      "action": "BUY",            # or SELL, WAIT
      "confidence": 0.95,
      "price": 150.25,
      "quantity": 10,
      "type": "market"或"limit"
  }
  ```

- **ExecutionResult** (from ExecutionAgent):
  ```python
  {
      "symbol": "NVDA",
      "action": "BUY",
      "quantity": 10,
      "price": 150.25,
      "filled_price": 150.27,
      "commission": 0.0,
      "status": "FILLED",
      "order_id": "SIM_001",
      "timestamp": "2026-03-29T09:15:00"
  }
  ```

---

## Key Points

- The pipeline is **event-driven**; agents publish/subscribe on the EventBus.
- The **Orchestrator** subscribes to all key events and orchestrates the per-symbol workflow.
- Only **one agent writes** to the database (PortfolioAgent via TradeRepository); others read only.
- **TelegramAgent** and **SchedulerAgent** run continuously as background tasks.
- **MarketScannerAgent** runs only on trigger (scheduled or manual).
- **Weekend behavior**: Market scan exits early if both US and HK markets closed (per `is_us_market_open()` / `is_hk_market_open()`). Other agents may still run if triggered, but data fetches often return stale or empty data causing skipped trades.
- **Caching**: OHLCV data is cached for 60 minutes to reduce yfinance API load and improve latency.
- **Concurrency**: All symbols from the scan are processed in parallel using asyncio tasks; no sequential per-symbol blocking.
- **Error handling**: Failures in any agent are logged and do not stop the whole pipeline; the orchestrator continues with other symbols.

---

**End of Document**
