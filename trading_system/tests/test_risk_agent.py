import pytest

from trading_system.agents.risk_agent import RiskAgent, RiskPolicy
from trading_system.core.models import Action, Position, TradeProposal


@pytest.mark.asyncio
async def test_buy_approved_and_sized_by_target_weight():
    agent = RiskAgent(RiskPolicy(min_confidence=0.5, max_position_weight=0.2))
    proposal = TradeProposal(symbol="AAPL", action=Action.BUY, confidence=0.8, target_weight=0.1)
    report = await agent.run(
        proposal, equity=100_000, current_position=None, open_position_count=0,
        realized_pnl_today=0, starting_equity_today=100_000, price=200.0,
    )
    decision = report.payload["decision"]
    assert decision.approved
    assert decision.quantity == pytest.approx(100_000 * 0.1 / 200.0)


@pytest.mark.asyncio
async def test_buy_rejected_below_confidence():
    agent = RiskAgent(RiskPolicy(min_confidence=0.7))
    proposal = TradeProposal(symbol="AAPL", action=Action.BUY, confidence=0.5, target_weight=0.1)
    report = await agent.run(
        proposal, equity=100_000, current_position=None, open_position_count=0,
        realized_pnl_today=0, starting_equity_today=100_000, price=200.0,
    )
    assert report.payload["decision"].approved is False


@pytest.mark.asyncio
async def test_buy_rejected_when_already_holding():
    agent = RiskAgent(RiskPolicy(min_confidence=0.5))
    proposal = TradeProposal(symbol="AAPL", action=Action.BUY, confidence=0.9, target_weight=0.1)
    pos = Position(symbol="AAPL", quantity=10, avg_price=180.0)
    report = await agent.run(
        proposal, equity=100_000, current_position=pos, open_position_count=1,
        realized_pnl_today=0, starting_equity_today=100_000, price=200.0,
    )
    assert report.payload["decision"].approved is False


@pytest.mark.asyncio
async def test_daily_loss_circuit_breaker():
    agent = RiskAgent(RiskPolicy(max_daily_loss_pct=0.02))
    proposal = TradeProposal(symbol="AAPL", action=Action.BUY, confidence=0.9, target_weight=0.1)
    report = await agent.run(
        proposal, equity=97_000, current_position=None, open_position_count=0,
        realized_pnl_today=-3000, starting_equity_today=100_000, price=200.0,
    )
    decision = report.payload["decision"]
    assert decision.approved is False
    assert "circuit breaker" in decision.reason


@pytest.mark.asyncio
async def test_sell_approved_uses_full_position_quantity():
    agent = RiskAgent(RiskPolicy())
    proposal = TradeProposal(symbol="AAPL", action=Action.SELL, confidence=0.9)
    pos = Position(symbol="AAPL", quantity=15, avg_price=180.0)
    report = await agent.run(
        proposal, equity=100_000, current_position=pos, open_position_count=1,
        realized_pnl_today=0, starting_equity_today=100_000, price=200.0,
    )
    decision = report.payload["decision"]
    assert decision.approved
    assert decision.quantity == 15


@pytest.mark.asyncio
async def test_cooldown_blocks_rebuy_after_loss():
    agent = RiskAgent(RiskPolicy(min_confidence=0.5))
    agent.register_loss("AAPL")
    proposal = TradeProposal(symbol="AAPL", action=Action.BUY, confidence=0.9, target_weight=0.1)
    report = await agent.run(
        proposal, equity=100_000, current_position=None, open_position_count=0,
        realized_pnl_today=0, starting_equity_today=100_000, price=200.0,
    )
    assert report.payload["decision"].approved is False
