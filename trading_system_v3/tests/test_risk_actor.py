import pytest

from trading_system_v3.actors.risk_actor import RiskActor, RiskPolicy
from trading_system_v3.core.models import (
    Action,
    OrderType,
    PositionSummary,
    RiskOutcomeNotification,
    RiskRequest,
    TradeProposal,
)


def _proposal(action=Action.BUY, confidence=0.8, target_weight=0.1) -> TradeProposal:
    return TradeProposal(symbol="AAPL", action=action, confidence=confidence, target_weight=target_weight)


@pytest.mark.asyncio
async def test_buy_approved_sizes_from_equity(tmp_memory_db):
    actor = RiskActor(memory_db_path=tmp_memory_db, policy=RiskPolicy(max_position_weight=0.2))
    resp = await actor.ask(RiskRequest(
        proposal=_proposal(target_weight=0.1), equity=100_000, price=100.0,
        current_position=None, open_position_count=0,
        realized_pnl_today=0.0, starting_equity_today=100_000,
    ))
    assert resp.decision.approved
    assert resp.decision.quantity == pytest.approx(100_000 * 0.1 / 100.0, rel=1e-6)
    await actor.stop()


@pytest.mark.asyncio
async def test_buy_rejected_below_min_confidence(tmp_memory_db):
    actor = RiskActor(memory_db_path=tmp_memory_db, policy=RiskPolicy(min_confidence=0.6))
    resp = await actor.ask(RiskRequest(
        proposal=_proposal(confidence=0.3), equity=100_000, price=100.0,
        current_position=None, open_position_count=0,
        realized_pnl_today=0.0, starting_equity_today=100_000,
    ))
    assert not resp.decision.approved


@pytest.mark.asyncio
async def test_daily_loss_circuit_breaker(tmp_memory_db):
    actor = RiskActor(memory_db_path=tmp_memory_db, policy=RiskPolicy(max_daily_loss_pct=0.02))
    resp = await actor.ask(RiskRequest(
        proposal=_proposal(), equity=97_000, price=100.0, current_position=None,
        open_position_count=0, realized_pnl_today=-3_000, starting_equity_today=100_000,
    ))
    assert not resp.decision.approved
    assert "circuit breaker" in resp.decision.reason.lower()


@pytest.mark.asyncio
async def test_sell_approved_when_holding(tmp_memory_db):
    actor = RiskActor(memory_db_path=tmp_memory_db)
    pos = PositionSummary(symbol="AAPL", quantity=10, avg_price=90.0)
    resp = await actor.ask(RiskRequest(
        proposal=_proposal(action=Action.SELL), equity=100_000, price=100.0,
        current_position=pos, open_position_count=1,
        realized_pnl_today=0.0, starting_equity_today=100_000,
    ))
    assert resp.decision.approved
    assert resp.decision.quantity == 10


@pytest.mark.asyncio
async def test_cooldown_persists_across_actor_instances_same_db(tmp_memory_db):
    """Private state survives a process/actor restart because it is
    durable SQLite, not an in-memory dict -- but is still only reachable
    through ask(), matching the isolation contract."""
    actor1 = RiskActor(memory_db_path=tmp_memory_db, policy=RiskPolicy(cooldown_minutes_after_loss=60))
    await actor1.ask(RiskOutcomeNotification(symbol="AAPL", realized_pnl=-500.0))
    await actor1.stop()

    actor2 = RiskActor(memory_db_path=tmp_memory_db)
    resp = await actor2.ask(RiskRequest(
        proposal=_proposal(), equity=100_000, price=100.0, current_position=None,
        open_position_count=0, realized_pnl_today=0.0, starting_equity_today=100_000,
    ))
    assert not resp.decision.approved
    assert "cooldown" in resp.decision.reason.lower()
    await actor2.stop()


@pytest.mark.asyncio
async def test_no_win_no_cooldown(tmp_memory_db):
    actor = RiskActor(memory_db_path=tmp_memory_db)
    await actor.ask(RiskOutcomeNotification(symbol="AAPL", realized_pnl=500.0))
    resp = await actor.ask(RiskRequest(
        proposal=_proposal(), equity=100_000, price=100.0, current_position=None,
        open_position_count=0, realized_pnl_today=0.0, starting_equity_today=100_000,
    ))
    assert resp.decision.approved
    await actor.stop()
