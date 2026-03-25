import logging
import json # Added for JSON formatting in Telegram messages
from typing import Dict, Any, Optional, List
import asyncio
from datetime import datetime
from flask import Flask, request, jsonify
import pandas as pd  # Added for DataFrame operations in quote endpoint
from zoneinfo import ZoneInfo

# Temporary storage for Flask-initiated async responses
flask_response_queues: Dict[str, asyncio.Queue] = {}

# Global orchestrator (initialized at startup, read-only thereafter)
_orchestrator: Optional['MainOrchestratorAgent'] = None
_startup_done: bool = False

def is_us_market_open() -> bool:
    """Check if US stock market is currently open (9:30 AM - 4:00 PM ET, Mon-Fri)."""
    try:
        eastern = ZoneInfo('US/Eastern')
        now = datetime.now(eastern)
        # Check weekday (Mon=0, Fri=4)
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        # Check time range (9:30 AM to 4:00 PM)
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        return market_open <= now <= market_close
    except Exception as e:
        logging.getLogger(__name__).warning(f"Error checking market hours: {e}")
        return False

def is_hk_market_open() -> bool:
    """Check if Hong Kong stock market is currently open (9:30 AM - 4:00 PM HKT, Mon-Fri)."""
    try:
        hkt = ZoneInfo('Asia/Hong_Kong')
        now = datetime.now(hkt)
        if now.weekday() >= 5:  # Weekend
            return False
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        return market_open <= now <= market_close
    except Exception as e:
        logging.getLogger(__name__).warning(f"Error checking HK market hours: {e}")
        return False

def get_orchestrator() -> 'MainOrchestratorAgent':
    """Return the initialized orchestrator. Must be called after service startup."""
    global _orchestrator
    if _orchestrator is None:
        raise RuntimeError("Orchestrator not initialized. Service is still starting up.")
    return _orchestrator

from .core.config import Config
from .core.logging import setup_logger, RunLogger
from .core.event_bus import get_event_bus, Event, Events
from .core.yaml_config import YAMLConfigEngine

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.agents.data_agent import DataAgent
from finance_service.agents.market_scanner_agent import MarketScannerAgent
from finance_service.agents.news_agent import NewsAgent
from finance_service.agents.analysis_agent import AnalysisAgent
from finance_service.agents.strategy_agent import StrategyAgent
from finance_service.agents.risk_agent import RiskAgent
from finance_service.agents.execution_agent import ExecutionAgent
from finance_service.agents.learning_agent import LearningAgent
from finance_service.agents.telegram_agent import TelegramAgent
from finance_service.agents.scheduler_agent import SchedulerAgent
from finance_service.agents.portfolio_agent import PortfolioAgent
from finance_service.agents.health_agent import HealthAgent  # New import

logger = setup_logger(__name__)
run_logger = RunLogger()

app = Flask(__name__)

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({"service": "finance", "status": "ok"}), 200

class DummyTelegramAgent:
    """Fallback no-op Telegram agent when real one can't be initialized."""
    
    def __getattr__(self, name):
        async def noop(*args, **kwargs):
            logger.debug(f"DummyTelegramAgent.{name} called (no-op)")
            return None
        return noop

