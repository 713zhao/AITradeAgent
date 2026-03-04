"""Portfolio management and simulation"""
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from ..core.models import Position, Trade, PortfolioSnapshot
from ..core.config import Config

logger = logging.getLogger(__name__)

class Portfolio:
    """Simulated trading portfolio with accounting"""
    
    def __init__(self, initial_cash: float = Config.DEFAULT_INITIAL_CASH):
        self.cash = initial_cash
        self.starting_cash = initial_cash
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.snapshots: List[PortfolioSnapshot] = []
        self.realized_pnl = 0.0
        self.created_at = datetime.utcnow()
    
    @property
    def total_value(self) -> float:
        """Total portfolio value (cash + positions)"""
        position_value = sum(p.market_value for p in self.positions.values())
        return self.cash + position_value
    
    @property
    def equity(self) -> float:
        """Total equity (excluding cash)"""
        return sum(p.market_value for p in self.positions.values())
    
    @property
    def unrealized_pnl(self) -> float:
        """Sum of unrealized PnL across all positions"""
        return sum(p.unrealized_pnl for p in self.positions.values())
    
    @property
    def total_pnl(self) -> float:
        """Total PnL (realized + unrealized)"""
        return self.realized_pnl + self.unrealized_pnl
    
    @property
    def exposure_pct(self) -> float:
        """Percentage of portfolio in stocks"""
        if self.total_value == 0:
            return 0.0
        return self.equity / self.total_value
    
    @property
    def drawdown(self) -> float:
        """Current drawdown from peak"""
        if not self.snapshots:
            return 0.0
        
        peak_value = max(s.total_value for s in self.snapshots) if self.snapshots else self.starting_cash
        current_value = self.total_value
        
        if peak_value == 0:
            return 0.0
        return (peak_value - current_value) / peak_value
    
    def update_prices(self, prices: Dict[str, float]):
        """Update position prices (mark to market)"""
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol].current_price = price
    
    def buy(self, symbol: str, qty: float, price: float) -> Tuple[bool, str]:
        """
        Execute a buy trade
        
        Returns:
            (success, message)
        """
        cost = qty * price * (1 + Config.TRADE_SLIPPAGE)
        
        if cost > self.cash:
            return False, f"Insufficient cash. Need ${cost:.2f}, have ${self.cash:.2f}"
        
        self.cash -= cost
        
        if symbol in self.positions:
            pos = self.positions[symbol]
            new_avg_cost = (pos.avg_cost * pos.qty + price * qty) / (pos.qty + qty)
            pos.avg_cost = new_avg_cost
            pos.qty += qty
        else:
            self.positions[symbol] = Position(
                symbol=symbol,
                qty=qty,
                avg_cost=price,
                current_price=price
            )
        
        logger.info(f"BUY {qty} {symbol} @ ${price:.2f}")
        return True, f"Bought {qty} shares of {symbol} @ ${price:.2f}"
    
    def sell(self, symbol: str, qty: float, price: float) -> Tuple[bool, str]:
        """
        Execute a sell trade
        
        Returns:
            (success, message)
        """
        if symbol not in self.positions:
            return False, f"No position in {symbol}"
        
        pos = self.positions[symbol]
        if qty > pos.qty:
            return False, f"Cannot sell {qty}: only hold {pos.qty}"
        
        proceeds = qty * price * (1 - Config.TRADE_SLIPPAGE)
        pnl = (price - pos.avg_cost) * qty
        
        self.cash += proceeds
        self.realized_pnl += pnl
        
        if qty == pos.qty:
            del self.positions[symbol]
        else:
            pos.qty -= qty
        
        logger.info(f"SELL {qty} {symbol} @ ${price:.2f} (PnL: ${pnl:.2f})")
        return True, f"Sold {qty} shares of {symbol} @ ${price:.2f} (PnL: ${pnl:.2f})"
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position details"""
        return self.positions.get(symbol)
    
    def get_state(self) -> Dict:
        """Get full portfolio state"""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "cash": round(self.cash, 2),
            "equity": round(self.equity, 2),
            "total_value": round(self.total_value, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "total_pnl": round(self.total_pnl, 2),
            "pnl_pct": round((self.total_pnl / self.starting_cash) * 100, 2) if self.starting_cash > 0 else 0,
            "exposure_pct": round(self.exposure_pct * 100, 2),
            "drawdown_pct": round(self.drawdown * 100, 2),
            "positions": {
                symbol: {
                    "qty": pos.qty,
                    "avg_cost": round(pos.avg_cost, 2),
                    "current_price": round(pos.current_price, 2),
                    "market_value": round(pos.market_value, 2),
                    "cost_basis": round(pos.cost_basis, 2),
                    "unrealized_pnl": round(pos.unrealized_pnl, 2),
                    "unrealized_pnl_pct": round(pos.unrealized_pnl_pct, 2),
                }
                for symbol, pos in self.positions.items()
            }
        }
    
    def snapshot(self):
        """Take portfolio snapshot"""
        snap = PortfolioSnapshot(
            timestamp=datetime.utcnow().isoformat(),
            cash=self.cash,
            equity=self.equity,
            positions=self.positions.copy()
        )
        self.snapshots.append(snap)
        return snap
    
    def reset(self):
        """Reset portfolio to initial state"""
        self.cash = self.starting_cash
        self.positions.clear()
        self.trades.clear()
        self.realized_pnl = 0.0
        self.snapshots.clear()
