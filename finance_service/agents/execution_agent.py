import logging
from finance_service.core.flow_logger import flow
from datetime import datetime
from typing import Dict, Any, Optional
from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.models import TradeProposal

logger = logging.getLogger(__name__)

class ExecutionAgent(Agent):
    """Execution Agent - Executes approved trade proposals with real broker integration."""

    @property
    def agent_id(self) -> str:
        return "execution_agent"

    @property
    def goal(self) -> str:
        return "Execute approved trade proposals efficiently and optimally in the market."

    def __init__(self, broker):
        """Initialize with broker instance to actually place trades."""
        self.broker = broker
        logger.info(f"✅ ExecutionAgent initialized with broker: {type(broker).__name__}")

    async def run(self, approval_report: AgentReport) -> Optional[AgentReport]:
        """
        Receives an approved trade proposal and executes it via the broker.
        The approval_report.payload contains:
        - trade_proposals: list of proposals (usually single item)
        - risk_assessments: list of assessments (matching proposals)
        - all_passed: bool
        - any_approval_required: bool
        """
        logger.info("🚀 ExecutionAgent: Executing approved trade proposal via broker")
        flow("ExecutionAgent", "START", "executing approved proposal via broker")

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

            # Execute via broker using submit_order(dict) interface
            logger.info(f"📊 Placing {trade_proposal.action.upper()} order: {trade_proposal.quantity} × {trade_proposal.symbol} @ ${trade_proposal.target_price}")
            
            try:
                order_dict = {
                    "symbol": trade_proposal.symbol,
                    "action": trade_proposal.action.upper(),
                    "quantity": trade_proposal.quantity or 1.0,
                    "order_type": "limit",
                    "price": trade_proposal.target_price,
                }
                order_result = await self.broker.submit_order(order_dict)
                
                if order_result.status == "rejected":
                    err = getattr(order_result, 'error_message', 'Unknown rejection reason')
                    logger.error(f"❌ Order rejected by broker: {err}")
                    return AgentReport(
                        agent_id=self.agent_id,
                        status="error",
                        message=f"Order rejected: {err}"
                    )
                
                logger.info(f"✅ Order submitted: {order_result.order_id} status={order_result.status}")
                
                execution_result = {
                    "trade_id": order_result.order_id,
                    "symbol": trade_proposal.symbol,
                    "action": trade_proposal.action,
                    "quantity": order_result.filled_quantity or order_result.quantity,
                    "price": order_result.filled_price or trade_proposal.target_price,
                    "filled_price": order_result.filled_price or trade_proposal.target_price,
                    "status": order_result.status,
                    "timestamp": datetime.utcnow().isoformat(),
                }
                
                flow("ExecutionAgent", "DONE", f"{trade_proposal.symbol} {trade_proposal.action} qty={execution_result['quantity']} @ ${execution_result['filled_price']} → {execution_result['status']}")
                message = f"✅ Trade {trade_proposal.symbol} {trade_proposal.action} executed: {execution_result['status']}"
                
            except Exception as broker_error:
                logger.error(f"❌ Broker execution failed: {broker_error}", exc_info=True)
                return AgentReport(
                    agent_id=self.agent_id,
                    status="error",
                    message=f"Broker execution failed: {broker_error}"
                )

            payload = {"execution_result": execution_result}

            report = AgentReport(
                agent_id=self.agent_id,
                status="success",
                message=message,
                payload=payload
            )
            return report
            
        except Exception as e:
            logger.error(f"❌ Error in ExecutionAgent run: {e}", exc_info=True)
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message=f"Error executing trade: {e}"
            )

    def __repr__(self) -> str:
        return f"<ExecutionAgent(id='{self.agent_id}', broker={type(self.broker).__name__})>"
