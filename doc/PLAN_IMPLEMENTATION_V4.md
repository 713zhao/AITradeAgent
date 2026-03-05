# OpenClaw Finance Agent v4 - Implementation Plan

**Project Duration**: ~8-12 weeks (full-time development)  
**Target Completion**: June 2026  
**Status**: Phase 5 Complete - 4 Mar 2026 | Next: Phase 6+ (Advanced Features)

### Completion Status
- ✅ **Phase 0** (Week 1): COMPLETE - 4 Mar 2026
  - Config engine, event bus, SQLite schema, Flask skeleton
  - Deliverables: 10/10 ✅ | Tests: 25/25 passing ✅
  
- ✅ **Phase 1** (Weeks 2-3): COMPLETE - 4 Mar 2026
  - Data layer, rate-limited provider, cache, universe scanner
  - Deliverables: 7/7 ✅ | Tests: 23/23 passing ✅

- ✅ **Phase 2** (Weeks 4-5): COMPLETE - 4 Mar 2026
  - 7 technical indicators, rule-based strategy, decision engine
  - Deliverables: 8/8 ✅ | Tests: 30/30 passing ✅
  
- ✅ **Phase 3** (Weeks 6-7): COMPLETE - 4 Mar 2026
  - Position tracking, trade management, equity calculation
  - Deliverables: 8/8 ✅ | Tests: 41/41 passing ✅ | Phase 1-3 combined: 94/94 passing ✅
  - See: `PHASE3_COMPLETION_REPORT.md` for detailed deliverables
  
- ✅ **Phase 4** (Weeks 8-9): COMPLETE - 4 Mar 2026
  - Risk policies, approval workflow, exposure management
  - Deliverables: 5/5 ✅ | Tests: 31/31 passing ✅ | Phase 1-4 combined: 125/125 passing ✅
  - See: `PHASE4_COMPLETION_REPORT.md` for detailed deliverables

- ✅ **Phase 5** (Weeks 10-11): COMPLETE - 4 Mar 2026
  - Trade execution, approval workflows, live monitoring, performance reporting
  - Deliverables: 3/3 ✅ | Tests: 21/21 passing ✅ | Phase 1-5 combined: 146/146 passing ✅
  - See: `PHASE5_COMPLETION_REPORT.md` for detailed deliverables

- 🚀 **Phase 6+** (Weeks 12+): PLANNING - Advanced Features
  - Live trading integration, advanced approval workflows, ML analytics, dashboards
  - See `PHASE6_PLANNING.md` for vision and roadmap

---

## Executive Summary

This document outlines the complete build plan for OpenClaw Finance Agent v4, organized into 9 implementation phases from bootstrap through deployment. Each phase includes specific deliverables, success criteria, and dependencies.

**Key Principles**:
- YAML-first configuration (minimize token waste, maximize reproducibility)
- Event-driven processing (analyze ASAP, no batch delays)
- Single Telegram bot reuse (leverage existing pairing)
- Zero LLM hallucination (local indicator computation only)
- Paper trading focus (no real execution risk)

---

## Phase 0: Bootstrap & Foundation (Week 1)

**Goal**: Set up project structure, configuration engine, data models, and SQLite schema.

### Tasks

#### 0.1 Project Setup
- [ ] Initialize repository structure per `DESIGN_V4.md`
- [ ] Create `config/`, `finance_service/`, `ui/`, `picoclaw_config/`, `tests/`, `scripts/` directories
- [ ] Create main `requirements.txt` with core dependencies:
  ```
  Flask==2.3.x or FastAPI==0.104.x
  yfinance==0.2.x
  pandas==2.x
  numpy==1.x
  SQLite3 (built-in)
  APScheduler==3.x
  streamlit==1.3x
  python-telegram-bot==20.x
  pytest==7.x
  sqlalchemy==2.x (optional ORM)
  ```
- [ ] Initialize git repo + .gitignore

#### 0.2 Configuration Engine
- [ ] Create `finance_service/core/config_engine.py`:
  - Load YAML files from `config/` directory
  - Validate schema (finance.yaml, schedule.yaml, providers.yaml)
  - Hot-reload on file change (watchdog + signal handler)
  - REST endpoints: GET /config, POST /config/reload
  - Logging of config changes (before/after diffs)

- [ ] Create default config files:
  - `config/finance.yaml` (universe, risk, strategy, backtest)
  - `config/schedule.yaml` (job schedules)
  - `config/providers.yaml` (data provider settings)

- [ ] Create `finance_service/core/models.py`:
  - Dataclass: `Decision` (symbol, decision, confidence, signals, SL/TP)
  - Dataclass: `Trade` (symbol, side, qty, price, timestamp, reason)
  - Dataclass: `Position` (symbol, qty, avg_cost)
  - Dataclass: `ExecutionReport` (trade, confidence, signals, risk_checks, portfolio_impact)
  - Dataclass: `Portfolio` (cash, positions, equity_snapshots)

#### 0.3 SQLite Schema
- [ ] Create `finance_service/storage/schema.sql`:
  - `positions` table (id, symbol, qty_open, avg_cost, created_at, updated_at)
  - `trades` table (id, task_id, symbol, side, qty, price, filled_at, reason, confidence, approval_required, approval_received)
  - `equity_snapshots` table (id, timestamp, cash, equity, total_value, max_drawdown)
  - `ohlcv_cache` table (id, symbol, timestamp, open, high, low, close, volume, timeframe, expires_at)
  - `backtest_runs` table (id, run_id, start_date, end_date, symbols, initial_cash, final_equity, metrics)
  - `config_audit_log` table (id, timestamp, config_file, before_yaml, after_yaml, diff)
  - `run_logs` table (id, task_id, symbol, event, timestamp, details_json)