class MainOrchestratorAgent(Agent):
    """Main Orchestrator Agent - Coordinates all specialized agents in the trading system."""

    @property
    def agent_id(self) -> str:
        return "main_orchestrator_agent"

    @property
    def goal(self) -> str:
        return "Orchestrate the end-to-end trading workflow, from market scanning to trade execution and learning."
    
    def __init__(self, config_engine: YAMLConfigEngine):
        self.config_engine = config_engine
        self.event_bus = None # Initialized in async initialize_orchestrator
        self.pending_news_reports: Dict[str, AgentReport] = {}
        self.pending_analysis_reports: Dict[str, AgentReport] = {}
        logger.info("MainOrchestratorAgent initializing...")

        # Initialize agents that require YAMLConfigEngine
        self.market_scanner_agent = MarketScannerAgent(config_engine)
        self.data_agent = DataAgent(config_engine)
        self.news_agent = NewsAgent(config_engine)
        self.analysis_agent = AnalysisAgent({})  # AnalysisAgent uses periods_config dict, not YAML config yet
        self.strategy_agent = StrategyAgent(config_engine)  # Needs rules from YAML
        
        # Extract risk config dict from finance YAML for RiskAgent
        risk_config = config_engine.get("finance", "risk", default={})
        self.risk_agent = RiskAgent(risk_config)
        
        # ExecutionAgent can use empty config or simple dict
        execution_config = config_engine.get("finance", "execution", default={})
        self.execution_agent = ExecutionAgent(execution_config)
        self.learning_agent = LearningAgent({})
        # Initialize TelegramAgent with compatibility handling
        try:
            self.telegram_agent = TelegramAgent({})
        except Exception as e:
            logger.warning(f"TelegramAgent initialization failed: {e}. Using dummy no-op agent.")
            self.telegram_agent = DummyTelegramAgent()
        self.scheduler_agent = SchedulerAgent({})
        self.portfolio_agent = PortfolioAgent({}, data_agent=self.data_agent)
        self.health_agent = HealthAgent(config_engine)  # Health monitoring agent

        # Event handlers will be registered in initialize_orchestrator after event_bus is awaited

    async def run(self):
        logger.info(f"{self.agent_id} starting run cycle.")
        # Start scheduler in background
        asyncio.create_task(self.scheduler_agent.run())
        # Initial trigger for market scan
        await self.market_scanner_agent.run()
        logger.info(f"{self.agent_id} finished initial run cycle.")

    async def handle_market_scanned(self, event: Event):
        logger.info(f"Orchestrator received MARKET_SCANNED event: {event.data}")
        # event.data is an AgentReport dict; symbols are in payload["symbols"]
        payload = event.data.get("payload", {})
        symbols = payload.get("symbols", [])
        logger.info(f"Processing {len(symbols)} symbols: {symbols}")
        # Use 365-day lookback (1 year) to ensure enough trading days for SMA200
        from datetime import datetime, timedelta
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365)
        for symbol in symbols:
            # Determine market and check if open
            market = None
            market_open = False
            if symbol.endswith('.HK'):
                market = 'HK'
                market_open = is_hk_market_open()
            else:
                market = 'US'
                market_open = is_us_market_open()
            if not market_open:
                logger.info(f"Market {market} is closed. Skipping {symbol}.")
                continue
            logger.info(f"Fetching data for {symbol} ({start_date} to {end_date}) [Market: {market}]")
            try:
                result = await self.data_agent.run(
                    symbol=symbol,
                    interval="1d",
                    start_date=str(start_date),
                    end_date=str(end_date),
                    use_cache=False  # Disable cache to ensure fresh data
                )
                logger.info(f"Data fetch for {symbol} completed: {result.status}")
            except Exception as e:
                logger.error(f"Error fetching data for {symbol}: {e}", exc_info=True)
    
    async def handle_data_fetch_complete(self, event: Event):
        logger.info(f"Orchestrator received DATA_FETCH_COMPLETE event: {event.data}")
        try:
            symbol = event.data.get("symbol")
            data_payload = event.data.get("dataframe") # dict of records
            logger.info(f"DATA_FETCH_COMPLETE for symbol={symbol}, dataframe type: {type(data_payload)}, size: {len(data_payload) if data_payload else 0}")
            if data_payload is not None and symbol is not None:
                logger.info(f"Calling news_agent.run({symbol})")
                await self.news_agent.run(symbol=symbol)
                logger.info(f"News done, calling analysis_agent.run with full payload")
                # Pass the entire event.data payload, which includes 'dataframe' and 'fundamentals'
                analysis_report = await self.analysis_agent.run(data_payload=event.data, symbol=symbol)
                logger.info(f"Analysis agent run completed for {symbol}, status: {analysis_report.status}")
                # Note: AnalysisAgent already publishes ANALYSIS_COMPLETE event internally, no need to duplicate here
            else:
                logger.warning(f"DATA_FETCH_COMPLETE missing symbol or dataframe: symbol={symbol}, has_dataframe={data_payload is not None}")
        except Exception as e:
            logger.error(f"Error in handle_data_fetch_complete: {e}", exc_info=True)
            raise

    async def handle_news_fetch_complete(self, event: Event):
        logger.info(f"Orchestrator received NEWS_FETCH_COMPLETE event: {event.data}")
        news_report = AgentReport(**event.data) # Reconstruct AgentReport
        symbol = news_report.payload.get("symbol")
        logger.info(f"News fetch complete for symbol={symbol}, about to call _try_trigger")
        if symbol:
            self.pending_news_reports[symbol] = news_report
            await self._try_trigger_strategy_agent(symbol)

    async def handle_analysis_complete(self, event: Event):
        logger.info(f"Orchestrator received ANALYSIS_COMPLETE event: {event.data}")
        # event.data is a dict containing 'indicators_snapshot' key
        snapshot = event.data.get('indicators_snapshot')
        if not snapshot:
            logger.error(f"ANALYSIS_COMPLETE event missing indicators_snapshot: {event.data}")
            return
        symbol = snapshot.symbol
        logger.info(f"Analysis complete for symbol={symbol}, about to call _try_trigger")
        if symbol:
            # Wrap in AgentReport with payload containing the snapshot under 'indicators_snapshot' key
            analysis_report = AgentReport(
                agent_id="analysis_agent",
                status="success",
                message=f"Analysis complete for {symbol}",
                payload={"indicators_snapshot": snapshot}
            )
            self.pending_analysis_reports[symbol] = analysis_report
            await self._try_trigger_strategy_agent(symbol)
        else:
            logger.error(f"ANALYSIS_COMPLETE event missing symbol in snapshot: {snapshot}")

    async def _try_trigger_strategy_agent(self, symbol: str):
        logger.info(f">>> _try_trigger_strategy_agent called for symbol={symbol}")
        logger.info(f"Pending news keys: {list(self.pending_news_reports.keys())}")
        logger.info(f"Pending analysis keys: {list(self.pending_analysis_reports.keys())}")
        news_report = self.pending_news_reports.get(symbol)
        analysis_report = self.pending_analysis_reports.get(symbol)
        logger.info(f"_try_trigger: news_present={news_report is not None}, analysis_present={analysis_report is not None}")
        if news_report and analysis_report:
            logger.info(f"Both news and analysis reports available for {symbol}. Triggering StrategyAgent.")
            try:
                result = await self.strategy_agent.run(indicators_report=analysis_report, news_report=news_report)
                logger.info(f"StrategyAgent.run returned: {result}")
            except Exception as e:
                logger.error(f"Error in strategy_agent.run: {e}", exc_info=True)
            # Clear pending reports after triggering strategy agent
            del self.pending_news_reports[symbol]
            del self.pending_analysis_reports[symbol]
            # If strategy generated trade proposals, publish event for RiskAgent
            if result and result.status == "success" and result.payload and result.payload.get("proposals"):
                proposals = result.payload["proposals"]
                logger.info(f"Strategy generated {len(proposals)} trade proposal(s). Publishing TRADE_PROPOSAL_GENERATED event.")
                # Convert AgentReport to dict for event payload
                from dataclasses import asdict
                await self.event_bus.publish(Event(
                    event_type=Events.TRADE_PROPOSAL_GENERATED,
                    data=asdict(result)
                ))
            else:
                logger.info(f"No trade proposals generated for {symbol}.")
        else:
            logger.warning(f"_try_trigger: missing one or both reports for {symbol}")
            # Log which one is missing
            if not news_report:
                logger.warning(f"  Missing news report for {symbol}")
            if not analysis_report:
                logger.warning(f"  Missing analysis report for {symbol}")
        logger.info(f"<<< _try_trigger_strategy_agent done for {symbol}")

    async def handle_trade_proposal_generated(self, event: Event):
        logger.info(f">>> HANDLER: handle_trade_proposal_generated ENTERED")
        logger.info(f"Orchestrator received TRADE_PROPOSAL_GENERATED event: {event.data}")
        try:
            trade_proposal_report = AgentReport(**event.data)
            logger.info(f"Calling risk_agent.run()...")
            result = await self.risk_agent.run(trade_proposal_report=trade_proposal_report)
            logger.info(f"<<< risk_agent.run() returned: {result}")
        except Exception as e:
            logger.error(f"<<< ERROR in handle_trade_proposal_generated: {e}", exc_info=True)
            raise

    async def handle_risk_check_complete(self, event: Event):
        logger.info(f"Orchestrator received RISK_CHECK_COMPLETE event: {event.data}")
        risk_check_report = AgentReport(**event.data)
        # RiskAgent payload has 'any_approval_required' and 'all_passed' flags
        any_approval_required = risk_check_report.payload.get("any_approval_required", False)
        all_passed = risk_check_report.payload.get("all_passed", False)
        
        if all_passed and not any_approval_required:
            # If no approval is required and all checks passed, proceed to execution
            # Pass the full risk_check_report as the approval_report (it contains both trade_proposals and risk_assessments)
            logger.info("Risk check passed, proceeding to execution.")
            await self.execution_agent.run(approval_report=risk_check_report)
        else:
            logger.info(f"Approval required for trade proposal (all_passed={all_passed}, any_approval_required={any_approval_required}). Skipping automatic execution.")

    async def handle_approval_required(self, event: Event):
        logger.info(f"Orchestrator received APPROVAL_REQUIRED event: {event.data}")
        approval_request_report = AgentReport(**event.data)
        # Delegate to a dedicated approval manager or directly to TelegramAgent for now
        # await self.telegram_agent.request_approval(approval_request_report.payload)
        logger.info("Approval request sent via Telegram Agent (mocked).")
        # For now, simulate immediate approval for testing
        await self.event_bus.publish(Event(event_type=Events.TRADE_EXECUTED, data={"trade_proposal": approval_request_report.payload.get("trade_proposal"), "status": "approved_mock"}))

    async def handle_trade_executed(self, event: Event):
        logger.info(f"Orchestrator received TRADE_EXECUTED event: {event.data}")
        execution_report = AgentReport(**event.data)
        
        # Extract execution_result from payload
        execution_result = execution_report.payload.get("execution_result", {})
        logger.info(f"Extracted execution_result: {execution_result}")
        
        if not execution_result:
            logger.warning("No execution_result found in payload")
            return
        
        logger.info(f"Calling portfolio_agent.run with execution_result: symbol={execution_result.get('symbol')} action={execution_result.get('action')}")
        try:
            # Update portfolio with trade details
            port_report = await self.portfolio_agent.run(
                event_type=Events.TRADE_EXECUTED,
                payload=execution_result
            )
            logger.info(f"PortfolioAgent.run returned: status={port_report.status}, message={port_report.message}")
        except Exception as e:
            logger.error(f"Error calling portfolio_agent.run: {e}", exc_info=True)
        
        logger.info("Portfolio update attempt completed")
        
        # Let the learning agent process the full execution report
        await self.learning_agent.run(execution_report=execution_report)
        
        # Send trade notification via health agent (to Telegram)
        try:
            await self.health_agent.run(event_type=Events.TRADE_EXECUTED, payload=execution_result)
        except Exception as e:
            logger.error(f"Error in health_agent trade notification: {e}", exc_info=True)
        
        logger.info("Trade execution handling complete")
        
        # Then let the learning agent process the full execution report
        await self.learning_agent.run(execution_report=execution_report)

    async def handle_learning_complete(self, event: Event):
        logger.info(f"Orchestrator received LEARNING_COMPLETE event: {event.data}")
        # Learning agent has completed its cycle, possibly publish feedback

    async def handle_market_scan_trigger(self, event: Event):
        logger.info("!!! HANDLER ENTERED !!!")
        logger.info(f">>> HANDLER START: handle_market_scan_trigger with event {event}")
        logger.info(f"Orchestrator received MARKET_SCAN_TRIGGER event: {event.data}")
        
        # Check if at least one market (US or HK) is open
        us_open = is_us_market_open()
        hk_open = is_hk_market_open()
        if not (us_open or hk_open):
            logger.info("Both US and HK markets are closed. Skipping market scan.")
            return
        logger.info(f"Market status: US={us_open}, HK={hk_open}. Proceeding with market scan.")
        
        try:
            logger.info("Calling market_scanner_agent.run()...")
            result = await self.market_scanner_agent.run()
            logger.info(f"<<< HANDLER DONE: market_scanner_agent.run() returned: {result}")
            # Publish MARKET_SCANNED event to continue pipeline
            await self.event_bus.publish(
                Event(event_type=Events.MARKET_SCANNED, data={"payload": result.payload, "agent_id": result.agent_id, "status": result.status, "message": result.message})
            )
            logger.info("Published MARKET_SCANNED event")
        except Exception as e:
            logger.error(f"<<< HANDLER ERROR: Error in handle_market_scan_trigger: {e}", exc_info=True)
            raise

    async def handle_data_refresh_trigger(self, event: Event):
        logger.info(f"Orchestrator received DATA_REFRESH_TRIGGER event: {event.data}")
        # This handler needs to know *which* symbols to refresh.
        # For now, it could trigger a scan or use a predefined list.
        # A more robust solution might involve the DataAgent maintaining a "universe" to refresh.
        await self.data_agent.run(refresh_all=True) # Assuming DataAgent can handle "refresh_all"

    async def handle_daily_report_trigger(self, event: Event):
        logger.info("Orchestrator received DAILY_REPORT_TRIGGER event. Generating report...")
        # Get actual portfolio performance data from PortfolioAgent
        portfolio_report = await self.portfolio_agent.run(event_type=Events.GET_PORTFOLIO_STATE, payload={})
        if portfolio_report.status == "success":
            metrics = portfolio_report.payload.get("equity_metrics", {})
            message_text = f"**Daily Report - {datetime.utcnow().strftime("%Y-%m-%d")}**\n\n"
            message_text += f"**Total Equity:** ${metrics.get("total_equity", 0.0):,.2f}\n"
            message_text += f"**Daily P&L:** ${metrics.get("total_pnl", 0.0):,.2f}\n"
            message_text += f"**Total Return %:** {metrics.get("total_return_pct", 0.0):.2f}%\n"
            message_text += f"**Open Positions:** {portfolio_report.payload.get("overview", {}).get("position_count", 0)}\n"
            await self.telegram_agent.send_scheduled_report(report_data=metrics) # Pass metrics directly, TelegramAgent formats it
        else:
            logger.error(f"Failed to get portfolio state for daily report: {portfolio_report.message}")
            await self.telegram_agent.send_message(chat_id=self.telegram_agent.chat_id, message="Failed to generate daily report.")

    async def handle_get_system_status(self, event: Event):
        logger.info(f"Orchestrator received GET_SYSTEM_STATUS event: {event.data}. Preparing status report.")
        status_report = {
            "orchestrator": "running",
            "market_scanner": "idle",
            "data_agent": "ready",
            "news_agent": "ready",
            "analysis_agent": "ready",
            "strategy_agent": "ready",
            "risk_agent": "ready",
            "execution_agent": "ready",
            "learning_agent": "ready",
            "portfolio_agent": "ready", # New status
            "scheduler_agent": "running",
            "last_scan": datetime.utcnow().isoformat(),
            "active_tasks": len(asyncio.all_tasks()) - 1 # Exclude current task
        }
        response_chat_id = event.data.get("chat_id")
        if response_chat_id:
            await self.telegram_agent.send_message(
                chat_id=response_chat_id,
                message=f"System Status Report:\n```json\n{json.dumps(status_report, indent=2)}\n```"
            )


    async def handle_get_portfolio_state(self, event: Event):
        logger.info(f"Orchestrator received GET_PORTFOLIO_STATE event: {event.data}. Preparing portfolio report.")
        response_chat_id = event.data.get("chat_id") # Can be a Telegram chat_id or "flask_request"
        
        portfolio_report = await self.portfolio_agent.run(event_type=Events.GET_PORTFOLIO_STATE, payload={})

        if portfolio_report.status == "success":
            if response_chat_id == "flask_request":
                # Respond directly to the Flask endpoint
                request_id = event.data.get("request_id")
                if request_id in flask_response_queues:
                    await flask_response_queues[request_id].put(portfolio_report)
            elif response_chat_id:
                portfolio_state = portfolio_report.payload
                # Format the portfolio state for a human-readable Telegram message
                message_text = f"**Portfolio State - {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}**\n\n"
                message_text += f"**Total Equity:** ${portfolio_state.get("equity_metrics", {}).get("total_equity", 0.0):,.2f}\n"
                message_text += f"**Current Cash:** ${portfolio_state.get("equity_metrics", {}).get("current_cash", 0.0):,.2f}\n"
                message_text += f"**Total P&L:** ${portfolio_state.get("equity_metrics", {}).get("total_pnl", 0.0):,.2f}\n"
                message_text += f"**Positions ({len(portfolio_state.get("positions", []))}):**\n"
                for pos in portfolio_state.get("positions", [])[:5]: # Limit to 5 positions for brevity
                    message_text += f"  - {pos.get("symbol")} | Qty: {pos.get("quantity")} | Avg Cost: ${pos.get("avg_cost"):,.2f} | Current Price: ${pos.get("current_price"):,.2f}\n"
                if len(portfolio_state.get("positions", [])) > 5:
                    message_text += f"  ... and {len(portfolio_state.get("positions", [])) - 5} more positions.\n"

                await self.telegram_agent.send_message(chat_id=response_chat_id, message=message_text, parse_mode="Markdown")
            else:
                logger.error("GET_PORTFOLIO_STATE event received with no chat_id and not a Flask request.")
        elif response_chat_id == "flask_request":
            request_id = event.data.get("request_id")
            if request_id in flask_response_queues:
                await flask_response_queues[request_id].put(portfolio_report) # Send error report back to Flask
        elif response_chat_id:
            await self.telegram_agent.send_message(
                chat_id=response_chat_id,
                message=f"Failed to retrieve portfolio state: {portfolio_report.message}"
            )
        else:
            logger.error(f"Failed to retrieve portfolio state or no chat_id: {portfolio_report.message}")
    
    async def handle_health_check_trigger(self, event: Event):
        """Handle periodic health check trigger from scheduler."""
        logger.info("Orchestrator received HEALTH_CHECK_TRIGGER. Running health check.")
        report = await self.health_agent.run(event_type=Events.SCHEDULE)
        logger.info(f"Health check completed: {report.message}")
        # Optionally send Telegram alert if issues
        if report.status == "success" and report.payload.get("status") in ("warning", "critical"):
            chat_id = self.config_engine.get("telegram", "chat_id", default=None)
            if chat_id:
                alerts = report.payload.get("alerts", [])
                message = "🦞 Health Check Alert:\n" + "\n".join(f"• {a}" for a in alerts)
                await self.telegram_agent.send_message(chat_id=chat_id, message=message)
    
    async def handle_get_health_status(self, event: Event):
        """Respond to health status query (GET_HEALTH_STATUS)."""
        logger.info("Orchestrator received GET_HEALTH_STATUS request.")
        report = await self.health_agent.run(event_type=Events.GET_SYSTEM_STATUS)
        response_chat_id = event.data.get("chat_id")
        if response_chat_id:
            payload = report.payload if report.status == "success" else {"error": report.message}
            message = f"**Health Status**\n```json\n{json.dumps(payload, indent=2)}\n```"
            await self.telegram_agent.send_message(chat_id=response_chat_id, message=message, parse_mode="Markdown")
        elif event.data.get("request_id"):
            request_id = event.data.get("request_id")
            if request_id in flask_response_queues:
                await flask_response_queues[request_id].put(report)


