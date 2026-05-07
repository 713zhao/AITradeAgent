"""Health Monitoring Agent

Monitors portfolio performance and system health.
Sends alerts if drawdown exceeds thresholds or system issues detected.
"""

import logging
from finance_service.core.flow_logger import flow
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events
from finance_service.agents.portfolio_agent import PortfolioAgent
from finance_service.agents.telegram_agent import TelegramAgent
from finance_service.core.remediation_helper import RemediationHelper
from pathlib import Path

logger = logging.getLogger(__name__)

class HealthAgent(Agent):
    """Health Monitoring Agent - Checks portfolio health and system status."""
    
    @property
    def agent_id(self) -> str:
        return "health_agent"
    
    @property
    def goal(self) -> str:
        return "Monitor portfolio performance and system health, raise alerts on anomalies."
    
    def __init__(self, config_engine):
        self.config_engine = config_engine
        self.event_bus = None  # Set by orchestrator
        self.portfolio_agent: Optional[PortfolioAgent] = None
        self.telegram_agent: Optional[TelegramAgent] = None
        self.market_scanner_agent = None
        self.data_agent = None
        self.market_scanner_agent = None
        self.data_agent = None
        self.market_scanner_agent = None
        self.data_agent = None
        
        # Alert thresholds (read from config/YAML if available)
        try:
            self.drawdown_warning_pct = config_engine.get("health", "drawdown_warning_pct", default=10.0)
            self.drawdown_critical_pct = config_engine.get("health", "drawdown_critical_pct", default=20.0)
            self.check_interval_hours = config_engine.get("health", "check_interval_hours", default=4)
            self.alert_cooldown_hours = config_engine.get("health", "alert_cooldown_hours", default=4)
        except AttributeError:
            # config_engine may be a plain dict; fallback to defaults
            self.drawdown_warning_pct = 10.0
            self.drawdown_critical_pct = 20.0
            self.check_interval_hours = 4
            self.alert_cooldown_hours = 4
        
        self.last_alert_time: Optional[datetime] = None
        self._hourly_price_refresh_lock = asyncio.Lock()
        
        # Initialize remediation helper for auto-recovery
        try:
            workspace = Path(__file__).parent.parent.parent.parent
            venv = workspace / "venv"
            self.remediation = RemediationHelper(
                config={},
                venv_path=str(venv),
                workspace_path=str(workspace)
            )
        except Exception as e:
            logger.warning(f"Failed to initialize remediation helper: {e}")
            self.remediation = None
        
        logger.info("HealthAgent initialized")
    
    async def run(self, event_type: Optional[str] = None, payload: Optional[Dict[str, Any]] = None) -> AgentReport:
        """
        Run health checks.
        Can be triggered by timer (SCHEDULE_HEALTH_CHECK), trade events, or manually.
        """
        if event_type == Events.SCHEDULE:
            # Periodic health check
            return await self.perform_health_check()
        
        elif event_type == Events.TRADE_EXECUTED:
            # Trade execution notification
            await self.send_trade_notification(payload)
            return AgentReport(agent_id=self.agent_id, status="success", message="Trade notification sent")
        
        elif event_type == Events.DAILY_REPORT_TRIGGER:
            # Daily summary after market close
            await self.send_daily_summary()
            return AgentReport(agent_id=self.agent_id, status="success", message="Daily summary sent")
        
        elif event_type == Events.HOURLY_PORTFOLIO_TRIGGER:
            await self.send_hourly_portfolio_report()
            return AgentReport(agent_id=self.agent_id, status="success", message="Hourly portfolio report sent")

        elif event_type == Events.GET_SYSTEM_STATUS:
            # Return health status for system status query
            health_report = await self.get_health_status()
            return AgentReport(agent_id=self.agent_id, status="success", message="Health status", payload=health_report)
        
        return AgentReport(agent_id=self.agent_id, status="success", message="HealthAgent is running.")
    
    async def perform_health_check(self) -> AgentReport:
        """Perform portfolio and system health checks."""
        flow("HealthAgent", "CHECK", "performing health check")
        logger.info("HealthAgent performing health check")
        
        # Get portfolio agent from orchestrator (injected)
        if not self.portfolio_agent:
            return AgentReport(agent_id=self.agent_id, status="error", message="PortfolioAgent not set")
        
        # Get recent portfolio metrics
        portfolio_report = await self.portfolio_agent.get_detailed_portfolio_state()
        if portfolio_report.status != "success":
            logger.warning(f"Portfolio state retrieval failed: {portfolio_report.message}")
            
            # Attempt auto-remediation for critical issues
            if self.remediation and ("500" in str(portfolio_report.message) or "async" in str(portfolio_report.message).lower()):
                logger.info("Triggering auto-remediation for portfolio error")
                issue_detail = f"portfolio_error: {portfolio_report.message}"
                fix_result = await self.remediation.attempt_fix("portfolio_state_error", issue_detail)
                logger.info(f"Remediation result: {fix_result}")
                
                # If remediation succeeded, retry portfolio state fetch
                if fix_result.success:
                    logger.info("Remediation succeeded, retrying portfolio state fetch")
                    import asyncio
                    await asyncio.sleep(2)  # Wait for service to fully restart
                    portfolio_report = await self.portfolio_agent.get_detailed_portfolio_state()
                    if portfolio_report.status == "success":
                        logger.info("Portfolio state fetch successful after remediation")
                    else:
                        logger.error(f"Portfolio state still failing after remediation: {portfolio_report.message}")
                        return AgentReport(agent_id=self.agent_id, status="error", message=f"Failed to get portfolio state even after remediation: {portfolio_report.message}")
                else:
                    return AgentReport(agent_id=self.agent_id, status="error", message=f"Failed to get portfolio state and remediation failed: {fix_result.reason}")
            else:
                return AgentReport(agent_id=self.agent_id, status="error", message=f"Failed to get portfolio state: {portfolio_report.message}")
        
        metrics = portfolio_report.payload.get("equity_metrics", {})
        drawdown = metrics.get("drawdown_pct", 0)
        total_return = metrics.get("total_return_pct", 0)
        total_equity = metrics.get("total_equity", 0)
        initial_cash = metrics.get("initial_cash", 0)
        
        alerts = []
        status = "healthy"
        
        # Drawdown alert
        if drawdown >= self.drawdown_critical_pct:
            alerts.append(f"⚠️ CRITICAL Drawdown: {drawdown:.2f}% (threshold: {self.drawdown_critical_pct}%)")
            status = "critical"
        elif drawdown >= self.drawdown_warning_pct:
            alerts.append(f"⚠️ WARNING Drawdown: {drawdown:.2f}% (threshold: {self.drawdown_warning_pct}%)")
            status = "warning"
        
        # Equity below initial capital?
        if total_equity < initial_cash * 0.9:
            alerts.append(f"📉 Equity below 90% of initial: ${total_equity:,.2f} vs ${initial_cash:,.2f}")

        # yFinance / price fetch errors from portfolio agent
        if self.portfolio_agent and getattr(self.portfolio_agent, "last_price_fetch_error", None):
            await self.send_error_alert(
                "Price Fetch Error",
                [self.portfolio_agent.last_price_fetch_error]
            )

        # Check if we sent an alert recently and are in cooldown
        now = datetime.utcnow()
        if alerts and self.last_alert_time:
            if (now - self.last_alert_time).total_seconds() < self.alert_cooldown_hours * 3600:
                logger.info(f"Health check alerts generated but in cooldown (last alert {self.last_alert_time})")
                alerts = [f"(cooldown) {a}" for a in alerts]
            else:
                # New alert outside cooldown, send Telegram
                await self.send_telegram_alert(alerts, metrics)
                self.last_alert_time = now
        elif alerts:
            await self.send_telegram_alert(alerts, metrics)
            self.last_alert_time = now
        
        health_status = {
            "status": status,
            "drawdown_pct": drawdown,
            "total_return_pct": total_return,
            "total_equity": total_equity,
            "initial_cash": initial_cash,
            "alerts": alerts,
            "checked_at": now.isoformat()
        }
        
        flow("HealthAgent", "DONE", f"status={status} drawdown={drawdown:.1f}% equity=${total_equity:,.0f}")
        return AgentReport(agent_id=self.agent_id, status="success", message="Health check completed", payload=health_status)
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Return latest health status (simplified for system status queries)."""
        # Could cache the last result? For now, run a quick check
        report = await self.perform_health_check()
        return report.payload if report.status == "success" else {"error": report.message}
    
    async def send_telegram_alert(self, alerts: list, metrics: Dict[str, Any]):
        """Send alert message via TelegramAgent."""
        if not self.telegram_agent or not self.telegram_agent.enabled:
            logger.warning("TelegramAgent not configured or disabled, cannot send alerts")
            return
        
        chat_id = self.telegram_agent.chat_id
        if not chat_id:
            logger.warning("TelegramAgent has no chat_id configured, cannot send alerts")
            return
        
        message_lines = ["🦞 AiTradeAgent Health Alert 🦞\n"]
        for alert in alerts:
            message_lines.append(f"• {alert}")
        message_lines.append("\n📊 Current Metrics:")
        message_lines.append(f"Equity: ${metrics.get('total_equity', 0):,.2f}")
        message_lines.append(f"Total Return: {metrics.get('total_return_pct', 0):.2f}%")
        message_lines.append(f"Drawdown: {metrics.get('drawdown_pct', 0):.2f}%")
        message_lines.append(f"Positions: {metrics.get('position_count', 0)}")
        message_lines.append(f"Trades: {metrics.get('trade_count', 0)}")
        
        message = "\n".join(message_lines)
        await self.telegram_agent.send_message(chat_id=chat_id, message=message)
        logger.info(f"Sent health alert via Telegram with {len(alerts)} alerts")

    async def send_error_alert(self, title: str, details: List[str]) -> None:
        """Send a system/operational error alert to Telegram."""
        if not self.telegram_agent or not self.telegram_agent.enabled:
            logger.warning("TelegramAgent not configured, cannot send error alert")
            return
        chat_id = self.telegram_agent.chat_id
        if not chat_id:
            return
        lines = [f"🚨 *{title}*"]
        for d in details:
            lines.append(f"  • {d}")
        message = "\n".join(lines)
        try:
            await self.telegram_agent.send_message(chat_id=chat_id, message=message)
            logger.info(f"Sent error alert: {title}")
        except Exception as e:
            logger.error(f"Failed to send error alert: {e}")

    async def send_trade_notification(self, execution_payload: Dict[str, Any]):
        """Send trade execution notification via Telegram."""
        if not self.telegram_agent or not self.telegram_agent.enabled:
            logger.warning("TelegramAgent not configured or disabled, cannot send trade notification")
            return
        
        chat_id = self.telegram_agent.chat_id
        if not chat_id:
            logger.warning("TelegramAgent has no chat_id configured, cannot send trade notification")
            return
        
        # Handle both wrapped (execution_result inside) and unwrapped payloads
        result = execution_payload.get("execution_result", execution_payload)
        symbol = result.get("symbol", "Unknown")
        action = result.get("action", "??")
        quantity = result.get("quantity", 0)
        price = result.get("filled_price", result.get("price", 0))
        status = result.get("status", "??")
        reason = result.get("reason", "")
        realized_pnl = result.get("realized_pnl", 0.0)
        pnl_pct = result.get("pnl_pct", 0.0)
        hold_days = result.get("hold_days", 0)
        
        # Get current portfolio info for context (with timeout to avoid blocking)
        portfolio_summary = "Portfolio info unavailable"
        if self.portfolio_agent:
            try:
                portfolio_report = await asyncio.wait_for(
                    self.portfolio_agent.get_detailed_portfolio_state(),
                    timeout=2.0
                )
                if portfolio_report.status == "success":
                    portfolio = portfolio_report.payload
                    metrics = portfolio.get("equity_metrics", {})
                    cash = metrics.get("current_cash", 0)
                    equity = metrics.get("total_equity", 0)
                    pos_value = equity - cash
                    n_positions = len(portfolio.get("positions", []))
                    portfolio_summary = (
                        f"Cash: ${cash:,.2f}  |  Positions: ${pos_value:,.2f} ({n_positions} open)  |  Equity: ${equity:,.2f}"
                    )
            except asyncio.TimeoutError:
                logger.warning("Portfolio state fetch timed out in trade notification; proceeding without portfolio context")
            except Exception as e:
                logger.warning(f"Could not get portfolio state for trade notification: {e}")
        
        message = f"🦞 Trade Executed\n"
        message += f"• Symbol: {symbol}\n"
        message += f"• Action: {action}\n"
        message += f"• Quantity: {quantity}\n"
        message += f"• Price: ${price:,.2f}\n"
        message += f"• Status: {status}\n"
        message += f"\n{portfolio_summary}"
        
        await self.telegram_agent.send_message(chat_id=chat_id, message=message)
        logger.info(f"Sent trade notification for {symbol} {action}")
    
    async def send_daily_summary(self):
        """Send daily portfolio summary after market close."""
        if not self.telegram_agent or not self.telegram_agent.enabled:
            logger.warning("TelegramAgent not configured or disabled, cannot send daily summary")
            return

        if not self.portfolio_agent:
            logger.warning("PortfolioAgent not set, cannot send daily summary")
            return

        chat_id = self.telegram_agent.chat_id
        if not chat_id:
            logger.warning("TelegramAgent has no chat_id configured, cannot send daily summary")
            return

        try:
            portfolio_report = await asyncio.wait_for(
                self.portfolio_agent.get_detailed_portfolio_state(),
                timeout=5.0
            )
            if portfolio_report.status != "success":
                logger.error(f"Failed to get portfolio state for daily summary: {portfolio_report.message}")
                return

            metrics = portfolio_report.payload.get("equity_metrics", {})
            _raw_positions = portfolio_report.payload.get("positions", [])
            # positions may be a list of dicts or a dict keyed by symbol — normalise to dict
            if isinstance(_raw_positions, list):
                positions = {p["symbol"]: p for p in _raw_positions if "symbol" in p}
            else:
                positions = _raw_positions

            # Get today's trades via date-range query
            from datetime import date
            today = date.today()
            today_trades = []
            if self.portfolio_agent.repository:
                today_dt = datetime(today.year, today.month, today.day, 0, 0, 0)
                today_trades = self.portfolio_agent.repository.get_trades_by_date_range(start=today_dt)

            # Fetch company names for open positions (best-effort, no timeout extension)
            company_names: dict = {}
            try:
                import yfinance as yf
                for sym in list(positions.keys()):
                    try:
                        info = yf.Ticker(sym).info or {}
                        company_names[sym] = info.get("longName") or info.get("shortName") or sym
                    except Exception:
                        company_names[sym] = sym
            except Exception:
                pass

            equity = metrics.get("total_equity", 0)
            cash   = metrics.get("current_cash", 0)
            gross  = metrics.get("gross_position_value", 0)
            ret    = metrics.get("total_return_pct", 0.0)
            dd     = metrics.get("drawdown_pct", 0.0)

            lines = [f"📊 *Daily Portfolio Summary — {today}*\n"]
            lines.append(f"💼 Equity: *${equity:,.2f}*  |  Return: {ret:+.2f}%  |  Drawdown: {dd:.2f}%")
            lines.append(f"💵 Cash: ${cash:,.2f}   📈 Positions: ${gross:,.2f}")
            lines.append(f"🔢 Trades today: {len(today_trades)}  |  Open positions: {len(positions)}\n")

            if positions:
                lines.append("*Open Positions:*")
                lines.append("```")
                lines.append(f"{'Symbol':<6} {'Name':<22} {'Qty':>5} {'Avg':>8} {'Value':>10} {'Wt':>6}")
                lines.append("-" * 62)
                for sym, pos in sorted(positions.items()):
                    mv  = pos.get("market_value", pos.get("cost_basis", 0))
                    qty = pos.get("quantity", 0)
                    avg = pos.get("avg_cost", 0)
                    wt  = mv / equity * 100 if equity else 0
                    name = (company_names.get(sym) or sym)[:22]
                    lines.append(f"{sym:<6} {name:<22} {qty:>5} {avg:>8.2f} {mv:>10,.0f} {wt:>5.1f}%")
                lines.append("```")

            if today_trades:
                lines.append("\n*Today\'s Trades:*")
                for t in today_trades[-10:]:
                    sym  = t.get("symbol", "?")
                    side = t.get("side", "?")
                    qty  = t.get("quantity") or t.get("filled_quantity") or 0
                    px   = t.get("price", 0)
                    ts   = (t.get("ordered_at") or "")[:16].replace("T", " ")
                    lines.append(f"  {side} {sym} ×{qty} @ ${px:.2f}  ({ts})")

            message = "\n".join(lines)
            await self.telegram_agent.send_message(chat_id=chat_id, message=message, parse_mode="Markdown")
            logger.info("Sent daily portfolio summary")
        except asyncio.TimeoutError:
            logger.error("Portfolio state fetch timed out for daily summary; cannot send summary")
        except Exception as e:
            logger.error(f"Error sending daily summary: {e}")

    async def send_hourly_portfolio_report(self):
        """Send a compact hourly portfolio summary — only while a market is open."""
        from finance_service.utils.market_hours import is_us_market_open, is_hk_market_open
        us_open = is_us_market_open()
        hk_open = is_hk_market_open()
        if not (us_open or hk_open):
            logger.info("Hourly portfolio report: markets closed, skipping.")
            return

        if not self.telegram_agent or not self.telegram_agent.enabled:
            logger.warning("TelegramAgent not configured; skipping hourly report")
            return
        chat_id = self.telegram_agent.chat_id
        if not chat_id:
            return

        try:
            # Always refresh prices for held positions before the hourly report.
            # Use force_held=True to bypass the market-hours filter — this ensures
            # US positions get their latest available price even during HK-only hours.
            # Stale = either all prices == avg_cost (fresh restart) OR positions
            # haven't been updated in more than STALE_MINUTES minutes.
            STALE_MINUTES = 20
            price_fetch_status = "skipped"
            price_fetch_count = 0
            price_fetch_error = None
            if self.market_scanner_agent and self.data_agent and self.portfolio_agent and not self._hourly_price_refresh_lock.locked():
                live_positions = self.portfolio_agent.repository.get_positions()
                held = [p.symbol for p in live_positions]
                now_dt = datetime.utcnow()
                # Check age: most recent position update
                max_age_mins = None
                if live_positions:
                    oldest = min(p.updated_at.replace(tzinfo=None) if p.updated_at.tzinfo else p.updated_at
                                 for p in live_positions)
                    max_age_mins = (now_dt - oldest).total_seconds() / 60
                all_same_as_cost = (
                    len(live_positions) > 0 and
                    all(abs(p.current_price - p.avg_cost) < 0.01 for p in live_positions)
                )
                prices_stale = all_same_as_cost or (max_age_mins is not None and max_age_mins > STALE_MINUTES)
                if prices_stale:
                    age_desc = f"{max_age_mins:.0f}m old" if max_age_mins is not None else "age unknown"
                    reason = "current_price==avg_cost" if all_same_as_cost else age_desc
                    logger.info(f"Hourly report: prices stale ({reason}), fetching live prices (force_held=True)")
                    try:
                        async with self._hourly_price_refresh_lock:
                            scan_report = await asyncio.wait_for(
                                self.market_scanner_agent.refresh_watchlist_prices(
                                    data_agent=self.data_agent,
                                    held_symbols=held,
                                    force_held=True,
                                ),
                                timeout=90.0
                            )
                        if scan_report and scan_report.status == "success":
                            price_dict = {item["symbol"]: item["price"]
                                          for item in scan_report.payload.get("prices", [])}
                            if price_dict:
                                self.portfolio_agent.repository.update_position_prices(price_dict)
                                price_fetch_count = len(price_dict)
                                price_fetch_status = "refreshed"
                                logger.info(f"Hourly report: applied {price_fetch_count} fresh price updates")
                            else:
                                price_fetch_status = "no_data"
                        else:
                            price_fetch_status = "failed"
                            price_fetch_error = scan_report.message if scan_report else "unknown"
                    except asyncio.TimeoutError:
                        price_fetch_status = "timeout"
                        price_fetch_error = "yfinance fetch timed out (>60s)"
                        logger.warning("Hourly report: price refresh timed out, using cached prices")
                    except Exception as e:
                        price_fetch_status = "error"
                        price_fetch_error = str(e)
                        logger.warning(f"Hourly report: price refresh failed ({e}), using cached prices")
                else:
                    price_fetch_status = "fresh"
                    logger.info(f"Hourly report: prices fresh ({max_age_mins:.0f}m old), skipping pre-refresh")

            portfolio_report = await asyncio.wait_for(
                self.portfolio_agent.get_detailed_portfolio_state(),
                timeout=5.0
            )
            if portfolio_report.status != "success":
                logger.error(f"Hourly report: portfolio fetch failed: {portfolio_report.message}")
                return

            metrics   = portfolio_report.payload.get("equity_metrics", {})
            _raw_pos  = portfolio_report.payload.get("positions", [])
            # normalise to dict keyed by symbol
            if isinstance(_raw_pos, list):
                positions = {p["symbol"]: p for p in _raw_pos if "symbol" in p}
            else:
                positions = _raw_pos
            equity    = metrics.get("total_equity", 0)
            cash      = metrics.get("current_cash", 0)
            gross     = metrics.get("gross_position_value", 0)
            ret       = metrics.get("total_return_pct", 0.0)
            dd        = metrics.get("drawdown_pct", 0.0)
            n_pos     = len(positions)

            # Which market(s) open right now?
            open_markets = []
            if us_open:
                open_markets.append("🇺🇸 US")
            if hk_open:
                open_markets.append("🇭🇰 HK")
            market_str = " & ".join(open_markets) + " market open"

            now_utc = datetime.utcnow().strftime("%H:%M UTC")

            unrealized_pnl = metrics.get("unrealized_pnl", 0.0)
            realized_pnl   = metrics.get("realized_pnl", 0.0)
            total_pnl      = metrics.get("total_pnl", unrealized_pnl + realized_pnl)
            pnl_sign  = "+" if total_pnl >= 0 else ""
            upnl_sign = "+" if unrealized_pnl >= 0 else ""

            # Data freshness indicator
            if price_fetch_status == "refreshed":
                data_line = f"🔄 Prices: just updated ({price_fetch_count} symbols)"
            elif price_fetch_status == "fresh":
                data_line = f"✅ Prices: live (updated <{STALE_MINUTES}m ago)"
            elif price_fetch_status in ("timeout", "error", "failed"):
                data_line = f"⚠️ Prices: stale — fetch failed ({price_fetch_error})"
            elif price_fetch_status == "no_data":
                data_line = f"⚠️ Prices: no data returned by yfinance — may be rate-limited"
            else:
                data_line = "ℹ️ Prices: cached"

            lines = [f"⏰ *Hourly Portfolio — {now_utc}* ({market_str})\n"]
            lines.append(f"💼 Equity: *${equity:,.2f}*  |  Return: {ret:+.2f}%  |  Drawdown: {dd:.2f}%")
            lines.append(f"💵 Cash: ${cash:,.2f}   📈 Positions: ${gross:,.2f}  ({n_pos} open)")
            lines.append(f"📊 P&L: *{pnl_sign}${total_pnl:,.2f}*  (Unrealized: {upnl_sign}${unrealized_pnl:,.2f}  |  Realized: ${realized_pnl:,.2f})")
            lines.append(f"{data_line}\n")

            if positions:
                lines.append("*Positions:*")
                lines.append("```")
                lines.append(f"{'Sym':<6} {'Qty':>5} {'Avg':>7} {'Cur':>7} {'P&L':>9} {'%':>6}")
                lines.append("-" * 45)
                for sym, pos in sorted(positions.items()):
                    qty      = pos.get("quantity", 0)
                    avg      = pos.get("avg_cost", 0)
                    cur      = pos.get("current_price", avg)
                    upnl     = pos.get("unrealized_pnl", (cur - avg) * qty)
                    upnl_pct = pos.get("unrealized_pnl_pct", ((cur - avg) / avg * 100) if avg else 0)
                    sign     = "+" if upnl >= 0 else ""
                    lines.append(f"{sym:<6} {qty:>5} {avg:>7.2f} {cur:>7.2f} {sign}{upnl:>8,.0f} {upnl_pct:>+5.1f}%")
                lines.append("```")
                lines.append("")
                lines.append("*Allocation:*")
                lines.append("```")
                lines.append(f"{'Sym':<6} {'Qty':>5} {'Avg':>8} {'Value':>10} {'Wt':>6}")
                lines.append("-" * 40)
                for sym, pos in sorted(positions.items()):
                    mv  = pos.get("market_value", pos.get("cost_basis", 0))
                    qty = pos.get("quantity", 0)
                    avg = pos.get("avg_cost", 0)
                    wt  = mv / equity * 100 if equity else 0
                    lines.append(f"{sym:<6} {qty:>5} {avg:>8.2f} {mv:>10,.0f} {wt:>5.1f}%")
                lines.append("```")

            message = "\n".join(lines)
            await self.telegram_agent.send_message(chat_id=chat_id, message=message, parse_mode="Markdown")
            logger.info(f"Sent hourly portfolio report ({n_pos} positions)")
        except asyncio.TimeoutError:
            logger.error("Hourly report: portfolio state fetch timed out")
        except Exception as e:
            logger.error(f"Error in hourly portfolio report: {e}")
