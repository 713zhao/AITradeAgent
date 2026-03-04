"""
OCO (One Cancels Other) Order Manager

Implements OCO order groups where executing one order automatically
cancels the other orders in the group.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from enum import Enum
from dataclasses import dataclass, field
import logging
import uuid

from ..base_broker import OrderRequest, Order, OrderStatus, OrderSide

logger = logging.getLogger(__name__)


class OCOGroupStatus(Enum):
    """Status of an OCO order group."""
    ACTIVE = "active"  # All orders active, waiting for execution
    PARTIAL = "partial"  # One order filled, others cancelled
    COMPLETED = "completed"  # All orders handled
    CANCELLED = "cancelled"  # Group cancelled manually
    EXPIRED = "expired"  # Group expired


@dataclass
class OCOGroup:
    """
    OCO (One Cancels Other) order group.
    
    When one order in the group fills, all other orders in the group
    are automatically cancelled.
    """
    
    group_id: str
    orders: List[OrderRequest] = field(default_factory=list)
    status: OCOGroupStatus = OCOGroupStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    triggered_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Tracking filled order
    filled_order_id: Optional[str] = None
    filled_order_side: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_order(self, order: OrderRequest) -> None:
        """Add an order to the OCO group."""
        # Validate order doesn't already exist in group
        for existing_order in self.orders:
            if existing_order.order_id == order.order_id:
                raise ValueError(f"Order {order.order_id} already exists in this OCO group")
        
        self.orders.append(order)
        logger.info(f"Added order {order.order_id} to OCO group {self.group_id}")
    
    def remove_order(self, order_id: str) -> bool:
        """Remove an order from the OCO group."""
        for i, order in enumerate(self.orders):
            if order.order_id == order_id:
                removed = self.orders.pop(i)
                logger.info(f"Removed order {order_id} from OCO group {self.group_id}")
                return True
        return False
    
    def trigger(self, filled_order_id: str) -> None:
        """
        Trigger OCO group when one order fills.
        
        Args:
            filled_order_id: ID of the order that filled
        """
        if self.status != OCOGroupStatus.ACTIVE:
            logger.warning(f"OCO group {self.group_id} not active, cannot trigger")
            return
        
        # Find the filled order
        filled_order = None
        for order in self.orders:
            if order.order_id == filled_order_id:
                filled_order = order
                break
        
        if not filled_order:
            logger.error(f"Filled order {filled_order_id} not found in group {self.group_id}")
            return
        
        # Update group status
        self.status = OCOGroupStatus.PARTIAL
        self.triggered_at = datetime.utcnow()
        self.filled_order_id = filled_order_id
        self.filled_order_side = filled_order.side.name if hasattr(filled_order.side, 'name') else str(filled_order.side).upper()
        
        # Store filled order details
        self.metadata['filled_order'] = {
            'order_id': filled_order.order_id,
            'symbol': filled_order.symbol,
            'side': filled_order.side,
            'quantity': filled_order.quantity,
            'order_type': filled_order.order_type.value,
            'triggered_at': self.triggered_at.isoformat()
        }
        
        logger.info(f"OCO group {self.group_id} triggered by order {filled_order_id}")
    
    def complete(self) -> None:
        """Mark OCO group as completed."""
        if self.status == OCOGroupStatus.PARTIAL:
            self.status = OCOGroupStatus.COMPLETED
            self.completed_at = datetime.utcnow()
            logger.info(f"OCO group {self.group_id} completed")
    
    def cancel(self) -> None:
        """Cancel the entire OCO group."""
        if self.status in [OCOGroupStatus.ACTIVE, OCOGroupStatus.PARTIAL]:
            self.status = OCOGroupStatus.CANCELLED
            logger.info(f"OCO group {self.group_id} cancelled")
    
    def expire(self) -> None:
        """Mark OCO group as expired."""
        if self.status == OCOGroupStatus.ACTIVE:
            self.status = OCOGroupStatus.EXPIRED
            logger.info(f"OCO group {self.group_id} expired")
    
    def get_orders_to_cancel(self) -> List[str]:
        """
        Get list of order IDs that should be cancelled (all except filled order).
        
        Returns:
            List of order IDs to cancel
        """
        if self.filled_order_id is None:
            return []
        
        return [order.order_id for order in self.orders 
                if order.order_id != self.filled_order_id]
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of the OCO group."""
        return {
            'group_id': self.group_id,
            'status': self.status.value,
            'order_count': len(self.orders),
            'orders': [
                {
                    'order_id': order.order_id,
                    'symbol': order.symbol,
                    'side': order.side.value,
                    'quantity': order.quantity,
                    'order_type': order.order_type.value,
                    'price': order.price,
                    'stop_price': order.stop_price
                }
                for order in self.orders
            ],
            'filled_order_id': self.filled_order_id,
            'filled_order_side': self.filled_order_side,
            'created_at': self.created_at.isoformat(),
            'triggered_at': self.triggered_at.isoformat() if self.triggered_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'metadata': self.metadata
        }
    
    def is_active(self) -> bool:
        """Check if OCO group is still active."""
        return self.status == OCOGroupStatus.ACTIVE
    
    def is_complete(self) -> bool:
        """Check if OCO group is complete."""
        return self.status in [OCOGroupStatus.COMPLETED, OCOGroupStatus.CANCELLED, OCOGroupStatus.EXPIRED]
    
    def validate_group(self) -> List[str]:
        """
        Validate OCO group for common issues.
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        if len(self.orders) < 2:
            errors.append("OCO group must have at least 2 orders")
        
        # Check order types
        for order in self.orders:
            if order.order_type in ['market', 'stop']:
                errors.append(f"OCO group contains unsupported order type: {order.order_type.value}")
        
        return errors


class OCOManager:
    """
    Manager for OCO (One Cancels Other) order groups.
    """
    
    def __init__(self):
        self.groups: Dict[str, OCOGroup] = {}
        self.order_to_group: Dict[str, str] = {}  # Maps order_id to group_id
        self.logger = logging.getLogger(__name__)
    
    def create_group(self, orders: List[OrderRequest]) -> str:
        """
        Create a new OCO group with the given orders.
        
        Args:
            orders: List of orders to include in the OCO group
            
        Returns:
            Group ID of the created group
        """
        group_id = str(uuid.uuid4())[:8]
        
        # Create group
        group = OCOGroup(group_id=group_id)
        
        # Add orders
        for order in orders:
            group.add_order(order)
            self.order_to_group[order.order_id] = group_id
        
        # Validate group
        errors = group.validate_group()
        if errors:
            # Clean up on validation failure
            for order in orders:
                self.order_to_group.pop(order.order_id, None)
            raise ValueError(f"OCO group validation failed: {'; '.join(errors)}")
        
        # Store group
        self.groups[group_id] = group
        
        self.logger.info(f"Created OCO group {group_id} with {len(orders)} orders")
        return group_id
    
    def add_order_to_group(self, group_id: str, order: OrderRequest) -> None:
        """Add an order to an existing OCO group."""
        if group_id not in self.groups:
            raise ValueError(f"OCO group {group_id} not found")
        
        group = self.groups[group_id]
        group.add_order(order)
        self.order_to_group[order.order_id] = group_id
        
        self.logger.info(f"Added order {order.order_id} to OCO group {group_id}")
    
    def remove_order_from_group(self, group_id: str, order_id: str) -> bool:
        """Remove an order from an OCO group."""
        if group_id not in self.groups:
            return False
        
        group = self.groups[group_id]
        if group.remove_order(order_id):
            self.order_to_group.pop(order_id, None)
            return True
        return False
    
    def trigger_group(self, order_id: str) -> Optional[str]:
        """
        Trigger OCO group when an order fills.
        
        Args:
            order_id: ID of the order that filled
            
        Returns:
            Group ID that was triggered
        """
        group_id = self.order_to_group.get(order_id)
        if not group_id:
            self.logger.warning(f"Order {order_id} not found in any OCO group")
            return None
        
        group = self.groups[group_id]
        group.trigger(order_id)
        
        self.logger.info(f"OCO group {group_id} triggered by order {order_id}")
        return group_id
    
    def get_group(self, group_id: str) -> Optional[OCOGroup]:
        """Get OCO group by ID."""
        return self.groups.get(group_id)
    
    def get_group_by_order(self, order_id: str) -> Optional[OCOGroup]:
        """Get OCO group that contains a specific order."""
        group_id = self.order_to_group.get(order_id)
        if group_id:
            return self.groups.get(group_id)
        return None
    
    def get_orders_to_cancel(self, filled_order_id: str) -> List[str]:
        """
        Get list of order IDs that should be cancelled when an order fills.
        
        Args:
            filled_order_id: ID of the order that filled
            
        Returns:
            List of order IDs to cancel
        """
        group = self.get_group_by_order(filled_order_id)
        if group:
            return group.get_orders_to_cancel()
        return []
    
    def complete_group(self, group_id: str) -> None:
        """Mark an OCO group as completed."""
        if group_id in self.groups:
            self.groups[group_id].complete()
    
    def cancel_group(self, group_id: str) -> None:
        """Cancel an OCO group."""
        if group_id in self.groups:
            self.groups[group_id].cancel()
    
    def expire_group(self, group_id: str) -> None:
        """Mark an OCO group as expired."""
        if group_id in self.groups:
            self.groups[group_id].expire()
    
    def get_active_groups(self) -> List[OCOGroup]:
        """Get all active OCO groups."""
        return [group for group in self.groups.values() if group.is_active()]
    
    def get_groups_by_symbol(self, symbol: str) -> List[OCOGroup]:
        """Get all OCO groups containing orders for a specific symbol."""
        return [group for group in self.groups.values() 
                if any(order.symbol == symbol for order in group.orders)]
    
    def cleanup_completed_groups(self) -> int:
        """
        Clean up completed, cancelled, or expired groups.
        
        Returns:
            Number of groups cleaned up
        """
        groups_to_remove = [
            group_id for group_id, group in self.groups.items()
            if group.is_complete()
        ]
        
        for group_id in groups_to_remove:
            # Remove order mappings
            group = self.groups[group_id]
            for order in group.orders:
                self.order_to_group.pop(order.order_id, None)
            
            # Remove group
            del self.groups[group_id]
            self.logger.info(f"Cleaned up OCO group {group_id}")
        
        return len(groups_to_remove)
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get summary status of all OCO groups."""
        total_groups = len(self.groups)
        active_groups = len(self.get_active_groups())
        completed_groups = len([g for g in self.groups.values() if g.status == OCOGroupStatus.COMPLETED])
        cancelled_groups = len([g for g in self.groups.values() if g.status == OCOGroupStatus.CANCELLED])
        expired_groups = len([g for g in self.groups.values() if g.status == OCOGroupStatus.EXPIRED])
        
        return {
            'total_groups': total_groups,
            'active_groups': active_groups,
            'completed_groups': completed_groups,
            'cancelled_groups': cancelled_groups,
            'expired_groups': expired_groups,
            'total_orders_in_groups': sum(len(group.orders) for group in self.groups.values())
        }


