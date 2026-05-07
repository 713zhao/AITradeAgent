# AITradeAgent - Full System Architecture

**Version:** 4.0  
**Last Updated:** 2026-04-04  
**Source:** `finance_service/agents/` + `finance_service/app.py`

---

## System Overview

AITradeAgent is an **autonomous multi-agent trading research system** built around an event-driven architecture. A central `MainOrchestratorAgent` wires together 13 specialized agents, each with a single responsibility. Agents communicate via an async **Event Bus** — no agent directly calls another; they publish and subscribe to named events.

The system continuously scans markets, analyzes candidates, generates trade proposals, enforces risk rules, executes orders, monitors positions, and reports everything to Telegram.

**Phase 3 addition:** An LLM-powered pre-selection layer sits between discovery and analysis. After `MarketScannerAgent` discovers up to 50+ candidates, `SymbolSelectorAgent` uses `MarketRegimeAgent` and `MacroNewsAgent` context to rank them via LLM and return the top 5–10 highest-conviction symbols. Only these proceed to deep analysis — reducing cost and noise.

---

## High-Level Architecture

```
                         ┌──────────────────────────────┐
                         │   Telegram / User Interface  │
                         │  /status  /portfolio  alerts │
                         └──────────┬───────────────────┘
                                    │
                         ┌──────────▼───────────────────┐
                         │    MainOrchestratorAgent      │
                         │  (app.py - event coordinator) │
                         │  Subscribes to all events;    │
                         │  routes between agents        │
                         └──────────┬───────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
┌──────────────────────┐ ┌──────────▼────────┐      ┌──────────▼──────────┐
│  SchedulerAgent      │ │ Trading Pipeline  │      │  Monitoring Loop    │
│ (continuous loop)    │ │ (main workflow)   │      │(continuous exit/    │
└──────────┬──────────┘  └──────────┬────────┘      │ reanalysis checks) │
           │                        │                └──────────┬──────────┘
    Emits (on schedule):    See pipeline below              │
    • MARKET_SCAN          (per symbol discovery)  Emits: EXIT_CHECK_TRIGGER
      (daily @ 01:00/13:00)  & strategy analysis  (every 5 min)
    • DATA_REFRESH (every 30 min)  │                      │
    • DAILY_REPORT (EOD)           │        ┌─────────────▼─────────┐
    • EXIT_CHECK (every 5 min)     │        │    ExitAgent          │
                                   │        │  (every 5 minutes)    │
                 ┌─────────────────┼────────┤  • Monitor exits      │
                 │                 │        │  • Re-analyze held    │
                 ▼                 │        │    positions          │
    ┌────────────────────────────────┐     │  • Emit signals       │
    │   MarketScannerAgent            │     │          └─────────────┬────────┘
    │   Tier 1: Daily discovery       │     │                       │
    │   Tier 2: Every 15 min prices   │     │     ┌─────────────────┴────────┐
    │   Emits: MARKET_SCANNED         │     │     │(if thesis degrades)     │
    └──────────┬─────────────────────┘     │     │                         │
               │ (50+ candidates)           │     │                         │
    ┌──────────────────────────────────────────────────────────┐
    │    LLM Pre-Selection Pipeline (Phase 3) ✅ (Daily)       │
    │                                                          │
    │  ┌──────────────────────┐  ┌────────────────────────┐   │
    │  │ MarketRegimeAgent    │  │ MacroNewsAgent         │   │
    │  │ (Daily per-market)   │  │ (Daily per-market)     │   │
    │  │ 9 indices: US + HK   │  │ US + HK news feeds     │   │
    │  │ SMA20/50/200         │  │ VADER sentiment        │   │
    │  │ Risk-on/off + regime │  │ categories + catalysts │   │
    │  └────────┬─────────────┘  └──────────┬─────────────┘   │
    │           └────────────┬──────────────┘                  │
    │                        ▼                                 │
    │    SymbolSelectorAgent (LLM ranking)                     │
    │    (Daily per-market: 01:00 HK, 13:00 US)              │
    │    50 candidates → top 5–10 picks                      │
    │    gpt-4o-mini via OpenRouter (~13k tokens)             │
    └──────────────┬───────────────────────────────────────────┘
                   │ (top N symbols)
               │ (per ranked symbol)                  │         │                       │
    ┌──────────▼────────────────────────┐      │    ┌────▼──────────────────┐
    │    RankingAgent (Phase 2)          │      │    │ POSITION_DEGRADED     │
    │  • 5-factor re-ranking             │      │    │ (sent back through    │
    │  • Liquidity, Momentum, Value,    │      │    │  orchestrator for     │
    │    Growth, Quality scoring         │      │    │  strategy recheck)    │
    │  Emits: RANKING_COMPLETE           │      │    └───────────────────────┘
    └──────────┬────────────────────────┘      │
               │ (re-ranked symbols)           │
    ┌──────────▼────────────────────────────┐  │
    │    DataAgent                          │  │
    │    Emits: DATA_FETCH_COMPLETE         │  │
    │           (per re-ranked symbol)      │  │
    └──────────┬────────────────────────────┘  │    ┌────────────────────┐
                                      │    └───────────────────────┘
              ┌──────────────┬────────┴──────────────────┬──────────┐
              │ (parallel)   │ (parallel)               │ (parallel)│
    ┌─────────▼──────┐   ┌───▼──────────┐   ┌──────────▼────────┐
    │  NewsAgent      │   │AnalysisAgent │   │TradingAgentsAnalyz│
    │ Emits: NEWS_    │   │ Emits:       │   │  (Phase 1 - LLM)  │
    │ FETCH_COMPLETE  │   │ANALYSIS_     │   │ Emits: LLM_       │
    │                 │   │COMPLETE      │   │ ANALYSIS_COMPLETE │
    └────────┬────────┘   └───┬──────────┘   │  ▲ via            │
             │                │              │  │ TradingAgentsAPI│
             │                │              └──┼────────────────┘
             │                │                 │ (REST gateway)
             └────────┬───────┴─────────────────┘
                      │(all ready)
         ┌────────────▼──────────────┐
         │   StrategyAgent            │
         │  (enriched with LLM data)  │
         │  Emits: TRADE_PROPOSAL_    │
         │         GENERATED          │
         └────────────┬───────────────┘
                      │
         ┌────────────▼──────────────┐
         │     RiskAgent              │
         │  Emits: RISK_CHECK_        │
         │         COMPLETE           │
         └────────────┬───────────────┘
                      │
         ┌────────────▼──────────────┐
         │   ExecutionAgent           │
         │  Emits: TRADE_EXECUTED     │
         └────────────┬───────────────┘
                      │
         ┌────────────▼──────────────┐
         │   PortfolioAgent           │
         │   Updates holdings         │
         └────────────────────────────┘
```

### Agent Run Frequencies (Illustrated Above)

The diagram shows the event-driven pipeline with these key timing patterns:

