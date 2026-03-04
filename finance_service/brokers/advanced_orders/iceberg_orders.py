"""
Iceberg Order Implementation

Implements iceberg orders that execute large orders by revealing
only a portion at a time to minimize market impact.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass, field
import logging
import uuid
import time

from ..base_broker import OrderRequest, Order, OrderStatus, OrderSide

logger = logging.getLogger(__name__)


class DisclosureType(Enum):
    """Types of iceberg order disclosure strategies."""
    TIME_BASED = "time"  # Reveal based on time intervals
    FILL_BASED = "fill"  # Reveal based on partial fills


class IcebergStatus(Enum):
    """Status of an iceberg order."""
    ACTIVE = "active"  # Order is actively executing
    PARTIAL = "partial"  # Some portions filled
    COMPLETED = "completed"  # All quantities filled
    CANCELLED = "cancelled"  # Order cancelled
    EXPIRED = "expired"  # Order expired


@dataclass
class IcebergOrder:
    """
    Iceberg order that reveals only a portion of the total order at a time.
    
    This helps minimize market impact when executing large orders by
    displaying only a smaller "displayed" quantity while keeping the
    remaining "hidden" quantity for later disclosure.
    """
    
    # Order identification
    iceberg_id: str
    parent_order_id: str  # ID of the parent iceberg order
    symbol: str
    side: str  # "BUY" or "SELL"
    
    # Quantities
    total_quantity: float
    displayed_quantity: float  # What market sees
    
    # Store original displayed for reuse
    _original_disclosed: float = field(init=False, default=None)
    
    # Disclosure configuration (required)
    disclosure_type: DisclosureType
    
    # Quantities with defaults
    filled_quantity: float = 0.0
    hidden_quantity: float = 0.0
    
    # Disclosure configuration (optional)
    disclosure_interval_seconds: Optional[int] = None  # For time-based
    disclosure_fill_threshold: Optional[float] = None  # For fill-based
    
    # Order details
    order_type: str = "limit"
    price: Optional[float] = None
    time_in_force: str = "day"
    
    # State tracking
    status: IcebergStatus = IcebergStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_disclosed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Child orders tracking
    child_orders: List[str] = field(default_factory=list)
    active_child_orders: List[str] = field(default_factory=list)
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        # Store the initial display chunk size for reuse in disclose_next_portion
        if self._original_disclosed is None:
            self._original_disclosed = self.displayed_quantity
        
        # Calculate initial hidden quantity
        self.hidden_quantity = self.total_quantity - self.displayed_quantity
        
        # Validate quantities
        if self.displayed_quantity <= 0:
            raise ValueError("displayed_quantity must be positive")
        if self.displayed_quantity > self.total_quantity:
            raise ValueError("displayed_quantity cannot exceed total_quantity")
        if self.hidden_quantity < 0:
            raise ValueError("hidden_quantity cannot be negative")
        
        # Set disclosure parameters based on type
        if self.disclosure_type == DisclosureType.TIME_BASED:
            if self.disclosure_interval_seconds is None:
                self.disclosure_interval_seconds = 60  # Default 1 minute
        elif self.disclosure_type == DisclosureType.FILL_BASED:
            if self.disclosure_fill_threshold is None:
                self.disclosure_fill_threshold = 0.8  # Default 80% fill
    
    def create_child_order(self) -> OrderRequest:
        """
        Create a child order for the current displayed portion.
        
        Returns:
            OrderRequest for the current displayed portion
        """
        if self.status != IcebergStatus.ACTIVE:
            return None
        
        if self.displayed_quantity <= 0:
            return None
        
        child_order_id = f"CHILD_{self.iceberg_id}_{uuid.uuid4().hex[:8]}"
        
        child_order = OrderRequest(
            order_id=child_order_id,
            symbol=self.symbol,
            side=OrderSide(self.side.lower()),
            quantity=self.displayed_quantity,
            order_type=self.order_type,
            price=self.price,
            time_in_force=self.time_in_force,
            metadata={
                'iceberg_id': self.iceberg_id,
                'parent_order_id': self.parent_order_id,
                'child_order': True,
                'remaining_total': self.total_quantity - self.filled_quantity,
                'remaining_hidden': self.hidden_quantity
            }
        )
        
        self.child_orders.append(child_order_id)
        self.active_child_orders.append(child_order_id)
        
        logger.info(f"Created child order {child_order_id} for iceberg {self.iceberg_id}")
        return child_order
    
    def on_child_fill(self, order_id: str, fill_price: float, fill_quantity: float) -> Optional[OrderRequest]:
        """
        Handle partial or full fill of a child order.
        
        Args:
            order_id: ID of the child order that filled
            fill_price: Price at which child order filled
            fill_quantity: Quantity filled
            
        Returns:
            New child order if more should be revealed, None otherwise
        """
        # Track the child if it exists
        was_active = order_id in self.active_child_orders
        if not was_active:
            logger.warning(f"Child order {order_id} not found in active orders, but fill will still be processed")
        
        # Update quantities
        self.filled_quantity += fill_quantity
        self.displayed_quantity -= fill_quantity
        
        # Remove from active orders if it was there
        if was_active:
            self.active_child_orders.remove(order_id)
        
        # Update metadata
        self.metadata[f'fill_{order_id}'] = {
            'fill_price': fill_price,
            'fill_quantity': fill_quantity,
            'fill_time': datetime.utcnow().isoformat()
        }
        
        # Check if iceberg is complete
        if self.filled_quantity >= self.total_quantity:
            self.status = IcebergStatus.COMPLETED
            self.completed_at = datetime.utcnow()
            logger.info(f"Iceberg {self.iceberg_id} completed with {self.filled_quantity} filled")
            return None
        
        # Check if we should reveal more
        if self.hidden_quantity > 0 and self.should_disclose():
            return self.disclose_next_portion()
        
        return None
    
    def should_disclose(self) -> bool:
        """
        Check if a new portion should be disclosed based on disclosure type.
        
        Returns:
            True if new portion should be disclosed
        """
        if self.disclosure_type == DisclosureType.TIME_BASED:
            if self.last_disclosed_at is None:
                return True
            
            time_since_last = datetime.utcnow() - self.last_disclosed_at
            return time_since_last.total_seconds() >= self.disclosure_interval_seconds
            
        elif self.disclosure_type == DisclosureType.FILL_BASED:
            if self.displayed_quantity <= 0:
                return True
            
            # Calculate fill percentage of current displayed portion
            if self.displayed_quantity > 0:
                fill_percentage = 1.0 - (self.displayed_quantity / (self.displayed_quantity + self.hidden_quantity))
                return fill_percentage >= self.disclosure_fill_threshold
        
        return False
    
    def disclose_next_portion(self) -> Optional[OrderRequest]:
        """
        Disclose the next portion of the iceberg order.
        
        Returns:
            New child order for the disclosed portion (without updating displayed_quantity yet)
        """
        if self.hidden_quantity <= 0:
            return None
        
        # Use the original disclosure chunk size to disclose similar portions
        disclosed_quantity = min(self._original_disclosed, self.hidden_quantity)
        
        # Update hidden_quantity only (displayed will be updated when child is placed)
        self.hidden_quantity -= disclosed_quantity
        
        # Update timing
        self.last_disclosed_at = datetime.utcnow()
        
        logger.info(f"Disclosed {disclosed_quantity} shares for iceberg {self.iceberg_id}")
        logger.info(f"Remaining hidden: {self.hidden_quantity}")
        
        # Create child order with the disclosed quantity
        # We temporarily set displayed to create the order, then reset it
        original_displayed = self.displayed_quantity
        self.displayed_quantity = disclosed_quantity
        child_order = self.create_child_order()
        self.displayed_quantity = original_displayed  # Reset to show it's not yet active
        
        return child_order
    
    def cancel(self) -> List[str]:
        """
        Cancel the iceberg order and all child orders.
        
        Returns:
            List of child order IDs to cancel
        """
        orders_to_cancel = self.active_child_orders.copy()
        
        self.status = IcebergStatus.CANCELLED
        self.completed_at = datetime.utcnow()
        self.active_child_orders.clear()
        
        logger.info(f"Cancelled iceberg {self.iceberg_id}, cancelling {len(orders_to_cancel)} child orders")
        return orders_to_cancel
    
    def expire(self) -> List[str]:
        """
        Mark the iceberg order as expired.
        
        Returns:
            List of child order IDs to cancel
        """
        if self.status == IcebergStatus.ACTIVE:
            self.status = IcebergStatus.EXPIRED
            self.completed_at = datetime.utcnow()
            orders_to_cancel = self.active_child_orders.copy()
            self.active_child_orders.clear()
            
            logger.info(f"Expired iceberg {self.iceberg_id}, cancelling {len(orders_to_cancel)} child orders")
            return orders_to_cancel
        
        return []
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of the iceberg order."""
        return {
            'iceberg_id': self.iceberg_id,
            'parent_order_id': self.parent_order_id,
            'symbol': self.symbol,
            'side': self.side,
            'status': self.status.value,
            'total_quantity': self.total_quantity,
            'displayed_quantity': self.displayed_quantity,
            'filled_quantity': self.filled_quantity,
            'hidden_quantity': self.hidden_quantity,
            'disclosure_type': self.disclosure_type.value,
            'disclosure_interval_seconds': self.disclosure_interval_seconds,
            'disclosure_fill_threshold': self.disclosure_fill_threshold,
            'child_orders_count': len(self.child_orders),
            'active_child_orders_count': len(self.active_child_orders),
            'created_at': self.created_at.isoformat(),
            'last_disclosed_at': self.last_disclosed_at.isoformat() if self.last_disclosed_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'completion_pct': (self.filled_quantity / self.total_quantity) * 100 if self.total_quantity > 0 else 0,
            'metadata': self.metadata
        }
    
    def is_active(self) -> bool:
        """Check if iceberg order is still active."""
        return self.status == IcebergStatus.ACTIVE
    
    def is_complete(self) -> bool:
        """Check if iceberg order is complete."""
        return self.status in [IcebergStatus.COMPLETED, IcebergStatus.CANCELLED, IcebergStatus.EXPIRED]
    
    def get_progress(self) -> Dict[str, float]:
        """Get progress metrics for the iceberg order."""
        total_pct = (self.filled_quantity / self.total_quantity) * 100 if self.total_quantity > 0 else 0
        hidden_pct = (self.hidden_quantity / self.total_quantity) * 100 if self.total_quantity > 0 else 0
        displayed_pct = (self.displayed_quantity / self.total_quantity) * 100 if self.total_quantity > 0 else 0
        
        return {
            'total_filled_pct': total_pct,
            'hidden_pct': hidden_pct,
            'displayed_pct': displayed_pct,
            'filled_quantity': self.filled_quantity,
            'remaining_quantity': self.total_quantity - self.filled_quantity
        }


