# AITradeAgent - Current Production Architecture

**Version:** 2.1  
**Last Updated:** 2026-03-31  
**Scope:** Active agents wired into `app.py` orchestrator  
**Status:** Production-ready, fully operational

---

## Quick Summary

**Currently Running:** 13 active agents wired into the orchestrator  
**3-Tier Architecture:**
- **Tier 1 (Daily):** Discovery Scan → 100 symbols → rank → top 10/theme → full pipeline
- **Tier 2 (15 min):** Lightweight price refresh for watchlist + held positions
- **Tier 3 (5 min):** ExitAgent monitors held positions (reactive + strategic)
**Interface:** Telegram bot for commands and notifications

**Recent Resolutions (2026-03-30/31):**
- ✅ Position corruption: added `entry_price` alias to Position model
- ✅ IndicatorsSnapshot compatibility: added `.get()` method for dict-like access
- ✅ Market scan rankings: real 0-1 composite scores (was uniform 0.5)
- ✅ Event bus timeout: increased to 300s for long scans
- ✅ Portfolio performance endpoint: `/portfolio/performance` now available
- ✅ Telegram routing: fixed config override bug
- ✅ Equity NaN issue: guarded against invalid prices
- ✅ Auto-execute: enabled at confidence 0.8 (was 1.0)

---

## Production Agent Inventory

| # | Agent | Status | Role |
|---|-------|--------|------|
| 1 | MainOrchestratorAgent | ✅ Active | Central coordinator, event router |
| 2 | SchedulerAgent | ✅ Active | Periodic triggers (scan, refresh, reports) |
| 3 | MarketScannerAgent | ✅ Active | Symbol discovery from configured themes |
| 4 | DataAgent | ✅ Active | OHLCV + fundamentals per symbol |
| 5 | NewsAgent | ✅ Active | News sentiment analysis per symbol |
| 6 | AnalysisAgent | ✅ Active | Technical indicators (RSI, MACD, SMAs, ATR) |
| 7 | StrategyAgent | ✅ Active | Rule-based trade proposal generation |
| 8 | RiskAgent | ✅ Active | Risk policy enforcement + approval workflow |
| 9 | ExecutionAgent | ✅ Active | Order submission to broker |
| 10 | PortfolioAgent | ✅ Active | Holdings tracking + P&L calculation |
| 11 | LearningAgent | ✅ Active | Trade outcome analysis + recommendations |
| 12 | HealthAgent | ✅ Active | Monitor system health + Telegram messages |
| — | TelegramAgent | ✅ Active | User interface + notifications |
| 13 | ExitAgent | ✅ Active | Reactive exits + strategic re-analysis (every 5 min) |

---

## Production Event Flow (Current)

```
Trading Pipeline (Daily):
1. SchedulerAgent emits MARKET_SCAN_TRIGGER at market open
   ↓
2. MarketScannerAgent returns list of symbols (e.g., 24 promising stocks)
   ↓
3. Orchestrator spawns DataAgent per symbol (parallel)
   ↓
4. For each symbol, orchestrator spawns:
   • NewsAgent (sentiment analysis)
   • AnalysisAgent (technical indicators)
   in PARALLEL
   ↓
5. When BOTH news + analysis are ready for a symbol:
   → StrategyAgent generates trade proposal
   ↓
6. RiskAgent validates proposal against risk limits
   ↓
7. If auto_execute=true and risks pass:
   → ExecutionAgent submits order
   Else:
   → Telegram approval request sent to user
   ↓
8. On TRADE_EXECUTED:
   → PortfolioAgent updates holdings
   → LearningAgent logs outcome
   → HealthAgent sends Telegram confirmation
   ↓
9. Daily EOD: SchedulerAgent emits DAILY_REPORT_TRIGGER
   → HealthAgent sends portfolio summary to Telegram

Monitoring Loop (Every 5 min):
10. SchedulerAgent emits EXIT_CHECK_TRIGGER
    ↓
11. Orchestrator retrieves portfolio positions from PortfolioAgent
    ↓
12. ExitAgent.run(positions, perform_strategy_check=True):
    • Reactive: checks stop-loss / take-profit triggers
    • Strategic: re-analyzes via AnalysisAgent (RSI, trend)
    ↓
13. If exits triggered → Telegram alert sent
    If degradation detected → POSITION_DEGRADED event emitted
```

