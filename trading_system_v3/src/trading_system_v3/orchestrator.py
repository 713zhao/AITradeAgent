"""Orchestrator: runs the per-symbol pipeline, talking to the mechanical
pipeline stages directly and to StrategyActor/RiskActor/LearningActor
exclusively through ``ask()``. It never reaches into an actor's private
state -- every fact one actor needs from another (e.g. RiskActor being
told about a realized loss, or LearningActor being handed resolved
decisions) crosses as an explicit message that the orchestrator relays.

Symbols are processed sequentially within a scan cycle (not concurrently)
for the same reason as the prior design: RiskActor's per-request decision
and PortfolioStage's equity snapshot must reflect a consistent, up-to-date
view of cash/positions/today's P&L, and PortfolioStage is the single
writer. Making this concurrent would let concurrent equity reads reflect
inconsistent state.
"""
from __future__ import annotations

import logging

from trading_system_v3.actors.learning_actor import LearningActor
from trading_system_v3.actors.risk_actor import RiskActor
from trading_system_v3.actors.strategy_actor import StrategyActor
from trading_system_v3.core.models import (
    Action,
    LearningRunRequest,
    PositionSummary,
    RiskOutcomeNotification,
    RiskRequest,
    StrategyAddLessonRequest,
    StrategyMarkExecutedRequest,
    StrategyOutcomeNotification,
    StrategyRecentOutcomesRequest,
    StrategyRequest,
)
from trading_system_v3.pipeline.analysis_stage import compute_indicators
from trading_system_v3.pipeline.data_stage import DataStage
from trading_system_v3.pipeline.execution_stage import ExecutionStage
from trading_system_v3.pipeline.portfolio_stage import PortfolioStage
from trading_system_v3.pipeline.scanner_stage import ScannerStage

logger = logging.getLogger(__name__)


def _position_summary(position) -> PositionSummary | None:  # noqa: ANN001
    if position is None:
        return None
    return PositionSummary(
        symbol=position.symbol, quantity=position.quantity,
        avg_price=position.avg_price, stop_loss_price=position.stop_loss_price,
    )


class Orchestrator:
    def __init__(
        self,
        scanner: ScannerStage,
        data: DataStage,
        strategy: StrategyActor,
        risk: RiskActor,
        execution: ExecutionStage,
        portfolio: PortfolioStage,
        learning: LearningActor | None = None,
        lookback_days: int = 250,
    ) -> None:
        self.scanner = scanner
        self.data = data
        self.strategy = strategy
        self.risk = risk
        self.execution = execution
        self.portfolio = portfolio
        self.learning = learning
        self.lookback_days = lookback_days

    async def run_symbol(self, symbol: str) -> dict:
        result: dict = {"symbol": symbol}

        try:
            ohlcv = await self.data.fetch(symbol, lookback_days=self.lookback_days)
        except Exception as exc:
            result["error"] = f"data fetch failed: {exc}"
            return result

        try:
            indicators = compute_indicators(ohlcv)
        except Exception as exc:
            result["error"] = f"analysis failed: {exc}"
            return result

        positions = self.portfolio.store.positions()
        current_position = positions.get(symbol)

        strategy_resp = await self.strategy.ask(
            StrategyRequest(indicators=indicators, position=_position_summary(current_position))
        )
        proposal = strategy_resp.proposal
        result["proposal"] = proposal

        prices = {symbol: indicators.price, **{s: p.avg_price for s, p in positions.items()}}
        equity = self.portfolio.store.record_equity(prices)

        risk_resp = await self.risk.ask(RiskRequest(
            proposal=proposal, equity=equity, price=indicators.price,
            current_position=_position_summary(current_position),
            open_position_count=len(positions),
            realized_pnl_today=self.portfolio.store.day_realized_pnl(),
            starting_equity_today=self.portfolio.store.day_start_equity(),
        ))
        decision = risk_resp.decision
        result["decision"] = decision

        if not decision.approved or decision.action == Action.HOLD:
            return result

        try:
            execution_result = await self.execution.execute(decision, reference_price=indicators.price)
        except Exception as exc:
            result["error"] = f"execution failed: {exc}"
            return result
        result["execution"] = execution_result

        await self.portfolio.apply(execution_result, stop_loss_price=decision.stop_loss_price)

        if execution_result.action == Action.BUY:
            await self.strategy.ask(StrategyMarkExecutedRequest(decision_id=strategy_resp.decision_id))

        if execution_result.action == Action.SELL:
            realized = self.portfolio.store.trade_history(limit=1)[0]["realized_pnl"]
            await self.strategy.ask(StrategyOutcomeNotification(symbol=symbol, realized_pnl=realized))
            await self.risk.ask(RiskOutcomeNotification(symbol=symbol, realized_pnl=realized))

        return result

    async def run_scan_cycle(self) -> list[dict]:
        symbols = await self.scanner.scan()
        results = []
        for symbol in symbols:
            try:
                results.append(await self.run_symbol(symbol))
            except Exception as exc:
                logger.exception("Pipeline failed for %s", symbol)
                results.append({"symbol": symbol, "error": str(exc)})
        return results

    async def run_learning_cycle(self) -> dict | None:
        """Pulls newly resolved decisions out of StrategyActor (as
        sanitized summaries), hands them to LearningActor, and relays any
        lesson text back into StrategyActor's private semantic memory.
        Safe to call after every scan cycle; a no-op if nothing new
        resolved."""
        if self.learning is None:
            return None
        outcomes = await self.strategy.ask(StrategyRecentOutcomesRequest())
        if not outcomes.decisions:
            return {"message": "No newly resolved decisions to review", "lessons": []}
        learn_resp = await self.learning.ask(LearningRunRequest(resolved_decisions=outcomes.decisions))
        for lesson in learn_resp.lessons:
            await self.strategy.ask(StrategyAddLessonRequest(
                text=lesson, source_decision_ids=[d.decision_id for d in outcomes.decisions],
            ))
        return {"message": learn_resp.message, "lessons": learn_resp.lessons}
