"""Exit Agent - Monitors positions for stop loss and take profit exits."""
import logging
from typing import List, Dict, Any, Optional
from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.events import Event, Events, get_event_bus

logger = logging.getLogger(__name__)

class ExitAgent(Agent):
    def __init__(self, config_engine, data_agent=None, execution_agent=None):
        self.config = config_engine
        self.event_bus = get_event_bus()  # Will be overwritten by orchestrator
        self.data_agent = data_agent
        self.execution_agent = execution_agent
        self.agent_id = "exit_agent"
        logger.info("ExitAgent initialized.")

    async def run(self, positions: Optional[List[Dict[str, Any]]] = None) -> AgentReport:
        """Check all open positions for exit conditions (stop loss / take profit)."""
        if positions is None:
            logger.warning("No positions provided to ExitAgent.run")
            return AgentReport(agent_id=self.agent_id, status="error", message="No positions", payload={})

        exits = []
        for pos in positions:
            symbol = pos.get("symbol")
            quantity = pos.get("quantity")
            current_price = pos.get("current_price")
            stop_loss = pos.get("stop_loss_price")
            take_profit = pos.get("take_profit_price")

            # Fetch fresh price if missing
            if current_price is None and self.data_agent:
                try:
                    quote_report = await self.data_agent.run(symbol=symbol, interval="1d", use_cache=False, emit_events=False)
                    if quote_report.status == "success" and "dataframe" in quote_report.payload:
                        import pandas as pd
                        df = pd.DataFrame.from_dict(quote_report.payload["dataframe"])
                        if not df.empty:
                            current_price = float(df.iloc[-1]['close'])
                except Exception as e:
                    logger.warning(f"Failed to fetch price for {symbol}: {e}")

            if current_price is None:
                continue

            reason = None
            if stop_loss and current_price <= stop_loss:
                reason = f"Stop loss triggered: price {current_price:.2f} <= {stop_loss:.2f}"
            elif take_profit and current_price >= take_profit:
                reason = f"Take profit triggered: price {current_price:.2f} >= {take_profit:.2f}"

            if reason:
                exits.append({
                    "symbol": symbol,
                    "quantity": quantity,
                    "price": current_price,
                    "reason": reason
                })
                # Execute sell order
                trade_proposal = {
                    "symbol": symbol,
                    "action": "SELL",
                    "confidence": 1.0,
                    "quantity": quantity,
                    "rationale": [reason]
                }
                if self.execution_agent:
                    try:
                        await self.execution_agent.run(approved_trade_proposal=trade_proposal)
                        logger.info(f"Exit executed for {symbol}: {reason}")
                    except Exception as e:
                        logger.error(f"Error executing exit for {symbol}: {e}", exc_info=True)
                else:
                    logger.warning(f"ExecutionAgent not set, cannot exit {symbol}")

        message = f"Checked {len(positions)} position(s); {len(exits)} exit(s) triggered."
        payload = {"exits": exits, "checked": len(positions)}
        logger.info(message)
        return AgentReport(agent_id=self.agent_id, status="success", message=message, payload=payload)
