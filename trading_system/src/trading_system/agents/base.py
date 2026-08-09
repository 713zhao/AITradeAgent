from __future__ import annotations

import abc

from trading_system.core.models import AgentReport


class Agent(abc.ABC):
    """Common contract for every agent. Mirrors the baseline's Agent ABC."""

    @property
    @abc.abstractmethod
    def agent_id(self) -> str: ...

    @property
    @abc.abstractmethod
    def goal(self) -> str: ...

    @abc.abstractmethod
    async def run(self, *args, **kwargs) -> AgentReport: ...