_orchestrator: Optional[MainOrchestratorAgent] = None
_event_bus_initialized: bool = False

@app.route("/analyze", methods=["POST"])
async def analyze_market():
    """Full analysis workflow: data → news → analysis → strategy → return trade proposals."""
    data = request.get_json() or {}
    symbol = data.get("symbol", "").upper()
    lookback_days = int(data.get("lookback_days", 30))
    interval = data.get("interval", "1d")
    
    if not symbol:
        return jsonify({"error": "Missing symbol parameter"}), 400
    
    # Calculate start date based on lookback
    from datetime import datetime, timedelta
    end_date = datetime.now().date()
    start_date = (datetime.now() - timedelta(days=lookback_days)).date().isoformat()
    
    orchestrator = get_orchestrator()
    
    try:
        # 1. Fetch data with sufficient lookback
        logger.info(f"[Analyze] Step 1: Fetching {lookback_days} days of data for {symbol}")
        data_report = await orchestrator.data_agent.run(
            symbol=symbol,
            interval=interval,
            start_date=start_date,
            end_date=end_date.isoformat(),
            emit_events=False,
            use_cache=False  # Bypass cache to ensure correct date range
        )
        if data_report.status != "success" or "dataframe" not in data_report.payload:
            return jsonify({"error": f"Data fetch failed: {data_report.message}"}), 500
        
        # Check if we got enough data
        df_len = len(data_report.payload["dataframe"].get("close", {}))
        if df_len < 50:
            return jsonify({"error": f"Insufficient historical data: only {df_len} rows, need 50+ for indicators. Try a longer lookback_days."}), 400
        
        # 2. Get news
        logger.info(f"[Analyze] Step 2: Fetching news for {symbol}")
        news_report = await orchestrator.news_agent.run(symbol=symbol)
        if news_report.status != "success":
            logger.warning(f"News fetch failed: {news_report.message}, using placeholder")
            news_report = AgentReport(
                agent_id="news_agent",
                status="success",
                message="Placeholder news (fetch failed)",
                payload={"symbol": symbol, "news_count": 0, "sentiment": {}, "catalysts": {}}
            )
        
        # 3. Calculate indicators
        logger.info(f"[Analyze] Step 3: Analyzing indicators for {symbol}")
        analysis_report = await orchestrator.analysis_agent.run(
            data_payload=data_report.payload["dataframe"],
            symbol=symbol
        )
        if analysis_report.status != "success":
            return jsonify({"error": f"Analysis failed: {analysis_report.message}"}), 500
        
        # 4. Generate trade proposals
        logger.info(f"[Analyze] Step 4: Generating trade proposals")
        strategy_report = await orchestrator.strategy_agent.run(
            indicators_report=analysis_report,
            news_report=news_report
        )
        if strategy_report.status != "success":
            return jsonify({"error": f"Strategy failed: {strategy_report.message}"}), 500
        
        # 5. Risk validation (if proposals generated)
        logger.info(f"[Analyze] Step 5: Running risk validation")
        proposals = strategy_report.payload.get("proposals", [])
        if proposals:
            # For now, validate first proposal only (future: batch validate all)
            first_proposal = proposals[0]
            from finance_service.core.models import TradeProposal
            proposal_obj = TradeProposal(**first_proposal)
            
            # Get current portfolio state for risk check
            portfolio_state = orchestrator.portfolio_agent.repository.calculate_portfolio(
                initial_cash=100000.0  # TODO: make configurable
            )
            
            # Build an AgentReport wrapper for RiskAgent (expects payload with "proposal")
            proposal_report = AgentReport(
                agent_id="strategy_agent",
                status="success",
                message="Trade proposal for risk check",
                payload={"proposal": first_proposal, "portfolio_state": portfolio_state.to_dict()}
            )
            
            # Run risk check
            risk_report = await orchestrator.risk_agent.run(trade_proposal_report=proposal_report)
            
            if risk_report.status == "success":
                risk_check = risk_report.payload.get("risk_assessment", {})
                # Risk check uses "passed" and "approval_required" fields
                if not risk_check.get("passed", False):
                    # Proposal rejected by risk
                    return jsonify({
                        "proposals": proposals,
                        "risk_rejection": {
                            "approved": False,
                            "reason": f"Failed: {', '.join(risk_check.get('violated_limits', []))}"
                        }
                    }), 200
                else:
                    logger.info(f"Risk check passed: score={risk_check.get('risk_score')}, approvals_required={risk_check.get('approval_required')}")
            else:
                logger.warning(f"Risk agent error: {risk_report.message}")
                # Continue anyway (risk not blocking if agent fails)
        
        return jsonify(strategy_report.payload), 200
        
    except Exception as e:
        logger.error(f"Error in analyze_market: {e}", exc_info=True)
        return jsonify({"error": f"Internal server error: {e}"}), 500


