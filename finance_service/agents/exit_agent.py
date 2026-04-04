"""Exit Agent - Monitors positions for stop loss, take profit, and strategic re-analysis."""
import logging
from finance_service.core.flow_logger import flow
from typing import List, Dict, Any, Optional
from datetime import datetime
from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events, get_event_bus
from skills.exit.exit import ExitStrategy

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
        # Load exit strategy config
        if self.config:
            self.exit_strategy = self.config.get("finance", "risk/exit_strategy", default="atr")
            self.partial_target_pct = self.config.get("finance", "risk/partial_target_pct", default=0.02)
            self.trail_stop_multiplier = self.config.get("finance", "risk/trail_stop_multiplier", default=1.5)
        else:
            self.exit_strategy = "atr"
            self.partial_target_pct = 0.02
            self.trail_stop_multiplier = 1.5

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
        Check for stop-loss and take-profit exit conditions based on configured strategy.
        
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
            entry_price = pos.get("avg_cost") or pos.get("entry_price")

            # Fetch fresh price if missing
            if current_price is None and self.data_agent:
                try:
                    quote_report = await self.data_agent.run(
                        symbol=symbol,
                        interval="1d",
                        use_cache=True,
                        cache_only=True,
                        emit_events=False
                    )
                    if quote_report.status == "success" and "dataframe" in quote_report.payload:
                        import pandas as pd
                        df = pd.DataFrame.from_dict(quote_report.payload["dataframe"])
                        if not df.empty:
                            current_price = float(df.iloc[-1]['close'])
                except Exception as e:
                    logger.warning(f"Failed to fetch price for {symbol}: {e}")

            if current_price is None or entry_price is None or quantity is None:
                logger.debug(f"Skipping {symbol}: missing essential data (price/entry/qty)")
                continue

            reason = None
            exit_qty = quantity  # default full exit
            # Determine exit based on strategy
            if self.exit_strategy == "atr":
                # Use stored stop_loss and take_profit (set at trade execution)
                if stop_loss and current_price <= stop_loss:
                    reason = f"ATR stop triggered: price ${current_price:.2f} <= ${stop_loss:.2f}"
                elif take_profit and current_price >= take_profit:
                    reason = f"ATR take profit triggered: price ${current_price:.2f} >= ${take_profit:.2f}"
            elif self.exit_strategy == "fixed_pct":
                # Use configured fixed percentages (stop_loss_default_pct, take_profit_default_pct) if not stored
                sl_pct = self.config.get("risk.stop_loss_default_pct", 0.015) if self.config else 0.015
                tp_pct = self.config.get("risk.take_profit_default_pct", 0.03) if self.config else 0.03
                stop = entry_price * (1 - sl_pct)
                take = entry_price * (1 + tp_pct)
                if current_price <= stop:
                    reason = f"Fixed % stop triggered ({sl_pct*100:.1f}%): price ${current_price:.2f} <= ${stop:.2f}"
                elif current_price >= take:
                    reason = f"Fixed % take profit triggered ({tp_pct*100:.1f}%): price ${current_price:.2f} >= ${take:.2f}"
            elif self.exit_strategy == "partial_trail":
                # Use ATR-based stop (from position) and a partial target
                partial_target = entry_price * (1 + self.partial_target_pct)
                if stop_loss and current_price <= stop_loss:
                    reason = f"ATR stop (partial_trail mode): price ${current_price:.2f} <= ${stop_loss:.2f}"
                elif current_price >= partial_target:
                    # For now, exit full position at partial target (simplified)
                    reason = f"Partial target ({self.partial_target_pct*100:.0f}%) reached: price ${current_price:.2f} >= ${partial_target:.2f} → exit full"
                else:
                    reason = None
            else:
                logger.warning(f"Unknown exit_strategy: {self.exit_strategy}")

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
                    use_cache=True,
                    cache_only=True,
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
                # Use strategy's exit rules to determine if position should be sold
                try:
                    should_sell, exit_rules = self.strategy_agent.rule_strategy.evaluate_exit(indicators)
                    is_degraded = should_sell
                except Exception as e:
                    logger.error(f"Error evaluating exit strategy for {symbol}: {e}")
                    is_degraded = False
                
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
                        "exit_rules": exit_rules,
                        "reason": f"Position exit signal: {', '.join(exit_rules) if exit_rules else 'strategy exit'}",
                        "recommendation": "Strategic exit triggered",
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
