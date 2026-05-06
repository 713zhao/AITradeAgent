import logging
from finance_service.core.flow_logger import flow
from datetime import datetime
from typing import Dict, Any, Optional
from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.models import TradeProposal

logger = logging.getLogger(__name__)


class ExecutionAgent(Agent):
    """Execution Agent - Executes approved trade proposals with optimal algorithms."""

    @property
    def agent_id(self) -> str:
        return "execution_agent"

    @property
    def goal(self) -> str:
        return (
            "Execute approved trade proposals efficiently and optimally in the market."
        )

    def __init__(self, config: Dict[str, Any]):
        self.config = config
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
        flow("ExecutionAgent", "START", "executing approved proposal")

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
                "timestamp": datetime.utcnow().isoformat(),
                "stop_loss": trade_proposal.stop_loss_price,
                "take_profit": trade_proposal.take_profit_price,
                "reason": trade_proposal.rationale[0]
                if trade_proposal.rationale
                else "Strategy execution",
            }

            flow(
                "ExecutionAgent",
                "DONE",
                f"{trade_proposal.symbol} {trade_proposal.action} qty={trade_proposal.quantity} @ ${trade_proposal.target_price} → {execution_result['status']}",
            )
            message = f"Trade {trade_proposal.symbol} {trade_proposal.action} executed with status {execution_result['status']}"
            payload = {"execution_result": execution_result}

            report = AgentReport(
                agent_id=self.agent_id,
                status="success",
                message=message,
                payload=payload,
            )
            return report
        except Exception as e:
            logger.error(f"Error in ExecutionAgent run: {e}")
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message=f"Error executing trade: {e}",
            )

    def __repr__(self) -> str:
        return f"<ExecutionAgent(id='{self.agent_id}')>"