- [ ] Create `finance_service/storage/__init__.py`:
  - SQLite connection initialization
  - Schema creation on startup

#### 0.4 Event Bus
- [ ] Create `finance_service/core/event_bus.py`:
  - Simple event dispatcher (publish/subscribe pattern)
  - Event types: `data_ready(symbol, timeframe)`, `analysis_complete`, `execution_done`
  - Async task queue or simple queue.Queue

#### 0.5 Logging & Audit
- [ ] Create `finance_service/core/logging.py`:
  - Structured logging (JSON format for machine readability)
  - Audit logger for config changes + execution decisions
  - File rotation (daily, max 30 days kept)

#### 0.6 Flask/FastAPI App Skeleton
- [ ] Create `finance_service/app.py`:
  - REST endpoints (stub implementations):
    - GET `/health` → {"status": "ok"}
    - GET `/config` → return current config
    - POST `/config/reload` → reload YAML files
    - POST `/analyze` → stub (will implement in Phase 2)
    - POST `/execute_trade` → stub (will implement in Phase 3)
  - Register event bus
  - Load config engine on startup

### Deliverables

- ✅ Project directory structure
- ✅ `requirements.txt` with all dependencies
- ✅ `config/finance.yaml`, `config/schedule.yaml`, `config/providers.yaml` (defaults)
- ✅ `finance_service/core/config_engine.py` (with hot-reload)
- ✅ `finance_service/core/models.py` (all data classes)
- ✅ `finance_service/storage/schema.sql` + init script
- ✅ `finance_service/core/event_bus.py`
- ✅ `finance_service/core/logging.py`
- ✅ `finance_service/app.py` (Flask/FastAPI skeleton)
- ✅ Unit tests for config engine + event bus

### Success Criteria

```bash
# Should pass:
python -m pytest tests/test_config_engine.py -v      # Config load + hot-reload
python -m pytest tests/test_event_bus.py -v           # Event dispatch
python finance_service/app.py                         # Runs without error
curl http://localhost:5000/health                     # Returns 200 + health JSON
curl http://localhost:5000/config                     # Returns current config
```

---

## Phase 1: Data Layer & Rate-Limit Optimization (Week 2-3)

**Goal**: Implement yfinance provider, cache, rate limiting, universe scanner, and event emission.

### Tasks

#### 1.1 Data Provider Interface
- [ ] Create `finance_service/data/provider.py`:
  - Abstract base class `DataProvider` with methods:
    - `fetch_ohlcv(symbols, timeframe, start_date, end_date) → Dict[symbol, OHLCV]`
    - `fetch_fundamentals(symbols) → Dict[symbol, fundamentals]`
    - `fetch_intraday(symbol, timeframe) → OHLCV`
  - Error handling (rate limits, network errors, missing data)

#### 1.2 yfinance Provider Implementation
- [ ] Create `finance_service/data/yfinance_provider.py`:
  - Implement `DataProvider` interface using yfinance
  - Features:
    - **Batch fetching**: Request multiple symbols in single call (reduce API calls)
    - **Jitter**: Add random delay (0.1-0.5 sec) between requests
    - **Backoff/Retry**: Exponential backoff on rate limit hits (max 3 retries)
    - **Request logging**: Log all API calls (symbol, timeframe, timestamp)
    - **Cache bypass option**: param to skip cache + fetch fresh
  - Error handling:
    - Rate limit (HTTP 429) → backoff + retry
    - Network error → retry with exponential backoff
    - Missing data → log warning, return None for missing symbols
  - Return structure:
    ```python
    {
      "AAPL": {
        "datetime": [list of timestamps],
        "open": [list of prices],
        "high": [...],
        "low": [...],
        "close": [...],
        "volume": [...]
      },
      ...
    }
    ```

#### 1.3 Cache Layer
- [ ] Create `finance_service/core/cache.py`:
  - SQLite-backed cache manager
  - `get(symbol, timeframe) → OHLCV or None`
  - `set(symbol, timeframe, ohlcv, ttl_minutes)`
  - TTL-based expiration (configurable per timeframe in `config/providers.yaml`)
  - Cache hit/miss logging
  - `clear_expired()` method (called on startup)
  - Stats method: `get_stats() → {hits, misses, hit_rate}`

#### 1.4 Data Fetcher (Orchestrator)
- [ ] Create `finance_service/data/fetcher.py`:
  - Public method: `fetch_and_cache(symbols, timeframe, config)`
  - Logic:
    1. Check cache for each symbol (batch check)
    2. Identify cache misses
    3. Fetch missing symbols from provider (batch call)
    4. Store fetched data in cache
    5. Emit `data_ready(symbol, timeframe)` event for each symbol
    6. Return complete data dict (cache hits + fresh data)
  - Error handling: Partial success (some symbols fail)
  - Request logging: Total calls, symbols fetched, cache hit rate

#### 1.5 Universe Scanner
- [ ] Create `finance_service/data/universe_scanner.py`:
  - Load symbols from multiple sources:
    - Explicit watchlist (config/finance.yaml → watchlist)
    - Theme keywords (config/finance.yaml → theme_keywords)
    - Exclude list (config/finance.yaml → exclude)
  - Theme lookup: Simple keyword matching against S&P 500 or Nasdaq list
    - AI theme: NVIDIA, TSLA, PLTR, AI, etc.
    - Semiconductor: NVDA, AMD, QCOM, AVGO, etc.
    - Cloud: MSFT, AMZN, CRWD, OKTA, etc.
    - Energy: XOM, CVX, COP, MPC, etc.
  - Limit universe size: `max_size` from config
  - Return: List of symbols (deduplicated, excluding excludes)
  - Cached for 1 hour (configurable)

