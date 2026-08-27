"""Isolated actor base class.

Each of StrategyActor, RiskActor, and LearningActor extends
``IsolatedActor``. An isolated actor:

- Runs its own ``asyncio.Task`` with a private inbox (``asyncio.Queue``).
  It is never called via a direct method call from the orchestrator or
  from another actor -- the *only* way to talk to it is
  ``await actor.ask(request)``, which enqueues an envelope and awaits a
  private ``asyncio.Future`` for the reply.
- Owns private state (an LLM client, a ``MemoryStore`` pointed at its own
  SQLite file) constructed in its own ``__init__``/``start`` and never
  handed out. No other actor or the orchestrator holds a reference to it.
  Two actors with the same *symbol* have completely disjoint memory --
  StrategyActor cannot read RiskActor's cooldown state and vice versa,
  which is deliberate: it forces every fact one actor needs from another
  to travel as an explicit message (see ``RiskOutcomeNotification`` and
  ``StrategyRequest`` in ``core/models.py``) instead of shared mutable
  state, and keeps each actor's context genuinely private.
- Processes one message at a time from its own inbox (no shared
  interpreter-level lock needed to keep its own state consistent) but
  never blocks the rest of the pipeline: other actors and the mechanical
  pipeline stages keep running concurrently while a slow LLM call is
  in flight inside one actor.

This is an in-process ``asyncio`` actor model, not separate OS processes.
See ``DESIGN.md`` for why, and for how this boundary could be promoted to
real process/subprocess isolation later without changing any call site,
since every request/response already crosses the boundary as a
serializable Pydantic model.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

Req = TypeVar("Req", bound=BaseModel)
Resp = TypeVar("Resp", bound=BaseModel)


class _Envelope(Generic[Req, Resp]):
    __slots__ = ("request", "future")

    def __init__(self, request: Req, future: "asyncio.Future[Resp]") -> None:
        self.request = request
        self.future = future


class IsolatedActor(ABC, Generic[Req, Resp]):
    """Base class for an isolated, message-only agent.

    Subclasses implement ``handle(request)`` and may set up private state
    (memory store, LLM client) in ``__init__``. That state must stay on
    ``self`` with no accessor the outside world can call -- the class
    intentionally exposes only ``start()``, ``ask()``, and ``stop()``.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._inbox: "asyncio.Queue[_Envelope]" = asyncio.Queue()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loop(), name=f"actor:{self.name}")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def ask(self, request: Req) -> Resp:
        """The only public entry point. Enqueues the request and awaits
        this actor's private processing of it."""
        if self._task is None or self._task.done():
            self.start()
        future: "asyncio.Future[Resp]" = asyncio.get_running_loop().create_future()
        await self._inbox.put(_Envelope(request, future))
        return await future

    async def _run_loop(self) -> None:
        while True:
            envelope = await self._inbox.get()
            try:
                response = await self.handle(envelope.request)
                if not envelope.future.done():
                    envelope.future.set_result(response)
            except Exception as exc:  # noqa: BLE001 - isolate failures per actor
                logger.exception("%s failed handling %r", self.name, envelope.request)
                if not envelope.future.done():
                    envelope.future.set_exception(exc)

    @abstractmethod
    async def handle(self, request: Req) -> Resp:
        """Process one request against this actor's private state."""
        raise NotImplementedError
