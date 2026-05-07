#!/usr/bin/env python3
"""Simulate a trade to test Telegram notifications."""
import asyncio
import sys
from pathlib import Path

# Add workspace to path
workspace = Path("/home/eric/.openclaw/workspace/AITradeAgent")
sys.path.insert(0, str(workspace))

from finance_service.core.event_bus import get_event_bus, Event, Events
from finance_service.agents.health_agent import HealthAgent
from finance_service.agents.telegram_agent import TelegramAgent
from finance_service.core.config import Config
from finance_service.agents.agent_interface import AgentReport
from finance_service.portfolio.trade_repository import TradeRepository
from finance_service.agents.portfolio_agent import PortfolioAgent

async def main():
    # Initialize TelegramAgent (bot ready to send)
    telegram_agent = TelegramAgent({})
    if not telegram_agent.enabled:
        print("ERROR: TelegramAgent not enabled (missing token/chat_id)")
        return
    print(f"TelegramAgent enabled with chat_id={telegram_agent.chat_id}")

    # Initialize HealthAgent with telegram_agent injected
    health_agent = HealthAgent(config_engine=Config)
    health_agent.telegram_agent = telegram_agent

    # Build a mock execution result (as would be passed from ExecutionAgent)
    execution_result = {
        "symbol": "NVDA",
        "action": "BUY",
        "quantity": 10,
        "price": 150.25,
        "commission": 0.0,
        "status": "FILLED",
        "order_id": "SIM_ORDER_001",
        "timestamp": "2026-03-28T05:00:00"
    }

    print("Simulating trade execution for NVDA BUY 10 @ $150.25")
    # Call health agent to send notification
    await health_agent.run(event_type=Events.TRADE_EXECUTED, payload=execution_result)
    print("Trade notification sent (or skipped if disabled). Check Telegram.")

    # Also update portfolio to reflect the trade (optional)
    portfolio_agent = PortfolioAgent({})
    repo = TradeRepository()
    portfolio_agent.repository = repo
    portfolio_agent.config = {}
    portfolio_report = await portfolio_agent.run(event_type=Events.TRADE_EXECUTED, payload=execution_result)
    print(f"Portfolio update status: {portfolio_report.status}")

if __name__ == "__main__":
    asyncio.run(main())