#### 1.6 Integration Test
- [ ] Create test: Fetch data for 5 symbols → emit `data_ready` events → verify cache population

### Deliverables

- ✅ `finance_service/data/provider.py` (abstract interface)
- ✅ `finance_service/data/yfinance_provider.py` (implementation + batch + backoff + logging)
- ✅ `finance_service/core/cache.py` (SQLite cache + TTL)
- ✅ `finance_service/data/fetcher.py` (orchestrator)
- ✅ `finance_service/data/universe_scanner.py` (theme + watchlist)
- ✅ Unit tests (cache, provider, fetcher, universe)
- ✅ Integration test (fetch → cache → data_ready events)

### Success Criteria

```bash
# Should pass:
python -m pytest tests/test_data_provider.py -v       # yfinance provider works
python -m pytest tests/test_cache.py -v               # Cache get/set/TTL
python -m pytest tests/test_fetcher.py -v             # Fetcher + event emit
python -m pytest tests/test_universe_scanner.py -v    # Universe selection

# Manual test:
python -c "from finance_service.data.fetcher import fetch_and_cache; data = fetch_and_cache(['AAPL', 'MSFT'], 'daily', config); print(len(data))"
# Should print: 2 (AAPL, MSFT data)

# Check imports:
python -c "from finance_service.data.yfinance_provider import YFinanceProvider; print('OK')"
```

---

## Phase 2: Indicators & Strategy Engine (Week 4-5)

**Goal**: Implement local indicator computation and decision engine (zero LLM).

### Tasks

#### 2.1 Indicator Calculator
- [ ] Create `finance_service/indicators/calculator.py`:
  - Stateless functions, input = OHLCV series:
    - `calc_rsi(close_prices, period=14) → float[0..100]`
    - `calc_macd(close_prices, fast=12, slow=26, signal=9) → {macd, signal, histogram}`
    - `calc_sma(close_prices, window) → float[]`
    - `calc_ema(close_prices, window) → float[]`
    - `calc_atr(high, low, close, period=14) → float[]`
    - `calc_bollinger_bands(close_prices, window=20, num_std=2) → {upper, middle, lower}`
    - `calc_stochastic(high, low, close, k_period=14, d_period=3) → {K, D}`
  - Optimized using numpy (vectorized operations)
  - Error handling: Insufficient data (require min length)
  - All parameters configurable via `config/finance.yaml`

#### 2.2 Strategy Interface
- [ ] Create `finance_service/strategy/interface.py`:
  - Abstract class `StrategyEngine`:
    - `analyze(symbol, ohlcv, indicators_config, risk_config) → Decision`
    - Returns `Decision` with: decision, confidence, signals, SL/TP

#### 2.3 Baseline Rule Strategy
- [ ] Create `finance_service/strategy/baseline_rule.py`:
  - Implement `StrategyEngine`
  - Rules (configurable via `config/finance.yaml`):
    - **Trend Filter**: Price above SMA(50) → uptrend; below → downtrend
    - **Momentum Filter**: RSI < 30 → oversold (BUY signal); RSI > 70 → overbought (SELL signal)
    - **Confirmation**: MACD bullish crossover (BUY) or bearish (SELL)
    - **Support/Resistance**: SMA(50) acts as support (buy near it)
    - **Volatility**: ATR for stop-loss sizing
    - **Entry/Exit**:
      - BUY: Oversold + trend up + MACD confirm + price near SMA(50)
      - SELL: Overbought OR price breaks SMA(50) support
      - HOLD: No clear signal
  - Confidence scoring (0.0 .. 1.0):
    - Base: 0.5
    - +0.1 per confirmed indicator (RSI + MACD + SMA + price proximity)
    - Cap at 1.0
  - Suggested stops/targets:
    - SL: SMA(50) - ATR
    - TP: SMA(50) + 2*ATR

#### 2.4 Decision Engine
- [ ] Create `finance_service/strategy/decision_engine.py`:
  - Public method: `decide(symbol, recent_ohlcv, config) → Decision`
  - Logic:
    1. Compute all indicators (RSI, MACD, SMA, EMA, ATR, Bollinger, Stochastic)
    2. Run baseline strategy → raw decision
    3. Apply confidence scoring
    4. Generate rationale string
    5. Calculate SL/TP
    6. Return Decision JSON
  - State: None (stateless, re-compute on each call)

#### 2.5 Integration Test
- [ ] Test: Feed real AAPL data → compute indicators → run strategy → verify Decision output

### Deliverables

- ✅ `finance_service/indicators/calculator.py` (7+ indicators)
- ✅ `finance_service/strategy/interface.py` (abstract class)
- ✅ `finance_service/strategy/baseline_rule.py` (configurable rules)
- ✅ `finance_service/strategy/decision_engine.py` (orchestrator)
- ✅ Unit tests (each indicator, strategy rules, decision engine)
- ✅ Integration test (OHLCV → Decision)

### Success Criteria

