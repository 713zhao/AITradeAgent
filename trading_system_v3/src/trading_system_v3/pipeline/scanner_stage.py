"""ScannerStage: config-driven candidate symbol universe."""
from __future__ import annotations


class ScannerStage:
    def __init__(self, universe: list[str], limit: int | None = None) -> None:
        self._universe = universe
        self._limit = limit

    async def scan(self) -> list[str]:
        return self._universe[: self._limit] if self._limit else list(self._universe)
