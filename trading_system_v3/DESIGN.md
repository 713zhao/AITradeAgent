# Design: isolated actor agents

## Problem

The `multi-agent-llm-v2` branch built StrategyAgent/RiskAgent/LearningAgent
as memory-augmented plain Python objects sharing one process: real
persistent state (a `MemoryStore` per concern), but no actual isolation --
any of them could reach into another's fields, and the orchestrator called
their `.run(...)` methods directly like any other function. This branch
goes further: each of those three judgment-making agents is a genuinely
isolated **actor**.

## What "isolated" means here

- **Own memory, unreachable from outside.** Each actor constructs its own
  `MemoryStore` in `__init__`, pointed at its own SQLite file
  (`storage/strategy_actor.sqlite`, `risk_actor.sqlite`,
  `learning_actor.sqlite`). No other actor, and not even the orchestrator,
  ever holds a reference to that store. `tests/test_strategy_actor.py::
  test_episodic_memory_is_private_and_only_reachable_via_messages` and the
  equivalent tests for the other two actors assert the actor's only public
  attributes are `name`/`ask`/`start`/`stop` -- there is no accessor for
  the memory object at all.
- **Only reachable by message.** `actors/base.py::IsolatedActor` exposes
  exactly one call surface: `await actor.ask(request)`. Internally this
  enqueues the request into a private `asyncio.Queue` and awaits a private
  `asyncio.Future`; the actor's own `asyncio.Task` dequeues and processes
  it against its private state. There is no other method to call.
- **Concurrent with the rest of the pipeline.** Because each actor is its
  own `asyncio.Task`, a slow LLM call inside StrategyActor does not block
  DataStage from fetching the next symbol's bars, or RiskActor from
  processing a different request concurrently -- only work *within* one
  actor is serialized against itself.
- **Cross-actor knowledge only travels as explicit messages, relayed by
  the orchestrator.** This is the part that took real design work. Naively,
  "LearningActor writes a lesson for StrategyActor" sounds like it needs a
  shared table. Instead:
  1. Orchestrator asks StrategyActor `StrategyRecentOutcomesRequest` ->
     StrategyActor returns a list of `ResolvedDecisionSummary` (a
     read-only, sanitized view) and advances its own private watermark so
     it won't hand out the same decisions twice.
  2. Orchestrator forwards those summaries in `LearningRunRequest` to
     LearningActor -> LearningActor (LLM or stats fallback) returns lesson
     text in `LearningRunResponse`. LearningActor never opens
     StrategyActor's database.
  3. Orchestrator relays each lesson back via `StrategyAddLessonRequest` ->
     StrategyActor stores it in its own private lessons table, where it
     shows up in the *next* `StrategyRequest`'s prompt context.

  See `core/models.py` for every contract; every one of these is a typed
  Pydantic model, not a dict.

## Why in-process `asyncio` actors, not separate OS processes

Considered and rejected for this scope:

- **Separate OS processes (multiprocessing/subprocess), IPC over pipes or
  a local socket.** Real isolation, and arguably "more real" than
  `asyncio` tasks in one interpreter. Rejected for now because: (a) the
  LLM client wraps an `httpx`/`openai` async client tied to one process's
  event loop -- running one per subprocess is easy, but structured
  request/response serialization across a process boundary adds real
  complexity (pickling, backpressure, restart/supervision) for a
  paper-trading system with three lightweight, IO-bound (network + SQLite)
  agents, not CPU-bound work that needs the extra process for true
  parallelism. (b) `asyncio.Queue` + `asyncio.Future` already gives every
  request/response the same shape a process boundary would need (typed,
  serializable Pydantic models) -- promoting this to real process/subprocess
  isolation later is a drop-in replacement of `IsolatedActor`'s transport
  (queue -> pipe/socket) with **zero changes to any call site**, since
  every caller already only ever does `await actor.ask(request)`.
- **A full external message broker (Redis/RabbitMQ/etc).** Overkill for
  three in-process actors in a single paper-trading daemon; adds an
  operational dependency for no isolation benefit at this scale.

The chosen design is the smallest change that makes the isolation claim
literally true and enforceable by tests (no shared references, no direct
method calls, all cross-actor knowledge via explicit typed messages)
while keeping the system a single deployable process, matching the
existing `PortfolioStage`/`RiskActor` "single consistent view of equity"
requirement described in the orchestrator docstring.

## Message contracts (see `core/models.py` for full definitions)

| Actor | Request(s) | Response(s) |
|---|---|---|
| StrategyActor | `StrategyRequest`, `StrategyOutcomeNotification`, `StrategyRecentOutcomesRequest`, `StrategyAddLessonRequest`, `StrategyMarkExecutedRequest` | `StrategyResponse`, `StrategyRecentOutcomesResponse`, `StrategyAddLessonResponse`, `StrategyMarkExecutedResponse` |
| RiskActor | `RiskRequest`, `RiskOutcomeNotification` | `RiskResponse` |
| LearningActor | `LearningRunRequest` | `LearningRunResponse` |

## What stays mechanical / non-isolated

`ScannerStage`, `DataStage`, `AnalysisStage` (a pure function,
`compute_indicators`), `ExecutionStage`, and `PortfolioStage` are plain
async classes/functions called directly by the orchestrator, same as the
prior branch. They hold no judgment/opinion and (aside from DataStage's
TTL cache, a performance optimization) no state worth isolating --
`PortfolioStage` in particular must remain the single writer of
cash/positions so `RiskActor` can be told a single consistent
`equity`/`open_position_count` on every request; making it an isolated
actor too would just add message-passing overhead around the one place
that already needs strict consistency.