---

## Current Agent Descriptions (What's Running)

---

### 1. MainOrchestratorAgent
**File:** `app.py` (lines ~50–450)  
**Status:** ✅ Fully operational

Central event coordinator. Subscribes to all events and routes work to appropriate agents.

**Key responsibilities:**
- Manages per-symbol buffers (waits for both news + analysis before triggering strategy)
- Chains agents in the correct sequence
- Handles all 11 active event subscriptions

**Wired to:** ALL other 11 agents (direct `run()` calls)

---

### 2. SchedulerAgent
**File:** `scheduler_agent.py`  
**Status:** ✅ Active, background loop

Fires periodic triggers throughout the day.

**Currently emits (3-tier scheduling):**
- `MARKET_SCAN_TRIGGER` — daily (Tier 1: full discovery scan)
- `PRICE_MONITOR_TRIGGER` — every 15 min (Tier 2: lightweight price refresh)
- `EXIT_CHECK_TRIGGER` — every 5 min (Tier 3: exit monitoring)
- `DATA_REFRESH_TRIGGER` — every 30 min (general data warming)
- `DAILY_REPORT_TRIGGER` — end-of-day summary
- `SCHEDULE` — every 4 hours (health check)

---

### 3. MarketScannerAgent (3-Tier Architecture)
**File:** `market_scanner_agent.py`  
**Status:** ✅ Operational — 3-tier scanning

Discovers and monitors symbols using a 3-tier approach:

**Tier 1 — Discovery (`run()`):**
- Scans 100 symbols across 5 themes (20/theme: AI, Semiconductor, Cloud, MegaCap, HK)
- 5-factor composite ranking: Technical 30% + Momentum 20% + Value 20% + Trend 20% + Liquidity 10%
- Selects top 10 per theme → builds watchlist with ratings
- Publishes `MARKET_SCANNED` with `rated_symbols` payload

**Tier 2 — Price Monitor (`refresh_watchlist_prices()`):**
- Lightweight quote fetch for watchlist + held positions
- Batch processing (20 symbols/batch, 1s delay)
- Publishes `PRICE_REFRESH_COMPLETE`

---

### 4. DataAgent
**File:** `data_agent.py`  
**Status:** ✅ Operational

Fetches OHLCV + fundamental data per symbol.

**Current behavior:**
- Default 365-day lookback (ensures SMA200 can be computed)
- Uses configured data provider (OpenBB / Yahoo Finance / IBKR)
- Caches results to avoid redundant API calls
- Normalizes data format across providers

---

### 5. NewsAgent
**File:** `news_agent.py`  
**Status:** ✅ Operational

Analyzes news sentiment for symbols.

**Current behavior:**
- Fetches recent news articles per symbol
- Sentiment analysis: bullish / bearish / neutral
- Returns sentiment score (0.0 to 1.0)
- Identifies catalysts if available

---

### 6. AnalysisAgent
**File:** `analysis_agent.py`  
**Status:** ✅ Operational

Computes technical indicators from OHLCV data.

**Current indicators:**
- RSI (14-period)
- MACD + signal line
- SMA 20, 50, 200
- ATR (volatility)
- Bollinger Bands
- Trend classification (bullish/bearish/neutral)

---

### 7. StrategyAgent
**File:** `strategy_agent.py`  
**Status:** ✅ Operational

Generates BUY/SELL/HOLD proposals based on rule-based strategy.

**Current behavior:**
- Evaluates `RuleStrategy` rules against indicator values
- Combines technical signals + news sentiment
- Checks portfolio to avoid duplicate positions
- Calculates confidence score, entry, stop-loss, take-profit
- Returns proposals only if confidence > `confidence_threshold` (default 0.70)

---

