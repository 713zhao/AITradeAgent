"""
Broker Manager - Unified broker interface and lifecycle management

Handles:
- Broker initialization (paper or live)
- Broker switching
- Order submission and tracking
- Position and account management
- Event publishing for order fills and state changes
"""

import logging
import uuid
from typing import Dict, Optional, List
from datetime import datetime
from enum import Enum

from .base_broker import (
    BaseBroker,
    OrderRequest,
    Order,
    OrderStatus,
    OrderSide,
    OrderType,
    Position,
    Account,
)
from .paper_broker import PaperBroker
from .alpaca_broker import AlpacaBroker

logger = logging.getLogger(__name__)


class BrokerMode(Enum):
    """Broker operating mode."""
    PAPER = "paper"       # Paper trading (simulated)
    LIVE = "live"         # Live trading (real money)
    BACKTEST = "backtest" # Backtest simulation


class BrokerManager:
    """
    Unified broker manager for live and paper trading.
    
    Responsibilities:
    - Initialize and manage broker instances
    - Switch between paper/live trading
    - Submit orders and track execution
    - Manage positions and accounts
    - Publish broker events
    """
    
    def __init__(
        self,
        mode: BrokerMode = BrokerMode.PAPER,
        initial_cash: float = 100000.0,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        alpaca_base_url: str = "https://paper-api.alpaca.markets",
        slippage_bps: float = 1.0,
        fill_delay_seconds: float = 0.1,
    ):
        """
        Initialize broker manager.
        
        Args:
            mode: Operating mode (PAPER, LIVE, BACKTEST)
            initial_cash: Initial cash for paper trading
            api_key: Alpaca API key for live/paper trading
            api_secret: Alpaca API secret for live/paper trading
            alpaca_base_url: Alpaca API base URL
            slippage_bps: Slippage in basis points (paper only)
            fill_delay_seconds: Fill delay in seconds (paper only)
        """
        self.mode = mode
        self.initial_cash = initial_cash
        self.api_key = api_key
        self.api_secret = api_secret
        self.alpaca_base_url = alpaca_base_url
        self.slippage_bps = slippage_bps
        self.fill_delay_seconds = fill_delay_seconds
        
        # Broker instances
        self.broker: Optional[BaseBroker] = None
        self.paper_broker: Optional[PaperBroker] = None
        self.alpaca_broker: Optional[AlpacaBroker] = None
        
        # Order tracking
        self.order_map: Dict[str, str] = {}  # trade_id -> order_id
        self.pending_orders: Dict[str, Order] = {}  # order_id -> Order
        self.filled_orders: Dict[str, Order] = {}  # order_id -> Order
        
        # Event callback registry
        self.event_listeners: Dict[str, List] = {
            "ORDER_SUBMITTED": [],
            "ORDER_ACCEPTED": [],
            "ORDER_FILLED": [],
            "ORDER_PARTIAL": [],
            "ORDER_CANCELLED": [],
            "ORDER_REJECTED": [],
            "POSITION_OPENED": [],
            "POSITION_CLOSED": [],
            "POSITION_UPDATED": [],
            "ACCOUNT_UPDATED": [],
        }
        
        # Initialize broker based on mode
        self._initialize_broker()
        
        logger.info(f"BrokerManager initialized in {mode.value} mode")
    
    def _initialize_broker(self):
        """Initialize broker based on mode."""
        if self.mode == BrokerMode.PAPER or self.mode == BrokerMode.BACKTEST:
            self.paper_broker = PaperBroker(
                initial_cash=self.initial_cash,
                slippage_bps=self.slippage_bps,
                fill_delay_seconds=self.fill_delay_seconds,
                simulate_partial_fills=False,
            )
            self.broker = self.paper_broker
            logger.info(f"Paper broker initialized with ${self.initial_cash:,.2f}")
        
        elif self.mode == BrokerMode.LIVE:
            if not self.api_key or not self.api_secret:
                raise ValueError("API key and secret required for live trading")
            
            self.alpaca_broker = AlpacaBroker(
                api_key=self.api_key,
                api_secret=self.api_secret,
                base_url=self.alpaca_base_url,
            )
            self.broker = self.alpaca_broker
            logger.info("Alpaca broker initialized")
        
        else:
            raise ValueError(f"Unknown broker mode: {self.mode}")
    
    def switch_mode(self, mode: BrokerMode):
        """
        Switch broker mode (paper ↔ live).
        
        Args:
            mode: New operating mode
            
        Raises:
            ValueError: If cannot switch (e.g., pending orders)
        """
        if self.mode == mode:
            logger.warning(f"Already in {mode.value} mode")
            return
        
        # Check for pending orders
        if self.pending_orders:
            raise ValueError(
                f"Cannot switch modes with {len(self.pending_orders)} pending orders"
            )
        
        self.mode = mode
        self._initialize_broker()
        logger.info(f"Switched to {mode.value} mode")
    
    def register_event_listener(self, event_type: str, callback):
        """
        Register event listener.
        
        Args:
            event_type: Event type to listen for
            callback: Function to call when event fires
        """
        if event_type not in self.event_listeners:
            logger.warning(f"Unknown event type: {event_type}")
            return
        
        self.event_listeners[event_type].append(callback)
        logger.debug(f"Registered listener for {event_type}")
    
    def unregister_event_listener(self, event_type: str, callback):
        """Unregister event listener."""
        if event_type in self.event_listeners:
            self.event_listeners[event_type] = [
                cb for cb in self.event_listeners[event_type] if cb != callback
            ]
    
    def _publish_event(self, event_type: str, data: Dict):
        """Publish event to all listeners."""
        if event_type not in self.event_listeners:
            logger.warning(f"Unknown event type: {event_type}")
            return
        
        for callback in self.event_listeners[event_type]:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Error in {event_type} listener: {e}")
    
    def place_order(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        order_type: str = "MARKET",
    ) -> Order:
        """
        Place an order.
        
        Args:
            trade_id: Associated trade ID (for tracking)
            symbol: Stock symbol
            side: BUY or SELL
            quantity: Number of shares
            price: Limit price (if limit order)
            order_type: MARKET, LIMIT, STOP, STOP_LIMIT
            
        Returns:
            Order object with order_id
            
        Raises:
            ValueError: If validation fails
        """
        if not self.broker:
            raise RuntimeError("Broker not initialized")
        
        # Generate order ID
        order_id = f"ORD_{uuid.uuid4().hex[:8]}_{datetime.utcnow().timestamp()}"
        
        # Convert side string to enum
        try:
            order_side = OrderSide[side.upper()]
        except KeyError:
            raise ValueError(f"Invalid order side: {side}")
        
        # Convert order type string to enum
        try:
            ot = OrderType[order_type.upper()]
        except KeyError:
            raise ValueError(f"Invalid order type: {order_type}")
        
        # Create order request
        request = OrderRequest(
            order_id=order_id,
            symbol=symbol.upper(),
            side=order_side,
            quantity=quantity,
            order_type=ot,
            price=price,
            time_in_force="day",
            metadata={"trade_id": trade_id},
        )
        
        # Validate
        if quantity <= 0:
            raise ValueError(f"Invalid quantity: {quantity}")
        
        if ot == OrderType.LIMIT or ot == OrderType.STOP_LIMIT:
            if not price or price <= 0:
                raise ValueError(f"Price required for {ot.name} order")
        
        # Place order with broker
        try:
            order = self.broker.place_order(request)
            
            # Track order
            self.order_map[trade_id] = order_id
            self.pending_orders[order_id] = order
            
            # Publish event
            self._publish_event("ORDER_SUBMITTED", {
                "order_id": order_id,
                "trade_id": trade_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "timestamp": datetime.utcnow().isoformat(),
            })
            
            logger.info(f"Order placed: {order_id} for {symbol} ({side} {quantity})")
            
            return order
        
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            raise
    
    def cancel_order(self, order_id: str) -> Optional[Order]:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            Cancelled order, or None if not found
        """
        if not self.broker:
            raise RuntimeError("Broker not initialized")
        
        try:
            order = self.broker.cancel_order(order_id)
            if order and order_id in self.pending_orders:
                del self.pending_orders[order_id]
            
            # Publish event
            self._publish_event("ORDER_CANCELLED", {
                "order_id": order_id,
                "timestamp": datetime.utcnow().isoformat(),
            })
            
            logger.info(f"Order cancelled: {order_id}")
            return order
        
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            raise
    
    def process_fills(self):
        """
        Process pending fills (paper broker only).
        
        This should be called periodically to simulate order fills.
        """
        if not isinstance(self.broker, PaperBroker):
            logger.debug("Skipping fill processing (not paper broker)")
            return
        
        # Process fills
        self.broker.process_fills()
        
        # Check for newly filled orders
        for order_id, order in list(self.pending_orders.items()):
            # Get updated order status
            updated_order = self.broker.get_order(order_id)
            if not updated_order:
                continue
            
            # Check if filled
            if updated_order.status == OrderStatus.FILLED:
                self.pending_orders[order_id] = updated_order
                self.filled_orders[order_id] = updated_order
                del self.pending_orders[order_id]
                
                # Get trade_id from order metadata or map
                trade_id = None
                for tid, oid in self.order_map.items():
                    if oid == order_id:
                        trade_id = tid
                        break
                
                # Publish fill event
                self._publish_event("ORDER_FILLED", {
                    "order_id": order_id,
                    "trade_id": trade_id,
                    "symbol": updated_order.symbol,
                    "side": updated_order.side.value,
                    "quantity": updated_order.filled_quantity,
                    "fill_price": updated_order.avg_fill_price,
                    "timestamp": updated_order.filled_at.isoformat() if updated_order.filled_at else None,
                })
                
                logger.info(
                    f"Order filled: {order_id} - {updated_order.symbol} "
                    f"{updated_order.filled_quantity} @ ${updated_order.avg_fill_price}"
                )
            
            elif updated_order.status == OrderStatus.PARTIAL:
                self.pending_orders[order_id] = updated_order
                
                # Publish partial event
                self._publish_event("ORDER_PARTIAL", {
                    "order_id": order_id,
                    "symbol": updated_order.symbol,
                    "filled_quantity": updated_order.filled_quantity,
                    "remaining": updated_order.quantity - updated_order.filled_quantity,
                    "timestamp": datetime.utcnow().isoformat(),
                })
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID."""
        if not self.broker:
            return None
        return self.broker.get_order(order_id)
    
    def get_orders(self, status: Optional[str] = None) -> List[Order]:
        """Get orders filtered by status."""
        if not self.broker:
            return []
        
        if status:
            try:
                status_enum = OrderStatus[status.upper()]
                return self.broker.get_orders(status_enum)
            except KeyError:
                logger.warning(f"Invalid status: {status}")
                return []
        
        return self.broker.get_orders()
    
    def get_positions(self) -> Dict[str, Position]:
        """Get all positions."""
        if not self.broker:
            return {}
        return self.broker.get_positions()
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position by symbol."""
        if not self.broker:
            return None
        return self.broker.get_position(symbol)
    
    def close_position(self, symbol: str) -> Optional[Order]:
        """
        Close position at market.
        
        Args:
            symbol: Symbol to close
            
        Returns:
            Closeout order
        """
        if not self.broker:
            return None
        
        try:
            order = self.broker.close_position(symbol)
            if order:
                self.pending_orders[order.order_id] = order
                
                self._publish_event("POSITION_CLOSED", {
                    "symbol": symbol,
                    "order_id": order.order_id,
                    "timestamp": datetime.utcnow().isoformat(),
                })
            
            return order
        
        except Exception as e:
            logger.error(f"Failed to close position {symbol}: {e}")
            raise
    
    def get_account(self) -> Optional[Account]:
        """Get account information."""
        if not self.broker:
            return None
        
        account = self.broker.get_account()
        
        if account:
            self._publish_event("ACCOUNT_UPDATED", {
                "cash": account.cash,
                "buying_power": account.buying_power,
                "total_equity": account.total_equity,
                "net_value": account.net_value,
                "timestamp": datetime.utcnow().isoformat(),
            })
        
        return account
    
    def get_cash(self) -> float:
        """Get available cash."""
        if not self.broker:
            return 0.0
        return self.broker.get_cash()
    
    def get_buying_power(self) -> float:
        """Get available buying power."""
        if not self.broker:
            return 0.0
        return self.broker.get_buying_power()
    
    def get_account_value(self) -> float:
        """Get total account value."""
        if not self.broker:
            return 0.0
        return self.broker.get_account_value()
    
    def get_stats(self) -> Dict:
        """Get broker statistics."""
        return {
            "mode": self.mode.value,
            "broker_type": type(self.broker).__name__ if self.broker else None,
            "pending_orders": len(self.pending_orders),
            "filled_orders": len(self.filled_orders),
            "total_orders": len(self.pending_orders) + len(self.filled_orders),
            "positions": len(self.get_positions()),
            "cash": self.get_cash(),
            "account_value": self.get_account_value(),
        }
    
    def reset(self):
        """Reset broker state (paper broker only)."""
        if isinstance(self.broker, PaperBroker):
            self.broker.reset()
            self.order_map.clear()
            self.pending_orders.clear()
            self.filled_orders.clear()
            logger.info("Broker reset to initial state")