@app.route("/portfolio/state", methods=["GET"])
async def get_portfolio_state():
    """Get current portfolio state"""
    orchestrator = get_orchestrator()
    request_id = f"flask_{id(request)}"
    flask_response_queues[request_id] = asyncio.Queue()
    # This needs to be handled by a PortfolioAgent later, for now we trigger an event
    response_event = Event(event_type=Events.GET_PORTFOLIO_STATE, data={"chat_id": "flask_request", "request_id": request_id})
    await orchestrator.event_bus.publish(response_event)
    
    try:
        response_report = await asyncio.wait_for(flask_response_queues[request_id].get(), timeout=30.0)
        del flask_response_queues[request_id]
        if response_report.status == "success":
            return jsonify(response_report.payload), 200
        else:
            return jsonify({"error": response_report.message}), 500
    except asyncio.TimeoutError:
        del flask_response_queues[request_id]
        return jsonify({"error": "Portfolio state request timed out."}), 500
    except Exception as e:
        logger.error(f"Error retrieving portfolio state: {e}")
        if request_id in flask_response_queues:
            del flask_response_queues[request_id]
        return jsonify({"error": f"Internal server error: {e}"}), 500


@app.route("/portfolio/propose", methods=["POST"])
async def propose_trade():
    """Propose a trade"""
    orchestrator = get_orchestrator()
    request_id = f"flask_{id(request)}"
    flask_response_queues[request_id] = asyncio.Queue()

    # Trigger the strategy agent to propose a trade
    data = request.get_json() or {}
    symbol = data.get("symbol")
    if not symbol:
        return jsonify({"error": "Symbol is required for trade proposal."}), 400

    # The /propose endpoint directly triggers the strategy agent flow.
    # We expect an approval gate or direct execution to follow.
    # For this, we'll need to publish a specific event that the strategy agent listens to
    # For now, we simulate calling the strategy agent and returning its response.
    # In a full implementation, the strategy agent would get `indicators_report` and `news_report`
    # from other agents, but for direct API call, we'll mock them or pass minimal data.
    
    # Mock indicators and news reports for direct API call scenario
    mock_indicators_report = AgentReport(agent_id="analysis_agent", status="success", message="Mock indicators", payload={"symbol": symbol, "timestamp": datetime.utcnow().isoformat(), "indicators": {}})
    mock_news_report = AgentReport(agent_id="news_agent", status="success", message="Mock news", payload={"symbol": symbol, "news_count": 0, "sentiment": {}, "catalysts": {}})

    strategy_report = await orchestrator.strategy_agent.run(indicators_report=mock_indicators_report, news_report=mock_news_report)

    if strategy_report.status == "success":
        # If proposals are generated, we might want to publish an event for risk agent
        # and wait for the result here, similar to get_portfolio_state.
        # For simplicity, returning proposals directly for now.
        return jsonify(strategy_report.payload), 200
    else:
        return jsonify({"error": strategy_report.message}), 500