```bash
# Should pass:
python -m pytest tests/test_indicators.py -v          # All indicators compute correctly
python -m pytest tests/test_strategy.py -v            # Strategy rules work
python -m pytest tests/test_decision_engine.py -v     # Decision JSON valid

# Manual test:
python -c "from finance_service.strategy.decision_engine import decide; d = decide('AAPL', ohlcv, config); print(f'Decision: {d.decision}, Confidence: {d.confidence}')"
# Should print decision + confidence between 0 and 1

# Verify no hallucination:
# - RSI calculated from close prices only (no invented values)
# - MACD uses only historical closes (no future peeking)
# - All outputs deterministic (same input → same output)
```

---

## Phase 3: Portfolio Simulation & Risk Validation (Week 6-7)

**Goal**: Implement paper trading portfolio, risk checks, position sizing.

### Tasks

#### 3.1 Portfolio Simulation Engine
- [ ] Create `finance_service/sim/portfolio.py`:
  - Class `SimulatedPortfolio`:
    - State: `cash`, `positions` (dict of Position), `trade_history` (list), `equity_snapshots` (list)
    - Methods:
      - `__init__(initial_cash=100000)`
      - `get_state() → {cash, positions, equity, total_value, pnl, max_drawdown}`
      - `execute_buy(symbol, qty, price) → Trade` (updates state, logs to history)
      - `execute_sell(symbol, qty, price) → Trade` (updates state, logs)
      - `mark_to_market(price_dict) → equity_snapshot` (update unrealized P&L)
      - `reset(mode='clear') → None` (wipe or archive history)
      - `add_equity_snapshot() → None` (record equity at a point in time)
    - Tracking:
      - Average cost per position (FIFO or weighted)
      - Realized P&L (when selling)
      - Unrealized P&L (mark-to-market)
      - Equity curve (max value, current value)
      - Max drawdown (% from peak to trough)
    - Persistence: Save/load from SQLite

#### 3.2 Risk Validator
- [ ] Create `finance_service/risk/validator.py`:
  - Class `RiskValidator`:
    - Methods:
      - `validate_trade(trade_proposal, portfolio_state, config) → {valid: bool, errors: [str], warnings: [str]}`
      - Checks:
        1. Position size: New position ≤ max_position_size_pct * portfolio_equity
        2. Total exposure: Sum of all positions ≤ max_total_exposure_pct * portfolio_equity
        3. Daily loss: Realized + unrealized daily loss ≥ -max_daily_loss_pct * starting_cash
        4. Max drawdown: Current drawdown ≤ max_drawdown_pct
        5. Halts: If any breach detected, mark halt flag (no more trades until reset)
      - Returns: {valid: bool, checks_passed: [str], checks_failed: [str]}

#### 3.3 Execution Engine
- [ ] Create `finance_service/sim/execution.py`:
  - Class `ExecutionEngine`:
    - Methods:
      - `execute(decision: Decision, portfolio: SimulatedPortfolio, config) → ExecutionReport`
      - Logic:
        1. Validate decision (price not stale, volume available)
        2. Estimate position size using config (% of capital or kelly criterion)
        3. Calculate fill price (close + slippage configurable)
        4. Simulate trade: Call portfolio.execute_buy/sell()
        5. Generate ExecutionReport with:
           - Trade details (symbol, side, qty, price)
           - Confidence + rationale
           - Signals used
           - Risk checks passed/failed
           - Portfolio impact (cash, equity, exposure, max drawdown)
        6. Return report
      - Slippage: Configurable parameter (default 0.1%)

#### 3.4 Metrics Computation
- [ ] Create `finance_service/sim/metrics.py`:
  - Stateless functions:
    - `compute_equity_curve(equity_snapshots) → {dates, values}`
    - `compute_max_drawdown(equity_curve) → float[0..1]`
    - `compute_daily_returns(equity_curve) → float[]`
    - `compute_cagr(start_value, end_value, years) → float`
    - `compute_sharpe_ratio(returns, risk_free_rate=0.02) → float`
    - `compute_win_rate(trades) → float[0..1]`
    - `compute_profit_factor(trades) → float`

#### 3.5 Integration Test
- [ ] Test: Execute 5 buys + 2 sells → verify portfolio state + risk checks + execution reports

### Deliverables

- ✅ `finance_service/sim/portfolio.py` (state + persistence)
- ✅ `finance_service/risk/validator.py` (risk checks)
- ✅ `finance_service/sim/execution.py` (trade execution)
- ✅ `finance_service/sim/metrics.py` (equity curve, drawdown, CAGR)
- ✅ Unit tests (portfolio, risk validator, execution)
- ✅ Integration test (buy/sell sequence → metrics)

### Success Criteria

```bash
# Should pass:
python -m pytest tests/test_portfolio.py -v           # Portfolio buy/sell/reset
python -m pytest tests/test_risk.py -v                # Risk validation
python -m pytest tests/test_execution.py -v           # Execution reports

# Manual test:
python -c "from finance_service.sim.portfolio import SimulatedPortfolio; p = SimulatedPortfolio(100000); p.execute_buy('AAPL', 10, 150); print(p.get_state())"
# Should show: cash reduced, position added, equity updated

# Verify risk checks work:
python -c "from finance_service.risk.validator import RiskValidator; r = RiskValidator(); result = r.validate_trade(trade, portfolio, config); print(result['checks_passed'])"
```

---

## Phase 4: Risk Management & Approval Workflow (Weeks 8-9) - ✅ COMPLETE

**Goal**: Implement multi-layered risk management, approval workflow, and exposure monitoring.

**STATUS**: ✅ COMPLETE - 4 Mar 2026  
**Tests**: 31/31 PASSING | Combined 1-4: 125/125 PASSING  
**Production Code**: 1,150 lines | Deliverables: 5/5 ✅