# Helper functions for common OCO patterns

def create_profit_target_stop_loss_oco(
    symbol: str,
    quantity: float,
    entry_price: Optional[float] = None,
    profit_target_pct: float = 5.0,
    stop_loss_pct: float = -3.0,
    order_type: str = "limit"
) -> List[OrderRequest]:
    """
    Create a common OCO pattern: profit target + stop loss.
    
    Args:
        symbol: Symbol to trade
        quantity: Quantity to trade
        entry_price: Entry price (for reference)
        profit_target_pct: Profit target percentage (e.g., 5.0 for +5%)
        stop_loss_pct: Stop loss percentage (e.g., -3.0 for -3%)
        order_type: Order type for TP/SL orders
        
    Returns:
        List of two OrderRequest objects (profit target and stop loss)
    """
    if entry_price is None:
        raise ValueError("entry_price is required for profit target/stop loss calculation")
    
    profit_target_price = entry_price * (1 + profit_target_pct / 100)
    stop_loss_price = entry_price * (1 + stop_loss_pct / 100)
    
    # Create profit target order (SELL for long positions)
    profit_target_order = OrderRequest(
        order_id=f"TP_{symbol}_{uuid.uuid4().hex[:8]}",
        symbol=symbol,
        side=OrderSide.SELL,
        quantity=quantity,
        order_type=order_type,
        price=profit_target_price,
        time_in_force="gtc",
        metadata={'order_purpose': 'profit_target'}
    )
    
    # Create stop loss order (SELL for long positions)
    stop_loss_order = OrderRequest(
        order_id=f"SL_{symbol}_{uuid.uuid4().hex[:8]}",
        symbol=symbol,
        side=OrderSide.SELL,
        quantity=quantity,
        order_type=order_type,
        price=stop_loss_price,
        time_in_force="gtc",
        metadata={'order_purpose': 'stop_loss'}
    )
    
    return [profit_target_order, stop_loss_order]


def create_entry_exit_oco(
    symbol: str,
    quantity: float,
    entry_price: float,
    exit_price: float,
    entry_side: str,
    exit_side: str,
    order_type: str = "limit"
) -> List[OrderRequest]:
    """
    Create an OCO pattern for entry and exit orders.
    
    Args:
        symbol: Symbol to trade
        quantity: Quantity to trade
        entry_price: Entry price
        exit_price: Exit price
        entry_side: Side for entry ("BUY" or "SELL")
        exit_side: Side for exit ("BUY" or "SELL")
        order_type: Order type for both orders
        
    Returns:
        List of two OrderRequest objects (entry and exit)
    """
    entry_side_enum = OrderSide(entry_side)
    exit_side_enum = OrderSide(exit_side)
    
    entry_order = OrderRequest(
        order_id=f"ENTRY_{symbol}_{uuid.uuid4().hex[:8]}",
        symbol=symbol,
        side=entry_side_enum,
        quantity=quantity,
        order_type=order_type,
        price=entry_price,
        time_in_force="day",
        metadata={'order_purpose': 'entry'}
    )
    
    exit_order = OrderRequest(
        order_id=f"EXIT_{symbol}_{uuid.uuid4().hex[:8]}",
        symbol=symbol,
        side=exit_side_enum,
        quantity=quantity,
        order_type=order_type,
        price=exit_price,
        time_in_force="day",
        metadata={'order_purpose': 'exit'}
    )
    
    return [entry_order, exit_order]