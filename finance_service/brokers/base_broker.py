"""
Abstract base broker interface for live trading integration.

All broker implementations (Alpaca, Interactive Brokers, etc.) must implement
this interface to ensure compatibility with the trading system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class OrderType(Enum):
    """Order types supported by brokers"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    """Order lifecycle states"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderSide(Enum):
    """Order direction"""
    BUY = "buy"
    SELL = "sell"


@dataclass
class OrderRequest:
    """Request to place an order"""
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType
    price: Optional[float] = None  # For limit orders
    stop_price: Optional[float] = None  # For stop orders
    time_in_force: str = "day"  # "day", "gtc", "ioc", "fok"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate order request"""
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive")
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("Limit price required for limit orders")
        if self.order_type == OrderType.STOP and self.stop_price is None:
            raise ValueError("Stop price required for stop orders")


@dataclass
class Order:
    """Order object returned from broker"""
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    filled_quantity: float
    avg_fill_price: float
    status: OrderStatus
    order_type: OrderType
    submitted_at: datetime
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    reason: Optional[str] = None  # Cancellation/rejection reason
    
    def is_closed(self) -> bool:
        """Check if order is in terminal state"""
        return self.status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED]
    
    def is_partially_filled(self) -> bool:
        """Check if order has partial fills"""
        return self.status == OrderStatus.PARTIAL and self.filled_quantity > 0


@dataclass
class Position:
    """Position in broker account"""
    symbol: str
    quantity: float
    entry_price: float = 0.0
    current_price: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    side: str = "long"  # "long" or "short"
    # Multi-broker fields
    avg_price: float = None
    realized_pnl: float = 0.0
    asset_type: 'AssetType' = None
    broker: str = None
    last_updated: datetime = None
    
    def __post_init__(self):
        """Set defaults for None values"""
        from datetime import datetime
        if self.last_updated is None:
            self.last_updated = datetime.now()
        if self.asset_type is None:
            self.asset_type = AssetType.STOCK
    
    def to_dict(self) -> Dict:
        """Serialize position"""
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "market_value": self.market_value,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "side": self.side,
            "avg_price": self.avg_price,
            "realized_pnl": self.realized_pnl,
            "asset_type": self.asset_type,
            "broker": self.broker,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