| Layer | Agents | Frequency | Trigger | Purpose |
|-------|--------|-----------|---------|---------|
| **Scheduler** | SchedulerAgent | Continuous | Self-loop | Emit periodic triggers |
| **Pre-Market Setup** | MarketRegimeAgent, MacroNewsAgent | Daily per-market | PRE_SCAN_CONTEXT_REFRESH | Pre-warm regime & macro context 5 min before scan |
| **Discovery (Tier 1)** | MarketScannerAgent | Daily @ 01:00 & 13:00 UTC+8 | MARKET_SCAN_TRIGGER | Discover 50+ HK/US candidates |
| **Pre-Selection (Phase 3)** | SymbolSelectorAgent | Daily per-market | MARKET_SCANNED | LLM rank 50→5-10 high-conviction picks |
| **Re-Ranking (Phase 2)** | RankingAgent | Per discovery | MARKET_SCANNED | Multi-factor scoring of all candidates |
| **Data Fetch** | DataAgent | Per-symbol | RANKING_COMPLETE | Fetch OHLCV + fundamentals |
| **Parallel Analysis** | NewsAgent, AnalysisAgent, TradingAgentsAnalyzer | Per-symbol | DATA_FETCH_COMPLETE | News sentiment + technical indicators + LLM analysis |
| **Strategy** | StrategyAgent | Per-symbol | NEWS + ANALYSIS ready | Generate BUY/SELL proposals |
| **Risk Check** | RiskAgent | Per proposal | TRADE_PROPOSAL_GENERATED | Validate against risk limits |
| **Execution** | ExecutionAgent | Per approved trade | RISK_CHECK_COMPLETE | Submit orders |
| **Post-Trade** | PortfolioAgent, LearningAgent, HealthAgent | Per execution | TRADE_EXECUTED | Update holdings; learn; notify |
| **Continuous Monitoring (Tier 3)** | ExitAgent | Every 5 min | EXIT_CHECK_TRIGGER | Check stops/profits & strategic degradation |
| **Intraday Refresh (Tier 2)** | MarketScannerAgent | Every 15 min | PRICE_MONITOR_TRIGGER | Refresh watchlist prices |
| **Periodic Health** | HealthAgent | Every 4 hours | HEALTH_CHECK_TRIGGER | System health check |
| **Daily Summary** | HealthAgent, TelegramAgent | Once daily @ 08:05 UTC | DAILY_REPORT_TRIGGER | Portfolio P&L report |
| **Always-On** | TelegramAgent | Real-time | User commands + events | Handle user interactions + broadcast alerts |

**Key Timing Insights:**
- **01:00 UTC+8**: HK pre-market scan starts (regime + macro pre-warmed)
- **13:00 UTC+8**: US pre-market scan starts (regime + macro pre-warmed)
- **Every 5 min**: ExitAgent monitors positions for stop-loss/take-profit
- **Every 15 min**: Price refresh for watchlist symbols
- **Per-symbol parallelism**: News + Analysis + LLM analysis run in parallel to minimize latency

----

## Agent Inventory

### Core Trading Agents

| # | Agent | `agent_id` | File | Trigger |
|---|-------|-----------|------|---------|
| 1 | MainOrchestratorAgent | `main_orchestrator_agent` | `app.py` | Always running |
| 2 | SchedulerAgent | `scheduler_agent` | `scheduler_agent.py` | Time-based loop |
| 3 | MarketScannerAgent | `market_scanner_agent` | `market_scanner_agent.py` | `MARKET_SCAN_TRIGGER` |
| 4 | DataAgent | `data_agent` | `data_agent.py` | Per-symbol after scan |
| 5 | NewsAgent | `news_agent` | `news_agent.py` | Per-symbol after data |
| 6 | AnalysisAgent | `analysis_agent` | `analysis_agent.py` | Per-symbol after data |
| 7 | RegimeAgent | `regime_agent` | `regime_agent.py` | `ANALYSIS_COMPLETE` (if LLM enabled) |
| 8 | StrategyAgent | `strategy_agent` | `strategy_agent.py` | When news + analysis both ready |
| 9 | RiskAgent | `risk_agent` | `risk_agent.py` | `TRADE_PROPOSAL_GENERATED` |
| 10 | ExecutionAgent | `execution_agent` | `execution_agent.py` | `RISK_CHECK_COMPLETE` |
| 11 | PortfolioAgent | `portfolio_agent` | `portfolio_agent.py` | `TRADE_EXECUTED` |
| 12 | LearningAgent | `learning_agent` | `learning_agent.py` | `TRADE_EXECUTED` |
| 13 | HealthAgent | `health_agent` | `health_agent.py` | `TRADE_EXECUTED`, `SCHEDULE`, `DAILY_REPORT_TRIGGER` |
| 14 | ExitAgent | `exit_agent` | `exit_agent.py` | ✅ Every 5 min via `EXIT_CHECK_TRIGGER` |
| — | TelegramAgent | `telegram_agent` | `telegram_agent.py` | User commands + broadcast messages |

### LLM & Advanced Analysis Agents (Phase 1 - Gemini Integration ✅)

| # | Agent | `agent_id` | File | Purpose |
|---|-------|-----------|------|---------|
| 15 | TradingAgentsAnalyzer | `trading_agents_analyzer` | `trading_agents_analyzer.py` | ✅ LLM-powered opportunity analysis using TradingAgents framework (Gemini 2.5) |
| 16 | TradingAgentsAPI | `trading_agents_api` | `trading_agents_api.py` | ✅ REST API gateway for TradingAgents framework multi-agent orchestration |
| — | LLM Config Module | — | `llm_config.py` | ✅ Multi-provider LLM configuration (Gemini, OpenRouter, OpenAI, Anthropic, xAI) |

### Ranking & Interpretability Agents (Phase 2 ✅)

| # | Agent | `agent_id` | File | Purpose |
|---|-------|-----------|------|---------|
| 17 | RankingAgent | `ranking_agent` | `ranking_agent.py` | ✅ Multi-factor symbol ranking with explainability and scoring breakdown |

### LLM Symbol Selection Agents (Phase 3 ✅)

| # | Agent | `agent_id` | File | Purpose |
|---|-------|-----------|------|---------|
| 18 | MarketRegimeAgent | `market_regime_agent` | `market_regime_agent.py` | ✅ Broad market context from 5 indices (SP500/NASDAQ/DOW/VIX/RUSSELL2000); risk-on/off flag, volatility regime, trend strength |
| 19 | MacroNewsAgent | `macro_news_agent` | `macro_news_agent.py` | ✅ Macro news aggregation from SPY/QQQ/DIA feeds; VADER sentiment; categories: monetary_policy, geopolitical, economic_data, regulatory, sector_rotation |
| 20 | SymbolSelectorAgent | `symbol_selector_agent` | `symbol_selector_agent.py` | ✅ LLM-powered symbol ranking; 50 candidates → top 5–10 high-conviction picks; 5-dimension scoring; Telegram report with token usage |

> **Docs:** [MARKET_REGIME_AGENT.md](MARKET_REGIME_AGENT.md) · [MACRO_NEWS_AGENT.md](MACRO_NEWS_AGENT.md) · [SYMBOL_SELECTOR_AGENT.md](SYMBOL_SELECTOR_AGENT.md)

---

## Event Bus — All Events

