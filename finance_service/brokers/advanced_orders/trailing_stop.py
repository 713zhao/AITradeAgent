"""
Trailing Stop Order Implementation

Implements trailing stop orders that automatically adjust the stop price
as the market moves favorably.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class TrailingType(Enum):
    """Types of trailing stop strategies."""
    DISTANCE = "distance"  # Fixed dollar amount trailing
    PERCENTAGE = "percentage"  # Fixed percentage trailing


class TrailingStopState(Enum):
    """States of a trailing stop order."""
    ACTIVE = "active"  # Order is active and monitoring
    TRIGGERED = "triggered"  # Stop price hit, order triggered
    FILLED = "filled"  # Order has been filled
    CANCELLED = "cancelled"  # Order was cancelled
    EXPIRED = "expired"  # Order expired


@dataclass
class TrailingStopOrder:
    """
    Trailing stop order that adjusts stop price as market moves favorably.
    
    For SELL trailing stops:
    - As price increases, stop price increases by trailing amount
    - When price decreases and hits stop price → trigger order
    
    For BUY trailing stops:
    - As price decreases, stop price decreases by trailing amount  
    - When price increases and hits stop price → trigger order
    """
    
    # Order identification
    order_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: float
    initial_stop_price: float
    
    # Trailing configuration
    trailing_type: TrailingType
    trailing_amount: float  # Dollar amount or percentage
    current_stop_price: float
    
    # State tracking
    state: TrailingStopState
    highest_price: float = 0.0  # For SELL trailing stops
    lowest_price: float = float('inf')  # For BUY trailing stops
    created_at: datetime = None
    triggered_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    
    # Metadata
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}
            
        # Initialize tracking prices based on side
        if self.side == "SELL":
            self.highest_price = self.initial_stop_price
        else:  # BUY
            self.lowest_price = self.initial_stop_price
    
    def update_stop_price(self, current_price: float) -> Optional[float]:
        """
        Update the trailing stop price based on current market price.
        
        Args:
            current_price: Current market price of the symbol
            
        Returns:
            New stop price if updated, None if no change
        """
        old_stop_price = self.current_stop_price
        
        if self.side == "SELL":
            # For SELL orders: trailing stop moves UP as price goes UP
            if current_price > self.highest_price:
                self.highest_price = current_price
                
                if self.trailing_type == TrailingType.DISTANCE:
                    new_stop = self.highest_price - self.trailing_amount
                else:  # PERCENTAGE
                    new_stop = self.highest_price * (1 - self.trailing_amount / 100)
                
                # Only update if new stop is higher than current
                if new_stop > self.current_stop_price:
                    self.current_stop_price = new_stop
                    logger.info(f"Trailing stop updated for {self.symbol}: {old_stop_price} -> {self.current_stop_price}")
                    return self.current_stop_price
                    
        else:  # BUY
            # For BUY orders: trailing stop moves DOWN as price goes DOWN
            if current_price < self.lowest_price:
                self.lowest_price = current_price
                
                if self.trailing_type == TrailingType.DISTANCE:
                    new_stop = self.lowest_price + self.trailing_amount
                else:  # PERCENTAGE
                    new_stop = self.lowest_price * (1 + self.trailing_amount / 100)
                
                # Only update if new stop is lower than current
                if new_stop < self.current_stop_price:
                    self.current_stop_price = new_stop
                    logger.info(f"Trailing stop updated for {self.symbol}: {old_stop_price} -> {self.current_stop_price}")
                    return self.current_stop_price
        
        return None
    
    def check_trigger(self, current_price: float) -> bool:
        """
        Check if the trailing stop should trigger.
        
        Args:
            current_price: Current market price
            
        Returns:
            True if stop should trigger
        """
        if self.side == "SELL":
            # Trigger when price falls to or below stop price
            return current_price <= self.current_stop_price
        else:  # BUY
            # Trigger when price rises to or above stop price
            return current_price >= self.current_stop_price
    
    def trigger(self) -> None:
        """Mark the order as triggered."""
        if self.state == TrailingStopState.ACTIVE:
            self.state = TrailingStopState.TRIGGERED
            self.triggered_at = datetime.utcnow()
            logger.info(f"Trailing stop triggered for {self.symbol} at {self.triggered_at}")
    
    def fill(self, fill_price: float, fill_quantity: float) -> None:
        """
        Mark the order as filled.
        
        Args:
            fill_price: Price at which order was filled
            fill_quantity: Quantity filled
        """
        if self.state == TrailingStopState.TRIGGERED:
            self.state = TrailingStopState.FILLED
            self.filled_at = datetime.utcnow()
            self.metadata['fill_price'] = fill_price
            self.metadata['fill_quantity'] = fill_quantity
            logger.info(f"Trailing stop filled for {self.symbol}: {fill_price} for {fill_quantity} shares")
    
    def cancel(self) -> None:
        """Cancel the trailing stop order."""
        if self.state in [TrailingStopState.ACTIVE, TrailingStopState.TRIGGERED]:
            self.state = TrailingStopState.CANCELLED
            logger.info(f"Trailing stop cancelled for {self.symbol}")
    
    def expire(self) -> None:
        """Mark the order as expired."""
        if self.state == TrailingStopState.ACTIVE:
            self.state = TrailingStopState.EXPIRED
            logger.info(f"Trailing stop expired for {self.symbol}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of the trailing stop order."""
        return {
            'order_id': self.order_id,
            'symbol': self.symbol,
            'side': self.side,
            'quantity': self.quantity,
            'state': self.state.value,
            'initial_stop_price': self.initial_stop_price,
            'current_stop_price': self.current_stop_price,
            'trailing_type': self.trailing_type.value,
            'trailing_amount': self.trailing_amount,
            'highest_price': self.highest_price if self.side == "SELL" else None,
            'lowest_price': self.lowest_price if self.side == "BUY" else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'triggered_at': self.triggered_at.isoformat() if self.triggered_at else None,
            'filled_at': self.filled_at.isoformat() if self.filled_at else None,
            'metadata': self.metadata
        }
    
    def is_active(self) -> bool:
        """Check if order is still active."""
        return self.state == TrailingStopState.ACTIVE
    
    def should_trigger(self, current_price: float) -> bool:
        """Check if order should trigger at current price."""
        return self.check_trigger(current_price)
    
    def update(self, current_price: float) -> Dict[str, Any]:
        """
        Update trailing stop with current price.
        
        Args:
            current_price: Current market price
            
        Returns:
            Dictionary with update information
        """
        # Update trailing stop price
        new_stop = self.update_stop_price(current_price)
        
        # Check for trigger
        should_trigger = self.check_trigger(current_price)
        if should_trigger and self.state == TrailingStopState.ACTIVE:
            self.trigger()
        
        return {
            'order_id': self.order_id,
            'symbol': self.symbol,
            'current_price': current_price,
            'stop_price_updated': new_stop is not None,
            'new_stop_price': new_stop,
            'current_stop_price': self.current_stop_price,
            'triggered': should_trigger,
            'state': self.state.value
        }


