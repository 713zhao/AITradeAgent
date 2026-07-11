"""Abstract broker interface.

All broker implementations must adhere to this interface.
Enables switching between paper trading, Alpaca, Tiger Brokers, etc.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from finance_service.core.models import Position, Trade


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        return super().__eq__(other)

    def __hash__(self):
        return hash(self.value)


@dataclass
class OrderRequest:
    """Request to place an order"""
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType
    price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "DAY"

    def __post_init__(self):
        if self.quantity <= 0:
            raise ValueError(f"Order quantity must be positive, got {self.quantity}")
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("Limit orders require a price")


@dataclass
class OrderResult:
    """Result of order submission"""
    order_id: str
    symbol: str
    action: str  # BUY, SELL
    quantity: float
    filled_quantity: float
    filled_price: float
    status: str  # "filled", "partial", "rejected", "cancelled"
    timestamp: datetime
    error_message: Optional[str] = None
    order_type: Optional["OrderType"] = None
    side: Optional["OrderSide"] = None

    @property
    def avg_fill_price(self) -> float:
        """Alias for filled_price."""
        return self.filled_price

    def __eq__(self, other):
        if isinstance(other, str):
            return self.status == other
        return super().__eq__(other)


class BrokerInterface(ABC):
    """Abstract base class for broker implementations."""

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to broker (API login, websocket, etc.)"""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection gracefully"""
        pass

    @abstractmethod
    async def submit_order(self, order: Dict[str, Any]) -> OrderResult:
        """
        Submit a trade order.

        Args:
            order: Dict with keys:
                - symbol: str
                - action: "BUY" or "SELL"
                - quantity: float (number of shares or contracts)
                - price: Optional[float] (market order if None)
                - order_type: "market" or "limit"
                - stop_loss: Optional[float]
                - take_profit: Optional[float]

        Returns:
            OrderResult with fill details
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order"""
        pass

    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """Get current open positions"""
        pass

    @abstractmethod
    async def get_account(self) -> Dict[str, Any]:
        """Get account information (cash, equity, buying power)"""
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """Check status of a specific order"""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if broker connection is active"""
        pass


class _PositionCompat:
    """Wrapper exposing test-compatible attributes on a Position."""
    __slots__ = ('_pos',)

    def __init__(self, pos: "Position"):
        self._pos = pos

    @property
    def quantity(self) -> float:
        return self._pos.qty

    @property
    def entry_price(self) -> float:
        return self._pos.avg_cost

    @property
    def current_price(self) -> float:
        return self._pos.current_price

    @property
    def side(self) -> str:
        return "long" if self._pos.qty >= 0 else "short"

    @property
    def symbol(self) -> str:
        return self._pos.symbol

    def __repr__(self):
        return f"<Position {self._pos.symbol} qty={self._pos.qty} avg_cost={self._pos.avg_cost}>"