```
# Scheduling / Triggers
MARKET_SCAN_TRIGGER       ← SchedulerAgent: start Tier 1 discovery scan (daily)
PRICE_MONITOR_TRIGGER     ← SchedulerAgent: start Tier 2 price refresh (every 15 min)
DATA_REFRESH_TRIGGER      ← SchedulerAgent: refresh prices for watched symbols
DAILY_REPORT_TRIGGER      ← SchedulerAgent: send daily summary to Telegram
HEALTH_CHECK_TRIGGER      ← SchedulerAgent: run health check
SCHEDULE                  ← SchedulerAgent: generic periodic tick

# Scan
MARKET_SCANNED            ← MarketScannerAgent: Tier 1 discovery complete (rated symbols)
PRICE_REFRESH_COMPLETE    ← MarketScannerAgent: Tier 2 price data refreshed

# Data
DATA_FETCH_STARTED        ← DataAgent: fetch in progress
DATA_FETCH_COMPLETE       ← DataAgent: OHLCV + fundamentals ready
DATA_READY                ← DataAgent: alias (may be removed)

# News
NEWS_FETCH_COMPLETE       ← NewsAgent: sentiment data ready

# Analysis
ANALYSIS_STARTED          ← AnalysisAgent: computing indicators
ANALYSIS_COMPLETE         ← AnalysisAgent: RSI, MACD, MAs, ATR ready
ANALYSIS_FAILED           ← AnalysisAgent: error

# Regime (Phase 1 - LLM Augmentation)
MARKET_REGIME_UPDATED     ← RegimeAgent: market regime classification (trending, range, vol)

# LLM Analysis (Phase 1 - Gemini Integration)
LLM_ANALYSIS_COMPLETE     ← TradingAgentsAnalyzer: Gemini LLM multi-agent analysis (opportunities, risks)

# Strategy
TRADE_PROPOSAL_GENERATED  ← StrategyAgent: BUY/SELL proposals ready

# Risk
RISK_CHECK_COMPLETE       ← RiskAgent: validated, may proceed to execution
RISK_CHECK_FAILED         ← RiskAgent: check failed
RISK_ALERT                ← RiskAgent: limit breach warning
APPROVAL_REQUIRED         ← RiskAgent: requires human approval via Telegram
TRADE_APPROVED            ← Human approved
APPROVAL_REJECTED         ← Human rejected
APPROVAL_TIMEOUT          ← Approval window expired

# Execution
EXECUTION_STARTED         ← ExecutionAgent: order in flight
TRADE_EXECUTED            ← ExecutionAgent: order filled
EXECUTION_FAILED          ← ExecutionAgent: order failed

# Portfolio
PORTFOLIO_UPDATED         ← PortfolioAgent: holdings updated
TRADE_OPENED              ← PortfolioAgent: new position opened
TRADE_CLOSED              ← PortfolioAgent: position closed
TRADE_STOPPED             ← PortfolioAgent: stop-loss triggered

# Learning
LEARNING_COMPLETE         ← LearningAgent: performance analysis done
LEARNING_FEEDBACK         ← LearningAgent: strategy feedback

# Query events (from Telegram commands)
GET_SYSTEM_STATUS         ← /status command
GET_PORTFOLIO_STATE       ← /portfolio command
GET_HEALTH_STATUS         ← health request

# System
CONFIG_RELOADED           ← Config changed at runtime
BACKTEST_STARTED          ← Backtest mode initiated
BACKTEST_COMPLETE         ← Backtest finished
```

---

## Agent Descriptions

---

### 1. MainOrchestratorAgent

**File:** `finance_service/app.py`  
**Goal:** Orchestrate the end-to-end trading workflow, from market scanning to trade execution and learning.

The central coordinator. It does not implement business logic — it subscribes to events and routes work to the correct next agent in the pipeline.

**Key behaviors:**
- After `DATA_FETCH_COMPLETE`, calls `NewsAgent` and `AnalysisAgent` **in parallel**
- Buffers each result; only triggers `StrategyAgent` once **both** news and analysis are ready for the same symbol (`_try_trigger_strategy_agent`)
- Handles the `TRADE_EXECUTED` fan-out: updates portfolio, triggers learning, and sends Telegram notification all in parallel

**Event subscriptions:**

| Event | Action |
|-------|--------|
| `MARKET_SCAN_TRIGGER` | Runs `MarketScannerAgent.run()` (Tier 1 discovery) |
| `MARKET_SCANNED` | Starts per-symbol full pipeline (data→news→analysis→strategy→risk→execution) |
| `PRICE_MONITOR_TRIGGER` | Runs `MarketScannerAgent.refresh_watchlist_prices()` (Tier 2) |
| `EXIT_CHECK_TRIGGER` | Runs `ExitAgent.run()` on held positions (Tier 3) |
| `DATA_FETCH_COMPLETE` | Runs `NewsAgent` + `AnalysisAgent` in parallel |
| `NEWS_FETCH_COMPLETE` | Buffers; triggers `StrategyAgent` when both ready |
| `ANALYSIS_COMPLETE` | Buffers; triggers `StrategyAgent` when both ready |
| `TRADE_PROPOSAL_GENERATED` | Runs `RiskAgent` |
| `RISK_CHECK_COMPLETE` | Runs `ExecutionAgent` (if `auto_execute` enabled) |
| `APPROVAL_REQUIRED` | Forwards to Telegram for human review |
| `TRADE_EXECUTED` | Runs `PortfolioAgent` + `LearningAgent` + `HealthAgent` |
| `DAILY_REPORT_TRIGGER` | Pulls portfolio metrics; sends Telegram report |
| `GET_SYSTEM_STATUS` | Responds to `/status` Telegram command |

---

### 2. SchedulerAgent

**File:** `finance_service/agents/scheduler_agent.py`  
**Goal:** Automate the execution of periodic tasks, such as market scanning, data fetching, and report generation.

**Runs:** Background loop — active from system startup, never stops.

**Emits (on schedule):**

| Event | Frequency | Purpose |
|-------|-----------|---------|
| `MARKET_SCAN_TRIGGER` | Daily (24h) | Tier 1: Full discovery scan |
| `PRICE_MONITOR_TRIGGER` | Every 15 min | Tier 2: Lightweight price refresh for watchlist |
| `EXIT_CHECK_TRIGGER` | Every 5 min | Tier 3: Position exit monitoring |
| `DATA_REFRESH_TRIGGER` | Every 30 min | General data warming |
| `DAILY_REPORT_TRIGGER` | Daily (EOD) | Send daily Telegram summary |
| `SCHEDULE` | Every 4 hours | Health checks |

**Dependencies:** None — fires first, nothing upstream.

---

### 3. MarketScannerAgent (3-Tier Architecture)

**File:** `finance_service/agents/market_scanner_agent.py`  
**Goal:** Discover promising stocks and maintain real-time watchlist prices via 3-tier scanning.

**Tier 1 — Discovery (daily):** `MARKET_SCAN_TRIGGER` → `run()`
- Scans 100 symbols across 5 themes (20 per theme: AI, Semiconductor, Cloud, MegaCap, Hong Kong)
- Filters by liquidity, ranks by 5-factor composite score
- Selects top 10 per theme → builds watchlist with ratings
- Publishes `MARKET_SCANNED` with `rated_symbols` payload

**Tier 2 — Price Monitor (every 15 min):** `PRICE_MONITOR_TRIGGER` → `refresh_watchlist_prices()`
- Lightweight quote fetch for watchlist + held positions
- Publishes `PRICE_REFRESH_COMPLETE`

**Output Event:** `MARKET_SCANNED` (Tier 1), `PRICE_REFRESH_COMPLETE` (Tier 2)
```python
{
    "agent_id": "market_scanner_agent",
    "status": "opportunity",
    "message": "Tier 1 discovery: 50 symbols across 5 themes",
    "payload": {
        "symbols": ["NVDA", "TSM", "MSFT", ...],
        "rated_symbols": [
            {"symbol": "NVDA", "theme": "ai_ml", "rating": 0.85, "rank": 1},
            ...
        ],
        "themes_scanned": ["ai_ml", "semiconductor", "cloud_saas", "mega_cap", "hong_kong"],
        "top_n_per_theme": 10,
        "discovery_timestamp": "2026-03-30T09:00:00"
    }
}
```

See [MARKET_SCANNER_AGENT.md](MARKET_SCANNER_AGENT.md) for full specification.

---

### 4. DataAgent

**File:** `finance_service/agents/data_agent.py`  
**Goal:** Maintain reliable and up-to-date market data, including OHLCV and fundamental data.

**Trigger:** Called per-symbol by orchestrator after `MARKET_SCANNED`.  
Also triggered by `DATA_REFRESH_TRIGGER` for hourly refreshes.

**Inputs:**
- `symbol` — ticker (e.g., `NVDA`, `700.HK`)
- `interval` — `1d`, `1h`, etc.
- `start_date` / `end_date` — defaults to 365-day lookback (ensures SMA200 has enough data)
- `use_cache` — avoids redundant API calls
- `emit_events` — controls event publishing (set to `False` for simple quote lookups)

**Processing:**
- Fetches OHLCV data from configured provider (OpenBB / Yahoo Finance / IBKR)
- Normalizes data into consistent column format
- Fetches fundamental data (P/E, market cap, etc.)
- Caches results with configurable TTL

