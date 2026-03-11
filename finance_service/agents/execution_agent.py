import logging
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
            # Placeholder for actual trade execution logic
            # This will involve:
            # 1. Extracting TradeProposal and possibly RiskCheckResult from approval_report.payload
            # 2. Selecting an execution algorithm (e.g., TWAP, VWAP, market order)
            # 3. Interacting with a BrokerManager to place the order
            # 4. Monitoring the order status
            # 5. Returning an ExecutionReport or similar payload in the AgentReport

            trade_proposal = TradeProposal(**approval_report.payload["trade_proposal"])
            # Assuming approval_report.payload also contains risk_assessment
            risk_assessment = approval_report.payload["risk_assessment"]

            # Mock execution result
            execution_result = {
                "trade_id": trade_proposal.symbol + "_exec_" + str(datetime.utcnow().timestamp()),
                "symbol": trade_proposal.symbol,
                "action": trade_proposal.action,
                "quantity": 1.0, # Placeholder quantity
                "filled_price": trade_proposal.target_price, # Assuming filled at target for mock
                "status": "FILLED",
                "timestamp": datetime.utcnow().isoformat()
            }

            message = f"Trade {trade_proposal.symbol} {trade_proposal.action} executed with status {execution_result['status']}"
            payload = {"execution_result": execution_result}

            self.event_bus.publish(Event(
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
            logger.error(f"Error in ExecutionAgent run: {e}")
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message=f"Error executing trade: {e}"
            )

    def __repr__(self) -> str:
        return f"<ExecutionAgent(id='{self.agent_id}')>"
