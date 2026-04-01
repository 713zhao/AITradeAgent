"""Abstract broker interface.

All broker implementations must adhere to this interface.
Enables switching between paper trading, Alpaca, Tiger Brokers, etc.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from finance_service.core.models import Position, Trade


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


class PaperBroker(BrokerInterface):
    """Paper trading broker - simulates orders locally.

    Maintains an in-memory portfolio and executes orders at midpoint prices.
    Used when `finance.execution.broker: "paper"`.
    """

    def __init__(self, initial_cash: float = 100000.0):
        self._connected = False
        self._cash = initial_cash
        self._positions: Dict[str, Position] = {}  # symbol -> Position
        self._orders: Dict[str, OrderResult] = {}
        self._order_counter = 0

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

        # For paper trading, assume immediate fill at provided price
        fill_price = limit_price if order_type == 'limit' and limit_price else order.get('price', 0.0)
        if fill_price == 0.0:
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
