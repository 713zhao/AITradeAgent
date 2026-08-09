"""Orchestrator: wires agents together via the EventBus and runs the
per-symbol pipeline concurrently, mirroring the baseline's Orchestrator
but as an explicit, linear async function per symbol (easier to trace
and test) plus event publication for observability/telegram-style hooks.
"""
from __future__ import annotations

import logging

from trading_system.agents.analysis_agent import AnalysisAgent
from trading_system.agents.data_agent import DataAgent
from trading_system.agents.execution_agent import ExecutionAgent
from trading_system.agents.portfolio_agent import PortfolioAgent
from trading_system.agents.risk_agent import RiskAgent
from trading_system.agents.scanner_agent import ScannerAgent
from trading_system.agents.strategy_agent import StrategyAgent
from trading_system.core.event_bus import Event, EventBus, Events
from trading_system.core.models import Action

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(
        self,
        scanner: ScannerAgent,
        data: DataAgent,
        analysis: AnalysisAgent,
        strategy: StrategyAgent,
        risk: RiskAgent,
        execution: ExecutionAgent,
        portfolio: PortfolioAgent,
        event_bus: EventBus | None = None,
        lookback_days: int = 250,
    ) -> None:
        self.scanner = scanner
        self.data = data
        self.analysis = analysis
        self.strategy = strategy
        self.risk = risk
        self.execution = execution
        self.portfolio = portfolio
        self.bus = event_bus or EventBus()
        self.lookback_days = lookback_days

    async def run_symbol(self, symbol: str) -> dict:
        result: dict = {"symbol": symbol}

        data_report = await self.data.run(symbol, lookback_days=self.lookback_days)
        if data_report.status != "success":
            result["error"] = data_report.message
            return result
        ohlcv = data_report.payload["ohlcv"]
        await self.bus.publish(Event(Events.DATA_FETCH_COMPLETE, {"symbol": symbol}))

        analysis_report = await self.analysis.run(ohlcv)
        if analysis_report.status != "success":
            result["error"] = analysis_report.message
            return result
        indicators = analysis_report.payload["indicators"]
        await self.bus.publish(Event(Events.ANALYSIS_COMPLETE, {"symbol": symbol}))

        positions = self.portfolio.store.positions()
        current_position = positions.get(symbol)

        strategy_report = await self.strategy.run(
            indicators, has_position=current_position is not None,
            position_summary=(
                f"{current_position.quantity} @ {current_position.avg_price}" if current_position else "none"
            ),
        )
        proposal = strategy_report.payload["proposal"]
        result["proposal"] = proposal
        await self.bus.publish(Event(Events.TRADE_PROPOSAL_GENERATED, {"symbol": symbol, "action": proposal.action}))

        equity = self.portfolio.store.record_equity({symbol: indicators.price, **{
            s: p.avg_price for s, p in positions.items()
        }})

        risk_report = await self.risk.run(
            proposal=proposal, equity=equity, current_position=current_position,
            open_position_count=len(positions), realized_pnl_today=self.portfolio.store.day_realized_pnl(),
            starting_equity_today=self.portfolio.store.day_start_equity(), price=indicators.price,
        )
        decision = risk_report.payload["decision"]
        result["decision"] = decision
        await self.bus.publish(Event(Events.RISK_DECISION_MADE, {"symbol": symbol, "approved": decision.approved}))

        if not decision.approved or decision.action == Action.HOLD:
            return result

        execution_report = await self.execution.run(decision, reference_price=indicators.price)
        execution_result = execution_report.payload["execution"]
        result["execution"] = execution_result
        await self.bus.publish(Event(Events.TRADE_EXECUTED, {"symbol": symbol, "action": execution_result.action}))

        await self.portfolio.run(execution_result, stop_loss_price=decision.stop_loss_price)
        if execution_result.action == Action.SELL:
            realized = self.portfolio.store.trade_history(limit=1)[0]["realized_pnl"]
            if realized < 0:
                self.risk.register_loss(symbol)
        await self.bus.publish(Event(Events.PORTFOLIO_UPDATED, {"symbol": symbol}))

        return result

    async def run_scan_cycle(self) -> list[dict]:
        scan_report = await self.scanner.run()
        symbols = scan_report.payload.get("symbols", [])
        await self.bus.publish(Event(Events.MARKET_SCANNED, {"symbols": symbols}))

        results = []
        for symbol in symbols:
            try:
                results.append(await self.run_symbol(symbol))
            except Exception as exc:
                logger.exception("Pipeline failed for %s", symbol)
                await self.bus.publish(Event(Events.PIPELINE_ERROR, {"symbol": symbol, "error": str(exc)}))
                results.append({"symbol": symbol, "error": str(exc)})
        return results
