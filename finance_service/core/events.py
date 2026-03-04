"""
Event management and types for brokers and trading systems

This module provides event types and event management for the trading system,
including EventType enums and EventManager for coordinating across multiple systems.
"""

from enum import Enum
from typing import Callable, Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
import logging

from finance_service.core.event_bus import Event, EventBus, get_event_bus

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Event types for trading system"""
    
    # Order events
    ORDER_SUBMITTED = "order_submitted"
    ORDER_ACCEPTED = "order_accepted"
    ORDER_FILLED = "order_filled"
    ORDER_PARTIALLY_FILLED = "order_partially_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_REJECTED = "order_rejected"
    ORDER_UPDATED = "order_updated"
    ORDER_EXPIRED = "order_expired"
    
    # Position events
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    POSITION_UPDATED = "position_updated"
    
    # Portfolio events
    PORTFOLIO_UPDATED = "portfolio_updated"
    PORTFOLIO_REBALANCED = "portfolio_rebalanced"
    PORTFOLIO_SNAPSHOT = "portfolio_snapshot"
    
    # Market data events
    MARKET_DATA_RECEIVED = "market_data_received"
    MARKET_SNAPSHOT = "market_snapshot"
    
    # Risk events
    RISK_ALERT = "risk_alert"
    RISK_LIMIT_EXCEEDED = "risk_limit_exceeded"
    MARGIN_CALL = "margin_call"
    
    # Performance events
    PERFORMANCE_UPDATED = "performance_updated"
    DAILY_PNL = "daily_pnl"
    STRATEGY_PERFORMANCE = "strategy_performance"
    
    # Connection events
    BROKER_CONNECTED = "broker_connected"
    BROKER_DISCONNECTED = "broker_disconnected"
    CONNECTION_ERROR = "connection_error"
    
    # System events
    SYSTEM_ERROR = "system_error"
    SYSTEM_WARNING = "system_warning"
    SYSTEM_INFO = "system_info"


class EventManager:
    """
    Central event manager for the trading system.
    
    Provides event publishing, subscribing, and management across all
    trading system components.
    """
    
    def __init__(self, event_bus: Optional[EventBus] = None):
        """
        Initialize EventManager.
        
        Args:
            event_bus: Optional EventBus instance. If None, uses global EventBus.
        """
        self.event_bus = event_bus or get_event_bus()
        self.logger = logging.getLogger(f"{__name__}.EventManager")
        self._event_handlers: Dict[str, List[Callable]] = {}
        self.logger.info("EventManager initialized")
    
    def subscribe(self, event_type: EventType, handler: Callable) -> str:
        """
        Subscribe to an event type.
        
        Args:
            event_type: EventType to listen for
            handler: Callback function to call when event occurs
            
        Returns:
            Subscription ID for unsubscribing
        """
        event_key = event_type.value if isinstance(event_type, EventType) else str(event_type)
        
        if event_key not in self._event_handlers:
            self._event_handlers[event_key] = []
            # Also subscribe in the underlying event bus
            self.event_bus.subscribe(event_key, self._dispatch_handler)
        
        self._event_handlers[event_key].append(handler)
        
        subscription_id = f"{event_key}_{len(self._event_handlers[event_key])}"
        self.logger.debug(f"Subscribed to {event_key} (id={subscription_id})")
        
        return subscription_id
    
    def _dispatch_handler(self, event: Event) -> None:
        """Internal handler for event bus events"""
        event_key = event.event_type
        
        if event_key in self._event_handlers:
            for handler in self._event_handlers[event_key]:
                try:
                    handler(event)
                except Exception as e:
                    self.logger.error(f"Error in handler for {event_key}: {e}", exc_info=True)
    
    def publish(self, event_type: EventType, data: Optional[Dict[str, Any]] = None, source: str = "trading_system") -> None:
        """
        Publish an event.
        
        Args:
            event_type: EventType to publish
            data: Optional event data
            source: Source of the event
        """
        event_key = event_type.value if isinstance(event_type, EventType) else str(event_type)
        
        event = Event(
            event_type=event_key,
            data=data or {},
            source=source,
            timestamp=datetime.now()
        )
        
        self.event_bus.publish(event)
        self.logger.debug(f"Event published: {event_key} from {source}")
    
    def publish_dict(self, event_dict: Dict[str, Any]) -> None:
        """
        Publish an event from a dictionary.
        
        Args:
            event_dict: Dictionary with 'type' key and optional 'data', 'source'
        """
        event_type = event_dict.get('type')
        data = event_dict.get('data', {})
        source = event_dict.get('source', 'unknown')
        
        if event_type:
            self.publish(event_type, data, source)
    
    def get_event_history(self, event_type: Optional[EventType] = None, limit: int = 100) -> List[Event]:
        """
        Get event history.
        
        Args:
            event_type: Optional EventType to filter by
            limit: Maximum number of events to return
            
        Returns:
            List of Event objects
        """
        event_key = None
        if event_type:
            event_key = event_type.value if isinstance(event_type, EventType) else str(event_type)
        
        return self.event_bus.get_event_history(event_type=event_key, limit=limit)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get event manager statistics"""
        return {
            "managed_handlers": len(self._event_handlers),
            "subscribed_types": list(self._event_handlers.keys()),
            "event_bus_stats": self.event_bus.get_stats()
        }


# Create a global EventManager instance
_global_event_manager: Optional[EventManager] = None


def get_event_manager() -> EventManager:
    """Get the global EventManager instance"""
    global _global_event_manager
    
    if _global_event_manager is None:
        _global_event_manager = EventManager()
    
    return _global_event_manager


# Default event manager
event_manager = get_event_manager()
