"""Layer 4 background scheduler — drives ETF Intelligence jobs on a time-based loop."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import pytz

logger = logging.getLogger(__name__)


class Layer4Scheduler:
    """Drives four recurring ETF Intelligence jobs:
      - daily_snapshot    : daily @ 21:30 UTC
      - daily_hedge       : daily @ 22:00 UTC
      - sector_rotation   : weekly, Monday @ 09:00 UTC
      - correlation_scan  : weekly, Sunday @ 20:30 UTC
    """

    def __init__(self, etf_agent, timezone: str = "UTC"):
        self.etf_agent = etf_agent
        self.tz = pytz.timezone(timezone)
        self.next_snapshot: Optional[datetime] = None
        self.next_hedge: Optional[datetime] = None
        self.next_sector_rotation: Optional[datetime] = None
        self.next_correlation: Optional[datetime] = None
        self._running = False

    async def start_scheduler(self):
        self._running = True
        self._refresh_next_runs()
        logger.info("Layer 4 scheduler started.")
        try:
            while self._running:
                jobs = {
                    "daily_snapshot":   self.next_snapshot,
                    "daily_hedge":       self.next_hedge,
                    "sector_rotation":   self.next_sector_rotation,
                    "correlation_scan":  self.next_correlation,
                }
                # Find next job to run
                next_name, next_time = min(jobs.items(), key=lambda kv: kv[1])
                now = datetime.now(tz=pytz.UTC)
                wait = (next_time - now).total_seconds()
                if wait > 0:
                    await asyncio.sleep(min(wait, 60))  # wake at least every 60s
                    continue
                await self._dispatch(next_name)
                self._advance_slot(next_name)
        except asyncio.CancelledError:
            logger.info("Layer 4 scheduler stopped.")
        except Exception as exc:
            logger.error(f"Layer 4 scheduler error: {exc}")

    def stop(self):
        self._running = False

    # ── Manual triggers (for testing / on-demand) ─────────────────────────────

    async def trigger_snapshot(self):
        await self._dispatch("daily_snapshot")

    async def trigger_sector_rotation(self):
        await self._dispatch("sector_rotation")

    async def trigger_hedge(self):
        await self._dispatch("daily_hedge")

    async def trigger_correlation(self):
        await self._dispatch("correlation_scan")

    # ── Internal ───────────────────────────────────────────────────────────────

    def _refresh_next_runs(self):
        now = datetime.now(tz=pytz.UTC)
        self.next_snapshot       = self._next_daily(21, 30, after=now)
        self.next_hedge          = self._next_daily(22,  0, after=now)
        self.next_sector_rotation = self._next_weekly(weekday=0, hour=9,  minute=0,  after=now)
        self.next_correlation    = self._next_weekly(weekday=6, hour=20, minute=30, after=now)

    def _next_daily(self, hour: int, minute: int, after: datetime) -> datetime:
        tz = pytz.UTC
        candidate = after.astimezone(tz).replace(
            hour=hour, minute=minute, second=0, microsecond=0,
        )
        if candidate <= after:
            candidate += timedelta(days=1)
        return candidate

    def _next_weekly(self, weekday: int, hour: int, minute: int, after: datetime) -> datetime:
        """Return next occurrence of (weekday, hour, minute) after `after`.
        weekday: 0=Monday … 6=Sunday (Python convention).
        """
        tz = pytz.UTC
        ref = after.astimezone(tz).replace(hour=hour, minute=minute, second=0, microsecond=0)
        days_ahead = (weekday - ref.weekday()) % 7
        candidate = ref + timedelta(days=days_ahead)
        if candidate <= after:
            candidate += timedelta(weeks=1)
        return candidate

    def _advance_slot(self, job_name: str):
        now = datetime.now(tz=pytz.UTC)
        if job_name == "daily_snapshot":
            self.next_snapshot = self._next_daily(21, 30, after=now)
        elif job_name == "daily_hedge":
            self.next_hedge = self._next_daily(22, 0, after=now)
        elif job_name == "sector_rotation":
            self.next_sector_rotation = self._next_weekly(0, 9, 0, after=now)
        elif job_name == "correlation_scan":
            self.next_correlation = self._next_weekly(6, 20, 30, after=now)

    async def _dispatch(self, job_name: str):
        logger.info(f"Layer 4 dispatch: {job_name}")
        try:
            if job_name == "daily_snapshot":
                await self.etf_agent.run_daily_snapshot()
            elif job_name == "daily_hedge":
                await self.etf_agent.run_hedge_analysis()
            elif job_name == "sector_rotation":
                await self.etf_agent.run_sector_rotation_analysis()
            elif job_name == "correlation_scan":
                await self.etf_agent.run_correlation_scan()
        except Exception as exc:
            logger.error(f"Layer 4 dispatch {job_name} failed: {exc}")