class PaperBroker(BrokerInterface):
    """Paper trading broker - simulates orders locally.

    Maintains an in-memory portfolio and executes orders at midpoint prices.
    Used when `finance.execution.broker: "paper"`.
    """

    def __init__(self, initial_cash: float = 100000.0, slippage_bps: float = 0.0, fill_delay_seconds: float = 0.0):
        self._connected = True  # Paper broker is always "connected"
        self._initial_cash = initial_cash
        self._cash = initial_cash
        self._slippage_bps = slippage_bps
        self._positions: Dict[str, Position] = {}  # symbol -> Position
        self._orders: Dict[str, OrderResult] = {}
        self._order_counter = 0
        self._quotes: Dict[str, Dict[str, float]] = {}  # symbol -> {bid, ask, last}
        self._filled_trades: List[OrderResult] = []

    # --- Backward-compatible properties ---
    @property
    def broker_name(self) -> str:
        return "Paper"

    @property
    def paper_trading(self) -> bool:
        return True

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def initial_cash(self) -> float:
        return self._initial_cash

    @property
    def slippage_bps(self) -> float:
        return self._slippage_bps

    @property
    def filled_trades(self) -> List[OrderResult]:
        return self._filled_trades

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def submit_order(self, order: Dict[str, Any]) -> OrderResult:
        if not self._connected:
            return OrderResult(
                order_id="",
                symbol=order['symbol'],
                action=order['action'],
                quantity=order['quantity'],
                filled_quantity=0,
                filled_price=0,
                status="rejected",
                timestamp=datetime.now(),
                error_message="Broker not connected"
            )

        symbol = order['symbol']
        action = order['action'].upper()
        quantity = order['quantity']
        order_type = order.get('order_type', 'market')
        limit_price = order.get('price')

        # Limit orders fill at the specified price; market orders use last known position price
        if order_type == 'limit' and limit_price is not None:
            fill_price = limit_price
        else:
            pos = self._positions.get(symbol)
            fill_price = pos.current_price if pos else None
        if not fill_price:
            return OrderResult(
                order_id="",
                symbol=symbol,
                action=action,
                quantity=quantity,
                filled_quantity=0,
                filled_price=0,
                status="rejected",
                timestamp=datetime.now(),
                error_message="PaperBroker requires explicit price in order"
            )

        self._order_counter += 1
        order_id = f"PAPER-{self._order_counter:08d}"

        # Calculate trade value and commission
        trade_value = fill_price * quantity
        commission = 0.0005 * trade_value  # 5 bps

        if action == 'BUY':
            if self._cash < trade_value + commission:
                return OrderResult(
                    order_id=order_id,
                    symbol=symbol,
                    action=action,
                    quantity=quantity,
                    filled_quantity=0,
                    filled_price=0,
                    status="rejected",
                    timestamp=datetime.now(),
                    error_message="Insufficient cash"
                )
            self._cash -= (trade_value + commission)
            # Update or create position
            if symbol in self._positions:
                pos = self._positions[symbol]
                total_cost = pos.avg_cost * pos.qty + trade_value
                pos.qty += quantity
                pos.avg_cost = total_cost / pos.qty
                pos.current_price = fill_price  # update to latest
            else:
                self._positions[symbol] = Position(
                    symbol=symbol,
                    qty=quantity,
                    avg_cost=fill_price,
                    current_price=fill_price,
                )
        elif action == 'SELL':
            if symbol not in self._positions or self._positions[symbol].qty < quantity:
                return OrderResult(
                    order_id=order_id,
                    symbol=symbol,
                    action=action,
                    quantity=quantity,
                    filled_quantity=0,
                    filled_price=0,
                    status="rejected",
                    timestamp=datetime.now(),
                    error_message="Insufficient shares"
                )
            pos = self._positions[symbol]
            pos.qty -= quantity
            self._cash += (trade_value - commission)
            if pos.qty == 0:
                del self._positions[symbol]
            else:
                pos.current_price = fill_price
        else:
            return OrderResult(order_id=order_id, status="rejected", error_message="Unknown action", symbol=symbol, action=action, quantity=quantity, filled_quantity=0, filled_price=0, timestamp=datetime.now())

        result = OrderResult(
            order_id=order_id,
            symbol=symbol,
            action=action,
            quantity=quantity,
            filled_quantity=quantity,
            filled_price=fill_price,
            status="filled",
            timestamp=datetime.now(),
        )
        self._orders[order_id] = result
        return result

    async def cancel_order(self, order_id: str) -> bool:
        if order_id in self._orders:
            order = self._orders[order_id]
            if order.status in ('pending', 'partial'):
                order.status = 'cancelled'
                return True
        return False

    async def get_positions(self) -> List[Position]:
        return list(self._positions.values())

    async def get_account(self) -> Dict[str, Any]:
        return {
            'cash': self._cash,
            'equity': self._cash + sum(p.qty * p.current_price for p in self._positions.values()),
            'buying_power': self._cash,
            'portfolio_value': self._cash + sum(p.qty * p.current_price for p in self._positions.values()),
        }

    async def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        return self._orders.get(order_id)

    def is_connected(self) -> bool:
        return self._connected

    # Helper for tests: set current price for positions
    def set_current_price(self, symbol: str, price: float):
        if symbol in self._positions:
            self._positions[symbol].current_price = price

    # --- Backward-compatible sync methods for tests ---

    def set_quote(self, symbol: str, bid: float = 0.0, ask: float = 0.0, last: float = 0.0):
        """Set current market quote for a symbol (used in test scenarios)."""
        mid = (bid + ask) / 2 if bid and ask else last
        self._quotes[symbol] = {"bid": bid, "ask": ask, "last": last, "mid": mid}
        self.set_current_price(symbol, mid or last)

    def place_order(self, order_request: "OrderRequest") -> OrderResult:
        """Sync order placement. Returns SUBMITTED immediately; call process_fills() to execute."""
        if not self._connected:
            result = OrderResult(
                order_id=order_request.order_id,
                symbol=order_request.symbol,
                action=order_request.side.value.upper(),
                quantity=order_request.quantity,
                filled_quantity=0,
                filled_price=0.0,
                status=OrderStatus.REJECTED.value,
                timestamp=datetime.now(),
                error_message="Broker not connected",
            )
            result.side = order_request.side
            result._order_request = order_request
            self._orders[order_request.order_id] = result
            return result

        self._order_counter += 1
        result = OrderResult(
            order_id=order_request.order_id,
            symbol=order_request.symbol,
            action=order_request.side.value.upper(),
            quantity=order_request.quantity,
            filled_quantity=0,
            filled_price=0.0,
            status=OrderStatus.SUBMITTED.value,
            timestamp=datetime.now(),
            order_type=order_request.order_type,
            side=order_request.side,
        )
        result._order_request = order_request  # keep for process_fills
        self._orders[order_request.order_id] = result
        return result

    def _fill_order(self, order: OrderResult, fill_price: float) -> None:
        """Internal: fill an order at the given price (updates cash/positions/status)."""
        action = order.action
        symbol = order.symbol
        quantity = order.quantity
        trade_value = fill_price * quantity
        commission = 0.0005 * trade_value

        if action == "BUY":
            if self._cash < trade_value + commission:
                order.status = OrderStatus.REJECTED.value
                order.error_message = "Insufficient cash"
                return
            self._cash -= (trade_value + commission)
            if symbol in self._positions:
                pos = self._positions[symbol]
                total_cost = pos.avg_cost * pos.qty + trade_value
                pos.qty += quantity
                pos.avg_cost = total_cost / pos.qty
                pos.current_price = fill_price
            else:
                self._positions[symbol] = Position(
                    symbol=symbol,
                    qty=quantity,
                    avg_cost=fill_price,
                    current_price=fill_price,
                )
        elif action == "SELL":
            if symbol not in self._positions or self._positions[symbol].qty < quantity:
                order.status = OrderStatus.REJECTED.value
                order.error_message = "Insufficient shares"
                return
            pos = self._positions[symbol]
            pos.qty -= quantity
            self._cash += (trade_value - commission)
            if pos.qty == 0:
                del self._positions[symbol]
            else:
                pos.current_price = fill_price

        order.filled_quantity = quantity
        order.filled_price = fill_price
        order.status = OrderStatus.FILLED.value
        self._filled_trades.append(order)

    def get_order(self, order_id: str) -> Optional[OrderResult]:
        """Return a placed order by id."""
        return self._orders.get(order_id)

    def get_orders(self, status=None) -> List[OrderResult]:
        """Return all orders, optionally filtered by status."""
        orders = list(self._orders.values())
        if status is not None:
            status_val = status.value if hasattr(status, 'value') else status
            orders = [o for o in orders if o.status == status_val]
        return orders

    def get_account(self):
        """Return account info as simple namespace."""
        from types import SimpleNamespace
        equity = self._cash + sum(p.qty * p.current_price for p in self._positions.values())
        return SimpleNamespace(
            account_number="PAPER_001",
            cash=self._cash,
            buying_power=self._cash * 4,  # 4x margin for paper
            equity=equity,
            total_equity=equity,
            portfolio_value=equity,
            is_margin=True,
            can_daytrade=True,
        )

    def get_buying_power(self) -> float:
        return self._cash * 4  # 4x margin for paper trading

    def get_account_value(self) -> float:
        return self._cash + sum(p.qty * p.current_price for p in self._positions.values())

    def close_position(self, symbol: str) -> Optional[OrderResult]:
        """Place a market SELL order to close the full position."""
        pos = self._positions.get(symbol)
        if pos is None:
            return None
        req = OrderRequest(
            order_id=f"CLOSE_{symbol}_{self._order_counter + 1}",
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=pos.qty,
            order_type=OrderType.MARKET,
        )
        return self.place_order(req)

    def get_filled_trades(self, symbol: str = None) -> List[dict]:
        """Return filled trades as dicts, optionally filtered by symbol."""
        trades = []
        for t in self._filled_trades:
            if symbol and t.symbol != symbol:
                continue
            trades.append({
                "symbol": t.symbol,
                "action": t.action,
                "quantity": t.filled_quantity or t.quantity,
                "price": t.filled_price,
                "status": t.status,
                "order_id": t.order_id,
                "timestamp": t.timestamp,
            })
        return trades

    def sync_positions_from_repository(
        self,
        repo_positions: Dict[str, Any],
        current_cash: Optional[float] = None,
    ) -> None:
        """Populate broker's internal state from the portfolio repository.

        Called once at startup so SELL orders aren't rejected as 'Insufficient shares'
        for positions that were opened in a previous session, and so BUY order cash
        checks reflect actual remaining cash rather than the full initial_cash.

        Args:
            repo_positions: Dict[symbol, portfolio.models.Position] from TradeRepository.
            current_cash: If provided, override broker's cash to match the portfolio's
                          computed remaining cash.
        """
        from finance_service.core.models import Position as CorePosition
        synced = 0
        for symbol, repo_pos in repo_positions.items():
            qty = getattr(repo_pos, 'quantity', None) or getattr(repo_pos, 'qty', 0.0)
            avg_cost = getattr(repo_pos, 'avg_cost', 0.0)
            current_price = getattr(repo_pos, 'current_price', avg_cost) or avg_cost
            if qty > 0:
                self._positions[symbol] = CorePosition(
                    symbol=symbol,
                    qty=qty,
                    avg_cost=avg_cost,
                    current_price=current_price,
                )
                synced += 1
        if current_cash is not None:
            self._cash = current_cash
        import logging
        logging.getLogger(__name__).info(
            f"PaperBroker: synced {synced} position(s) from repository"
            + (f", cash set to ${current_cash:,.2f}" if current_cash is not None else "")
        )

    def reset_broker(self):
        """Reset to initial state."""
        self._cash = self._initial_cash
        self._positions.clear()
        self._orders.clear()
        self._filled_trades.clear()
        self._order_counter = 0
        self._quotes.clear()

    def reset(self):
        """Alias for reset_broker()."""
        self.reset_broker()

    @property
    def orders(self) -> Dict[str, Any]:
        """Expose orders dict (for test assertions)."""
        return self._orders

    def get_positions_sync(self) -> List[Position]:
        """Sync version of get_positions."""
        return list(self._positions.values())

    def get_positions(self) -> Dict[str, Position]:  # type: ignore[override]
        """Sync override: return positions as dict keyed by symbol."""
        return dict(self._positions)

    def get_position(self, symbol: str) -> Optional[Any]:
        """Return a single position by symbol, with test-compatible attributes."""
        pos = self._positions.get(symbol)
        if pos is None:
            return None
        # Return a compat wrapper exposing 'quantity', 'entry_price', 'side'
        return _PositionCompat(pos)

    def get_cash(self) -> float:
        """Return current cash (sync helper)."""
        return self._cash

    def process_fills(self):
        """Process all SUBMITTED orders: fill them at current quote prices."""
        for order_id, order in list(self._orders.items()):
            if order.status != OrderStatus.SUBMITTED.value:
                continue
            req = getattr(order, '_order_request', None)
            if req is None:
                continue
            quote = self._quotes.get(order.symbol, {})
            if req.order_type == OrderType.LIMIT and req.price:
                fill_price = req.price
                if self._slippage_bps:
                    slip = self._slippage_bps / 10000.0
                    fill_price *= (1 + slip) if req.side == OrderSide.BUY else (1 - slip)
            elif req.side == OrderSide.BUY and quote.get("ask"):
                fill_price = quote["ask"]
                if self._slippage_bps:
                    fill_price *= (1 + self._slippage_bps / 10000.0)
            elif req.side == OrderSide.SELL and quote.get("bid"):
                fill_price = quote["bid"]
                if self._slippage_bps:
                    fill_price *= (1 - self._slippage_bps / 10000.0)
            else:
                fill_price = req.price or quote.get("mid", 0.0)
            if fill_price:
                self._fill_order(order, fill_price)

    def cancel_order(self, order_id: str) -> Optional[OrderResult]:
        """Sync cancel. Raises ValueError if order is already filled."""
        order = self._orders.get(order_id)
        if order is None:
            return None
        filled = {OrderStatus.FILLED.value, "filled"}
        if order.status in filled:
            raise ValueError(f"Cannot cancel filled order {order_id}")
        rejected_cancelled = {OrderStatus.REJECTED.value, "rejected", OrderStatus.CANCELLED.value, "cancelled"}
        if order.status in rejected_cancelled:
            return order  # Already terminal
        order.status = OrderStatus.CANCELLED.value
        return order


