"""Event Bus - Publish/Subscribe event handling"""
import logging
import threading
from typing import Callable, Dict, List, Any, Optional
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
    """Publish/Subscribe event handling with thread safety"""
    
    def __init__(self):
        # Storage
        self._subscribers: Dict[str, List[Callable]] = {}
        self._event_history: List[Event] = []
        self._max_history: int = 1000
        
        # Thread safety
        self._lock = threading.RLock()
        self._dispatch_thread_count = 0
    
    def subscribe(self, event_type: str, callback: Callable) -> str:
        """
        Subscribe to an event type
        
        Args:
            event_type: Type of event to listen for (e.g., "data_ready", "analysis_complete")
            callback: Function to call when event is published
        
        Returns:
            Subscription ID (for unsubscribing)
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            
            self._subscribers[event_type].append(callback)
            
            sub_id = f"{event_type}_{len(self._subscribers[event_type])}"
            logger.debug(f"Subscribed to {event_type} (id={sub_id})")
            
            return sub_id
    
    def on(self, event_type: str, callback: Callable) -> str:
        """
        Alias for subscribe - subscribe to an event type
        
        Usage: event_bus.on('DATA_READY', my_handler)
        """
        return self.subscribe(event_type, callback)
    
    def publish(self, event_or_dict: Any, sync: bool = False) -> None:
        """
        Publish an event
        
        Args:
            event_or_dict: Event object or dict with 'type' key
                If dict: {type: 'EVENT_NAME', data: {...}, ...}
                If Event: use directly
            sync: If True, wait for all handlers to complete
        """
        # Convert dict to Event if needed
        if isinstance(event_or_dict, dict):
            event_type = event_or_dict.get('type', 'UNKNOWN')
            data = {k: v for k, v in event_or_dict.items() if k != 'type'}
            event = Event(event_type=event_type, data=data)
        else:
            event = event_or_dict
        
        with self._lock:
            self._event_history.append(event)
            
            # Trim history
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]
            
            logger.debug(f"Event published: {event}")
        
        if sync:
            self._dispatch_event(event)
        else:
            # Dispatch in background thread
            thread = threading.Thread(target=self._dispatch_event, args=(event,), daemon=True)
            thread.start()

    
    def _dispatch_event(self, event: Event) -> None:
        """Dispatch event to all subscribers"""
        with self._lock:
            callbacks = self._subscribers.get(event.event_type, []).copy()
        
        logger.debug(f"Dispatching {event.event_type} to {len(callbacks)} subscribers")
        
        for callback in callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Error in event handler for {event.event_type}: {e}", exc_info=True)
    
    def get_subscribers_count(self, event_type: str) -> int:
        """Get count of subscribers for event type"""
        with self._lock:
            return len(self._subscribers.get(event_type, []))
    
    def get_event_history(self, event_type: Optional[str] = None, limit: int = 100) -> List[Event]:
        """Get event history"""
        with self._lock:
            history = self._event_history.copy()
        
        if event_type:
            history = [e for e in history if e.event_type == event_type]
        
        return history[-limit:]
    
    def clear_history(self) -> None:
        """Clear event history"""
        with self._lock:
            self._event_history.clear()
        logger.info("Event history cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get event bus statistics"""
        with self._lock:
            stats = {
                "total_events_published": len(self._event_history),
                "subscribed_event_types": list(self._subscribers.keys()),
                "total_subscribers": sum(len(v) for v in self._subscribers.values()),
                "subscribers_per_type": {k: len(v) for k, v in self._subscribers.items()},
                "history_size": len(self._event_history),
            }
        
        return stats
    
    def __repr__(self) -> str:
        with self._lock:
            types = list(self._subscribers.keys())
            total = sum(len(v) for v in self._subscribers.values())
        
        return f"EventBus(event_types={types}, total_subscribers={total})"


# Global event bus instance
_global_event_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Get global event bus instance (singleton)"""
    global _global_event_bus
    
    if _global_event_bus is None:
        with _bus_lock:
            if _global_event_bus is None:
                _global_event_bus = EventBus()
                logger.info("Global EventBus created")
    
    return _global_event_bus


# Common event types
class Events:
    """Predefined event type constants"""
    
    # Data events
    DATA_FETCH_STARTED = "data_fetch_started"
    DATA_FETCH_COMPLETE = "data_fetch_complete"
    DATA_READY = "data_ready"                 # Symbol data ready for analysis
    
    # Analysis events
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_COMPLETE = "analysis_complete"
    
    # Decision events
    DECISION_MADE = "decision_made"           # Strategy produced decision
    DECISION_AWAITING_APPROVAL = "decision_awaiting_approval"
    
    # Execution events
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETE = "execution_complete"
    EXECUTION_FAILED = "execution_failed"
    
    # Portfolio events
    PORTFOLIO_UPDATED = "portfolio_updated"
    TRADE_OPENED = "trade_opened"
    TRADE_CLOSED = "trade_closed"
    TRADE_STOPPED = "trade_stopped"
    
    # Risk events
    RISK_ALERT = "risk_alert"                # Position limit, drawdown, etc.
    RISK_CHECK_FAILED = "risk_check_failed"
    
    # System events
    SYSTEM_ERROR = "system_error"
    CONFIG_RELOADED = "config_reloaded"
    BACKTEST_STARTED = "backtest_started"
    BACKTEST_COMPLETE = "backtest_complete"
    
    # Approval events
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_APPROVED = "approval_approved"
    APPROVAL_REJECTED = "approval_rejected"
    APPROVAL_TIMEOUT = "approval_timeout"


# Global event bus instance (lazy-loaded singleton)
event_bus = get_event_bus()
