"""
Finance Service ASGI application.
"""
import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from quart import Quart, request, jsonify, Response
from hypercorn.config import Config
from hypercorn.asyncio import serve

from finance_service.core.config import Config as AppConfig
from finance_service.core.event_bus import get_event_bus, Event, Events
from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.agents.scheduler_agent import SchedulerAgent
from finance_service.agents.market_scanner_agent import MarketScannerAgent
from finance_service.agents.data_agent import DataAgent
from finance_service.agents.news_agent import NewsAgent
from finance_service.agents.analysis_agent import AnalysisAgent
from finance_service.agents.strategy_agent import StrategyAgent
from finance_service.agents.risk_agent import RiskAgent
from finance_service.agents.execution_agent import ExecutionAgent
from finance_service.agents.portfolio_agent import PortfolioAgent
from finance_service.agents.health_agent import HealthAgent
from finance_service.agents.telegram_agent import TelegramAgent
from finance_service.tools.approval_gate import get_approval_gate
from finance_service.agents.exit_agent import ExitAgent
from finance_service.agents.agent_interface import AgentReport
from finance_service.portfolio.trade_repository import TradeRepository

logger = logging.getLogger(__name__)

# Global orchestrator reference (for background tasks and event handlers)
_orchestrator: Optional['MainOrchestratorAgent'] = None
_system_paused: bool = False

# EventBus will be initialized in startup
event_bus = None

