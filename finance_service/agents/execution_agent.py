import logging
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import asdict

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events, get_event_bus
from finance_service.core.models import TradeProposal
from finance_service.brokers.interface import BrokerInterface, OrderResult

logger = logging.getLogger(__name__)

class ExecutionAgent(Agent):
    """Execution Agent - Executes approved trade proposals via configured broker."""

    @property
    def agent_id(self) -> str:
        return "execution_agent"

    @property
    def goal(self) -> str:
        return "Execute approved trade proposals efficiently and optimally in the market."

    def __init__(self, broker: BrokerInterface):
        """
        Args:
            broker: A BrokerInterface implementation (PaperBroker, TigerBrokersBroker, etc.)
        """
        self.broker = broker
        self.event_bus = get_event_bus()
        logger.info(f"ExecutionAgent initialized with broker: {broker.__class__.__name__}")

    async def run(self, approval_report: AgentReport) -> Optional[AgentReport]:
        """
        Receives an approved trade proposal and executes it via broker.

        Args:
            approval_report: Contains trade_proposals and risk_assessments

        Returns:
            AgentReport with execution result
        """
        logger.info("ExecutionAgent run: Executing approved trade proposal.")

        try:
            trade_proposals = approval_report.payload.get("trade_proposals", [])
            if not trade_proposals:
                raise ValueError("No trade_proposals found")
            trade_data = trade_proposals[0]
            trade_proposal = TradeProposal(**trade_data)

            # Build order dict for broker
            order = {
                'symbol': trade_proposal.symbol,
                'action': trade_proposal.action,
                'quantity': trade_proposal.quantity or 1.0,
                'order_type': 'market',  # Could be extended to limit orders
                'price': trade_proposal.target_price,  # broker may use as limit or reference
            }

            # Submit to broker
            order_result = await self.broker.submit_order(order)

            if order_result.status != "filled":
                return AgentReport(
                    agent_id=self.agent_id,
                    status="error",
                    message=f"Order failed: {order_result.error_message}",
                    payload={"execution_result": asdict(order_result)}
                )

            # Build execution result
            execution_result = {
                "trade_id": order_result.order_id,
                "symbol": order_result.symbol,
                "action": order_result.action,
                "quantity": order_result.filled_quantity,
                "filled_price": order_result.filled_price,
                "status": order_result.status,
                "timestamp": order_result.timestamp.isoformat(),
            }

            # Publish event
            report = AgentReport(
                agent_id=self.agent_id,
                status="success",
                message=f"Trade {trade_proposal.symbol} {trade_proposal.action} executed",
                payload={"execution_result": execution_result}
            )
            await self.event_bus.publish(Event(
                event_type=Events.TRADE_EXECUTED,
                data=asdict(report)
            ))
            return report

        except Exception as e:
            logger.error(f"Error in ExecutionAgent run: {e}", exc_info=True)
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message=f"Execution failed: {e}",
                payload={}
            )

    def __repr__(self) -> str:
        return f"<ExecutionAgent(id='{self.agent_id}', broker={self.broker.__class__.__name__})>"
