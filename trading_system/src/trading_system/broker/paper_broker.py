"""PaperBroker: simulated fills with slippage + commission, no external I/O.

Kept separate from ExecutionAgent so a real broker adapter (Alpaca paper
trading REST API, etc.) can implement the same Protocol later without
touching agent logic.
"""
from __future__ import annotations

import uuid
from typing import Protocol

from trading_system.core.models import Action, OrderType


class BrokerFill:
    def __init__(self, filled_price: float, commission: float, slippage: float, order_id: str) -> None:
        self.filled_price = filled_price
        self.commission = commission
        self.slippage = slippage
        self.order_id = order_id


class Broker(Protocol):
    def submit_order(
        self, symbol: str, action: Action, quantity: float, reference_price: float,
        order_type: OrderType, limit_price: float | None,
    ) -> BrokerFill: ...


class PaperBroker:
    def __init__(self, slippage_bps: float = 5.0, commission_bps: float = 1.0) -> None:
        self.slippage_bps = slippage_bps
        self.commission_bps = commission_bps

    def submit_order(
        self, symbol: str, action: Action, quantity: float, reference_price: float,
        order_type: OrderType = OrderType.MARKET, limit_price: float | None = None,
    ) -> BrokerFill:
        direction = 1 if action == Action.BUY else -1
        slip = reference_price * (self.slippage_bps / 10_000) * direction
        fill_price = reference_price + slip

        if order_type == OrderType.LIMIT and limit_price is not None:
            if action == Action.BUY and fill_price > limit_price:
                fill_price = limit_price
            elif action == Action.SELL and fill_price < limit_price:
                fill_price = limit_price

        commission = abs(quantity * fill_price) * (self.commission_bps / 10_000)
        return BrokerFill(
            filled_price=fill_price, commission=commission, slippage=abs(slip),
            order_id=f"PAPER-{uuid.uuid4().hex[:10]}",
        )
