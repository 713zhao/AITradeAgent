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
        async with self._lock:
            callbacks = self._subscribers.get(event.event_type, []).copy()
        
        logger.debug(f"Dispatching {event.event_type} to {len(callbacks)} subscribers")
        
        # Run callbacks concurrently if they are async
        tasks = []
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    tasks.append(callback(event))
                else:
                    # Run sync callbacks in a thread pool to avoid blocking the event loop
                    # This requires an executor to be set on the event loop, or using run_in_executor
                    await asyncio.get_event_loop().run_in_executor(None, callback, event)
            except Exception as e:
                logger.error(f"Error in event handler for {event.event_type}: {e}", exc_info=True)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

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


class Events:\n    """Predefined event type constants"""\n    \n    # Data events\n    MARKET_SCANNED = "market_scanned" # New event for market scanner\n    DATA_FETCH_STARTED = "data_fetch_started"\n    DATA_FETCH_COMPLETE = "data_fetch_complete"\n    DATA_READY = "data_ready"                 # Symbol data ready for analysis (can be removed if DATA_FETCH_COMPLETE is sufficient)
    NEWS_FETCH_COMPLETE = "news_fetch_complete" # New event for news agent\n    \n    # Analysis events\n    ANALYSIS_STARTED = "analysis_started"\n    ANALYSIS_COMPLETE = "analysis_complete"\n    ANALYSIS_FAILED = "analysis_failed" # Add failure event\n    \n    # Decision events (now Trade Proposals)\n    TRADE_PROPOSAL_GENERATED = "trade_proposal_generated" # Renamed from DECISION_MADE\n    # DECISION_MADE = "decision_made"           # Strategy produced decision\n    # DECISION_AWAITING_APPROVAL = "decision_awaiting_approval" # Replaced by APPROVAL_REQUIRED\n    \n    # Execution events\n    EXECUTION_STARTED = "execution_started"\n    TRADE_EXECUTED = "trade_executed" # Renamed from EXECUTION_COMPLETE\n    EXECUTION_FAILED = "execution_failed"\n    \n    # Portfolio events\n    PORTFOLIO_UPDATED = \"portfolio_updated\"\n    TRADE_OPENED = \"trade_opened\"\n    TRADE_CLOSED = \"trade_closed\"\n    TRADE_STOPPED = \"trade_stopped\"\n    \n    # Risk events\n    RISK_ALERT = \"risk_alert\"                # Position limit, drawdown, etc.\n    RISK_CHECK_COMPLETE = "risk_check_complete" # New event for risk agent completion\n    RISK_CHECK_FAILED = \"risk_check_failed\"\n    \n    # System events\n    SYSTEM_ERROR = \"system_error\"\n    CONFIG_RELOADED = \"config_reloaded\"\n    BACKTEST_STARTED = \"backtest_started\"\n    BACKTEST_COMPLETE = \"backtest_complete\"\n    \n    # Approval events\n    APPROVAL_REQUIRED = \"approval_required\" # Renamed from APPROVAL_REQUESTED\n    TRADE_APPROVED = \"trade_approved\" # Renamed from APPROVAL_APPROVED\n    APPROVAL_REJECTED = \"approval_rejected\"\n    APPROVAL_TIMEOUT = \"approval_timeout\"\n\n    # Learning events\n    LEARNING_COMPLETE = "learning_complete" # New event for learning agent\n    LEARNING_FEEDBACK = "learning_feedback" # Optional feedback event\n
# Global event bus instance (lazy-loaded singleton)
# event_bus = get_event_bus() # This will now be awaited in main if needed



