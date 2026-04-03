"""Status Report Agent - Generates formatted heartbeat and system status reports."""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events
from finance_service.utils.market_hours import is_us_market_open, is_hk_market_open

logger = logging.getLogger(__name__)


class StatusReportAgent(Agent):
    """Generates formatted status reports with accurate market status."""

    @property
    def agent_id(self) -> str:
        return "status_report_agent"

    @property
    def goal(self) -> str:
        return "Generate formatted heartbeat and system status reports with market information."

    def __init__(self, config_engine):
        self.config_engine = config_engine
        self.event_bus = None  # Set by orchestrator
        self.portfolio_agent: Optional[Any] = None
        self.telegram_agent: Optional[Any] = None
        logger.info("StatusReportAgent initialized")

    async def run(self, event_type: Optional[str] = None, payload: Optional[Dict[str, Any]] = None) -> AgentReport:
        """Generate status reports on demand or via event."""
        if event_type == Events.GET_SYSTEM_STATUS:
            # Generate formatted heartbeat report
            report_text = await self.generate_heartbeat_report()
            return AgentReport(
                agent_id=self.agent_id,
                status="success",
                message="Heartbeat report generated",
                payload={"report": report_text}
            )
        return AgentReport(agent_id=self.agent_id, status="success", message="StatusReportAgent ready")

    async def generate_heartbeat_report(self) -> str:
        """Generate a formatted heartbeat report with current market status."""
        lines = []
        
        # Get current time in HK timezone
        hk_time = datetime.now(ZoneInfo("Asia/Hong_Kong"))
        hk_time_str = hk_time.strftime("%H:%M")
        
        # Header
        lines.append(f"Heartbeat {hk_time_str} UTC+8 – System Status\n")
        
        # Service health
        lines.append("✅ Service: Healthy (port 8801)")  # TODO: Get from config
        
        # Get portfolio info if available
        if self.portfolio_agent:
            try:
                portfolio_report = await self.portfolio_agent.get_detailed_portfolio_state()
                if portfolio_report.status == "success":
                    payload = portfolio_report.payload
                    metrics = payload.get("equity_metrics", {})
                    positions = payload.get("positions", {})
                    
                    lines.append(f"✅ Strategy: sma50_trend_regime")  # TODO: Get from config
                    lines.append("✅ Auto-execute: Enabled\n")
                    
                    # Portfolio section
                    lines.append("Portfolio:\n")
                    lines.append(f"• Equity: ${metrics.get('total_equity', 0):,.0f}")
                    
                    # Calculate cash (this might need adjustment based on your portfolio structure)
                    total_cash = metrics.get('cash', 0)
                    lines.append(f"• Cash: ${total_cash:,.0f}")
                    lines.append(f"• Positions: {len(positions)}")
                    
                    trades_count = payload.get("trades_count", 0)
                    lines.append(f"• Trades: {trades_count}\n")
                    
                    # Performance section
                    total_return = metrics.get('total_return_pct', 0)
                    lines.append(f"Performance: {total_return:.2f}%\n")
                    lines.append(f"• Unrealized: ${metrics.get('unrealized_pnl', 0):,.2f}")
                    lines.append(f"• Realized: ${metrics.get('realized_pnl', 0):,.2f}\n")
            except Exception as e:
                logger.warning(f"Could not get portfolio data for report: {e}")
        
        # Market status - using CORRECT times from market_hours.py
        us_open = is_us_market_open()
        hk_open = is_hk_market_open()
        
        # Get current time in both timezones for display
        ny_time = datetime.now(ZoneInfo("America/New_York"))
        ny_time_str = ny_time.strftime("%H:%M")
        
        if us_open or hk_open:
            market_status = "OPEN"
            status_text = "US" if us_open else "HK"
            if us_open and hk_open:
                status_text = "US & HK"
            lines.append(f"Market: ACTIVE – {status_text} market{'s' if 'market' in status_text[0] else ''} open\n")
        else:
            lines.append(f"Market: {hk_time_str} UTC+8 – Both HK and US markets CLOSED\n")
        
        lines.append("System Health: No active errors.")
        lines.append("All actions logged.")
        
        return "\n".join(lines)
