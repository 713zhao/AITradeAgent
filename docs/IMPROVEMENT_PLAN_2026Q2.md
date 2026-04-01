# AITradeAgent Improvement Plan - Q2 2026

**Based on:** Comparative analysis with TradingAgents framework  
**Date:** 2026-04-01  
**Target Branch:** `feature/llm-augmentation-advanced-backtesting`  
**Status:** Planning Phase

---

## Executive Summary

AITradeAgent is a production-ready, event-driven paper trading system with solid risk management and operational excellence. This plan introduces optional LLM augmentation, advanced backtesting, multi-symbol portfolio optimization, fundamental data integration, and options support — transforming it from a robust rule-based system into a hybrid AI-enhanced trading platform.

---

## 1. LLM Augmentation Layer (Optional)

### Rationale
TradingAgents demonstrates the power of LLM-based market reasoning. We'll add **optional** LLM modules that can be toggled via configuration, preserving deterministic behavior as the default.

### Components

#### 1.1 Market Regime Classifier
- **Purpose:** Classify current market regime (Trending Up/Down, Range-Bound, High Volatility, Low Volatility)
- **Implementation:** Lightweight LLM prompt with recent price action summary + technical indicator snapshot
- **Output:** `regime: {type, confidence, description}`
- **Use:** Dynamically adjust strategy parameters (e.g., tighten stops in high volatility, favor trend-following in trending regimes)
- **Config path:** `llm/market_regime.enabled: bool`, `llm/market_regime.model: string`

#### 1.2 News Sentiment Interpreter
- **Purpose:** Replace/Augment current `NewsAgent` (which returns raw sentiment scores) with LLM that extracts narratives, catalysts, and risk factors
- **Implementation:** Feed recent headlines + summaries to LLM; ask for sentiment + key themes + impact assessment
- **Output:** `sentiment_breakdown: {score, narratives: [], catalysts: [], risk_factors: []}`
- **Config:** `llm/news_sentiment.enabled: bool`

#### 1.3 Adaptive Rule Tuner
- **Purpose:** Periodically (weekly) review strategy performance and suggest rule parameter adjustments
- **Implementation:** LLM reviews trade history, winning vs losing patterns, suggests: RSI thresholds, SMA periods, confidence thresholds
- **Output:** `rule_adjustments: [{rule_name, old_value, new_value, rationale}]`
- **Safety:** Changes require manual approval via config version bump
- **Config:** `llm/adaptive_tuning.enabled: bool`, `llm/adaptive_tuning.schedule: cron`

#### 1.4 Anomaly Explanation Engine
- **Purpose:** When unusual signals fire (e.g., RSI < 20 with price > 200-SMA), generate plausible market narratives
- **Implementation:** LLM prompt combining indicator snapshot + recent events
- **Output:** `anomaly_explanation: string` (added to `AgentReport` context)
- **Use:** Enrich Telegram alerts and dashboard displays
- **Config:** `llm/anomaly_explanation.enabled: bool`

### LLM Configuration

```yaml
# config/llm.yaml
llm:
  provider: "openrouter"  # openrouter, openai, anthropic, ollama
  api_key_env: "OPENROUTER_API_KEY"
  base_url: "https://openrouter.ai/api/v1"
  model: "anthropic/claude-3.7-sonnet"  # or "openai/gpt-4.1-mini"
  temperature: 0.3
  max_retries: 3
  timeout: 30

  modules:
    market_regime:
      enabled: false
      model: "anthropic/claude-3.7-sonnet"
      temperature: 0.2
    news_sentiment:
      enabled: false
      model: "openai/gpt-4.1-mini"
      temperature: 0.4
    adaptive_tuning:
      enabled: false
      schedule: "0 6 * * 1"  # Mondays 6 AM
    anomaly_explanation:
      enabled: false
      model: "openai/gpt-4.1-mini"
```

### New Agent: RegimeAgent

- **File:** `finance_service/agents/regime_agent.py`
- **Listens to:** Optional; can be invoked by `StrategyAgent` or `SchedulerAgent`
- **Publishes:** `MARKET_REGIME_UPDATED` event with regime snapshot
- **Integration:** `StrategyAgent` reads latest regime and adjusts rule weights/thresholds

---

## 2. Advanced Backtesting Engine

### Rationale
Current `tools/backtest.py` is standalone. Need integrated, vectorized backtesting with proper walk-forward analysis.

### Architecture

#### 2.1 Backtesting Service Module

- **Package:** `finance_service/backtesting/`
- **Components:**
  - `engine.py` — Vectorized backtest runner using `pandas` + `numpy`
  - `walk_forward.py` — Walk-forward/WFA with expanding/rolling windows
  - `metrics.py` — Performance metrics: Sharpe, Sortino, Calmar, max drawdown, CAGR, Win%, Profit Factor
  - `benchmarks.py` — Benchmark comparison (SPY, QQQ, buy-and-hold)
  - `reporter.py` — PDF/HTML report generator with equity curves, drawdown charts, monthly returns heatmap
  - `slippage.py` — Configurable slippage and commission models

#### 2.2 Strategy Backtest Interface

```python
class BacktestableStrategy(ABC):
    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Return DataFrame with columns: signal (1/-1/0), confidence (0-1), stop_loss, take_profit"""
        pass

class RuleStrategyBacktest(BacktestableStrategy):
    """Wraps RuleStrategy for backtesting with vectorized signal generation"""
```

#### 2.3 CLI Commands

Add to `run_backtest.py`:

```bash
# Single backtest
python3 run_backtest.py --strategy rule_strategy --start 2023-01-01 --end 2024-12-31 --symbols AAPL,MSFT,NVDA

# Walk-forward analysis
python3 run_backtest.py --wfa --window 252*2 --step 63 --symbols SPY

# Optimization (grid search over rule parameters)
python3 run_backtest.py --optimize --param-file config/optimization_grid.yaml
```

#### 2.4 Integration with LearningAgent

- `LearningAgent` stores backtest results in `storage/backtest_results/`
- Automated weekly backtest of current strategy vs previous version
- Alerts on performance degradation (>10% Sharpe drop)

---

## 3. Multi-Symbol Portfolio Optimization

### 3.1 Portfolio-Level Risk Manager

**Current:** `RiskAgent` checks per-position limits but not portfolio-level correlations.

**Add:**

- `PortfolioRisk` class in `finance_service/risk/portfolio_risk.py`
- Computes:
  - Correlation matrix of returns (30-day rolling)
  - Sector exposure tracking (need sector mapping)
  - Portfolio volatility (annualized)
  - VaR (Value-at-Risk) at 95%/99%
  - Expected Shortfall (Conditional VaR)

**New Risk Limits:**

```yaml
risk:
  max_sector_exposure_pct: 30
  max_portfolio_volatility_annual: 30%  # 30% annualized vol limit
  max_correlation_avg: 0.7  # Avoid highly correlated basket
  max_var_95_usd: 10000  # Max daily VaR
```

**Implementation:**

Add method `PortfolioRisk.evaluate()` called by `RiskAgent` before approving trades. Reject if adding position would push sector exposure or portfolio volatility over limits.

### 3.2 Position Sizing Algorithms

**Current:** Fixed quantity from rule output.

**Add:**

```python
# finance_service/risk/position_sizing.py

class PositionSizer(ABC):
    @abstractmethod
    def calculate(self, portfolio_state: Portfolio, signal: Signal, risk_budget: float) -> float:
        pass

class EqualRiskPositionSizer(PositionSizer):
    """Kelly-inspired: risk same dollar amount per trade"""
    def calculate(self, portfolio, signal, risk_budget):
        # risk_budget = max_loss_per_trade (e.g., 1% of portfolio)
        # position_size = risk_budget / (stop_loss_distance * price)
        pass

class VolatilityAdjustedPositionSizer(PositionSizer):
    """Inverse volatility sizing: higher vol -> smaller position"""
    pass

class EqualWeightPositionSizer(PositionSizer):
    """Equal weight across N positions"""
    pass
```

**Config:**

```yaml
strategy:
  position_sizing_method: "equal_risk"  # equal_risk, volatility_adjusted, equal_weight
  risk_per_trade_pct: 1.0  # 1% of portfolio per trade
```

