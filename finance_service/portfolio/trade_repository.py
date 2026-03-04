"""
Trade Repository

CRUD operations for managing trades and positions in the portfolio.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from .models import Trade, Position, Portfolio, TradeStatus


class TradeRepository:
    """
    Repository for managing trades and positions.
    
    Maintains in-memory storage of trades and positions.
    Can be extended with SQLite persistence (Phase 3+).
    """
    
    def __init__(self):
        """Initialize empty repository."""
        self.trades: List[Trade] = []
        self.positions: Dict[str, Position] = {}
        self._trade_counter = 0
    
    def create_trade(
        self,
        task_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        decision: Dict[str, Any],
        confidence: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reason: str = "",
        approval_required: bool = False,
    ) -> Trade:
        """
        Create a new trade record.
        
        Args:
            task_id: Associated decision task ID
            symbol: Trading symbol
            side: "BUY" or "SELL"
            quantity: Number of shares
            price: Execution price
            decision: Decision object JSON
            confidence: Decision confidence (0-1)
            stop_loss: Stop loss price
            take_profit: Take profit price
            reason: Trade reason
            approval_required: Whether approval is needed
        
        Returns:
            Created Trade object
        """
        self._trade_counter += 1
        trade_id = f"TRADE_{self._trade_counter:06d}"
        
        trade = Trade(
            trade_id=trade_id,
            task_id=task_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            decision=decision,
            confidence=confidence,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=reason,
            approval_required=approval_required,
            status=TradeStatus.PENDING,
        )
        
        self.trades.append(trade)
        return trade
    
    def get_trade(self, trade_id: str) -> Optional[Trade]:
        """Get trade by ID."""
        for trade in self.trades:
            if trade.trade_id == trade_id:
                return trade
        return None
    
    def get_trades_by_symbol(self, symbol: str) -> List[Trade]:
        """Get all trades for a symbol."""
        return [t for t in self.trades if t.symbol == symbol]
    
    def get_trades_by_status(self, status: TradeStatus) -> List[Trade]:
        """Get all trades with specific status."""
        return [t for t in self.trades if t.status == status]
    
    def get_open_trades(self) -> List[Trade]:
        """Get all open (not filled) trades."""
        open_statuses = [
            TradeStatus.PENDING,
            TradeStatus.APPROVED,
            TradeStatus.EXECUTION_REQUESTED,
            TradeStatus.PARTIALLY_FILLED,
        ]
        return [t for t in self.trades if t.status in open_statuses]
    
    def get_filled_trades(self) -> List[Trade]:
        """Get all filled trades."""
        return [t for t in self.trades if t.status == TradeStatus.FILLED]
    
    def update_trade_status(
        self,
        trade_id: str,
        status: TradeStatus,
        filled_quantity: float = None,
        executed_by: str = None,
        error_reason: str = None,
    ) -> Optional[Trade]:
        """
        Update trade status.
        
        Args:
            trade_id: Trade to update
            status: New status
            filled_quantity: Quantity filled
            executed_by: User/system that executed
            error_reason: If rejected, reason why
        
        Returns:
            Updated Trade or None if not found
        """
        trade = self.get_trade(trade_id)
        if not trade:
            return None
        
        trade.status = status
        if filled_quantity is not None:
            trade.filled_quantity = filled_quantity
        if executed_by:
            trade.executed_by = executed_by
        if error_reason:
            trade.error_reason = error_reason
        if status == TradeStatus.FILLED:
            trade.filled_at = datetime.utcnow()
        
        trade.updated_at = datetime.utcnow()
        return trade
    
    def approve_trade(self, trade_id: str, approved_by: str) -> Optional[Trade]:
        """Approve a pending trade (Phase 4)."""
        trade = self.get_trade(trade_id)
        if not trade:
            return None
        trade.approval_received = True
        trade.executed_by = approved_by
        trade.updated_at = datetime.utcnow()
        return trade
    
    def reject_trade(self, trade_id: str, reason: str, rejected_by: str) -> Optional[Trade]:
        """Reject a pending trade."""
        trade = self.get_trade(trade_id)
        if not trade:
            return None
        trade.status = TradeStatus.REJECTED
        trade.error_reason = reason
        trade.executed_by = rejected_by
        trade.updated_at = datetime.utcnow()
        return trade
    
    def create_position(
        self,
        symbol: str,
        quantity: float,
        avg_cost: float,
        trades: List[str] = None,
    ) -> Position:
        """
        Create a new position.
        
        Args:
            symbol: Trading symbol
            quantity: Number of shares
            avg_cost: Average cost per share
            trades: List of trade IDs that make up position
        
        Returns:
            Created Position object
        """
        position = Position(
            symbol=symbol,
            quantity=quantity,
            avg_cost=avg_cost,
            trades=trades or [],
        )
        self.positions[symbol] = position
        return position
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for symbol."""
        return self.positions.get(symbol)
    
    def get_positions(self) -> List[Position]:
        """Get all positions."""
        return list(self.positions.values())
    
    def update_position(
        self,
        symbol: str,
        quantity: float = None,
        avg_cost: float = None,
        current_price: float = None,
        add_trade: str = None,
    ) -> Optional[Position]:
        """
        Update position.
        
        Args:
            symbol: Trading symbol
            quantity: New quantity
            avg_cost: New average cost
            current_price: Current market price
            add_trade: Trade ID to add to position
        
        Returns:
            Updated Position or None if not found
        """
        position = self.get_position(symbol)
        if not position:
            return None
        
        if quantity is not None:
            position.quantity = quantity
        if avg_cost is not None:
            position.avg_cost = avg_cost
        if current_price is not None:
            position.current_price = current_price
        if add_trade:
            if add_trade not in position.trades:
                position.trades.append(add_trade)
        
        position.updated_at = datetime.utcnow()
        return position
    
    def close_position(self, symbol: str) -> Optional[Position]:
        """Close a position (remove it)."""
        position = self.positions.pop(symbol, None)
        return position
    
    def update_position_prices(self, prices: Dict[str, float]) -> None:
        """
        Update current prices for all positions.
        
        Args:
            prices: Dict of symbol → current_price
        """
        for symbol, price in prices.items():
            position = self.get_position(symbol)
            if position:
                position.current_price = price
                position.updated_at = datetime.utcnow()
    
    def calculate_portfolio(self, initial_cash: float) -> Portfolio:
        """
        Calculate complete portfolio state.
        
        Args:
            initial_cash: Starting cash amount
        
        Returns:
            Portfolio object with current state
        """
        # Calculate current cash (initial - spent on open positions)
        spent = sum(
            pos.cost_basis()
            for pos in self.positions.values()
            if pos.quantity > 0  # Long positions only
        )
        # Shorts reduce cash available (margin requirement)
        short_margin = sum(
            abs(pos.market_value())
            for pos in self.positions.values()
            if pos.quantity < 0  # Short positions
        )
        current_cash = initial_cash - spent - short_margin
        
        portfolio = Portfolio(
            initial_cash=initial_cash,
            current_cash=current_cash,
            positions=self.positions.copy(),
            trades=self.trades.copy(),
        )
        return portfolio
    
    def clear_all(self) -> None:
        """Clear all trades and positions (for reset/testing)."""
        self.trades.clear()
        self.positions.clear()
        self._trade_counter = 0
