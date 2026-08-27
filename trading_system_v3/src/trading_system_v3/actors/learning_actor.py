"""LearningActor: reviews resolved decisions handed to it (as sanitized
``ResolvedDecisionSummary`` values, never a database handle) and distills
a lesson via LLM, or a stats fallback. It has no reference to
StrategyActor; the orchestrator relays the lesson text back via a
``StrategyAddLessonRequest``."""
from __future__ import annotations

import logging

from trading_system_v3.actors.base import IsolatedActor
from trading_system_v3.core.models import LearningRunRequest, LearningRunResponse, ResolvedDecisionSummary
from trading_system_v3.llm.client import LLMClient
from trading_system_v3.memory.store import MemoryStore

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a trading strategy reviewer. You are given a list of recently closed trade decisions (symbol, action, confidence, reasoning, realized P&L). Identify ONE short, generalizable lesson (max 30 words) that would help avoid repeating a loss or reinforce a winning pattern. Return ONLY a JSON object: {"lesson": "..."}. If the sample is too small or mixed to support any conclusion, return {"lesson": null}."""


def _format_decisions(decisions: list[ResolvedDecisionSummary]) -> str:
    return "\n".join(
        f"- {d.symbol} {d.action} conf={d.confidence:.2f} pnl={d.outcome_pnl:.2f}: {d.reasoning}"
        for d in decisions
    )


def _stats_fallback_lesson(decisions: list[ResolvedDecisionSummary]) -> str | None:
    if len(decisions) < 3:
        return None
    losers = [d for d in decisions if d.outcome_pnl < 0]
    if len(losers) / len(decisions) >= 0.6:
        symbols = ", ".join(sorted({d.symbol for d in losers}))
        return f"Recent losing streak across {symbols}: {len(losers)}/{len(decisions)} trades lost money; review sizing/entry filters."
    winners = [d for d in decisions if d.outcome_pnl > 0]
    if len(winners) / len(decisions) >= 0.7:
        return f"Recent win rate strong ({len(winners)}/{len(decisions)}); current entry filters are working, no change needed."
    return None


class LearningActor(IsolatedActor):
    """Owns its own private ``MemoryStore`` purely for auditability of
    lessons it has produced (a local copy), plus an optional private LLM
    client. Its input (resolved decisions) and output (lesson text)
    travel exclusively as messages."""

    def __init__(self, memory_db_path: str, llm_client: LLMClient | None = None) -> None:
        super().__init__(name="learning_actor")
        self._memory = MemoryStore(memory_db_path)
        self._llm = llm_client

    async def handle(self, request):  # noqa: ANN001
        if isinstance(request, LearningRunRequest):
            return await self._handle_run(request)
        raise TypeError(f"LearningActor cannot handle {type(request)!r}")

    async def _handle_run(self, request: LearningRunRequest) -> LearningRunResponse:
        decisions = request.resolved_decisions
        if not decisions:
            return LearningRunResponse(lessons=[], message="No newly resolved decisions to review")

        lesson_text: str | None = None
        if self._llm is not None:
            try:
                raw = await self._llm.complete_json(SYSTEM_PROMPT, _format_decisions(decisions))
                lesson_text = raw.get("lesson")
            except Exception as exc:
                logger.warning("LearningActor LLM call failed (%s); using stats fallback", exc)

        if not lesson_text:
            lesson_text = _stats_fallback_lesson(decisions)

        if not lesson_text:
            return LearningRunResponse(
                lessons=[], message=f"Reviewed {len(decisions)} decisions; no actionable lesson yet",
            )

        self._memory.add_lesson(lesson_text, scope="global", source_decision_ids=[d.decision_id for d in decisions])
        return LearningRunResponse(
            lessons=[lesson_text], message=f"Recorded lesson from {len(decisions)} decisions",
        )
