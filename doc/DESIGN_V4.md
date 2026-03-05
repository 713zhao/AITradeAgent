# OpenClaw Finance Agent - Design Document v4

## 1. Overview & Core Objectives

Build an **AI-driven Finance Agent** system where:

- **OpenClaw/PicoClaw** is the Orchestrator (reuses existing Telegram bot + pairing)
- **OpenBB/yfinance** provides market data with free rate-limit optimization
- **Event-driven processing**: Analysis runs ASAP when data is ready (no batch delays)
- **Theme-focused scanning**: Monitor AI, semiconductors, energy, etc. (configurable)
- **Paper trading simulation**: Tracks portfolio with real market data
- **Conditional auto-execution**: High-confidence trades ≥ threshold execute automatically
- **UI dashboard**: Streamlit-based live portfolio + trade history + charts
- **Historical backtesting**: Validate strategies with zero lookahead bias

**Target Portfolio**: $100,000 (resettable anytime)  
**Success Metric**: Maximize simulated profit under risk controls

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  OpenClaw/PicoClaw (Telegram Bot Orchestrator)              │
│  - Reuses existing bot + pairing                            │
│  - Routes "finance" messages to Finance Service (HTTP)      │
│  - Handles approval workflows via Telegram inline buttons   │
└────────────┬────────────────────────────────────────────────┘
             │ REST API + Event Hooks
             ▼
┌─────────────────────────────────────────────────────────────┐
│  Finance Service (Python Backend - Flask/FastAPI)           │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Config Engine (YAML-first, Hot-reload)               │   │
│  │ - Load: finance.yaml, schedule.yaml, providers.yaml  │   │
│  │ - Watch for file changes, reload without restart     │   │
│  │ - Expose config via REST API                         │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Event-Driven Processor (Async Task Queue)            │   │
│  │ - Listen for data_ready(symbol, timeframe) events    │   │
│  │ - Trigger: fetch → analyze → decide → validate       │   │
│  │ - Auto-execute if confidence ≥ threshold + risk OK   │   │
│  │ - Report execution result to Telegram immediately    │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Data Layer (Batch + Cache + Rate-limit Optimization) │   │
│  │ - yfinance wrapper: batch fetch, jitter, backoff     │   │
│  │ - SQLite cache (OHLCV + fundamentals) with TTL       │   │
│  │ - Track API calls per run (logging)                  │   │
│  │ - Emit data_ready event on completion                │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Universe Scanner (Theme-based + Watchlist)           │   │
│  │ - Select stocks by theme keywords (AI, chip, energy) │   │
│  │ - Combine with explicit watchlist                    │   │
│  │ - Respect exclude list + max universe size           │   │
│  │ - Hot-reload universe on config change               │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Indicator Engine (Local Compute, Zero LLM Hallucination) │
│  │ - RSI(period), MACD(fast,slow,signal), SMA(window)   │   │
│  │ - EMA, ATR, Bollinger Bands, Stochastic, Volume      │   │
│  │ - All params configurable via YAML                   │   │
│  │ - Computed from cached OHLCV only                    │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Strategy & Decision Engine (Strict JSON Output)      │   │
│  │ - Configurable rule-based strategy                   │   │
│  │ - Input: cached OHLCV + computed indicators          │   │
│  │ - Output: {decision, confidence, signals, SL/TP}     │   │
│  │ - Confidence: aggregated signal strength (0.0..1.0)  │   │
│  │ - No LLM involved; deterministic rules only          │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Risk & Approval System                               │   │
│  │ - Validate: position limit, exposure, daily loss,    │   │
│  │   max drawdown, halts if limits breach               │   │
│  │ - Auto-execute if: confidence ≥ threshold + risk OK  │   │
│  │ - Fallback: Manual approval via Telegram             │   │
│  │ - Log all decisions (execution report)               │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Portfolio Simulation Engine (SQLite)                 │   │
│  │ - Track: cash, positions (avg cost), realized/       │   │
│  │   unrealized P&L, equity curve, drawdown             │   │
│  │ - Support reset (clear or archive), replay           │   │
│  │ - Mark-to-market on each price update                │   │
│  │ - Historical equity snapshots per trade              │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Backtest Engine (Zero Lookahead Bias)                │   │
│  │ - Historical OHLC replay, no forward peeking         │   │
│  │ - Configurable fill rule (close/next open)           │   │
│  │ - Compute: equity curve, max DD, CAGR, win rate,     │   │
│  │   Sharpe ratio; store in SQLite                      │   │
│  │ - Generate performance report + charts               │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Telegram Bridge (Approval + Notifications)           │   │
│  │ - Send approval request with inline buttons          │   │
│  │ - Receive approval/reject response                   │   │
│  │ - Send execution reports with details:               │   │
│  │   symbol, qty, price, confidence, signals, risk OK   │   │
│  │ - Log all Telegram interactions                      │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Storage Layer (SQLite Triple)                        │   │
│  │ - portfolio.sqlite: positions, trades, equity curve  │   │
│  │ - cache.sqlite: OHLCV data + fundamentals (TTL)      │   │
│  │ - backtest.sqlite: backtest runs + metrics           │   │
│  │ - audit log: config changes (before/after diff)      │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│  UI Dashboard (Streamlit)                                   │
│  - Portfolio Status: cash, positions, exposure, risk flags  │
│  - Trade History: log, filters (date/symbol), CSV export    │
│  - Charts: equity curve, drawdown, price + signals          │
│  - Backtest: performance metrics + comparison charts        │
│  - Config: view/edit settings (optional read-only)          │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Repository Structure

