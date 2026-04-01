"""Exit Agent - Monitors positions for stop loss, take profit, and strategic re-analysis."""
import logging
from finance_service.core.flow_logger import flow
from typing import List, Dict, Any, Optional
from datetime import datetime
from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events, get_event_bus

logger = logging.getLogger(__name__)

class ExitAgent(Agent):
    """
    Exit Agent - Multi-mode position monitoring:
    1. Reactive exits: Stop-loss and take-profit triggers
    2. Strategic re-analysis: Check if held positions still meet BUY criteria
    """

    @property
    def agent_id(self) -> str:
        return "exit_agent"

    @property
    def goal(self) -> str:
        return "Monitor open positions for exit conditions (stops/profits) and strategic degradation."

    def __init__(self, config_engine=None, data_agent=None, execution_agent=None, analysis_agent=None, strategy_agent=None):
        self.config = config_engine
        self.event_bus = get_event_bus()
        self.data_agent = data_agent
        self.execution_agent = execution_agent
        self.analysis_agent = analysis_agent
        self.strategy_agent = strategy_agent
        logger.info("ExitAgent initialized with enhanced re-analysis capability.")

    async def run(self, positions: Optional[List[Dict[str, Any]]] = None, 
                  perform_strategy_check: bool = False,
                  **kwargs) -> AgentReport:
        """
        Check all open positions for exit conditions.
        
        Args:
            positions: List of open position dicts
            perform_strategy_check: If True, re-analyze if positions still meet BUY criteria
            **kwargs: Additional parameters (for compatibility)
        
        Returns:
            AgentReport with exits and/or degraded positions
        """
        if positions is None:
            logger.warning("No positions provided to ExitAgent.run")
            return AgentReport(agent_id=self.agent_id, status="error", message="No positions", payload={})

        exits = []
        degraded_positions = []
        
        # Mode 1: Check for reactive exits (stop-loss / take-profit)
        flow("ExitAgent", "START", f"checking {len(positions)} position(s) for exits")
        logger.info(f"ExitAgent: Checking {len(positions)} position(s) for reactive exits...")
        exits = await self._check_reactive_exits(positions)
        
        # Mode 2: Strategic re-analysis (if enabled)
        if perform_strategy_check and self.analysis_agent:
            logger.info(f"ExitAgent: Performing strategic re-analysis on {len(positions)} position(s)...")
            degraded_positions = await self._check_strategic_degradation(positions)

        message = f"Checked {len(positions)} position(s): {len(exits)} reactive exit(s), {len(degraded_positions)} strategic degradation(s)."
        payload = {
            "checked_count": len(positions),
            "reactive_exits": exits,
            "exits_count": len(exits),
            "degraded_positions": degraded_positions,
            "degraded_count": len(degraded_positions),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        flow("ExitAgent", "DONE", message)
        logger.info(message)
        return AgentReport(agent_id=self.agent_id, status="success", message=message, payload=payload)

    async def _check_reactive_exits(self, positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Check for stop-loss and take-profit exit conditions.
        
        Returns:
            List of triggered exits
        """
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
                    quote_report = await self.data_agent.run(
                        symbol=symbol, 
                        interval="1d", 
                        use_cache=False, 
                        emit_events=False
                    )
                    if quote_report.status == "success" and "dataframe" in quote_report.payload:
                        import pandas as pd
                        df = pd.DataFrame.from_dict(quote_report.payload["dataframe"])
                        if not df.empty:
                            current_price = float(df.iloc[-1]['close'])
                except Exception as e:
                    logger.warning(f"Failed to fetch price for {symbol}: {e}")

            if current_price is None:
                logger.debug(f"Skipping {symbol}: no price available")
                continue

            reason = None
            if stop_loss and current_price <= stop_loss:
                reason = f"Stop loss triggered: price ${current_price:.2f} <= ${stop_loss:.2f}"
            elif take_profit and current_price >= take_profit:
                reason = f"Take profit triggered: price ${current_price:.2f} >= ${take_profit:.2f}"

            if reason:
                exit_record = {
                    "symbol": symbol,
                    "quantity": quantity,
                    "current_price": current_price,
                    "exit_price": current_price,
                    "reason": reason,
                    "exit_type": "reactive",
                    "triggered_at": datetime.utcnow().isoformat()
                }
                exits.append(exit_record)
                logger.info(f"Exit triggered for {symbol}: {reason}")
                
                # Execute sell order if we have execution agent
                if self.execution_agent:
                    try:
                        trade_proposal = {
                            "symbol": symbol,
                            "action": "SELL",
                            "confidence": 1.0,
                            "quantity": quantity,
                            "rationale": [reason]
                        }
                        await self.execution_agent.run(approved_trade_proposal=trade_proposal)
                        logger.info(f"Exit order executed for {symbol}")
                    except Exception as e:
                        logger.error(f"Error executing exit for {symbol}: {e}", exc_info=True)
                else:
                    logger.warning(f"ExecutionAgent not set, cannot auto-execute exit for {symbol}")

        return exits

    async def _check_strategic_degradation(self, positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Re-analyze held positions to check if they still meet BUY criteria.
        
        Strategy: Fetch current data, run analysis, check if still "buy-worthy".
        If not, flag as degraded for human review.
        
        Returns:
            List of degraded positions that no longer meet BUY criteria
        """
        degraded = []
        
        for pos in positions:
            symbol = pos.get("symbol")
            
            if not symbol:
                continue
            
            try:
                # Fetch fresh data
                data_report = await self.data_agent.run(
                    symbol=symbol,
                    interval="1d",
                    use_cache=False,
                    emit_events=False
                )
                
                if data_report.status != "success":
                    logger.warning(f"Could not fetch fresh data for {symbol}")
                    continue
                
                # Run analysis on fresh data
                analysis_report = await self.analysis_agent.run(
                    data_payload=data_report.payload,
                    symbol=symbol
                )
                
                if analysis_report.status != "success":
                    logger.warning(f"Analysis failed for {symbol}")
                    continue
                
                # Check if still meets BUY criteria
                indicators = analysis_report.payload.get("indicators_snapshot", {})
                
                # Simple heuristic: RSI < 30 is "buy-worthy" (oversold)
                # If RSI > 70 now, it's degraded (overbought, should exit)
                rsi = indicators.get("rsi", 50)
                trend = indicators.get("trend", "neutral")
                
                # Degradation signal: RSI > 70 (overbought) OR bearish trend reversal
                is_degraded = (rsi > 70) or (trend == "bearish")
                
                if is_degraded:
                    entry_price = pos.get("entry_price", 0)
                    current_price = indicators.get("close", entry_price)
                    pnl = current_price - entry_price if entry_price else 0
                    
                    degraded_record = {
                        "symbol": symbol,
                        "quantity": pos.get("quantity"),
                        "entry_price": entry_price,
                        "current_price": current_price,
                        "pnl": pnl,
                        "rsi": rsi,
                        "trend": trend,
                        "reason": f"Position degraded: RSI {rsi:.1f} (overbought) or trend {trend}",
                        "recommendation": "Review for strategic exit",
                        "checked_at": datetime.utcnow().isoformat()
                    }
                    degraded.append(degraded_record)
                    logger.info(f"Position degraded for {symbol}: RSI={rsi:.1f}, trend={trend}")
                    
                    # Try to emit POSITION_DEGRADED event for orchestrator
                    try:
                        await self.event_bus.publish(Event(
                            event_type=Events.POSITION_DEGRADED,
                            data={
                                "symbol": symbol,
                                "degraded_record": degraded_record
                            }
                        ))
                        logger.info(f"Emitted POSITION_DEGRADED event for {symbol}")
                    except AttributeError:
                        # Event type might not exist, log but don't fail
                        logger.debug("Events.POSITION_DEGRADED not available in current event system")
                    except Exception as e:
                        logger.warning(f"Could not emit POSITION_DEGRADED event: {e}")
                
            except Exception as e:
                logger.error(f"Error checking strategic degradation for {symbol}: {e}", exc_info=True)
                continue
        
        return degraded
