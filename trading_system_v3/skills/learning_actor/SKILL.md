# Learning Actor Skill

Isolated agent that reviews resolved trade decisions (handed to it as
sanitized summaries, never a database handle) and distills one short,
generalizable lesson via LLM, or a stats fallback with no LLM configured.
Closes the memory loop back into StrategyActor via the orchestrator.

Implementation: `src/trading_system_v3/actors/learning_actor.py`.

## Purpose

- Turns raw trade history into an actionable, human-readable lesson
  string that StrategyActor sees injected into its future prompts.
- Never talks to StrategyActor directly -- receives a list of
  `ResolvedDecisionSummary` values (symbol, action, confidence, reasoning,
  outcome_pnl) and returns lesson text only; the orchestrator does the
  relaying in both directions.

## Isolation

Private state: a `MemoryStore` at `learning_memory_db_path`
(`storage/learning_actor.sqlite` by default), kept purely as a local
audit trail of lessons this actor has produced -- it is never StrategyActor's
source of truth for lessons (that lives in StrategyActor's own private
`lessons` table, populated via `StrategyAddLessonRequest`). Only public
surface is `ask()`/`start()`/`stop()`.

## Reachable only via `ask(request)`

| Request | Response | When |
|---|---|---|
| `LearningRunRequest` | `LearningRunResponse` | after each scan cycle, if `run_learning_after_each_cycle: true` in config |

## Fallback rule (no LLM / LLM fails)

- Fewer than 3 resolved decisions in the batch: no lesson.
- >= 60% of the batch are losers: "losing streak across {symbols}..." lesson.
- >= 70% of the batch are winners: "current entry filters are working..." lesson.
- Otherwise: no lesson (`lessons: []`, not an error -- the loop is a no-op, not a failure).

## Usage

```python
from trading_system_v3.actors.learning_actor import LearningActor
from trading_system_v3.core.models import LearningRunRequest, StrategyRecentOutcomesRequest, StrategyAddLessonRequest

actor = LearningActor(memory_db_path="storage/learning_actor.sqlite", llm_client=llm_client)
actor.start()

outcomes = await strategy_actor.ask(StrategyRecentOutcomesRequest())
resp = await actor.ask(LearningRunRequest(resolved_decisions=outcomes.decisions))
for lesson in resp.lessons:
    await strategy_actor.ask(StrategyAddLessonRequest(
        text=lesson, source_decision_ids=[d.decision_id for d in outcomes.decisions],
    ))

await actor.stop()
```

This exact three-step relay is what `Orchestrator.run_learning_cycle()`
does; see `src/trading_system_v3/orchestrator.py` and
`tests/test_orchestrator_integration.py::test_full_memory_loop_buy_sell_learn`.

## Future enhancements

- Per-symbol lessons (`scope=symbol`) instead of only global.
- Batch size / review cadence tuning (currently reviews everything new
  since its private watermark on StrategyActor, unbounded batch size).
