"""LearningAgent: closes the memory loop.

Periodically reviews decisions whose outcome has just been resolved
(outcome_pnl backfilled by the orchestrator after a position closes) and
asks an LLM to distill a short, generalizable lesson. Lessons are stored
in MemoryStore and injected into StrategyAgent's future prompts, giving
the system genuine cross-cycle learning instead of stateless one-shot
decisions.

Falls back to a simple statistical summary (no LLM call) when no LLM is
configured, so the loop still produces useful signal without an API key.
"""
from __future__ import annotations

import logging

from trading_system.agents.base import Agent
from trading_system.core.models import AgentReport
from trading_system.llm.client import LLMClient
from trading_system.memory.store import MemoryStore

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a trading strategy reviewer. You are given a list of recently closed trade decisions (symbol, action, confidence, reasoning, realized P&L). Identify ONE short, generalizable lesson (max 30 words) that would help avoid repeating a loss or reinforce a winning pattern. Return ONLY a JSON object: {"lesson": "..."}. If the sample is too small or mixed to support any conclusion, return {"lesson": null}."""


def _format_decisions(decisions) -> str:
    lines = []
    for d in decisions:
        lines.append(
            f"- {d.symbol} {d.action} conf={d.confidence:.2f} pnl={d.outcome_pnl:.2f}: {d.reasoning}"
        )
    return "\n".join(lines)


def _stats_fallback_lesson(decisions) -> str | None:
    if len(decisions) < 3:
        return None
    losers = [d for d in decisions if d.outcome_pnl is not None and d.outcome_pnl < 0]
    if len(losers) / len(decisions) >= 0.6:
        symbols = ", ".join(sorted({d.symbol for d in losers}))
        return f"Recent losing streak across {symbols}: {len(losers)}/{len(decisions)} trades lost money; review sizing/entry filters."
    winners = [d for d in decisions if d.outcome_pnl is not None and d.outcome_pnl > 0]
    if len(winners) / len(decisions) >= 0.7:
        return f"Recent win rate strong ({len(winners)}/{len(decisions)}); current entry filters are working, no change needed."
    return None


class LearningAgent(Agent):
    def __init__(self, memory: MemoryStore, llm_client: LLMClient | None = None, batch_size: int = 10) -> None:
        self.memory = memory
        self._llm = llm_client
        self._batch_size = batch_size
        self._last_reviewed_id = 0

    @property
    def agent_id(self) -> str:
        return "learning_agent"

    @property
    def goal(self) -> str:
        return "Review recently closed trades and distill lessons for the strategy agent"

    async def run(self) -> AgentReport:
        decisions = self.memory.unresolved_decisions_since(self._last_reviewed_id, limit=self._batch_size)
        if not decisions:
            return AgentReport(
                agent_id=self.agent_id, status="info", message="No newly resolved decisions to review",
            )
        self._last_reviewed_id = max(d.id for d in decisions)

        lesson_text: str | None = None
        if self._llm is not None:
            try:
                raw = await self._llm.complete_json(SYSTEM_PROMPT, _format_decisions(decisions))
                lesson_text = raw.get("lesson")
            except Exception as exc:
                logger.warning("LearningAgent LLM call failed (%s); using stats fallback", exc)

        if not lesson_text:
            lesson_text = _stats_fallback_lesson(decisions)

        if not lesson_text:
            return AgentReport(
                agent_id=self.agent_id, status="info",
                message=f"Reviewed {len(decisions)} decisions; no actionable lesson yet",
            )

        lesson_id = self.memory.add_lesson(lesson_text, scope="global", source_decision_ids=[d.id for d in decisions])
        return AgentReport(
            agent_id=self.agent_id, status="success",
            message=f"Recorded lesson from {len(decisions)} decisions",
            payload={"lesson_id": lesson_id, "lesson": lesson_text},
        )
