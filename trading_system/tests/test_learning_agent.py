import pytest

from trading_system.agents.learning_agent import LearningAgent
from trading_system.memory.store import MemoryStore


class FakeLLM:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    async def complete_json(self, system, user):
        self.calls += 1
        return self.response


def _resolved_decision(memory, symbol, pnl):
    decision_id = memory.log_decision(symbol, "BUY", 0.8, 0.1, "reason", "llm_strategy")
    memory.mark_executed(decision_id)
    memory.backfill_outcome_for_symbol(symbol, pnl)


@pytest.mark.asyncio
async def test_learning_agent_noop_when_nothing_resolved(tmp_path):
    memory = MemoryStore(str(tmp_path / "memory.sqlite"))
    agent = LearningAgent(memory=memory, llm_client=None)
    report = await agent.run()
    assert report.status == "info"
    assert "No newly resolved" in report.message


@pytest.mark.asyncio
async def test_learning_agent_uses_llm_lesson_when_available(tmp_path):
    memory = MemoryStore(str(tmp_path / "memory.sqlite"))
    _resolved_decision(memory, "AAPL", -20.0)
    _resolved_decision(memory, "MSFT", -15.0)
    _resolved_decision(memory, "NVDA", -30.0)

    llm = FakeLLM({"lesson": "Recent BUY signals underperformed; tighten entry filters."})
    agent = LearningAgent(memory=memory, llm_client=llm)
    report = await agent.run()

    assert report.status == "success"
    assert llm.calls == 1
    assert memory.recent_lessons("global", limit=1)[0] == "Recent BUY signals underperformed; tighten entry filters."


@pytest.mark.asyncio
async def test_learning_agent_stats_fallback_on_losing_streak(tmp_path):
    memory = MemoryStore(str(tmp_path / "memory.sqlite"))
    _resolved_decision(memory, "AAPL", -20.0)
    _resolved_decision(memory, "MSFT", -15.0)
    _resolved_decision(memory, "NVDA", -30.0)

    agent = LearningAgent(memory=memory, llm_client=None)
    report = await agent.run()

    assert report.status == "success"
    lessons = memory.recent_lessons("global", limit=1)
    assert "losing streak" in lessons[0]


@pytest.mark.asyncio
async def test_learning_agent_does_not_reprocess_same_decisions(tmp_path):
    memory = MemoryStore(str(tmp_path / "memory.sqlite"))
    _resolved_decision(memory, "AAPL", -20.0)
    _resolved_decision(memory, "MSFT", -15.0)
    _resolved_decision(memory, "NVDA", -30.0)

    agent = LearningAgent(memory=memory, llm_client=None)
    await agent.run()
    report2 = await agent.run()
    assert report2.status == "info"
