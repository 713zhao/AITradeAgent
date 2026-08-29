# Strategy Actor Skill

Isolated agent that turns one symbol's technical indicators + position
context into a BUY/SELL/HOLD trade proposal, using an LLM with a
deterministic rule-based fallback. Owns private episodic (own decision
history/outcomes) and semantic (lessons from LearningActor) memory.

Implementation: `src/trading_system_v3/actors/strategy_actor.py`.

## Purpose

- Primary judgment-maker in the pipeline: decides *what* to trade.
- Never blocked on LLM availability -- automatically falls back to
  `rule_based_proposal` (SMA20/50 trend + RSI + MACD histogram) if no LLM
  is configured, or a call fails, or returns invalid/unparseable JSON.
- Learns across cycles: injects its own win-rate/recent-decisions for the
  symbol, plus recent global lessons, into every LLM prompt.

## Isolation

Private state: a `MemoryStore` at `strategy_memory_db_path`
(`storage/strategy_actor.sqlite` by default) and an optional LLM client,
both set in `__init__` and never exposed. The only public surface is
`ask()`/`start()`/`stop()` (see `IsolatedActor` in
`src/trading_system_v3/actors/base.py`). No other actor or the
orchestrator ever reads this actor's database directly.

## Reachable only via `ask(request)`

| Request | Response | When |
|---|---|---|
| `StrategyRequest` | `StrategyResponse` | every scan cycle, per symbol |
| `StrategyMarkExecutedRequest` | `StrategyMarkExecutedResponse` | after a BUY fills |
| `StrategyOutcomeNotification` | `StrategyResponse` (ack) | after a SELL fills; backfills realized P&L onto the resolved decision |
| `StrategyRecentOutcomesRequest` | `StrategyRecentOutcomesResponse` | orchestrator pulling newly resolved decisions to feed LearningActor |
| `StrategyAddLessonRequest` | `StrategyAddLessonResponse` | orchestrator relaying a lesson LearningActor wrote |

All request/response types are defined in `src/trading_system_v3/core/models.py`.

## Usage

```python
from trading_system_v3.actors.strategy_actor import StrategyActor
from trading_system_v3.core.models import StrategyRequest

actor = StrategyActor(memory_db_path="storage/strategy_actor.sqlite", llm_client=llm_client)
actor.start()

resp = await actor.ask(StrategyRequest(indicators=indicators, position=position_summary))
proposal, decision_id = resp.proposal, resp.decision_id

await actor.stop()
```

See `tests/test_strategy_actor.py` for fake-LLM unit tests and
`tests/test_orchestrator_integration.py` for the full pipeline usage.

## Configuration (`config.yaml`)

- `strategy_memory_db_path` -- path to this actor's private SQLite file.
- `llm.*` -- shared LLM config (`enabled`, `provider`, `model`, `base_url`,
  `api_key_env`); currently the same client instance is also handed to
  LearningActor (see "LLM setup" notes -- splitting per-actor LLM config
  is a small, unimplemented follow-up).

## Rule fallback (no LLM / LLM fails)

- BUY: `price > sma_20 > sma_50`, `macd_hist > 0`, `rsi_14 < 70` (or unknown).
- SELL (only if currently holding): `price < sma_50` or `rsi_14 > 75`.
- Otherwise: HOLD.

## Future enhancements

- Per-actor LLM override (different/cheaper model than LearningActor).
- Confidence calibration against realized win-rate per symbol.
- Multi-timeframe indicators in the prompt.
