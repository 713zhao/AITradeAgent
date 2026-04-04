"""
Trade Repository

CRUD operations for managing trades and positions in the portfolio.
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from .models import Trade, Position, Portfolio, TradeStatus
from finance_service.storage import get_portfolio_db

logger = logging.getLogger(__name__)


class TradeRepository:
    """
    Repository for managing trades and positions.
    
    Maintains in-memory storage of trades and positions.
    Can be extended with SQLite persistence (Phase 3+).
    """
    
    def __init__(self, use_db: bool = True):
        """
        Initialize repository.
        
        Args:
            use_db: If True, enable persistence using portfolio database.
        """
        self.trades: List[Trade] = []
        self.positions: Dict[str, Position] = {}
        self._trade_counter = 0
        self.db = None
        if use_db:
            try:
                self.db = get_portfolio_db()
                self._load_from_db()
            except Exception as e:
                logger.error(f"Failed to initialize database for TradeRepository: {e}")
                self.db = None
    
    def _load_from_db(self) -> None:
        """Load trades from database and rebuild positions."""
        if not self.db:
            return
        
        try:
            trade_dicts = self.db.load_all_trade_objects()
            trades = []
            for td in trade_dicts:
                try:
                    # Convert status string to Enum
                    status_val = td.get('status', 'PENDING')
                    if isinstance(status_val, str):
                        status = TradeStatus(status_val)
                    else:
                        status = status_val
                    # Parse datetimes
                    ordered_at = td.get('ordered_at')
                    if ordered_at:
                        if isinstance(ordered_at, str):
                            ordered_at = datetime.fromisoformat(ordered_at.replace('Z', '+00:00'))
                        else:
                            ordered_at = datetime.utcnow()
                    else:
                        ordered_at = datetime.utcnow()
                    filled_at = td.get('filled_at')
                    if filled_at:
                        if isinstance(filled_at, str):
                            filled_at = datetime.fromisoformat(filled_at.replace('Z', '+00:00'))
                        else:
                            filled_at = None
                    else:
                        filled_at = None
                    
                    trade = Trade(
                        trade_id=td['trade_id'],
                        task_id=td.get('task_id', ''),
                        symbol=td['symbol'],
                        side=td['side'],
                        quantity=td['quantity'],
                        price=td['price'],
                        status=status,
                        filled_quantity=td.get('filled_quantity', 0.0),
                        decision=td.get('decision', {}),
                        confidence=td.get('confidence', 0.0),
                        stop_loss=td.get('stop_loss'),
                        take_profit=td.get('take_profit'),
                        ordered_at=ordered_at,
                        filled_at=filled_at,
                        reason=td.get('reason', ''),
                        approval_required=td.get('approval_required', False),
                        approval_received=td.get('approval_received'),
                        executed_by=td.get('executed_by'),
                        error_reason=td.get('error_reason'),
                        metadata=td.get('metadata', {})
                    )
                    trades.append(trade)
                except Exception as e:
                    logger.warning(f"Failed to reconstruct trade {td.get('trade_id')}: {e}")
                    continue
            
            # Sort trades by ordered_at (and by trade_id numeric for stable order)
            trades.sort(key=lambda t: (t.ordered_at, int(t.trade_id.split('_')[1]) if '_' in t.trade_id else 0))
            self.trades = trades
            
            # Rebuild positions from FILLED trades
            self.positions = {}
            for trade in self.trades:
                if trade.status == TradeStatus.FILLED:
                    self._apply_trade_to_position(trade)
            
            # Update trade counter to highest existing
            max_num = 0
            for t in self.trades:
                try:
                    num = int(t.trade_id.split('_')[1])
                    if num > max_num:
                        max_num = num
                except:
                    pass
            self._trade_counter = max_num
            
            logger.info(f"TradeRepository loaded {len(self.trades)} trades and {len(self.positions)} positions from DB")
        except Exception as e:
            logger.error(f"Error loading trades from DB: {e}")
    
    def _apply_trade_to_position(self, trade: Trade) -> None:
        """Apply a filled trade to the in-memory position."""
        symbol = trade.symbol
        qty = trade.quantity
        price = trade.price
        side = trade.side.upper()
        stop_loss = trade.stop_loss
        take_profit = trade.take_profit
        
        position = self.positions.get(symbol)
        if side == "BUY":
            if position:
                # Existing long: update avg cost and quantity
                old_qty = position.quantity
                old_cost = position.avg_cost
                new_qty = old_qty + qty
                new_cost = (old_cost * old_qty + price * qty) / new_qty
                position.quantity = new_qty
                position.avg_cost = new_cost
                # Update stop_loss/take_profit to latest values if provided
                if stop_loss is not None:
                    position.stop_loss_price = stop_loss
                if take_profit is not None:
                    position.take_profit_price = take_profit
            else:
                # New long position
                position = Position(
                    symbol=symbol,
                    quantity=qty,
                    avg_cost=price,
                    current_price=price,
                    stop_loss_price=stop_loss,
                    take_profit_price=take_profit,
                )
                self.positions[symbol] = position
            position.trades.append(trade.trade_id)
        elif side == "SELL":
            if position:
                # Reduce or close position
                new_qty = position.quantity - qty
                if new_qty <= 0:
                    # Position closed or flipped (we remove for simplicity)
                    if new_qty < 0:
                        # This would be a short, not fully supported yet; create negative position?
                        # For now, just set quantity negative (short)
                        position.quantity = new_qty
                        position.avg_cost = price  # avg cost for short?
                        # For short, we might set stop_loss/take_profit as well?
                        if stop_loss is not None:
                            position.stop_loss_price = stop_loss
                        if take_profit is not None:
                            position.take_profit_price = take_profit
                    else:
                        # Exact zero close
                        del self.positions[symbol]
                        return
                else:
                    position.quantity = new_qty
                position.trades.append(trade.trade_id)
            else:
                # Short selling (not enabled typically)
                position = Position(
                    symbol=symbol,
                    quantity=-qty,
                    avg_cost=price,
                    current_price=price,
                    stop_loss_price=stop_loss,
                    take_profit_price=take_profit,
                )
                self.positions[symbol] = position
                position.trades.append(trade.trade_id)
        else:
            logger.warning(f"Unknown side {side} for trade {trade.trade_id}")
    
    def _persist_trade(self, trade: Trade) -> None:
        """Persist a trade object to the database."""
        if self.db:
            try:
                trade_dict = trade.to_dict()
                self.db.upsert_trade_object(trade_dict)
            except Exception as e:
                logger.error(f"Failed to persist trade {trade.trade_id}: {e}")
    
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
        self._persist_trade(trade)
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
        self._persist_trade(trade)
        return trade
    
    def approve_trade(self, trade_id: str, approved_by: str) -> Optional[Trade]:
        """Approve a pending trade (Phase 4)."""
        trade = self.get_trade(trade_id)
        if not trade:
            return None
        trade.approval_received = True
        trade.executed_by = approved_by
        trade.updated_at = datetime.utcnow()
        self._persist_trade(trade)
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
        self._persist_trade(trade)
        return trade
    
    def create_position(
        self,
        symbol: str,
        quantity: float,
        avg_cost: float,
        trades: List[str] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
    ) -> Position:
        """
        Create a new position.
        
        Args:
            symbol: Trading symbol
            quantity: Number of shares
            avg_cost: Average cost per share
            trades: List of trade IDs that make up position
            stop_loss_price: Stop loss price
            take_profit_price: Take profit price
        
        Returns:
            Created Position object
        """
        position = Position(
            symbol=symbol,
            quantity=quantity,
            avg_cost=avg_cost,
            trades=trades or [],
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
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
        stop_loss_price: float = None,
        take_profit_price: float = None,
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
        if stop_loss_price is not None:
            position.stop_loss_price = stop_loss_price
        if take_profit_price is not None:
            position.take_profit_price = take_profit_price
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