**Output Event:** `DATA_FETCH_COMPLETE`
```python
{
    "agent_id": "data_agent",
    "status": "success",
    "payload": {
        "symbol": "NVDA",
        "dataframe": { ... },        # OHLCV as dict of records
        "fundamentals": { ... },     # P/E, market cap, sector, etc.
        "interval": "1d",
        "rows": 252
    }
}
```

---

### 5. NewsAgent

**File:** `finance_service/agents/news_agent.py`  
**Goal:** Monitor news and sentiment for specified symbols to identify catalysts.

**Trigger:** Called per-symbol by orchestrator after `DATA_FETCH_COMPLETE` (in parallel with `AnalysisAgent`).

**Inputs:**
- `symbol` — ticker to fetch news for

**Processing:**
- Fetches recent news articles for the symbol
- Runs sentiment analysis (bullish / bearish / neutral)
- Identifies key catalysts (earnings beats, analyst upgrades, product launches, etc.)

**Output Event:** `NEWS_FETCH_COMPLETE`
```python
{
    "agent_id": "news_agent",
    "status": "success",
    "payload": {
        "symbol": "NVDA",
        "sentiment": "bullish",
        "sentiment_score": 0.72,
        "articles": [ ... ],
        "catalysts": ["analyst upgrade", "earnings beat"]
    }
}
```

---

### 6. AnalysisAgent

**File:** `finance_service/agents/analysis_agent.py`  
**Goal:** Transform raw market data into actionable technical analysis signals.

**Trigger:** Called per-symbol by orchestrator after `DATA_FETCH_COMPLETE` (in parallel with `NewsAgent`).

**Inputs:**
- `data_payload` — full payload from `DataAgent` (OHLCV dataframe + fundamentals)
- `symbol` — ticker

**Processing:**
Computes technical indicators from OHLCV data:

| Indicator | Description |
|-----------|-------------|
| RSI | Relative Strength Index (default period 14) |
| MACD | Signal line + histogram |
| SMA 20 / 50 / 200 | Simple Moving Averages |
| ATR | Average True Range (volatility) |
| Bollinger Bands | Upper / middle / lower bands |
| Trend | Directional signal (bullish / bearish / neutral) |

**Output Event:** `ANALYSIS_COMPLETE`
```python
{
    "agent_id": "analysis_agent",
    "status": "success",
    "payload": {
        "indicators_snapshot": {
            "symbol": "NVDA",
            "rsi": 32.4,
            "macd": 1.24,
            "macd_signal": 0.87,
            "sma_20": 135.20,
            "sma_50": 152.10,
            "sma_200": 140.30,
            "atr": 4.82,
            "bb_upper": 148.20,
            "bb_lower": 122.40,
            "trend": "bullish"
        }
    }
}
```

---

### 7. RegimeAgent (Phase 1 - LLM Augmentation)

**File:** `finance_service/agents/regime_agent.py`  
**Goal:** Classify current market regime (trending, range-bound, high/low volatility) to enable strategy adaptation.

**Trigger:** Event-driven; called after `ANALYSIS_COMPLETE` for each symbol when LLM regime module is enabled via config.

**Inputs:**
- `symbol` — ticker
- `ohlcv_data` — DataFrame with OHLCV
- `indicators` — dict of technical indicators

**Processing:**
- If LLM module enabled: sends prompt to configured provider (OpenRouter/OpenAI/Anthropic/Ollama) with market data, requests JSON classification
- If LLM disabled or fails: uses deterministic rules (ATR ratio + SMA trend)
- Caches response (24h TTL)
- Publishes `MARKET_REGIME_UPDATED` event

**Regimes:**
- `trending_bullish` — price > SMA200, SMA50 > SMA200, MACD > 0
- `trending_bearish` — price < SMA200, SMA50 < SMA200, MACD < 0
- `range_bound` — low ATR, oscillating near MAs
- `high_volatility` — ATR > 2× normal
- `low_volatility` — ATR < 0.5× normal
- `mixed` — unclear/transitioning

**Output Event:** `MARKET_REGIME_UPDATED`
```python
{
    "agent_id": "regime_agent",
    "status": "success",
    "payload": {
        "regime": {
            "regime": "trending_bullish",
            "confidence": 0.87,
            "description": "Price 7% above SMA200, MACD positive",
            "timestamp": "2026-04-01T10:30:00Z",
            "indicators_used": ["rsi", "macd", "atr", "sma_50", "sma_200"]
        }
    }
}
```

**Configuration (config/config.yaml):**
```yaml
llm:
  enabled: true  # Global LLM switch
  modules:
    market_regime:
      enabled: true
      model: "anthropic/claude-3.7-sonnet"
      temperature: 0.2
      prompt_template: "prompts/regime_classifier.md"
```

**Integration:** `StrategyAgent` subscribes to this event and adjusts confidence thresholds accordingly (e.g., higher thresholds in trending markets, lower in low volatility).

---


### 15. TradingAgentsAnalyzer (Phase 1 - Gemini Integration ✅)

**File:** `finance_service/agents/trading_agents_analyzer.py`  
**Goal:** Leverage LLM-powered multi-agent analysis through TradingAgents framework for deep opportunity evaluation.

**Trigger:** Called by orchestrator after analysis indicators are ready; integrates with `RegimeAgent` and `StrategyAgent`.

**Inputs:**
- `symbol` — ticker to analyze
- `ohlcv_data` — OHLCV DataFrame
- `fundamentals` — fundamental metrics
- `indicators` — technical indicators from `AnalysisAgent`
- `market_regime` — regime classification from `RegimeAgent`

**Processing:**
- Routes multi-step LLM analysis through TradingAgents framework
- Quick-think LLM (Gemini 2.5 Flash): Rapid pattern recognition (0.2s latency)
- Deep-think LLM (Gemini 2.5 Pro): Detailed opportunity assessment (1-2s latency)
- Evaluates trader psychology, market microstructure, regime-specific tactics
- Returns ranked opportunities with detailed rationale and risk assessment

**Output Event:** `LLM_ANALYSIS_COMPLETE`
```python
{
    "agent_id": "trading_agents_analyzer",
    "status": "success",
    "payload": {
        "symbol": "NVDA",
        "opportunities": [
            {
                "opportunity_id": "opp-001",
                "type": "breakout_momentum",
                "strength": 0.88,
                "rationale": "Bullish regime confirmation + RSI recovery from oversold",
                "recommended_action": "aggressive_entry",
                "risk_factors": ["sector_volatility", "macro_uncertainty"]
            }
        ],
        "llm_models_used": ["gemini-2.5-flash-v1", "gemini-2.5-pro-v1"],
        "analysis_latency_ms": 1245
    }
}
```

**Integration:** Works in tandem with `RegimeAgent` (shares market regime context) and `StrategyAgent` (enriches proposals with LLM analysis).

---

### 16. TradingAgentsAPI (Phase 1 - Gemini Integration ✅)

**File:** `finance_service/agents/trading_agents_api.py`  
**Goal:** Provide REST API gateway for TradingAgents framework multi-agent orchestration and external integrations.

**Endpoints:**
- `POST /analyze` — Submit symbol for LLM-powered analysis
- `GET /status/{task_id}` — Poll analysis completion status
- `GET /results/{task_id}` — Retrieve analysis results
- `POST /feedback` — Log analysis outcome for future model tuning

**Integration:** Used by `MainOrchestratorAgent` to queue and retrieve LLM analyses asynchronously.

---

### LLM Configuration

**File:** `finance_service/agents/llm_config.py`  
**Goal:** Centralized multi-provider LLM configuration and credential management.