### Completed Deliverables

- ✅ `finance_service/risk/models.py` (400 lines)
  - RiskPolicy, RiskLimit, RiskCheckType, ApprovalStatus
  - RiskCheckResult, ApprovalRequest dataclasses
  - Full serialization and validation

- ✅ `finance_service/risk/approval_engine.py` (200 lines)
  - ApprovalEngine for request lifecycle management
  - Create, approve, reject, expire workflows
  - Request tracking and statistics

- ✅ `finance_service/risk/risk_enforcer.py` (300 lines)
  - Multi-point trade validation against policies
  - Risk score calculation (0-100 algorithm)
  - Support for 5 configurable limits

- ✅ `finance_service/risk/exposure_manager.py` (250 lines)
  - Sector exposure tracking and concentration checks
  - Leverage and correlation monitoring
  - Portfolio-wide exposure summary

- ✅ `finance_service/app.py` integration
  - Phase 4 imports and component initialization
  - Risk policy loading from config
  - TRADE_OPENED event handler for risk checks
  - APPROVAL_REQUIRED and TRADE_APPROVED event emission

### Test Coverage

- ✅ `tests/test_phase4_risk_management.py` (700+ lines, 31 tests)
  - TestRiskLimit (4): limit validation, capacity, utilization
  - TestRiskPolicy (4): policy creation, limits, violations
  - TestRiskCheckResult (2): result tracking, violation management
  - TestApprovalEngine (6): request lifecycle, approval workflow
  - TestRiskEnforcer (6): trade validation, risk scoring
  - TestExposureManager (6): sector exposure, leverage, correlation
  - TestPhase4Integration (3): full approval workflow, rejection flow

### System Features

**Risk Management**:
- 5 Enforced Limits: Position Size, Sector Exposure, Leverage, Daily Loss, Drawdown
- Risk Score Calculation: Violations (0-20) + Confidence (0-20) + Position (0-20)
- Approval Requirement Logic: Based on risk score and confidence threshold
- Policy Customization: Adjustable via config/finance.yaml

**Approval Workflow**:
- Request Creation with auto-expiration (1 hour default)
- Manual Approval/Rejection by risk manager
- Request Status Tracking: PENDING → APPROVED/REJECTED/EXPIRED
- Approval Analytics: Statistics on request handling

**Exposure Management**:
- Sector Exposure % Calculation and Limits
- Gross/Net Exposure Tracking
- Leverage Calculation (exposure / equity)
- Position Correlation Monitoring
- Portfolio-wide Exposure Summary

**Event Integration**:
- Consumes: TRADE_OPENED (from Phase 3)
- Performs: Multi-check risk validation
- Emits: APPROVAL_REQUIRED (if violations) or TRADE_APPROVED (if passed)
- Fully Async: Non-blocking event-driven flow

### See Also
- `PHASE4_COMPLETION_REPORT.md` - Detailed completion report with full metrics
- `finance_service/risk/` - Complete Phase 4 source code

---

## Phase 5: Backtesting Engine (Week 10)

**Goal**: Implement historical backtesting with zero lookahead bias and performance metrics.

### Tasks

#### 5.1 Backtest Engine
- [ ] Create `finance_service/sim/backtest.py`:
  - Class `BacktestEngine`:
    - Methods:
      - `run(symbols, start_date, end_date, strategy, config) → BacktestResult`
      - Logic:
        1. Fetch historical OHLCV for date range (no future peeking!)
        2. Initialize portfolio (starting_cash)
        3. Iterate through dates (chronologically):
           - Mark-to-market positions
           - Run decision engine on current OHLCV (up to current date only)
           - If decision: Execute trade (respecting fill rule)
           - Record trade + equity snapshot
        4. Compute end metrics:
           - Final equity
           - Max drawdown
           - CAGR
           - Sharpe ratio
           - Win rate
           - Profit factor
           - # Trades
        5. Return BacktestResult (with equity curve, trades, metrics)
    - Fill rule: Configurable (close or next_open)
    - Slippage: Configurable
    - Zero lookahead: Strict chronological order, no future data access

#### 5.2 Fast Backtester
- [ ] Optimize for speed:
    - Vectorize computations where possible
    - Cache indicator calculations (avoid recompute)
    - Batch database writes
    - Progress bar (tqdm) for long runs

#### 5.3 Backtest Result Storage
- [ ] Extend `finance_service/storage/backtest.sqlite`:
  - Store: run_id, symbols, date range, metrics, trades, equity curve
  - Query methods: `get_backtest_result(run_id)`, `list_backtests()`, `compare_backtests(run_ids)`

#### 5.4 REST API
- [ ] Add endpoints:
  - `POST /backtest` (symbols, date_range, config) → BacktestResult JSON + run_id
  - `GET /backtest/{run_id}` → BacktestResult (with metrics + equity curve)
  - `GET /backtest/list` → List of all backtest runs

#### 5.5 Integration Test
- [ ] Test: Run backtest on AAPL (1 year) → verify metrics computed → verify no lookahead

### Deliverables

- ✅ `finance_service/sim/backtest.py` (engine + zero lookahead)
- ✅ Result storage + retrieval
- ✅ REST API endpoints
- ✅ Unit tests (fill rule, slippage, metrics)
- ✅ Integration test (full backtest run)

### Success Criteria

