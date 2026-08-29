# trading_system_v3 skills

Documentation for the reusable, isolated agent components in
`trading_system_v3`, following the same `skills/<name>/SKILL.md`
convention as the rest of this repo (see `../../skills/exit/SKILL.md`
for the original baseline example).

Unlike `../../skills/exit/`, these skills document code that already
lives in `src/trading_system_v3/actors/` rather than duplicating an
implementation under `skills/` -- each SKILL.md is a pointer plus
usage/contract reference, not a second copy of the class.

| Skill | Actor class | Has LLM? | Has private memory? |
|---|---|---|---|
| [`strategy_actor`](strategy_actor/SKILL.md) | `StrategyActor` | yes (rule fallback) | yes -- episodic decisions + semantic lessons |
| [`risk_actor`](risk_actor/SKILL.md) | `RiskActor` | no | yes -- durable cooldowns/circuit-breaker events |
| [`learning_actor`](learning_actor/SKILL.md) | `LearningActor` | yes (stats fallback) | yes -- local audit copy of lessons produced |

All three are isolated actors per `DESIGN.md`: reachable only via
`await actor.ask(request)`, never a direct method call or shared
reference. The mechanical pipeline stages (`ScannerStage`, `DataStage`,
`AnalysisStage`/`compute_indicators`, `ExecutionStage`, `PortfolioStage`)
are not actors and have no skill doc here -- they're plain classes/functions
called directly by `Orchestrator`, documented in the top-level `README.md`.
