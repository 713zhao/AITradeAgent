"""Data models for trading system"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import json

@dataclass
class Position:
    """Represents a stock position"""
    symbol: str
    qty: float
    avg_cost: float
    current_price: float
    
    @property
    def market_value(self) -> float:
        return self.qty * self.current_price
    
    @property
    def cost_basis(self) -> float:
        return self.qty * self.avg_cost
    
    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.cost_basis
    
    @property
    def unrealized_pnl_pct(self) -> float:
        if self.cost_basis == 0:
            return 0
        return (self.unrealized_pnl / self.cost_basis) * 100

@dataclass
class Trade:
    """Represents a trade execution"""
    task_id: str
    symbol: str
    action: str  # BUY, SELL
    qty: float
    price: float
    timestamp: str
    approval_id: Optional[str] = None
    approved: bool = False
    
    @property
    def value(self) -> float:
        return self.qty * self.price

@dataclass
class Signal:
    """Technical indicator signal"""
    indicator: str
    value: float
    threshold: float
    signal: str  # BUY, SELL, HOLD, NEUTRAL
    timestamp: Optional[str] = None

@dataclass
@dataclass
class Decision:
    """Trading decision output"""
    symbol: str
    decision: str  # BUY, SELL, HOLD
    confidence: float
    signals: List[str]
    timestamp: datetime = None
    task_id: str = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position: Dict[str, Any] = None
    risk: Dict[str, Any] = None
    rationale: List[str] = None
    required_approval: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'symbol': self.symbol,
            'decision': self.decision,
            'confidence': self.confidence,
            'signals': self.signals,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'task_id': self.task_id,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'required_approval': self.required_approval
        }
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class PortfolioSnapshot:
    """Point-in-time portfolio state"""
    timestamp: str
    cash: float
    equity: float
    positions: Dict[str, Position]
    
    @property
    def total_value(self) -> float:
        return self.cash + sum(p.market_value for p in self.positions.values())
    
    @property
    def exposure_pct(self) -> float:
        if self.total_value == 0:
            return 0
        return sum(p.market_value for p in self.positions.values()) / self.total_value


def signal_to_dict(signal: Signal) -> Dict[str, Any]:
    """Convert Signal to dictionary"""
    return asdict(signal)

def decision_to_dict(decision: Decision) -> Dict[str, Any]:
    """Convert Decision to dictionary"""
    return asdict(decision)
