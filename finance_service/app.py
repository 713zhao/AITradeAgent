import logging
import json # Added for JSON formatting in Telegram messages
from typing import Dict, Any, Optional, List
import asyncio
from datetime import datetime
from flask import Flask, request, jsonify

# Temporary storage for Flask-initiated async responses
flask_response_queues: Dict[str, asyncio.Queue] = {}

from .core.config import Config
from .core.logging import setup_logger, RunLogger
from .core.event_bus import get_event_bus, Event, Events

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
from finance_service.agents.portfolio_agent import PortfolioAgent # New import

logger = setup_logger(__name__)
run_logger = RunLogger()

app = Flask(__name__)

class MainOrchestratorAgent(Agent):
    """Main Orchestrator Agent - Coordinates all specialized agents in the trading system."""

    @property
    def agent_id(self) -> str:
        return "main_orchestrator_agent"

    @property
    def goal(self) -> str:
        return "Orchestrate the end-to-end trading workflow, from market scanning to trade execution and learning."
    
    def __init__(self, config: Dict[str, Any]): # __init__ should not be async
        self.config = config
        self.event_bus = None # Initialized in async initialize_orchestrator
        self.pending_news_reports: Dict[str, AgentReport] = {}
        self.pending_analysis_reports: Dict[str, AgentReport] = {}
        logger.info("MainOrchestratorAgent initializing...")

        # Initialize all agents
        self.market_scanner_agent = MarketScannerAgent(config.get("market_scanner", {}))
        self.data_agent = DataAgent(config.get("data_agent", {}))
        self.news_agent = NewsAgent(config.get("news_agent", {}))
        self.analysis_agent = AnalysisAgent(config.get("analysis_agent", {}))
        self.strategy_agent = StrategyAgent(config.get("strategy_agent", {}))
        self.risk_agent = RiskAgent(config.get("risk_agent", {}))
        self.execution_agent = ExecutionAgent(config.get("execution_agent", {}))
        self.learning_agent = LearningAgent(config.get("learning_agent", {}))
        self.telegram_agent = TelegramAgent(config.get("telegram_agent", {}))
        self.scheduler_agent = SchedulerAgent(config.get("scheduler_agent", {}))
        self.portfolio_agent = PortfolioAgent(config.get("portfolio_agent", {})) # New agent initialization

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
        symbols = event.data.get("symbols", [])
        for symbol in symbols:
            await self.data_agent.run(symbol=symbol, interval="1d")
    
    async def handle_data_fetch_complete(self, event: Event):
        logger.info(f"Orchestrator received DATA_FETCH_COMPLETE event: {event.data}")
        symbol = event.data.get("symbol")
        data_payload = event.data.get("dataframe") # Now this is a dict
        if data_payload is not None and symbol is not None:
            await self.news_agent.run(symbol=symbol)
            # Pass the data_payload (dict) to analysis_agent.run
            await self.analysis_agent.run(data_payload=data_payload, symbol=symbol)

    async def handle_news_fetch_complete(self, event: Event):
        logger.info(f"Orchestrator received NEWS_FETCH_COMPLETE event: {event.data}")
        news_report = AgentReport(**event.data) # Reconstruct AgentReport
        symbol = news_report.payload.get("symbol")
        if symbol:
            self.pending_news_reports[symbol] = news_report
            await self._try_trigger_strategy_agent(symbol)

    async def handle_analysis_complete(self, event: Event):
        logger.info(f"Orchestrator received ANALYSIS_COMPLETE event: {event.data}")
        analysis_report = AgentReport(**event.data) # Reconstruct AgentReport
        symbol = analysis_report.payload.get("symbol")
        if symbol:
            self.pending_analysis_reports[symbol] = analysis_report
            await self._try_trigger_strategy_agent(symbol)

    async def _try_trigger_strategy_agent(self, symbol: str):
        news_report = self.pending_news_reports.get(symbol)
        analysis_report = self.pending_analysis_reports.get(symbol)

        if news_report and analysis_report:
            logger.info(f"Both news and analysis reports available for {symbol}. Triggering StrategyAgent.")
            await self.strategy_agent.run(indicators_report=analysis_report, news_report=news_report)
            # Clear pending reports after triggering strategy agent
            del self.pending_news_reports[symbol]
            del self.pending_analysis_reports[symbol]

    async def handle_trade_proposal_generated(self, event: Event):
        logger.info(f"Orchestrator received TRADE_PROPOSAL_GENERATED event: {event.data}")
        trade_proposal_report = AgentReport(**event.data)
        await self.risk_agent.run(trade_proposal_report=trade_proposal_report)

    async def handle_risk_check_complete(self, event: Event):
        logger.info(f"Orchestrator received RISK_CHECK_COMPLETE event: {event.data}")
        risk_check_report = AgentReport(**event.data)
        # Assuming RiskAgent's report contains a RiskCheckResult with approval_required
        risk_check_result = risk_check_report.payload.get("risk_check_result")
        
        if risk_check_result and not risk_check_result.get("approval_required", False):
            # If no approval is required, proceed to execution
            await self.execution_agent.run(approved_trade_proposal=risk_check_report.payload.get("trade_proposal"))
        else:
            logger.info("Approval required for trade proposal.")

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
        trade_execution_report = AgentReport(**event.data)
        
        # Check if this trade execution was initiated by a Flask request
        request_id = event.data.get("request_id")
        if request_id and request_id in flask_response_queues:
            await flask_response_queues[request_id].put(trade_execution_report)
            logger.info(f"Sent TRADE_EXECUTED report back to Flask request {request_id}")

        # Update portfolio first
        await self.portfolio_agent.run(event_type=Events.TRADE_EXECUTED, payload=trade_execution_report.payload)
        # Then let the learning agent process
        await self.learning_agent.run(execution_report=trade_execution_report)

    async def handle_learning_complete(self, event: Event):
        logger.info(f"Orchestrator received LEARNING_COMPLETE event: {event.data}")
        # Learning agent has completed its cycle, possibly publish feedback

    async def handle_market_scan_trigger(self, event: Event):
        logger.info(f"Orchestrator received MARKET_SCAN_TRIGGER event: {event.data}")
        await self.market_scanner_agent.run()

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


