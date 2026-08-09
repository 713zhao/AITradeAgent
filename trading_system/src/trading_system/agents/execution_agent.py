from __future__ import annotations

from trading_system.agents.base import Agent
from trading_system.broker.paper_broker import Broker
from trading_system.core.models import AgentReport, ExecutionResult, RiskDecision


class ExecutionAgent(Agent):
    def __init__(self, broker: Broker) -> None:
        self._broker = broker

    @property
    def agent_id(self) -> str:
        return "execution_agent"

    @property
    def goal(self) -> str:
        return "Submit approved trade decisions to the broker and report fills"

    async def run(self, decision: RiskDecision, reference_price: float) -> AgentReport:
        if not decision.approved:
            return AgentReport(
                agent_id=self.agent_id, status="failure",
                message=f"Cannot execute unapproved decision for {decision.symbol}",
            )
        fill = self._broker.submit_order(
            symbol=decision.symbol, action=decision.action, quantity=decision.quantity,
            reference_price=reference_price, order_type=decision.order_type,
            limit_price=decision.limit_price,
        )
        result = ExecutionResult(
            symbol=decision.symbol, action=decision.action, quantity=decision.quantity,
            requested_price=reference_price, filled_price=fill.filled_price,
            commission=fill.commission, slippage=fill.slippage, status="filled",
            order_id=fill.order_id,
        )
        return AgentReport(
            agent_id=self.agent_id, status="success",
            message=f"Filled {decision.action} {decision.quantity} {decision.symbol} @ {fill.filled_price:.2f}",
            payload={"execution": result, "stop_loss_price": decision.stop_loss_price},
        )