### 3.3 Watchlist Scanning & Concurrent Analysis

Current `MarketScannerAgent` selects 10 symbols daily. Extend to:

- Maintain a `watchlist` of 50-100 symbols across themes
- Daily: scan entire watchlist, rank by composite score, select top 10
- Hourly: refresh watchlist prices (already exists)
- `StrategyAgent` can handle concurrent symbol analysis (already parallel per symbol)
- Add portfolio-level signal aggregation: `signal_aggregation_window` to avoid overtrading

---

## 4. Fundamental Data Integration

### 4.1 FundamentalsAgent

**Purpose:** Fetch and analyze fundamental metrics (PE, PB, revenue growth, EPS, margins, debt ratios).

**Data Source:** OpenBB (already available in requirements). Provider: `openbb.stocks.ca.screener` or `openbb.stocks.fa`.

**Output:** `FundamentalsSnapshot` dataclass:

```python
@dataclass
class FundamentalsSnapshot:
    symbol: str
    timestamp: datetime
    metrics: Dict[str, float]  # pe_ratio, pb_ratio, revenue_growth_yoy, eps_growth, roe, debt_to_equity, etc.
    scores: Dict[str, float]  # value_score, quality_score, growth_score (0-1)
```

**Integration:**

- `DataAgent` optionally fetches fundamentals (costly; cache aggressively)
- `StrategyAgent` incorporates fundamental scores as additional signal weights
- Example rule: `fundamental_value_buy: pe_ratio < 15 and roe > 15`

**Configuration:**

```yaml
data:
  fetch_fundamentals: true
  fundamentals_cache_ttl: 86400  # 24h (fundamentals change slowly)
  fundamental_weights:
    value_score: 0.3
    quality_score: 0.3
    growth_score: 0.2
```

### 4.2 NewsAgent Enhancement

**Current:** `NewsAgent` likely returns basic sentiment (maybe placeholder).

**Upgrade:**

- Use multiple news sources: Yahoo Finance, Benzinga, Seeking Alpha (via OpenBB)
- LLM-based sentiment extraction (see Section 1.2)
- Identify catalysts: earnings, FDA approvals, M&A, guidance changes
- Store in database for learning

---

## 5. Options & Derivatives Support

### 5.1 OptionsDataAgent

- **Fetches:** Options chains for symbols in portfolio/watchlist
- **Computes:** Implied volatility (IV), IV rank (percentile vs 1-year), open interest, put/call ratio
- **Provider:** OpenBB options module (`openbb.stocks.options`)

**Output:** `OptionsSnapshot`

```python
@dataclass
class OptionsSnapshot:
    symbol: str
    expiration: str
    strikes: List[float]
    call_iv: float
    put_iv: float
    iv_rank: float  # 0-1
    put_call_ratio: float
    max_oi_strike: float  # strike with highest open interest
```

### 5.2 OptionsStrategyAgent

- **Strategies:**
  - Covered call (if holding underlying, sell OTM call)
  - Cash-secured put (sell OTM put to acquire at discount)
  -irectional call/put buys based on high conviction signals
  - Spreads (vertical spreads for defined risk)

- **Risk:** Greeks (Delta, Gamma, Theta, Vega) exposure in `RiskAgent`

### 5.3 Portfolio Model Extension

Add option positions to `Position` model:

```python
@dataclass
class Position:
    symbol: str
    quantity: float
    avg_cost: float
    current_price: float
    # New for options:
    option_type: Optional[str] = None  # "CALL" or "PUT"
    strike: Optional[float] = None
    expiration: Optional[str] = None
    greeks: Optional[Dict[str, float]] = None  # delta, gamma, theta, vega
```

---

## 6. Machine Learning Pipeline

### 6.1 Feature Store

- Store all signals (technical, fundamental, news sentiment, regime, options) per symbol per day
- Table: `feature_store` with columns: `date, symbol, feature_name, feature_value`
- Used for training and for online inference (if adding ML later)

### 6.2 LearningAgent Enhancements

**Current:** Likely basic trade outcome analysis.

**Upgrade:**

