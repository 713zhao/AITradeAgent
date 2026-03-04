"""
Portfolio Data Models

Defines Position, Trade, Portfolio data structures for position tracking and trade management.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class TradeStatus(Enum):
    """Trade execution status."""
    PENDING = "pending"          # Awaiting approval or execution
    APPROVED = "approved"        # Approved by risk manager (Phase 4)
    EXECUTION_REQUESTED = "execution_requested"  # Sent to broker
    FILLED = "filled"            # Fully filled
    PARTIALLY_FILLED = "partially_filled"  # Partially filled
    CANCELLED = "cancelled"      # User cancelled
    REJECTED = "rejected"        # Risk manager rejected
    ERROR = "error"              # Execution error


@dataclass
class Position:
    """
    Represents an open position in a single symbol.
    
    Attributes:
        symbol: Trading symbol (e.g., 'AAPL')
        quantity: Number of shares held (positive = long, negative = short)
        avg_cost: Average cost per share (purchase price or short price)
        current_price: Current market price (updated real-time)
        opened_at: Timestamp when position opened
        updated_at: Last update timestamp
        trades: List of Trade IDs that make up this position
        metadata: Additional data (decision_id, reason, etc.)
    """
    symbol: str
    quantity: float
    avg_cost: float
    current_price: float = 0.0
    opened_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    trades: List[str] = field(default_factory=list)  # Trade IDs
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def market_value(self) -> float:
        """Current market value of position."""
        return self.quantity * self.current_price
    
    def cost_basis(self) -> float:
        """Total cost of position (avg_cost * qty)."""
        return self.quantity * self.avg_cost
    
    def unrealized_pnl(self) -> float:
        """Unrealized profit/loss."""
        return self.market_value() - self.cost_basis()
    
    def unrealized_pnl_pct(self) -> float:
        """Unrealized P&L as percentage."""
        if self.cost_basis() == 0:
            return 0.0
        return (self.unrealized_pnl() / abs(self.cost_basis())) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "avg_cost": self.avg_cost,
            "current_price": self.current_price,
            "market_value": self.market_value(),
            "cost_basis": self.cost_basis(),
            "unrealized_pnl": self.unrealized_pnl(),
            "unrealized_pnl_pct": self.unrealized_pnl_pct(),
            "opened_at": self.opened_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "trades": self.trades,
            "metadata": self.metadata,
        }


@dataclass
class Trade:
    """
    Represents a single trade execution.
    
    Attributes:
        trade_id: Unique trade identifier
        task_id: Associated decision task ID from Phase 2
        symbol: Trading symbol
        side: "BUY" or "SELL"
        quantity: Number of shares
        price: Execution price per share
        filled_quantity: Actual quantity filled (may be partial)
        status: Trade status (pending, filled, rejected, etc.)
        decision: Associated Decision object JSON {symbol, decision, confidence, signals, SL, TP}
        confidence: Decision confidence (0-1)
        stop_loss: Stop loss price (from decision engine)
        take_profit: Take profit price (from decision engine)
        ordered_at: When trade was requested
        filled_at: When trade was filled (None if pending)
        reason: Trade reason (e.g., "RSI oversold", "MACD bullish")
        approval_required: Whether approval needed (Phase 4)
        approval_received: Whether approved (None if not required)
        executed_by: User/system that executed (approval_by)
        error_reason: If rejected, reason why
        metadata: Additional data (order_id, broker_ref, etc.)
    """
    trade_id: str
    task_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: float
    price: float
    status: TradeStatus = TradeStatus.PENDING
    filled_quantity: float = 0.0
    decision: Dict[str, Any] = field(default_factory=dict)  # Decision JSON
    confidence: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    ordered_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = None
    reason: str = ""
    approval_required: bool = False
    approval_received: Optional[bool] = None
    executed_by: Optional[str] = None
    error_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_filled(self) -> bool:
        """Check if trade is fully filled."""
        return self.status == TradeStatus.FILLED
    
    def is_partial(self) -> bool:
        """Check if trade is partially filled."""
        return self.status == TradeStatus.PARTIALLY_FILLED
    
    def fill_percentage(self) -> float:
        """Percentage of trade filled."""
        if self.quantity == 0:
            return 0.0
        return (self.filled_quantity / self.quantity) * 100
    
    def realized_pnl(self, sell_price: float = None) -> float:
        """
        Calculate realized P&L (for closed positions).
        
        Args:
            sell_price: Sale price (use self.price if not provided)
        
        Returns:
            P&L for actual filled quantity
        """
        if self.side == "BUY":
            return 0.0  # P&L realized when selling
        else:  # SELL
            # Short sale: profit if sell_price > price (we shorted at price, bought back lower)
            sell_price = sell_price or self.price
            return (self.price - sell_price) * self.filled_quantity
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "trade_id": self.trade_id,
            "task_id": self.task_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "filled_quantity": self.filled_quantity,
            "fill_percentage": self.fill_percentage(),
            "status": self.status.value if isinstance(self.status, TradeStatus) else self.status,
            "decision": self.decision,
            "confidence": self.confidence,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "ordered_at": self.ordered_at.isoformat(),
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "reason": self.reason,
            "approval_required": self.approval_required,
            "approval_received": self.approval_received,
            "executed_by": self.executed_by,
            "error_reason": self.error_reason,
            "metadata": self.metadata,
        }


@dataclass
class Portfolio:
    """
    Represents the complete portfolio state.
    
    Attributes:
        initial_cash: Starting cash amount
        current_cash: Available cash (not in positions)
        positions: Dict of symbol → Position
        trades: List of all Trade objects
        created_at: Portfolio creation timestamp
        updated_at: Last update timestamp
        metadata: Additional data (account_id, custodian, etc.)
    """
    initial_cash: float
    current_cash: float = 0.0
    positions: Dict[str, Position] = field(default_factory=dict)
    trades: List[Trade] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize current_cash if not provided."""
        if self.current_cash == 0.0:
            self.current_cash = self.initial_cash
    
    def gross_position_value(self) -> float:
        """Total market value of all positions (long + short)."""
        return sum(pos.market_value() for pos in self.positions.values())
    
    def net_position_value(self) -> float:
        """Net market value of positions (long - short)."""
        return sum(pos.market_value() for pos in self.positions.values())
    
    def total_equity(self) -> float:
        """Total portfolio equity = cash + position values."""
        return self.current_cash + self.net_position_value()
    
    def unrealized_pnl(self) -> float:
        """Total unrealized P&L from all open positions."""
        return sum(pos.unrealized_pnl() for pos in self.positions.values())
    
    def realized_pnl(self) -> float:
        """Total realized P&L from closed positions."""
        # Realized P&L = Initial cash - closing trade value
        # For now, calculate from trades that are closed
        initial_spent = sum(
            trade.quantity * trade.price 
            for trade in self.trades 
            if trade.side == "BUY" and trade.status == TradeStatus.FILLED
        )
        realized = self.initial_cash - initial_spent - self.current_cash
        return realized
    
    def total_pnl(self) -> float:
        """Total P&L = realized + unrealized."""
        return self.realized_pnl() + self.unrealized_pnl()
    
    def total_return_pct(self) -> float:
        """Total return as percentage of initial capital."""
        if self.initial_cash == 0:
            return 0.0
        return (self.total_pnl() / self.initial_cash) * 100
    
    def drawdown_pct(self) -> float:
        """Current drawdown from initial capital."""
        equity = self.total_equity()
        if self.initial_cash == 0:
            return 0.0
        if equity >= self.initial_cash:
            return 0.0
        return ((self.initial_cash - equity) / self.initial_cash) * 100
    
    def position_count(self) -> int:
        """Number of open positions."""
        return len(self.positions)
    
    def trade_count(self) -> int:
        """Total number of trades."""
        return len(self.trades)
    
    def win_rate(self) -> float:
        """Percentage of profitable trades."""
        if not self.trades:
            return 0.0
        filled_trades = [t for t in self.trades if t.is_filled()]
        if not filled_trades:
            return 0.0
        winners = len([t for t in filled_trades if t.realized_pnl() > 0])
        return (winners / len(filled_trades)) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "initial_cash": self.initial_cash,
            "current_cash": self.current_cash,
            "gross_position_value": self.gross_position_value(),
            "net_position_value": self.net_position_value(),
            "total_equity": self.total_equity(),
            "unrealized_pnl": self.unrealized_pnl(),
            "realized_pnl": self.realized_pnl(),
            "total_pnl": self.total_pnl(),
            "total_return_pct": self.total_return_pct(),
            "drawdown_pct": self.drawdown_pct(),
            "positions": {
                symbol: pos.to_dict()
                for symbol, pos in self.positions.items()
            },
            "position_count": self.position_count(),
            "trade_count": self.trade_count(),
            "win_rate": self.win_rate(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }
