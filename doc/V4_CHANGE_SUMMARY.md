# OpenClaw Finance Agent v4 - Change Summary & Update Guide

**Date**: 2026-03-04  
**Project**: OpenClaw Finance Agent  
**Version**: v4 (Major Redesign)  
**Previous**: v3 (PicoClaw-based, baseline implementation)

---

## 1. What Changed from v3 to v4?

### Major Architectural Changes

| Aspect | v3 | v4 | Benefit |
|--------|--|----|---------|
| **Telegram Integration** | Create new bot | Reuse existing bot | Simplify setup, leverage pairing |
| **Configuration** | Code-based defaults | YAML-first approach | Token efficiency, reproducible, hot-reload |
| **Processing** | Batch (wait for all symbols) | Event-driven (analyze ASAP) | Faster trades, responsive system |
| **Auto-Execution** | Manual approval only | Conditional auto-execute | Autonomous trades on high confidence |
| **Universe** | Fixed watchlist | Theme/industry-focused scanning | Flexible, dynamic universe selection |
| **UI** | None | Streamlit dashboard | Real-time visibility, charts, export |
| **Backtesting** | Basic simulation | Full historical backtest | Validate strategies with metrics |
| **Data Source** | OpenBB (official) | yfinance (free, rate-limit optimized) | Cost-effective, with batching + cache + jitter |

### New Features in v4

1. **YAML-Based Configuration** ✨
   - All settings in YAML files: `config/finance.yaml`, `config/schedule.yaml`, `config/providers.yaml`
   - Hot-reload on file change (no restart needed)
   - Config audit log (before/after diffs)
   - Reduces token waste, enables reproducible behavior

2. **Event-Driven Processing** ✨
   - Emit `data_ready(symbol, timeframe)` immediately on data fetch completion
   - Parallel symbol analysis (not sequential batching)
   - Faster decision-making

3. **Conditional Auto-Execution** ✨
   - Auto-execute if: confidence ≥ threshold + risk checks pass
   - Configurable threshold: `auto_execute_confidence_threshold` (0.0..1.0)
   - Always generate execution report + send to Telegram

4. **Theme-Based Universe Scanning** ✨
   - Select stocks by theme keywords (AI, semiconductor, cloud, energy, etc.)
   - Combine with explicit watchlist
   - Exclude list support
   - Max universe size limit

5. **Streamlit UI Dashboard** ✨
   - **Portfolio Status**: Cash, positions, exposure, risk flags, equity curve
   - **Trade History**: Log with filters (date, symbol, side), CSV export
   - **Charts**: Equity curve, drawdown, price + buy/sell markers, indicator overlay
   - **Backtest Results**: Metrics table, comparison, monthly returns heatmap
   - **Settings**: Config viewer (read-only recommended)

6. **Rate-Limit Optimization** ✨
   - **Batch Fetch**: Request multiple symbols in single call (yfinance)
   - **Jitter**: Random delays between requests (avoid thundering herd)
   - **Backoff/Retry**: Exponential backoff on HTTP 429 (rate limit)
   - **SQLite Cache**: OHLCV with TTL (configurable per timeframe)
   - **Request Tracking**: Log API calls per run (transparency)

7. **Approval & Execution Reports** ✨
   - **Approval Request**: Inline buttons in Telegram (Approve/Reject)
   - **Execution Report**: Always sent to Telegram with:
     - Symbol, side, qty, fill price, confidence
     - Key signals used (RSI, MACD, SMA, etc.)
     - Risk checks passed
     - Portfolio impact snapshot (cash, equity, exposure, drawdown)

8. **Portfolio Reset Support** ✨
   - Reset to configured starting cash (default $100k)
   - Two modes:
     - `clear`: Wipe all history
     - `archive`: Move history to separate archive
   - Useful for A/B testing strategies

9. **Historical Backtesting** ✨
   - Chronological date replay (zero lookahead bias)
   - Configurable fill rule: close price or next open
   - Metrics computed:
     - CAGR (annualized return)
     - Max drawdown
     - Sharpe ratio
     - Win rate
     - Profit factor
   - Results stored in SQLite + visualized in UI

10. **Deployment-Ready** ✨
    - Systemd service file
    - Nginx reverse proxy config
    - Docker + Docker Compose stack
    - Prometheus metrics + Grafana dashboard config
    - Complete deployment runbook

---

## 2. Key Design Principles

### 2.1 YAML-First Configuration

**Philosophy**: Minimize token waste, enable reproducible behavior, support hot-reload.

**How It Works**:
- All system behavior defined in YAML (not code)
- Changed config → reload within N seconds (no restart)
- Config changes logged with audit trail
- Optional: Agent can update YAML directly (with logging)

**Files**:
```
config/
├── finance.yaml          # Universe, risk, strategy, backtest
├── schedule.yaml         # Job schedules (daily scan, hourly update, backtest)
└── providers.yaml        # Data provider, caching, rate limiting
```

### 2.2 Event-Driven Processing

**Philosophy**: Analyze ASAP when data is ready, don't wait for batch.

**How It Works**:
1. Fetch symbols in parallel/batch
2. As each symbol's data completes → emit `data_ready(symbol, timeframe)` event
3. Event triggers: Fetch indicators → run strategy → validate risk → auto-execute or request approval
4. Multiple symbols process in parallel (no blocking)

**Benefit**: Faster trades, responsive system.

### 2.3 Conditional Auto-Execution

**Philosophy**: Enable autonomy for high-conviction trades; retain control via threshold + risk gates.

**How It Works**:
```
If (confidence >= auto_execute_confidence_threshold) AND (risk validation passes):
    Auto-execute immediately
    Send execution report to Telegram
Else:
    Request approval via Telegram (inline buttons)
    Wait for user response
    Execute or cancel based on response
```

**Configurable**: Threshold set in `config/finance.yaml` (default 0.75 = 75%)

### 2.4 Zero LLM Hallucination

**Philosophy**: LLM must not invent prices, returns, or indicators.

**How It Works**:
- All indicators (RSI, MACD, SMA, ATR, etc.) computed locally in Python
- LLM interprets signals but cannot compute them
- Strategy rules are deterministic (no LLM involved)
- Decision JSON has strict schema (decision, confidence, signals, SL/TP)

**Benefit**: Prevents catastrophic errors, maintains accuracy.

### 2.5 Rate-Limit Optimization

**Philosophy**: yfinance is free but rate-limited; optimize usage strategically.

**How It Works**:
- **Batch Fetch**: Request 10 symbols at once (vs 1 at a time)
- **Jitter**: Add random delay (0.1-0.5 sec) between requests
- **Backoff/Retry**: Exponential backoff on HTTP 429 (rate limit hit)
- **SQLite Cache**: OHLCV with TTL (1 day for daily data, 1 hour for hourly)
- **Request Tracking**: Log all API calls per run

**Benefit**: Maximize free tier usage, minimize rate limit hits.

### 2.6 Paper Trading Focus

**Philosophy**: Simulate trading only; no real money at risk.

**How It Works**:
- Track portfolio in SQLite (cash, positions, P&L)
- Fill prices from historical/current market data (no fabrication)
- Slippage configurable (default 0.1%)
- Halt trading if max drawdown or daily loss limit breached
- Support reset (clear or archive history)

**Benefit**: Safe experimentation, risk-free learning.

---

## 3. New Data Models

### 3.1 Decision JSON (Strategy Output)

```json
{
  "task_id": "uuid",
  "symbol": "AAPL",
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

### 3.2 ExecutionReport (Auto or Manual)

```json
{
  "task_id": "uuid",
  "trade_id": "uuid",
  "symbol": "AAPL",
  "side": "BUY",
  "qty": 50,
  "fill_price": 184.9,
  "reason": "auto_execute (confidence=0.78 ≥ threshold=0.75)",
  "signals_used": ["RSI oversold", "MACD bullish", "SMA support"],
  "risk_checks_passed": [
    "position_limit: 5% ≤ 20%",
    "total_exposure: 45% ≤ 90%",
    "daily_loss: -$500 ≥ -$3000"
  ],
  "portfolio_impact": {
    "cash_before": 99000,
    "cash_after": 90754.50,
    "total_value": 100254.50,
    "exposure_pct": 45.2,
    "max_drawdown_pct": 2.1
  }
}
```

---

## 4. Configuration Schema Overview

### 4.1 config/finance.yaml (Key Sections)

```yaml
universe:
  market: US  # Market to scan
  theme_keywords: [AI, semiconductor]  # Industry themes
  watchlist: [AAPL, MSFT, NVDA]  # Explicit symbols
  exclude: [TEMP, XYZZ]  # Excluded symbols
  max_size: 50  # Max universe size

risk:
  starting_cash: 100000  # Portfolio starting capital
  max_position_size_pct: 20  # Max position = 20% of equity
  max_total_exposure_pct: 90  # Max total positions = 90%
  max_daily_loss_pct: 3  # Stop if daily loss > 3%
  max_drawdown_pct: 10  # Stop if drawdown > 10%
  auto_execute_confidence_threshold: 0.75  # ← NEW: Auto-execute if confidence ≥ 75%

strategy:
  type: baseline_rule  # Rule-based (deterministic)
  indicators:
    rsi: {period: 14, oversold: 30, overbought: 70}
    macd: {fast: 12, slow: 26, signal: 9}
    sma: {short: 20, long: 50}
    atr: {period: 14}

backtest:
  date_range: ["2024-01-01", "2026-03-04"]
  fill_rule: close  # close or next_open
  slippage_pct: 0.1
```

### 4.2 config/schedule.yaml (Job Scheduling)

```yaml
jobs:
  daily_universe_scan:
    schedule: "0 8 * * MON-FRI"  # 8 AM weekdays
    action: scan_universe
    
  hourly_update:
    schedule: "0 * * * *"  # Every hour
    action: update_active_positions
```

### 4.3 config/providers.yaml (Data Provider Config)

```yaml
yfinance:
  enabled: true
  batch_size: 10  # Fetch 10 symbols at once
  request_jitter_sec: 0.5  # Random delay (0.5 sec)
  backoff_max_retries: 3  # Retry on rate limit (3x)
  cache_ttl_minutes:
    daily: 1440  # 1 day
    hourly: 60   # 1 hour
  throttle_requests_per_min: 60
```

---

## 5. Updated File Structure

```
openclaw-finance-agent/
├── DESIGN_V4.md                     ← NEW: Detailed design
├── PLAN_IMPLEMENTATION_V4.md        ← NEW: 9-phase plan
├── config/
│   ├── finance.yaml                 ← NEW: Universe, risk, strategy
│   ├── schedule.yaml                ← NEW: Job schedules
│   └── providers.yaml               ← NEW: Data provider config
│
├── finance_service/
│   ├── core/
│   │   ├── config_engine.py         ← NEW: YAML loader + hot-reload
│   │   ├── event_bus.py             ← NEW: Event dispatcher
│   │   └── ... (other core modules)
│   ├── data/
│   │   ├── yfinance_provider.py     ← NEW: Batch + jitter + backoff
│   │   └── universe_scanner.py      ← NEW: Theme-based scanning
│   ├── telegram_bridge/             ← NEW: Telegram integration
│   │   ├── approval_handler.py
│   │   └── notifier.py
│   └── ... (other modules)
│
├── ui/
│   └── dashboard.py                 ← NEW: Streamlit UI
│
├── picoclaw_config/
│   ├── finance_router_rules.yaml    ← NEW: Intent routing
│   ├── finance_system_prompt.md     ← NEW: LLM instructions
│   └── ... (other config)
│
└── ... (tests, scripts, docs)
```

---

## 6. Migration Path (v3 → v4)

### For v3 Users

If you've built v3 (original PicoClaw implementation), here's how to migrate to v4:

1. **Backup v3 Database**
   ```bash
   cp finance_service/storage/*.sqlite backups/
   ```

2. **Create YAML Configuration**
   - Extract settings from code → `config/finance.yaml`
   - Create `config/schedule.yaml` for job schedules
   - Create `config/providers.yaml` for data provider settings

3. **Reuse Data**
   - Copy existing portfolio state, trade history to new schema
   - Optional: Keep v3 database as reference

4. **Test Event-Driven Flow**
   - Emit data_ready events manually
   - Verify analysis pipeline works

5. **Configure Auto-Execution Threshold**
   - Start conservative (0.90 = 90%, very high confidence only)
   - Monitor for 1 week
   - Gradually lower if comfortable (0.75, 0.65, etc.)

6. **Deploy Streamlit UI**
   - Run: `streamlit run ui/dashboard.py`
   - Configure port in `.streamlit/config.toml`

---

## 7. Key Differences in Behavior

### v3: "Always Ask for Approval"
```
User sends "analyze AAPL"
  ↓
Service analyzes → decides BUY (confidence 65%)
  ↓
Send approval request to Telegram
  ↓
User clicks Approve/Reject
  ↓
Execute or cancel
```

### v4: "Auto-Execute if Confident"
```
User sends "analyze AAPL"
  ↓
Service analyzes → decides BUY (confidence 80%)
  ↓
Check: confidence (80%) ≥ threshold (75%) AND risk OK?
  ├─ YES → Auto-execute immediately + send report to Telegram
  └─ NO → Send approval request + wait for response
```

**Result**: Faster trades for high-conviction decisions, manual control for uncertain ones.

---

## 8. Frequently Asked Questions

### Q: Do I need to create a new Telegram bot?
**A**: No! v4 reuses the existing PicoClaw/OpenClaw bot. No new setup needed.

### Q: What if I want all trades to require approval?
**A**: Set `auto_execute_confidence_threshold: 1.0` in config. No trades will auto-execute (require 100% confidence, which rarely happens).

### Q: What if I want all trades to auto-execute?
**A**: Set `auto_execute_confidence_threshold: 0.0` in config. All valid trades execute immediately (risky!).

### Q: Will yfinance rate limits affect me?
**A**: v4 includes batching, jitter, cache, and backoff. For 50 symbols daily, you'll stay well within free tier limits.

### Q: How do I reset the portfolio?
**A**: Call `/reset` endpoint in API (or button in UI). Choose mode: `clear` (wipe history) or `archive` (keep history).

### Q: Can I run backtests?
**A**: Yes! Call `POST /backtest` endpoint. Returns metrics (CAGR, max DD, Sharpe, win rate). Results stored in SQLite.

### Q: How do I see my trades?
**A**: Open Streamlit dashboard → Trade History page. Filter by date/symbol/side. Export as CSV.

### Q: Can I change strategy rules without restarting?
**A**: Yes! Edit `config/finance.yaml` (indicator parameters, thresholds). Service hot-reloads on change.

### Q: Is real money at risk?
**A**: No. All trades are paper trades (simulated in SQLite). No real execution.

---

## 9. Quick Reference: Config Checklist

Before deploying v4, configure these YAML keys:

```yaml
# ✅ finance.yaml
universe.market: "US"                      # Market
universe.theme_keywords: [...]             # Themes to scan
universe.watchlist: [...]                  # Explicit symbols
universe.exclude: [...]                    # Exclude list
universe.max_size: 50                      # Universe limit

risk.starting_cash: 100000                 # Portfolio capital
risk.max_position_size_pct: 20             # Max position
risk.max_total_exposure_pct: 90            # Max exposure
risk.max_daily_loss_pct: 3                 # Daily loss stop
risk.max_drawdown_pct: 10                  # Drawdown stop
risk.auto_execute_confidence_threshold: 0.75  # ← KEY: Auto-execute threshold

strategy.indicators.rsi.period: 14         # Indicator params
strategy.indicators.macd.fast: 12
strategy.indicators.sma.long: 50
strategy.indicators.atr.period: 14

backtest.date_range: [...]                 # Backtest period
backtest.fill_rule: "close"                # Fill rule
backtest.slippage_pct: 0.1                 # Slippage

# ✅ schedule.yaml
jobs:
  daily_universe_scan:
    schedule: "0 8 * * MON-FRI"           # Cron format
    
# ✅ providers.yaml
yfinance.batch_size: 10                    # Batch fetch
yfinance.request_jitter_sec: 0.5           # Jitter
yfinance.backoff_max_retries: 3            # Retries
yfinance.cache_ttl_minutes.daily: 1440     # Cache TTL
```

---

## 10. Testing the v4 Design

### Phase 0 Verification (Bootstrap)
```bash
# Clone and setup
git clone <repo>
cd openclaw-finance-agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Test config engine
python -m pytest tests/test_config_engine.py -v
# Should: Load YAML, validate schema, support hot-reload

# Test Flask API
python finance_service/app.py
curl http://localhost:5000/health
# Should: Return 200 + health JSON
```

### Phase 1 Verification (Data Layer)
```bash
# Test data provider
python -m pytest tests/test_yfinance_provider.py -v
# Should: Fetch AAPL, MSFT (batched), handle rate limits

# Test cache
python -m pytest tests/test_cache.py -v
# Should: Store/retrieve OHLCV, expire on TTL

# Test universe scanner
python -c "from finance_service.data.universe_scanner import scan_universe; print(scan_universe(['AI']))"
# Should: Return list of AI-related symbols
```

### Phase 2 Verification (Indicators & Strategy)
```bash
# Test indicators
python -m pytest tests/test_indicators.py -v
# Should: RSI, MACD, SMA compute correctly

# Test decision engine
python -c "from finance_service.strategy.decision_engine import decide; d = decide('AAPL', ohlcv, config); print(d)"
# Should: Return Decision JSON with confidence
```

### Full Integration Test
```bash
# Run complete flow
bash tests/integration_test.sh
# Should: Fetch → analyze → decide → execute → report
```

---

## 11. Success Metrics

✅ **v4 Launch Checklist**

- [ ] All 3 YAML config files created + validated
- [ ] Event-driven processing working (data_ready events)
- [ ] Auto-execution triggers on high confidence
- [ ] Approval workflow works (Telegram inline buttons)
- [ ] Execution reports sent to Telegram
- [ ] Streamlit UI shows portfolio + trades + charts
- [ ] Backtesting produces valid metrics (zero lookahead)
- [ ] Config hot-reload working (no restart needed)
- [ ] Rate-limit optimization prevents 429 errors
- [ ] > 80% test coverage
- [ ] Deployment artifacts ready (systemd, nginx, Docker)

---

## 12. Next Steps

1. **Review Design**: Read `DESIGN_V4.md` in full
2. **Review Plan**: Read `PLAN_IMPLEMENTATION_V4.md` (phases 0-9)
3. **Start Phase 0**: Bootstrap config engine + SQLite schema
4. **Track Progress**: Use `PLAN_IMPLEMENTATION_V4.md` as checklist
5. **Deploy**: Follow deployment runbook in `DEPLOYMENT.md` (to be created)

---

**Version**: v4 (Updated 2026-03-04)  
**Status**: Design phase complete, ready for implementation  
**Context**: Transitioning from v3 (basic simulation) to v4 (production-ready autonomous trading system)  
**Estimated Duration**: 14 weeks (full-time development)
