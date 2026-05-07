import logging
import asyncio
import threading
from typing import Callable, Dict, List, Any, Optional, Union
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class Event:
    """Base event class"""
    event_type: str
    timestamp: datetime = field(default_factory=datetime.now)
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = "system"
    
    def __repr__(self) -> str:
        return f"Event(type={self.event_type}, source={self.source}, data_keys={list(self.data.keys())})"


class EventBus:
    """Publish/Subscribe event handling with asyncio support"""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._event_history: List[Event] = []
        self._max_history: int = 1000
        self._lock = asyncio.Lock() # Use asyncio lock for async safety
        logger.info("EventBus initialized for asyncio")

    async def subscribe(self, event_type: str, callback: Callable) -> str:
        """
        Subscribe to an event type. Supports both sync and async callbacks.
        """
        async with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            
            self._subscribers[event_type].append(callback)
            
            sub_id = f"{event_type}_{len(self._subscribers[event_type])}"
            logger.debug(f"Subscribed to {event_type} (id={sub_id})")
            
            return sub_id
    
    async def on(self, event_type: str, callback: Callable) -> str:
        """
        Alias for subscribe - subscribe to an event type.
        """
        return await self.subscribe(event_type, callback)
    
    async def publish(self, event_or_dict: Union[Event, Dict[str, Any]]) -> None:
        """
        Publish an event. Dispatches to all subscribers asynchronously.
        """
        if isinstance(event_or_dict, dict):
            event_type = event_or_dict.get('type', 'UNKNOWN')
            data = {k: v for k, v in event_or_dict.items() if k != 'type'}
            event = Event(event_type=event_type, data=data)
        else:
            event = event_or_dict
        
        async with self._lock:
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]
            logger.debug(f"Event published: {event}")
        
        # Schedule event dispatching as a background task
        asyncio.create_task(self._dispatch_event(event))

    async def _dispatch_event(self, event: Event) -> None:
        """
        Dispatch event to all subscribers, handling async callbacks.
        """
        logger.info(f"[DEBUG] _dispatch_event called for {event.event_type}")
        async with self._lock:
            callbacks = self._subscribers.get(event.event_type, []).copy()
        logger.info(f"[DEBUG] Found {len(callbacks)} callbacks for {event.event_type}")
        
        logger.debug(f"Dispatching {event.event_type} to {len(callbacks)} subscribers")
        
        # Run callbacks concurrently if they are async
        tasks = []
        for i, callback in enumerate(callbacks):
            try:
                # Check if callback is an async function (including bound methods)
                is_async = asyncio.iscoroutinefunction(callback) or (
                    hasattr(callback, '__func__') and asyncio.iscoroutinefunction(callback.__func__)
                )
                logger.info(f"[DEBUG] Callback {i}: {callback}, async={is_async}")
                if is_async:
                    # Create a Task to allow cancellation on timeout
                    task = asyncio.create_task(callback(event))
                    logger.info(f"[DEBUG] Created task {i}: {task}")
                    tasks.append(task)
                else:
                    # Run sync callbacks in a thread pool to avoid blocking the event loop
                    logger.info(f"[DEBUG] Running sync callback {callback} in executor")
                    await asyncio.get_event_loop().run_in_executor(None, callback, event)
            except Exception as e:
                logger.error(f"Error in event handler for {event.event_type}: {e}", exc_info=True)
        
        if tasks:
            logger.info(f"[DEBUG] About to await gather of {len(tasks)} tasks")
            # Add a timeout to prevent hanging; retry on timeout
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    timeout_seconds = 300.0  # 5 minutes for long-running scans
                    logger.info(f"[DEBUG] Attempt {attempt+1}/{max_retries}: waiting with timeout={timeout_seconds}s")
                    results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=timeout_seconds)
                    logger.info(f"[DEBUG] Gather completed, results count: {len(results)}")
                    for result in results:
                        if isinstance(result, Exception):
                            logger.error(f"Exception in event handler for {event.event_type}: {result}", exc_info=True)
                    break  # Success, exit retry loop
                except asyncio.TimeoutError:
                    logger.warning(f"[DEBUG] TIMEOUT: Event handler tasks for {event.event_type} timed out after {timeout_seconds}s (attempt {attempt+1}/{max_retries})")
                    if attempt < max_retries - 1:
                        # Cancel current tasks and recreate them for retry
                        for task in tasks:
                            task.cancel()
                        # Recreate tasks from original callbacks
                        tasks = []
                        for callback in callbacks:
                            is_async = asyncio.iscoroutinefunction(callback) or (
                                hasattr(callback, '__func__') and asyncio.iscoroutinefunction(callback.__func__)
                            )
                            if is_async:
                                task = asyncio.create_task(callback(event))
                                tasks.append(task)
                            # Note: sync callbacks already handled above; they wouldn't cause timeout in same way
                        logger.info(f"[DEBUG] Recreated {len(tasks)} tasks for retry")
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff before retry
                    else:
                        # Final attempt failed; log error but continue (non-fatal)
                        for task in tasks:
                            task.cancel()
                        logger.error(f"[DEBUG] All {max_retries} attempts timed out for {event.event_type}. Giving up but continuing service.")
        else:
            logger.info(f"[DEBUG] No async tasks to run for {event.event_type}")
        logger.info(f"[DEBUG] _dispatch_event finished for {event.event_type}")

    async def get_subscribers_count(self, event_type: str) -> int:
        """Get count of subscribers for event type"""
        async with self._lock:
            return len(self._subscribers.get(event_type, []))
    
    async def get_event_history(self, event_type: Optional[str] = None, limit: int = 100) -> List[Event]:
        """Get event history"""
        async with self._lock:
            history = self._event_history.copy()
        
        if event_type:
            history = [e for e in history if e.event_type == event_type]
        
        return history[-limit:]
    
    async def clear_history(self) -> None:
        """Clear event history"""
        async with self._lock:
            self._event_history.clear()
        logger.info("Event history cleared")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get event bus statistics"""
        async with self._lock:
            stats = {
                "total_events_published": len(self._event_history),
                "subscribed_event_types": list(self._subscribers.keys()),
                "total_subscribers": sum(len(v) for v in self._subscribers.values()),
                "subscribers_per_type": {k: len(v) for k, v in self._subscribers.items()},
                "history_size": len(self._event_history),
            }
        
        return stats
    
    def __repr__(self) -> str:
        # __repr__ does not need to be async
        # it's usually called for debugging/logging synchronous contexts
        # Accessing _subscribers directly here is fine for repr purposes
        # but for any critical read/write, the async lock should be used.
        types = list(self._subscribers.keys())
        total = sum(len(v) for v in self._subscribers.values())
        return f"EventBus(event_types={types}, total_subscribers={total})"


_global_event_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()  # Use threading lock for synchronous singleton access

def get_event_bus() -> EventBus:
    """Get global event bus instance (singleton) - synchronous version"""
    global _global_event_bus

    if _global_event_bus is None:
        with _bus_lock:
            if _global_event_bus is None:
                _global_event_bus = EventBus()
                logger.info("Global EventBus created")

    return _global_event_bus


class Events:
    """Predefined event type constants"""
    
    # Data events
    MARKET_SCANNED = "market_scanned" # New event for market scanner
    PRICE_REFRESH_COMPLETE = "price_refresh_complete"  # Tier 2: watchlist price update done
    DATA_FETCH_STARTED = "data_fetch_started"
    DATA_FETCH_COMPLETE = "data_fetch_complete"
    DATA_READY = "data_ready"                 # Symbol data ready for analysis (can be removed if DATA_FETCH_COMPLETE is sufficient)
    NEWS_FETCH_COMPLETE = "news_fetch_complete" # New event for news agent
    
    # Analysis events
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_COMPLETE = "analysis_complete"
    ANALYSIS_FAILED = "analysis_failed" # Add failure event
    MARKET_REGIME_UPDATED = "market_regime_updated"  # Market regime change notification
    
    # Decision events (now Trade Proposals)
    TRADE_PROPOSAL_GENERATED = "trade_proposal_generated" # Renamed from DECISION_MADE
    # DECISION_MADE = "decision_made"           # Strategy produced decision
    # DECISION_AWAITING_APPROVAL = "decision_awaiting_approval" # Replaced by APPROVAL_REQUIRED
    
    # Execution events
    EXECUTION_STARTED = "execution_started"
    TRADE_EXECUTED = "trade_executed" # Renamed from EXECUTION_COMPLETE
    EXECUTION_FAILED = "execution_failed"
    
    # Portfolio events
    PORTFOLIO_UPDATED = "portfolio_updated"
    TRADE_OPENED = "trade_opened"
    TRADE_CLOSED = "trade_closed"
    TRADE_STOPPED = "trade_stopped"
    POSITION_DEGRADED = "position_degraded"  # Exit agent: position no longer meets buy criteria
    
    # Risk events
    RISK_ALERT = "risk_alert"                # Position limit, drawdown, etc.
    RISK_CHECK_COMPLETE = "risk_check_complete" # New event for risk agent completion
    RISK_CHECK_FAILED = "risk_check_failed"
    
    # System events
    SYSTEM_ERROR = "system_error"
    CONFIG_RELOADED = "config_reloaded"
    BACKTEST_STARTED = "backtest_started"
    BACKTEST_COMPLETE = "backtest_complete"
    
    # Approval events
    APPROVAL_REQUIRED = "approval_required" # Renamed from APPROVAL_REQUESTED
    TRADE_APPROVED = "trade_approved" # Renamed from APPROVAL_APPROVED
    APPROVAL_REJECTED = "approval_rejected"
    APPROVAL_TIMEOUT = "approval_timeout"

    # Learning events
    LEARNING_COMPLETE = "learning_complete" # New event for learning agent
    LEARNING_FEEDBACK = "learning_feedback" # Optional feedback event
    
    # Regime events
    MARKET_REGIME_UPDATED = "market_regime_updated"  # Market regime classification updated
    
    # System query/response events
    GET_SYSTEM_STATUS = "get_system_status"
    GET_PORTFOLIO_STATE = "get_portfolio_state"
    GET_HEALTH_STATUS = "get_health_status"
    SCHEDULE = "schedule"  # Generic scheduling event
    
    # Scheduler events
    MARKET_SCAN_TRIGGER = "market_scan_trigger"  # Trigger to start market scan (used by scheduler and manual triggers)
    EXIT_CHECK_TRIGGER = "exit_check_trigger"  # Trigger to check open positions for exits and degradation
    DATA_REFRESH_TRIGGER = "data_refresh_trigger"  # Trigger to refresh data for existing symbols
    PRICE_MONITOR_TRIGGER = "price_monitor_trigger"  # Tier 2: lightweight price refresh (every 15 min)
    DAILY_REPORT_TRIGGER = "daily_report_trigger"
    HOURLY_PORTFOLIO_TRIGGER = "hourly_portfolio_trigger"  # Hourly portfolio summary (market hours only)
    HEALTH_CHECK_TRIGGER = "health_check_trigger"
    PRE_SCAN_CONTEXT_REFRESH = "pre_scan_context_refresh"  # Pre-warm MarketRegimeAgent + MacroNewsAgent before scanner

# Global event bus instance (lazy-loaded singleton)
# For backward compatibility, provide a direct reference
event_bus = get_event_bus()