```bash
# Should pass:
python -m pytest tests/test_backtest.py -v            # Backtest engine

# Manual test:
curl POST http://localhost:5000/backtest -d '{"symbols": ["AAPL"], "start_date": "2023-01-01", "end_date": "2024-01-01"}'
# Should return: BacktestResult with CAGR, max DD, Sharpe, etc.

# Verify zero lookahead:
# - No future prices used in decision
# - Metrics match manual calculation
# - Next-open fill rule works correctly
```

---

## Phase 6: Streamlit UI Dashboard (Week 11)

**Goal**: Build interactive dashboard showing portfolio, trade history, charts, and backtest results.

### Tasks

#### 6.1 Main Dashboard
- [ ] Create `ui/dashboard.py`:
  - Streamlit app entry point
  - Page structure:
    - Home (portfolio summary + charts)
    - Trade History (filterable table + CSV export)
    - Backtest Results (metrics + charts)
    - Settings (config viewer)

#### 6.2 Portfolio Status Page
- [ ] Create `ui/pages/portfolio.py`:
  - Display:
    - KPI row: Total equity | Cash | Exposure % | Max DD %
    - Positions table: Symbol | Qty | Avg Cost | Last Price | Unrealized PnL | % Return
    - Risk alerts: ⚠️ if approaching limits
    - Exposure pie chart (by symbol or sector)
    - Equity curve: Time series of total equity
    - Drawdown chart: Time series of max drawdown
  - Refresh: Real-time via API calls or cached (configurable)

#### 6.3 Trade History Page
- [ ] Create `ui/pages/trade_history.py`:
  - Display:
    - Trade log table: Timestamp | Symbol | Side | Qty | Price | Reason | Task ID
    - Filters: Date range, symbol, side (BUY/SELL), tag (auto-execute vs approval)
    - Export: CSV download button
  - Pagination or infinite scroll
  - Total trades count, win rate in header

#### 6.4 Charts Page
- [ ] Create `ui/pages/charts.py`:
  - Display:
    - Equity curve (line chart)
    - Drawdown curve (area chart, red)
    - Price chart with buy/sell markers (select symbol from dropdown)
    - Indicator overlay: RSI, MACD, SMA on price chart
  - Interactive: Hover for details, zoom, pan
  - Date range selector

#### 6.5 Backtest Page
- [ ] Create `ui/pages/backtest.py`:
  - Display:
    - Backtest runs list (dropdown to select)
    - Metrics table: Start | End | Symbol | CAGR | Max DD | Win Rate | Sharpe | # Trades
    - Equity curve (backtest vs live if available)
    - Monthly returns heatmap
    - Drawdown analysis chart
  - Buttons:
    - Run new backtest (input: symbols, date range)
    - Download report (CSV)
    - Compare backtests (select 2-3 runs)

#### 6.6 Settings Page (Optional)
- [ ] Create `ui/pages/settings.py`:
  - Display: Current config (YAML files) in read-only format
  - Edit button (optional): Allow inline editing of finance.yaml
  - Reload config button

#### 6.7 Utilities
- [ ] Create `ui/utils.py`:
  - Helper functions:
    - `fetch_api(endpoint) → json` (cached with TTL)
    - `format_currency(num) → str`
    - `format_percent(num) → str`
    - `plot_equity_curve(equity_snapshots) → plotly chart`
    - etc.

#### 6.8 Configuration
- [ ] Streamlit config: `.streamlit/config.toml`
  - Theme, layout, etc.

### Deliverables

- ✅ `ui/dashboard.py` (main app)
- ✅ `ui/pages/portfolio.py`
- ✅ `ui/pages/trade_history.py`
- ✅ `ui/pages/charts.py`
- ✅ `ui/pages/backtest.py`
- ✅ `ui/pages/settings.py` (optional)
- ✅ `ui/utils.py`
- ✅ `.streamlit/config.toml`

### Success Criteria

```bash
# Should run:
streamlit run ui/dashboard.py
# Should display portfolio status, interact with API, show charts

# Manual test:
# - Portfolio page shows correct cash/equity
# - Trade history table populated + filters work
# - Charts load + interactive
# - Backtest page shows results when backtest runs
```

---

## Phase 7: Integration & Telegram Bot Integration (Week 12)

**Goal**: Integrate all components, wire up Telegram bot, ensure hot-reload works end-to-end.

### Tasks

#### 7.1 PicoClaw Telegram Bot Configuration
- [ ] Create `picoclaw_config/finance_router_rules.yaml`:
  - Intent routing rules:
    - Pattern: ticker symbol (AAPL, MSFT, etc.) → Route to finance.analyze_symbol
    - Pattern: "analyze" + symbol → finance.analyze_symbol
    - Pattern: "backtest" → finance.run_backtest
    - Pattern: "portfolio" → finance.portfolio_state
    - Pattern: "history" → finance.trade_history
  - Confidence thresholds (0.7+ to route to finance)

#### 7.2 Finance System Prompt
- [ ] Create `picoclaw_config/finance_system_prompt.md`:
  - Instructions for LLM:
    - Tool-first approach: Always call tools, don't fabricate prices/data
    - Available tools: analyze_symbol, run_backtest, portfolio_state, trade_history, send_execution_report
    - Constraints: No hallucination, no real trading, paper trading only
    - Output format: JSON for decisions, natural language for explanations

#### 7.3 Tool Schemas
- [ ] Create `picoclaw_config/tool_schemas.json`:
  - OpenAPI schema for all Finance Service tools:
    - analyze_symbol(symbol) → Decision
    - run_backtest(symbols, date_range) → BacktestResult
    - portfolio_state() → Portfolio
    - trade_history() → [Trade]
    - send_execution_report(execution_report) → Confirmation