class TigerBrokersBroker(BrokerInterface):
    """Tiger Brokers implementation (stub for future).

    To implement:
    1. Install `tigeropen` SDK
    2. Configure with account credentials in .env:
       - TIGER_ACCOUNT_ID
       - TIGER_PRIVATE_KEY
       - TIGER_SERVER (https://api.tigerbrokers.com)
    3. Implement all abstract methods using Tiger Open API
    """

    def __init__(self, config: Dict[str, Any] = None):
        self._connected = False
        self._client = None
        self.config = config or {}

    async def connect(self) -> bool:
        try:
            from tigeropen.tiger_open_client import TigerOpenClient
            # Load from env / config
            account_id = self.config.get('account_id') or os.getenv('TIGER_ACCOUNT_ID')
            private_key_path = self.config.get('private_key_path') or os.getenv('TIGER_PRIVATE_KEY_PATH')
            server = self.config.get('server', 'https://api.tigerbrokers.com')

            if not account_id or not private_key_path:
                logger.error("Tiger Brokers: missing account_id or private_key_path")
                return False

            self._client = TigerOpenClient(account_id, private_key_path, server)
            # Test connection
            self._client.get_account()
            self._connected = True
            logger.info("Tiger Brokers connected successfully")
            return True
        except Exception as e:
            logger.error(f"Tiger Brokers connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        if self._client:
            self._client.logout()
            self._client = None
        self._connected = False

    async def submit_order(self, order: Dict[str, Any]) -> OrderResult:
        if not self._connected or not self._client:
            return OrderResult(status="rejected", error_message="Not connected", **{k: order.get(k) for k in ['symbol', 'action', 'quantity']})

        try:
            # Convert to Tiger order format
            # Placeholder: actual implementation depends on Tiger SDK
            # resp = self._client.place_order(...)
            raise NotImplementedError("TigerBrokersBroker.submit_order not yet implemented")
        except Exception as e:
            return OrderResult(
                order_id="",
                symbol=order['symbol'],
                action=order['action'],
                quantity=order['quantity'],
                filled_quantity=0,
                filled_price=0,
                status="rejected",
                timestamp=datetime.now(),
                error_message=str(e)
            )

    async def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError

    async def get_positions(self) -> List[Position]:
        if not self._connected:
            return []
        try:
            # positions = self._client.get_positions()
            # convert to Position objects
            raise NotImplementedError
        except Exception:
            return []

    async def get_account(self) -> Dict[str, Any]:
        if not self._connected:
            return {}
        try:
            # acct = self._client.get_account()
            # return {...}
            raise NotImplementedError
        except Exception:
            return {}

    async def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        return None

    def is_connected(self) -> bool:
        return self._connected
