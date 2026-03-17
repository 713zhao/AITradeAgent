import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Callable, Awaitable, Optional

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.events import Event, Events, get_event_bus

logger = logging.getLogger(__name__)


class SchedulerAgent(Agent):
    """Scheduler Agent - Manages and executes scheduled tasks."""

    @property
    def agent_id(self) -> str:
        return "scheduler_agent"

    @property
    def goal(self) -> str:
        return "Automate the execution of periodic tasks, such as market scanning, data fetching, and report generation."

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.event_bus = get_event_bus()
        self.scheduled_tasks: Dict[str, asyncio.Task] = {}
        logger.info(f"SchedulerAgent initialized with config: {self.config}")
        # Auto-start scheduling tasks in the background upon initialization
        # We'll create a task to run the scheduler setup, but it's better to be started by orchestrator
        # For now, we mark that we are ready; actual scheduling will be triggered by orchestrator calling run()
    
    async def run(self) -> Optional[AgentReport]:
        """Starts the scheduler, running predefined tasks."""
        if self.scheduled_tasks:
            # Already started
            return AgentReport(agent_id=self.agent_id, status="success", message="SchedulerAgent already running.")
        
        logger.info("SchedulerAgent starting tasks...")
        try:
            # Example: Schedule a daily market scan event
            self._schedule_task(
                "daily_market_scan",
                self._trigger_daily_market_scan,
                timedelta(minutes=1)  # For testing, run every minute
            )
            # Example: Schedule an hourly data refresh event
            self._schedule_task(
                "hourly_data_refresh",
                self._trigger_hourly_data_refresh,
                timedelta(minutes=5)  # For testing, run every 5 minutes
            )
            # Schedule periodic health check every 4 hours
            self._schedule_task(
                "health_check",
                self._trigger_health_check,
                timedelta(hours=4)
            )
            # Schedule daily report at a specific hour (e.g., 17:00 local time), simplified here to run every 24 hours after start
            self._schedule_task(
                "daily_report",
                self._trigger_daily_report,
                timedelta(hours=24)
            )

            logger.info("SchedulerAgent tasks initiated.")
            return AgentReport(agent_id=self.agent_id, status="success", message="SchedulerAgent started.")
        except Exception as e:
            logger.error(f"Error starting SchedulerAgent: {e}")
            return AgentReport(agent_id=self.agent_id, status="error", message=f"Failed to start SchedulerAgent: {e}")

    async def _trigger_daily_report(self):
        await self.event_bus.publish(Event(event_type=Events.DAILY_REPORT_TRIGGER, data={}))
        logger.info("Published DAILY_REPORT_TRIGGER event.")
    
    def _schedule_task(self, task_name: str, coro: Callable[..., Awaitable[None]], interval: timedelta):
        """Schedules an async coroutine to run at a fixed interval."""
        async def task_wrapper():
            # Initial delay to space out tasks
            await asyncio.sleep(interval.total_seconds())
            while True:
                try:
                    logger.info(f"Executing scheduled task: {task_name}")
                    await coro()
                except Exception as e:
                    logger.error(f"Error in scheduled task {task_name}: {e}", exc_info=True)
                await asyncio.sleep(interval.total_seconds())

        # Cancel existing task if it exists
        if task_name in self.scheduled_tasks and not self.scheduled_tasks[task_name].done():
            self.scheduled_tasks[task_name].cancel()

        self.scheduled_tasks[task_name] = asyncio.create_task(task_wrapper())
        logger.info(f"Task {task_name} scheduled to run every {interval}.")

    async def _trigger_daily_market_scan(self):
        # Publish an event that the MainOrchestratorAgent (or MarketScannerAgent) will listen to
        await self.event_bus.publish(Event(event_type=Events.MARKET_SCAN_TRIGGER, data={"interval": "daily"}))
        logger.info("Published MARKET_SCAN_TRIGGER event (daily).")

    async def _trigger_hourly_data_refresh(self):
        # Publish an event to refresh data, which DataAgent might pick up
        await self.event_bus.publish(Event(event_type=Events.DATA_REFRESH_TRIGGER, data={"interval": "hourly"}))
        logger.info("Published DATA_REFRESH_TRIGGER event (hourly).")

    async def _trigger_health_check(self):
        """Publish health check trigger event."""
        await self.event_bus.publish(Event(event_type=Events.HEALTH_CHECK_TRIGGER, data={}))
        logger.info("Published HEALTH_CHECK_TRIGGER event.")
    
    async def stop(self):
        """Stops all scheduled tasks."""
        for task_name, task in self.scheduled_tasks.items():
            if not task.done():
                task.cancel()
                logger.info(f"Cancelled scheduled task: {task_name}")
        await asyncio.gather(*[t for t in self.scheduled_tasks.values() if not t.done()], return_exceptions=True)
        self.scheduled_tasks.clear()
        logger.info("SchedulerAgent stopped all tasks.")

    def __repr__(self) -> str:
        return f"<SchedulerAgent(id='{self.agent_id}')>"