**Supported Providers:**
- **Google Gemini** ✅ (Active: gemini-2.5-flash-v1, gemini-2.5-pro-v1)
- **OpenRouter** (OpenAI, Anthropic, xAI models)
- **OpenAI** (GPT-4, GPT-3.5)
- **Anthropic** (Claude 3 Sonnet)
- **xAI** (Grok v2, v3)

**Configuration Source:** Environment variables (`.env` file)
```bash
LLM_PROVIDER=google
GOOGLE_API_KEY=<gemini-key>
TA_QUICK_THINK_MODEL=gemini-2.5-flash-v1
TA_DEEP_THINK_MODEL=gemini-2.5-pro-v1
```

**Key Feature:** Hot-reload support — change LLM provider without restarting system.



### 17. RankingAgent (Phase 2 - Interpretability ✅)

**File:** `finance_service/agents/ranking_agent.py`  
**Goal:** Provide explainable, multi-factor ranking of symbols with detailed scoring breakdown.

**Trigger:** Called by orchestrator after `MARKET_SCANNED` to re-rank and enrich discovered symbols with scoring details.

**Inputs:**
- `symbols_with_data` — dict of {symbol: {theme, data, indicators, fundamentals}}

**Processing:**
Computes composite ranking score from 5 independent factors:

| Factor | Weight | Description |
|--------|--------|-------------|
| Liquidity | 20% | Trading volume, bid-ask spread (min $1M daily) |
| Momentum | 25% | RSI trend + MACD + SMA trend (technical) |
| Value | 20% | P/E ratio, book value (fundamental valuation) |
| Growth | 20% | EPS growth, revenue growth (expansion metrics) |
| Quality | 15% | ROE, debt/equity ratio (financial health) |

**Scoring Pipeline:**
1. Compute raw metric for each factor
2. Normalize each to 0-1 scale using configurable thresholds
3. Apply weighted sum: `composite_score = Σ(weight_i × normalized_score_i)`
4. Generate human-readable explanation highlighting top 3 factors
5. Assign confidence score based on data completeness

**Output Event:** `RANKING_COMPLETE`
```python
{
    "agent_id": "ranking_agent",
    "status": "success",
    "payload": {
        "ranked_symbols": [
            {
                "symbol": "NVDA",
                "theme": "AI",
                "composite_score": 0.87,
                "rank": 1,
                "confidence": 0.95,
                "factors": [
                    {
                        "name": "momentum",
                        "weight": 0.25,
                        "raw_value": 32.4,
                        "normalized_score": 0.85,
                        "contribution": 0.212
                    },
                    {
                        "name": "liquidity",
                        "weight": 0.20,
                        "raw_value": 45000000,
                        "normalized_score": 0.90,
                        "contribution": 0.180
                    }
                ],
                "explanation": "NVDA: Strong momentum (0.85), Strong liquidity (0.90), Moderate value (0.62)"
            }
        ],
        "ranking_timestamp": "2026-04-03T12:00:00Z",
        "total_symbols": 50
    }
}
```

**Integration:**
- Sits between `MARKET_SCANNED` and `DataAgent` processing
- Re-rankable: can be called independently anytime to re-score symbolsexisting watch list
- Decoder for strategy: StrategyAgent can use ranking confidence/explanations to adjust decision thresholds
- Transparent: full factor breakdown enables learning and backtesting analysis

**Key Design Decisions:**
1. **Independent**: Not tied to MarketScannerAgent; can rank any symbol set
2. **Explainable**: Returns full factor breakdown so users understand why symbol ranked where
3. **Tunable**: All weights and thresholds configurable via YAML
4. **Extensible**: New factors can be added without changing agent interface

---

### 7. StrategyAgent (renumbered from 7)

**File:** `finance_service/agents/strategy_agent.py`  
**Goal:** Generate actionable trade proposals by analyzing market indicators and news sentiment.

**Trigger:** Called by orchestrator once **both** `NEWS_FETCH_COMPLETE` and `ANALYSIS_COMPLETE` are buffered for the same symbol.

**Inputs:**
- `indicators_report` — `AgentReport` from `AnalysisAgent`
- `news_report` — `AgentReport` from `NewsAgent`

**Processing:**
- Evaluates rule-based strategy (`Rule`/`RuleStrategy`) against indicator values
- Combines technical signals with news sentiment score
- Queries `PortfolioAgent` to check if symbol is already held (avoids duplicate buys)
- Calculates confidence score, entry price, stop-loss, and take-profit targets
- Generates `BUY` / `SELL` / `HOLD` proposals

**Output Event:** `TRADE_PROPOSAL_GENERATED`
```python
{
    "agent_id": "strategy_agent",
    "status": "success",
    "payload": {
        "proposals": [
            {
                "symbol": "NVDA",
                "action": "BUY",
                "confidence": 0.86,
                "entry_price": 128.50,
                "stop_loss": 122.07,
                "take_profit": 138.78,
                "reason": "RSI oversold (32) + bullish news sentiment (0.72)"
            }
        ]
    }
}
```

---

### 8. RiskAgent

**File:** `finance_service/agents/risk_agent.py`  
**Goal:** Enforce risk management policies and facilitate trade approval workflows.

**Trigger:** `TRADE_PROPOSAL_GENERATED` event.

**Inputs:**
- `trade_proposal_report` — `AgentReport` from `StrategyAgent`

**Processing:**
Runs configurable risk checks against limits from `finance.yaml`:

| Check | Description |
|-------|-------------|
| Position size | Max allocation per symbol (e.g., 10%) |
| Portfolio exposure | Max total open positions (e.g., 80%) |
| Drawdown | Halt if portfolio drawdown exceeds threshold |
| Duplicate position | Reject if symbol already held |
| Sector concentration | Limit over-allocation to one sector |

**Output Events:**
- `RISK_CHECK_COMPLETE` — passes; orchestrator proceeds to execution if `auto_execute` is enabled
- `APPROVAL_REQUIRED` — requires human Telegram approval before execution
- `RISK_ALERT` — limit breach warning

```python
{
    "agent_id": "risk_agent",
    "status": "success",
    "payload": {
        "all_passed": True,
        "any_approval_required": False,
        "results": [
            {
                "symbol": "NVDA",
                "approved": True,
                "max_shares": 18,
                "checks_passed": ["position_size", "exposure", "drawdown"]
            }
        ]
    }
}
```

---

### 9. ExecutionAgent

**File:** `finance_service/agents/execution_agent.py`  
**Goal:** Execute approved trade proposals efficiently and optimally in the market.

**Trigger:** `RISK_CHECK_COMPLETE` (when `auto_execute = true`), or after human Telegram approval.

**Inputs:**
- `approval_report` — `AgentReport` from `RiskAgent` with approved proposals

**Processing:**
- Submits orders to configured broker (`paper_broker`, `alpaca`, or `ibkr`)
- Handles order routing and size optimization
- Captures fill price, quantity, and order ID

**Output Event:** `TRADE_EXECUTED`
```python
{
    "agent_id": "execution_agent",
    "status": "success",
    "payload": {
        "execution_result": {
            "symbol": "NVDA",
            "action": "BUY",
            "quantity": 18,
            "filled_price": 128.50,
            "order_id": "ORD-001",
            "status": "filled"
        }
    }
}
```

---

### 10. PortfolioAgent

**File:** `finance_service/agents/portfolio_agent.py`  
**Goal:** Maintain an accurate record of portfolio holdings, execute trades, and provide real-time portfolio metrics.

**Trigger:** `TRADE_EXECUTED` event. Also responds to `GET_PORTFOLIO_STATE` and `ANALYSIS_COMPLETE`.

**Inputs:**
- `event_type` — `TRADE_EXECUTED`, `GET_PORTFOLIO_STATE`, `ANALYSIS_COMPLETE`
- `payload` — trade details (symbol, action, quantity, price)

**Processing:**
- Opens / closes / updates positions
- Tracks cost basis and unrealized P&L per position
- Calculates total equity, return %, and daily P&L
- Serves portfolio snapshots on request

