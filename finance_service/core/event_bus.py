import logging
import asyncio
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
        logger.info(f"EventBus.publish CALLED with event_or_dict={event_or_dict}")
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
        logger.info(f">>> _dispatch_event START: {event.event_type}")
        async with self._lock:
            callbacks = self._subscribers.get(event.event_type, []).copy()
        
        logger.info(f"EVENT BUS DISPATCH: {event.event_type} to {len(callbacks)} subscribers")
        
        # Run callbacks concurrently if they are async
        tasks = []
        for i, callback in enumerate(callbacks):
            try:
                logger.info(f"Preparing task {i} for {event.event_type}, callback={callback.__qualname__ if hasattr(callback, '__qualname__') else str(callback)}")
                if asyncio.iscoroutinefunction(callback):
                    tasks.append(callback(event))
                else:
                    # Run sync callbacks in a thread pool to avoid blocking the event loop
                    # This requires an executor to be set on the event loop, or using run_in_executor
                    await asyncio.get_event_loop().run_in_executor(None, callback, event)
            except Exception as e:
                logger.error(f"Error preparing task {i} for {event.event_type}: {e}", exc_info=True)
                raise
        
        if tasks:
            logger.info(f"Dispatching {len(tasks)} tasks for {event.event_type}")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"Tasks completed for {event.event_type}: {len(results)} results")
        else:
            logger.warning(f"No tasks to dispatch for {event.event_type} (callbacks={len(callbacks)})")

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
_bus_lock = asyncio.Lock() # Use asyncio lock for singleton initialization

async def get_event_bus() -> EventBus:
    """Get global event bus instance (singleton)"""
    global _global_event_bus
    
    if _global_event_bus is None:
        async with _bus_lock:
            if _global_event_bus is None:
                _global_event_bus = EventBus()
                logger.info("Global EventBus created")
    
    return _global_event_bus


class Events:
    """Predefined event type constants"""
    
    # Data events
    MARKET_SCANNED = "market_scanned"
    DATA_FETCH_STARTED = "data_fetch_started"
    DATA_FETCH_COMPLETE = "data_fetch_complete"
    DATA_READY = "data_ready"
    NEWS_FETCH_COMPLETE = "news_fetch_complete"
    
    # Analysis events
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_COMPLETE = "analysis_complete"
    ANALYSIS_FAILED = "analysis_failed"
    
    # Decision events
    TRADE_PROPOSAL_GENERATED = "trade_proposal_generated"
    
    # Execution events
    EXECUTION_STARTED = "execution_started"
    TRADE_EXECUTED = "trade_executed"
    EXECUTION_FAILED = "execution_failed"
    
    # Portfolio events
    PORTFOLIO_UPDATED = "portfolio_updated"
    TRADE_OPENED = "trade_opened"
    TRADE_CLOSED = "trade_closed"
    TRADE_STOPPED = "trade_stopped"
    
    # Risk events
    RISK_ALERT = "risk_alert"
    RISK_CHECK_COMPLETE = "risk_check_complete"
    RISK_CHECK_FAILED = "risk_check_failed"
    
    # System events
    SYSTEM_ERROR = "system_error"
    CONFIG_RELOADED = "config_reloaded"
    BACKTEST_STARTED = "backtest_started"
    BACKTEST_COMPLETE = "backtest_complete"
    
    # Approval events
    APPROVAL_REQUIRED = "approval_required"
    TRADE_APPROVED = "trade_approved"
    
    # Scheduler/Trigger events
    MARKET_SCAN_TRIGGER = "market_scan_trigger"
    DATA_REFRESH_TRIGGER = "data_refresh_trigger"
    DAILY_REPORT_TRIGGER = "daily_report_trigger"
    HEALTH_CHECK_TRIGGER = "health_check_trigger"
    GET_SYSTEM_STATUS = "get_system_status"
    GET_PORTFOLIO_STATE = "get_portfolio_state"
    GET_HEALTH_STATUS = "get_health_status"
    APPROVAL_REJECTED = "approval_rejected"
    APPROVAL_TIMEOUT = "approval_timeout"
    
    # Learning events
    LEARNING_COMPLETE = "learning_complete"
    LEARNING_FEEDBACK = "learning_feedback"
# Global event bus instance (lazy-loaded singleton)
# event_bus = get_event_bus() # This will now be awaited in main if needed



