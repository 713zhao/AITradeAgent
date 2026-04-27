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
from finance_service.agents.market_regime_agent import MarketRegimeAgent
from finance_service.agents.macro_news_agent import MacroNewsAgent
from finance_service.agents.symbol_selector_agent import SymbolSelectorAgent
from finance_service.agents.data_agent import DataAgent
from finance_service.agents.fundamentals_agent import FundamentalsAgent
from finance_service.agents.options_data_agent import OptionsDataAgent
from finance_service.agents.options_strategy_agent import OptionsStrategyAgent
from finance_service.agents.regime_agent import RegimeAgent
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
from finance_service.agents.learning_agent import LearningAgent
from finance_service.agents.ranking_agent import RankingAgent
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
        from finance_service.core.yaml_config import YAMLConfigEngine
        self.config_engine = YAMLConfigEngine(config_dir="config")
        self.config = config
        self.event_bus = get_event_bus()  # Get the singleton
        self.repository = TradeRepository()
        # Agents will be initialized in startup_orchestrator
        self.scheduler_agent: Optional[SchedulerAgent] = None
        self.market_scanner_agent: Optional[MarketScannerAgent] = None
        self.market_regime_agent: Optional[MarketRegimeAgent] = None
        self.macro_news_agent: Optional[MacroNewsAgent] = None
        self.symbol_selector_agent: Optional[SymbolSelectorAgent] = None
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
        self.last_scan_meta: Dict[str, Any] = {
            "status": "never",
            "triggered_at": None,
            "market": None,
            "debug_bypass_market_hours": False,
            "as_of_date": None,
        }

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
        telegram_token = config_engine.get("notifications", "telegram/bot_token", default=None)
        if telegram_token:
            simple_config["telegram_bot_token"] = telegram_token
        telegram_chat = config_engine.get("notifications", "telegram/chat_id", default=None)
        if telegram_chat:
            simple_config["telegram_chat_id"] = telegram_chat
        telegram_thread = config_engine.get("notifications", "telegram/message_thread_id", default=None)
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
            "approval_required_pct",
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
        # New LLM-powered context agents
        self.market_regime_agent = MarketRegimeAgent(config_engine, data_agent=self.data_agent, market_scanner=self.market_scanner_agent)
        self.macro_news_agent = MacroNewsAgent(config_engine)
        self.news_agent = NewsAgent(config_engine)
        # FundamentalsAgent: fetch fundamental metrics (Phase 4)
        self.fundamentals_agent = FundamentalsAgent(config_engine)
        # OptionsDataAgent: fetch options chains (Phase 5)
        self.options_data_agent = OptionsDataAgent(config_engine)
        # OptionsStrategyAgent: generate options-enhanced proposals (Phase 5)
        self.options_strategy_agent = OptionsStrategyAgent(config_engine)
        # RegimeAgent: optional LLM market regime classifier (Phase 1)
        self.regime_agent = RegimeAgent(config_engine)
        # AnalysisAgent: uses default indicator periods; no config needed
        self.analysis_agent = AnalysisAgent()
        # SymbolSelectorAgent: LLM-powered ranking with market context (Phase X)
        self.symbol_selector_agent = SymbolSelectorAgent(
            config_engine=config_engine,
            data_agent=self.data_agent,
            market_scanner=self.market_scanner_agent,
            market_regime_agent=self.market_regime_agent,
            macro_news_agent=self.macro_news_agent,
            analysis_agent=self.analysis_agent,
            news_agent=self.news_agent
        )
        # StrategyAgent: needs config_engine and portfolio_agent (injected after)
        self.strategy_agent = StrategyAgent(config_engine, portfolio_agent=None)
        # RiskAgent: uses simple_config with policy dict
        self.risk_agent = RiskAgent(simple_config, portfolio_agent=None)
        
        # Broker (Phase 7): create from config
        broker_type = config_engine.get("finance", "execution/broker", default="paper")
        broker_config = config_engine.get_section("finance").get("execution", {}).get("broker_config", {})
        from finance_service.brokers.factory import BrokerFactory
        broker = BrokerFactory.create(broker_type, broker_config)
        # Connect broker
        await broker.connect()
        logger.info(f"Broker connected: {broker_type}")
        
        # ExecutionAgent: now takes broker instance
        self.execution_agent = ExecutionAgent(broker)
        
        # PortfolioAgent: needs simple_config and data_agent
        self.portfolio_agent = PortfolioAgent(simple_config, data_agent=self.data_agent)
        # HealthAgent: uses config_engine
        self.health_agent = HealthAgent(config_engine)
        # LearningAgent: ML model training and inference (Phase 6)
        self.learning_agent = LearningAgent(config_engine)
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
        await self.event_bus.subscribe(Events.PRE_SCAN_CONTEXT_REFRESH, self.handle_pre_scan_context_refresh)
        await self.event_bus.subscribe(Events.DAILY_REPORT_TRIGGER, self.handle_daily_report)
        await self.event_bus.subscribe(Events.HOURLY_PORTFOLIO_TRIGGER, self.handle_hourly_portfolio_report)

        # Start background agents (those with continuous loops)
        asyncio.create_task(self.scheduler_agent.run())
        asyncio.create_task(self.telegram_agent.run())
        logger.info("Orchestrator startup complete. All agents initialized and scheduled.")

    # Event handlers
    async def handle_pre_scan_context_refresh(self, event: Event):
        """Pre-warm MarketRegimeAgent and MacroNewsAgent caches before the discovery scan runs."""
        market = event.data.get("market", "US")
        logger.info(f"[PreWarm] Refreshing MarketRegimeAgent + MacroNewsAgent for {market} market...")
        try:
            regime_report, macro_report = await asyncio.gather(
                self.market_regime_agent.run({"force_refresh": True}),
                self.macro_news_agent.run({"force_refresh": True}),
                return_exceptions=True,
            )
            regime_ok = not isinstance(regime_report, Exception) and regime_report and regime_report.status == "success"
            macro_ok = not isinstance(macro_report, Exception) and macro_report and macro_report.status == "success"
            logger.info(f"[PreWarm] Done — regime: {'✓' if regime_ok else '✗'}  macro: {'✓' if macro_ok else '✗'}")
        except Exception as e:
            logger.error(f"[PreWarm] Context refresh failed: {e}")

    async def handle_market_scan_trigger(self, event: Event):
        logger.info("Received MARKET_SCAN_TRIGGER")
        event_data_in = event.data or {}
        triggered_at = datetime.utcnow().isoformat()
        self.last_scan_meta = {
            "status": "triggered",
            "triggered_at": triggered_at,
            "market": event_data_in.get("market", "US"),
            "debug_bypass_market_hours": bool(event_data_in.get("debug_bypass_market_hours", False)),
            "as_of_date": event_data_in.get("as_of_date"),
            "enforce_market_hours_for_scan": None,
        }

        # Configurable market-hours gate (can be disabled for debug scans)
        enforce_market_hours = self.config_engine.get(
            "finance", "scanner/enforce_market_hours_for_scan", default=True
        )
        self.last_scan_meta["enforce_market_hours_for_scan"] = bool(enforce_market_hours)
        debug_bypass_market_hours = bool(event_data_in.get("debug_bypass_market_hours", False))
        bypass_market_hours_scan = bool(event_data_in.get("bypass_market_hours_scan", False))
        market_for_scan = event_data_in.get("market", "US")

        from finance_service.utils.market_hours import is_us_market_open, is_hk_market_open
        if enforce_market_hours and not debug_bypass_market_hours and not bypass_market_hours_scan:
            hk_open = is_hk_market_open()
            us_open = is_us_market_open()
            # For market-specific scans, only check the relevant market
            if market_for_scan == "HK" and not hk_open:
                logger.info("HK market closed. Skipping HK market scan.")
                self.last_scan_meta["status"] = "skipped"
                self.last_scan_meta["reason"] = "hk_market_closed"
                return
            elif market_for_scan != "HK" and not us_open and not hk_open:
                logger.info("Markets closed (US and HK). Skipping market scan.")
                self.last_scan_meta["status"] = "skipped"
                self.last_scan_meta["reason"] = "markets_closed"
                return

        if debug_bypass_market_hours:
            logger.info("Debug bypass enabled: running market scan even though markets may be closed.")
        elif bypass_market_hours_scan:
            logger.info(f"Scheduler bypass: running {market_for_scan} market scan at scheduled market-open time.")

        # Trigger scanner with DataAgent for proper ranking
        report = await self.market_scanner_agent.run(data_agent=self.data_agent)
        self.last_scan_meta["scanner_report_status"] = report.status
        self.last_scan_meta["scanner_message"] = report.message
        self.last_scan_meta["symbols_discovered"] = len((report.payload or {}).get("symbols", []))
        if report.status == "success" or report.status == "opportunity":
            # Publish the payload as event data; include status in payload if needed
            event_data = report.payload.copy()
            event_data["status"] = report.status
            event_data["message"] = report.message
            # Pass optional trigger context downstream
            event_data["market"] = event_data_in.get("market", "US")
            if event_data_in.get("as_of_date"):
                event_data["as_of_date"] = event_data_in.get("as_of_date")
            await self.event_bus.publish(Event(event_type=Events.MARKET_SCANNED, data=event_data))

    async def handle_market_scanned(self, event: Event):
        logger.info(f"Orchestrator received MARKET_SCANNED event: {event.data}")
        # Event data is directly the payload from MarketScannerAgent, with possible additional fields
        symbols = event.data.get("symbols", [])
        rated_symbols = event.data.get("rated_symbols", [])
        market = event.data.get("market", "US")
        logger.info(f"Processing {len(symbols)} symbols [{market}]: {symbols}")

        # Use SymbolSelectorAgent (LLM) to rank and filter candidates
        if (self.symbol_selector_agent and getattr(self.symbol_selector_agent, '_llm_manager', None)):
            try:
                logger.info("Invoking SymbolSelectorAgent for ranking...")
                selector_report = await self.symbol_selector_agent.run({"symbols": symbols, "market": market})
                if selector_report.status == "success":
                    rankings = selector_report.payload.get("rankings", [])
                    llm_summary = selector_report.payload.get("llm_summary", "")
                    tokens_used = selector_report.payload.get("tokens_used", 0)
                    market_context = selector_report.payload.get("market_context", {})
                    selected_symbols = [r["symbol"] for r in rankings[:5]]  # top 5 per market
                    logger.info(f"SymbolSelector ranked {len(selected_symbols)} symbols (from {len(symbols)}) using {tokens_used} tokens")
                    symbols = selected_symbols  # override processing list
                    # Send LLM analysis result to Telegram (with regime + macro context)
                    if self.telegram_agent and self.telegram_agent.enabled:
                        asyncio.create_task(self._send_llm_ranking_to_telegram(
                            rankings, llm_summary, tokens_used, market_context, market
                        ))
                else:
                    logger.warning(f"SymbolSelector failed: {selector_report.message}; using original list")
            except Exception as e:
                logger.error(f"SymbolSelector error: {e}; proceeding with unfiltered list")
        else:
            logger.info("SymbolSelector not available; proceeding with unfiltered list")

        # Send market scan summary to Telegram (always; includes details and ranked scores)
        if self.telegram_agent and self.telegram_agent.enabled:
            chat_id = self.telegram_agent.chat_id
            if chat_id:
                # Build detailed ranked summary with composite scores
                import html as _html
                preview_symbols = rated_symbols[:50] if rated_symbols else []
                details = []

                for item in preview_symbols:
                    sym = item.get("symbol", "")
                    score = item.get("rating", 0)
                    rank = item.get("rank", 0)
                    snap = await self._get_symbol_snapshot(sym)
                    yf_symbol = sym.replace(".", "-")
                    quote_url = f"https://finance.yahoo.com/quote/{yf_symbol}"
                    if snap:
                        price = snap.get("price", 0)
                        full_name = _html.escape(snap.get("full_name") or sym)
                        details.append(
                            f'{rank:2d}. <a href="{quote_url}">{_html.escape(sym)}</a> [{full_name}]  ${price:7.2f} (score={score:.3f})'
                        )
                    else:
                        details.append(
                            f'{rank:2d}. <a href="{quote_url}">{_html.escape(sym)}</a> [N/A]  N/A (score={score:.3f})'
                        )

                # Header with ranking info
                total_count = len(symbols)
                header = f"📊 Daily Market Scan – Top {min(50, total_count)} Symbols (Ranked by Composite Score)\n"
                
                # Add footer with additional info
                footer = ""
                if len(symbols) > 50:
                    footer = f"\n... and {len(symbols) - 50} more symbols"
                
                message = header + "\n".join(details) + footer
                
                try:
                    await self.telegram_agent.send_message(chat_id=chat_id, message=message, parse_mode="HTML")
                    logger.info("Sent market scan summary to Telegram")
                except Exception as e:
                    logger.error(f"Failed to send market scan Telegram: {e}")
                # Also send top analysis summary in background (does not block)
                # Temporarily disabled until method is implemented
                # asyncio.create_task(self._send_top_analysis_summary(symbols))

        # Use 365-day lookback (1 year) to ensure enough trading days for SMA200
        from datetime import datetime, timedelta
        as_of_date = event.data.get("as_of_date")
        if as_of_date:
            try:
                end_date = datetime.strptime(as_of_date, "%Y-%m-%d").date()
                logger.info(f"Using debug as_of_date for scan: {as_of_date}")
            except ValueError:
                logger.warning(f"Invalid as_of_date format {as_of_date}, expected YYYY-MM-DD. Falling back to today.")
                end_date = datetime.now().date()
        else:
            end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365)
        self.last_scan_meta["as_of_date_resolved"] = end_date.isoformat()
        self.last_scan_meta["lookback_start_date"] = start_date.isoformat()
        fetch_errors: list = []
        for symbol in symbols:
            # Data fetch (1d)
            data_report = await self.data_agent.run(symbol=symbol, interval="1d", start_date=start_date, end_date=end_date)
            if data_report.status != "success":
                logger.warning(f"Data fetch failed for {symbol}: {data_report.message}")
                fetch_errors.append(f"{symbol}: {data_report.message}")
                continue
            # Fundamentals fetch (optional, parallel with news)
            fundamentals_report = None
            if self.config_engine.get("finance", "data/fetch_fundamentals", default=False):
                fundamentals_report = await self.fundamentals_agent.run({"symbol": symbol})
                if fundamentals_report.status != "success":
                    logger.debug(f"Fundamentals unavailable for {symbol}: {fundamentals_report.message}")
                    fundamentals_report = None
            # News fetch
            news_report = await self.news_agent.run(symbol=symbol)
            # Analysis
            analysis_report = await self.analysis_agent.run(data_payload=data_report.payload, symbol=symbol)
            if analysis_report.status != "success":
                logger.warning(f"Analysis failed for {symbol}: {analysis_report.message}")
                continue
            
            # Attach fundamentals to analysis payload for strategy if available
            if fundamentals_report and fundamentals_report.status == "success":
                analysis_report.payload["fundamentals"] = fundamentals_report.payload.get("analysis", {})
            
            # Regime classification (if enabled)
            if self.config_engine.get("llm", "modules/market_regime/enabled", default=False):
                try:
                    regime_report = await self.regime_agent.run({
                        "symbol": symbol,
                        "ohlcv_data": data_report.payload.get("dataframe"),
                        "indicators": analysis_report.payload.get("indicators_snapshot", {}).get("indicators", {})
                    })
                    if regime_report and regime_report.payload:
                        logger.debug(f"Regime for {symbol}: {regime_report.payload.get('regime', {}).get('regime')}")
                except Exception as e:
                    logger.warning(f"RegimeAgent skipped for {symbol}: {e}")
            
            # Strategy
            strategy_report = await self.strategy_agent.run(analysis_report.payload, symbol=symbol)
            if strategy_report.status != "success":
                logger.warning(f"Strategy failed for {symbol}: {strategy_report.message}")
                continue
            
            # --- Phase 5: Options Strategy Enhancement ---
            base_proposals = strategy_report.payload.get("proposals", [])
            final_proposals = base_proposals  # default to base
            
            options_enabled = self.config_engine.get("finance", "options/enabled", default=False)
            logger.info(f"[ORCHESTRATOR] Options enabled config value: {options_enabled}, base_proposals count: {len(base_proposals)}")
            if options_enabled and base_proposals:
                try:
                    # Get current portfolio position (if any)
                    position = None
                    if self.portfolio_agent:
                        portfolio_report = await self.portfolio_agent.run(event_type=Events.GET_PORTFOLIO_STATE, payload={})
                        if portfolio_report.status == "success":
                            for pos in portfolio_report.payload.get("positions", []):
                                if pos.get("symbol") == symbol:
                                    position = pos
                                    break
                    # Fetch options chain
                    options_chain_report = await self.options_data_agent.run({"symbol": symbol})
                    if options_chain_report.status == "success":
                        # Generate options-enhanced proposals
                        options_payload = await self.options_strategy_agent.run({
                            "base_proposal": base_proposals[0],
                            "options_chain": options_chain_report.payload["options_chain"],
                            "portfolio_position": position,
                        })
                        if options_payload.status == "success":
                            options_proposals = options_payload.payload.get("options_proposals", [])
                            if options_proposals:
                                final_proposals = options_proposals
                                logger.info(f"Options strategy generated {len(options_proposals)} proposal(s) for {symbol}")
                except Exception as e:
                    logger.warning(f"Options pipeline failed for {symbol}: {e}")
            
            if not final_proposals:
                logger.info(f"[ORCHESTRATOR] No proposals for {symbol}, skipping")
                continue
            proposal = final_proposals[0]  # best proposal
            logger.info(f"[ORCHESTRATOR] Proposal details: symbol={proposal.get('symbol')}, action={proposal.get('action')}, quantity={proposal.get('quantity')}, confidence={proposal.get('confidence')}")
            try:
                risk_report = await self.risk_agent.run(proposal)
                logger.info(f"[ORCHESTRATOR] RiskAgent returned: status={risk_report.status}, decision={risk_report.payload.get('decision')}")
            except Exception as e:
                logger.error(f"[ORCHESTRATOR] RiskAgent call failed: {e}", exc_info=True)
                continue
            logger.info(f"Risk report for {symbol}: status={risk_report.status}, decision={risk_report.payload.get('decision')}, passed={risk_report.payload.get('all_passed')}, approval_required={risk_report.payload.get('any_approval_required')}")
            if risk_report.payload.get("decision") == "APPROVED":
                # Guard: only execute during the relevant market's hours
                from finance_service.utils.market_hours import is_us_market_open, is_hk_market_open
                _sym_is_hk = symbol.endswith(".HK")
                _market_open = is_hk_market_open() if _sym_is_hk else is_us_market_open()
                if not _market_open:
                    _mkt_name = "HK" if _sym_is_hk else "US"
                    logger.warning(f"Skipping execution for {symbol}: {_mkt_name} market closed")
                    continue
                # Send pre-execution Telegram notification before placing the trade
                if self.telegram_agent and self.telegram_agent.enabled:
                    try:
                        _snap = analysis_report.payload.get("indicators_snapshot") if analysis_report else None
                        _news_score = news_report.payload.get("sentiment_score") if (news_report and news_report.status == "success") else None
                        _news_cats = news_report.payload.get("catalysts") if (news_report and news_report.status == "success") else None
                        # Fetch company name from yfinance (best-effort; cached in prior scan)
                        _company_name = None
                        _pf_cash = None
                        _pf_equity = None
                        try:
                            _sym_snap = await self._get_symbol_snapshot(symbol)
                            if _sym_snap:
                                _company_name = _sym_snap.get("full_name")
                        except Exception:
                            pass
                        # Fetch live portfolio cash/equity for the notification
                        try:
                            if self.portfolio_agent:
                                _pf_report = await asyncio.wait_for(
                                    self.portfolio_agent.get_detailed_portfolio_state(),
                                    timeout=2.0
                                )
                                if _pf_report.status == "success":
                                    _em = _pf_report.payload.get("equity_metrics", {})
                                    _pf_cash = _em.get("current_cash")
                                    _pf_equity = _em.get("total_equity")
                        except Exception:
                            pass
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
                            company_name=_company_name,
                            portfolio_cash=_pf_cash,
                            portfolio_equity=_pf_equity,
                        )
                    except Exception as _tg_err:
                        logger.warning(f"Pre-execution Telegram notification failed: {_tg_err}")
                exec_report = await self.execution_agent.run(risk_report)
                if exec_report.status == "success":
                    await self.event_bus.publish(Event(event_type=Events.TRADE_EXECUTED, data=exec_report.payload))
            # else: require approval, skip for now

        # Send error summary to Telegram if any data fetches failed
        self.last_scan_meta["status"] = "completed"
        self.last_scan_meta["completed_at"] = datetime.utcnow().isoformat()
        self.last_scan_meta["processed_symbols"] = len(symbols)
        self.last_scan_meta["fetch_errors_count"] = len(fetch_errors)

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

        watchlist_symbols = list(self.market_scanner_agent.get_watchlist())
        if not watchlist_symbols:
            logger.info("Watchlist empty — skipping intra-day entry evaluation.")
            return

        logger.info(f"[Tier2-Entry] Evaluating {len(watchlist_symbols)} watchlist symbols for intra-day entries")
        from datetime import datetime, timedelta
        end_date   = datetime.now().date()
        start_date = end_date - timedelta(days=365)

        for symbol in watchlist_symbols:
            # Only evaluate symbols whose market is currently open
            _is_hk = symbol.endswith(".HK")
            if _is_hk and not is_hk_market_open():
                continue
            if not _is_hk and not is_us_market_open():
                continue

            # Skip symbols already at max position size (strategy_agent handles this too,
            # but short-circuit here saves redundant data fetches)
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

                # Pre-execution Telegram notification
                if self.telegram_agent and self.telegram_agent.enabled:
                    try:
                        snapshot = await self._get_symbol_snapshot(symbol)
                        _company_name = (snapshot or {}).get("full_name")
                        _pf_cash, _pf_equity = None, None
                        try:
                            _pf = await asyncio.wait_for(
                                self.portfolio_agent.get_detailed_portfolio_state(), timeout=2.0
                            )
                            if _pf.status == "success":
                                _pf_cash   = _pf.payload.get("equity_metrics", {}).get("current_cash")
                                _pf_equity = _pf.payload.get("equity_metrics", {}).get("total_equity")
                        except Exception:
                            pass
                        await self.telegram_agent.send_pre_execution_notification(
                            symbol=symbol,
                            action=proposal.get("action"),
                            quantity=proposal.get("quantity"),
                            price=proposal.get("target_price"),
                            confidence=proposal.get("confidence", 0),
                            rationale=proposal.get("rationale", "Intra-day entry: rule conditions met"),
                            company_name=_company_name,
                            portfolio_cash=_pf_cash,
                            portfolio_equity=_pf_equity,
                        )
                    except Exception as _e:
                        logger.warning(f"[Tier2-Entry] Pre-execution notification failed: {_e}")

                task_id = f"TIER2-{symbol}-{int(datetime.utcnow().timestamp())}"
                await self.execute_trade_proposal(proposal, task_id)

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
            approval_gate = await get_approval_gate("telegram")
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
        """Execute a trade proposal after Telegram approval, using real broker."""
        try:
            from datetime import datetime
            from finance_service.agents.agent_interface import AgentReport
            from finance_service.core.models import TradeProposal
            from dataclasses import asdict

            trade_proposal = TradeProposal(
                symbol=proposal.get("symbol", ""),
                action=proposal.get("action", "BUY"),
                quantity=proposal.get("quantity", 1.0),
                target_price=proposal.get("target_price"),
                confidence=proposal.get("confidence", 1.0),
            )
            risk_report = AgentReport(
                agent_id="approval_gate",
                status="success",
                message="Manual approval granted",
                payload={
                    "trade_proposals": [asdict(trade_proposal)],
                    "risk_assessments": [],
                    "all_passed": True,
                    "decision": "APPROVED",
                },
            )
            exec_report = await self.execution_agent.run(risk_report)
            if exec_report.status == "success":
                execution_result = exec_report.payload.get("execution_result", {})
                await self.event_bus.publish(Event(
                    event_type=Events.TRADE_EXECUTED,
                    data=exec_report.payload,
                ))
                if self.telegram_agent and self.telegram_agent.enabled:
                    status = execution_result.get("status", "?")
                    filled = execution_result.get("filled_price", proposal.get("target_price"))
                    await self.telegram_agent.send_message(
                        f"✅ Trade Executed: {proposal.get('action')} {proposal.get('quantity')} "
                        f"{proposal.get('symbol')} @ ${filled} [{status}]"
                    )
            else:
                if self.telegram_agent and self.telegram_agent.enabled:
                    await self.telegram_agent.send_message(
                        f"❌ Trade execution failed: {exec_report.message}"
                    )
            logger.info(f"Trade {task_id} execution completed: {exec_report.status}")
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

    async def handle_daily_report(self, event: Event):
        """Dispatch DAILY_REPORT_TRIGGER to HealthAgent."""
        await self.health_agent.run(event_type=Events.DAILY_REPORT_TRIGGER, payload={})

    async def handle_hourly_portfolio_report(self, event: Event):
        """Dispatch HOURLY_PORTFOLIO_TRIGGER to HealthAgent."""
        await self.health_agent.run(event_type=Events.HOURLY_PORTFOLIO_TRIGGER, payload={})

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
            full_name = symbol
            try:
                info = ticker.info or {}
                full_name = info.get("longName") or info.get("shortName") or symbol
            except Exception:
                pass

            return {
                "symbol": symbol,
                "price": float(close),
                "change": float(change) if change is not None else None,
                "volume": int(volume) if volume is not None else None,
                "full_name": full_name,
            }
        except Exception as e:
            logger.debug(f"Snapshot fetch failed for {symbol}: {e}")
            return None


    async def _send_llm_ranking_to_telegram(
        self,
        rankings: list,
        llm_summary: str,
        tokens_used: int = 0,
        market_context: dict = None,
        market: str = "US",
    ):
        """Send LLM stock ranking analysis to Telegram, including regime + macro context."""
        if not rankings:
            return
        if not (self.telegram_agent and self.telegram_agent.enabled):
            return
        chat_id = self.telegram_agent.chat_id
        if not chat_id:
            return

        try:
            market_context = market_context or {}
            market_flag = "🇺🇸" if market == "US" else "🇭🇰"
            lines = [f"🤖 LLM Stock Ranking Analysis {market_flag} {market}"]
            if tokens_used:
                lines.append(f"💰 Tokens used: {tokens_used:,}")

            # --- Regime context block ---
            regime = market_context.get("regime", {})
            if regime:
                risk_icon = "🟢" if regime.get("risk_on") else "🔴"
                vol = regime.get("volatility_regime", "?")
                trend = regime.get("trend_strength", "?")
                lines.append("")
                lines.append(f"🌐 Regime: {risk_icon} " + ("Risk-ON" if regime.get("risk_on") else "Risk-OFF") + f" | Vol: {vol} | Trend: {trend}")

            # --- Macro sentiment block ---
            macro_sent = market_context.get("macro_sentiment_score")
            if macro_sent is not None:
                sent_icon = "🟢" if macro_sent > 0.2 else ("🔴" if macro_sent < -0.2 else "🟡")
                lines.append(f"📰 Macro Sentiment: {sent_icon} {macro_sent:+.2f}")

            if llm_summary:
                lines.append("")
                lines.append("📝 " + llm_summary)

            lines.append("")
            lines.append("🏆 Top Picks:")
            for i, r in enumerate(rankings[:10], 1):
                symbol = r.get("symbol", "?")
                action = r.get("action", "?")
                price = r.get("price", 0.0) or 0.0
                conf = r.get("confidence", 0.0) or 0.0
                lines.append(f"{i}. {symbol}: {action} @ ${price:.2f} (conf: {conf:.2f})")

            message = "\n".join(lines)
            await self.telegram_agent.send_message(chat_id=chat_id, message=message)
            logger.info(f"Sent LLM ranking to Telegram ({market})")
        except Exception as e:
            logger.error(f"Failed to send LLM ranking Telegram: {e}")

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
            market = request.args.get("market", "US")
            debug_bypass_market_hours = request.args.get("debug_bypass_market_hours", "false").lower() in ("1", "true", "yes", "on")
            debug_last_friday = request.args.get("debug_last_friday", "false").lower() in ("1", "true", "yes", "on")
            as_of_date = request.args.get("as_of_date")

            if debug_last_friday and not as_of_date:
                today = datetime.utcnow().date()
                # Python weekday: Monday=0 .. Sunday=6, Friday=4
                days_since_friday = (today.weekday() - 4) % 7
                as_of_date = (today - timedelta(days=days_since_friday)).isoformat()

            payload = {
                "market": market,
                "debug_bypass_market_hours": debug_bypass_market_hours,
            }
            if as_of_date:
                payload["as_of_date"] = as_of_date
            await _orchestrator.event_bus.publish(Event(event_type=Events.MARKET_SCAN_TRIGGER, data=payload))
            return jsonify({
                "status": "queued",
                "trigger": "market_scan",
                "market": market,
                "debug_bypass_market_hours": debug_bypass_market_hours,
                "as_of_date": as_of_date,
            })
        else:
            return jsonify({"error": "unknown trigger_type"}), 400


    @app.route("/api/scan/last")
    async def api_scan_last():
        global _orchestrator
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        return jsonify(_sanitize_floats({"status": "success", "data": _orchestrator.last_scan_meta}))

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

    @app.route("/api/trades/history")
    async def api_trades_history():
        """
        Return trade history with optional filters.

        Query params:
            period  : today | this_week | this_month | this_year  (default: all)
            date    : YYYY-MM-DD  — override period with a specific day
            symbol  : filter by ticker (e.g. ARM)
            side    : BUY or SELL
            limit   : max records to return (default 200)
        """
        global _orchestrator
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503

        from datetime import date, timedelta, timezone

        try:
            period = request.args.get("period", "all").lower()
            date_param = request.args.get("date")
            symbol = request.args.get("symbol")
            side = request.args.get("side")
            try:
                limit = int(request.args.get("limit", 200))
            except (ValueError, TypeError):
                limit = 200

            now_utc = datetime.utcnow()
            today_utc = now_utc.date()
            start: Optional[datetime] = None
            end: Optional[datetime] = None

            if date_param:
                try:
                    d = date.fromisoformat(date_param)
                    start = datetime(d.year, d.month, d.day, 0, 0, 0)
                    end   = datetime(d.year, d.month, d.day, 23, 59, 59)
                except ValueError:
                    return jsonify({"error": f"Invalid date format: {date_param}. Use YYYY-MM-DD."}), 400
            elif period == "today":
                start = datetime(today_utc.year, today_utc.month, today_utc.day, 0, 0, 0)
            elif period == "this_week":
                week_start = today_utc - timedelta(days=today_utc.weekday())
                start = datetime(week_start.year, week_start.month, week_start.day, 0, 0, 0)
            elif period == "this_month":
                start = datetime(today_utc.year, today_utc.month, 1, 0, 0, 0)
            elif period == "this_year":
                start = datetime(today_utc.year, 1, 1, 0, 0, 0)
            # else "all" — no date bounds

            repo = _orchestrator.portfolio_agent.repository
            trades = repo.get_trades_by_date_range(start=start, end=end, symbol=symbol, side=side)
            trades = trades[-limit:]  # newest N

            # Build simple summary counts
            buys  = sum(1 for t in trades if t.get("side", "").upper() == "BUY")
            sells = sum(1 for t in trades if t.get("side", "").upper() == "SELL")
            total_value = sum(
                (t.get("quantity") or 0) * (t.get("price") or 0)
                for t in trades
            )

            return jsonify(_sanitize_floats({
                "status": "success",
                "filter": {
                    "period": date_param if date_param else period,
                    "symbol": symbol,
                    "side": side,
                    "limit": limit,
                },
                "summary": {
                    "count": len(trades),
                    "buys": buys,
                    "sells": sells,
                    "total_trade_value": total_value,
                },
                "trades": trades,
            }))
        except Exception as e:
            logger.error(f"api_trades_history error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/market/watchlist")
    async def api_market_watchlist():
        """Return the current market scanner watchlist with ratings and latest prices (top 10)."""
        global _orchestrator
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        try:
            scanner = _orchestrator.market_scanner_agent
            data_agent = _orchestrator.data_agent
            watchlist = scanner.get_watchlist()  # [{symbol, theme, rating, rank}, ...]
            if not watchlist:
                return jsonify({"status": "success", "data": [], "message": "Watchlist empty"})
            symbols = [item["symbol"] for item in watchlist]
            # Fetch latest prices (blocking I/O -> run in thread)
            prices = await asyncio.to_thread(data_agent.fetch_latest_prices, symbols)
            # Combine
            combined = []
            for item in watchlist:
                sym = item["symbol"]
                combined.append({
                    "symbol": sym,
                    "theme": item.get("theme"),
                    "rating": item.get("rating"),
                    "rank": item.get("rank"),
                    "current_price": prices.get(sym)
                })
            # Sort by rank (ascending) and take top 10
            combined.sort(key=lambda x: x["rank"] if isinstance(x["rank"], (int, float)) else 9999)
            top10 = combined[:10]
            return jsonify(_sanitize_floats({"status": "success", "data": top10}))
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

    @app.route("/admin/force_scan", methods=["POST"])
    async def admin_force_scan():
        """Force a market scan, bypassing market-hours check."""
        global _orchestrator
        if not _orchestrator:
            return jsonify({"error": "Orchestrator not initialized"}), 503
        try:
            report = await _orchestrator.market_scanner_agent.run(data_agent=_orchestrator.data_agent)
            if report.status in ("success", "opportunity"):
                event_data = report.payload.copy()
                event_data["status"] = report.status
                event_data["message"] = report.message
                from finance_service.core.event_bus import Event, Events
                await _orchestrator.event_bus.publish(Event(event_type=Events.MARKET_SCANNED, data=event_data))
                return jsonify({"status": "success", "message": report.message, "symbols": event_data.get("symbols", [])})
            else:
                return jsonify({"status": report.status, "message": report.message})
        except Exception as e:
            logger.error(f"Force scan error: {e}", exc_info=True)
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
