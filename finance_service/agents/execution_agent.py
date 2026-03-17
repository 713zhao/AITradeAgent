import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.events import Event, Events, get_event_bus
from finance_service.core.models import TradeProposal

logger = logging.getLogger(__name__)

class ExecutionAgent(Agent):
    """Execution Agent - Executes approved trade proposals with optimal algorithms."""

    @property
    def agent_id(self) -> str:
        return "execution_agent"

    @property
    def goal(self) -> str:
        return "Execute approved trade proposals efficiently and optimally in the market."

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.event_bus = get_event_bus()
        logger.info(f"ExecutionAgent initialized with config: {self.config}")

    async def run(self, approval_report: AgentReport) -> Optional[AgentReport]:
        """
        Receives an approved trade proposal and executes it.
        """
        logger.info("ExecutionAgent run: Executing approved trade proposal.")

        try:
            trade_proposal = TradeProposal(**approval_report.payload["trade_proposal"])
            risk_assessment = approval_report.payload.get("risk_assessment", {})
            
            # Mock execution - fill at target price
            execution_result = {
                "trade_id": f"exec_{int(datetime.utcnow().timestamp()*1000)}",
                "symbol": trade_proposal.symbol,
                "action": trade_proposal.action,
                "quantity": 1.0,  # Fixed quantity for now
                "price": trade_proposal.target_price,
                "status": "FILLED",
                "timestamp": datetime.utcnow().isoformat()
            }

            message = f"Trade {trade_proposal.symbol} {trade_proposal.action} executed"
            payload = {"execution_result": execution_result}
            
            # Publish as a proper AgentReport for the orchestrator
            execution_report = AgentReport(
                agent_id=self.agent_id,
                status="success",
                message=message,
                payload=payload
            )
            
            # Publish event with full AgentReport structure
            await self.event_bus.publish(Event(
                event_type=Events.TRADE_EXECUTED,
                data=execution_report.to_dict() if hasattr(execution_report, 'to_dict') else {
                    "agent_id": execution_report.agent_id,
                    "status": execution_report.status,
                    "message": execution_report.message,
                    "payload": execution_report.payload
                }
            ))

            return execution_report
            
        except Exception as e:
            logger.error(f"Error in ExecutionAgent run: {e}")
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message=f"Error executing trade: {e}",
                payload={}
            )

    def __repr__(self) -> str:
        return f"<ExecutionAgent(id='{self.agent_id}')>"