```
openclaw-finance-agent/
├── README.md
├── requirements.md (v4)
├── design.md (v4) - High-level vision
├── DESIGN_V4.md - This detailed design
├── plan_implementation.md (NEW) - Phase-by-phase build plan
│
├── config/
│   ├── finance.yaml          # Universe, risk, strategy, backtest
│   ├── schedule.yaml         # Job schedules + triggers
│   └── providers.yaml        # Data provider, caching, throttling
│
├── finance_service/
│   ├── __init__.py
│   ├── app.py                # Flask REST API + event dispatcher
│   ├── requirements.txt
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config_engine.py  # YAML loader + hot-reload
│   │   ├── cache.py          # SQLite cache with TTL
│   │   ├── models.py         # Trade, Position, Decision, ExecutionReport
│   │   ├── logging.py        # Audit logger + config change logger
│   │   └── event_bus.py      # Event dispatcher (data_ready, etc.)
│   │
│   ├── data/
│   │   ├── __init__.py
│   │   ├── provider.py       # Abstract DataProvider interface
│   │   ├── yfinance_provider.py  # yfinance with batch + jitter + backoff
│   │   └── universe_scanner.py   # Theme-based universe + watchlist
│   │
│   ├── indicators/
│   │   ├── __init__.py
│   │   └── calculator.py     # RSI, MACD, SMA, EMA, ATR, Bollinger, Stoch
│   │
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── interface.py      # StrategyEngine abstract class
│   │   ├── baseline_rule.py  # Configurable rule-based strategy
│   │   └── decision_engine.py # Outputs strict decision JSON
│   │
│   ├── risk/
│   │   ├── __init__.py
│   │   ├── validator.py      # Risk checks (position, drawdown, daily loss)
│   │   └── portfolio_mgr.py  # Position sizing + kelly criterion
│   │
│   ├── sim/
│   │   ├── __init__.py
│   │   ├── portfolio.py      # Paper trading portfolio state
│   │   ├── backtest.py       # Historical backtest engine (zero lookahead)
│   │   ├── execution.py      # Order execution + fill simulation
│   │   └── metrics.py        # Equity curve, DD, CAGR, Sharpe
│   │
│   ├── telegram_bridge/
│   │   ├── __init__.py
│   │   ├── approval_handler.py  # Async approval request/response
│   │   └── notifier.py          # Send execution reports to Telegram
│   │
│   └── storage/
│       ├── __init__.py
│       ├── schema.sql        # SQLite schema definition
│       ├── portfolio.sqlite  # Positions, trades, equity snapshots
│       ├── cache.sqlite      # OHLCV + fundamentals (TTL)
│       └── backtest.sqlite   # Backtest runs + metrics
│
├── ui/
│   ├── dashboard.py          # Streamlit main app (home page)
│   ├── pages/
│   │   ├── portfolio.py      # Portfolio status, positions, exposure
│   │   ├── trade_history.py  # Trade log, filters, CSV export
│   │   ├── charts.py         # Equity, drawdown, price + buy/sell marks
│   │   ├── backtest.py       # Backtest results + metrics + comparison
│   │   └── settings.py       # Config viewer (read-only recommended)
│   └── utils.py              # Streamlit helpers
│
├── tests/
│   ├── test_indicators.py
│   ├── test_strategy.py
│   ├── test_portfolio.py
│   ├── test_backtest.py
│   ├── test_risk.py
│   ├── test_data_provider.py
│   └── test_config_engine.py
│
├── picoclaw_config/
│   ├── finance_router_rules.yaml    # Intent routing: "analyze AAPL" → finance
│   ├── finance_system_prompt.md     # LLM instructions for Finance mode
│   ├── finance_tool_policy.md       # Tool constraints, caching strategy
│   ├── tool_schemas.json            # OpenAPI schema for all tools
│   └── approval_workflow.md         # Telegram approval workflow
│
└── scripts/
    ├── backtest_runner.py       # Standalone backtest CLI
    ├── validate.py              # Validation script (imports, config, etc.)
    ├── reset_portfolio.py       # Portfolio reset utility
    └── export_backtest.py       # Export backtest results to CSV
```

