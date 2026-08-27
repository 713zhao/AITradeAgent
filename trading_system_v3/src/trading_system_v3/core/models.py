"""Core typed contracts shared across pipeline stages and isolated actors.

Every boundary in this system -- pipeline stage to pipeline stage, and
orchestrator to isolated actor -- passes one of these Pydantic models,
never a raw dict. That is what makes the actor mailboxes in
``actors/base.py`` a real message-passing boundary instead of just a
queue of opaque blobs: a StrategyActor only ever sees a
``StrategyRequest`` and only ever returns a ``StrategyResponse``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

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
    pct_change_5d: Optional[float] = None
    pct_change_20d: Optional[float] = None


class PositionSummary(BaseModel):
    """Read-only snapshot of a position, handed to actors instead of the
    live PortfolioStore object so they cannot mutate portfolio state
    directly -- only PortfolioActor/PortfolioAgent (the single writer)
    ever touches the ledger."""

    symbol: str
    quantity: float
    avg_price: float
    stop_loss_price: Optional[float] = None


class TradeProposal(BaseModel):
    symbol: str
    action: Action
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    target_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    proposed_by: str = "strategy_actor"
    decision_id: Optional[int] = None


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


# --------------------------------------------------------------------------
# Actor request/response contracts (StrategyActor / RiskActor / LearningActor)
# --------------------------------------------------------------------------


class StrategyRequest(BaseModel):
    indicators: IndicatorSet
    position: Optional[PositionSummary] = None


class StrategyResponse(BaseModel):
    proposal: TradeProposal
    decision_id: int


class RiskRequest(BaseModel):
    proposal: TradeProposal
    equity: float
    price: float
    current_position: Optional[PositionSummary] = None
    open_position_count: int = 0
    realized_pnl_today: float = 0.0
    starting_equity_today: float = 0.0


class RiskResponse(BaseModel):
    decision: RiskDecision


class RiskOutcomeNotification(BaseModel):
    """Fire-and-forget notification the orchestrator sends to RiskActor
    after a SELL fills, so its private cooldown/circuit-breaker state
    (which nothing outside RiskActor can see or mutate) reflects reality."""

    symbol: str
    realized_pnl: float


class ResolvedDecisionSummary(BaseModel):
    """Sanitized, read-only view of one of StrategyActor's own resolved
    decisions, handed out only through ``StrategyRecentOutcomesResponse``.
    LearningActor never sees StrategyActor's database -- only this."""

    decision_id: int
    symbol: str
    action: Action
    confidence: float
    reasoning: str
    outcome_pnl: float


class StrategyMarkExecutedRequest(BaseModel):
    """Tells StrategyActor to flip ``executed`` on its own private
    decision row once ExecutionStage/PortfolioStage have actually filled
    the trade. The orchestrator never writes to StrategyActor's DB."""

    decision_id: int


class StrategyMarkExecutedResponse(BaseModel):
    ok: bool = True


class StrategyOutcomeNotification(BaseModel):
    """Sent by the orchestrator to StrategyActor after a position closes,
    so StrategyActor can backfill outcome_pnl on its own private decision
    record. The orchestrator never writes to StrategyActor's database
    directly."""

    symbol: str
    realized_pnl: float


class StrategyRecentOutcomesRequest(BaseModel):
    """Ask StrategyActor for decisions resolved since its own private
    'last reviewed' watermark, advancing that watermark as a side
    effect. Used to feed LearningActor without exposing the database."""

    limit: int = 50


class StrategyRecentOutcomesResponse(BaseModel):
    decisions: list[ResolvedDecisionSummary] = Field(default_factory=list)


class StrategyAddLessonRequest(BaseModel):
    """LearningActor's output, relayed back into StrategyActor's private
    semantic memory by the orchestrator."""

    text: str
    source_decision_ids: list[int] = Field(default_factory=list)


class StrategyAddLessonResponse(BaseModel):
    lesson_id: int


class LearningRunRequest(BaseModel):
    resolved_decisions: list[ResolvedDecisionSummary] = Field(default_factory=list)


class LearningRunResponse(BaseModel):
    lessons: list[str] = Field(default_factory=list)
    message: str
