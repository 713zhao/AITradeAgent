"""StrategyAgent: turns an IndicatorSet into a TradeProposal.

Architecture decision vs. the AITradeAgent baseline: the baseline's
StrategyAgent was a fixed rule (`sma20_trend`) with no market context or
reasoning trace. Here the primary strategy is an LLM given the full
indicator snapshot plus current position context, asked to return a
structured decision with a reasoning string (auditable) and a target
portfolio weight instead of a hardcoded share count, so RiskAgent/
PortfolioAgent do the actual sizing math against live equity.

Memory: this agent is memory-augmented. Every proposal it makes is
logged to MemoryStore (decisions table) regardless of whether it gets
executed. Before each decision it retrieves:
  - episodic memory: this symbol's recent past proposals + realized
    outcomes (win rate / avg P&L), so repeated bad setups are visible.
  - semantic memory: recent global "lessons" written by LearningAgent
    after reviewing closed trades.
Both are injected into the LLM prompt as context. Outcomes are
backfilled later by the orchestrator once a position closes.

A deterministic rule-based strategy is kept as:
  1. the default when no LLM API key is configured, and
  2. an automatic fallback if the LLM call fails or returns an
     unparseable/invalid response,
so the pipeline is never blocked on LLM availability.
"""
from __future__ import annotations

import logging

from trading_system.agents.base import Agent
from trading_system.core.models import Action, AgentReport, IndicatorSet, TradeProposal
from trading_system.llm.client import LLMClient
from trading_system.memory.store import MemoryStore

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a disciplined swing-trading strategy agent for a paper-trading system. You receive one symbol's technical indicators, current position (if any), your own past decisions for this symbol with their outcomes, and distilled lessons from past reviews. Return ONLY a JSON object with keys:
  action: "BUY" | "SELL" | "HOLD"
  confidence: float 0..1
  target_weight: float 0..1 (fraction of total portfolio equity this position should     occupy if the action is BUY; ignored for SELL/HOLD)
  stop_loss_pct: float or null (fraction below entry price for a stop, e.g. 0.05)
  reasoning: short string (max 40 words) explaining the decision using the indicators     and memory given

Rules: Be conservative. Only BUY when trend and momentum indicators agree (e.g. price above sma_20/sma_50, MACD histogram positive, RSI between 40-70). Only SELL an existing position on clear trend reversal or overbought exhaustion (RSI > 75) or breakdown below sma_50. Otherwise HOLD. Weigh your own track record and the provided lessons; if similar past setups lost money, lower confidence or prefer HOLD. Never invent data not provided."""


def rule_based_proposal(indicators: IndicatorSet, has_position: bool) -> TradeProposal:
    """Deterministic fallback strategy: SMA20/50 trend-follow with RSI filter."""
    price = indicators.price
    sma20 = indicators.sma_20
    sma50 = indicators.sma_50
    rsi = indicators.rsi_14
    macd_hist = indicators.macd_hist

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
            reasoning="Price above SMA20/50 with positive MACD momentum.",
            proposed_by="rule_fallback",
        )
    if bearish:
        return TradeProposal(
            symbol=indicators.symbol, action=Action.SELL, confidence=0.6,
            reasoning="Price broke below SMA50 or RSI overbought exhaustion.",
            proposed_by="rule_fallback",
        )
    return TradeProposal(
        symbol=indicators.symbol, action=Action.HOLD, confidence=0.5,
        reasoning="No clear trend/momentum alignment.", proposed_by="rule_fallback",
    )


def _build_user_prompt(
    indicators: IndicatorSet, has_position: bool, position_summary: str,
    memory_context: str,
) -> str:
    return (
        f"Symbol: {indicators.symbol}\n"
        f"As of: {indicators.as_of}\n"
        f"Price: {indicators.price}\n"
        f"SMA20: {indicators.sma_20} SMA50: {indicators.sma_50} SMA200: {indicators.sma_200}\n"
        f"EMA12: {indicators.ema_12} EMA26: {indicators.ema_26}\n"
        f"RSI14: {indicators.rsi_14}\n"
        f"MACD: {indicators.macd} Signal: {indicators.macd_signal} Hist: {indicators.macd_hist}\n"
        f"ATR14: {indicators.atr_14}\n"
        f"Bollinger upper/lower: {indicators.bb_upper} / {indicators.bb_lower}\n"
        f"5d change: {indicators.pct_change_5d} 20d change: {indicators.pct_change_20d}\n"
        f"Current position: {position_summary}\n"
        f"\n--- Memory ---\n{memory_context}\n"
    )


def _build_memory_context(memory: MemoryStore | None, symbol: str) -> str:
    if memory is None:
        return "No memory store configured."

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


class StrategyAgent(Agent):
    def __init__(self, llm_client: LLMClient | None = None, memory: MemoryStore | None = None) -> None:
        self._llm = llm_client
        self.memory = memory

    @property
    def agent_id(self) -> str:
        return "strategy_agent"

    @property
    def goal(self) -> str:
        return "Produce a trade proposal (BUY/SELL/HOLD) with reasoning from indicators and memory"

    async def run(
        self, indicators: IndicatorSet, has_position: bool = False, position_summary: str = "none",
    ) -> AgentReport:
        memory_context = _build_memory_context(self.memory, indicators.symbol)

        if self._llm is not None:
            try:
                raw = await self._llm.complete_json(
                    SYSTEM_PROMPT,
                    _build_user_prompt(indicators, has_position, position_summary, memory_context),
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
                decision_id = self._log(proposal)
                return AgentReport(
                    agent_id=self.agent_id, status="success",
                    message=f"LLM proposal for {indicators.symbol}: {proposal.action}",
                    payload={"proposal": proposal, "decision_id": decision_id},
                )
            except Exception as exc:
                logger.warning("LLM strategy failed for %s (%s); falling back to rules", indicators.symbol, exc)

        proposal = rule_based_proposal(indicators, has_position)
        decision_id = self._log(proposal)
        return AgentReport(
            agent_id=self.agent_id, status="success",
            message=f"Rule-based proposal for {indicators.symbol}: {proposal.action}",
            payload={"proposal": proposal, "decision_id": decision_id},
        )

    def _log(self, proposal: TradeProposal) -> int | None:
        if self.memory is None:
            return None
        return self.memory.log_decision(
            symbol=proposal.symbol, action=proposal.action.value, confidence=proposal.confidence,
            target_weight=proposal.target_weight, reasoning=proposal.reasoning,
            proposed_by=proposal.proposed_by,
        )