_orchestrator: Optional[MainOrchestratorAgent] = None
_event_bus_initialized: bool = False

async def initialize_orchestrator() -> MainOrchestratorAgent:
    global _orchestrator, _event_bus_initialized
    if _orchestrator is None:
        config_instance = Config()
        app_config = config_instance.load_config()
        
        _orchestrator = MainOrchestratorAgent(app_config)
        _orchestrator.event_bus = await get_event_bus() # Assign event bus after orchestrator is created
        
        # Register event listeners for inter-agent communication
        await _orchestrator.event_bus.on(Events.MARKET_SCANNED, _orchestrator.handle_market_scanned)
        await _orchestrator.event_bus.on(Events.DATA_FETCH_COMPLETE, _orchestrator.handle_data_fetch_complete)
        await _orchestrator.event_bus.on(Events.NEWS_FETCH_COMPLETE, _orchestrator.handle_news_fetch_complete)
        await _orchestrator.event_bus.on(Events.ANALYSIS_COMPLETE, _orchestrator.handle_analysis_complete)
        await _orchestrator.event_bus.on(Events.TRADE_PROPOSAL_GENERATED, _orchestrator.handle_trade_proposal_generated)
        await _orchestrator.event_bus.on(Events.RISK_CHECK_COMPLETE, _orchestrator.handle_risk_check_complete)
        await _orchestrator.event_bus.on(Events.APPROVAL_REQUIRED, _orchestrator.handle_approval_required)
        await _orchestrator.event_bus.on(Events.TRADE_EXECUTED, _orchestrator.handle_trade_executed)
        await _orchestrator.event_bus.on(Events.LEARNING_COMPLETE, _orchestrator.handle_learning_complete)
        await _orchestrator.event_bus.on(Events.MARKET_SCAN_TRIGGER, _orchestrator.handle_market_scan_trigger)
        await _orchestrator.event_bus.on(Events.DATA_REFRESH_TRIGGER, _orchestrator.handle_data_refresh_trigger)
        await _orchestrator.event_bus.on(Events.DAILY_REPORT_TRIGGER, _orchestrator.handle_daily_report_trigger)
        await _orchestrator.event_bus.on(Events.GET_SYSTEM_STATUS, _orchestrator.handle_get_system_status)
        await _orchestrator.event_bus.on(Events.GET_PORTFOLIO_STATE, _orchestrator.handle_get_portfolio_state)

        _event_bus_initialized = True
        logger.info("MainOrchestratorAgent and event listeners initialized.")
    return _orchestrator