### 8. RiskAgent
**File:** `risk_agent.py`  
**Status:** ✅ Operational

Enforces risk management policies.

**Current checks:**
- Max position size per symbol (e.g., 10% of portfolio)
- Max total portfolio exposure (e.g., 80%)
- Max portfolio drawdown tolerance (e.g., 15%)
- Duplicate position check
- Sector concentration limits

**Output:**
- `RISK_CHECK_COMPLETE` — all checks passed, safe to execute
- `APPROVAL_REQUIRED` — requires human Telegram approval
- `RISK_ALERT` — limit breach warning

---

### 9. ExecutionAgent
**File:** `execution_agent.py`  
**Status:** ✅ Operational

Submits orders to configured broker.

**Current brokers supported:**
- `paper` — simulated paper trading (default for dev/testing)
- `alpaca` — live equity trading
- `ibkr` — live trading via Interactive Brokers

**Current behavior:**
- Takes approved trade from RiskAgent
- Submits order to broker
- Returns fill price, order ID, status

---

### 10. PortfolioAgent
**File:** `portfolio_agent.py`  
**Status:** ✅ Operational

Maintains portfolio state and metrics.

**Current capabilities:**
- Tracks open positions (symbol, quantity, entry price, stop-loss, take-profit)
- Updates positions on each execution
- Calculates P&L metrics (total equity, cash, position P&L, return %)
- Serves as single source of truth for holdings
- Responds to `GET_PORTFOLIO_STATE` queries from Telegram

---

### 11. LearningAgent
**File:** `learning_agent.py`  
**Status:** ✅ Operational

Analyzes trade outcomes to identify patterns.

**Current metrics tracked:**
- Win rate (% of profitable trades)
- Avg return % per trade
- Total trades executed
- Sharpe ratio
- Detects winning vs losing trade patterns

**Output:**
- Recommendations for strategy adjustments
- Flags parameter adjustments if needed

---

### 12. HealthAgent
**File:** `health_agent.py`  
**Status:** ✅ Operational

Monitors system health and sends Telegram notifications.

**Current responsibilities:**
- Live portfolio health metrics
- Anomaly detection (unusual drawdown, stale data)
- Trade confirmation messages to Telegram
- Daily P&L summary reports
- System status replies to `/status` command

---

### 13. ExitAgent
**File:** `exit_agent.py`  
**Status:** ✅ Operational (wired via `EXIT_CHECK_TRIGGER` every 5 min)

Monitors held positions for exit conditions and strategic degradation.

**Dual-mode operation:**
- **Reactive exits:** Checks stop-loss (`current_price ≤ stop_loss_price`) and take-profit (`current_price ≥ take_profit_price`)
- **Strategic re-analysis:** Fetches fresh data, runs AnalysisAgent, flags if RSI > 70 (overbought) or trend is bearish

**Integration flow:**
- SchedulerAgent → `EXIT_CHECK_TRIGGER` → Orchestrator → `PortfolioAgent.get_positions()` → `ExitAgent.run()` → Telegram alerts

---

### 14. TelegramAgent
**File:** `telegram_agent.py`  
**Status:** ✅ Operational, always listening

User interface via Telegram bot.

**Current commands:**
- `/start` — Welcome message
- `/status` — Show all agent statuses
- `/portfolio` — Show current holdings + equity

**Automatic messages sent by system:**
- Market scan summaries
- Trade confirmations (via HealthAgent)
- Daily P&L reports
- Approval requests (when APPROVAL_REQUIRED)
- Error alerts

---

## Production Configuration

**Key settings in `finance.yaml`:**

