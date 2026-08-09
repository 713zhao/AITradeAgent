"""Full memory-loop integration: strategy proposal is logged, execution
marks it executed, a subsequent SELL backfills the realized outcome, and
LearningAgent turns resolved decisions into a lesson that shows up in
StrategyAgent's next prompt via MemoryStore."""
from __future__ import annotations

import pytest

from tests.conftest import make_ohlcv, _random_walk
from trading_system.agents.analysis_agent import AnalysisAgent
from trading_system.agents.data_agent import DataAgent
from trading_system.agents.execution_agent import ExecutionAgent
from trading_system.agents.learning_agent import LearningAgent
from trading_system.agents.portfolio_agent import PortfolioAgent, PortfolioStore
from trading_system.agents.risk_agent import RiskAgent, RiskPolicy
from trading_system.agents.scanner_agent import ScannerAgent
from trading_system.agents.strategy_agent import StrategyAgent
from trading_system.broker.paper_broker import PaperBroker
from trading_system.memory.store import MemoryStore
from trading_system.orchestrator import Orchestrator


class SwitchableProvider:
    def __init__(self, series):
        self.series = series

    def fetch(self, symbol, lookback_days, interval):
        return make_ohlcv(symbol, self.series)


class FakeLLM:
    """Always proposes BUY on the way up and mirrors rule logic otherwise;
    used to exercise the llm_strategy code path with memory logging."""

    def __init__(self):
        self.calls = 0
        self.last_user_prompt = None

    async def complete_json(self, system, user):
        self.calls += 1
        self.last_user_prompt = user
        if "Current position: none" in user:
            return {"action": "BUY", "confidence": 0.9, "target_weight": 0.1, "reasoning": "uptrend"}
        return {"action": "SELL", "confidence": 0.9, "target_weight": 0.0, "reasoning": "breakdown"}


def _build(tmp_path, provider, llm=None):
    memory = MemoryStore(str(tmp_path / "memory.sqlite"))
    scanner = ScannerAgent(["REV"])
    data_agent = DataAgent(provider, ttl_seconds=0)
    analysis_agent = AnalysisAgent()
    strategy_agent = StrategyAgent(llm_client=llm, memory=memory)
    risk_agent = RiskAgent(RiskPolicy(min_confidence=0.5), memory=memory)
    broker = PaperBroker(slippage_bps=0.0, commission_bps=0.0)
    execution_agent = ExecutionAgent(broker)
    store = PortfolioStore(str(tmp_path / "portfolio.sqlite"), starting_cash=100_000.0)
    portfolio_agent = PortfolioAgent(store)
    learning_agent = LearningAgent(memory=memory, llm_client=llm, batch_size=10)
    orchestrator = Orchestrator(
        scanner, data_agent, analysis_agent, strategy_agent, risk_agent, execution_agent,
        portfolio_agent, memory=memory, learning=learning_agent,
    )
    return orchestrator, memory, store


@pytest.mark.asyncio
async def test_buy_sell_backfills_outcome_in_memory(tmp_path):
    up_series = _random_walk(seed=42, drift_low=-1.0, drift_high=1.6)
    down_series = up_series + [up_series[-1] - i * 2.0 for i in range(1, 25)]
    provider = SwitchableProvider(up_series)
    orchestrator, memory, store = _build(tmp_path, provider)

    await orchestrator.run_scan_cycle()
    decisions = memory.recent_decisions("REV", limit=1)
    assert decisions[0].action == "BUY"
    assert decisions[0].outcome_pnl is None  # not resolved yet

    provider.series = down_series
    await orchestrator.run_scan_cycle()

    decisions_after = memory.recent_decisions("REV", limit=10)
    resolved = [d for d in decisions_after if d.outcome_pnl is not None]
    assert len(resolved) == 1


@pytest.mark.asyncio
async def test_learning_cycle_writes_lesson_that_appears_in_next_strategy_prompt(tmp_path):
    up_series = _random_walk(seed=42, drift_low=-1.0, drift_high=1.6)
    down_series = up_series + [up_series[-1] - i * 2.0 for i in range(1, 25)]
    provider = SwitchableProvider(up_series)
    llm = FakeLLM()
    orchestrator, memory, store = _build(tmp_path, provider, llm=llm)

    await orchestrator.run_scan_cycle()  # BUY, logged
    provider.series = down_series
    await orchestrator.run_scan_cycle()  # SELL, outcome backfilled (likely a loss)

    learning_result = await orchestrator.run_learning_cycle()
    assert learning_result is not None

    # Manually seed a clear losing streak so the stats fallback/LLM has
    # unambiguous signal, then rerun learning and confirm the lesson
    # reaches the next strategy call's prompt.
    for _ in range(3):
        did = memory.log_decision("XYZ", "BUY", 0.7, 0.1, "chase", "llm_strategy")
        memory.mark_executed(did)
        memory.backfill_outcome_for_symbol("XYZ", -10.0)
    await orchestrator.run_learning_cycle()

    lessons = memory.recent_lessons("global", limit=5)
    assert len(lessons) >= 1

    provider.series = up_series
    await orchestrator.run_scan_cycle()
    assert "Recent lessons from trade review" in llm.last_user_prompt
