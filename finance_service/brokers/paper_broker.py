"""
Paper Trading Broker - Simulated broker for testing and demonstration.

This broker simulates real broker behavior including:
- Order placement and fills
- Slippage simulation
- Position tracking
- Account cash management
- Order status transitions
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from collections import defaultdict

from .base_broker import (
    BaseBroker, OrderRequest, Order, OrderStatus, OrderSide, OrderType,
    Position, Account, OrderType
)

logger = logging.getLogger(__name__)


@dataclass
class PaperConfig:
    """Configuration for Paper broker."""
    initial_cash: float = 100000.0
    slippage_bps: float = 1.0
    fill_delay_seconds: float = 1.0
    simulate_partial_fills: bool = False


class PaperBroker(BaseBroker):
    """
    Paper trading broker that simulates real broker behavior.
    
    Features:
    - Simulated order fills with configurable delay
    - Slippage simulation for market orders
    - Position tracking
    - Account cash management
    - Order status transitions
    - Partial fills simulation
    """
    
    def __init__(
        self,
        initial_cash: float = 100000.0,
        slippage_bps: float = 1.0,  # 1 basis point
        fill_delay_seconds: float = 1.0,
        simulate_partial_fills: bool = False,
    ):
        """
        Initialize paper broker.
        
        Args:
            initial_cash: Starting cash amount
            slippage_bps: Slippage in basis points (0.01 = 1 bps = 0.01%)
            fill_delay_seconds: Simulated delay before order fills (seconds)
            simulate_partial_fills: Whether to simulate partial fills
        """
        super().__init__("Paper", paper_trading=True)
        
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.slippage_bps = slippage_bps / 10000.0  # Convert to decimal
        self.fill_delay_seconds = fill_delay_seconds
        self.simulate_partial_fills = simulate_partial_fills
        
        # Storage
        self.orders: Dict[str, Order] = {}
        self.positions: Dict[str, Position] = {}
        self.quotes: Dict[str, Dict[str, float]] = {}
        self.order_queue: Dict[str, datetime] = {}  # Orders waiting to fill
        
        # Track trades for statistics
        self.filled_trades: List[Dict] = []
        
        logger.info(f"PaperBroker initialized: cash=${initial_cash:,.2f}")
    
    # =====================
    # ACCOUNT OPERATIONS
    # =====================
    
    def get_account(self) -> Account:
        """Get account information"""
        total_equity = self.cash + sum(p.market_value for p in self.positions.values())
        
        return Account(
            account_number="PAPER_001",
            cash=self.cash,
            buying_power=self.cash * 4,  # 4x margin
            total_equity=total_equity,
            initial_equity=self.initial_cash,
            net_value=total_equity,
            multiplier=4.0,
            is_margin=True,
            can_daytrade=True,
            last_updated=datetime.now(),
        )
    
    def get_cash(self) -> float:
        """Get available cash"""
        return self.cash
    
    def get_buying_power(self) -> float:
        """Get available buying power"""
        return self.cash * 4  # 4x leverage
    
    def get_account_value(self) -> float:
        """Get total account value"""
        return self.cash + sum(p.market_value for p in self.positions.values())
    
    # =====================
    # POSITION OPERATIONS
    # =====================
    
    def get_positions(self) -> Dict[str, Position]:
        """Get all open positions"""
        return self.positions.copy()
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for symbol"""
        return self.positions.get(symbol)
    
    def close_position(self, symbol: str) -> Order:
        """Close position at market"""
        if symbol not in self.positions:
            raise ValueError(f"No position in {symbol}")
        
        position = self.positions[symbol]
        side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
        quantity = abs(position.quantity)
        
        order_req = OrderRequest(
            order_id=str(uuid.uuid4()),
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=OrderType.MARKET,
        )
        
        return self.place_order(order_req)
    
    # =====================
    # ORDER OPERATIONS
    # =====================
    
    def place_order(self, order_request: OrderRequest) -> Order:
        """Place an order"""
        # Get current quote
        quote = self.quotes.get(order_request.symbol, {"last": 100.0, "bid": 99.5, "ask": 100.5})
        
        # Calculate fill price with slippage
        if order_request.order_type == OrderType.MARKET:
            if order_request.side == OrderSide.BUY:
                # Buy at ask + slippage
                fill_price = quote["ask"] * (1 + self.slippage_bps)
            else:
                # Sell at bid - slippage
                fill_price = quote["bid"] * (1 - self.slippage_bps)
        else:
            # Limit order uses specified price
            fill_price = order_request.price or quote["last"]
        
        # Create order object
        order = Order(
            order_id=order_request.order_id,
            symbol=order_request.symbol,
            side=order_request.side,
            quantity=order_request.quantity,
            filled_quantity=0.0,
            avg_fill_price=0.0,
            status=OrderStatus.SUBMITTED,
            order_type=order_request.order_type,
            submitted_at=datetime.now(),
        )
        
        self.orders[order.order_id] = order
        self.order_queue[order.order_id] = datetime.now() + timedelta(seconds=self.fill_delay_seconds)
        
        logger.info(f"Order placed: {order.order_id} {order.side.value} {order.quantity} {order.symbol} @ ${fill_price:.2f}")
        
        return order
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID"""
        return self.orders.get(order_id)
    
    def get_orders(self, status: Optional[OrderStatus] = None) -> List[Order]:
        """Get orders, optionally filtered by status"""
        orders = list(self.orders.values())
        if status:
            orders = [o for o in orders if o.status == status]
        return orders
    
    def cancel_order(self, order_id: str) -> Order:
        """Cancel an order"""
        order = self.orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        
        if order.is_closed():
            raise ValueError(f"Cannot cancel closed order: {order_id}")
        
        order.status = OrderStatus.CANCELLED
        order.cancelled_at = datetime.now()
        
        # Remove from queue
        if order_id in self.order_queue:
            del self.order_queue[order_id]
        
        logger.info(f"Order cancelled: {order_id}")
        return order
    
    def process_fills(self):
        """
        Process pending orders and fill them.
        
        This should be called periodically to simulate order fills.
        """
        now = datetime.now()
        orders_to_fill = []
        
        for order_id, ready_time in list(self.order_queue.items()):
            if now >= ready_time:
                orders_to_fill.append(order_id)
        
        for order_id in orders_to_fill:
            order = self.orders[order_id]
            quote = self.quotes.get(order.symbol, {"last": 100.0, "bid": 99.5, "ask": 100.5})
            
            # Calculate fill price
            if order.order_type == OrderType.MARKET:
                if order.side == OrderSide.BUY:
                    fill_price = quote["ask"] * (1 + self.slippage_bps)
                else:
                    fill_price = quote["bid"] * (1 - self.slippage_bps)
            else:
                fill_price = order.order_type == OrderType.LIMIT and order.price or quote["last"]
            
            # Fill order
            order.filled_quantity = order.quantity
            order.avg_fill_price = fill_price
            order.status = OrderStatus.FILLED
            order.filled_at = now
            
            # Update cash and positions
            if order.side == OrderSide.BUY:
                cost = order.quantity * fill_price
                self.cash -= cost
                self._add_position(order.symbol, order.quantity, fill_price)
            else:
                proceeds = order.quantity * fill_price
                self.cash += proceeds
                self._remove_position(order.symbol, order.quantity)
            
            # Record fill
            self.filled_trades.append({
                "order_id": order.order_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "price": fill_price,
                "timestamp": now,
            })
            
            del self.order_queue[order_id]
            logger.info(f"Order filled: {order_id} {order.quantity}@${fill_price:.2f}")
    
    def set_quote(self, symbol: str, bid: float, ask: float, last: float = None):
        """Manually set quote for a symbol (for testing)"""
        if last is None:
            last = (bid + ask) / 2
        
        self.quotes[symbol] = {
            "bid": bid,
            "ask": ask,
            "last": last,
            "bid_size": 1000,
            "ask_size": 1000,
            "volume": 1000000,
        }
    
    def get_last_quote(self, symbol: str) -> Dict[str, float]:
        """Get last quote"""
        return self.quotes.get(symbol, {
            "bid": 100.0,
            "ask": 100.1,
            "last": 100.0,
            "bid_size": 1000,
            "ask_size": 1000,
            "volume": 1000000,
        })
    
    # =====================
    # INTERNAL METHODS
    # =====================
    
    def _add_position(self, symbol: str, quantity: float, price: float):
        """Add quantity to position"""
        if symbol in self.positions:
            pos = self.positions[symbol]
            # Weighted average cost
            total_qty = pos.quantity + quantity
            pos.entry_price = (pos.quantity * pos.entry_price + quantity * price) / total_qty
            pos.quantity = total_qty
        else:
            quote = self.quotes.get(symbol, {"last": price})
            self.positions[symbol] = Position(
                symbol=symbol,
                quantity=quantity,
                entry_price=price,
                current_price=quote["last"],
                market_value=quantity * quote["last"],
                unrealized_pnl=0.0,
                unrealized_pnl_pct=0.0,
                side="long",
            )
    
    def _remove_position(self, symbol: str, quantity: float):
        """Remove quantity from position"""
        if symbol not in self.positions:
            raise ValueError(f"No position in {symbol}")
        
        pos = self.positions[symbol]
        pos.quantity -= quantity
        
        if pos.quantity <= 0:
            del self.positions[symbol]
        else:
            quote = self.quotes.get(symbol, {"last": pos.current_price})
            pos.current_price = quote["last"]
            pos.market_value = pos.quantity * pos.current_price
            pos.unrealized_pnl = (pos.current_price - pos.entry_price) * pos.quantity
            pos.unrealized_pnl_pct = (pos.current_price - pos.entry_price) / pos.entry_price * 100
    
    def get_filled_trades(self) -> List[Dict]:
        """Get all filled trades"""
        return self.filled_trades.copy()
    
    def reset(self):
        """Reset broker to initial state"""
        self.cash = self.initial_cash
        self.orders.clear()
        self.positions.clear()
        self.order_queue.clear()
        self.filled_trades.clear()
        logger.info("PaperBroker reset to initial state")
