import pytest

from trading_system_v3.actors.strategy_actor import StrategyActor, rule_based_proposal
from trading_system_v3.core.models import (
    Action,
    StrategyAddLessonRequest,
    StrategyMarkExecutedRequest,
    StrategyOutcomeNotification,
    StrategyRecentOutcomesRequest,
    StrategyRequest,
)
from trading_system_v3.pipeline.analysis_stage import compute_indicators


def test_rule_based_bullish(uptrend_ohlcv):
    ind = compute_indicators(uptrend_ohlcv)
    proposal = rule_based_proposal(ind, has_position=False)
    assert proposal.action == Action.BUY
    assert proposal.target_weight > 0


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
async def test_strategy_actor_uses_llm_when_available(uptrend_ohlcv, tmp_memory_db):
    ind = compute_indicators(uptrend_ohlcv)
    llm = FakeLLM({"action": "BUY", "confidence": 0.9, "target_weight": 0.1, "reasoning": "test"})
    actor = StrategyActor(memory_db_path=tmp_memory_db, llm_client=llm)
    resp = await actor.ask(StrategyRequest(indicators=ind, position=None))
    assert resp.proposal.action == Action.BUY
    assert resp.proposal.proposed_by == "llm_strategy"
    assert llm.calls == 1
    assert resp.decision_id > 0
    await actor.stop()


@pytest.mark.asyncio
async def test_strategy_actor_falls_back_to_rules_on_llm_error(uptrend_ohlcv, tmp_memory_db):
    ind = compute_indicators(uptrend_ohlcv)
    actor = StrategyActor(memory_db_path=tmp_memory_db, llm_client=BrokenLLM())
    resp = await actor.ask(StrategyRequest(indicators=ind, position=None))
    assert resp.proposal.proposed_by == "rule_fallback"
    await actor.stop()


@pytest.mark.asyncio
async def test_strategy_actor_no_llm_uses_rules(uptrend_ohlcv, tmp_memory_db):
    ind = compute_indicators(uptrend_ohlcv)
    actor = StrategyActor(memory_db_path=tmp_memory_db, llm_client=None)
    resp = await actor.ask(StrategyRequest(indicators=ind, position=None))
    assert resp.proposal.proposed_by == "rule_fallback"
    await actor.stop()


@pytest.mark.asyncio
async def test_episodic_memory_is_private_and_only_reachable_via_messages(uptrend_ohlcv, tmp_memory_db):
    """The only way to learn about a resolved decision is asking this
    actor -- there is no public attribute exposing the memory store."""
    ind = compute_indicators(uptrend_ohlcv)
    actor = StrategyActor(memory_db_path=tmp_memory_db, llm_client=None)
    public_attrs = {name for name in vars(actor) if not name.startswith("_")}
    assert public_attrs == {"name"}, "memory/llm must stay private, only reachable via ask()"

    resp = await actor.ask(StrategyRequest(indicators=ind, position=None))
    await actor.ask(StrategyMarkExecutedRequest(decision_id=resp.decision_id))
    await actor.ask(StrategyOutcomeNotification(symbol=ind.symbol, realized_pnl=42.0))

    outcomes = await actor.ask(StrategyRecentOutcomesRequest())
    assert len(outcomes.decisions) == 1
    assert outcomes.decisions[0].outcome_pnl == 42.0

    # watermark advances, so asking again returns nothing new
    outcomes_again = await actor.ask(StrategyRecentOutcomesRequest())
    assert outcomes_again.decisions == []
    await actor.stop()


@pytest.mark.asyncio
async def test_lesson_relayed_back_shows_up_in_next_prompt_context(uptrend_ohlcv, tmp_memory_db):
    ind = compute_indicators(uptrend_ohlcv)
    calls = []

    class RecordingLLM:
        async def complete_json(self, system, user):
            calls.append(user)
            return {"action": "HOLD", "confidence": 0.5, "reasoning": "x"}

    actor = StrategyActor(memory_db_path=tmp_memory_db, llm_client=RecordingLLM())
    await actor.ask(StrategyAddLessonRequest(text="Avoid chasing overbought RSI.", source_decision_ids=[]))
    await actor.ask(StrategyRequest(indicators=ind, position=None))
    assert "Avoid chasing overbought RSI." in calls[-1]
    await actor.stop()