**Output Event:** `PORTFOLIO_UPDATED`
```python
{
    "agent_id": "portfolio_agent",
    "status": "success",
    "payload": {
        "overview": {
            "total_equity": 101540.00,
            "cash": 23000.00,
            "position_count": 6,
            "total_pnl": 1540.00,
            "total_return_pct": 1.54
        },
        "positions": [
            {
                "symbol": "NVDA",
                "quantity": 18,
                "entry_price": 128.50,
                "current_price": 135.20,
                "unrealized_pnl": 120.60,
                "stop_loss_price": 122.07,
                "take_profit_price": 138.78
            }
        ]
    }
}
```

---

### 11. LearningAgent

**File:** `finance_service/agents/learning_agent.py`  
**Goal:** Monitor and analyze trade outcomes and overall portfolio performance to identify learning opportunities.

**Trigger:** `TRADE_EXECUTED` event (runs after every trade).

**Inputs:**
- `execution_report` — `AgentReport` from `ExecutionAgent`

**Processing:**
- Logs trade outcome (win/loss, P&L, holding period)
- Calculates rolling performance metrics (Sharpe, win rate, average R)
- Detects patterns between winning and losing trades
- Generates strategy improvement recommendations and flags parameter adjustments

**Output Event:** `LEARNING_COMPLETE`
```python
{
    "agent_id": "learning_agent",
    "status": "success",
    "payload": {
        "win_rate": 0.62,
        "avg_return_pct": 3.4,
        "total_trades": 47,
        "sharpe_ratio": 1.28,
        "recommendation": "Increase stop-loss buffer for momentum symbols"
    }
}
```

---

### 12. HealthAgent

**File:** `finance_service/agents/health_agent.py`  
**Goal:** Monitor portfolio performance and system health, raise alerts on anomalies.

**Trigger:** `TRADE_EXECUTED`, `SCHEDULE`, `DAILY_REPORT_TRIGGER`, `GET_SYSTEM_STATUS`.

**Processing:**
- Computes live portfolio health metrics
- Checks for anomalies (unusual drawdown, stale data, failed agents)
- Sends trade confirmation messages to Telegram on `TRADE_EXECUTED`
- Generates scheduled health summaries

**Telegram message on trade execution:**
```
Trade Executed ✅

Symbol: NVDA
Action: BUY
Shares: 18
Price: $128.50

Reason:
• RSI oversold (32)
• Bullish MACD crossover
• Confidence: 0.86

Portfolio equity: $101,540
```

---

### 13. ExitAgent

**File:** `finance_service/agents/exit_agent.py`  
**Goal:** Monitor open positions for exit conditions (stops/profits) and strategic degradation.

**Status:** ✅ Fully integrated — triggered every 5 minutes via `EXIT_CHECK_TRIGGER` from SchedulerAgent.

**Inputs:**
- `positions` — list of open positions from `PortfolioAgent`
- `perform_strategy_check` — if `True`, runs strategic re-analysis (default when called from orchestrator)

**Processing (Dual-Mode):**

**Mode 1 — Reactive Exits** (`_check_reactive_exits`):
1. Fetches current price via `DataAgent`
2. Compares against `stop_loss_price` and `take_profit_price`
3. If triggered: logs exit and optionally executes sell via `ExecutionAgent`

**Mode 2 — Strategic Re-Analysis** (`_check_strategic_degradation`):
1. Fetches fresh OHLCV data via `DataAgent`
2. Runs `AnalysisAgent` to compute current indicators
3. Checks for degradation: RSI > 70 (overbought) or trend == "bearish"
4. Emits `POSITION_DEGRADED` event if thesis no longer holds

**Exit/Degradation conditions:**

| Condition | Trigger | Action |
|-----------|---------|--------|
| Stop-loss | `current_price ≤ stop_loss_price` | Sell immediately |
| Take-profit | `current_price ≥ take_profit_price` | Sell to lock gains |
| RSI Overbought | `RSI > 70` | Flag as degraded, recommend review |
| Bearish Trend | `trend == "bearish"` | Flag as degraded, recommend review |

**Integration:** Orchestrator `handle_exit_check_trigger()` → retrieves positions from `PortfolioAgent` → calls `ExitAgent.run(positions, perform_strategy_check=True)` → sends Telegram alerts for any exits or degradations.

---

### 14. TelegramAgent

**File:** `finance_service/agents/telegram_agent.py`  
**Goal:** Provide a Telegram interface for interacting with the trading system and delivering scheduled reports.

**Runs:** Always active — listens for user commands and receives broadcast messages from all other agents.

**User commands:**

| Command | Action |
|---------|--------|
| `/start` | Welcome message, confirm bot is connected |
| `/status` | Publishes `GET_SYSTEM_STATUS` → orchestrator replies with all agent statuses |
| `/portfolio` | Publishes `GET_PORTFOLIO_STATE` → orchestrator replies with holdings + equity |

**Outbound messages (sent automatically):**
- **Pre-execution alerts** — sent by orchestrator before every approved trade; includes symbol with Yahoo Finance link, quantity, entry price, stop-loss, confidence, all technical indicator values (RSI, MACD, SMA20/50/200, ATR, Stochastic, Bollinger Bands, Regime Score), news sentiment, and entry rationale
- Market scan summaries (after `MARKET_SCANNED`)
- Trade confirmations (via `HealthAgent` on `TRADE_EXECUTED`)
- Daily P&L report (via `DAILY_REPORT_TRIGGER`)
- Approval requests (when `APPROVAL_REQUIRED`)
- System error alerts

---

## Full Event-Driven Workflow (Step-by-Step)

```
Step 1:  SchedulerAgent
         └─> Emits: MARKET_SCAN_TRIGGER  (daily at market open)

Step 2:  Orchestrator handles MARKET_SCAN_TRIGGER
         └─> Checks: is US or HK market open?
         └─> Calls: MarketScannerAgent.run()
         └─> MarketScannerAgent emits: MARKET_SCANNED
             → payload: {symbols: ["NVDA", "PLTR", "AMD", "700.HK", ...]}

Step 3:  Orchestrator handles MARKET_SCANNED
         └─> For each symbol (if market is open):
             └─> Calls: DataAgent.run(symbol, 365-day lookback)
             └─> DataAgent emits: DATA_FETCH_COMPLETE
                 → payload: {symbol, dataframe, fundamentals}

Step 4:  Orchestrator handles DATA_FETCH_COMPLETE
         └─> In PARALLEL:
             ├─> Calls: NewsAgent.run(symbol)
             │   └─> NewsAgent emits: NEWS_FETCH_COMPLETE
             │       → payload: {sentiment, sentiment_score, catalysts}
             └─> Calls: AnalysisAgent.run(data_payload, symbol)
                 └─> AnalysisAgent emits: ANALYSIS_COMPLETE
                     → payload: {indicators_snapshot: {rsi, macd, sma_20/50/200, ...}}

Step 5:  Orchestrator buffers reports per symbol
         └─> When BOTH NEWS_FETCH_COMPLETE and ANALYSIS_COMPLETE
             are available for the same symbol:
             └─> Calls: StrategyAgent.run(indicators_report, news_report)
             └─> StrategyAgent emits: TRADE_PROPOSAL_GENERATED
                 → payload: {proposals: [{symbol, action, confidence, target, stop}]}

Step 6:  Orchestrator handles TRADE_PROPOSAL_GENERATED
         └─> Calls: RiskAgent.run(trade_proposal_report)
         └─> RiskAgent emits: RISK_CHECK_COMPLETE  or  APPROVAL_REQUIRED

Step 7a: [auto_execute = true + RISK_CHECK_COMPLETE]
         └─> TelegramAgent.send_pre_execution_notification() ← symbol, qty, price,
             stop-loss, confidence, all technical indicators, news sentiment, rationale
         └─> Calls: ExecutionAgent.run(approval_report)
         └─> ExecutionAgent emits: TRADE_EXECUTED
             → payload: {symbol, action, quantity, filled_price, order_id}

Step 7b: [APPROVAL_REQUIRED]
         └─> TelegramAgent sends approval request to user
         └─> User sends approval → TRADE_APPROVED → same as Step 7a

Step 8:  Orchestrator handles TRADE_EXECUTED
         └─> In PARALLEL:
             ├─> Calls: PortfolioAgent.run(TRADE_EXECUTED, execution_result)
             │   └─> Updates holdings, equity, P&L
             ├─> Calls: LearningAgent.run(execution_report)
             │   └─> Logs outcome, updates win rate, recommends adjustments
             └─> Calls: HealthAgent.run(TRADE_EXECUTED, execution_result)
                 └─> Sends trade confirmation message to Telegram

Step 9:  SchedulerAgent emits DAILY_REPORT_TRIGGER  (end of day)
         └─> Orchestrator calls PortfolioAgent for metrics
         └─> TelegramAgent sends daily P&L summary report
```

