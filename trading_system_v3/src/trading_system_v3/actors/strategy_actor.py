"""StrategyActor: isolated agent that turns an IndicatorSet into a
TradeProposal, using an LLM given the indicator snapshot, position
context, and its own private memory -- with no path for any other
component to read that memory except through ``ask()``.

Reachable only via ``StrategyRequest`` -> ``StrategyResponse`` (per-cycle
decisions), ``StrategyOutcomeNotification`` (backfill an outcome after a
position closes), ``StrategyRecentOutcomesRequest`` (hand a sanitized
summary of newly resolved decisions to LearningActor, via the
orchestrator), and ``StrategyAddLessonRequest`` (receive a lesson
LearningActor wrote, again via the orchestrator -- StrategyActor never
talks to LearningActor directly).
"""
from __future__ import annotations

import logging

from trading_system_v3.actors.base import IsolatedActor
from trading_system_v3.core.models import (
    Action,
    IndicatorSet,
    ResolvedDecisionSummary,
    StrategyAddLessonRequest,
    StrategyAddLessonResponse,
    StrategyMarkExecutedRequest,
    StrategyMarkExecutedResponse,
    StrategyOutcomeNotification,
    StrategyRecentOutcomesRequest,
    StrategyRecentOutcomesResponse,
    StrategyRequest,
    StrategyResponse,
    TradeProposal,
)
from trading_system_v3.llm.client import LLMClient
from trading_system_v3.memory.store import MemoryStore

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a disciplined swing-trading strategy agent for a paper-trading system. You receive one symbol's technical indicators, current position (if any), your own past decisions for this symbol with their outcomes, and distilled lessons from past reviews. Return ONLY a JSON object with keys:
  action: "BUY" | "SELL" | "HOLD"
  confidence: float 0..1
  target_weight: float 0..1 (fraction of total portfolio equity this position should occupy if the action is BUY; ignored for SELL/HOLD)
  stop_loss_pct: float or null (fraction below entry price for a stop, e.g. 0.05)
  reasoning: short string (max 40 words) explaining the decision using the indicators and memory given