---

## 4. Key Design Decisions

### 4.1 Single Telegram Bot (Reuse Existing)

- **Decision**: Reuse existing OpenClaw/PicoClaw Telegram bot, no new bot.
- **Reason**: Minimize setup friction, leverage existing pairing/auth.
- **Implementation**: Finance mode activated by intent routing (e.g., ticker mention).
- **Approval Flow**: Inline buttons (Approve/Reject) in Telegram messages.

### 4.2 YAML-First Configuration

- **Decision**: All system behavior configurable via YAML files, hot-reload on change.
- **Reason**: Minimize token waste, enable reproducible behavior, no code changes needed.
- **Files**:
  - `config/finance.yaml`: Universe, risk limits, strategy params, backtest defaults.
  - `config/schedule.yaml`: Scheduled jobs (daily scan, hourly updates, backtest times).
  - `config/providers.yaml`: Data provider config, cache TTL, rate limiting.
- **Hot-Reload**: File watchdog triggers reload on change; caches invalidated as needed.

### 4.3 Event-Driven Processing

- **Decision**: Emit `data_ready(symbol, timeframe)` immediately upon data fetch completion.
- **Reason**: Analyze ASAP; don't wait for batch to complete.
- **Flow**: data_ready → fetch indicators → run strategy → validate risk → auto-execute or propose to Telegram.

### 4.4 Auto-Execution on High Confidence

- **Decision**: If `confidence ≥ auto_execute_confidence_threshold` AND risk checks pass, execute immediately.
- **Reason**: Enable autonomous behavior for high-conviction trades; retain control via threshold + risk gates.
- **Execution Report**: Always generate + send to Telegram with:
  - Symbol, side, qty, fill price, confidence score
  - Key signals used (RSI, MACD, etc.)
  - Risk checks passed
  - Portfolio impact snapshot

### 4.5 Zero LLM Hallucination

- **Decision**: All indicators + decisions computed locally in Python; LLM never invents prices/returns.
- **Reason**: Prevent catastrophic errors; maintain accuracy.
- **Trade-off**: LLM may interpret signals but cannot compute them.

### 4.6 Rate-Limit Optimization

- **Decision**: Batch fetch, jitter, backoff, cache with TTL.
- **Reason**: yfinance is free but rate-limited; optimize usage.
- **Implementation**: `yfinance_provider.py` handles retry logic, batch requests, request staggering.