@app.route("/portfolio/execute", methods=["POST"])
async def execute_trade():
    """Execute a proposed trade"""
    orchestrator = get_orchestrator()
    request_id = f"flask_{id(request)}"
    flask_response_queues[request_id] = asyncio.Queue()

    data = request.get_json() or {}
    trade_proposal = data.get("trade_proposal")
    if not trade_proposal:
        return jsonify({"error": "trade_proposal is required for execution."}), 400

    # Call ExecutionAgent directly to execute the trade
    try:
        # Build a mock approval_report structure that ExecutionAgent expects
        approval_report = AgentReport(
            agent_id="mock_risk_agent",
            status="approved",
            message="Trade approved for direct execution",
            payload={
                "trade_proposal": trade_proposal,
                "risk_assessment": {"approved": True}  # placeholder
            }
        )
        
        execution_report = await orchestrator.execution_agent.run(approval_report)
        
        if execution_report.status == "success":
            # The execution agent already published TRADE_EXECUTED event which updates portfolio
            # Wait a brief moment for portfolio update to complete
            await asyncio.sleep(0.5)
            return jsonify(execution_report.payload), 200
        else:
            return jsonify({"error": execution_report.message}), 500
            
    except Exception as e:
        logger.error(f"Error executing trade: {e}")
        return jsonify({"error": f"Internal server error: {e}"}), 500


