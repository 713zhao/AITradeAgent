"""
Trade Monitor - Phase 5: Monitor open trades, track SL/TP levels

Responsibilities:
- Monitor open positions
- Track stop-loss and take-profit triggers
- Generate trade status reports
- Calculate real-time P&L
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, List
from enum import Enum


class TradeState(Enum):
    """State of a monitored trade."""
    OPEN = "open"
    SL_HIT = "sl_hit"  # Stop-loss triggered
    TP_HIT = "tp_hit"  # Take-profit triggered
    CLOSED = "closed"  # Manually closed
    EXPIRED = "expired"  # Position aged out


@dataclass
class TradeMonitorRecord:
    """Record for monitoring a single trade."""
    
    trade_id: str
    symbol: str
    side: str  # BUY or SELL
    entry_price: float
    entry_quantity: int
    
    # Stop-loss and take-profit
    stop_loss: float
    take_profit: float
    
    # Current state
    current_price: float = 0.0
    state: TradeState = TradeState.OPEN
    
    # Timing
    entry_time: datetime = field(default_factory=datetime.utcnow)
    exit_time: Optional[datetime] = None
    
    # P&L tracking
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    
    def calculate_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L."""
        if self.side == "BUY":
            self.unrealized_pnl = (current_price - self.entry_price) * self.entry_quantity
        else:  # SELL
            self.unrealized_pnl = (self.entry_price - current_price) * self.entry_quantity
        
        return self.unrealized_pnl
    
    def check_sl_tp(self, current_price: float) -> Optional[TradeState]:
        """
        Check if SL or TP is hit.
        
        Args:
            current_price: Current market price
            
        Returns:
            TradeState if triggered, None otherwise
        """
        self.current_price = current_price
        self.calculate_pnl(current_price)
        
        if self.side == "BUY":
            # For long positions: SL below entry, TP above entry
            if current_price <= self.stop_loss:
                self.state = TradeState.SL_HIT
                self.realized_pnl = (self.stop_loss - self.entry_price) * self.entry_quantity
                return TradeState.SL_HIT
            elif current_price >= self.take_profit:
                self.state = TradeState.TP_HIT
                self.realized_pnl = (self.take_profit - self.entry_price) * self.entry_quantity
                return TradeState.TP_HIT
        else:  # SELL
            # For short positions: SL above entry, TP below entry
            if current_price >= self.stop_loss:
                self.state = TradeState.SL_HIT
                self.realized_pnl = (self.entry_price - self.stop_loss) * self.entry_quantity
                return TradeState.SL_HIT
            elif current_price <= self.take_profit:
                self.state = TradeState.TP_HIT
                self.realized_pnl = (self.entry_price - self.take_profit) * self.entry_quantity
                return TradeState.TP_HIT
        
        return None
    
    def close_trade(self, exit_price: float, reason: str = "manual") -> None:
        """Close a trade."""
        self.current_price = exit_price
        self.state = TradeState.CLOSED
        self.exit_time = datetime.utcnow()
        
        if self.side == "BUY":
            self.realized_pnl = (exit_price - self.entry_price) * self.entry_quantity
        else:
            self.realized_pnl = (self.entry_price - exit_price) * self.entry_quantity
    
    def to_dict(self) -> Dict:
        """Serialize monitor record."""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "entry_quantity": self.entry_quantity,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "current_price": self.current_price,
            "state": self.state.value,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "pnl_pct": (self.unrealized_pnl / (self.entry_price * self.entry_quantity) * 100) if self.entry_price > 0 else 0.0,
        }


