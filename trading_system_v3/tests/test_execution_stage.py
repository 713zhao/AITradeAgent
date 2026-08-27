import pytest

from trading_system_v3.broker.paper_broker import PaperBroker
from trading_system_v3.core.models import Action, OrderType, RiskDecision, TradeProposal
from trading_system_v3.pipeline.execution_stage import ExecutionStage


def test_paper_broker_applies_slippage_direction():
    broker = PaperBroker(slippage_bps=10.0, commission_bps=0.0)
    buy = broker.submit_order("AAPL", Action.BUY, 10, 100.0, OrderType.MARKET, None)
    sell = broker.submit_order("AAPL", Action.SELL, 10, 100.0, OrderType.MARKET, None)
    assert buy.filled_price > 100.0
    assert sell.filled_price < 100.0


@pytest.mark.asyncio
async def test_execution_stage_rejects_unapproved_decision():
    stage = ExecutionStage(PaperBroker())
    proposal = TradeProposal(symbol="AAPL", action=Action.BUY, confidence=0.9)
    decision = RiskDecision(symbol="AAPL", action=Action.BUY, approved=False, reason="x", original_proposal=proposal)
    with pytest.raises(ValueError):
        await stage.execute(decision, reference_price=100.0)


@pytest.mark.asyncio
async def test_execution_stage_fills_approved_decision():
    stage = ExecutionStage(PaperBroker(slippage_bps=0.0, commission_bps=0.0))
    proposal = TradeProposal(symbol="AAPL", action=Action.BUY, confidence=0.9)
    decision = RiskDecision(
        symbol="AAPL", action=Action.BUY, approved=True, reason="ok", quantity=5, original_proposal=proposal,
    )
    execution = await stage.execute(decision, reference_price=100.0)
    assert execution.status == "filled"
    assert execution.quantity == 5
    assert execution.filled_price == pytest.approx(100.0)
