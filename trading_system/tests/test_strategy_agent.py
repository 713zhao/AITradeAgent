import pytest

from trading_system.agents.strategy_agent import StrategyAgent, rule_based_proposal
from trading_system.agents.analysis_agent import compute_indicators
from trading_system.core.models import Action


def test_rule_based_bullish(uptrend_ohlcv):
    ind = compute_indicators(uptrend_ohlcv)
    proposal = rule_based_proposal(ind, has_position=False)
    assert proposal.action == Action.BUY
    assert proposal.target_weight > 0


def test_rule_based_no_position_no_sell(downtrend_ohlcv):
    ind = compute_indicators(downtrend_ohlcv)
    proposal = rule_based_proposal(ind, has_position=False)
    assert proposal.action != Action.SELL


def test_rule_based_sell_when_holding_and_downtrend(downtrend_ohlcv):
    ind = compute_indicators(downtrend_ohlcv)
    proposal = rule_based_proposal(ind, has_position=True)
    assert proposal.action == Action.SELL


class FakeLLM:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    async def complete_json(self, system, user):
        self.calls += 1
        return self.response


class BrokenLLM:
    async def complete_json(self, system, user):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_strategy_agent_uses_llm_when_available(uptrend_ohlcv):
    ind = compute_indicators(uptrend_ohlcv)
    llm = FakeLLM({"action": "BUY", "confidence": 0.9, "target_weight": 0.1, "reasoning": "test"})
    agent = StrategyAgent(llm_client=llm)
    report = agent.run
    result = await agent.run(ind)
    proposal = result.payload["proposal"]
    assert proposal.action == Action.BUY
    assert proposal.proposed_by == "llm_strategy"
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_strategy_agent_falls_back_to_rules_on_llm_error(uptrend_ohlcv):
    ind = compute_indicators(uptrend_ohlcv)
    agent = StrategyAgent(llm_client=BrokenLLM())
    result = await agent.run(ind)
    proposal = result.payload["proposal"]
    assert proposal.proposed_by == "rule_fallback"


@pytest.mark.asyncio
async def test_strategy_agent_no_llm_uses_rules(uptrend_ohlcv):
    ind = compute_indicators(uptrend_ohlcv)
    agent = StrategyAgent(llm_client=None)
    result = await agent.run(ind)
    assert result.payload["proposal"].proposed_by == "rule_fallback"