- **Labeling:** Define outcome labels: `successful_trade` (hit take-profit before stop-loss), `losing_trade`, `breakeven`
- **Feature Collection:** Gather all features active at trade entry
- **Model:** LightGBM or XGBoost classifier (train weekly)
- **Feature Importance:** SHAP values to understand what drives success
- **Online Learning:** Update model incrementally as new trades complete

**Output:** `learning_report` with:
- Feature importance chart
- Win rate by feature bucket (e.g., "RSI < 30" win rate = 65%)
- Recommendations: adjust rule thresholds based on ML insights

### 6.3 Auto-Optimization (Optional)

Use Optuna to optimize rule parameters:

```python
def objective(trial):
    params = {
        "rsi_oversold": trial.suggest_int(20, 35),
        "sma_fast": trial.suggest_categorical([10, 20, 30]),
        "confidence_threshold": trial.suggest_float(0.7, 0.95),
    }
    results = run_backtest(symbols, strategy_params=params)
    return results.sharpe_ratio  # maximize

study = optuna.create_study(direction="maximize")
study.optimize(objective, n_trials=100)
```

**Caution:** Overfitting risk. Use walk-forward validation.

---

## 7. Real Broker Integration

### 7.1 Abstract Broker Interface

```python
# finance_service/brokers/broker_interface.py

class BrokerInterface(ABC):
    @abstractmethod
    def submit_order(self, order: Order) -> OrderResult:
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        pass

    @abstractmethod
    def get_positions(self) -> List[Position]:
        pass

    @abstractmethod
    def get_account(self) -> Account:
        pass
```

### 7.2 Implementations

