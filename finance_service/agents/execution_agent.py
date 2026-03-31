import logging
from datetime import datetime
from typing import Dict, Any, Optional
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
        Supports payload with either 'trade_proposal' (single) or 'trade_proposals' (array).
        """
        logger.info("ExecutionAgent run: Executing approved trade proposal.")

        try:
            # Extract trade proposal(s) from payload
            payload_data = approval_report.payload
            
            if "trade_proposals" in payload_data:
                proposals_data = payload_data["trade_proposals"]
                if not isinstance(proposals_data, list):
                    proposals_data = [proposals_data]
                # For now, execute first proposal only (batch execution can be added later)
                proposal_data = proposals_data[0]
                logger.info(f"Found {len(proposals_data)} proposals, executing first one for {proposal_data.get('symbol')}")
            elif "trade_proposal" in payload_data:
                proposal_data = payload_data["trade_proposal"]
            else:
                raise ValueError(f"Neither 'trade_proposal' nor 'trade_proposals' found in approval_report payload. Keys: {list(payload_data.keys())}")
            
            trade_proposal = TradeProposal(**proposal_data)
            # Assuming approval_report.payload also contains risk_assessment
            risk_assessment = approval_report.payload.get("risk_assessment", {})

            # Mock execution result
            execution_result = {
                "trade_id": f"trade_{trade_proposal.symbol}_{datetime.utcnow().timestamp()}",
                "symbol": trade_proposal.symbol,
                "action": trade_proposal.action,
                "quantity": 1.0,  # TODO: use actual position sizing
                "price": trade_proposal.target_price,  # PortfolioAgent expects 'price'
                "status": "FILLED",
                "timestamp": datetime.utcnow().isoformat()
            }

            message = f"Trade {trade_proposal.symbol} {trade_proposal.action} executed with status {execution_result['status']}"
            payload = {"execution_result": execution_result}

            await self.event_bus.publish(Event(
                event_type=Events.TRADE_EXECUTED,
                data=payload
            ))

            return AgentReport(
                agent_id=self.agent_id,
                status="success",
                message=message,
                payload=payload
            )
        except Exception as e:
            logger.error(f"Error in ExecutionAgent run: {e}", exc_info=True)
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message=f"Error executing trade: {e}"
            )

    def __repr__(self) -> str:
        return f"<ExecutionAgent(id='{self.agent_id}')>"