class MainOrchestratorAgent:
    """Orchestrates all agents and handles event routing."""

    def __init__(self, config: Dict[str, Any]):
        self.config_engine = AppConfig()
        self.config = config
        self.event_bus = get_event_bus()  # Get the singleton
        self.repository = TradeRepository()
        # Agents will be initialized in startup_orchestrator
        self.scheduler_agent: Optional[SchedulerAgent] = None
        self.market_scanner_agent: Optional[MarketScannerAgent] = None
        self.data_agent: Optional[DataAgent] = None
        self.news_agent: Optional[NewsAgent] = None
        self.analysis_agent: Optional[AnalysisAgent] = None
        self.strategy_agent: Optional[StrategyAgent] = None
        self.risk_agent: Optional[RiskAgent] = None
        self.execution_agent: Optional[ExecutionAgent] = None
        self.portfolio_agent: Optional[PortfolioAgent] = None
        self.health_agent: Optional[HealthAgent] = None
        self.telegram_agent: Optional[TelegramAgent] = None
        self.exit_agent: Optional[ExitAgent] = None

    async def run(self):
        """Main run loop - not used; agents run as background tasks."""
        pass

    async def startup_orchestrator(self):
        """Initialize agents and register event handlers."""
        global event_bus
        if event_bus is None:
            event_bus = get_event_bus()
        logger.info("Starting orchestrator initialization...")
        # Initialize YAML config engine (reads config/*.yaml) with absolute path
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_engine = YAMLConfigEngine(config_dir=os.path.join(base_dir, "config"))
        # Build a simple config dict for agents that expect dict (Telegram, Execution, Portfolio, Risk, Scheduler)
        # Populate with values from YAML where needed.
        simple_config: Dict[str, Any] = {
            "initial_cash": config_engine.get("finance", "portfolio/initial_cash", default=100000.0),
        }
        # Only add Telegram config from YAML if present; otherwise TelegramAgent will use .env via Config fallback
        telegram_token = config_engine.get("telegram", "bot_token", default=None)
        if telegram_token:
            simple_config["telegram_bot_token"] = telegram_token
        telegram_chat = config_engine.get("telegram", "chat_id", default=None)
        if telegram_chat:
            simple_config["telegram_chat_id"] = telegram_chat
        telegram_thread = config_engine.get("telegram", "message_thread_id", default=None)
        if telegram_thread is not None:
            simple_config["telegram_message_thread_id"] = telegram_thread
        # Build risk policy dict from YAML risk section (to satisfy RiskAgent)
        risk_policy: Dict[str, Any] = {}
        # Map of RiskPolicy field -> config path relative to finance/risk
        risk_fields = [
            "max_position_size_pct",
            "max_exposure_pct",
            "max_daily_loss_pct",
            "max_drawdown_pct",
            "default_risk_budget_pct",
            "stop_loss_default_pct",
            "take_profit_default_pct",
            "max_concurrent_positions",
            "min_position_size_usd",
            "allow_short_selling",
            "margin_enabled",
        ]
        for field in risk_fields:
            val = config_engine.get("finance", f"risk/{field}", default=None)
            if val is not None:
                risk_policy[field] = val
        simple_config["policy"] = risk_policy

        # Pass auto_execute flag to RiskAgent to enforce approval override
        auto_execute_enabled = config_engine.get("finance", "strategy/auto_execute/enabled", default=True)
        simple_config["auto_execute_enabled"] = auto_execute_enabled

        # Initialize agents
        self.scheduler_agent = SchedulerAgent(simple_config)
        self.market_scanner_agent = MarketScannerAgent(config_engine)
        self.data_agent = DataAgent(config_engine)
        self.news_agent = NewsAgent(config_engine)
        # AnalysisAgent: uses default indicator periods; no config needed
        self.analysis_agent = AnalysisAgent()
        # StrategyAgent: needs config_engine and portfolio_agent (injected after)
        self.strategy_agent = StrategyAgent(config_engine, portfolio_agent=None)
        # RiskAgent: uses simple_config with policy dict
        self.risk_agent = RiskAgent(simple_config, portfolio_agent=None)
        # ExecutionAgent: simple config
        self.execution_agent = ExecutionAgent(simple_config)
        # PortfolioAgent: needs simple_config and data_agent
        self.portfolio_agent = PortfolioAgent(simple_config, data_agent=self.data_agent)
        # HealthAgent: uses config_engine
        self.health_agent = HealthAgent(config_engine)
        # TelegramAgent: uses simple_config
        self.telegram_agent = TelegramAgent(simple_config)
        # ExitAgent: monitors held positions for exit conditions
        self.exit_agent = ExitAgent(
            config_engine=config_engine,
            data_agent=self.data_agent,
            execution_agent=self.execution_agent,
            analysis_agent=self.analysis_agent,
            strategy_agent=self.strategy_agent
        )

        # Inject dependencies
        self.strategy_agent.portfolio_agent = self.portfolio_agent
        self.risk_agent.portfolio_agent = self.portfolio_agent
        self.health_agent.portfolio_agent = self.portfolio_agent
        self.health_agent.telegram_agent = self.telegram_agent
        self.portfolio_agent.repository = self.repository

        # Inject dependencies
        self.health_agent.telegram_agent = self.telegram_agent
        self.health_agent.portfolio_agent = self.portfolio_agent
        self.portfolio_agent.repository = self.repository

        # Register event handlers (await async subscribe)
        await self.event_bus.subscribe(Events.MARKET_SCAN_TRIGGER, self.handle_market_scan_trigger)
        await self.event_bus.subscribe(Events.MARKET_SCANNED, self.handle_market_scanned)
        await self.event_bus.subscribe(Events.DATA_FETCH_COMPLETE, self.handle_data_fetched)
        await self.event_bus.subscribe(Events.NEWS_FETCH_COMPLETE, self.handle_news_fetched)
        await self.event_bus.subscribe(Events.ANALYSIS_COMPLETE, self.handle_analysis_complete)
        # Strategy agent is called directly; no event subscription needed
        await self.event_bus.subscribe(Events.RISK_CHECK_COMPLETE, self.handle_risk_complete)
        await self.event_bus.subscribe(Events.TRADE_EXECUTED, self.handle_trade_executed)
        await self.event_bus.subscribe(Events.GET_PORTFOLIO_STATE, self.handle_get_portfolio_state)
        await self.event_bus.subscribe(Events.GET_SYSTEM_STATUS, self.handle_get_system_status)
        await self.event_bus.subscribe(Events.SCHEDULE, self.handle_schedule)  # health checks, daily report
        await self.event_bus.subscribe(Events.EXIT_CHECK_TRIGGER, self.handle_exit_check)  # Tier 3
        await self.event_bus.subscribe(Events.POSITION_DEGRADED, self.handle_position_degraded)  # strategic exit
        await self.event_bus.subscribe(Events.PRICE_MONITOR_TRIGGER, self.handle_price_monitor)  # Tier 2
        await self.event_bus.subscribe(Events.APPROVAL_REQUIRED, self.handle_approval_required)

        # Start background agents
        asyncio.create_task(self.scheduler_agent.run())
        asyncio.create_task(self.telegram_agent.run())
        logger.info("Orchestrator startup complete. All agents initialized and scheduled.")

    # Event handlers
    async def handle_market_scan_trigger(self, event: Event):
        logger.info("Received MARKET_SCAN_TRIGGER")
        # Check market hours: if both US and HK closed, skip scan entirely
        from finance_service.utils.market_hours import is_us_market_open, is_hk_market_open
        if not (is_us_market_open() or is_hk_market_open()):
            logger.info("Markets closed (US and HK). Skipping market scan.")
            return
        # Trigger scanner with DataAgent for proper ranking
        report = await self.market_scanner_agent.run(data_agent=self.data_agent)
        if report.status == "success" or report.status == "opportunity":
            # Publish the payload as event data; include status in payload if needed
            event_data = report.payload.copy()
            event_data["status"] = report.status
            event_data["message"] = report.message
            await self.event_bus.publish(Event(event_type=Events.MARKET_SCANNED, data=event_data))

    async def handle_market_scanned(self, event: Event):
        logger.info(f"Orchestrator received MARKET_SCANNED event: {event.data}")
        # Event data is directly the payload from MarketScannerAgent, with possible additional fields
        symbols = event.data.get("symbols", [])
        rated_symbols = event.data.get("rated_symbols", [])
        logger.info(f"Processing {len(symbols)} symbols: {symbols}")

        # Send market scan summary to Telegram (always; includes details and ranked scores)
        if self.telegram_agent and self.telegram_agent.enabled:
            chat_id = self.telegram_agent.chat_id
            if chat_id:
                # Build detailed ranked summary with composite scores
                preview_symbols = rated_symbols[:50] if rated_symbols else []
                details = []
                
                # Pre-load symbol names from cache for the scan report
                _scan_name_cache: dict = {}
                from pathlib import Path as _Path
                _names_path = _Path(__file__).parent.parent / "memory" / "symbol_names.json"
                if _names_path.exists():
                    try:
                        import json as _json
                        _scan_name_cache = _json.loads(_names_path.read_text())
                    except Exception:
                        pass

                for item in preview_symbols:
                    sym = item.get("symbol", "")
                    score = item.get("rating", 0)
                    rank = item.get("rank", 0)
                    name = (_scan_name_cache.get(sym) or sym)[:20]
                    snap = await self._get_symbol_snapshot(sym)
                    if snap:
                        price = snap.get('price', 0)
                        details.append(f"{rank:2d}. {sym:<6}  {name:<20}  ${price:7.2f}  (score={score:.3f})")
                    else:
                        details.append(f"{rank:2d}. {sym:<6}  {name:<20}  N/A        (score={score:.3f})")
                
                # Header with ranking info
                total_count = len(symbols)
                header = f"📊 Daily Market Scan – Top {min(50, total_count)} Symbols (Ranked by Composite Score)\n"
                
                # Add footer with additional info
                footer = ""
                if len(symbols) > 50:
                    footer = f"\n... and {len(symbols) - 50} more symbols"
                
                message = header + "\n".join(details) + footer
                
                try:
                    await self.telegram_agent.send_message(chat_id=chat_id, message=message)
                    logger.info("Sent market scan summary to Telegram")
                except Exception as e:
                    logger.error(f"Failed to send market scan Telegram: {e}")
                # Also send top analysis summary in background (does not block)
                asyncio.create_task(self._send_top_analysis_summary(symbols))

        # Use 365-day lookback (1 year) to ensure enough trading days for SMA200
        from datetime import datetime, timedelta
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365)
        fetch_errors: list = []
        for symbol in symbols:
            # Data fetch (1d)
            data_report = await self.data_agent.run(symbol=symbol, interval="1d", start_date=start_date, end_date=end_date)
            if data_report.status != "success":
                logger.warning(f"Data fetch failed for {symbol}: {data_report.message}")
                fetch_errors.append(f"{symbol}: {data_report.message}")
                continue
            # News fetch
            news_report = await self.news_agent.run(symbol=symbol)
            # Analysis
            analysis_report = await self.analysis_agent.run(data_payload=data_report.payload, symbol=symbol)
            if analysis_report.status != "success":
                logger.warning(f"Analysis failed for {symbol}: {analysis_report.message}")
                continue
            # Strategy
            strategy_report = await self.strategy_agent.run(analysis_report.payload, symbol=symbol)
            if strategy_report.status != "success":
                logger.warning(f"Strategy failed for {symbol}: {strategy_report.message}")
                continue
            # Risk
            proposals = strategy_report.payload.get("proposals", [])
            if not proposals:
                continue
            proposal = proposals[0]  # best proposal
            risk_report = await self.risk_agent.run(proposal)
            if risk_report.payload.get("decision") == "APPROVED":
                # Guard: only execute during market hours
                from finance_service.utils.market_hours import is_us_market_open, is_hk_market_open
                if not (is_us_market_open() or is_hk_market_open()):
                    logger.warning(f"Skipping execution for {symbol}: markets closed")
                    continue
                # Send pre-execution Telegram notification before placing the trade
                if self.telegram_agent and self.telegram_agent.enabled:
                    try:
                        _snap = analysis_report.payload.get("indicators_snapshot") if analysis_report else None
                        _news_score = news_report.payload.get("sentiment_score") if (news_report and news_report.status == "success") else None
                        _news_cats = news_report.payload.get("catalysts") if (news_report and news_report.status == "success") else None
                        await self.telegram_agent.send_pre_execution_notification(
                            symbol=proposal.get("symbol", "?"),
                            action=proposal.get("action", "BUY"),
                            quantity=proposal.get("quantity") or 1.0,
                            target_price=proposal.get("target_price"),
                            stop_loss_price=proposal.get("stop_loss_price"),
                            confidence=proposal.get("confidence", 0.0),
                            rationale=proposal.get("rationale"),
                            indicators_snapshot=_snap,
                            news_sentiment=_news_score,
                            news_catalysts=_news_cats,
                        )
                    except Exception as _tg_err:
                        logger.warning(f"Pre-execution Telegram notification failed: {_tg_err}")
                exec_report = await self.execution_agent.run(risk_report)
                if exec_report.status == "success":
                    await self.event_bus.publish(Event(event_type=Events.TRADE_EXECUTED, data=exec_report.payload))
            # else: require approval, skip for now

        # Send error summary to Telegram if any data fetches failed
        if fetch_errors and self.health_agent:
            asyncio.create_task(
                self.health_agent.send_error_alert(
                    "Data Fetch Failures",
                    [f"yFinance fetch failed for {len(fetch_errors)} symbol(s):"] + fetch_errors[:10]
                )
            )

    async def handle_exit_check(self, event: Event):
        """Tier 3: Check held positions for exit conditions every 5 min."""
        logger.info("Received EXIT_CHECK_TRIGGER")
        if not self.portfolio_agent or not self.exit_agent:
            logger.warning("ExitAgent or PortfolioAgent not initialized, skipping exit check")
            return
        # Get current open positions from portfolio
        report = await self.portfolio_agent.get_detailed_portfolio_state()
        positions = report.payload.get("positions", []) if isinstance(report, AgentReport) else []
        if not positions:
            logger.info("No open positions to check for exits.")
            return
        # Filter positions to only those whose primary market is open
        from finance_service.utils.market_hours import is_us_market_open, is_hk_market_open
        us_open = is_us_market_open()
        hk_open = is_hk_market_open()
        filtered_positions = []
        for pos in positions:
            sym = pos.get("symbol", "")
            if sym.endswith('.HK'):
                if hk_open:
                    filtered_positions.append(pos)
            else:
                if us_open:
                    filtered_positions.append(pos)
        if not filtered_positions:
            logger.info("All positions in closed markets; skipping exit check.")
            return
        # Run exit agent with strategic re-analysis every other check
        report = await self.exit_agent.run(positions=filtered_positions, perform_strategy_check=True)
        if report.status == "success":
            exits = report.payload.get("exits", [])
            degraded = report.payload.get("degraded_positions", [])
            if exits:
                logger.info(f"ExitAgent found {len(exits)} exit signals")
                for exit_signal in exits:
                    await self.event_bus.publish(Event(event_type=Events.TRADE_EXECUTED, data=exit_signal))
            if degraded:
                logger.warning(f"ExitAgent found {len(degraded)} degraded positions")
                await self.event_bus.publish(Event(event_type=Events.POSITION_DEGRADED, data={"degraded": degraded}))

    async def handle_position_degraded(self, event: Event):
        """Execute a market-sell for every degraded position reported by ExitAgent."""
        degraded_list = event.data.get("degraded", [])
        if not degraded_list:
            return
        logger.info(f"handle_position_degraded: {len(degraded_list)} position(s) to exit")
        for record in degraded_list:
            symbol = record.get("symbol")
            quantity = record.get("quantity")
            current_price = record.get("current_price")
            reason = record.get("reason", "strategic degradation")
            if not symbol or not quantity:
                logger.warning(f"Degraded record missing symbol/quantity: {record}")
                continue
            logger.info(f"Executing strategic exit for {symbol}: {reason}")
            trade_proposal = {
                "symbol": symbol,
                "action": "SELL",
                "quantity": quantity,
                "target_price": current_price,
                "confidence": 1.0,
                "rationale": [reason],
            }
            try:
                # Wrap trade_proposal in an AgentReport payload to match ExecutionAgent.run() signature
                exit_approval_report = AgentReport(
                    agent_id="exit_agent",
                    status="success",
                    message="Exit signal validated",
                    payload={"trade_proposals": [trade_proposal]}
                )
                exec_report = await self.execution_agent.run(exit_approval_report)
                if exec_report and exec_report.status == "success":
                    await self.event_bus.publish(Event(event_type=Events.TRADE_EXECUTED, data=exec_report.payload))
                    logger.info(f"Strategic exit executed for {symbol}")
                else:
                    logger.warning(f"Strategic exit failed for {symbol}: {exec_report.message if exec_report else 'no report'}")
            except Exception as e:
                logger.error(f"Error executing strategic exit for {symbol}: {e}", exc_info=True)

    async def handle_price_monitor(self, event: Event):
        """Tier 2: Price refresh + optional intra-day entry evaluation for watchlist symbols."""
        logger.info("Received PRICE_MONITOR_TRIGGER")
        from finance_service.utils.market_hours import is_us_market_open, is_hk_market_open
        if not (is_us_market_open() or is_hk_market_open()):
            logger.info("Markets closed (US and HK). Skipping price monitor.")
            return

        # ── Refresh prices for watchlist + held positions ──────────────────
        held_symbols = set()
        if self.portfolio_agent:
            report = await self.portfolio_agent.get_detailed_portfolio_state()
            if isinstance(report, AgentReport) and isinstance(report.payload, dict):
                for pos in report.payload.get("positions", []):
                    sym = pos.get("symbol")
                    if sym:
                        held_symbols.add(sym)

        scan_report = await self.market_scanner_agent.refresh_watchlist_prices(
            data_agent=self.data_agent,
            held_symbols=held_symbols
        )
        if scan_report and scan_report.status == "success" and self.portfolio_agent:
            price_dict = {item["symbol"]: item["price"] for item in scan_report.payload.get("prices", [])}
            if price_dict:
                self.portfolio_agent.repository.update_position_prices(price_dict)
                logger.info(f"Applied {len(price_dict)} price updates to portfolio")
            logger.info(f"Price monitor complete: {scan_report.message}")

        # ── Intra-day entry evaluation (Tier 2 buy decisions) ───────────────
        intraday_entries = self.config_engine.get("strategy", "enable_intraday_entries", default=True)
        if not intraday_entries:
            logger.info("Intra-day entry evaluation disabled (strategy.enable_intraday_entries=false).")
            return

        watchlist_symbols = self.market_scanner_agent.get_watchlist_symbols()
        if not watchlist_symbols:
            logger.info("Watchlist empty — skipping intra-day entry evaluation.")
            return

        logger.info(f"[Tier2-Entry] Evaluating {len(watchlist_symbols)} watchlist symbols for intra-day entries")
        from datetime import datetime, timedelta
        end_date   = datetime.now().date()
        start_date = end_date - timedelta(days=365)

        for symbol in watchlist_symbols:
            _is_hk = symbol.endswith(".HK")
            if _is_hk and not is_hk_market_open():
                continue
            if not _is_hk and not is_us_market_open():
                continue

            try:
                data_report = await self.data_agent.run(
                    symbol=symbol, interval="1d", start_date=start_date, end_date=end_date
                )
                if data_report.status != "success":
                    logger.debug(f"[Tier2-Entry] Data fetch failed for {symbol}: {data_report.message}")
                    continue

                analysis_report = await self.analysis_agent.run(data_payload=data_report.payload, symbol=symbol)
                if analysis_report.status != "success":
                    logger.debug(f"[Tier2-Entry] Analysis failed for {symbol}: {analysis_report.message}")
                    continue

                strategy_report = await self.strategy_agent.run(analysis_report.payload, symbol=symbol)
                if strategy_report.status != "success":
                    logger.debug(f"[Tier2-Entry] Strategy failed for {symbol}: {strategy_report.message}")
                    continue

                proposals = strategy_report.payload.get("proposals", [])
                if not proposals:
                    continue
                proposal = proposals[0]
                if proposal.get("action") != "BUY":
                    continue

                risk_report = await self.risk_agent.run(proposal)
                if risk_report.payload.get("decision") != "APPROVED":
                    logger.info(f"[Tier2-Entry] {symbol}: risk not approved — {risk_report.payload.get('violations', [])}")
                    continue

                logger.info(f"[Tier2-Entry] {symbol}: APPROVED BUY — proceeding to execution")

                if not (is_us_market_open() or is_hk_market_open()):
                    logger.warning(f"[Tier2-Entry] Markets closed before execution of {symbol}, skipping")
                    continue

                exec_report = await self.execution_agent.run(risk_report)
                if exec_report and exec_report.status == "success":
                    await self.event_bus.publish(Event(event_type=Events.TRADE_EXECUTED, data=exec_report.payload))
                    logger.info(f"[Tier2-Entry] Trade executed for {symbol}")
                else:
                    logger.warning(f"[Tier2-Entry] Execution failed for {symbol}: {exec_report.message if exec_report else 'no report'}")

            except Exception as e:
                logger.error(f"[Tier2-Entry] Error evaluating {symbol}: {e}", exc_info=True)

    async def handle_data_fetched(self, event: Event):
        pass  # No action needed; downstream continues via event chain

    async def handle_news_fetched(self, event: Event):
        pass

    async def handle_analysis_complete(self, event: Event):
        pass

    async def handle_strategy_complete(self, event: Event):
        pass

    async def handle_risk_complete(self, event: Event):
        pass

    async def handle_approval_required(self, event: Event):
        """Handle APPROVAL_REQUIRED event - send telegram notification with approval buttons"""
        try:
            payload = event.data.get("payload", {})
            proposals = payload.get("trade_proposals", [])
            risk_assessments = payload.get("risk_assessments", [])
            
            if not proposals:
                logger.warning("APPROVAL_REQUIRED event has no trade proposals")
                return
            
            proposal = proposals[0]
            risk = risk_assessments[0] if risk_assessments else {}
            
            symbol = proposal.get("symbol", "?")
            action = proposal.get("action", "?") 
            quantity = proposal.get("quantity", 1)
            price = proposal.get("target_price", "?")
            confidence = risk.get("confidence", 0)
            
            # Create task_id for approval tracking
            task_id = f"{symbol}_{action}_{int(__import__('time').time())}"
            
            # Prepare approval details
            details = {
                "symbol": symbol,
                "quantity": quantity,
                "price": price,
                "confidence": confidence,
                "violations": risk.get("violations", [])
            }
            
            proposal_summary = f"{action} {quantity} shares of {symbol} @ ${price}"
            
            # Get approval gate and request approval
            approval_gate = get_approval_gate("telegram")
            if not approval_gate.enabled:
                logger.warning("Approval gate not enabled, executing trade anyway")
                await self.execute_trade_proposal(proposal, task_id)
                return
            
            # Send approval request with buttons and wait for response  
            approved, message = await approval_gate.request_approval(
                task_id=task_id,
                proposal_summary=proposal_summary,
                details=details
            )
            
            if approved:
                logger.info(f"Trade {task_id} approved: {message}")
                # Execute the trade
                await self.execute_trade_proposal(proposal, task_id)
            else:
                logger.info(f"Trade {task_id} rejected: {message}")
                await self.telegram_agent.send_message(f"❌ Trade {symbol} {action} cancelled by user")
                
        except Exception as e:
            logger.error(f"Error handling approval required: {e}", exc_info=True)
    
    async def execute_trade_proposal(self, proposal: Dict[str, Any], task_id: str):
        """Execute a trade proposal after approval"""
        try:
            from datetime import datetime
            
            execution_result = {
                "trade_id": task_id,
                "symbol": proposal.get("symbol"),
                "action": proposal.get("action"),
                "quantity": proposal.get("quantity", 1.0),
                "filled_price": proposal.get("target_price"),
                "status": "FILLED",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Send execution notification
            await self.telegram_agent.send_message(
                f"✅ Trade Executed: {proposal.get('action')} {proposal.get('quantity')} {proposal.get('symbol')} @ ${proposal.get('target_price')}"
            )
            
            # Publish trade executed event
            await self.event_bus.publish(__import__('finance_service.core.event_bus', fromlist=['Event']).Event(
                event_type=__import__('finance_service.core.event_bus', fromlist=['Events']).Events.TRADE_EXECUTED,
                data={"trade_info": execution_result}
            ))
            
            logger.info(f"Trade {task_id} execution completed")
        except Exception as e:
            logger.error(f"Error executing trade proposal: {e}", exc_info=True)


    async def handle_trade_executed(self, event: Event):
        # PortfolioAgent handles trade updates
        await self.portfolio_agent.handle_trade_executed(event.data)
        # HealthAgent sends notification
        await self.health_agent.run(event_type=Events.TRADE_EXECUTED, payload=event.data)

    async def handle_get_portfolio_state(self, event: Event):
        # Usually from Telegram /portfolio command
        report = await self.portfolio_agent.get_detailed_portfolio_state(event.data.get("chat_id"))
        # Could reply directly via Telegram if chat_id present
        if event.data.get("chat_id") and self.telegram_agent and self.telegram_agent.enabled:
            await self.telegram_agent.send_message(chat_id=event.data["chat_id"], message=str(report.payload))

    async def handle_get_system_status(self, event: Event):
        report = await self.health_agent.get_health_status(payload=event.data)
        if event.data.get("chat_id") and self.telegram_agent and self.telegram_agent.enabled:
            await self.telegram_agent.send_message(chat_id=event.data["chat_id"], message=str(report.payload))

    async def handle_schedule(self, event: Event):
        # Route to HealthAgent for periodic health check and daily summary
        await self.health_agent.run(event_type=Events.SCHEDULE, payload={})

    # Helper methods
    async def _get_symbol_snapshot(self, symbol: str) -> Optional[Dict]:
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="2d")
            if hist.empty or len(hist) < 1:
                return None
            last = hist.iloc[-1]
            prev_close = hist.iloc[-2]["Close"] if len(hist) >= 2 else last["Close"]
            close = last["Close"]
            change = ((close - prev_close) / prev_close) * 100 if prev_close else None
            volume = last.get("Volume")
            return {
                "symbol": symbol,
                "price": float(close),
                "change": float(change) if change is not None else None,
                "volume": int(volume) if volume is not None else None
            }
        except Exception as e:
            logger.debug(f"Snapshot fetch failed for {symbol}: {e}")
            return None

    async def _send_top_analysis_summary(self, symbols: List[str]):
        symbols_to_check = symbols[:20]
        results = []
        for sym in symbols_to_check:
            try:
                data_report = await self.data_agent.run(symbol=sym, interval="1d", start_date=None, end_date=None, emit_events=False)
                if data_report.status != "success" or "dataframe" not in data_report.payload:
                    continue
                df = data_report.payload["dataframe"]
                analysis_report = await self.analysis_agent.run(data_payload=df, symbol=sym)
                if analysis_report.status != "success":
                    continue
                strategy_report = await self.strategy_agent.run(analysis_report.payload, symbol=sym)
                if strategy_report.status != "success":
                    continue
                proposals = strategy_report.payload.get("proposals", [])
                if not proposals:
                    continue
                prop = proposals[0]
                price = prop.get("price") or self._get_latest_price_from_df(df)
                results.append({
                    "symbol": sym,
                    "action": prop.get("action", "WAIT"),
                    "confidence": prop.get("confidence", 0.0),
                    "price": price
                })
            except Exception as e:
                logger.debug(f"Quick analysis skipped for {sym}: {e}")
                continue

        results.sort(key=lambda x: (0 if x["action"] == "BUY" else 1, -x.get("confidence", 0)))
        top10 = results[:10]
        if not top10:
            return

        lines = [f"🏆 Top {len(top10)} Candidates (quick analysis)"]
        for r in top10:
            lines.append(f"• {r['symbol']}: {r['action']} @ ${r['price']:.2f} (conf: {r['confidence']:.2f})")
        message = "\n".join(lines)

        if self.telegram_agent and self.telegram_agent.enabled:
            chat_id = self.telegram_agent.chat_id
            if chat_id:
                try:
                    await self.telegram_agent.send_message(chat_id=chat_id, message=message)
                    logger.info("Sent top analysis summary to Telegram")
                except Exception as e:
                    logger.error(f"Failed to send top analysis Telegram: {e}")

    def _get_latest_price_from_df(self, df) -> float:
        try:
            if hasattr(df, 'iloc') and len(df) > 0:
                return float(df.iloc[-1]["Close"])
        except Exception:
            pass
        return 0.0