### 4.7 Portfolio Reset Support

- **Decision**: System allows reset to configured starting cash (default $100k).
- **Behavior**:
  - `reset_mode: clear` = wipe history
  - `reset_mode: archive` = move history to separate archive
- **UI**: Reset button in dashboard.

### 4.8 Paper Trading (No Real Execution)

- **Decision**: All trades are paper trades; no real money involved.
- **Fills**: Use last traded price (close) or next open (configurable).
- **Slippage**: Optional configurableSlippage percentage.
- **Goal**: Maximize profit under risk constraints.

---

## 5. Data Models & API Contracts

### 5.1 Decision JSON (Strategy Output)

```json
{
  "task_id": "uuid",
  "symbol": "AAPL",
  "timestamp": "2026-03-04T10:30:00Z",
  "decision": "BUY",
  "confidence": 0.78,
  "rationale": "RSI oversold + MACD bullish crossover + SMA(50) support",
  "signals": {
    "rsi_14": 28.5,
    "macd_signal": "bullish_cross",
    "sma_50": 185.2,
    "price": 184.8
  },
  "suggested_sl": 183.0,
  "suggested_tp": 190.0,
  "position_size_pct": 5.0
}
```

### 5.2 Execution Report (Auto or Manual)

```json
{
  "task_id": "uuid",
  "trade_id": "uuid",
  "symbol": "AAPL",
  "side": "BUY",
  "qty": 50,
  "fill_price": 184.9,
  "timestamp": "2026-03-04T10:31:00Z",
  "reason": "auto_execute (confidence=0.78 ≥ threshold=0.75)",
  "signals_used": ["RSI oversold", "MACD bullish", "SMA support"],
  "risk_checks_passed": [
    "position_limit: 5% ≤ 20% limit",
    "total_exposure: 45% ≤ 90% limit",
    "daily_loss: -$500 ≥ -$3000 limit"
  ],
  "portfolio_impact": {
    "cash_before": 99000,
    "cash_after": 90754.50,
    "equity_before": 100000,
    "equity_after": 100254.50,
    "total_value": 100254.50,
    "exposure_pct": 45.2,
    "max_drawdown_pct": 2.1
  }
}
```

### 5.3 Approval Request (Telegram)

```json
{
  "task_id": "uuid",
  "message_text": "AAPL: BUY 50 @ $184.90 (confidence=0.78)\nSignals: RSI oversold, MACD bullish\nRisk: ✓ Passed all checks",
  "inline_buttons": [
    {"text": "✓ Approve", "callback_data": "approve_uuid"},
    {"text": "✗ Reject", "callback_data": "reject_uuid"}
  ]
}
```

---

## 6. YAML Configuration Schema

### 6.1 config/finance.yaml

```yaml
universe:
  market: US  # US, HK, SG, AUTO
  theme_keywords: [AI, semiconductor, cloud]
  watchlist: [AAPL, MSFT, NVDA, TSLA]
  exclude: [TEMP, XYZZ]
  max_size: 50

risk:
  starting_cash: 100000
  max_position_size_pct: 20
  max_total_exposure_pct: 90
  max_daily_loss_pct: 3
  max_drawdown_pct: 10
  approval_required_default: true
  auto_execute_confidence_threshold: 0.75  # float 0..1
  auto_execute_requires_risk_pass: true

strategy:
  type: baseline_rule
  indicators:
    rsi:
      period: 14
      oversold: 30
      overbought: 70
    macd:
      fast: 12
      slow: 26
      signal: 9
    sma:
      short: 20
      long: 50
    atr:
      period: 14

backtest:
  date_range: ["2024-01-01", "2026-03-04"]
  fill_rule: close  # close or next_open
  slippage_pct: 0.1
```

### 6.2 config/schedule.yaml