Rules: Be conservative. Only BUY when trend and momentum indicators agree (e.g. price above sma_20/sma_50, MACD histogram positive, RSI between 40-70). Only SELL an existing position on clear trend reversal or overbought exhaustion (RSI > 75) or breakdown below sma_50. Otherwise HOLD. Weigh your own track record and the provided lessons; if similar past setups lost money, lower confidence or prefer HOLD. Never invent data not provided."""


def rule_based_proposal(indicators: IndicatorSet, has_position: bool) -> TradeProposal:
    price, sma20, sma50 = indicators.price, indicators.sma_20, indicators.sma_50
    rsi, macd_hist = indicators.rsi_14, indicators.macd_hist

    if sma20 is None or sma50 is None:
        return TradeProposal(
            symbol=indicators.symbol, action=Action.HOLD, confidence=0.3,
            reasoning="Insufficient history for SMA signals.", proposed_by="rule_fallback",
        )

    bullish = price > sma20 > sma50 and (macd_hist or 0) > 0 and (rsi is None or rsi < 70)
    bearish = has_position and (price < sma50 or (rsi is not None and rsi > 75))

    if bullish:
        return TradeProposal(
            symbol=indicators.symbol, action=Action.BUY, confidence=0.6,
            target_weight=0.08, stop_loss_pct=0.06,
            reasoning="Price above SMA20/50 with positive MACD momentum.", proposed_by="rule_fallback",
        )
    if bearish:
        return TradeProposal(
            symbol=indicators.symbol, action=Action.SELL, confidence=0.6,
            reasoning="Price broke below SMA50 or RSI overbought exhaustion.", proposed_by="rule_fallback",
        )
    return TradeProposal(
        symbol=indicators.symbol, action=Action.HOLD, confidence=0.5,
        reasoning="No clear trend/momentum alignment.", proposed_by="rule_fallback",
    )


def _build_memory_context(memory: MemoryStore, symbol: str) -> str:
    parts = [memory.win_rate_summary(symbol)]
    recent = memory.recent_decisions(symbol, limit=5)
    if recent:
        parts.append("Recent decisions for this symbol:")
        for d in recent:
            outcome = f"outcome_pnl={d.outcome_pnl:.2f}" if d.outcome_pnl is not None else "outcome=pending"
            parts.append(f"  - {d.timestamp} {d.action} conf={d.confidence:.2f} ({outcome}): {d.reasoning}")
    lessons = memory.recent_lessons(scope="global", limit=5)
    if lessons:
        parts.append("Recent lessons from trade review:")
        for lesson in lessons:
            parts.append(f"  - {lesson}")
    return "\n".join(parts)


def _build_user_prompt(indicators: IndicatorSet, position_summary: str, memory_context: str) -> str:
    return (
        f"Symbol: {indicators.symbol}\nAs of: {indicators.as_of}\nPrice: {indicators.price}\n"
        f"SMA20: {indicators.sma_20} SMA50: {indicators.sma_50} SMA200: {indicators.sma_200}\n"
        f"EMA12: {indicators.ema_12} EMA26: {indicators.ema_26}\nRSI14: {indicators.rsi_14}\n"
        f"MACD: {indicators.macd} Signal: {indicators.macd_signal} Hist: {indicators.macd_hist}\n"
        f"ATR14: {indicators.atr_14}\n"
        f"5d change: {indicators.pct_change_5d} 20d change: {indicators.pct_change_20d}\n"
        f"Current position: {position_summary}\n\n--- Memory ---\n{memory_context}\n"
    )


class StrategyActor(IsolatedActor):
    """Owns a private ``MemoryStore`` (episodic decisions + semantic
    lessons) and an optional private LLM client. Nothing outside this
    class ever references ``self._memory`` or ``self._llm``."""

    def __init__(self, memory_db_path: str, llm_client: LLMClient | None = None) -> None:
        super().__init__(name="strategy_actor")
        self._memory = MemoryStore(memory_db_path)
        self._llm = llm_client
        self._learning_watermark = 0

    async def handle(self, request):  # noqa: ANN001 - dispatch on type below
        if isinstance(request, StrategyRequest):
            return await self._handle_decision(request)
        if isinstance(request, StrategyOutcomeNotification):
            return await self._handle_outcome(request)
        if isinstance(request, StrategyRecentOutcomesRequest):
            return await self._handle_recent_outcomes(request)
        if isinstance(request, StrategyAddLessonRequest):
            return await self._handle_add_lesson(request)
        if isinstance(request, StrategyMarkExecutedRequest):
            return await self._handle_mark_executed(request)
        raise TypeError(f"StrategyActor cannot handle {type(request)!r}")

    async def _handle_decision(self, request: StrategyRequest) -> StrategyResponse:
        indicators = request.indicators
        has_position = request.position is not None
        position_summary = (
            f"{request.position.quantity} @ {request.position.avg_price}" if request.position else "none"
        )
        memory_context = _build_memory_context(self._memory, indicators.symbol)

        proposal: TradeProposal | None = None
        if self._llm is not None:
            try:
                raw = await self._llm.complete_json(
                    SYSTEM_PROMPT, _build_user_prompt(indicators, position_summary, memory_context),
                )
                proposal = TradeProposal(
                    symbol=indicators.symbol,
                    action=Action(str(raw["action"]).upper()),
                    confidence=float(raw.get("confidence", 0.5)),
                    target_weight=float(raw.get("target_weight") or 0.0),
                    stop_loss_pct=raw.get("stop_loss_pct"),
                    reasoning=str(raw.get("reasoning", ""))[:400],
                    proposed_by="llm_strategy",
                )
            except Exception as exc:
                logger.warning("LLM strategy failed for %s (%s); falling back to rules", indicators.symbol, exc)

        if proposal is None:
            proposal = rule_based_proposal(indicators, has_position)

        decision_id = self._memory.log_decision(
            symbol=proposal.symbol, action=proposal.action.value, confidence=proposal.confidence,
            target_weight=proposal.target_weight, reasoning=proposal.reasoning, proposed_by=proposal.proposed_by,
        )
        proposal.decision_id = decision_id
        return StrategyResponse(proposal=proposal, decision_id=decision_id)

    async def _handle_outcome(self, request: StrategyOutcomeNotification) -> StrategyResponse:
        self._memory.backfill_outcome_for_symbol(request.symbol, request.realized_pnl)
        # Return a no-op-ish response type consistency isn't required here since
        # the orchestrator does not await a meaningful value; reuse StrategyResponse
        # with a synthetic HOLD proposal to keep the type contract simple.
        return StrategyResponse(
            proposal=TradeProposal(symbol=request.symbol, action=Action.HOLD, confidence=0.0, proposed_by="system"),
            decision_id=-1,
        )

    async def _handle_mark_executed(self, request: StrategyMarkExecutedRequest) -> StrategyMarkExecutedResponse:
        self._memory.mark_executed(request.decision_id)
        return StrategyMarkExecutedResponse(ok=True)

    async def _handle_recent_outcomes(self, request: StrategyRecentOutcomesRequest) -> StrategyRecentOutcomesResponse:
        rows = self._memory.newly_resolved_decisions(self._learning_watermark, limit=request.limit)
        if rows:
            self._learning_watermark = max(r.id for r in rows)
        summaries = [
            ResolvedDecisionSummary(
                decision_id=r.id, symbol=r.symbol, action=Action(r.action),
                confidence=r.confidence, reasoning=r.reasoning, outcome_pnl=r.outcome_pnl,
            )
            for r in rows
        ]
        return StrategyRecentOutcomesResponse(decisions=summaries)

    async def _handle_add_lesson(self, request: StrategyAddLessonRequest) -> StrategyAddLessonResponse:
        lesson_id = self._memory.add_lesson(request.text, scope="global", source_decision_ids=request.source_decision_ids)
        return StrategyAddLessonResponse(lesson_id=lesson_id)
