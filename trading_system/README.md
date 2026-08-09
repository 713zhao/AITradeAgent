# trading_system (v2)

A real, event-driven multi-agent paper-trading system, using the
`AITradeAgent` codebase (root of this repo, branch `main`) as the
architectural baseline. This is a from-scratch, tested implementation,
not a copy of the baseline's code.

## Why a rewrite instead of extending the baseline directly

The baseline (`finance_service/`) has the right shape — an event bus and
specialist agents (scanner, data, analysis, strategy, risk, execution,
portfolio) — but:

- Agent boundaries pass untyped `dict` payloads (`AgentReport.payload: Dict[str, Any]`).
- `StrategyAgent` is one hardcoded rule (`sma20_trend`) with no reasoning trace.
- `RiskAgent`/position sizing was decoupled from live equity in places.
- `EventBus._dispatch_event` retries by recreating and re-awaiting *all*
  handler tasks on a timeout, which can duplicate side effects such as
  order submission if a slow handler is retried after partially succeeding.
- ~150 files including many `.backup` files, duplicate scripts, and
  several overlapping "layer" ML schedulers — hard to use as a clean base.

This implementation keeps the same pipeline shape (it is a legitimate,
proven design) but rebuilds it with typed Pydantic contracts at every
agent boundary, unit + integration tests for every agent, and a safer
event bus.

## Architecture

```
ScannerAgent -> DataAgent -> AnalysisAgent -> StrategyAgent -> RiskAgent -> ExecutionAgent -> PortfolioAgent
```

Run per scan cycle, one symbol at a time (deliberately **sequential**,
not parallel across symbols): `RiskAgent` needs an accurate, up-to-date
view of live equity, open position count, and today's realized P&L to
enforce portfolio-level limits (max positions, daily loss circuit
breaker) correctly, and `PortfolioAgent` is the single writer. Making the
loop concurrent would race those checks. Fetching data and computing
indicators concurrently across symbols would be a safe, straightforward
optimization if scan latency becomes a problem (order tens of symbols);
not needed at current universe sizes.

Agents:

- **ScannerAgent** — selects the candidate universe from config.
- **DataAgent** — fetches OHLCV via a `DataProvider` protocol
  (`YFinanceProvider` by default), with an in-memory TTL cache. Network
  vendor is swappable and mockable.
- **AnalysisAgent** — computes SMA/EMA/RSI/MACD/ATR/Bollinger indicators
  in plain pandas (no C-extension indicator library dependency).
- **StrategyAgent** — the main architecture change from the baseline:
  primary decision-maker is an **LLM** given the full indicator snapshot
  plus current position context, returning a structured JSON decision
  (`action`, `confidence`, `target_weight`, `stop_loss_pct`, `reasoning`).
  Falls back automatically to a deterministic SMA20/50 + RSI + MACD rule
  strategy if no LLM API key is configured, or if the LLM call fails or
  returns something invalid — the pipeline is never blocked on LLM
  availability. Every decision carries a `reasoning` string, so trade
  history is auditable even for the rule fallback.
- **RiskAgent** — approves/rejects/sizes proposals against a policy:
  max weight per position, max concurrent positions, min confidence,
  daily loss circuit breaker, and a post-loss cooldown per symbol.
  Position size is computed from live portfolio equity and the
  strategy's target weight, not a fixed share count.
- **ExecutionAgent** / **PaperBroker** — simulated fills with
  configurable slippage (bps) and commission (bps); a real broker
  adapter (e.g. Alpaca paper trading REST API) can implement the same
  `Broker` protocol later without touching agent logic.
- **PortfolioAgent** / **PortfolioStore** — single writer of cash,
  positions, trade history, and daily equity, persisted to SQLite so
  state survives restarts.

## Running

```bash
uv sync
cp .env.example .env   # optional, only needed for the LLM strategy path

# single scan cycle, ignoring market-hours gate (useful for testing)
uv run python -m trading_system.main --config config.yaml --once --bypass-market-hours

# continuous paper trading loop, respecting US market hours,
# scanning every `scan_interval_minutes` from config.yaml
uv run python -m trading_system.main --config config.yaml --loop
```

Portfolio state persists to `storage/portfolio.sqlite` (path configurable
via `db_path` in `config.yaml`).

### Enabling the LLM strategy agent

In `config.yaml`:

```yaml
llm:
  enabled: true
  provider: openai
  model: gpt-4o-mini
  base_url: null       # set to point at any OpenAI-compatible endpoint
  api_key_env: OPENAI_API_KEY
```

Set the referenced env var (e.g. `OPENAI_API_KEY`) before running. If
unset, or if the LLM call errors, `StrategyAgent` transparently falls
back to the rule-based strategy and logs a warning — the system keeps
trading.

## Tests

```bash
uv run pytest -q
```

27 tests cover every agent in isolation (with fake data providers and a
fake LLM client — no network or API key required) plus full
scanner-to-portfolio integration scenarios (buy on uptrend, hold on flat
market, independent multi-symbol scans, buy-then-sell realized P&L).

## What's real here vs. simulated

- Real technical indicators computed from real OHLCV data (yfinance).
- Real (optional) LLM call for the trading decision, with a real
  auditable reasoning trail.
- Real portfolio accounting (cash, avg cost, realized/unrealized P&L,
  SQLite persistence across restarts).
- Simulated fills only (no live broker order routing yet) — this is
  paper trading by design, per the current task scope. Swapping in a
  real broker means implementing the `Broker` protocol
  (`broker/paper_broker.py`) against a live REST API; nothing else in
  the pipeline needs to change.