@app.route("/analyze", methods=["POST"])
async def analyze_market():
    """Analyze market data for a given symbol."""
    data = request.get_json() or {}
    symbol = data.get("symbol", "").upper()
    interval = data.get("interval", "1d")
    
    if not symbol:
        return jsonify({"error": "Missing symbol parameter"}), 400
    
    # Trigger the workflow through the orchestrator's event bus or direct agent call
    orchestrator = await initialize_orchestrator()
    report = await orchestrator.data_agent.run(symbol=symbol, interval=interval)
    if report.status == "success":
        return jsonify(report.payload), 200
    else:
        return jsonify({"error": report.message}), 500


@app.route("/portfolio/state", methods=["GET"])
async def get_portfolio_state():
    """Get current portfolio state"""
    orchestrator = await initialize_orchestrator()
    # This needs to be handled by a PortfolioAgent later, for now we trigger an event
    response_event = Event(event_type=Events.GET_PORTFOLIO_STATE, data={"chat_id": request_id}) 
    await orchestrator.event_bus.publish(response_event)
    
    try:
        response_report = await asyncio.wait_for(flask_response_queues[request_id].get(), timeout=10.0)
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
    orchestrator = await initialize_orchestrator()
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
    mock_indicators_report = AgentReport(agent_id="analysis_agent", status="success", message="Mock indicators", payload={"symbol": symbol, "timestamp": datetime.utcnow().isoformat(), "indicators": {}}))
    mock_news_report = AgentReport(agent_id="news_agent", status="success", message="Mock news", payload={"symbol": symbol, "news_count": 0, "sentiment": {}, "catalysts": {}}))

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
    orchestrator = await initialize_orchestrator()
    request_id = f"flask_{id(request)}"
    flask_response_queues[request_id] = asyncio.Queue()

    data = request.get_json() or {}
    trade_proposal = data.get("trade_proposal")
    if not trade_proposal:
        return jsonify({"error": "trade_proposal is required for execution."}), 400

    # Publish event to execution agent directly (assuming pre-approved or risk check done)
    # In a real scenario, this would typically follow an approval flow.
    await orchestrator.event_bus.publish(Event(event_type=Events.TRADE_EXECUTED, data={"trade_proposal": trade_proposal, "status": "direct_execute", "request_id": request_id}))
    
    try:
        response_report = await asyncio.wait_for(flask_response_queues[request_id].get(), timeout=10.0)
        del flask_response_queues[request_id]
        if response_report.status == "success":
            return jsonify(response_report.payload), 200
        else:
            return jsonify({"error": response_report.message}), 500
    except asyncio.TimeoutError:
        del flask_response_queues[request_id]
        return jsonify({"error": "Trade execution request timed out."}), 500
    except Exception as e:
        logger.error(f"Error executing trade: {e}")
        if request_id in flask_response_queues:
            del flask_response_queues[request_id]
        return jsonify({"error": f"Internal server error: {e}"}), 500


@app.route("/quote/<symbol>", methods=["GET"])
async def get_quote(symbol):
    """Get latest quote for symbol"""
    orchestrator = await initialize_orchestrator()
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


if __name__ == "__main__":
    Config.validate()
    async def main():
        orchestrator = await initialize_orchestrator()
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
