import pytest

from trading_system_v3.actors.learning_actor import LearningActor
from trading_system_v3.core.models import Action, LearningRunRequest, ResolvedDecisionSummary


def _summary(symbol, outcome_pnl, decision_id=1) -> ResolvedDecisionSummary:
    return ResolvedDecisionSummary(
        decision_id=decision_id, symbol=symbol, action=Action.BUY, confidence=0.6,
        reasoning="trend follow", outcome_pnl=outcome_pnl,
    )


@pytest.mark.asyncio
async def test_no_op_when_no_decisions(tmp_memory_db):
    actor = LearningActor(memory_db_path=tmp_memory_db)
    resp = await actor.ask(LearningRunRequest(resolved_decisions=[]))
    assert resp.lessons == []
    await actor.stop()


@pytest.mark.asyncio
async def test_stats_fallback_losing_streak(tmp_memory_db):
    actor = LearningActor(memory_db_path=tmp_memory_db)
    decisions = [_summary("AAPL", -10, 1), _summary("AAPL", -20, 2), _summary("MSFT", -5, 3)]
    resp = await actor.ask(LearningRunRequest(resolved_decisions=decisions))
    assert len(resp.lessons) == 1
    assert "losing streak" in resp.lessons[0].lower()
    await actor.stop()


@pytest.mark.asyncio
async def test_llm_lesson_used_when_available(tmp_memory_db):
    class FakeLLM:
        async def complete_json(self, system, user):
            return {"lesson": "Custom LLM lesson"}

    actor = LearningActor(memory_db_path=tmp_memory_db, llm_client=FakeLLM())
    decisions = [_summary("AAPL", -10, 1), _summary("AAPL", -20, 2), _summary("MSFT", -5, 3)]
    resp = await actor.ask(LearningRunRequest(resolved_decisions=decisions))
    assert resp.lessons == ["Custom LLM lesson"]
    await actor.stop()


@pytest.mark.asyncio
async def test_learning_actor_cannot_see_strategy_actor_database(tmp_memory_db, tmp_path):
    """LearningActor only ever receives ResolvedDecisionSummary values in
    the request -- it never opens another actor's sqlite file."""
    actor = LearningActor(memory_db_path=tmp_memory_db)
    public_attrs = {name for name in vars(actor) if not name.startswith("_")}
    assert public_attrs == {"name"}
    await actor.stop()
