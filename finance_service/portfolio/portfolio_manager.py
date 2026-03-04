"""
Portfolio Manager

Orchestrates portfolio operations including position tracking, trade execution,
and P&L management.
"""

from datetime import datetime
from typing import Tuple, Optional, Dict, Any
import logging

from .models import Position, Trade, Portfolio, TradeStatus
from .trade_repository import TradeRepository
from .equity_calculator import EquityCalculator

logger = logging.getLogger(__name__)


class PortfolioManager:
    """
    Manages portfolio operations.
    
    Responsibilities:
    - Track open positions and trades
    - Execute buy/sell operations
    - Calculate position-level P&L
    - Manage portfolio equity
    """
    
    def __init__(self, initial_cash: float = 100000.0):
        """
        Initialize portfolio manager.
        
        Args:
            initial_cash: Starting balance
        """
        self.initial_cash = initial_cash
        self.repository = TradeRepository()
        self.equity_calculator = EquityCalculator()
        self.updated_at = datetime.utcnow()
    
    def execute_buy(
        self,
        task_id: str,
        symbol: str,
        quantity: float,
        price: float,
        decision: Dict[str, Any],
        confidence: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reason: str = "",
    ) -> Trade:
        """
        Execute a BUY trade.
        
        Args:
            task_id: Decision task ID
            symbol: Trading symbol
            quantity: Number of shares
            price: Execution price
            decision: Decision object from Phase 2
            confidence: Decision confidence
            stop_loss: Stop loss price
            take_profit: Take profit price
            reason: Trade reason
        
        Returns:
            Created Trade object
        """
        trade = self.repository.create_trade(
            task_id=task_id,
            symbol=symbol,
            side="BUY",
            quantity=quantity,
            price=price,
            decision=decision,
            confidence=confidence,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=reason,
        )
        
        # Update or create position
        position = self.repository.get_position(symbol)
        if position:
            # Average in to existing position
            new_qty = position.quantity + quantity
            new_cost = (position.cost_basis() + quantity * price) / new_qty
            self.repository.update_position(
                symbol,
                quantity=new_qty,
                avg_cost=new_cost,
                add_trade=trade.trade_id,
            )
        else:
            # Create new position
            self.repository.create_position(
                symbol,
                quantity=quantity,
                avg_cost=price,
                trades=[trade.trade_id],
            )
        
        self.updated_at = datetime.utcnow()
        logger.info(f"BUY trade created: {trade.trade_id} {symbol} {quantity}@{price}")
        return trade
    
    def execute_sell(
        self,
        task_id: str,
        symbol: str,
        quantity: float,
        price: float,
        decision: Dict[str, Any],
        confidence: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reason: str = "",
    ) -> Trade:
        """
        Execute a SELL trade.
        
        Args:
            task_id: Decision task ID
            symbol: Trading symbol
            quantity: Number of shares
            price: Execution price
            decision: Decision object from Phase 2
            confidence: Decision confidence
            stop_loss: Stop loss price (for short position)
            take_profit: Take profit price (for short position)
            reason: Trade reason
        
        Returns:
            Created Trade object
        """
        trade = self.repository.create_trade(
            task_id=task_id,
            symbol=symbol,
            side="SELL",
            quantity=quantity,
            price=price,
            decision=decision,
            confidence=confidence,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=reason,
        )
        
        # Update or create position
        position = self.repository.get_position(symbol)
        if position:
            # Reduce position or short if selling more than held
            new_qty = position.quantity - quantity
            if new_qty == 0:
                # Close position
                self.repository.close_position(symbol)
            else:
                # Update position
                self.repository.update_position(
                    symbol,
                    quantity=new_qty,
                    add_trade=trade.trade_id,
                )
        else:
            # Short position (sell without owning)
            self.repository.create_position(
                symbol,
                quantity=-quantity,
                avg_cost=price,
                trades=[trade.trade_id],
            )
        
        self.updated_at = datetime.utcnow()
        logger.info(f"SELL trade created: {trade.trade_id} {symbol} {quantity}@{price}")
        return trade
    
    def fill_trade(
        self,
        trade_id: str,
        filled_quantity: float = None,
        executed_by: str = "system",
    ) -> Optional[Trade]:
        """
        Mark trade as filled (simulating broker execution in paper trading).
        
        Args:
            trade_id: Trade to fill
            filled_quantity: Actual filled amount (None = full quantity)
            executed_by: System that executed
        
        Returns:
            Updated Trade or None
        """
        trade = self.repository.get_trade(trade_id)
        if not trade:
            return None
        
        filled_qty = filled_quantity or trade.quantity
        trade = self.repository.update_trade_status(
            trade_id,
            TradeStatus.FILLED,
            filled_quantity=filled_qty,
            executed_by=executed_by,
        )
        
        # Update position with actual fill
        if filled_qty < trade.quantity:
            # Partial fill
            trade.status = TradeStatus.PARTIALLY_FILLED
        
        self.updated_at = datetime.utcnow()
        logger.info(f"Trade filled: {trade_id} ({filled_qty}/{trade.quantity})")
        return trade
    
    def cancel_trade(self, trade_id: str, reason: str = "") -> Optional[Trade]:
        """
        Cancel a pending trade.
        
        Args:
            trade_id: Trade to cancel
            reason: Cancellation reason
        
        Returns:
            Updated Trade or None
        """
        trade = self.repository.get_trade(trade_id)
        if not trade:
            return None
        
        if trade.status not in [TradeStatus.PENDING, TradeStatus.APPROVED]:
            return None  # Can't cancel filled/rejected trades
        
        trade = self.repository.update_trade_status(
            trade_id,
            TradeStatus.CANCELLED,
            error_reason=reason,
        )
        
        # Revert position update (remove from trades list)
        position = self.repository.get_position(trade.symbol)
        if position and trade.trade_id in position.trades:
            position.trades.remove(trade.trade_id)
        
        self.updated_at = datetime.utcnow()
        logger.info(f"Trade cancelled: {trade_id} ({reason})")
        return trade
    
    def update_position_price(self, symbol: str, price: float) -> Optional[Position]:
        """
        Update current price for a position (for real-time P&L).
        
        Args:
            symbol: Trading symbol
            price: Current market price
        
        Returns:
            Updated Position or None
        """
        position = self.repository.update_position(symbol, current_price=price)
        self.updated_at = datetime.utcnow()
        return position
    
    def update_all_prices(self, prices: Dict[str, float]) -> None:
        """
        Update prices for all positions.
        
        Args:
            prices: Dict of symbol → current_price
        """
        self.repository.update_position_prices(prices)
        self.updated_at = datetime.utcnow()
    
    def get_portfolio(self) -> Portfolio:
        """Get current portfolio state."""
        return self.repository.calculate_portfolio(self.initial_cash)
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get specific position."""
        return self.repository.get_position(symbol)
    
    def get_positions(self) -> list:
        """Get all open positions."""
        return self.repository.get_positions()
    
    def get_trade(self, trade_id: str) -> Optional[Trade]:
        """Get specific trade."""
        return self.repository.get_trade(trade_id)
    
    def get_trades(self, symbol: str = None, status: TradeStatus = None):
        """
        Get trades filtered by symbol and/or status.
        
        Args:
            symbol: Optional symbol filter
            status: Optional status filter
        
        Returns:
            List of Trade objects
        """
        if symbol:
            trades = self.repository.get_trades_by_symbol(symbol)
        else:
            trades = self.repository.trades
        
        if status:
            trades = [t for t in trades if t.status == status]
        
        return trades
    
    def get_open_trades(self) -> list:
        """Get all pending/unfilled trades."""
        return self.repository.get_open_trades()
    
    def get_position_pnl(self, symbol: str) -> Tuple[float, float]:
        """
        Get P&L for a position.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Tuple of (unrealized_pnl, unrealized_pnl_pct)
        """
        position = self.get_position(symbol)
        if not position:
            return 0.0, 0.0
        
        return position.unrealized_pnl(), position.unrealized_pnl_pct()
    
    def get_portfolio_pnl(self) -> Tuple[float, float, float]:
        """
        Get portfolio-level P&L.
        
        Returns:
            Tuple of (realized_pnl, unrealized_pnl, total_pnl)
        """
        portfolio = self.get_portfolio()
        return (
            portfolio.realized_pnl(),
            portfolio.unrealized_pnl(),
            portfolio.total_pnl(),
        )
    
    def get_equity_metrics(self) -> Dict[str, Any]:
        """
        Get equity and risk metrics.
        
        Returns:
            Dict with equity, return %, drawdown, etc.
        """
        portfolio = self.get_portfolio()
        return {
            "initial_cash": portfolio.initial_cash,
            "current_cash": portfolio.current_cash,
            "gross_position_value": portfolio.gross_position_value(),
            "net_position_value": portfolio.net_position_value(),
            "total_equity": portfolio.total_equity(),
            "total_pnl": portfolio.total_pnl(),
            "total_return_pct": portfolio.total_return_pct(),
            "unrealized_pnl": portfolio.unrealized_pnl(),
            "realized_pnl": portfolio.realized_pnl(),
            "drawdown_pct": portfolio.drawdown_pct(),
            "position_count": portfolio.position_count(),
            "trade_count": portfolio.trade_count(),
            "win_rate": portfolio.win_rate(),
        }
    
    def reset(self) -> None:
        """Reset portfolio to initial state."""
        self.repository.clear_all()
        self.updated_at = datetime.utcnow()
        logger.info("Portfolio reset to initial state")
