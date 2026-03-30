import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Callable, Awaitable, Optional

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events, get_event_bus

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

    async def run(self) -> Optional[AgentReport]:
        """Starts the scheduler, running predefined tasks."""
        logger.info("SchedulerAgent starting...")
        try:
            # Schedule tasks with appropriate intervals
            # Tier 1: Discovery scan — daily (runs once then every 24h)
            await self._schedule_task(
                "discovery_scan",
                self._trigger_discovery_scan,
                timedelta(hours=24)
            )
            # Tier 2: Price monitor — every 15 min for watchlist symbols
            await self._schedule_task(
                "price_monitor",
                self._trigger_price_monitor,
                timedelta(minutes=15)
            )
            # Tier 3: Exit check — every 5 min (continuous position monitoring)
            await self._schedule_task(
                "exit_check",
                self._trigger_exit_check,
                timedelta(minutes=5)
            )
            # Data refresh: every 30 minutes (general data warming)
            await self._schedule_task(
                "data_refresh",
                self._trigger_hourly_data_refresh,
                timedelta(minutes=30)
            )
            # Daily health check: every 4 hours
            await self._schedule_task(
                "health_check",
                self._trigger_health_check,
                timedelta(hours=4)
            )
            # Daily summary after market close: run at 16:05 UTC+8 (08:05 UTC) daily
            await self._schedule_task(
                "daily_report",
                self._trigger_daily_report,
                timedelta(days=1)
            )
            
            logger.info("SchedulerAgent tasks initiated.")
            return AgentReport(agent_id=self.agent_id, status="success", message="SchedulerAgent started.")
        except Exception as e:
            logger.error(f"Error starting SchedulerAgent: {e}")
            return AgentReport(agent_id=self.agent_id, status="error", message=f"Failed to start SchedulerAgent: {e}")

    async def _schedule_task(self, task_name: str, coro: Callable[..., Awaitable[None]], interval: timedelta):
        """Schedules an async coroutine to run at a fixed interval."""
        async def task_wrapper():
            while True:
                try:
                    logger.info(f"Executing scheduled task: {task_name}")
                    await coro()
                except asyncio.CancelledError:
                    logger.info(f"Scheduled task {task_name} cancelled, exiting loop.")
                    break
                except Exception as e:
                    logger.error(f"Error in scheduled task {task_name}: {e}", exc_info=True)
                try:
                    await asyncio.sleep(interval.total_seconds())
                except asyncio.CancelledError:
                    logger.info(f"Scheduled task {task_name} sleep cancelled, exiting loop.")
                    break
        
        # Cancel existing task if it exists
        if task_name in self.scheduled_tasks and not self.scheduled_tasks[task_name].done():
            self.scheduled_tasks[task_name].cancel()

        self.scheduled_tasks[task_name] = asyncio.create_task(task_wrapper())
        logger.info(f"Task {task_name} scheduled to run every {interval}.")

    async def _trigger_discovery_scan(self):
        """Tier 1: Full discovery scan — rank universe, build watchlist."""
        await self.event_bus.publish(Event(event_type=Events.MARKET_SCAN_TRIGGER, data={"interval": "daily", "mode": "discovery"}))
        logger.info("Published MARKET_SCAN_TRIGGER event (Tier 1: daily discovery).")

    async def _trigger_price_monitor(self):
        """Tier 2: Lightweight price refresh for watchlist symbols."""
        await self.event_bus.publish(Event(event_type=Events.PRICE_MONITOR_TRIGGER, data={"interval": "15min", "mode": "price_monitor"}))
        logger.info("Published PRICE_MONITOR_TRIGGER event (Tier 2: every 15 min).")

    async def _trigger_exit_check(self):
        """Trigger continuous position monitoring for exits and degradation."""
        await self.event_bus.publish(Event(event_type=Events.EXIT_CHECK_TRIGGER, data={"interval": "5min"}))
        logger.info("Published EXIT_CHECK_TRIGGER event (every 5 min).")

    async def _trigger_hourly_data_refresh(self):
        await self.event_bus.publish(Event(event_type=Events.DATA_REFRESH_TRIGGER, data={"interval": "hourly"}))
        logger.info("Published DATA_REFRESH_TRIGGER event (hourly).")

    async def _trigger_health_check(self):
        await self.event_bus.publish(Event(event_type=Events.SCHEDULE, data={}))
        logger.info("Published SCHEDULE event for health check.")

    async def _trigger_daily_report(self):
        """Trigger daily summary report after market close."""
        await self.event_bus.publish(Event(event_type=Events.DAILY_REPORT_TRIGGER, data={}))
        logger.info("Published DAILY_REPORT_TRIGGER event.")

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
        return f"<SchedulerAgent(id=\'{self.agent_id}\')>"
