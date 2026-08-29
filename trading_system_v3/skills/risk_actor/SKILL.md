# Risk Actor Skill

Isolated agent that approves, resizes, or rejects every trade proposal
against a deterministic risk policy. No LLM. Owns private, durable
cooldown/circuit-breaker state that survives a restart.

Implementation: `src/trading_system_v3/actors/risk_actor.py`.

## Purpose

- Enforces portfolio-level and per-trade risk limits so no other
  component (including StrategyActor) can bypass them.
- Sizes BUYs from *live* equity x target weight, not a fixed share count.
- Single source of truth for "is this symbol in cooldown right now" --
  persisted, not an in-memory dict that resets on restart.

## Isolation

Private state: a `MemoryStore` at `risk_memory_db_path`
(`storage/risk_actor.sqlite` by default) holding cooldown/circuit-breaker
events. Only public surface is `ask()`/`start()`/`stop()`. RiskActor never
reads PortfolioStore or StrategyActor directly -- it is told everything
it needs (equity, open position count, today's realized P&L) as fields on
`RiskRequest` by the orchestrator.

## Reachable only via `ask(request)`

| Request | Response | When |
|---|---|---|
| `RiskRequest` | `RiskResponse` | every scan cycle, per symbol with a non-HOLD proposal |
| `RiskOutcomeNotification` | `RiskResponse` (ack) | after a SELL fills; starts a cooldown if the trade lost money |

## Policy knobs (`RiskPolicy`, from `config.yaml` `risk:`)

- `max_position_weight` -- hard cap on `target_weight` regardless of what the proposal asks for.
- `max_positions` -- max concurrent open positions.
- `min_confidence` -- reject BUY proposals below this confidence.
- `max_daily_loss_pct` -- circuit breaker: rejects all BUYs once today's realized loss crosses this fraction of starting equity.
- `cooldown_minutes_after_loss` -- per-symbol cooldown after a losing SELL.
- `default_stop_loss_pct` -- used when the proposal doesn't specify a `stop_loss_pct`.

## Usage

```python
from trading_system_v3.actors.risk_actor import RiskActor, RiskPolicy
from trading_system_v3.core.models import RiskRequest

actor = RiskActor(memory_db_path="storage/risk_actor.sqlite", policy=RiskPolicy(max_positions=12))
actor.start()

resp = await actor.ask(RiskRequest(
    proposal=proposal, equity=equity, price=price,
    current_position=position_summary, open_position_count=3,
    realized_pnl_today=-120.0, starting_equity_today=100_000.0,
))
if resp.decision.approved:
    ...

await actor.stop()
```

See `tests/test_risk_actor.py`, including
`test_cooldown_persists_across_actor_instances_same_db` for the
restart-survives-cooldown guarantee.

## Future enhancements

- Per-sector/correlation exposure caps (would need the orchestrator to
  pass sector info in `RiskRequest`; still no cross-actor peeking).
- Volatility-scaled position sizing (ATR-based) instead of a flat target weight.
