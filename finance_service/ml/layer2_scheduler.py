"""Weekly scheduler for Layer 2 pattern analysis."""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
import pytz

logger = logging.getLogger(__name__)


class Layer2Scheduler:
    """Manages weekly Layer 2 analysis scheduling."""
    
    def __init__(self, learning_agent, run_day: int = 6, run_hour: int = 20, run_minute: int = 0, timezone: str = 'UTC'):
        """
        Initialize Layer 2 scheduler.
        
        Args:
            learning_agent: Reference to LearningAgent instance
            run_day: Day to run analysis (0=Monday, 6=Sunday)
            run_hour: Hour to run (24-hour format)
            run_minute: Minute to run
            timezone: Timezone for scheduling
        """
        self.learning_agent = learning_agent
        self.run_day = run_day
        self.run_hour = run_hour
        self.run_minute = run_minute
        self.timezone = timezone
        self.tz = pytz.timezone(timezone)
        self.is_running = False
        self.next_run: Optional[datetime] = None
        
        logger.info(f"Layer 2 Scheduler initialized: Sunday at {run_hour:02d}:{run_minute:02d} {timezone}")
    
    def _get_next_run_time(self) -> datetime:
        """Calculate next scheduled run time."""
        now = datetime.now(self.tz)
        
        days_until_target = (self.run_day - now.weekday()) % 7
        if days_until_target == 0:
            target_time = now.replace(hour=self.run_hour, minute=self.run_minute, second=0, microsecond=0)
            if target_time <= now:
                days_until_target = 7
        
        next_run = now + timedelta(days=days_until_target)
        next_run = next_run.replace(hour=self.run_hour, minute=self.run_minute, second=0, microsecond=0)
        
        return next_run
    
    async def start_scheduler(self) -> None:
        """Start the weekly scheduler loop."""
        if self.is_running:
            return
        
        self.is_running = True
        logger.info("Layer 2 Scheduler started")
        
        try:
            while self.is_running:
                self.next_run = self._get_next_run_time()
                wait_seconds = (self.next_run - datetime.now(self.tz)).total_seconds()
                
                logger.info(f"Next Layer 2 run: {self.next_run.strftime('%Y-%m-%d %H:%M:%S %Z')} (in {wait_seconds/3600:.1f}h)")
                
                try:
                    await asyncio.sleep(wait_seconds)
                except asyncio.CancelledError:
                    break
                
                if self.is_running:
                    await self._run_weekly_analysis()
        
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
        finally:
            self.is_running = False
    
    async def _run_weekly_analysis(self) -> None:
        """Execute weekly Layer 2 analysis."""
        try:
            now = datetime.now(self.tz).date()
            
            if now.weekday() == 6:
                week_ending = now
            else:
                days_since_sunday = (now.weekday() + 1) % 7
                week_ending = now - timedelta(days=days_since_sunday if days_since_sunday > 0 else 7)
            
            week_ending_str = week_ending.isoformat()
            
            logger.info(f"Starting Layer 2 analysis for week ending {week_ending_str}")
            
            results = await self.learning_agent.layer2_analyze_patterns(week_ending_str)
            
            if results:
                logger.info(f"Layer 2 analysis complete: {len(results)} patterns")
            else:
                logger.warning("Layer 2 analysis returned no results")
        
        except Exception as e:
            logger.error(f"Layer 2 analysis failed: {e}", exc_info=True)
    
    def stop_scheduler(self) -> None:
        """Stop the scheduler."""
        self.is_running = False
    
    def get_status(self) -> dict:
        """Get scheduler status."""
        return {
            'running': self.is_running,
            'next_run': self.next_run.isoformat() if self.next_run else None
        }
