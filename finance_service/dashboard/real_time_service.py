"""Real-time service for WebSocket updates and streaming data."""

import logging
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Callable, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Real-time event types."""
    PORTFOLIO_UPDATE = "portfolio_update"
    POSITION_UPDATE = "position_update"
    ORDER_UPDATE = "order_update"
    TRADE_EXECUTED = "trade_executed"
    PRICE_ALERT = "price_alert"
    RISK_ALERT = "risk_alert"
    CONNECTION = "connection"
    HEARTBEAT = "heartbeat"


@dataclass
class RealTimeEvent:
    """Real-time event message."""
    event_type: EventType
    timestamp: datetime
    data: Dict[str, Any]
    
    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps({
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        })


class SubscriptionManager:
    """Manages subscriptions to real-time updates."""
    
    def __init__(self):
        """Initialize subscription manager."""
        self.subscribers: Dict[EventType, List[Callable]] = {}
        
    def subscribe(self, event_type: EventType, callback: Callable):
        """Subscribe to event type."""
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)
        logger.debug(f"Subscriber added for {event_type.value}")
    
    def unsubscribe(self, event_type: EventType, callback: Callable):
        """Unsubscribe from event type."""
        if event_type in self.subscribers:
            self.subscribers[event_type] = [
                cb for cb in self.subscribers[event_type] if cb != callback
            ]
    
    async def publish(self, event: RealTimeEvent):
        """Publish event to all subscribers."""
        if event.event_type in self.subscribers:
            callbacks = self.subscribers[event.event_type]
            for callback in callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    logger.error(f"Error in subscriber callback: {e}")


class RealTimeService:
    """
    Service for real-time updates via WebSocket.
    
    Manages subscriptions, publishes events from trades/orders,
    and broadcasts to connected clients.
    """
    
    def __init__(self, finance_service):
        """
        Initialize real-time service.
        
        Args:
            finance_service: Reference to main FinanceService
        """
        self.finance_service = finance_service
        self.subscription_manager = SubscriptionManager()
        
        # Connected WebSocket clients
        self.clients: List[Any] = []
        
        # Event history for replay
        self.event_history: List[RealTimeEvent] = []
        self.max_history = 100
        
        # Price subscriptions
        self.price_subscriptions: Dict[str, float] = {}  # symbol -> latest price
        self.price_alerts: Dict[str, Dict[str, float]] = {}  # symbol -> {"high": X, "low": Y}
        
        # Heartbeat configuration
        self.heartbeat_interval = 30  # seconds
        self.running = False
    
    async def register_client(self, websocket: Any):
        """Register new WebSocket client."""
        self.clients.append(websocket)
        logger.info(f"Client registered. Total clients: {len(self.clients)}")
        
        # Send connection confirmation
        await self._send_to_client(
            websocket,
            RealTimeEvent(
                event_type=EventType.CONNECTION,
                timestamp=datetime.now(),
                data={"status": "connected", "client_count": len(self.clients)},
            )
        )
    
    async def unregister_client(self, websocket: Any):
        """Unregister WebSocket client."""
        if websocket in self.clients:
            self.clients.remove(websocket)
            logger.info(f"Client unregistered. Total clients: {len(self.clients)}")
    
    async def broadcast_event(self, event: RealTimeEvent):
        """Broadcast event to all connected clients."""
        if not self.clients:
            return
        
        # Store in history
        self.event_history.append(event)
        if len(self.event_history) > self.max_history:
            self.event_history.pop(0)
        
        # Broadcast to all clients
        disconnected = []
        for client in self.clients:
            try:
                await self._send_to_client(client, event)
            except Exception as e:
                logger.warning(f"Error broadcasting to client: {e}")
                disconnected.append(client)
        
        # Remove disconnected clients
        for client in disconnected:
            await self.unregister_client(client)
    
    async def _send_to_client(self, websocket: Any, event: RealTimeEvent):
        """Send event to specific client."""
        try:
            message = event.to_json()
            if hasattr(websocket, 'send'):
                await websocket.send(message)
        except Exception as e:
            logger.error(f"Error sending to client: {e}")
    
    async def start_heartbeat(self):
        """Start periodic heartbeat."""
        self.running = True
        while self.running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                event = RealTimeEvent(
                    event_type=EventType.HEARTBEAT,
                    timestamp=datetime.now(),
                    data={
                        "active_clients": len(self.clients),
                        "memory_usage_mb": 0,
                    },
                )
                await self.broadcast_event(event)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    def stop_heartbeat(self):
        """Stop heartbeat."""
        self.running = False
    
    # Event publishing methods
    
    async def publish_portfolio_update(self, portfolio_data: Dict[str, Any]):
        """Publish portfolio update."""
        event = RealTimeEvent(
            event_type=EventType.PORTFOLIO_UPDATE,
            timestamp=datetime.now(),
            data=portfolio_data,
        )
        await self.broadcast_event(event)
    
    async def publish_position_update(
        self,
        symbol: str,
        quantity: float,
        avg_cost: float,
        current_price: float,
        unrealized_pnl: float
    ):
        """Publish position update."""
        event = RealTimeEvent(
            event_type=EventType.POSITION_UPDATE,
            timestamp=datetime.now(),
            data={
                "symbol": symbol,
                "quantity": quantity,
                "avg_cost": avg_cost,
                "current_price": current_price,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": (unrealized_pnl / (quantity * avg_cost) * 100) if quantity > 0 else 0,
            },
        )
        await self.broadcast_event(event)
    
    async def publish_order_update(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        filled_quantity: float,
        status: str
    ):
        """Publish order update."""
        event = RealTimeEvent(
            event_type=EventType.ORDER_UPDATE,
            timestamp=datetime.now(),
            data={
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "filled_quantity": filled_quantity,
                "fill_pct": (filled_quantity / quantity * 100) if quantity > 0 else 0,
                "status": status,
            },
        )
        await self.broadcast_event(event)
    
    async def publish_trade_executed(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        fill_price: float
    ):
        """Publish trade execution."""
        event = RealTimeEvent(
            event_type=EventType.TRADE_EXECUTED,
            timestamp=datetime.now(),
            data={
                "trade_id": trade_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "entry_price": entry_price,
                "fill_price": fill_price,
                "slippage_bps": ((fill_price - entry_price) / entry_price * 10000) if entry_price > 0 else 0,
            },
        )
        await self.broadcast_event(event)
    
    async def publish_price_alert(
        self,
        symbol: str,
        current_price: float,
        alert_type: str,  # "high" or "low"
        threshold: float
    ):
        """Publish price alert."""
        event = RealTimeEvent(
            event_type=EventType.PRICE_ALERT,
            timestamp=datetime.now(),
            data={
                "symbol": symbol,
                "current_price": current_price,
                "alert_type": alert_type,
                "threshold": threshold,
                "message": f"{symbol} hit {alert_type} alert at ${current_price:.2f}",
            },
        )
        await self.broadcast_event(event)
    
    async def publish_risk_alert(
        self,
        alert_type: str,
        severity: str,  # "info", "warning", "critical"
        message: str,
        data: Optional[Dict[str, Any]] = None
    ):
        """Publish risk alert."""
        event = RealTimeEvent(
            event_type=EventType.RISK_ALERT,
            timestamp=datetime.now(),
            data={
                "alert_type": alert_type,
                "severity": severity,
                "message": message,
                **(data or {}),
            },
        )
        await self.broadcast_event(event)
    
    # Subscription management
    
    def set_price_alert(self, symbol: str, high: Optional[float] = None, low: Optional[float] = None):
        """Set price alerts for symbol."""
        if symbol not in self.price_alerts:
            self.price_alerts[symbol] = {}
        
        if high is not None:
            self.price_alerts[symbol]["high"] = high
        if low is not None:
            self.price_alerts[symbol]["low"] = low
        
        logger.info(f"Price alert set for {symbol}: high={high}, low={low}")
    
    def remove_price_alert(self, symbol: str):
        """Remove price alerts for symbol."""
        if symbol in self.price_alerts:
            del self.price_alerts[symbol]
            logger.info(f"Price alert removed for {symbol}")
    
    def get_event_history(self, event_type: Optional[EventType] = None) -> List[RealTimeEvent]:
        """Get event history, optionally filtered by type."""
        if event_type:
            return [e for e in self.event_history if e.event_type == event_type]
        return self.event_history
    
    def clear_event_history(self):
        """Clear event history."""
        self.event_history.clear()
        logger.info("Event history cleared")