---

## Scheduling Summary

| Agent | Frequency | Trigger |
|-------|-----------|---------|
| SchedulerAgent | Continuous background loop | Self |
| MarketScannerAgent (Tier 1) | Daily (Discovery) | `MARKET_SCAN_TRIGGER` at pre-market (01:00 HK / 13:00 HK for US) |
| MarketScannerAgent (Tier 2) | Every 15 min | `PRICE_MONITOR_TRIGGER` (price refresh) |
| DataAgent | Per-symbol after each scan | `MARKET_SCANNED` / `DATA_REFRESH_TRIGGER` |
| NewsAgent | Per-symbol after data fetch | `DATA_FETCH_COMPLETE` |
| AnalysisAgent | Per-symbol after data fetch | `DATA_FETCH_COMPLETE` |
| StrategyAgent | Per-symbol when news + analysis both ready | Internal buffer |
| RiskAgent | Per proposal | `TRADE_PROPOSAL_GENERATED` |
| ExecutionAgent | Per approved trade | `RISK_CHECK_COMPLETE` |
| PortfolioAgent | Per trade | `TRADE_EXECUTED` |
| LearningAgent | Per trade | `TRADE_EXECUTED` |
| HealthAgent | Per trade + daily schedule | `TRADE_EXECUTED` / `SCHEDULE` |
| ExitAgent | ✅ Every 5 minutes | `EXIT_CHECK_TRIGGER` (reactive + strategic) |
| TradingAgentsAnalyzer | Per-symbol after analysis ready | `ANALYSIS_COMPLETE` |
| TradingAgentsAPI | Per LLM request | REST API (`POST /analyze`) |
| RankingAgent | Per discovery batch | `MARKET_SCANNED` (re-ranking) |
| MarketRegimeAgent | **Daily per-market** (60-min cache) | `PRE_SCAN_CONTEXT_REFRESH` (5 min pre-market) + On-demand from SymbolSelector |
| MacroNewsAgent | **Daily per-market** (6-hour cache) | `PRE_SCAN_CONTEXT_REFRESH` (5 min pre-market) + On-demand from SymbolSelector |
| SymbolSelectorAgent | **Daily per-market** (post-discovery) | `MARKET_SCANNED` with market param (after scanner, before per-symbol pipeline) |
| TelegramAgent | Always on | User commands + incoming messages |

---

---

## Agent Run Frequencies and Scheduling

### Overview

AITradeAgent uses a **dual-market pre-market scan model** (Hong Kong + US) with cache pre-warming:

1. **HK Pre-Market Scan** — 01:00 UTC+8 (30 min before HK market open at 09:30 HKT)
2. **US Pre-Market Scan** — 13:00 UTC+8 (evening before US market open at 21:30 UTC / 09:30 EST next day)

Both market scans follow the same **3-step workflow** with pre-warming:

```
Scheduler publishes PRE_SCAN_CONTEXT_REFRESH (market="HK"/"US")
    ↓
MarketRegimeAgent + MacroNewsAgent run in parallel (cache refresh)
    ↓ [5-second delay for cache to warm]
    ↓
MarketScannerAgent triggers market scan (50+ symbols)
    ↓
SymbolSelectorAgent ranks candidates (LLM pre-selection → top 5-10)
    ↓
Per-symbol pipeline (DataAgent → NewsAgent + AnalysisAgent → etc.)
```

### Detailed Timing

#### **Morning: HK Pre-Market Scan (01:00 UTC+8)**

| Time | Event | Agents | Purpose |
|------|-------|--------|---------|
| 01:00 | PRE_SCAN_CONTEXT_REFRESH published | SchedulerAgent | Trigger cache pre-warm |
| 01:00–01:02 | MarketRegimeAgent + MacroNewsAgent run (parallel) | MarketRegimeAgent, MacroNewsAgent | Compute `regime_hk`, `hk_sentiment_score`, cache results |
| 01:02 | MARKET_SCAN_TRIGGER published | SchedulerAgent | Trigger HK symbol discovery |
| 01:02–01:08 | MarketScannerAgent scans (~50 HK candidates) | MarketScannerAgent | Discover HK listing symbols matching themes |
| 01:08 | MARKET_SCANNED event published | MarketScannerAgent | Publish candidates list with `market="HK"` |
| 01:08–01:15 | SymbolSelectorAgent ranks top 5-10 via LLM | SymbolSelectorAgent | Use `regime_hk` + `hk_sentiment_score` for ranking |
| 01:15–01:30 | Per-symbol pipeline (top 10 symbols) | DataAgent, NewsAgent, AnalysisAgent | Fetch data, fetch news, compute scores |
| 01:30+ | Telegram report sent | TelegramAgent | Publish "\[HK\] Top Stock Rankings" to Telegram |

**Result**: HK symbols ready for trading 30 min before market open; regime + macro context pre-cached.

#### **Evening: US Pre-Market Scan (13:00 UTC+8 / 21:30 UTC)**

Same workflow as HK scan:

| Time (UTC+8) | Time (EST) | Event | Agents |
|---|---|---|---|
| 13:00 | 21:30 (Fri) | PRE_SCAN_CONTEXT_REFRESH published | SchedulerAgent |
| 13:00–13:02 | 21:30–21:32 | MarketRegimeAgent + MacroNewsAgent run (parallel) | MarketRegimeAgent, MacroNewsAgent |
| 13:02 | 21:32 | MARKET_SCAN_TRIGGER published | SchedulerAgent |
| 13:02–13:08 | 21:32–21:38 | MarketScannerAgent scans (~50 US candidates) | MarketScannerAgent |
| 13:08 | 21:38 | MARKET_SCANNED event published | MarketScannerAgent |
| 13:08–13:15 | 21:38–21:45 | SymbolSelectorAgent ranks top 5-10 via LLM | SymbolSelectorAgent |
| 13:15–13:30 | 21:45–22:00 | Per-symbol pipeline (top 10 symbols) | DataAgent, NewsAgent, AnalysisAgent |
| 13:30+ | 22:00+ | Telegram report sent | TelegramAgent |

**Result**: US symbols ready for trading 7+ hours before market open (overnight analysis); regime + macro context ready before market open.

#### **Continuous Monitoring (24/7)**

| Interval | Event | Agents | Purpose |
|----------|-------|--------|---------|
| Every 5 min | EXIT_CHECK_TRIGGER | ExitAgent | Monitor open positions, check exit conditions |
| Every 15 min | PRICE_MONITOR_TRIGGER | MarketScannerAgent | Price refresh on top 50 symbols (intraday) |
| Every 30 min | DATA_REFRESH_TRIGGER | DataAgent | Refresh OHLCV cache for all tracked symbols |
| Every 4 hours | HEALTH_CHECK_TRIGGER | HealthAgent | System health monitoring, resource check |
| Daily (08:05 UTC) | DAILY_REPORT_TRIGGER | HealthAgent | End-of-day portfolio summary + metrics |