#### 7.4 Telegram Bot Bridge
- [ ] Ensure Telegram bot (existing PicoClaw) can:
  - Send approval requests to user
  - Receive button clicks (Approve/Reject)
  - Send execution reports
  - Reuse existing credentials + pairing
- [ ] Test: Send message to bot → triggers finance analysis → receives execution report

#### 7.5 Config Hot-Reload Integration
- [ ] Wire up hot-reload:
  - File watcher on `config/` directory
  - On change: Reload YAML in config engine
  - Cascade effects:
    - Universe scanner updates symbol list
    - Strategy parameters update
    - Risk limits update
    - Backtest defaults update
  - Log config change to audit log
  - Optional: Send Telegram notification of config change

#### 7.6 End-to-End Testing
- [ ] Test flows:
  1. User sends "analyze AAPL" to Telegram bot
  2. Bot routes to Finance Service
  3. Service fetches data → analyzes → decides
  4. If high confidence: Auto-execute → send report to Telegram
  5. If low confidence: Request approval → wait → execute or reject
  6. Check dashboard: Trade appears in history + portfolio updated

### Deliverables

- ✅ `picoclaw_config/finance_router_rules.yaml`
- ✅ `picoclaw_config/finance_system_prompt.md`
- ✅ `picoclaw_config/tool_schemas.json`
- ✅ Telegram bot integration tests
- ✅ Hot-reload integration tests
- ✅ End-to-end integration tests

### Success Criteria

```bash
# Should pass:
# 1. User sends Telegram message → bot routes to finance
# 2. Finance service analyzes + decides
# 3. Auto-execute if confident OR request approval
# 4. Execution report appears in Telegram + dashboard
# 5. Config change on disk → reloaded in service

# Manual test:
# - Send "analyze NVDA" to Telegram bot
# - Wait for execution report or approval request
# - Check dashboard: Trade in history, portfolio updated
```

---

## Phase 8: Testing & Validation (Week 13)

**Goal**: Comprehensive testing of all components, edge cases, and deployment readiness.

### Tasks

#### 8.1 Unit Test Coverage
- [ ] Complete test suite:
  - `tests/test_config_engine.py` (config load, hot-reload, validation)
  - `tests/test_cache.py` (TTL, hit rate, expiration)
  - `tests/test_data_provider.py` (fetch, batch, backoff, retry)
  - `tests/test_universe_scanner.py` (theme matching, dedup, exclude)
  - `tests/test_indicators.py` (RSI, MACD, SMA, ATR, etc., correctness)
  - `tests/test_strategy.py` (rule engine, confidence scoring)
  - `tests/test_decision_engine.py` (full decision generation)
  - `tests/test_portfolio.py` (buy/sell, state, reset)
  - `tests/test_risk.py` (position limit, exposure, daily loss)
  - `tests/test_execution.py` (trade execution, slippage)
  - `tests/test_backtest.py` (zero lookahead, metrics)
  - `tests/test_task_processor.py` (event processing, auto-execute)
  - `tests/test_approval_handler.py` (approval workflow)
- [ ] Target: > 80% code coverage

#### 8.2 Integration Tests
- [ ] Multi-component tests:
  - Data fetch → cache → event → analysis → decision
  - Auto-execute flow (high confidence)
  - Approval workflow (low confidence)
  - Portfolio state + risk validation
  - Full backtest run (1 year of data)
  - Config hot-reload → universe update
  - Telegram approval request/response

#### 8.3 Edge Cases
- [ ] Handle:
  - Missing data (symbol not found, incomplete OHLCV)
  - Rate limit hits (backoff + retry)
  - Network errors (timeout, 500s)
  - Invalid config (syntax error, missing keys)
  - Insufficient portfolio cash (reduce position size)
  - Risk limit breaches (halt trading)
  - Concurrent requests (thread-safe)
  - Portfolio reset during active trades

#### 8.4 Performance Tests
- [ ] Measure:
  - Data fetch time (batch vs sequential)
  - Indicator computation speed (large dataset)
  - Strategy decision latency (< 100ms target)
  - Backtest speed (1 year of daily data < 5s)
  - API response time (< 500ms target)

#### 8.5 Validation Script
- [ ] Create `scripts/validate.py`:
  - Check:
    - All imports work
    - Config loads + valid schema
    - SQLite schema created
    - API endpoints respond
    - Indicators compute correctly
    - Strategy runs without error
    - Portfolio simulation works
    - Backtest runs without lookahead violations
  - Output: Summary report

### Deliverables

- ✅ Comprehensive test suite (13+ test modules)
- ✅ > 80% code coverage
- ✅ Integration tests (all major flows)
- ✅ Edge case tests
- ✅ Performance tests
- ✅ `scripts/validate.py` (validation script)

### Success Criteria

```bash
# Should pass:
pytest tests/ -v --cov=finance_service
# Output: > 80% code coverage, all tests pass

python scripts/validate.py
# Output: All checks pass (config, API, indicators, portfolio, backtest)
```

---

## Phase 9: Documentation & Deployment (Week 14)

**Goal**: Complete documentation, prepare deployment packages, and production readiness.

### Tasks