def _sanitize_floats(obj):
    """Recursively replace NaN/Inf with None for valid JSON serialization."""
    import math
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_floats(v) for v in obj]
    return obj


def create_app():
    """Factory to create Quart app."""
    app = Quart(__name__)
    _orchestrator = None  # will be set on startup

    @app.route("/health")
    async def health():
        return {"status": "ok"}


    @app.route("/api/market/status")
    async def market_status():
        """Return current market status."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from finance_service.utils.market_hours import is_us_market_open, is_hk_market_open
        
        hk_time = datetime.now(ZoneInfo("Asia/Hong_Kong"))
        us_open = is_us_market_open()
        hk_open = is_hk_market_open()
        
        hk_time_str = hk_time.strftime("%H:%M UTC+8")
        us_time = datetime.now(ZoneInfo("America/New_York"))
        us_time_str = us_time.strftime("%H:%M EST")
        
        if us_open or hk_open:
            market_status = "OPEN"
            status_text = "US & HK" if (us_open and hk_open) else ("US" if us_open else "HK")
            message = f"Market: {hk_time_str} – {status_text} market{'s' if status_text != 'US' else ''} OPEN"
        else:
            message = f"Market: {hk_time_str} – Both HK and US markets CLOSED"
        
        return jsonify({
            "status": "success",
            "market_status": message,
            "us_open": us_open,
            "hk_open": hk_open,
            "hk_time": hk_time_str,
            "us_time": us_time_str,
            "timestamp": hk_time.isoformat()
        })

    @app.route("/portfolio")
    async def get_portfolio():
        global _orchestrator
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        report = await _orchestrator.portfolio_agent.get_detailed_portfolio_state()
        return jsonify(report.payload)

    @app.route("/portfolio/state")
    async def get_portfolio_state():
        global _orchestrator
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        report = await _orchestrator.portfolio_agent.get_detailed_portfolio_state()
        return jsonify(report.payload)

    @app.route("/trigger")
    async def trigger():
        global _orchestrator
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        trigger_type = request.args.get("trigger_type")
        if trigger_type == "market-scan":
            await _orchestrator.event_bus.publish(Event(event_type=Events.MARKET_SCAN_TRIGGER, data={}))
            return jsonify({"status": "queued", "trigger": "market_scan"})
        elif trigger_type == "hourly-report" or trigger_type == "status-report":
            await _orchestrator.event_bus.publish(Event(event_type=Events.GET_SYSTEM_STATUS, data={}))
            return jsonify({"status": "queued", "trigger": "hourly_report"})
        elif trigger_type == "price-monitor":
            await _orchestrator.event_bus.publish(Event(event_type=Events.PRICE_MONITOR_TRIGGER, data={}))
            return jsonify({"status": "queued", "trigger": "price_monitor"})
        else:
            return jsonify({"error": "unknown trigger_type"}), 400


    @app.route("/api/report/hourly", methods=["GET", "POST"])
    async def api_report_hourly():
        """Generate and send hourly portfolio report via Telegram."""
        global _orchestrator
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        
        try:
            # Get portfolio state
            portfolio_report = await _orchestrator.portfolio_agent.get_detailed_portfolio_state()
            if portfolio_report.status != "success":
                return jsonify({"error": "Failed to get portfolio state"}), 500
            
            payload = portfolio_report.payload
            metrics = payload.get("equity_metrics", {})
            positions = payload.get("positions", [])
            
            # Generate report message
            report_lines = ["📊 *Hourly Portfolio Report*\n"]
            report_lines.append(f"💰 *Summary*")
            report_lines.append(f"Equity: ${metrics.get('total_equity', 0):,.0f}")
            report_lines.append(f"Return: {metrics.get('total_return_pct', 0):.2f}%")
            report_lines.append(f"P&L: ${metrics.get('unrealized_pnl', 0):,.0f}")
            report_lines.append(f"Positions: {len(positions)}")
            report_lines.append(f"Drawdown: {metrics.get('drawdown_pct', 0):.2f}%\n")
            
            # Top 5 gainers
            gainers = sorted([p for p in positions if p.get('unrealized_pnl_pct', 0) > 0], 
                           key=lambda x: x.get('unrealized_pnl_pct', 0), reverse=True)[:5]
            if gainers:
                report_lines.append("📈 *Top Gainers*")
                for pos in gainers:
                    report_lines.append(f"{pos.get('symbol', '?')}: +{pos.get('unrealized_pnl_pct', 0):.2f}%")
                report_lines.append("")
            
            # Top 5 losers
            losers = sorted([p for p in positions if p.get('unrealized_pnl_pct', 0) < 0], 
                          key=lambda x: x.get('unrealized_pnl_pct', 0))[:5]
            if losers:
                report_lines.append("📉 *Top Losers*")
                for pos in losers:
                    report_lines.append(f"{pos.get('symbol', '?')}: {pos.get('unrealized_pnl_pct', 0):.2f}%")
            
            message = "\n".join(report_lines)
            
            # Send via Telegram if available
            if _orchestrator.telegram_agent and _orchestrator.telegram_agent.enabled:
                chat_id = _orchestrator.telegram_agent.chat_id
                if chat_id:
                    await _orchestrator.telegram_agent.send_message(chat_id=chat_id, message=message)
                    return jsonify({"status": "success", "message": "Hourly report sent via Telegram", "payload": payload})
            
            return jsonify({"status": "success", "message": "Hourly report generated (Telegram not configured)", "payload": payload})
        except Exception as e:
            logger.exception("Error generating hourly report")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/dashboard/overview")
    async def api_dashboard_overview():
        global _orchestrator
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        report = await _orchestrator.portfolio_agent.get_detailed_portfolio_state()
        if report.status != "success":
            return jsonify({"error": report.message}), 500
        p = report.payload
        overview = p.get("overview", {})
        equity = p.get("equity_metrics", {})
        # Merge equity metrics into overview for dashboard consumption
        overview.update({
            "total_equity": equity.get("total_equity"),
            "unrealized_pnl": equity.get("unrealized_pnl"),
            "realized_pnl": equity.get("realized_pnl"),
            "total_return_pct": equity.get("total_return_pct"),
            "drawdown_pct": equity.get("drawdown_pct"),
            "win_rate": equity.get("win_rate"),
            "last_updated": p.get("last_updated"),
        })
        return jsonify(_sanitize_floats({"status": "success", "data": overview}))

    @app.route("/api/dashboard/positions")
    async def api_dashboard_positions():
        global _orchestrator
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        report = await _orchestrator.portfolio_agent.get_detailed_portfolio_state()
        if report.status != "success":
            return jsonify({"error": report.message}), 500
        positions = report.payload.get("positions", [])
        return jsonify(_sanitize_floats({"status": "success", "data": positions}))

    @app.route("/api/dashboard/performance")
    async def api_dashboard_performance():
        global _orchestrator
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        report = await _orchestrator.portfolio_agent.get_detailed_portfolio_state()
        if report.status != "success":
            return jsonify({"error": report.message}), 500
        metrics = report.payload.get("equity_metrics", {})
        return jsonify(_sanitize_floats({"status": "success", "data": metrics}))

    @app.route("/api/dashboard/risk")
    async def api_dashboard_risk():
        global _orchestrator
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        report = await _orchestrator.portfolio_agent.get_detailed_portfolio_state()
        if report.status != "success":
            return jsonify({"error": report.message}), 500
        metrics = report.payload.get("equity_metrics", {})
        risk_data = {
            "drawdown_pct": metrics.get("drawdown_pct"),
            "max_drawdown_pct": metrics.get("max_drawdown_pct"),
            "total_return_pct": metrics.get("total_return_pct"),
            "win_rate": metrics.get("win_rate"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "total_equity": metrics.get("total_equity"),
        }
        return jsonify(_sanitize_floats({"status": "success", "data": risk_data}))

    @app.route("/api/dashboard/alerts")
    async def api_dashboard_alerts():
        global _orchestrator
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        try:
            health = await _orchestrator.health_agent.get_health_status()
            raw_alerts = health.get("alerts", [])
            alerts = [{"message": a, "level": "warning"} for a in raw_alerts]
        except Exception:
            alerts = []
        return jsonify(_sanitize_floats({"status": "success", "data": alerts}))

    @app.route("/api/dashboard/trades")
    async def api_dashboard_trades():
        global _orchestrator
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        try:
            limit = int(request.args.get("limit", 50))
        except (ValueError, TypeError):
            limit = 50
        report = await _orchestrator.portfolio_agent.get_detailed_portfolio_state()
        if report.status != "success":
            return jsonify({"error": report.message}), 500
        trades = report.payload.get("trades", [])
        return jsonify(_sanitize_floats({"status": "success", "data": trades[:limit]}))

    @app.route("/api/system/pause", methods=["POST"])
    async def api_system_pause():
        global _orchestrator, _system_paused
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        _system_paused = True
        if _orchestrator.scheduler_agent:
            await _orchestrator.scheduler_agent.stop()
        return jsonify({"status": "success", "message": "Trading paused"})

    @app.route("/api/system/resume", methods=["POST"])
    async def api_system_resume():
        global _orchestrator, _system_paused
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        _system_paused = False
        if _orchestrator.scheduler_agent:
            asyncio.create_task(_orchestrator.scheduler_agent.run())
        return jsonify({"status": "success", "message": "Trading resumed"})

    @app.route("/api/system/status")
    async def api_system_status():
        global _orchestrator, _system_paused
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        try:
            health = await _orchestrator.health_agent.get_health_status()
        except Exception as e:
            health = {"error": str(e)}
        data = {
            "is_running": True,
            "is_paused": _system_paused,
            "health": health,
            "agents": {
                "scheduler": _orchestrator.scheduler_agent is not None,
                "portfolio": _orchestrator.portfolio_agent is not None,
                "health": _orchestrator.health_agent is not None,
            }
        }
        return jsonify(_sanitize_floats({"status": "success", "data": data}))

    @app.route("/portfolio/performance")
    async def portfolio_performance():
        """Return portfolio performance metrics (alias for /api/dashboard/performance)."""
        global _orchestrator
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        report = await _orchestrator.portfolio_agent.get_detailed_portfolio_state()
        if report.status != "success":
            return jsonify({"error": report.message}), 500
        metrics = report.payload.get("equity_metrics", {})
        return jsonify(_sanitize_floats({"status": "success", "data": metrics}))

    @app.route("/api/market/watchlist")
    async def api_market_watchlist():
        """Return the current market scanner watchlist with ratings and latest prices (top 10)."""
        global _orchestrator
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        try:
            scanner = _orchestrator.market_scanner_agent
            watchlist = scanner.get_watchlist()  # [{symbol, theme, rating, rank}, ...]
            if not watchlist:
                return jsonify({"status": "success", "data": [], "message": "Watchlist empty"})
            # Sort by rank and take top 10
            watchlist = sorted(watchlist, key=lambda x: x.get("rank", 9999))[:10]
            symbols = [item["symbol"] for item in watchlist]
            # Fetch latest prices directly via yfinance (simple and reliable)
            import yfinance as yf
            prices = {}
            for sym in symbols:
                try:
                    ticker = yf.Ticker(sym)
                    # Try to get a recent quote; use fast info if available
                    info = ticker.info
                    price = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('previousClose')
                    if price is None:
                        # Fallback to 1-day history
                        hist = ticker.history(period="1d")
                        if not hist.empty:
                            price = hist['Close'].iloc[-1]
                    prices[sym] = price
                except Exception as e:
                    logger.warning(f"yfinance failed for {sym}: {e}")
                    prices[sym] = None
            # Combine
            result = []
            for item in watchlist:
                sym = item["symbol"]
                result.append({
                    "symbol": sym,
                    "theme": item.get("theme"),
                    "rating": item.get("rating"),
                    "rank": item.get("rank"),
                    "current_price": prices.get(sym)
                })
            return jsonify(_sanitize_floats({"status": "success", "data": result}))
        except Exception as e:
            logger.exception("Error fetching watchlist")
            return jsonify({"error": str(e)}), 500

    @app.route("/admin/trigger_market_scan", methods=["POST"])
    async def admin_trigger_market_scan():
        """Admin endpoint to manually trigger a market scan."""
        global _orchestrator
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        try:
            await _orchestrator.scheduler_agent.handle_market_scan_trigger()
            return jsonify({"status": "success", "message": "Market scan triggered"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app

# Create the Quart app instance at module level for the launcher to use
app = create_app()

# Separate function for launcher to initialize orchestrator before app starts
async def startup_orchestrator():
    """Initialize orchestrator and start background agents. Called by launcher."""
    global _orchestrator
    logger.info("Creating orchestrator...")
    _orchestrator = MainOrchestratorAgent(config={})
    await _orchestrator.startup_orchestrator()
    logger.info("Orchestrator started.")

async def run():
    config = Config()
    app = create_app()
    await serve(app, config)

if __name__ == "__main__":
    asyncio.run(run())