@dataclass
class Account:
    """Broker account information"""
    account_number: str
    cash: float
    buying_power: float
    total_equity: float
    initial_equity: float
    net_value: float
    multiplier: float  # 1 for cash, 4+ for margin
    is_margin: bool
    can_daytrade: bool
    last_updated: datetime
    
    def to_dict(self) -> Dict:
        """Serialize account"""
        return {
            "account_number": self.account_number,
            "cash": self.cash,
            "buying_power": self.buying_power,
            "total_equity": self.total_equity,
            "initial_equity": self.initial_equity,
            "net_value": self.net_value,
            "multiplier": self.multiplier,
            "is_margin": self.is_margin,
            "can_daytrade": self.can_daytrade,
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class AccountInfo:
    """Account information for multi-broker system"""
    account_id: str
    broker: str
    currency: str = "USD"
    cash_balance: float = 0.0
    buying_power: float = 0.0
    total_value: float = 0.0
    day_trade_count: int = 0
    maintenance_margin: float = 0.0
    equity_with_loan: float = 0.0
    last_updated: datetime = None
    
    def __post_init__(self):
        """Set defaults for None values"""
        if self.last_updated is None:
            self.last_updated = datetime.now()
    
    def to_dict(self) -> Dict:
        """Serialize account info"""
        return {
            "account_id": self.account_id,
            "broker": self.broker,
            "currency": self.currency,
            "cash_balance": self.cash_balance,
            "buying_power": self.buying_power,
            "total_value": self.total_value,
            "day_trade_count": self.day_trade_count,
            "maintenance_margin": self.maintenance_margin,
            "equity_with_loan": self.equity_with_loan,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


@dataclass
class OrderResult:
    """Result of order placement"""
    success: bool
    order_id: Optional[str] = None
    order: Optional['Order'] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Serialize result"""
        return {
            "success": self.success,
            "order_id": self.order_id,
            "error_message": self.error_message,
        }


@dataclass
class MarketData:
    """Market data snapshot"""
    symbol: str
    bid: float
    ask: float
    bid_size: float = 0.0
    ask_size: float = 0.0
    last_trade_price: Optional[float] = None
    last_trade_size: Optional[float] = None
    volume: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    # Alternate name for last_trade_price (for compatibility)
    last: Optional[float] = field(default=None, init=True, repr=False)
    
    def __post_init__(self):
        """Handle alternate field names"""
        if self.last is not None and self.last_trade_price is None:
            self.last_trade_price = self.last
    
    def to_dict(self) -> Dict:
        """Serialize market data"""
        return {
            "symbol": self.symbol,
            "bid": self.bid,
            "ask": self.ask,
            "bid_size": self.bid_size,
            "ask_size": self.ask_size,
            "last_trade_price": self.last_trade_price,
            "last_trade_size": self.last_trade_size,
            "volume": self.volume,
            "timestamp": self.timestamp.isoformat(),
        }


class AssetType(Enum):
    """Asset types for trading"""
    STOCK = "stock"
    CRYPTO = "crypto"
    FOREX = "forex"
    COMMODITY = "commodity"
    OPTION = "option"
    FUTURE = "future"


class BaseBroker(ABC):
    """
    Abstract base class for broker integrations.
    
    All concrete broker implementations must inherit from this class
    and implement all abstract methods.
    """
    
    def __init__(self, broker_name: str, paper_trading: bool = False):
        """
        Initialize broker.
        
        Args:
            broker_name: Name of the broker (e.g., "Alpaca", "IBKR")
            paper_trading: Whether to use paper trading mode
        """
        self.broker_name = broker_name
        self.paper_trading = paper_trading
        self.logger = logging.getLogger(f"{__name__}.{broker_name}")
        self.logger.info(f"Initialized {broker_name} (paper_trading={paper_trading})")
    
    def is_connected(self) -> bool:
        """
        Check if broker connection is active.
        
        Returns:
            True if connected, False otherwise.
        """
        return True  # Default implementation - subclasses can override
    
    # =====================
    # ACCOUNT OPERATIONS
    # =====================
    
    @abstractmethod
    def get_account(self) -> Account:
        """
        Get current account information.
        
        Returns:
            Account object with cash, equity, buying power, etc.
        """
        pass
    
    @abstractmethod
    def get_cash(self) -> float:
        """Get available cash in account"""
        pass
    
    @abstractmethod
    def get_buying_power(self) -> float:
        """Get available buying power (includes margin)"""
        pass
    
    @abstractmethod
    def get_account_value(self) -> float:
        """Get total account value"""
        pass
    
    # =====================
    # POSITION OPERATIONS
    # =====================
    
    @abstractmethod
    def get_positions(self) -> Dict[str, Position]:
        """
        Get all open positions.
        
        Returns:
            Dictionary mapping symbol to Position
        """
        pass
    
    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for specific symbol"""
        pass
    
    @abstractmethod
    def close_position(self, symbol: str) -> Order:
        """
        Close entire position for a symbol (market order).
        
        Args:
            symbol: Symbol to close
            
        Returns:
            Order object
        """
        pass
    
    # =====================
    # ORDER OPERATIONS
    # =====================
    
    @abstractmethod
    def place_order(self, order_request: OrderRequest) -> Order:
        """
        Place an order.
        
        Args:
            order_request: OrderRequest object with details
            
        Returns:
            Order object with initial status
        """
        pass
    
    @abstractmethod
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get status of an order"""
        pass
    
    @abstractmethod
    def get_orders(self, status: Optional[OrderStatus] = None) -> List[Order]:
        """
        Get orders, optionally filtered by status.
        
        Args:
            status: Filter by OrderStatus, or None for all
            
        Returns:
            List of Order objects
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> Order:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            Updated Order object
        """
        pass
    
    # =====================
    # MARKET DATA
    # =====================
    
    @abstractmethod
    def get_last_quote(self, symbol: str) -> Dict[str, float]:
        """
        Get last quote for a symbol.
        
        Returns:
            Dict with 'bid', 'ask', 'bid_size', 'ask_size', 'last', 'volume'
        """
        pass
    
    # =====================
    # UTILITY METHODS
    # =====================
    
    def is_market_open(self) -> bool:
        """Check if market is currently open"""
        # Default to checking US market hours (9:30 AM - 4:00 PM ET)
        # Override in subclasses for broker-specific logic
        from datetime import time
        now = datetime.now()
        
        # Only open Mon-Fri (weekday 0-4)
        if now.weekday() >= 5:
            return False
        
        # Market hours: 9:30 AM - 4:00 PM
        market_open = time(9, 30)
        market_close = time(16, 0)
        
        return market_open <= now.time() < market_close
    
    def validate_symbol(self, symbol: str) -> bool:
        """Validate that a symbol is tradeable"""
        # Default implementation - override in subclasses
        if not symbol or len(symbol) > 5:
            return False
        return symbol.isalpha()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize broker info"""
        return {
            "broker_name": self.broker_name,
            "paper_trading": self.paper_trading,
        }
