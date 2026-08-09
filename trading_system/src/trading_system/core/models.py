"""Core data models shared across all agents.

Kept deliberately small and explicit (pydantic dataclasses) so every agent
boundary has a typed, serializable contract instead of loose dicts, which
was one of the pain points in the AITradeAgent baseline (payload: Dict[str, Any]).
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class AgentReport(BaseModel):
    """Uniform envelope every agent returns, mirroring the baseline's
    AgentReport but with a typed payload field per report kind instead of
    an untyped dict, while still allowing pass-through extras."""

    agent_id: str
    status: str  # success | failure | info | opportunity | rejected
    message: str
    timestamp: datetime = Field(default_factory=utcnow)
    payload: dict[str, Any] = Field(default_factory=dict)


class Bar(BaseModel):
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class OHLCV(BaseModel):
    symbol: str
    interval: str
    bars: list[Bar]

    def closes(self) -> list[float]:
        return [b.close for b in self.bars]

    @property
    def last_close(self) -> float:
        if not self.bars:
            raise ValueError(f"No bars for {self.symbol}")
        return self.bars[-1].close


class IndicatorSet(BaseModel):
    symbol: str
    as_of: datetime
    price: float
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    atr_14: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    pct_change_5d: Optional[float] = None
    pct_change_20d: Optional[float] = None


class TradeProposal(BaseModel):
    symbol: str
    action: Action
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    target_weight: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Fraction of portfolio equity this position should target if approved",
    )
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    proposed_by: str = "strategy_agent"


class RiskDecision(BaseModel):
    symbol: str
    action: Action
    approved: bool
    reason: str
    quantity: float = 0.0
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    original_proposal: TradeProposal


class ExecutionResult(BaseModel):
    symbol: str
    action: Action
    quantity: float
    requested_price: float
    filled_price: float
    commission: float
    slippage: float
    status: str  # filled | rejected | error
    order_id: str
    timestamp: datetime = Field(default_factory=utcnow)


class Position(BaseModel):
    symbol: str
    quantity: float
    avg_price: float
    stop_loss_price: Optional[float] = None

    def market_value(self, price: float) -> float:
        return self.quantity * price

    def unrealized_pnl(self, price: float) -> float:
        return (price - self.avg_price) * self.quantity


class PortfolioState(BaseModel):
    cash: float
    positions: dict[str, Position] = Field(default_factory=dict)
    realized_pnl: float = 0.0
    equity_history: list[tuple[datetime, float]] = Field(default_factory=list)

    def equity(self, prices: dict[str, float]) -> float:
        total = self.cash
        for sym, pos in self.positions.items():
            total += pos.market_value(prices.get(sym, pos.avg_price))
        return total
