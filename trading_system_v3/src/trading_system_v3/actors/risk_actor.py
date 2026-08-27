"""RiskActor: isolated agent that approves/resizes/rejects proposals
against a risk policy, with its own private cooldown/circuit-breaker
memory. Reachable only via ``RiskRequest`` -> ``RiskResponse`` and
``RiskOutcomeNotification`` (told about a realized loss after the fact,
so it can start a cooldown -- it never reads PortfolioStore or
StrategyActor directly)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading_system_v3.actors.base import IsolatedActor
from trading_system_v3.core.models import (
    Action,
    RiskDecision,
    RiskOutcomeNotification,
    RiskRequest,
    RiskResponse,
    TradeProposal,
)
from trading_system_v3.memory.store import MemoryStore


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


class RiskActor(IsolatedActor):
    def __init__(self, memory_db_path: str, policy: RiskPolicy | None = None) -> None:
        super().__init__(name="risk_actor")
        self.policy = policy or RiskPolicy()
        self._memory = MemoryStore(memory_db_path)

    async def handle(self, request):  # noqa: ANN001
        if isinstance(request, RiskRequest):
            return await self._handle_request(request)
        if isinstance(request, RiskOutcomeNotification):
            return await self._handle_outcome(request)
        raise TypeError(f"RiskActor cannot handle {type(request)!r}")

    def _in_cooldown(self, symbol: str) -> bool:
        until = self._memory.cooldown_until(symbol)
        return until is not None and datetime.now(timezone.utc) < until

    async def _handle_outcome(self, request: RiskOutcomeNotification) -> RiskResponse:
        if request.realized_pnl < 0:
            until = datetime.now(timezone.utc) + timedelta(minutes=self.policy.cooldown_minutes_after_loss)
            self._memory.set_cooldown(request.symbol, until, reason="loss_on_close")
        ack_proposal = TradeProposal(symbol=request.symbol, action=Action.HOLD, confidence=0.0, proposed_by="system")
        return RiskResponse(decision=RiskDecision(
            symbol=request.symbol, action=Action.HOLD, approved=False, reason="outcome noted",
            original_proposal=ack_proposal,
        ))

    async def _handle_request(self, request: RiskRequest) -> RiskResponse:
        p = self.policy
        proposal = request.proposal

        def reject(reason: str, log_event: str | None = None) -> RiskResponse:
            if log_event is not None:
                self._memory.record_risk_event(proposal.symbol, log_event, reason)
            return RiskResponse(decision=RiskDecision(
                symbol=proposal.symbol, action=proposal.action, approved=False,
                reason=reason, original_proposal=proposal,
            ))

        if proposal.action == Action.HOLD:
            return RiskResponse(decision=RiskDecision(
                symbol=proposal.symbol, action=Action.HOLD, approved=False,
                reason="Proposal is HOLD", original_proposal=proposal,
            ))

        if request.starting_equity_today > 0:
            daily_loss_pct = -request.realized_pnl_today / request.starting_equity_today
            if daily_loss_pct >= p.max_daily_loss_pct:
                return reject(
                    f"Daily loss circuit breaker triggered ({daily_loss_pct:.2%} >= {p.max_daily_loss_pct:.2%})",
                    log_event="circuit_breaker",
                )

        if proposal.action == Action.SELL:
            pos = request.current_position
            if pos is None or pos.quantity <= 0:
                return reject(f"No open position to sell for {proposal.symbol}")
            return RiskResponse(decision=RiskDecision(
                symbol=proposal.symbol, action=Action.SELL, approved=True,
                reason="Sell approved", quantity=pos.quantity, original_proposal=proposal,
            ))

        # BUY path
        if self._in_cooldown(proposal.symbol):
            return reject(f"{proposal.symbol} is in post-loss cooldown")
        if proposal.confidence < p.min_confidence:
            return reject(f"Confidence {proposal.confidence:.2f} below threshold {p.min_confidence:.2f}")
        if request.current_position is not None and request.current_position.quantity > 0:
            return reject(f"Already holding a position in {proposal.symbol}")
        if request.open_position_count >= p.max_positions:
            return reject(f"Max concurrent positions reached ({p.max_positions})")

        target_weight = min(proposal.target_weight, p.max_position_weight)
        if target_weight <= 0 or request.price <= 0:
            return reject("Target weight or price invalid")

        notional = request.equity * target_weight
        quantity = round(notional / request.price, 4)
        if quantity <= 0:
            return reject("Computed quantity is zero")

        stop_pct = proposal.stop_loss_pct or p.default_stop_loss_pct
        stop_price = request.price * (1 - stop_pct)

        return RiskResponse(decision=RiskDecision(
            symbol=proposal.symbol, action=Action.BUY, approved=True,
            reason=f"Approved at {target_weight:.2%} target weight",
            quantity=quantity, order_type=proposal.order_type,
            limit_price=proposal.limit_price, stop_loss_price=stop_price,
            original_proposal=proposal,
        ))
