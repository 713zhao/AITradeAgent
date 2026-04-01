"""Health Monitoring Agent

Monitors portfolio performance and system health.
Sends alerts if drawdown exceeds thresholds or system issues detected.
"""

import logging
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
        
        elif event_type == Events.GET_SYSTEM_STATUS:
            # Return health status for system status query
            health_report = await self.get_health_status()
            return AgentReport(agent_id=self.agent_id, status="success", message="Health status", payload=health_report)
        
        return AgentReport(agent_id=self.agent_id, status="success", message="HealthAgent is running.")
    
    async def perform_health_check(self) -> AgentReport:
        """Perform portfolio and system health checks."""
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
                    equity = portfolio.get("equity_metrics", {}).get("total_equity", 0)
                    positions = len(portfolio.get("positions", {}))
                    portfolio_summary = f"Portfolio: ${equity:,.2f}, {positions} positions"
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
                timeout=3.0
            )
            if portfolio_report.status != "success":
                logger.error(f"Failed to get portfolio state for daily summary: {portfolio_report.message}")
                return
        except asyncio.TimeoutError:
            logger.error("Portfolio state fetch timed out for daily summary; cannot send summary")
            return
        except Exception as e:
            logger.error(f"Error fetching portfolio state for daily summary: {e}")
            return
            
            metrics = portfolio_report.payload.get("equity_metrics", {})
            positions = portfolio_report.payload.get("positions", {})
            
            # Get today's trades
            from datetime import date
            today = date.today()
            trades = []
            if self.portfolio_agent.repository:
                all_trades = self.portfolio_agent.repository.get_all_trades()
                for t in all_trades:
                    trade_date = datetime.fromisoformat(t.get("timestamp", "")).date()
                    if trade_date == today:
                        trades.append(t)
            
            summary_lines = [f"📊 Daily Portfolio Summary - {today}\n"]
            summary_lines.append(f"Equity: ${metrics.get('total_equity', 0):,.2f}")
            summary_lines.append(f"Total Return: {metrics.get('total_return_pct', 0):.2f}%")
            summary_lines.append(f"Drawdown: {metrics.get('drawdown_pct', 0):.2f}%")
            summary_lines.append(f"Positions: {len(positions)}")
            summary_lines.append(f"Trades Today: {len(trades)}")
            
            if positions:
                summary_lines.append("\nCurrent Positions:")
                for sym, pos in positions.items():
                    summary_lines.append(f"  {sym}: {pos.quantity} @ ${pos.avg_cost:.2f}")
            
            if trades:
                summary_lines.append("\nToday's Trades:")
                for t in trades[-10:]:  # last 10 trades
                    summary_lines.append(f"  {t.get('action')} {t.get('symbol')} x{t.get('quantity')} @ ${t.get('price'):,.2f}")
            
            message = "\n".join(summary_lines)
            await self.telegram_agent.send_message(chat_id=chat_id, message=message)
            logger.info("Sent daily portfolio summary")
            
        except Exception as e:
            logger.error(f"Error sending daily summary: {e}")