### Pre-Scan Context Refresh Mechanism (PRE_SCAN_CONTEXT_REFRESH)

**New in Phase 4**: A new event `PRE_SCAN_CONTEXT_REFRESH` is published **5 minutes before** each pre-market scan to pre-warm the agent caches:

```python
# Example: SchedulerAgent._trigger_pre_market_scan_hk()
await self.event_bus.publish(Event(
    event_type=Events.PRE_SCAN_CONTEXT_REFRESH,
    data={"market": "HK"}
))
logger.info("PRE_SCAN_CONTEXT_REFRESH published for HK")

# MainOrchestratorAgent subscribes and routes to:
# 1. MarketRegimeAgent.run({"market": "HK", "force_refresh": True})
# 2. MacroNewsAgent.run({"market": "HK", "force_refresh": True})
# Both run in parallel and update agent-level caches

# After 5 sec delay, MARKET_SCAN_TRIGGER is published
await asyncio.sleep(5)
await self.event_bus.publish(Event(
    event_type=Events.MARKET_SCAN_TRIGGER,
    data={"market": "HK", "interval": "pre_market"}
))
```

**Benefits**:
- Regime + macro context already computed when SymbolSelector runs
- No time wasted on LLM call waiting for regime/macro data
- Cache hit rates improve (60-min and 6-hour TTLs respected)

### Agent Run Schedule Summary

**Daily Pre-Market Triggers**:
- HK: 01:00 UTC+8 (every trading day)
- US: 13:00 UTC+8 / 21:30 UTC (every trading day)

**Per-Market Regime Run Frequency**:
- `regime_us`: Computed daily at 13:00 UTC+8 (pre-warm) + on-demand when SymbolSelector needs it
- `regime_hk`: Computed daily at 01:00 UTC+8 (pre-warm) + on-demand when SymbolSelector needs it

**Per-Market Macro News Run Frequency**:
- `us_sentiment_score`: Updated daily at 13:00 UTC+8 (pre-warm) + cached for 6 hours; re-fetched on-demand from SymbolSelector if cache miss
- `hk_sentiment_score`: Updated daily at 01:00 UTC+8 (pre-warm) + cached for 6 hours; re-fetched on-demand from SymbolSelector if cache miss

**Per-Market SymbolSelector (LLM Ranking) Run Frequency**:
- Runs once per pre-market scan: 01:00 UTC+8 (HK) + 13:00 UTC+8 (US)
- Returns top 5–10 symbols per market
- LLM invocation cost: ~13k tokens per run

---
## Configuration Reference

**`finance.yaml` — key sections:**

```yaml
finance:
  risk:
    max_position_pct: 0.10       # Max 10% of portfolio per symbol
    max_total_exposure_pct: 0.80 # Max 80% in open positions
    max_drawdown_pct: 0.15       # Halt if portfolio drops 15%
    stop_loss_pct: 0.05          # Stop-loss 5% below entry
    take_profit_pct: 0.08        # Take-profit 8% above entry

  strategy:
    auto_execute:
      enabled: false             # false = require Telegram approval
    confidence_threshold: 0.70   # Minimum confidence to generate proposal

  execution:
    broker: paper                # paper | alpaca | ibkr

  scanner:
    discovery_top_n_per_theme: 10
    price_monitor_top_n: 50
    price_monitor_interval_minutes: 15
    discovery_interval: daily
```

---

---

## REST API Endpoints

The Finance Service exposes the following HTTP endpoints on `http://127.0.0.1:8801`:

| Endpoint | Method | Purpose | Response |
|----------|--------|---------|----------|
| `/health` | GET | Service liveness probe | `{"status": "ok"}` |
| `/portfolio` | GET | Get comprehensive portfolio state (detailed) | Full portfolio snapshot with positions, trades, equity metrics |
| `/portfolio/state` | GET | Get portfolio state (alias endpoint) | Same as `/portfolio` (fixes dashboard 404 errors) |
| `/trigger` | GET | Manually trigger system events | `{"status": "queued", "trigger": "..."}` |

### `/health` Example
```bash
curl http://127.0.0.1:8801/health
→ {"status":"ok"}
```

### `/portfolio/state` Example
```bash
curl http://127.0.0.1:8801/portfolio/state
→ {
    "overview": {
        "initial_cash": 100000,
        "current_cash": 63883.86,
        "total_equity": 102954.04,
        "position_count": 5,
        "trade_count": 22,
        "total_pnl": 2954.04,
        "total_return_pct": 2.954
    },
    "positions": [
        {
            "symbol": "NVDA",
            "quantity": 18,
            "avg_cost": 128.50,
            "current_price": 135.20,
            "market_value": 2433.60,
            "unrealized_pnl": 120.60,
            "unrealized_pnl_pct": 5.21,
            "opened_at": "2026-03-30T15:56:05.712187"
        }
    ],
    "trades": [...],
    "equity_metrics": {
        "realized_pnl": 0.0,
        "unrealized_pnl": 2954.04,
        "drawdown_pct": 0.0,
        "win_rate": 0.0
    },
    "last_updated": "2026-03-30T15:56:24.365690"
}
```

### `/trigger` Example
```bash
# Manually trigger market scan
curl "http://127.0.0.1:8801/trigger?trigger_type=market-scan"
→ {"status": "queued", "trigger": "market_scan"}
```

---

## Proposed Enhancements

See [NEXT_STEPS.md](NEXT_STEPS.md) for the full roadmap. Top items:

| Priority | Enhancement | Benefit |
|----------|-------------|---------|
| ~~High~~ | ~~Wire `ExitAgent` into `SchedulerAgent` (every 5 min)~~ | ✅ Done — Tier 3 exit monitoring every 5 min |
| ~~High~~ | ~~3-tier scanning architecture~~ | ✅ Done — daily discovery + 15-min price monitor + 5-min exits |
| ~~Medium~~ | ~~Expand symbol universe to 100 symbols~~ | ✅ Done — 20 per theme across 5 themes |
| ~~High~~ | ~~Integrate Gemini LLM for regime analysis~~ | ✅ Done — TradingAgentsAnalyzer + Gemini 2.5 (Flash/Pro) |
| ~~Medium~~ | ~~Add TradingAgents framework integration~~ | ✅ Done — LLM multi-agent analysis engine + REST API |
| ~~Medium~~ | ~~Add `RankingAgent` as separate agent~~ | ✅ Done — Multi-factor ranking with 5-factor scoring (liquidity, momentum, value, growth, quality) |
| ~~High~~ | ~~Add LLM-powered symbol pre-selection~~ | ✅ Done — `SymbolSelectorAgent` (Phase 3): 50→5-10 picks via gpt-4o-mini, enriched with market regime + macro context |
| Medium | Implement position degradation alerts | Re-analyze held positions for thesis invalidation (via ExitAgent) |
| Low | Add backtest harness for strategy evaluation | Historical performance validation |
| Low | Add options analytics agent | Volatility surface analysis, pricing models |

---

## Advantages of Multi-Agent Architecture

| Benefit | How |
|---------|-----|
| **Separation of Concerns** | Each agent has exactly one responsibility |
| **Event-driven decoupling** | Agents never call each other directly — all via Event Bus |
| **Parallelism** | News + Analysis run in parallel per symbol; portfolio/learning/health run in parallel after trades |
| **Testability** | Each agent can be unit tested completely independently |
| **Scalability** | New agents (e.g., `RankingAgent`, options scanner) add without touching existing code |
| **Observability** | Every step has a named event — full audit trail |
| **Configurability** | All thresholds and weights live in `finance.yaml` |
| **Resilience** | One agent failing does not block the others |
