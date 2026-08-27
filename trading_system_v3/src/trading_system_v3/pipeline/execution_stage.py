"""ExecutionStage: submits approved RiskDecisions to the broker."""
from __future__ import annotations

from trading_system_v3.broker.paper_broker import Broker
from trading_system_v3.core.models import ExecutionResult, RiskDecision


class ExecutionStage:
    def __init__(self, broker: Broker) -> None:
        self._broker = broker

    async def execute(self, decision: RiskDecision, reference_price: float) -> ExecutionResult:
        if not decision.approved:
            raise ValueError(f"Cannot execute unapproved decision for {decision.symbol}")
        fill = self._broker.submit_order(
            symbol=decision.symbol, action=decision.action, quantity=decision.quantity,
            reference_price=reference_price, order_type=decision.order_type,
            limit_price=decision.limit_price,
        )
        return ExecutionResult(
            symbol=decision.symbol, action=decision.action, quantity=decision.quantity,
            requested_price=reference_price, filled_price=fill.filled_price,
            commission=fill.commission, slippage=fill.slippage, status="filled",
            order_id=fill.order_id,
        )
