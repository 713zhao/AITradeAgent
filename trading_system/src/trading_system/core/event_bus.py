"""Async pub/sub event bus.

Simplified and hardened relative to the AITradeAgent baseline's EventBus:
- Each handler gets its own timeout + exception isolation (a hung/broken
  handler cannot block or corrupt delivery to other subscribers).
- No global retry-storm logic (the baseline recreated and re-awaited all
  tasks for an event on timeout, which can duplicate side effects like
  trade execution). Here a handler that isn't done in time is cancelled
  and logged once.
- publish() awaits dispatch directly (still concurrent across handlers)
  instead of firing an untracked background task, so callers can know
  when a publish has actually finished and tests are deterministic.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, DefaultDict

logger = logging.getLogger(__name__)

Handler = Callable[["Event"], Awaitable[None]]


@dataclass
class Event:
    event_type: str
    data: dict[str, Any] = field(default_factory=dict)
    source: str = "system"
    timestamp: datetime = field(default_factory=datetime.utcnow)


class EventBus:
    def __init__(self, handler_timeout: float = 60.0, history_limit: int = 2000) -> None:
        self._subscribers: DefaultDict[str, list[Handler]] = defaultdict(list)
        self._history: list[Event] = []
        self._history_limit = history_limit
        self._handler_timeout = handler_timeout

    def subscribe(self, event_type: str, handler: Handler) -> None:
        self._subscribers[event_type].append(handler)

    async def publish(self, event: Event) -> None:
        self._history.append(event)
        if len(self._history) > self._history_limit:
            self._history = self._history[-self._history_limit:]

        handlers = list(self._subscribers.get(event.event_type, []))
        if not handlers:
            logger.debug("No subscribers for %s", event.event_type)
            return

        async def _run(handler: Handler) -> None:
            try:
                await asyncio.wait_for(handler(event), timeout=self._handler_timeout)
            except asyncio.TimeoutError:
                logger.error("Handler %s timed out on %s", handler, event.event_type)
            except Exception:
                logger.exception("Handler %s failed on %s", handler, event.event_type)

        await asyncio.gather(*(_run(h) for h in handlers))

    def history(self, event_type: str | None = None, limit: int = 100) -> list[Event]:
        items = self._history if event_type is None else [e for e in self._history if e.event_type == event_type]
        return items[-limit:]


class Events:
    MARKET_SCAN_REQUESTED = "market_scan_requested"
    MARKET_SCANNED = "market_scanned"
    DATA_FETCH_COMPLETE = "data_fetch_complete"
    ANALYSIS_COMPLETE = "analysis_complete"
    TRADE_PROPOSAL_GENERATED = "trade_proposal_generated"
    RISK_DECISION_MADE = "risk_decision_made"
    TRADE_EXECUTED = "trade_executed"
    PORTFOLIO_UPDATED = "portfolio_updated"
    PIPELINE_ERROR = "pipeline_error"
