import pytest

from trading_system.agents.risk_agent import RiskAgent, RiskPolicy
from trading_system.core.models import Action, TradeProposal
from trading_system.memory.store import MemoryStore


@pytest.mark.asyncio
async def test_cooldown_persists_across_agent_instances(tmp_path):
    db_path = str(tmp_path / "memory.sqlite")
    memory1 = MemoryStore(db_path)
    agent1 = RiskAgent(RiskPolicy(min_confidence=0.5), memory=memory1)
    agent1.register_loss("AAPL")

    memory2 = MemoryStore(db_path)
    agent2 = RiskAgent(RiskPolicy(min_confidence=0.5), memory=memory2)  # simulates a fresh process
    proposal = TradeProposal(symbol="AAPL", action=Action.BUY, confidence=0.9, target_weight=0.1)
    report = await agent2.run(
        proposal, equity=100_000, current_position=None, open_position_count=0,
        realized_pnl_today=0, starting_equity_today=100_000, price=200.0,
    )
    assert report.payload["decision"].approved is False
    assert "cooldown" in report.payload["decision"].reason


@pytest.mark.asyncio
async def test_circuit_breaker_logs_risk_event(tmp_path):
    memory = MemoryStore(str(tmp_path / "memory.sqlite"))
    agent = RiskAgent(RiskPolicy(max_daily_loss_pct=0.02), memory=memory)
    proposal = TradeProposal(symbol="AAPL", action=Action.BUY, confidence=0.9, target_weight=0.1)
    await agent.run(
        proposal, equity=97_000, current_position=None, open_position_count=0,
        realized_pnl_today=-3000, starting_equity_today=100_000, price=200.0,
    )
    row = memory._conn.execute(
        "SELECT event_type FROM risk_events WHERE symbol = ?", ("AAPL",)
    ).fetchone()
    assert row is not None
    assert row[0] == "circuit_breaker"
