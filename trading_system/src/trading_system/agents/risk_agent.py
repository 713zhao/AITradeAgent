"""RiskAgent: applies portfolio-level and per-trade risk policy.

Improvements vs baseline RiskAgent: sizing is computed from *live*
portfolio equity and a target weight (not a fixed share count picked by
the strategy layer), a hard per-symbol exposure cap, a max concurrent
positions cap, a daily-loss circuit breaker, and a per-symbol cooldown
after a loss to avoid immediately re-entering a stopped-out name.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading_system.agents.base import Agent
from trading_system.core.models import (
    Action,
    AgentReport,
    OrderType,
    Position,
    RiskDecision,
    TradeProposal,
)


class RiskPolicy:
    def __init__(
        self,
        max_position_weight: float = 0.15,
        max_positions: int = 12,
        min_confidence: float = 0.55,
        max_daily_loss_pct: float = 0.03,
        cooldown_minutes_after_loss: int = 60,
        default_stop_loss_pct: float = 0.08,
    ) -> None:
        self.max_position_weight = max_position_weight
        self.max_positions = max_positions
        self.min_confidence = min_confidence
        self.max_daily_loss_pct = max_daily_loss_pct
        self.cooldown_minutes_after_loss = cooldown_minutes_after_loss
        self.default_stop_loss_pct = default_stop_loss_pct


class RiskAgent(Agent):
    def __init__(self, policy: RiskPolicy | None = None) -> None:
        self.policy = policy or RiskPolicy()
        self._cooldowns: dict[str, datetime] = {}

    @property
    def agent_id(self) -> str:
        return "risk_agent"

    @property
    def goal(self) -> str:
        return "Approve, resize, or reject trade proposals against risk policy"

    def register_loss(self, symbol: str) -> None:
        self._cooldowns[symbol] = datetime.now(timezone.utc) + timedelta(
            minutes=self.policy.cooldown_minutes_after_loss
        )

    def _in_cooldown(self, symbol: str) -> bool:
        until = self._cooldowns.get(symbol)
        return until is not None and datetime.now(timezone.utc) < until

    async def run(
        self,
        proposal: TradeProposal,
        equity: float,
        current_position: Position | None,
        open_position_count: int,
        realized_pnl_today: float,
        starting_equity_today: float,
        price: float,
    ) -> AgentReport:
        p = self.policy

        def reject(reason: str) -> AgentReport:
            decision = RiskDecision(
                symbol=proposal.symbol, action=proposal.action, approved=False,
                reason=reason, original_proposal=proposal,
            )
            return AgentReport(
                agent_id=self.agent_id, status="rejected", message=reason,
                payload={"decision": decision},
            )

        if proposal.action == Action.HOLD:
            decision = RiskDecision(
                symbol=proposal.symbol, action=Action.HOLD, approved=False,
                reason="Proposal is HOLD", original_proposal=proposal,
            )
            return AgentReport(
                agent_id=self.agent_id, status="info", message="HOLD - no action",
                payload={"decision": decision},
            )

        if starting_equity_today > 0:
            daily_loss_pct = -realized_pnl_today / starting_equity_today
            if daily_loss_pct >= p.max_daily_loss_pct:
                return reject(
                    f"Daily loss circuit breaker triggered ({daily_loss_pct:.2%} >= {p.max_daily_loss_pct:.2%})"
                )

        if proposal.action == Action.SELL:
            if current_position is None or current_position.quantity <= 0:
                return reject(f"No open position to sell for {proposal.symbol}")
            decision = RiskDecision(
                symbol=proposal.symbol, action=Action.SELL, approved=True,
                reason="Sell approved", quantity=current_position.quantity,
                original_proposal=proposal,
            )
            return AgentReport(
                agent_id=self.agent_id, status="success", message="Sell approved",
                payload={"decision": decision},
            )

        # BUY path
        if self._in_cooldown(proposal.symbol):
            return reject(f"{proposal.symbol} is in post-loss cooldown")
        if proposal.confidence < p.min_confidence:
            return reject(f"Confidence {proposal.confidence:.2f} below threshold {p.min_confidence:.2f}")
        if current_position is not None and current_position.quantity > 0:
            return reject(f"Already holding a position in {proposal.symbol}")
        if open_position_count >= p.max_positions:
            return reject(f"Max concurrent positions reached ({p.max_positions})")

        target_weight = min(proposal.target_weight, p.max_position_weight)
        if target_weight <= 0 or price <= 0:
            return reject("Target weight or price invalid")

        notional = equity * target_weight
        quantity = round(notional / price, 4)
        if quantity <= 0:
            return reject("Computed quantity is zero")

        stop_pct = proposal.stop_loss_pct or p.default_stop_loss_pct
        stop_price = price * (1 - stop_pct)

        decision = RiskDecision(
            symbol=proposal.symbol, action=Action.BUY, approved=True,
            reason=f"Approved at {target_weight:.2%} target weight",
            quantity=quantity, order_type=proposal.order_type,
            limit_price=proposal.limit_price, stop_loss_price=stop_price,
            original_proposal=proposal,
        )
        return AgentReport(
            agent_id=self.agent_id, status="success", message="Buy approved",
            payload={"decision": decision},
        )
