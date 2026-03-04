"""
Bracket Order Implementation

Implements bracket orders that automatically create profit target and stop loss
orders when the entry order fills.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass, field
import logging
import uuid

from ..base_broker import OrderRequest, Order, OrderStatus, OrderSide, OrderType

logger = logging.getLogger(__name__)


class BracketStatus(Enum):
    """Status of a bracket order group."""
    PENDING = "pending"  # Entry order not yet placed
    ACTIVE = "active"  # Entry order placed, waiting for fill
    ENTRY_FILLED = "entry_filled"  # Entry filled, TP/SL orders placed
    PARTIAL = "partial"  # One exit order filled, other cancelled
    COMPLETED = "completed"  # All exit orders handled
    CANCELLED = "cancelled"  # Bracket cancelled manually
    EXPIRED = "expired"  # Bracket expired


@dataclass
class BracketOrder:
    """
    Bracket order that creates a complete trading setup.
    
    When the entry order fills, automatically creates profit target
    and stop loss orders that form an OCO group.
    """
    
    bracket_id: str
    symbol: str
    quantity: float
    entry_price: Optional[float] = None
    profit_target_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    
    # Order tracking
    entry_order_id: Optional[str] = None
    profit_target_order_id: Optional[str] = None
    stop_loss_order_id: Optional[str] = None
    
    # Status tracking
    status: BracketStatus = BracketStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    entry_filled_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Entry order details
    entry_side: str = "buy"  # Default to buy for long positions
    entry_order_type: OrderType = OrderType.MARKET
    
    # Exit order details
    profit_target_side: str = "sell"  # Default to sell for long positions
    stop_loss_side: str = "sell"      # Default to sell for long positions
    exit_order_type: OrderType = OrderType.LIMIT
    
    # Time in force
    entry_time_in_force: str = "day"
    exit_time_in_force: str = "gtc"
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def create_entry_order(self) -> OrderRequest:
        """Create the entry order for the bracket."""
        if self.entry_price is None:
            raise ValueError("entry_price must be set before creating entry order")
        
        self.entry_order_id = f"ENTRY_{self.bracket_id}_{uuid.uuid4().hex[:8]}"
        
        entry_order = OrderRequest(
            order_id=self.entry_order_id,
            symbol=self.symbol,
            side=OrderSide(self.entry_side.lower()),
            quantity=self.quantity,
            order_type=self.entry_order_type,
            price=self.entry_price,
            time_in_force=self.entry_time_in_force,
            metadata={
                'bracket_id': self.bracket_id,
                'order_purpose': 'entry',
                'bracket_entry': True
            }
        )
        
        logger.info(f"Created entry order {self.entry_order_id} for bracket {self.bracket_id}")
        return entry_order
    
    def create_exit_orders(self) -> List[OrderRequest]:
        """
        Create profit target and stop loss orders for the bracket.
        
        Returns:
            List of two OrderRequest objects (profit target and stop loss)
        """
        if self.profit_target_price is None or self.stop_loss_price is None:
            raise ValueError("profit_target_price and stop_loss_price must be set")
        
        # Create profit target order
        self.profit_target_order_id = f"PT_{self.bracket_id}_{uuid.uuid4().hex[:8]}"
        profit_target_order = OrderRequest(
            order_id=self.profit_target_order_id,
            symbol=self.symbol,
            side=OrderSide(self.profit_target_side.lower()),
            quantity=self.quantity,
            order_type=self.exit_order_type,
            price=self.profit_target_price,
            time_in_force=self.exit_time_in_force,
            metadata={
                'bracket_id': self.bracket_id,
                'order_purpose': 'profit_target',
                'bracket_exit': True,
                'parent_order': self.entry_order_id
            }
        )
        
        # Create stop loss order
        self.stop_loss_order_id = f"SL_{self.bracket_id}_{uuid.uuid4().hex[:8]}"
        stop_loss_order = OrderRequest(
            order_id=self.stop_loss_order_id,
            symbol=self.symbol,
            side=OrderSide(self.stop_loss_side.lower()),
            quantity=self.quantity,
            order_type=self.exit_order_type,
            price=self.stop_loss_price,
            time_in_force=self.exit_time_in_force,
            metadata={
                'bracket_id': self.bracket_id,
                'order_purpose': 'stop_loss',
                'bracket_exit': True,
                'parent_order': self.entry_order_id
            }
        )
        
        logger.info(f"Created exit orders for bracket {self.bracket_id}")
        return [profit_target_order, stop_loss_order]
    
    def on_entry_filled(self, fill_price: float, fill_quantity: float) -> List[OrderRequest]:
        """
        Handle entry order fill and create exit orders.
        
        Args:
            fill_price: Price at which entry order filled
            fill_quantity: Quantity filled
            
        Returns:
            List of exit orders to place
        """
        if self.status != BracketStatus.ACTIVE:
            logger.warning(f"Bracket {self.bracket_id} not active, cannot handle entry fill")
            return []
        
        # Update status and tracking
        self.status = BracketStatus.ENTRY_FILLED
        self.entry_filled_at = datetime.utcnow()
        self.metadata['entry_fill_price'] = fill_price
        self.metadata['entry_fill_quantity'] = fill_quantity
        
        # Create exit orders
        exit_orders = self.create_exit_orders()
        
        logger.info(f"Entry filled for bracket {self.bracket_id} at {fill_price}, creating exit orders")
        return exit_orders
    
    def on_exit_filled(self, order_id: str, fill_price: float, fill_quantity: float) -> None:
        """
        Handle exit order fill.
        
        Args:
            order_id: ID of the exit order that filled
            fill_price: Price at which exit order filled
            fill_quantity: Quantity filled
        """
        if self.status != BracketStatus.ENTRY_FILLED:
            logger.warning(f"Bracket {self.bracket_id} not in entry_filled state")
            return
        
        # Determine which exit order filled
        filled_order_type = "unknown"
        if order_id == self.profit_target_order_id:
            filled_order_type = "profit_target"
        elif order_id == self.stop_loss_order_id:
            filled_order_type = "stop_loss"
        
        # Update metadata
        self.metadata[f'{filled_order_type}_fill_price'] = fill_price
        self.metadata[f'{filled_order_type}_fill_quantity'] = fill_quantity
        self.metadata['completed_exit_order'] = filled_order_type
        
        # Update status
        self.status = BracketStatus.PARTIAL
        self.completed_at = datetime.utcnow()
        
        logger.info(f"Exit order {filled_order_type} filled for bracket {self.bracket_id} at {fill_price}")
    
    def cancel(self) -> List[str]:
        """
        Cancel the bracket order and all associated orders.
        
        Returns:
            List of order IDs that should be cancelled
        """
        orders_to_cancel = []
        
        if self.entry_order_id and self.status in [BracketStatus.PENDING, BracketStatus.ACTIVE]:
            orders_to_cancel.append(self.entry_order_id)
        
        if self.profit_target_order_id and self.status == BracketStatus.ENTRY_FILLED:
            orders_to_cancel.append(self.profit_target_order_id)
        
        if self.stop_loss_order_id and self.status == BracketStatus.ENTRY_FILLED:
            orders_to_cancel.append(self.stop_loss_order_id)
        
        self.status = BracketStatus.CANCELLED
        self.completed_at = datetime.utcnow()
        
        logger.info(f"Cancelled bracket {self.bracket_id}, cancelling orders: {orders_to_cancel}")
        return orders_to_cancel
    
    def complete(self) -> None:
        """Mark bracket order as completed."""
        if self.status == BracketStatus.PARTIAL:
            self.status = BracketStatus.COMPLETED
            if not self.completed_at:
                self.completed_at = datetime.utcnow()
            logger.info(f"Bracket {self.bracket_id} completed")
    
    def expire(self) -> None:
        """Mark bracket order as expired."""
        if self.status in [BracketStatus.PENDING, BracketStatus.ACTIVE]:
            self.status = BracketStatus.EXPIRED
            self.completed_at = datetime.utcnow()
            logger.info(f"Bracket {self.bracket_id} expired")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of the bracket order."""
        return {
            'bracket_id': self.bracket_id,
            'symbol': self.symbol,
            'quantity': self.quantity,
            'status': self.status.value,
            'entry_price': self.entry_price,
            'profit_target_price': self.profit_target_price,
            'stop_loss_price': self.stop_loss_price,
            'entry_order_id': self.entry_order_id,
            'profit_target_order_id': self.profit_target_order_id,
            'stop_loss_order_id': self.stop_loss_order_id,
            'entry_side': self.entry_side,
            'profit_target_side': self.profit_target_side,
            'stop_loss_side': self.stop_loss_side,
            'created_at': self.created_at.isoformat(),
            'entry_filled_at': self.entry_filled_at.isoformat() if self.entry_filled_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'metadata': self.metadata
        }
    
    def is_active(self) -> bool:
        """Check if bracket order is still active."""
        return self.status in [BracketStatus.PENDING, BracketStatus.ACTIVE, BracketStatus.ENTRY_FILLED]
    
    def is_entry_pending(self) -> bool:
        """Check if entry order is still pending."""
        return self.status in [BracketStatus.PENDING, BracketStatus.ACTIVE]
    
    def is_exits_pending(self) -> bool:
        """Check if exit orders are pending."""
        return self.status == BracketStatus.ENTRY_FILLED
    
    def get_orders_to_cancel(self) -> List[str]:
        """Get list of order IDs that should be cancelled."""
        if self.status == BracketStatus.CANCELLED:
            return []
        
        orders_to_cancel = []
        
        if self.status in [BracketStatus.PENDING, BracketStatus.ACTIVE] and self.entry_order_id:
            orders_to_cancel.append(self.entry_order_id)
        
        if self.status == BracketStatus.ENTRY_FILLED:
            if self.profit_target_order_id:
                orders_to_cancel.append(self.profit_target_order_id)
            if self.stop_loss_order_id:
                orders_to_cancel.append(self.stop_loss_order_id)
        
        return orders_to_cancel
    
    def calculate_risk_reward(self) -> Dict[str, float]:
        """
        Calculate risk-reward metrics for the bracket.
        
        Returns:
            Dictionary with risk-reward metrics
        """
        if self.entry_price is None or self.profit_target_price is None or self.stop_loss_price is None:
            return {}
        
        # Calculate profit and loss amounts
        if self.entry_side == "BUY":
            profit_amount = (self.profit_target_price - self.entry_price) * self.quantity
            loss_amount = (self.entry_price - self.stop_loss_price) * self.quantity
        else:  # SELL
            profit_amount = (self.entry_price - self.profit_target_price) * self.quantity
            loss_amount = (self.stop_loss_price - self.entry_price) * self.quantity
        
        # Calculate percentages
        if self.entry_price > 0:
            profit_pct = ((self.profit_target_price - self.entry_price) / self.entry_price) * 100
            loss_pct = ((self.entry_price - self.stop_loss_price) / self.entry_price) * 100
        else:
            profit_pct = 0
            loss_pct = 0
        
        # Risk-reward ratio
        risk_reward_ratio = abs(profit_amount / loss_amount) if loss_amount > 0 else float('inf')
        
        return {
            'profit_amount': profit_amount,
            'loss_amount': loss_amount,
            'profit_pct': profit_pct,
            'loss_pct': loss_pct,
            'risk_reward_ratio': risk_reward_ratio,
            'entry_price': self.entry_price,
            'profit_target_price': self.profit_target_price,
            'stop_loss_price': self.stop_loss_price
        }


class BracketManager:
    """
    Manager for bracket order groups.
    """
    
    def __init__(self):
        self.brackets: Dict[str, BracketOrder] = {}
        self.order_to_bracket: Dict[str, str] = {}  # Maps order_id to bracket_id
        self.logger = logging.getLogger(__name__)
    
    def create_bracket(
        self,
        symbol: str,
        quantity: float,
        entry_price: Optional[float] = None,
        profit_target_pct: Optional[float] = None,
        stop_loss_pct: Optional[float] = None,
        profit_target_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        entry_side: str = "BUY",
        entry_order_type: OrderType = OrderType.MARKET,
        exit_order_type: OrderType = OrderType.LIMIT,
        entry_time_in_force: str = "day",
        exit_time_in_force: str = "gtc"
    ) -> str:
        """
        Create a new bracket order.
        
        Args:
            symbol: Symbol to trade
            quantity: Quantity to trade
            entry_price: Entry price (optional, can be set later)
            profit_target_pct: Profit target percentage (e.g., 5.0 for +5%)
            stop_loss_pct: Stop loss percentage (e.g., -3.0 for -3%)
            profit_target_price: Absolute profit target price
            stop_loss_price: Absolute stop loss price
            entry_side: Side for entry ("BUY" or "SELL")
            entry_order_type: Order type for entry
            exit_order_type: Order type for exits
            entry_time_in_force: Time in force for entry
            exit_time_in_force: Time in force for exits
            
        Returns:
            Bracket ID of the created bracket
        """
        bracket_id = str(uuid.uuid4())[:8]
        
        # Calculate prices if percentages provided
        calculated_profit_target = None
        calculated_stop_loss = None
        
        if entry_price is not None:
            if profit_target_pct is not None:
                if entry_side == "BUY":
                    calculated_profit_target = entry_price * (1 + profit_target_pct / 100)
                    calculated_stop_loss = entry_price * (1 - stop_loss_pct / 100) if stop_loss_pct else None
                else:  # SELL
                    calculated_profit_target = entry_price * (1 - profit_target_pct / 100)
                    calculated_stop_loss = entry_price * (1 + stop_loss_pct / 100) if stop_loss_pct else None
            
            # Use calculated or provided prices
            final_profit_target = profit_target_price or calculated_profit_target
            final_stop_loss = stop_loss_price or calculated_stop_loss
        else:
            final_profit_target = profit_target_price
            final_stop_loss = stop_loss_price
        
        # Create bracket
        bracket = BracketOrder(
            bracket_id=bracket_id,
            symbol=symbol,
            quantity=quantity,
            entry_price=entry_price,
            profit_target_price=final_profit_target,
            stop_loss_price=final_stop_loss,
            entry_side=entry_side,
            entry_order_type=entry_order_type,
            exit_order_type=exit_order_type,
            entry_time_in_force=entry_time_in_force,
            exit_time_in_force=exit_time_in_force
        )
        
        # Store bracket
        self.brackets[bracket_id] = bracket
        
        self.logger.info(f"Created bracket {bracket_id} for {symbol} ({quantity} shares)")
        return bracket_id
    
    def place_entry_order(self, bracket_id: str) -> Optional[OrderRequest]:
        """Place the entry order for a bracket."""
        if bracket_id not in self.brackets:
            return None
        
        bracket = self.brackets[bracket_id]
        if bracket.status != BracketStatus.PENDING:
            return None
        
        # Create and track entry order
        entry_order = bracket.create_entry_order()
        self.order_to_bracket[entry_order.order_id] = bracket_id
        
        # Update bracket status
        bracket.status = BracketStatus.ACTIVE
        
        return entry_order
    
    def on_entry_filled(self, order_id: str, fill_price: float, fill_quantity: float) -> List[OrderRequest]:
        """
        Handle entry order fill and create exit orders.
        
        Args:
            order_id: ID of the entry order that filled
            fill_price: Price at which entry filled
            fill_quantity: Quantity filled
            
        Returns:
            List of exit orders to place
        """
        bracket_id = self.order_to_bracket.get(order_id)
        if not bracket_id:
            return []
        
        bracket = self.brackets[bracket_id]
        exit_orders = bracket.on_entry_filled(fill_price, fill_quantity)
        
        # Track exit orders
        for exit_order in exit_orders:
            self.order_to_bracket[exit_order.order_id] = bracket_id
        
        return exit_orders
    
    def on_exit_filled(self, order_id: str, fill_price: float, fill_quantity: float) -> Optional[str]:
        """
        Handle exit order fill.
        
        Args:
            order_id: ID of the exit order that filled
            fill_price: Price at which exit filled
            fill_quantity: Quantity filled
            
        Returns:
            Bracket ID that was completed
        """
        bracket_id = self.order_to_bracket.get(order_id)
        if not bracket_id:
            return None
        
        bracket = self.brackets[bracket_id]
        bracket.on_exit_filled(order_id, fill_price, fill_quantity)
        
        # If bracket is now partial, mark as completed
        if bracket.status == BracketStatus.PARTIAL:
            bracket.complete()
        
        return bracket_id
    
    def cancel_bracket(self, bracket_id: str) -> List[str]:
        """Cancel a bracket order and return orders to cancel."""
        if bracket_id not in self.brackets:
            return []
        
        bracket = self.brackets[bracket_id]
        orders_to_cancel = bracket.cancel()
        
        # Clean up order mappings
        for order_id in orders_to_cancel:
            self.order_to_bracket.pop(order_id, None)
        
        return orders_to_cancel
    
    def get_bracket(self, bracket_id: str) -> Optional[BracketOrder]:
        """Get bracket by ID."""
        return self.brackets.get(bracket_id)
    
    def get_bracket_by_order(self, order_id: str) -> Optional[BracketOrder]:
        """Get bracket that contains a specific order."""
        bracket_id = self.order_to_bracket.get(order_id)
        if bracket_id:
            return self.brackets.get(bracket_id)
        return None
    
    def get_active_brackets(self) -> List[BracketOrder]:
        """Get all active bracket orders."""
        return [bracket for bracket in self.brackets.values() if bracket.is_active()]
    
    def get_brackets_by_symbol(self, symbol: str) -> List[BracketOrder]:
        """Get all bracket orders for a specific symbol."""
        return [bracket for bracket in self.brackets.values() if bracket.symbol == symbol]
    
    def cleanup_completed_brackets(self) -> int:
        """Clean up completed, cancelled, or expired brackets."""
        brackets_to_remove = [
            bracket_id for bracket_id, bracket in self.brackets.items()
            if bracket.status in [BracketStatus.COMPLETED, BracketStatus.CANCELLED, BracketStatus.EXPIRED]
        ]
        
        for bracket_id in brackets_to_remove:
            # Clean up order mappings
            bracket = self.brackets[bracket_id]
            for order_id in bracket.get_orders_to_cancel():
                self.order_to_bracket.pop(order_id, None)
            
            # Remove bracket
            del self.brackets[bracket_id]
            self.logger.info(f"Cleaned up bracket {bracket_id}")
        
        return len(brackets_to_remove)
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get summary status of all bracket orders."""
        total_brackets = len(self.brackets)
        active_brackets = len(self.get_active_brackets())
        pending_entry = len([b for b in self.brackets.values() if b.status == BracketStatus.PENDING])
        active_entry = len([b for b in self.brackets.values() if b.status == BracketStatus.ACTIVE])
        entry_filled = len([b for b in self.brackets.values() if b.status == BracketStatus.ENTRY_FILLED])
        completed = len([b for b in self.brackets.values() if b.status == BracketStatus.COMPLETED])
        cancelled = len([b for b in self.brackets.values() if b.status == BracketStatus.CANCELLED])
        
        return {
            'total_brackets': total_brackets,
            'active_brackets': active_brackets,
            'pending_entry': pending_entry,
            'active_entry': active_entry,
            'entry_filled': entry_filled,
            'completed_brackets': completed,
            'cancelled_brackets': cancelled,
            'expired_brackets': len([b for b in self.brackets.values() if b.status == BracketStatus.EXPIRED]),
            'total_orders_tracked': len(self.order_to_bracket)
        }