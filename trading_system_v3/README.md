# trading_system_v3

A real, event-driven paper-trading pipeline, rebuilt from `AITradeAgent`'s
`master` baseline (`finance_service/`), with StrategyAgent, RiskAgent, and
LearningAgent as genuinely **isolated actors** -- each with its own
private memory and its own `asyncio.Task`, reachable only through a typed
`ask(request)` message, never a direct method call or shared reference.
See `DESIGN.md` for the full isolation design and why it's `asyncio`
actors rather than separate OS processes.

This supersedes the `multi-agent-llm-v2` branch's `trading_system/`
(memory-augmented, but the three judgment agents were still plain shared
objects in one process). This branch keeps everything that was good about
that design -- typed Pydantic contracts at every boundary, real technical
indicators, real portfolio accounting with SQLite persistence, an
LLM-driven strategy with a deterministic rule fallback, per-symbol
episodic memory + LearningAgent-distilled lessons -- and adds real actor
isolation on top.

## Architecture

```
ScannerStage -> DataStage -> compute_indicators -> [StrategyActor.ask] -> [RiskActor.ask] -> ExecutionStage -> PortfolioStage
                                                          |                                                          |
                                                          `-------------------- Orchestrator relays -----------------'
                                                                  (outcome notifications, resolved-decision summaries,
                                                                   lessons -- see DESIGN.md)
```

Symbols are processed sequentially within one scan cycle (not
concurrently) -- `RiskActor` needs an accurate, up-to-date view of live
equity/open-position-count/today's P&L on every request, and
`PortfolioStage` is the single writer; making the loop concurrent would
race those reads. StrategyActor/RiskActor/LearningActor calls themselves
run concurrently with the rest of the system as their own `asyncio.Task`s
-- a slow LLM call in one does not block anything else.

- **ScannerStage** -- config-driven candidate universe.
- **DataStage** -- fetches OHLCV via a `DataProvider` protocol
  (`YFinanceProvider` by default), with an in-memory TTL cache.
- **`compute_indicators`** -- SMA/EMA/RSI/MACD/ATR in plain pandas.
- **StrategyActor** (isolated) -- LLM-driven trade proposal (structured
  JSON: action/confidence/target_weight/stop_loss/reasoning), falling
  back automatically to a deterministic SMA20/50 + RSI + MACD rule
  strategy if no LLM is configured or the call fails/returns something
  invalid. Owns private episodic memory (its own decision history +
  outcomes per symbol) and semantic memory (lessons relayed from
  LearningActor) in `storage/strategy_actor.sqlite`.
- **RiskActor** (isolated) -- approves/sizes/rejects proposals: max
  weight per position, max concurrent positions, min confidence, daily
  loss circuit breaker, post-loss cooldown per symbol. Sizing is computed
  from live equity and the strategy's target weight. Owns private durable
  cooldown/circuit-breaker state in `storage/risk_actor.sqlite`.
- **ExecutionStage** / **PaperBroker** -- simulated fills with
  configurable slippage/commission bps.
- **PortfolioStage** / **PortfolioStore** -- single writer of cash,
  positions, trade history, daily equity; SQLite-persisted.
- **LearningActor** (isolated) -- reviews decisions handed to it (as
  sanitized summaries relayed by the orchestrator, never StrategyActor's
  database) and distills a short lesson via LLM, or a stats fallback with
  no LLM configured. Never talks to StrategyActor directly.

## Running

```bash
cd trading_system_v3
python3 -m venv .venv
.venv/bin/pip install -e . --group dev

# single scan cycle, ignoring market-hours gate (useful for testing)
.venv/bin/python -m trading_system_v3.main --config config.yaml --once --bypass-market-hours

# continuous paper trading loop, respecting US market hours
.venv/bin/python -m trading_system_v3.main --config config.yaml --loop
```

Portfolio state persists to `storage/portfolio.sqlite` (`db_path` in
`config.yaml`). Each actor's private memory persists separately:
`storage/strategy_actor.sqlite`, `storage/risk_actor.sqlite`,
`storage/learning_actor.sqlite` (paths configurable in `config.yaml`).

### Enabling the LLM strategy/learning actors

In `config.yaml`:

```yaml
llm:
  enabled: true
  provider: openai
  model: gpt-4o-mini
  base_url: null
  api_key_env: OPENAI_API_KEY
```

Set the referenced env var before running. If unset, or if a call errors,
StrategyActor/LearningActor transparently fall back to their deterministic
paths and log a warning -- the system keeps trading.

## Tests

```bash
cd trading_system_v3
.venv/bin/python -m pytest -q
```

35 tests: actor-isolation contract tests (only `ask()`/`start()`/`stop()`
are public; private state is unreachable; concurrent `ask()` calls don't
interleave a single actor's own state), unit tests for every actor and
pipeline stage with fakes (no network/API key required), and full
orchestrator integration tests -- buy on an uptrend, hold on a flat
market, independent multi-symbol scans, and a full buy -> sell ->
outcome-relay -> learning-cycle -> lesson-visible-in-next-prompt loop that
exercises every actor message contract end to end.

A real smoke run (`--once --bypass-market-hours` against live yfinance
data, no LLM configured) was also run manually to confirm the pipeline
and all three actor SQLite files populate correctly end to end, not just
under mocks.

## What's real here vs. simulated

- Real technical indicators from real OHLCV data (yfinance).
- Real (optional) LLM calls for strategy/learning, with an auditable
  reasoning trail.
- Real portfolio accounting (cash, avg cost, realized/unrealized P&L,
  SQLite persistence across restarts).
- Real actor isolation: private per-actor SQLite memory, message-only
  communication, independently scheduled `asyncio.Task`s -- see
  `DESIGN.md` for what this does and doesn't guarantee vs. OS-process
  isolation.
- Simulated fills only (no live broker order routing) -- paper trading by
  design. Swapping in a real broker means implementing the `Broker`
  protocol (`broker/paper_broker.py`) against a live REST API; nothing
  else in the pipeline needs to change.