```yaml
finance:
  execution:
    broker: paper              # Paper trading (simulated)

  risk:
    max_position_pct: 0.01    # 1% max per symbol (Kelly-inspired)
    max_total_exposure_pct: 0.80  # 80% max total
    max_daily_loss_pct: 0.02  # Halt if daily loss >2%
    max_drawdown_pct: 0.15    # Halt at 15% drawdown
    default_risk_budget_pct: 0.01

  strategy:
    type: sma20_trend          # Current active strategy
    auto_execute:
      enabled: true            # Auto-execute approved trades
      confidence_threshold: 0.8  # Minimum 0.8 confidence (0-1 scale)
      require_approval: false  # No manual approval needed
    indicators:
      rsi:
        enabled: true
        period: 14
        oversold: 40
        overbought: 65
      macd:
        enabled: true
        fast_period: 12
        slow_period: 26
        signal_period: 9
      sma:
        enabled: true
        periods: [10, 20, 50]
      atr:
        enabled: true
        period: 14
    rules:
      rsi_entry_oversold: true
      rsi_entry_oversold_threshold: 40
      macd_crossover: true
      price_above_sma10: true
      rsi_exit_overbought: true
      rsi_exit_overbought_threshold: 65
      macd_signal_exit: true
      stop_loss_enabled: true
      take_profit_enabled: true

  universe:
    themes:
      - name: AI
        symbols: [NVDA, PLTR, UPST, AVGO, MSTR, AI, SYM, PATH, BBAI, SOUN, GFAI, AITX, PRCT, LQDA, EXAI, HIMS, GRAB, IONQ, RGTI, QUBT]
      - name: Semiconductor
        symbols: [TSM, QCOM, AMD, ASML, ASR, INTC, MU, MRVL, ADI, NXPI, KLAC, LRCX, AMAT, ON, SWKS, ARM, MCHP, TXN, GFS, WOLF]
      - name: Cloud
        symbols: [CRWD, DDOG, NET, MDB, SNOW, ZS, PANW, FTNT, S, OKTA, TEAM, HUBS, VEEV, BILL, MNDY, NOW, WDAY, ADBE, CRM, SHOP]
      - name: MegaCap
        symbols: [MSFT, GOOGL, AAPL, AMZN, META, TSLA, BRK-B, LLY, V, UNH, JPM, XOM, JNJ, WMT, MA, PG, COST, HD, NFLX, ORCL]
      - name: Hong Kong
        symbols: [0700.HK, 9988.HK, 0941.HK, 1398.HK, 0388.HK, 2318.HK, 0005.HK, 1299.HK, 0027.HK, 0003.HK, 9618.HK, 9999.HK, 3690.HK, 1810.HK, 0966.HK, 0175.HK, 2382.HK, 0883.HK, 0002.HK, 0001.HK]
    all_symbols: [auto-generated list of 100]
    whitelist:
      enabled: false
      symbols: []

  data:
    default_interval: 1d
    default_lookback_days: 120
    cache_ttl_minutes: 5
    cache_enabled: true
    batch_size: 20
    batch_delay_sec: 1.0

  scanner:
    discovery_top_n_per_theme: 10   # Top 10 per theme after ranking
    price_monitor_top_n: 50         # Max symbols for price monitoring
    price_monitor_interval_minutes: 15
    discovery_interval: daily

  performance:
    max_workers: 4
    api_timeout_sec: 30
    api_retries: 3

---

## Daily Workflow

```
Morning (Tier 1 — Daily Discovery):
└─ SchedulerAgent fires MARKET_SCAN_TRIGGER
└─ MarketScannerAgent.run() scans 100 symbols across 5 themes
   └─ Per-theme: fetch OHLCV → filter liquidity → 5-factor rank → top 10
   └─ Builds watchlist with ratings (50 symbols)
└─ Orchestrator runs full pipeline per discovered symbol:
   └─ DataAgent → NewsAgent + AnalysisAgent → StrategyAgent → RiskAgent → ExecutionAgent
└─ PortfolioAgent updates holdings
└─ HealthAgent sends Telegram notifications

Throughout Day (Tier 2 — Price Monitor, every 15 min):
└─ SchedulerAgent emits PRICE_MONITOR_TRIGGER
└─ Orchestrator calls scanner.refresh_watchlist_prices()
   └─ Lightweight quote fetch for watchlist + held positions
   └─ Publishes PRICE_REFRESH_COMPLETE

