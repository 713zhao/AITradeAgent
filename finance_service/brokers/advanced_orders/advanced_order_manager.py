"""
Advanced Order Types Integration

Integrates trailing stops, OCO orders, bracket orders, and iceberg orders
with the existing broker system.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from dataclasses import dataclass
import logging

from ..base_broker import OrderRequest, Order, OrderStatus, OrderSide, OrderType
from .trailing_stop import TrailingStopOrder, TrailingStopManager
from .oco_manager import OCOManager, OCOGroup
from .bracket_orders import BracketOrder, BracketManager
from .iceberg_orders import IcebergOrder, IcebergManager

logger = logging.getLogger(__name__)


# Extended OrderType enum for advanced orders
class AdvancedOrderType(Enum):
    """Extended order types including advanced order types."""
    # Basic types (from base_broker)
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    
    # Advanced types
    TRAILING_STOP = "trailing_stop"
    OCO = "oco"
    BRACKET = "bracket"
    ICEBERG = "iceberg"


class AdvancedOrderEvent(Enum):
    """Events for advanced order types."""
    # Trailing stop events
    TRAILING_STOP_CREATED = "trailing_stop_created"
    TRAILING_STOP_UPDATED = "trailing_stop_updated"
    TRAILING_STOP_TRIGGERED = "trailing_stop_triggered"
    TRAILING_STOP_FILLED = "trailing_stop_filled"
    
    # OCO events
    OCO_GROUP_CREATED = "oco_group_created"
    OCO_GROUP_TRIGGERED = "oco_group_triggered"
    OCO_ORDER_CANCELLED = "oco_order_cancelled"
    
    # Bracket events
    BRACKET_CREATED = "bracket_created"
    BRACKET_ENTRY_FILLED = "bracket_entry_filled"
    BRACKET_EXIT_FILLED = "bracket_exit_filled"
    BRACKET_COMPLETED = "bracket_completed"
    
    # Iceberg events
    ICEBERG_CREATED = "iceberg_created"
    ICEBERG_PORTION_FILLED = "iceberg_portion_filled"
    ICEBERG_PORTION_DISCLOSED = "iceberg_portion_disclosed"
    ICEBERG_COMPLETED = "iceberg_completed"


@dataclass
class AdvancedOrderEventData:
    """Data structure for advanced order events."""
    event_type: AdvancedOrderEvent
    order_id: str
    symbol: str
    timestamp: datetime
    data: Dict[str, Any]
    metadata: Dict[str, Any] = None


class AdvancedOrderManager:
    """
    Manager that integrates all advanced order types with the broker system.
    """
    
    def __init__(self):
        # Individual managers
        self.trailing_stop_manager = TrailingStopManager()
        self.oco_manager = OCOManager()
        self.bracket_manager = BracketManager()
        self.iceberg_manager = IcebergManager()
        
        # Event system
        self.event_listeners: Dict[AdvancedOrderEvent, List[Callable]] = {}
        
        # Integration tracking
        self.order_mappings: Dict[str, Dict[str, str]] = {}  # Maps order_id to advanced order info
        self.logger = logging.getLogger(__name__)
    
    # Event system methods
    def register_event_listener(self, event_type: AdvancedOrderEvent, callback: Callable) -> None:
        """Register a callback for advanced order events."""
        if event_type not in self.event_listeners:
            self.event_listeners[event_type] = []
        self.event_listeners[event_type].append(callback)
    
    def _publish_event(self, event_data: AdvancedOrderEventData) -> None:
        """Publish an advanced order event."""
        event_type = event_data.event_type
        if event_type in self.event_listeners:
            for callback in self.event_listeners[event_type]:
                try:
                    callback(event_data.data)
                except Exception as e:
                    self.logger.error(f"Error in event callback for {event_type}: {e}")
    
    # Trailing stop methods
    def create_trailing_stop(
        self,
        symbol: str,
        side: str,
        quantity: float,
        initial_stop_price: float,
        trailing_type: str,
        trailing_amount: float
    ) -> str:
        """Create a trailing stop order."""
        order_id = f"TS_{symbol}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        from .trailing_stop import TrailingType
        trailing_type_enum = TrailingType(trailing_type)
        
        trailing_stop = TrailingStopOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            initial_stop_price=initial_stop_price,
            trailing_type=trailing_type_enum,
            trailing_amount=trailing_amount,
            current_stop_price=initial_stop_price,
            state=trailing_stop.state.ACTIVE if 'trailing_stop' in locals() else None
        )
        
        # Fix the state assignment
        from .trailing_stop import TrailingStopState
        trailing_stop.state = TrailingStopState.ACTIVE
        
        self.trailing_stop_manager.add_order(trailing_stop)
        
        # Track mapping
        self.order_mappings[order_id] = {
            'type': 'trailing_stop',
            'symbol': symbol,
            'side': side,
            'quantity': quantity
        }
        
        # Publish event
        self._publish_event(AdvancedOrderEventData(
            event_type=AdvancedOrderEvent.TRAILING_STOP_CREATED,
            order_id=order_id,
            symbol=symbol,
            timestamp=datetime.utcnow(),
            data={'trailing_stop': trailing_stop.get_status()}
        ))
        
        return order_id
    
    def update_trailing_stop(self, symbol: str, current_price: float) -> List[Dict[str, Any]]:
        """Update trailing stops for a symbol."""
        return self.trailing_stop_manager.update_all(symbol, current_price)
    
    def trigger_trailing_stops(self, symbol: str, current_price: float) -> List[str]:
        """Trigger any trailing stops that should trigger."""
        return self.trailing_stop_manager.trigger_orders(symbol, current_price)
    
    # OCO methods
    def create_oco_group(self, orders: List[OrderRequest]) -> str:
        """Create an OCO order group."""
        group_id = self.oco_manager.create_group(orders)
        
        # Track mapping for all orders in group
        for order in orders:
            self.order_mappings[order.order_id] = {
                'type': 'oco',
                'group_id': group_id,
                'symbol': order.symbol,
                'side': order.side.value
            }
        
        # Publish event
        self._publish_event(AdvancedOrderEventData(
            event_type=AdvancedOrderEvent.OCO_GROUP_CREATED,
            order_id=group_id,
            symbol=orders[0].symbol if orders else '',
            timestamp=datetime.utcnow(),
            data={'group_id': group_id, 'order_count': len(orders)}
        ))
        
        return group_id
    
    def trigger_oco_group(self, order_id: str) -> Optional[str]:
        """Trigger OCO group when an order fills."""
        return self.oco_manager.trigger_group(order_id)
    
    def get_oco_cancellations(self, filled_order_id: str) -> List[str]:
        """Get orders that should be cancelled when an OCO order fills."""
        return self.oco_manager.get_orders_to_cancel(filled_order_id)
    
    # Bracket methods
    def create_bracket(
        self,
        symbol: str,
        quantity: float,
        entry_price: Optional[float],
        profit_target_pct: Optional[float],
        stop_loss_pct: Optional[float],
        entry_side: str = "BUY"
    ) -> str:
        """Create a bracket order."""
        bracket_id = self.bracket_manager.create_bracket(
            symbol=symbol,
            quantity=quantity,
            entry_price=entry_price,
            profit_target_pct=profit_target_pct,
            stop_loss_pct=stop_loss_pct,
            entry_side=entry_side
        )
        
        # Track mapping
        self.order_mappings[bracket_id] = {
            'type': 'bracket',
            'symbol': symbol,
            'side': entry_side,
            'quantity': quantity
        }
        
        # Publish event
        self._publish_event(AdvancedOrderEventData(
            event_type=AdvancedOrderEvent.BRACKET_CREATED,
            order_id=bracket_id,
            symbol=symbol,
            timestamp=datetime.utcnow(),
            data={'bracket_id': bracket_id, 'quantity': quantity}
        ))
        
        return bracket_id
    
    def place_bracket_entry(self, bracket_id: str) -> Optional[OrderRequest]:
        """Place the entry order for a bracket."""
        return self.bracket_manager.place_entry_order(bracket_id)
    
    def on_bracket_entry_filled(self, order_id: str, fill_price: float, fill_quantity: float) -> List[OrderRequest]:
        """Handle bracket entry fill and create exit orders."""
        exit_orders = self.bracket_manager.on_entry_filled(order_id, fill_price, fill_quantity)
        
        # Track exit orders
        for exit_order in exit_orders:
            self.order_mappings[exit_order.order_id] = {
                'type': 'bracket_exit',
                'bracket_id': self.bracket_manager.get_bracket_by_order(order_id).bracket_id,
                'symbol': exit_order.symbol,
                'side': exit_order.side.value
            }
        
        # Publish event
        self._publish_event(AdvancedOrderEventData(
            event_type=AdvancedOrderEvent.BRACKET_ENTRY_FILLED,
            order_id=order_id,
            symbol=exit_orders[0].symbol if exit_orders else '',
            timestamp=datetime.utcnow(),
            data={'order_id': order_id, 'fill_price': fill_price, 'exit_orders_count': len(exit_orders)}
        ))
        
        return exit_orders
    
    def on_bracket_exit_filled(self, order_id: str, fill_price: float, fill_quantity: float) -> Optional[str]:
        """Handle bracket exit fill."""
        bracket_id = self.bracket_manager.on_exit_filled(order_id, fill_price, fill_quantity)
        
        if bracket_id:
            # Publish event
            self._publish_event(AdvancedOrderEventData(
                event_type=AdvancedOrderEvent.BRACKET_EXIT_FILLED,
                order_id=order_id,
                symbol='',
                timestamp=datetime.utcnow(),
                data={'bracket_id': bracket_id, 'order_id': order_id, 'fill_price': fill_price}
            ))
        
        return bracket_id
    
    # Iceberg methods
    def create_iceberg(
        self,
        symbol: str,
        side: str,
        total_quantity: float,
        displayed_quantity: float,
        disclosure_type: str = "time",
        disclosure_interval: int = 60
    ) -> str:
        """Create an iceberg order."""
        from .iceberg_orders import DisclosureType
        disclosure_type_enum = DisclosureType(disclosure_type)
        
        iceberg_id = self.iceberg_manager.create_iceberg(
            symbol=symbol,
            side=side,
            total_quantity=total_quantity,
            displayed_quantity=displayed_quantity,
            disclosure_type=disclosure_type_enum,
            disclosure_interval_seconds=disclosure_interval
        )
        
        # Track mapping
        self.order_mappings[iceberg_id] = {
            'type': 'iceberg',
            'symbol': symbol,
            'side': side,
            'quantity': total_quantity
        }
        
        # Publish event
        self._publish_event(AdvancedOrderEventData(
            event_type=AdvancedOrderEvent.ICEBERG_CREATED,
            order_id=iceberg_id,
            symbol=symbol,
            timestamp=datetime.utcnow(),
            data={'iceberg_id': iceberg_id, 'total_quantity': total_quantity}
        ))
        
        return iceberg_id
    
    def place_iceberg_first_child(self, iceberg_id: str) -> Optional[OrderRequest]:
        """Place the first child order for an iceberg."""
        return self.iceberg_manager.place_first_child_order(iceberg_id)
    
    def on_iceberg_child_fill(self, order_id: str, fill_price: float, fill_quantity: float) -> Optional[OrderRequest]:
        """Handle iceberg child order fill."""
        new_child_order = self.iceberg_manager.on_child_fill(order_id, fill_price, fill_quantity)
        
        # Publish event
        self._publish_event(AdvancedOrderEventData(
            event_type=AdvancedOrderEvent.ICEBERG_PORTION_FILLED,
            order_id=order_id,
            symbol='',
            timestamp=datetime.utcnow(),
            data={'order_id': order_id, 'fill_price': fill_price, 'fill_quantity': fill_quantity}
        ))
        
        # Track new child order if created
        if new_child_order:
            iceberg = self.iceberg_manager.get_iceberg_by_order(order_id)
            if iceberg:
                self.order_mappings[new_child_order.order_id] = {
                    'type': 'iceberg_child',
                    'iceberg_id': iceberg.iceberg_id,
                    'symbol': new_child_order.symbol,
                    'side': new_child_order.side.value
                }
        
        return new_child_order
    
    # Utility methods
    def get_order_info(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get information about an advanced order."""
        return self.order_mappings.get(order_id)
    
    def cancel_advanced_order(self, order_id: str) -> List[str]:
        """Cancel an advanced order and return child orders to cancel."""
        order_info = self.order_mappings.get(order_id)
        if not order_info:
            return []
        
        orders_to_cancel = []
        order_type = order_info['type']
        
        if order_type == 'trailing_stop':
            # Trailing stops don't have child orders to cancel
            pass
        elif order_type == 'oco':
            group_id = order_info['group_id']
            orders_to_cancel = self.oco_manager.get_orders_to_cancel(order_id)
        elif order_type == 'bracket':
            bracket_id = order_info.get('bracket_id', order_id)
            orders_to_cancel = self.bracket_manager.cancel_bracket(bracket_id)
        elif order_type == 'iceberg':
            iceberg_id = order_info.get('iceberg_id', order_id)
            orders_to_cancel = self.iceberg_manager.cancel_iceberg(iceberg_id)
        
        # Clean up mapping
        self.order_mappings.pop(order_id, None)
        
        return orders_to_cancel
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get comprehensive status of all advanced orders."""
        return {
            'trailing_stops': self.trailing_stop_manager.get_status_summary(),
            'oco_groups': self.oco_manager.get_status_summary(),
            'brackets': self.bracket_manager.get_status_summary(),
            'icebergs': self.iceberg_manager.get_status_summary(),
            'total_advanced_orders': len(self.order_mappings)
        }
    
    def cleanup_completed_orders(self) -> Dict[str, int]:
        """Clean up completed orders from all managers."""
        results = {
            'trailing_stops': self.trailing_stop_manager.cleanup_completed_orders() if hasattr(self.trailing_stop_manager, 'cleanup_completed_orders') else 0,
            'oco_groups': self.oco_manager.cleanup_completed_groups(),
            'brackets': self.bracket_manager.cleanup_completed_brackets(),
            'icebergs': self.iceberg_manager.cleanup_completed_icebergs()
        }
        
        # Clean up order mappings for completed orders
        completed_orders = [
            order_id for order_id, info in self.order_mappings.items()
            if self._is_order_completed(order_id, info)
        ]
        
        for order_id in completed_orders:
            self.order_mappings.pop(order_id, None)
        
        return results
    
    def _is_order_completed(self, order_id: str, order_info: Dict[str, Any]) -> bool:
        """Check if an order is completed."""
        order_type = order_info['type']
        
        if order_type == 'trailing_stop':
            order = self.trailing_stop_manager.get_order(order_id)
            return order and not order.is_active()
        elif order_type == 'oco':
            group = self.oco_manager.get_group_by_order(order_id)
            return group and group.is_complete()
        elif order_type == 'bracket':
            bracket = self.bracket_manager.get_bracket_by_order(order_id)
            return bracket and not bracket.is_active()
        elif order_type == 'iceberg':
            iceberg = self.iceberg_manager.get_iceberg_by_order(order_id)
            return iceberg and iceberg.is_complete()
        
        return False