- **PaperBroker** (current): Updates portfolio in-memory/SQLite
- **AlpacaBroker:** REST API + WebSocket (US markets)
- **TigerBrokersBroker:** For HK/US (already user's interest)
- **InteractiveBrokersBroker:** For advanced users

### 7.3 ExecutionAgent Enhancement

- Config: `execution.broker: "paper" | "alpaca" | "tiger"`
- `ExecutionAgent` uses factory to get broker instance
- Sandbox mode: broker uses paper trading endpoints
- Order state tracking: PENDING → SUBMITTED → PARTIAL → FILLED/CANCELLED

---

## 8. Configuration Management Overhaul

### 8.1 Single Source of Truth

Current: `.env`, YAML files, Pydantic settings scattered.

**Goal:** One `config/config.yaml` for all non-secret configs; `.env` only for API keys.

**Structure:**

```yaml
# config/config.yaml
app:
  name: "AITradeAgent"
  log_level: "INFO"
  environment: "production"

finance:
  service:
    port: 8801
    host: "0.0.0.0"
  data:
    default_lookback_days: 365
    cache_ttl_seconds: 3600
    provider: "yfinance"  # yfinance, openbb, alpha_vantage
    fetch_fundamentals: true
  portfolio:
    initial_cash: 100000.0
    currency: "USD"
    trade_slippage: 0.0005  # 5 bps
  strategy:
    type: "rule_based"
    rule_file: "config/rules.yaml"
    position_sizing_method: "equal_risk"
    risk_per_trade_pct: 1.0
    auto_execute:
      enabled: true
      confidence_threshold: 0.8
  risk:
    policy:
      max_position_size_pct: 10
      max_exposure_pct: 50
      max_daily_loss_pct: 3
      max_drawdown_pct: 15
      default_risk_budget_pct: 1.0
      stop_loss_default_pct: 5
      take_profit_default_pct: 10
      max_concurrent_positions: 10
      min_position_size_usd: 1000
      allow_short_selling: false
      margin_enabled: false
  execution:
    broker: "paper"  # paper, alpaca, tiger
    broker_config: {}
  scheduling:
    market_scan_interval_minutes: 15
    price_refresh_interval_minutes: 15
    exit_check_interval_minutes: 5
    health_check_interval_hours: 4
  notifications:
    telegram:
      enabled: true
      bot_token_env: "TELEGRAM_BOT_TOKEN"
      chat_id: "YOUR_CHAT_ID"
      message_thread_id: null
    slack:
      enabled: false
      webhook_url: ""
  llm:
    provider: "openrouter"
    api_key_env: "OPENROUTER_API_KEY"
    base_url: "https://openrouter.ai/api/v1"
    model: "anthropic/claude-3.7-sonnet"
    temperature: 0.3
    modules:
      market_regime:
        enabled: false
      news_sentiment:
        enabled: false
      adaptive_tuning:
        enabled: false
      anomaly_explanation:
        enabled: false
```

**Pydantic Settings:** Update `finance_service/core/pydantic_config.py` to load entire YAML + `.env` for secrets.

### 8.2 Hot Reload

Watch `config/` directory; on change, reload config without restart (except for agent-specific inits).

---

## 9. Testing Gaps

### 9.1 Missing Test Coverage

- ✅ End-to-end pipeline test (scan → data → analysis → strategy → risk → execution → portfolio)
- ✅ Market data mocking with deterministic fixture
- ✅ RiskAgent edge cases (pre-existing position correlation, simultaneous signals)
- ✅ Backtesting engine validation (known strategy should match manual calculation)
- ✅ LLM module mocking (test prompts without calling API)

### 9.2 Performance Testing

- Load test: 100 symbols concurrently
- Latency per agent measurement
- Memory leak detection (long-running service)

Add to `tests/load/` directory.

---

## 10. Observability

### 10.1 Metrics (Prometheus)

Expose `/metrics` endpoint:

```python
# finance_service/monitoring/metrics.py

TRADE_COUNT = Counter('trades_total', 'Total trades', ['symbol', 'side'])
PORTFOLIO_VALUE = Gauge('portfolio_value_usd', 'Current portfolio value')
PNL = Gauge('portfolio_pnl_usd', 'Unrealized P&L')
AGENT_LATENCY = Histogram('agent_latency_seconds', 'Agent execution time', ['agent_id'])
RISK_LIMIT_UTILIZATION = Gauge('risk_limit_pct', 'Risk limit utilization', ['limit_type'])
```

Register in `app.py` and have agents record metrics.

### 10.2 Structured Logging

Switch to `structlog` or `logging` with JSON formatter for ELK stack.

### 10.3 Health Checks

Split `/health` into:
- `/health/live` (liveness: is process running?)
- `/health/ready` (readiness: all agents initialized?)
- `/health/detail` (full agent status, last activity timestamps)

---

## 11. Deployment & Reliability

### 11.1 Docker Enhancements

Add multi-stage build to reduce image size:

```dockerfile
# Builder stage
FROM python:3.13-slim as builder
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.13-slim
COPY --from=builder /root/.local /root/.local
COPY . /app
ENV PATH=/root/.local/bin:$PATH
CMD ["python", "run_finance_service.py"]
```

### 11.2 Kubernetes Manifests

- `k8s/deployment.yaml` (with HPA based on CPU/memory)
- `k8s/service.yaml` (ClusterIP for internal, LoadBalancer for external)
- `k8s/ingress.yaml` (nginx)
- `k8s/configmap.yaml` (config.yaml)
- `k8s/secret.yaml` (API keys)
- `k8s/pvc.yaml` (storage for SQLite)

### 11.3 Database Migration

Switch from raw SQLite to Alembic for schema migrations (if adding new tables like backtest_results, feature_store).

---

## Implementation Phases

### Phase 1: Foundation (Week 1)
1. LLM configuration module with provider abstraction
2. RegimeAgent prototype (simple prompt + caching)
3. Config management overhaul (single YAML + hot reload)
4. Unit tests for LLM abstraction (mock provider)

### Phase 2: Backtesting (Week 2)
1. Backtesting engine with vectorized signal application
2. Metrics module
3. Report generator (equity curve, drawdown chart)
4. Walk-forward analysis
5. Integration tests

### Phase 3: Portfolio Optimization (Week 3)
1. PortfolioRisk class (correlation, sector exposure)
2. Position sizers (EqualRisk, VolatilityAdjusted)
3. Update RiskAgent to call portfolio risk evaluator
4. Update StrategyAgent to use position sizer
5. Tests

### Phase 4: Fundamentals & News (Week 4)
1. FundamentalsAgent (OpenBB integration)
2. NewsAgent upgrade (LLM sentiment breakdown)
3. StrategyAgent rule expansion (fundamental filters)
4. Cache fundamentals aggressively (24h TTL)
5. Tests

### Phase 5: Options (Week 5)
1. OptionsDataAgent (OpenBB options)
2. OptionsStrategyAgent (covered calls, CSP)
3. Portfolio model extension
4. Greeks calculation (Delta-based position sizing)
5. Tests

### Phase 6: ML & Learning (Week 6)
1. Feature store schema + writer
2. LearningAgent upgrade (LightGBM training)
3. SHAP explanations
4. Weekly auto-training pipeline
5. Backtest integration: "How would ML model have performed?"

### Phase 7: Broker & Deployment (Week 7)
1. BrokerInterface + PaperBroker refactor
2. AlpacaBroker implementation (REST API)
3. TigerBrokersBroker stub (for user)
4. Docker multi-stage build
5. K8s manifests

### Phase 8: Observability & Polish (Week 8)
1. Prometheus metrics
2. JSON structured logging
3. Health check splitting
4. Performance tests
5. Documentation updates

---

## Success Metrics

- **Backtesting:** In-sample and out-of-sample Sharpe > 1.5 for rule strategies
- **LLM Modules:** Market regime classifier accuracy > 70% (vs manual labeling)
- **Portfolio Risk:** Max drawdown reduced by 20% via correlation limits
- **Fundamentals:** 10% of top signals have fundamental confirmation
- **Operations:** 99.9% uptime, < 30s end-to-end signal latency
- **Testing:** > 80% code coverage across new modules

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM cost escalation | High | Use cached prompts, rate limit, default disabled |
| Overfitting from optimization | High | Walk-forward validation, out-of-sample testing |
| Broker API rate limits | Medium | Exponential backoff, batch orders |
| Data quality issues (yfinance gaps) | Medium | Validate OHLCV, fill missing with OpenBB fallback |
| Options complexity (Greeks) | Medium | Start with simple covered calls only |
| Configuration drift | Low | Single YAML source + version pinning |

---

## Appendix: File Additions Summary

### New Files
```
finance_service/
├── agents/
│   ├── regime_agent.py
│   ├── fundamentals_agent.py
│   ├── options_agent.py
│   └── options_strategy_agent.py
├── backtesting/
│   ├── __init__.py
│   ├── engine.py
│   ├── walk_forward.py
│   ├── metrics.py
│   ├── benchmarks.py
│   ├── reporter.py
│   └── slippage/
├── brokers/
│   ├── __init__.py
│   ├── broker_interface.py
│   ├── paper_broker.py
│   ├── alpaca_broker.py
│   └── tiger_broker.py
├── risk/
│   ├── portfolio_risk.py
│   └── position_sizing.py
├── monitoring/
│   ├── __init__.py
│   ├── metrics.py
│   └── logging_config.py
├── config/
│   ├── config.yaml (new structure)
│   └── rules.yaml (moved from root)
└── storage/
    ├── backtest_results/
    ├── feature_store/
    └── ml_models/
```

### Modified Files
- `app.py` — Add new agent classes, metrics endpoint
- ` agents/strategy_agent.py` — Add regime awareness, LLM modules optional
- ` agents/risk_agent.py` — Add portfolio risk checks
- ` finance_service/core/pydantic_config.py` — Load full YAML
- ` run_finance_service.py` — Hot reload support
- ` requirements.txt` — Add: openbb, optuna, lightgbm, prometheus_client, reportlab, shap

### Documentation Updates
- `docs/CURRENT_ARCHITECTURE.md` — Update agent list, 3-tier details
- `docs/architecture/agent_workflow_and_data_flow.md` — Add new flows
- `docs/BACKTESTING_GUIDE.md` (new)
- `docs/LLM_AUGMENTATION_GUIDE.md` (new)
- `docs/FUNDAMENTALS_INTEGRATION.md` (new)
- `docs/OPTIONS_TRADING.md` (new)
- `docs/MONITORING_AND_ALERTING.md` (new)
- `README.md` — Update feature matrix

---

## Conclusion

This plan elevates AITradeAgent from a **robust rule-based paper trader** to a **hybrid AI-powered trading platform** while preserving its production reliability. Implementation in 8-week sprints ensures each component is tested and documented before moving to the next.
