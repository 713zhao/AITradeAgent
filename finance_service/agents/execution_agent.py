import logging
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import asdict
from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events, get_event_bus
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
        The approval_report.payload contains:
        - trade_proposals: list of proposals (usually single item)
        - risk_assessments: list of assessments (matching proposals)
        - all_passed: bool
        - any_approval_required: bool
        """
        logger.info("ExecutionAgent run: Executing approved trade proposal.")

        try:
            # Extract the first trade proposal (single-proposal flow)
            trade_proposals = approval_report.payload.get("trade_proposals", [])
            if not trade_proposals:
                raise ValueError("No trade_proposals found in approval_report.payload")
            trade_proposal_data = trade_proposals[0]
            trade_proposal = TradeProposal(**trade_proposal_data)

            # Extract risk assessment if needed
            risk_assessments = approval_report.payload.get("risk_assessments", [])
            risk_assessment = risk_assessments[0] if risk_assessments else {}

            # Mock execution result
            execution_result = {
                "trade_id": f"trade_{trade_proposal.symbol}_{datetime.utcnow().timestamp()}",
                "symbol": trade_proposal.symbol,
                "action": trade_proposal.action,
                "quantity": trade_proposal.quantity or 1.0,
                "filled_price": trade_proposal.target_price,  # mock: fill at target
                "status": "FILLED",
                "timestamp": datetime.utcnow().isoformat()
            }

            message = f"Trade {trade_proposal.symbol} {trade_proposal.action} executed with status {execution_result['status']}"
            payload = {"execution_result": execution_result}

            # Publish execution event as an AgentReport
            report = AgentReport(
                agent_id=self.agent_id,
                status="success",
                message=message,
                payload=payload
            )
            event_data = asdict(report)
            logger.info(f"[EXECUTION DEBUG] Publishing TRADE_EXECUTED event with data keys: {list(event_data.keys())}")
            await self.event_bus.publish(Event(
                event_type=Events.TRADE_EXECUTED,
                data=event_data
            ))
            return report
        except Exception as e:
            logger.error(f"Error in ExecutionAgent run: {e}")
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message=f"Error executing trade: {e}"
            )

    def __repr__(self) -> str:
        return f"<ExecutionAgent(id='{self.agent_id}')>"
