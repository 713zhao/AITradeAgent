import pytest

from trading_system.agents.strategy_agent import StrategyAgent
from trading_system.agents.analysis_agent import compute_indicators
from trading_system.memory.store import MemoryStore


class FakeLLM:
    def __init__(self, response):
        self.response = response
        self.last_user_prompt = None

    async def complete_json(self, system, user):
        self.last_user_prompt = user
        return self.response


@pytest.mark.asyncio
async def test_strategy_agent_logs_every_proposal_to_memory(tmp_path, uptrend_ohlcv):
    memory = MemoryStore(str(tmp_path / "memory.sqlite"))
    ind = compute_indicators(uptrend_ohlcv)
    agent = StrategyAgent(llm_client=None, memory=memory)

    result = await agent.run(ind)
    decision_id = result.payload["decision_id"]
    assert decision_id is not None

    logged = memory.recent_decisions(ind.symbol, limit=1)
    assert len(logged) == 1
    assert logged[0].id == decision_id


@pytest.mark.asyncio
async def test_strategy_agent_injects_memory_context_into_llm_prompt(tmp_path, uptrend_ohlcv):
    memory = MemoryStore(str(tmp_path / "memory.sqlite"))
    memory.add_lesson("Avoid buying into RSI > 75", scope="global")
    ind = compute_indicators(uptrend_ohlcv)
    llm = FakeLLM({"action": "BUY", "confidence": 0.7, "target_weight": 0.1, "reasoning": "ok"})
    agent = StrategyAgent(llm_client=llm, memory=memory)

    await agent.run(ind)

    assert "Avoid buying into RSI > 75" in llm.last_user_prompt
    assert "Memory" in llm.last_user_prompt


@pytest.mark.asyncio
async def test_strategy_agent_without_memory_still_works(uptrend_ohlcv):
    ind = compute_indicators(uptrend_ohlcv)
    agent = StrategyAgent(llm_client=None, memory=None)
    result = await agent.run(ind)
    assert result.payload["decision_id"] is None


@pytest.mark.asyncio
async def test_strategy_agent_memory_reflects_past_outcomes(tmp_path, uptrend_ohlcv):
    memory = MemoryStore(str(tmp_path / "memory.sqlite"))
    ind = compute_indicators(uptrend_ohlcv)
    decision_id = memory.log_decision(ind.symbol, "BUY", 0.7, 0.1, "prior trade", "llm_strategy")
    memory.mark_executed(decision_id)
    memory.backfill_outcome_for_symbol(ind.symbol, -50.0)

    llm = FakeLLM({"action": "HOLD", "confidence": 0.5, "target_weight": 0.0, "reasoning": "ok"})
    agent = StrategyAgent(llm_client=llm, memory=memory)
    await agent.run(ind)

    assert "0/1 profitable" in llm.last_user_prompt