@app.route("/quote/<symbol>", methods=["GET"])
async def get_quote(symbol):
    """Get latest quote for symbol"""
    orchestrator = get_orchestrator()
    # For a simple quote, we can directly ask the DataAgent
    report = await orchestrator.data_agent.run(symbol=symbol, interval="1d", emit_events=False) # No events for simple quote

    if report.status == "success" and report.payload:
        # Assuming the dataframe in payload contains the latest quote
        df_dict = report.payload.get("dataframe")
        if df_dict:
            df = pd.DataFrame.from_dict(df_dict)
            if not df.empty:
                latest_row = df.iloc[-1]
                quote = {
                    "symbol": symbol,
                    "open": float(latest_row["open"]),
                    "high": float(latest_row["high"]),
                    "low": float(latest_row["low"]),
                    "close": float(latest_row["close"]),
                    "volume": float(latest_row["volume"]),
                    "timestamp": latest_row.name.isoformat() if hasattr(latest_row.name, 'isoformat') else str(latest_row.name)
                }
                return jsonify(quote), 200
        return jsonify({"error": f"No quote data found for {symbol}"}), 404
    else:
        return jsonify({"error": report.message}), 500


@app.route("/trigger/<trigger_type>", methods=["POST"])
async def trigger_event(trigger_type: str):
    """Manual trigger endpoint for testing scheduled tasks."""
    logger.info(f"TRIGGER ENDPOINT CALLED with trigger_type={trigger_type}")
    orchestrator = get_orchestrator()
    
    event_type_map = {
        "market-scan": Events.MARKET_SCAN_TRIGGER,
        "data-refresh": Events.DATA_REFRESH_TRIGGER,
        "daily-report": Events.DAILY_REPORT_TRIGGER,
        "system-status": Events.GET_SYSTEM_STATUS
    }
    
    if trigger_type not in event_type_map:
        return jsonify({"error": f"Unknown trigger: {trigger_type}. Valid: {list(event_type_map.keys())}"}), 400
    
    event_type = event_type_map[trigger_type]
    event = Event(event_type=event_type, data={})
    logger.info(f"Calling handler directly for: {event_type}")
    # Directly call the appropriate handler instead of publishing via event bus (temporary bypass)
    if event_type == Events.MARKET_SCAN_TRIGGER:
        try:
            result = await orchestrator.handle_market_scan_trigger(event)
            logger.info(f"Direct handler returned: {result}")
        except Exception as e:
            logger.error(f"Error in direct handler: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    else:
        logger.info(f"Publishing event: {event_type}")
        await orchestrator.event_bus.publish(event)
        logger.info(f"Event published successfully")
    
    return jsonify({"status": "ok", "event": event_type, "message": f"Triggered {trigger_type}"}), 200


if __name__ == "__main__":
    Config.validate()
    async def main():
        orchestrator = get_orchestrator()
        # You can trigger the orchestrator's run method here if it has a continuous loop
        asyncio.create_task(orchestrator.run()) # Start the orchestrator's main loop in the background
        # Use gunicorn or hypercorn for production async Flask deployment
        # For development, run the Flask app directly. Flask 2.0+ supports async views.
        # However, app.run() itself is synchronous and blocks. 
        # To run async Flask with `app.run()`, we need an async-aware server like `quart` or `hypercorn`.
        # For this exercise, we'll keep app.run() blocking for simplicity, 
        # but ideally, this would be `hypercorn app:app` or similar.
        # For now, the orchestrator.run() will be started as a background task,
        # and the Flask app.run() will block the main thread as usual.
        app.run(host="0.0.0.0", port=5000, debug=True)

    asyncio.run(main())


# ============================================================================
# Simple synchronous API for direct programmatic access (testing/demos)
# ============================================================================

class SimpleFinanceService:
    """Simple synchronous wrapper for analysis and portfolio operations."""

    def __init__(self):
        self._config_engine = YAMLConfigEngine()
        self._orchestrator = None

    async def _get_orchestrator(self):
        if self._orchestrator is None:
            self._orchestrator = get_orchestrator()
        return self._orchestrator

    def analyze(self, symbol: str) -> dict:
        """
        Run full analysis for a symbol and return decision.

        Returns:
            dict with keys: symbol, decision, confidence, required_approval,
                           position (with action_qty, action_value), risk (risk_level, max_loss_estimate, stop_loss, take_profit)
        """
        try:
            # Run async analysis synchronously
            result = asyncio.run(self._analyze_async(symbol))
            return result
        except Exception as e:
            logger.error(f"Analysis failed for {symbol}: {e}", exc_info=True)
            return {"error": str(e), "symbol": symbol}

    async def _analyze_async(self, symbol: str) -> dict:
        orchestrator = await self._get_orchestrator()

        # 1. Data fetch
        data_report = await orchestrator.data_agent.run(symbol=symbol, interval="1d", emit_events=False)
        if data_report.status != "success":
            return {"error": data_report.message, "symbol": symbol}

        # 2. Analysis
        analysis_payload = data_report.payload.get("dataframe")
        if not analysis_payload:
            return {"error": "No data returned from data agent", "symbol": symbol}
        analysis_report = await orchestrator.analysis_agent.run(data_payload=analysis_payload, symbol=symbol)
        if analysis_report.status != "success":
            return {"error": analysis_report.message, "symbol": symbol}

        # 3. Strategy
        strategy_report = await orchestrator.strategy_agent.run(analysis_report.payload, symbol=symbol)
        if strategy_report.status != "success":
            return {"error": strategy_report.message, "symbol": symbol}

        # 4. Risk
        risk_report = await orchestrator.risk_agent.run(strategy_report.payload, symbol=symbol)
        if risk_report.status != "success":
            return {"error": risk_report.message, "symbol": symbol}

        # Build result
        decision = risk_report.payload.get("decision", "HOLD")
        confidence = risk_report.payload.get("confidence", 0.0)
        requires_approval = risk_report.payload.get("requires_approval", False)

        result = {
            "symbol": symbol,
            "decision": decision,
            "confidence": confidence,
            "required_approval": requires_approval,
        }

        # Add position sizing if available
        if "position" in risk_report.payload:
            result["position"] = risk_report.payload["position"]
        if "risk" in risk_report.payload:
            result["risk"] = risk_report.payload["risk"]

        return result

    def portfolio_state(self) -> dict:
        """Get current portfolio state."""
        try:
            return asyncio.run(self._portfolio_state_async())
        except Exception as e:
            logger.error(f"Portfolio state error: {e}")
            return {"error": str(e)}

    async def _portfolio_state_async(self) -> dict:
        orchestrator = await self._get_orchestrator()
        report = await orchestrator.portfolio_agent.run(event_type=Events.GET_PORTFOLIO_STATE, payload={})
        if report.status == "success":
            return report.payload
        else:
            return {"error": report.message}

# ============================================================================
# Global orchestrator startup function (called from main thread before serving)
# ============================================================================
async def startup_orchestrator() -> MainOrchestratorAgent:
    """Initialize the orchestrator at service startup. Must be called in main thread before any requests."""
    global _orchestrator, _startup_done
    if _startup_done and _orchestrator is not None:
        logger.info("[STARTUP] Orchestrator already initialized, returning existing")
        return _orchestrator
    
    logger.info("[STARTUP] Initializing orchestrator...")
    config_engine = YAMLConfigEngine(config_dir="config")
    _orchestrator = MainOrchestratorAgent(config_engine)
    _orchestrator.event_bus = get_event_bus()
    
    # Inject event bus into all agents
    agents = [
        _orchestrator.market_scanner_agent,
        _orchestrator.data_agent,
        _orchestrator.news_agent,
        _orchestrator.analysis_agent,
        _orchestrator.strategy_agent,
        _orchestrator.risk_agent,
        _orchestrator.execution_agent,
        _orchestrator.learning_agent,
        _orchestrator.telegram_agent,
        _orchestrator.scheduler_agent,
        _orchestrator.portfolio_agent,
        _orchestrator.health_agent,
    ]
    for agent in agents:
        if hasattr(agent, 'event_bus'):
            agent.event_bus = _orchestrator.event_bus
    
    # Additional cross-agent dependencies
    _orchestrator.strategy_agent.portfolio_agent = _orchestrator.portfolio_agent
    _orchestrator.health_agent.portfolio_agent = _orchestrator.portfolio_agent
    _orchestrator.health_agent.telegram_agent = _orchestrator.telegram_agent
    _orchestrator.scheduler_agent._orchestrator = _orchestrator  # Scheduler needs orchestrator to publish events
    
    # Start scheduler
    asyncio.create_task(_orchestrator.scheduler_agent.run())
    
    # Register event handlers
    handlers = [
        (Events.MARKET_SCANNED, _orchestrator.handle_market_scanned, "MARKET_SCANNED"),
        (Events.DATA_FETCH_COMPLETE, _orchestrator.handle_data_fetch_complete, "DATA_FETCH_COMPLETE"),
        (Events.NEWS_FETCH_COMPLETE, _orchestrator.handle_news_fetch_complete, "NEWS_FETCH_COMPLETE"),
        (Events.ANALYSIS_COMPLETE, _orchestrator.handle_analysis_complete, "ANALYSIS_COMPLETE"),
        (Events.TRADE_PROPOSAL_GENERATED, _orchestrator.handle_trade_proposal_generated, "TRADE_PROPOSAL_GENERATED"),
        (Events.RISK_CHECK_COMPLETE, _orchestrator.handle_risk_check_complete, "RISK_CHECK_COMPLETE"),
        (Events.APPROVAL_REQUIRED, _orchestrator.handle_approval_required, "APPROVAL_REQUIRED"),
        (Events.TRADE_EXECUTED, _orchestrator.handle_trade_executed, "TRADE_EXECUTED"),
        (Events.LEARNING_COMPLETE, _orchestrator.handle_learning_complete, "LEARNING_COMPLETE"),
        (Events.MARKET_SCAN_TRIGGER, _orchestrator.handle_market_scan_trigger, "MARKET_SCAN_TRIGGER"),
        (Events.DATA_REFRESH_TRIGGER, _orchestrator.handle_data_refresh_trigger, "DATA_REFRESH_TRIGGER"),
        (Events.DAILY_REPORT_TRIGGER, _orchestrator.handle_daily_report_trigger, "DAILY_REPORT_TRIGGER"),
        (Events.HEALTH_CHECK_TRIGGER, _orchestrator.handle_health_check_trigger, "HEALTH_CHECK_TRIGGER"),
        (Events.GET_SYSTEM_STATUS, _orchestrator.handle_get_system_status, "GET_SYSTEM_STATUS"),
        (Events.GET_HEALTH_STATUS, _orchestrator.handle_get_health_status, "GET_HEALTH_STATUS"),
        (Events.GET_PORTFOLIO_STATE, _orchestrator.handle_get_portfolio_state, "GET_PORTFOLIO_STATE"),
    ]
    for event_type, handler, name in handlers:
        await _orchestrator.event_bus.on(event_type, handler)
    
    logger.info("[STARTUP] Orchestrator initialization complete")
    _startup_done = True
    return _orchestrator

# Create singleton for import
finance_service = SimpleFinanceService()