```yaml
jobs:
  daily_universe_scan:
    schedule: "0 8 * * MON-FRI"  # 8 AM weekdays
    action: scan_universe
    
  hourly_update:
    schedule: "0 * * * *"  # Every hour
    action: update_active_positions
    
  weekly_backtest:
    schedule: "0 17 * * FRI"  # 5 PM Friday
    action: run_backtest
    symbols: [AAPL, MSFT, NVDA]
```

### 6.3 config/providers.yaml

```yaml
yfinance:
  enabled: true
  batch_size: 10
  request_jitter_sec: 0.5
  backoff_max_retries: 3
  cache_ttl_minutes:
    daily: 1440
    hourly: 60
    minute: 5
  throttle_requests_per_min: 60
```

---

## 7. Telegram Integration Flow

### 7.1 User Sends Message

```
User: "analyze AAPL ASAP"
       ↓
    OpenClaw/PicoClaw (Telegram)
       ↓ (Intent: finance + symbol = AAPL)
    Finance REST API: POST /analyze {symbol: "AAPL"}
       ↓
    Finance Service: Fetch → Analyze → Decide
       ↓
       ├─→ If confidence ≥ threshold + risk OK:
       │    Auto-execute + send execution report to Telegram
       │
       └─→ Else:
            Send approval request with inline buttons to Telegram
            Wait for user response
            On approval: execute + send report
            On reject: cancel
```

### 7.2 Execution Report Example

```
📊 EXECUTION REPORT
━━━━━━━━━━━━━━━━━━━━
Symbol: AAPL
Action: BUY
Qty: 50 shares @ $184.90
Confidence: 78%

Signals:
• RSI(14): 28.5 (oversold)
• MACD: Bullish crossover
• SMA(50): Price above support

Risk ✓ Passed:
✓ Position: 5% ≤ 20% limit
✓ Exposure: 45% ≤ 90% limit
✓ Daily loss: -$500 ≥ -$3000

Portfolio:
Cash: $90,754.50 | Equity: $100,254.50
Max DD: 2.1%
━━━━━━━━━━━━━━━━━━━━
Task: uuid-12345
```

---

## 8. UI Dashboard (Streamlit)

### 8.1 Portfolio Status

- **Top KPI Row**: Total equity, Cash, Exposure %, Max drawdown %
- **Positions Table**: Symbol | Qty | Avg Cost | Last Price | Unrealized PnL | %Return
- **Risk Alerts**: ⚠️ warnings if approaching limits
- **Exposure Chart**: Pie chart by symbol or sector
- **Equity Curve**: Line chart over portfolio life

### 8.2 Trade History

- **Trade Log Table**: Timestamp | Symbol | Side | Qty | Price | Reason | Task ID
- **Filters**: Date range, symbol, side (BUY/SELL), tag (auto-execute vs manual approval)
- **Export**: Download as CSV

### 8.3 Charts

- **Equity Curve**: Net portfolio value over time
- **Drawdown Curve**: Max DD from peak
- **Price Chart (Select Symbol)**: OHLC + buy/sell markers
- **Indicator Overlay**: RSI, MACD, SMA on price chart

### 8.4 Backtest Results

- **Metrics Table**: CAGR, Max DD, Win Rate, Sharpe, # Trades
- **Equity Curve**: Backtest vs current portfolio (overlay)
- **Monthly Returns**: Heatmap
- **Drawdown Analysis**: Max DD, recovery time

### 8.5 Config Viewer (Optional)

- Read-only view of finance.yaml, schedule.yaml, providers.yaml
- Optionally allow inline edit + apply button (triggers hot-reload)

---

## 9. Storage (SQLite)

### 9.1 portfolio.sqlite

```sql
CREATE TABLE positions (
  id INTEGER PRIMARY KEY,
  symbol TEXT NOT NULL,
  qty_open REAL,
  avg_cost REAL,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

CREATE TABLE trades (
  id INTEGER PRIMARY KEY,
  task_id TEXT UNIQUE,
  symbol TEXT NOT NULL,
  side TEXT NOT NULL,  -- BUY, SELL
  qty REAL NOT NULL,
  price REAL NOT NULL,
  filled_at TIMESTAMP,
  reason TEXT,
  confidence REAL,
  approval_required BOOLEAN,
  approval_received BOOLEAN,
  approval_at TIMESTAMP
);

CREATE TABLE equity_snapshots (
  id INTEGER PRIMARY KEY,
  timestamp TIMESTAMP,
  cash REAL,
  equity REAL,
  total_value REAL,
  max_drawdown REAL
);
```