class TradeMonitor:
    """
    Monitor for open trades.
    
    Tracks:
    - Open positions
    - SL/TP levels
    - Real-time P&L
    - Trade closure triggers
    """
    
    def __init__(self):
        """Initialize trade monitor."""
        self.open_trades: Dict[str, TradeMonitorRecord] = {}
        self.closed_trades: Dict[str, TradeMonitorRecord] = {}
        self.sl_tp_triggers: List[Dict] = []
    
    def add_trade(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        entry_price: float,
        entry_quantity: int,
        stop_loss: float,
        take_profit: float
    ) -> TradeMonitorRecord:
        """
        Add trade to monitoring.
        
        Args:
            trade_id: Trade identifier
            symbol: Stock symbol
            side: BUY or SELL
            entry_price: Entry price
            entry_quantity: Quantity of shares
            stop_loss: Stop-loss price
            take_profit: Take-profit price
            
        Returns:
            TradeMonitorRecord
        """
        record = TradeMonitorRecord(
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            entry_quantity=entry_quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        
        self.open_trades[trade_id] = record
        return record
    
    def update_price(self, trade_id: str, current_price: float) -> Optional[Dict]:
        """
        Update trade price and check for SL/TP triggers.
        
        Args:
            trade_id: Trade to update
            current_price: Current market price
            
        Returns:
            Trigger dict if SL/TP hit, None otherwise
        """
        if trade_id not in self.open_trades:
            return None
        
        record = self.open_trades[trade_id]
        triggered_state = record.check_sl_tp(current_price)
        
        if triggered_state:
            # Move to closed
            self.closed_trades[trade_id] = record
            del self.open_trades[trade_id]
            
            # Record trigger
            trigger = {
                "trade_id": trade_id,
                "symbol": record.symbol,
                "trigger_type": triggered_state.value,
                "trigger_price": current_price,
                "triggered_at": datetime.utcnow().isoformat(),
                "pnl": record.realized_pnl,
                "pnl_pct": (record.realized_pnl / (record.entry_price * record.entry_quantity) * 100) if record.entry_price > 0 else 0.0,
            }
            self.sl_tp_triggers.append(trigger)
            return trigger
        
        return None
    
    def get_trade_status(self, trade_id: str) -> Optional[Dict]:
        """Get status of a specific trade."""
        if trade_id in self.open_trades:
            return self.open_trades[trade_id].to_dict()
        elif trade_id in self.closed_trades:
            return self.closed_trades[trade_id].to_dict()
        return None
    
    def get_open_trades(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get all open trades.
        
        Args:
            symbol: Filter by symbol (optional)
            
        Returns:
            List of trade dicts
        """
        trades = list(self.open_trades.values())
        
        if symbol:
            trades = [t for t in trades if t.symbol == symbol]
        
        return [t.to_dict() for t in trades]
    
    def get_closed_trades(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get all closed trades."""
        trades = list(self.closed_trades.values())
        
        if symbol:
            trades = [t for t in trades if t.symbol == symbol]
        
        return [t.to_dict() for t in trades]
    
    def get_portfolio_stats(self) -> Dict:
        """Get portfolio-wide stats from monitored trades."""
        open_records = list(self.open_trades.values())
        closed_records = list(self.closed_trades.values())
        
        # Calculate totals
        total_unrealized = sum(t.unrealized_pnl for t in open_records)
        total_realized = sum(t.realized_pnl for t in closed_records)
        total_pnl = total_unrealized + total_realized
        
        # Count by side
        long_trades = len([t for t in open_records if t.side == "BUY"])
        short_trades = len([t for t in open_records if t.side == "SELL"])
        
        # Winning trades
        winning_closed = len([t for t in closed_records if t.realized_pnl > 0])
        losing_closed = len([t for t in closed_records if t.realized_pnl < 0])
        
        winning_open = len([t for t in open_records if t.unrealized_pnl > 0])
        losing_open = len([t for t in open_records if t.unrealized_pnl < 0])
        
        # Triggers
        sl_hits = len([t for t in self.sl_tp_triggers if t["trigger_type"] == "sl_hit"])
        tp_hits = len([t for t in self.sl_tp_triggers if t["trigger_type"] == "tp_hit"])
        
        return {
            "open_position_count": len(open_records),
            "closed_position_count": len(closed_records),
            "long_positions": long_trades,
            "short_positions": short_trades,
            "total_unrealized_pnl": total_unrealized,
            "total_realized_pnl": total_realized,
            "total_pnl": total_pnl,
            "winning_closed": winning_closed,
            "losing_closed": losing_closed,
            "winning_open": winning_open,
            "losing_open": losing_open,
            "win_rate": winning_closed / (winning_closed + losing_closed) if (winning_closed + losing_closed) > 0 else 0.0,
            "sl_hits": sl_hits,
            "tp_hits": tp_hits,
            "total_triggers": len(self.sl_tp_triggers),
        }
    
    def get_sl_tp_triggers(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get all SL/TP triggers."""
        triggers = list(self.sl_tp_triggers)
        
        if symbol:
            triggers = [t for t in triggers if t["symbol"] == symbol]
        
        return triggers
