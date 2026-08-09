"""Minimal provider-agnostic LLM client for structured trading decisions.

Uses the OpenAI-compatible chat completions API (works with OpenAI,
and any OpenAI-compatible gateway/proxy by overriding base_url) and asks
for strict JSON output. No provider SDK lock-in beyond the `openai`
package's HTTP client, and it's injected as a Protocol so tests use a
fake implementation instead of a live API key.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    async def complete_json(self, system: str, user: str) -> dict[str, Any]: ...


class OpenAICompatibleClient:
    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)


class NullLLMClient:
    """Used when no API key is configured. Always raises so callers fall
    back to the deterministic rule strategy instead of silently guessing."""

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        raise RuntimeError("No LLM configured (NullLLMClient)")
