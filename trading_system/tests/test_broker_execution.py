import pytest

from trading_system.broker.paper_broker import PaperBroker
from trading_system.agents.execution_agent import ExecutionAgent
from trading_system.core.models import Action, OrderType, RiskDecision, TradeProposal


def test_paper_broker_applies_slippage_direction():
    broker = PaperBroker(slippage_bps=10.0, commission_bps=0.0)
    buy = broker.submit_order("AAPL", Action.BUY, 10, 100.0, OrderType.MARKET, None)
    sell = broker.submit_order("AAPL", Action.SELL, 10, 100.0, OrderType.MARKET, None)
    assert buy.filled_price > 100.0
    assert sell.filled_price < 100.0


@pytest.mark.asyncio
async def test_execution_agent_rejects_unapproved_decision():
    broker = PaperBroker()
    agent = ExecutionAgent(broker)
    proposal = TradeProposal(symbol="AAPL", action=Action.BUY, confidence=0.9)
    decision = RiskDecision(symbol="AAPL", action=Action.BUY, approved=False, reason="x", original_proposal=proposal)
    report = await agent.run(decision, reference_price=100.0)
    assert report.status == "failure"


@pytest.mark.asyncio
async def test_execution_agent_fills_approved_decision():
    broker = PaperBroker(slippage_bps=0.0, commission_bps=0.0)
    agent = ExecutionAgent(broker)
    proposal = TradeProposal(symbol="AAPL", action=Action.BUY, confidence=0.9)
    decision = RiskDecision(
        symbol="AAPL", action=Action.BUY, approved=True, reason="ok",
        quantity=5, original_proposal=proposal,
    )
    report = await agent.run(decision, reference_price=100.0)
    execution = report.payload["execution"]
    assert execution.status == "filled"
    assert execution.quantity == 5
    assert execution.filled_price == pytest.approx(100.0)