### 9.2 cache.sqlite

```sql
CREATE TABLE ohlcv_cache (
  id INTEGER PRIMARY KEY,
  symbol TEXT NOT NULL,
  timestamp TIMESTAMP,
  open REAL, high REAL, low REAL, close REAL, volume INTEGER,
  timeframe TEXT,  -- daily, hourly, etc.
  expires_at TIMESTAMP
);
```

### 9.3 backtest.sqlite

```sql
CREATE TABLE backtest_runs (
  id INTEGER PRIMARY KEY,
  run_id TEXT UNIQUE,
  start_date DATE,
  end_date DATE,
  symbols TEXT,  -- JSON array
  initial_cash REAL,
  final_equity REAL,
  max_drawdown REAL,
  cagr REAL,
  sharpe_ratio REAL,
  win_rate REAL,
  num_trades INTEGER,
  created_at TIMESTAMP
);
```

---

## 10. Safety & Constraints

### 10.1 Never

- ❌ Fabricate market data or prices
- ❌ Execute trades without approval OR (high confidence + risk pass)
- ❌ Ignore position size limits
- ❌ Continue trading if max DD or daily loss limit breached
- ❌ Update YAML without logging before/after diff

### 10.2 Always

- ✅ Compute indicators from cached OHLCV only
- ✅ Validate all decisions against risk policy
- ✅ Log all executions + approval decisions
- ✅ Report execution details to Telegram immediately
- ✅ Support portfolio reset (clear or archive)
- ✅ Track data API calls per run

---

## 11. Success Criteria

✅ **Telegram Integration**
- Single bot reused; no separate bot created
- Finance mode activated by intent routing
- Auto-execution OR approval workflow working

✅ **YAML Configuration**
- All major settings in config/ YAML files
- Hot-reload works on config change
- Config changes logged with before/after diffs

✅ **Event-Driven Processing**
- Data fetch → data_ready event → analysis → decision (no batching delays)
- Multiple symbols parallelize (not sequential)

✅ **Auto-Execution**
- High-confidence trades auto-execute (confidence ≥ threshold + risk OK)
- Manual approval fallback for lower confidence
- Execution report always sent to Telegram

✅ **UI Dashboard**
- Live portfolio status (cash, positions, exposure)
- Trade history with filters + CSV export
- Equity + drawdown charts
- Backtest results visualization

✅ **Backtesting**
- Historical data replay with zero lookahead bias
- Metrics: CAGR, Max DD, win rate, Sharpe
- Results stored + visualized in UI

---

## 12. Implementation Phases (See plan_implementation.md)

1. **Phase 0**: Bootstrap (config, models, SQLite schema)
2. **Phase 1**: Data layer (yfinance provider, cache, rate limiting)
3. **Phase 2**: Indicators + Strategy (engine, decision output)
4. **Phase 3**: Portfolio simulation + Risk validation
5. **Phase 4**: Event-driven processor + Approval workflow
6. **Phase 5**: Telegram bridge (approval + execution reports)
7. **Phase 6**: Backtest engine
8. **Phase 7**: Streamlit UI
9. **Phase 8**: Integration + testing + deployment

---

## 13. Technology Stack

- **Backend**: Python 3.8+ (Flask/FastAPI for REST API)
- **Data**: yfinance (free), SQLite (storage)
- **UI**: Streamlit
- **Task Queue**: APScheduler (for scheduled jobs) + async event bus
- **Telegram**: python-telegram-bot or telethon
- **Testing**: pytest
- **Deployment**: systemd service + Nginx reverse proxy (optional)

---

**Version**: v4  
**Last Updated**: 2026-03-04  
**Status**: Design Phase Complete → Ready for Implementation Plan
