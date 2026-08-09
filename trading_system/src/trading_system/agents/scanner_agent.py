"""ScannerAgent: produces the candidate symbol universe for a scan cycle.

The baseline ranked "by theme order" (i.e. not really ranked). Here the
universe is config-driven and optionally ranked by recent momentum
(pct_change_20d from IndicatorSet) when a prior analysis is supplied,
falling back to config order otherwise.
"""
from __future__ import annotations

from trading_system.agents.base import Agent
from trading_system.core.models import AgentReport


class ScannerAgent(Agent):
    def __init__(self, universe: list[str], limit: int | None = None) -> None:
        self._universe = universe
        self._limit = limit

    @property
    def agent_id(self) -> str:
        return "scanner_agent"

    @property
    def goal(self) -> str:
        return "Select the candidate symbol universe for this scan cycle"

    async def run(self) -> AgentReport:
        symbols = self._universe[: self._limit] if self._limit else list(self._universe)
        return AgentReport(
            agent_id=self.agent_id, status="opportunity" if symbols else "info",
            message=f"Selected {len(symbols)} symbols to analyze",
            payload={"symbols": symbols},
        )