#### 9.1 Documentation
- [ ] Create/update:
  - `README.md` (overview, quick start, features)
  - `DEPLOYMENT.md` (systemd service, nginx proxy, monitoring)
  - `USER_GUIDE.md` (how to use dashboard, configure, run backtest)
  - `DEVELOPER_GUIDE.md` (architecture, extending strategy, adding indicators)
  - `API_REFERENCE.md` (all REST endpoints, request/response schemas)
  - `CONFIG_REFERENCE.md` (all YAML keys, defaults, meanings)
  - `TROUBLESHOOTING.md` (common issues + solutions)

#### 9.2 Deployment Artifacts
- [ ] Create:
  - `Dockerfile` (if Docker deployment desired)
  - `docker-compose.yml` (service + redis cache + nginx + prometheus)
  - Systemd service file: `picotradeagent.service`
  - Nginx config: `picotradeagent-nginx.conf`
  - Monitoring: Prometheus config, Grafana dashboard JSON

#### 9.3 Scripts
- [ ] Create:
  - `scripts/backtest_runner.py` (standalone backtest CLI)
  - `scripts/reset_portfolio.py` (portfolio reset utility)
  - `scripts/export_backtest.py` (export backtest results to CSV)
  - `scripts/install.sh` (setup entrypoint)

#### 9.4 Example Configurations
- [ ] Create example configs:
  - `config/finance_example_conservative.yaml` (low risk)
  - `config/finance_example_aggressive.yaml` (high risk)
  - `config/schedule_example.yaml` (example job schedule)

#### 9.5 Demo Data
- [ ] Prepare demo:
  - Sample SQLite databases with example trades + backtests
  - Demo config file
  - Sample Telegram messages

#### 9.6 Deployment Runbook
- [ ] Document:
  - Prerequisites (Python 3.8+, sqlite3, systemd)
  - Installation steps
  - Configuration steps
  - Service startup
  - Health checks
  - Monitoring setup
  - Troubleshooting

### Deliverables

- ✅ Complete documentation (6+ documents)
- ✅ Deployment artifacts (Dockerfile, Docker Compose, systemd, nginx)
- ✅ Utility scripts (backtest, reset, export)
- ✅ Example configurations
- ✅ Deployment runbook
- ✅ Demo data

### Success Criteria

```bash
# Deployment readiness:
# - systemd service starts cleanly
# - nginx proxy routes /api requests correctly
# - Streamlit dashboard accessible
# - Telegram bot integration works
# - All documentation complete + accurate

# Smoke test:
# 1. Deploy on fresh Linux VM
# 2. Run install.sh
# 3. Start services
# 4. Run backtest
# 5. Check dashboard
# 6. Send Telegram message → receive response
```

---

## Timeline Summary

| Phase | Duration | Milestones |
|-------|----------|-----------|
| 0 | 1 week | Config engine, SQLite schema, Flask skeleton ✅ |
| 1 | 2 weeks | Data layer, cache, universe scanner ✅ |
| 2 | 2 weeks | Indicators, strategy, decision engine ✅ |
| 3 | 2 weeks | Portfolio simulation, risk validation ✅ |
| 4 | 2 weeks | Event processing, approval workflow ✅ |
| 5 | 1 week | Backtest engine ✅ |
| 6 | 1 week | Streamlit UI ✅ |
| 7 | 1 week | Telegram integration, hot-reload ✅ |
| 8 | 1 week | Testing & validation ✅ |
| 9 | 1 week | Documentation & deployment ✅ |
| **Total** | **~14 weeks** | **Ready for production** |

---

## Dependencies & Prerequisites

### Technologies
- Python 3.8+
- Flask or FastAPI
- SQLite3
- Streamlit
- yfinance
- pandas, numpy
- python-telegram-bot
- APScheduler

### External Services
- OpenClaw/PicoClaw Telegram bot (existing, reuse)
- yfinance API (free, Yahoo Finance data)
- (Optional) Prometheus + Grafana (monitoring)

### Development Tools
- pytest (testing)
- Git (version control)
- Linux/systemd (deployment)
- Nginx (reverse proxy)

---

## Risk & Mitigation

| Risk | Mitigation |
|------|-----------|
| yfinance rate limits | Batch fetch, jitter, cache, backoff/retry |
| LLM hallucination | Zero LLM computation (local indicators only) |
| Telegram approval timeout | Fallback to auto-execute if threshold met |
| Portfolio loss | Risk limits enforce max drawdown + daily loss stops |
| Config errors | Schema validation + audit logging |
| Data lookahead in backtest | Strict chronological order, test edge cases |

---

## Success Criteria (Final)

✅ **All Phases Complete**
- Phase 0-9 deliverables completed
- > 80% test coverage
- Zero critical bugs in final testing

✅ **Functional Requirements**
1. Single Telegram bot reused (no new bot)
2. YAML configuration (hot-reload works)
3. Event-driven analysis (data_ready triggers)
4. Auto-execute on high confidence (configurable threshold)
5. Approval workflow for lower confidence
6. Paper trading simulation with real data
7. Portfolio reset capability
8. Historical backtesting (zero lookahead)
9. Streamlit UI (portfolio, trades, charts, backtest)
10. All executions reported to Telegram

✅ **Non-Functional Requirements**
- API response time < 500ms
- Backtest speed: 1 year data < 5s
- Test coverage > 80%
- Documentation complete
- Deployment artifacts ready

✅ **Production Ready**
- Systemd service + auto-restart
- Nginx reverse proxy + SSL
- Monitoring configuration
- Runbook for deployment
- Troubleshooting guides

---

**Created**: 2026-03-04  
**Version**: v1 (Phase Planning)  
**Status**: Ready for Phase 0 kickoff  
**Next Step**: Allocate developer resources + start Phase 0 bootstrap