class IcebergManager:
    """
    Manager for iceberg orders.
    """
    
    def __init__(self):
        self.icebergs: Dict[str, IcebergOrder] = {}
        self.order_to_iceberg: Dict[str, str] = {}  # Maps child order ID to iceberg ID
        self.logger = logging.getLogger(__name__)
    
    def create_iceberg(
        self,
        symbol: str,
        side: str,
        total_quantity: float,
        displayed_quantity: float,
        disclosure_type: DisclosureType = DisclosureType.TIME_BASED,
        disclosure_interval_seconds: Optional[int] = None,
        disclosure_fill_threshold: Optional[float] = None,
        order_type: str = "limit",
        price: Optional[float] = None,
        time_in_force: str = "day"
    ) -> str:
        """
        Create a new iceberg order.
        
        Args:
            symbol: Symbol to trade
            side: Side ("BUY" or "SELL")
            total_quantity: Total quantity to execute
            displayed_quantity: Quantity to display initially
            disclosure_type: How to disclose remaining portions
            disclosure_interval_seconds: Time interval for time-based disclosure
            disclosure_fill_threshold: Fill threshold for fill-based disclosure
            order_type: Order type for child orders
            price: Price for limit orders
            time_in_force: Time in force for child orders
            
        Returns:
            Iceberg ID of the created order
        """
        iceberg_id = str(uuid.uuid4())[:8]
        parent_order_id = f"PARENT_{iceberg_id}"
        
        # Create iceberg order
        iceberg = IcebergOrder(
            iceberg_id=iceberg_id,
            parent_order_id=parent_order_id,
            symbol=symbol,
            side=side,
            total_quantity=total_quantity,
            displayed_quantity=displayed_quantity,
            disclosure_type=disclosure_type,
            disclosure_interval_seconds=disclosure_interval_seconds,
            disclosure_fill_threshold=disclosure_fill_threshold,
            order_type=order_type,
            price=price,
            time_in_force=time_in_force
        )
        
        # Store iceberg
        self.icebergs[iceberg_id] = iceberg
        
        self.logger.info(f"Created iceberg {iceberg_id} for {symbol} ({total_quantity} total, {displayed_quantity} displayed)")
        return iceberg_id
    
    def place_first_child_order(self, iceberg_id: str) -> Optional[OrderRequest]:
        """Place the first child order for an iceberg."""
        if iceberg_id not in self.icebergs:
            return None
        
        iceberg = self.icebergs[iceberg_id]
        child_order = iceberg.create_child_order()
        
        if child_order:
            self.order_to_iceberg[child_order.order_id] = iceberg_id
        
        return child_order
    
    def on_child_fill(self, order_id: str, fill_price: float, fill_quantity: float) -> Optional[OrderRequest]:
        """
        Handle child order fill and potentially create new child order.
        
        Args:
            order_id: ID of the child order that filled
            fill_price: Price at which child order filled
            fill_quantity: Quantity filled
            
        Returns:
            New child order if more should be revealed
        """
        iceberg_id = self.order_to_iceberg.get(order_id)
        if not iceberg_id:
            return None
        
        iceberg = self.icebergs[iceberg_id]
        new_child_order = iceberg.on_child_fill(order_id, fill_price, fill_quantity)
        
        # Track new child order if created
        if new_child_order:
            self.order_to_iceberg[new_child_order.order_id] = iceberg_id
        
        # Clean up old order mapping
        self.order_to_iceberg.pop(order_id, None)
        
        return new_child_order
    
    def check_disclosure_timing(self, iceberg_id: str) -> Optional[OrderRequest]:
        """
        Check if an iceberg should disclose new portion based on timing.
        
        Args:
            iceberg_id: ID of the iceberg to check
            
        Returns:
            New child order if disclosure is due
        """
        if iceberg_id not in self.icebergs:
            return None
        
        iceberg = self.icebergs[iceberg_id]
        
        if iceberg.is_active() and iceberg.should_disclose():
            return iceberg.disclose_next_portion()
        
        return None
    
    def cancel_iceberg(self, iceberg_id: str) -> List[str]:
        """Cancel an iceberg order and return child orders to cancel."""
        if iceberg_id not in self.icebergs:
            return []
        
        iceberg = self.icebergs[iceberg_id]
        orders_to_cancel = iceberg.cancel()
        
        # Clean up order mappings
        for order_id in orders_to_cancel:
            self.order_to_iceberg.pop(order_id, None)
        
        return orders_to_cancel
    
    def expire_iceberg(self, iceberg_id: str) -> List[str]:
        """Expire an iceberg order and return child orders to cancel."""
        if iceberg_id not in self.icebergs:
            return []
        
        iceberg = self.icebergs[iceberg_id]
        orders_to_cancel = iceberg.expire()
        
        # Clean up order mappings
        for order_id in orders_to_cancel:
            self.order_to_iceberg.pop(order_id, None)
        
        return orders_to_cancel
    
    def get_iceberg(self, iceberg_id: str) -> Optional[IcebergOrder]:
        """Get iceberg by ID."""
        return self.icebergs.get(iceberg_id)
    
    def get_iceberg_by_order(self, order_id: str) -> Optional[IcebergOrder]:
        """Get iceberg that contains a specific child order."""
        iceberg_id = self.order_to_iceberg.get(order_id)
        if iceberg_id:
            return self.icebergs.get(iceberg_id)
        return None
    
    def get_active_icebergs(self) -> List[IcebergOrder]:
        """Get all active iceberg orders."""
        return [iceberg for iceberg in self.icebergs.values() if iceberg.is_active()]
    
    def get_icebergs_by_symbol(self, symbol: str) -> List[IcebergOrder]:
        """Get all iceberg orders for a specific symbol."""
        return [iceberg for iceberg in self.icebergs.values() if iceberg.symbol == symbol]
    
    def cleanup_completed_icebergs(self) -> int:
        """Clean up completed, cancelled, or expired icebergs."""
        icebergs_to_remove = [
            iceberg_id for iceberg_id, iceberg in self.icebergs.items()
            if iceberg.is_complete()
        ]
        
        for iceberg_id in icebergs_to_remove:
            # Clean up order mappings
            iceberg = self.icebergs[iceberg_id]
            for order_id in iceberg.child_orders:
                self.order_to_iceberg.pop(order_id, None)
            
            # Remove iceberg
            del self.icebergs[iceberg_id]
            self.logger.info(f"Cleaned up iceberg {iceberg_id}")
        
        return len(icebergs_to_remove)
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get summary status of all iceberg orders."""
        total_icebergs = len(self.icebergs)
        active_icebergs = len(self.get_active_icebergs())
        completed_icebergs = len([i for i in self.icebergs.values() if i.status == IcebergStatus.COMPLETED])
        cancelled_icebergs = len([i for i in self.icebergs.values() if i.status == IcebergStatus.CANCELLED])
        
        total_quantity = sum(i.total_quantity for i in self.icebergs.values())
        filled_quantity = sum(i.filled_quantity for i in self.icebergs.values())
        
        return {
            'total_icebergs': total_icebergs,
            'active_icebergs': active_icebergs,
            'completed_icebergs': completed_icebergs,
            'cancelled_icebergs': cancelled_icebergs,
            'expired_icebergs': len([i for i in self.icebergs.values() if i.status == IcebergStatus.EXPIRED]),
            'total_quantity': total_quantity,
            'filled_quantity': filled_quantity,
            'fill_rate_pct': (filled_quantity / total_quantity * 100) if total_quantity > 0 else 0,
            'total_child_orders': sum(len(i.child_orders) for i in self.icebergs.values()),
            'active_child_orders': sum(len(i.active_child_orders) for i in self.icebergs.values())
        }


# Helper functions for common iceberg patterns

def create_large_order_iceberg(
    symbol: str,
    side: str,
    total_quantity: float,
    display_ratio: float = 0.1,  # Display 10% by default
    disclosure_type: DisclosureType = DisclosureType.TIME_BASED,
    disclosure_interval: int = 60,  # 1 minute
    order_type: str = "limit",
    price: Optional[float] = None
) -> str:
    """
    Create an iceberg order for large positions.
    
    Args:
        symbol: Symbol to trade
        side: Side ("BUY" or "SELL")
        total_quantity: Total quantity to execute
        display_ratio: Ratio of total quantity to display (0.1 = 10%)
        disclosure_type: How to disclose remaining portions
        disclosure_interval: Seconds between disclosures
        order_type: Order type for child orders
        price: Price for limit orders
        
    Returns:
        Iceberg ID
    """
    displayed_quantity = total_quantity * display_ratio
    
    return IcebergManager().create_iceberg(
        symbol=symbol,
        side=side,
        total_quantity=total_quantity,
        displayed_quantity=displayed_quantity,
        disclosure_type=disclosure_type,
        disclosure_interval_seconds=disclosure_interval,
        order_type=order_type,
        price=price
    )