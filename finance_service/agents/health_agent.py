"""Health Monitoring Agent

Monitors portfolio performance and system health.
Sends alerts if drawdown exceeds thresholds or system issues detected.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events
from finance_service.agents.portfolio_agent import PortfolioAgent
from finance_service.agents.telegram_agent import TelegramAgent

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
        
        logger.info("HealthAgent initialized")
    
    async def run(self, event_type: Optional[str] = None, payload: Optional[Dict[str, Any]] = None) -> AgentReport:
        """
        Run health checks.
        Can be triggered by timer (SCHEDULE_HEALTH_CHECK) or manually.
        """
        if event_type == Events.SCHEDULE:
            # Periodic health check
            return await self.perform_health_check()
        
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
        if not self.telegram_agent:
            logger.warning("TelegramAgent not configured, cannot send alerts")
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
        # Use default chat ID from config if available, else orchestrator may forward
        await self.telegram_agent.send_message(chat_id=self.config.get("telegram_chat_id", ""), message=message)
        logger.info(f"Sent health alert via Telegram with {len(alerts)} alerts")