Throughout Day (Tier 3 — Exit Monitor, every 5 min):
└─ SchedulerAgent emits EXIT_CHECK_TRIGGER
└─ Orchestrator retrieves positions → ExitAgent.run()
   └─ Reactive: stop-loss / take-profit checks
   └─ Strategic: re-analysis via AnalysisAgent (RSI, trend)
└─ Telegram alerts for exits or degraded positions

End of Day (Market Close):
└─ SchedulerAgent fires DAILY_REPORT_TRIGGER
└─ HealthAgent compiles portfolio metrics
└─ TelegramAgent sends daily P&L summary
```

---

## Known Limitations (Current Production)

| Issue | Impact | Status |
|-------|--------|--------|
| ~~ExitAgent not wired~~ | ✅ ExitAgent wired — Tier 3 every 5 min | Completed |
| ~~No ranking/scoring~~ | ✅ 5-factor composite scoring in Tier 1 | Completed |
| ~~Small symbol universe~~ | ✅ Expanded to 100 symbols (20/theme) | Completed |
| ~~Full pipeline every 15 min~~ | ✅ Separated into daily discovery + 15-min price monitor | Completed |
| Approval workflow mocked | Auto-approval for testing | ✅ By design |

---

## Feature Status (as of 2026-03-31)

| Feature | Status |
|---------|--------|
| Active agents | 13 (all wired) |
| Symbol universe | 100 symbols across 5 themes |
| Scanning | 3-tier: discovery (daily) + price monitor (15min) + exit (5min) |
| Ranking | 5-factor composite scoring (0-1) with real data |
| Exit management | Reactive (stops/profits) + strategic (re-analysis) |
| Risk checks | Portfolio exposure, position size, drawdown, duplicates |
| Data providers | Yahoo Finance (yfinance) |
| Auto-execution | Enabled (confidence ≥ 0.8) |
| Position model | `entry_price` alias (compatible with broker-style code) |
| IndicatorsSnapshot | Dict-like `.get()` for compatibility |
| Event bus timeout | 300s for long-running scans |
| API endpoints | `/health`, `/portfolio/state`, `/portfolio/performance`, `/api/dashboard/*` |
| Telegram routing | Fixed (uses .env fallback) |

---

## Recent Critical Fixes (2026-03-30/31)

| Fix | Description |
|-----|-------------|
| Position corruption | Added `entry_price` property alias to Position class; `to_dict()` now includes `entry_price`. Resolved NaN equity caused by missing entry price. |
| IndicatorsSnapshot compatibility | Added `.get()` method to support dict-like access; fixed ExitAgent AttributeError. |
| Market scan rankings | Fixed `handle_market_scan_trigger` to pass `data_agent`; rankings now computed (0-1) instead of uniform 0.5. |
| Event bus timeout | Increased from 60s to 300s to allow full universe scans to complete. |
| Missing performance endpoint | Added `/portfolio/performance` route (alias to `/api/dashboard/performance`). |
| Telegram config override | Orchestrator no longer overrides Telegram settings with empty YAML values; falls back to .env. |
| Equity NaN guard | `Position.market_value()` guards against invalid `current_price`; price updates validated. |
| Auto-execute threshold | Changed from 1.0 → 0.8 to allow more trades while maintaining confidence filter. |

All systems verified healthy and operational.

---

## How to Use This Document

- **For operations:** Follow the "Daily Workflow" section
- **For troubleshooting:** Check agent-specific docs in `/docs`
- **For development:** See `AGENT_ARCHITECTURE.md` for full system design including proposed enhancements
- **For status:** Run `curl http://localhost:8801/health` and `/portfolio/state`

---

## Files Reference

| Purpose | File |
|---------|------|
| **This file** | `CURRENT_ARCHITECTURE.md` (production state) |
| **Full design** | `AGENT_ARCHITECTURE.md` (comprehensive, all agents + proposed) |
| **Roadmap** | `NEXT_STEPS.md` (planned enhancements) |
| **Code** | `finance_service/app.py` (orchestrator) |
| **Config** | `finance.yaml` (all settings) |