class TrailingStopManager:
    """
    Manager for multiple trailing stop orders.
    """
    
    def __init__(self):
        self.orders: Dict[str, TrailingStopOrder] = {}
        self.logger = logging.getLogger(__name__)
    
    def add_order(self, order: TrailingStopOrder) -> None:
        """Add a trailing stop order."""
        self.orders[order.order_id] = order
        self.logger.info(f"Added trailing stop order {order.order_id} for {order.symbol}")
    
    def remove_order(self, order_id: str) -> Optional[TrailingStopOrder]:
        """Remove a trailing stop order."""
        return self.orders.pop(order_id, None)
    
    def get_order(self, order_id: str) -> Optional[TrailingStopOrder]:
        """Get a trailing stop order by ID."""
        return self.orders.get(order_id)
    
    def get_orders_by_symbol(self, symbol: str) -> list[TrailingStopOrder]:
        """Get all trailing stop orders for a symbol."""
        return [order for order in self.orders.values() if order.symbol == symbol]
    
    def get_active_orders(self) -> list[TrailingStopOrder]:
        """Get all active trailing stop orders."""
        return [order for order in self.orders.values() if order.is_active()]
    
    def update_all(self, symbol: str, current_price: float) -> list[Dict[str, Any]]:
        """
        Update all trailing stop orders for a symbol.
        
        Args:
            symbol: Symbol to update
            current_price: Current market price
            
        Returns:
            List of update results
        """
        results = []
        orders = self.get_orders_by_symbol(symbol)
        
        for order in orders:
            if order.is_active():
                result = order.update(current_price)
                results.append(result)
        
        return results
    
    def trigger_orders(self, symbol: str, current_price: float) -> list[str]:
        """
        Trigger any orders that should trigger at current price.
        
        Args:
            symbol: Symbol to check
            current_price: Current market price
            
        Returns:
            List of triggered order IDs
        """
        triggered_orders = []
        orders = self.get_orders_by_symbol(symbol)
        
        for order in orders:
            if order.is_active() and order.should_trigger(current_price):
                order.trigger()
                triggered_orders.append(order.order_id)
        
        return triggered_orders
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get summary status of all trailing stop orders."""
        total_orders = len(self.orders)
        active_orders = len(self.get_active_orders())
        triggered_orders = len([o for o in self.orders.values() if o.state == TrailingStopState.TRIGGERED])
        filled_orders = len([o for o in self.orders.values() if o.state == TrailingStopState.FILLED])
        
        return {
            'total_orders': total_orders,
            'active_orders': active_orders,
            'triggered_orders': triggered_orders,
            'filled_orders': filled_orders,
            'cancelled_orders': len([o for o in self.orders.values() if o.state == TrailingStopState.CANCELLED]),
            'expired_orders': len([o for o in self.orders.values() if o.state == TrailingStopState.EXPIRED])
        }