"""LLM abstraction layer for optional AI augmentation.

Provides a unified interface to multiple LLM providers (OpenRouter, OpenAI, Anthropic, Ollama).
All LLM features are opt-in via configuration; defaults to no-op if disabled.
"""
import os
import json
import logging
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Standardized LLM response"""
    content: str
    model: str
    tokens_used: int
    latency_ms: float
    cached: bool = False
    raw_response: Optional[Any] = None


@dataclass
class LLMConfig:
    """Configuration for LLM provider"""
    provider: str  # "openrouter", "openai", "anthropic", "ollama"
    api_key_env: str  # Environment variable name containing API key
    base_url: Optional[str] = None
    default_model: str = "gpt-4o-mini"
    temperature: float = 0.3
    max_tokens: int = 2000
    timeout: int = 30
    max_retries: int = 3


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._api_key = self._load_api_key()

    def _load_api_key(self) -> str:
        """Load API key from environment"""
        api_key = os.getenv(self.config.api_key_env, "")
        if not api_key:
            logger.warning(f"API key not found in env var {self.config.api_key_env}")
        return api_key

    @abstractmethod
    async def generate_async(self, prompt: str, system_prompt: Optional[str] = None,
                           temperature: Optional[float] = None, model: Optional[str] = None) -> LLMResponse:
        """Generate text asynchronously"""
        pass

    def generate_sync(self, prompt: str, system_prompt: Optional[str] = None,
                     temperature: Optional[float] = None, model: Optional[str] = None) -> LLMResponse:
        """Generate text synchronously (wrapper around async for simplicity)"""
        import asyncio
        return asyncio.run(self.generate_async(prompt, system_prompt, temperature, model))

    @abstractmethod
    def validate_connection(self) -> bool:
        """Test connection to provider"""
        pass


class OpenRouterProvider(LLMProvider):
    """OpenRouter.ai provider (unified access to multiple models)"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None
        self._init_client()

    def _init_client(self):
        """Initialize HTTP client (lazy)"""
        try:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self.config.base_url or "https://openrouter.ai/api/v1",
                timeout=self.config.timeout,
            )
        except ImportError:
            logger.error("openai package required for OpenRouter provider")
            raise

    async def generate_async(self, prompt: str, system_prompt: Optional[str] = None,
                           temperature: Optional[float] = None, model: Optional[str] = None) -> LLMResponse:
        import time
        start = time.time()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self._client.chat.completions.create(
                model=model or self.config.default_model,
                messages=messages,
                temperature=temperature or self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
            latency = (time.time() - start) * 1000

            return LLMResponse(
                content=response.choices[0].message.content,
                model=response.model,
                tokens_used=response.usage.total_tokens if response.usage else 0,
                latency_ms=latency,
                raw_response=response,
            )
        except Exception as e:
            logger.error(f"OpenRouter API error: {e}")
            raise

    def validate_connection(self) -> bool:
        try:
            import requests
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            # Simple models list request to test auth
            resp = requests.get(
                "https://openrouter.ai/api/v1/models",
                headers=headers,
                timeout=10,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"OpenRouter connection test failed: {e}")
            return False


class OpenAIProvider(LLMProvider):
    """OpenAI provider (GPT-4o, GPT-4o-mini, etc.)"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None
        self._init_client()

    def _init_client(self):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self.config.base_url,  # Allow custom base (Azure, etc.)
            timeout=self.config.timeout,
        )

    async def generate_async(self, prompt: str, system_prompt: Optional[str] = None,
                           temperature: Optional[float] = None, model: Optional[str] = None) -> LLMResponse:
        import time
        start = time.time()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=model or self.config.default_model,
            messages=messages,
            temperature=temperature or self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        latency = (time.time() - start) * 1000

        return LLMResponse(
            content=response.choices[0].message.content,
            model=response.model,
            tokens_used=response.usage.total_tokens if response.usage else 0,
            latency_ms=latency,
            raw_response=response,
        )

    def validate_connection(self) -> bool:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self._api_key)
            client.models.list(limit=1)
            return True
        except Exception as e:
            logger.error(f"OpenAI connection test failed: {e}")
            return False


class AnthropicProvider(LLMProvider):
    """Anthropic provider (Claude)"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None
        self._init_client()

    def _init_client(self):
        import anthropic
        self._client = anthropic.AsyncAnthropic(api_key=self._api_key)

    async def generate_async(self, prompt: str, system_prompt: Optional[str] = None,
                           temperature: Optional[float] = None, model: Optional[str] = None) -> LLMResponse:
        import time
        start = time.time()

        try:
            response = await self._client.messages.create(
                model=model or self.config.default_model,
                max_tokens=self.config.max_tokens,
                system=system_prompt or "",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature or self.config.temperature,
            )
            latency = (time.time() - start) * 1000

            content = response.content[0].text if response.content else ""
            return LLMResponse(
                content=content,
                model=response.model,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                latency_ms=latency,
                raw_response=response,
            )
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise

    def validate_connection(self) -> bool:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self._api_key)
            client.messages.count_tokens(model="claude-3-haiku-20240307", max_tokens=1)
            return True
        except Exception as e:
            logger.error(f"Anthropic connection test failed: {e}")
            return False


class GeminiProvider(LLMProvider):
    """Google Gemini provider"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None
        self._init_client()

    def _init_client(self):
        import google.generativeai as genai
        genai.configure(api_key=self._api_key)
        self._genai = genai

    async def generate_async(self, prompt: str, system_prompt: Optional[str] = None,
                           temperature: Optional[float] = None, model: Optional[str] = None) -> LLMResponse:
        import time
        start = time.time()

        model_name = model or self.config.default_model
        genai_model = self._genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_prompt if system_prompt else None
        )

        try:
            response = await genai_model.generate_content_async_enhanced(
                prompt,
                generation_config=self._genai.types.GenerationConfig(
                    temperature=temperature or self.config.temperature,
                    max_output_tokens=self.config.max_tokens,
                )
            )
        except AttributeError:
            # Fallback if generate_content_async_enhanced not available
            response = await genai_model.generate_content_async(
                prompt,
                generation_config=self._genai.types.GenerationConfig(
                    temperature=temperature or self.config.temperature,
                    max_output_tokens=self.config.max_tokens,
                )
            )

        latency = (time.time() - start) * 1000

        content = response.text if hasattr(response, 'text') else ""
        tokens_used = 0
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            tokens_used = response.usage_metadata.total_token_count

        return LLMResponse(
            content=content,
            model=model_name,
            tokens_used=tokens_used,
            latency_ms=latency,
            raw_response=response,
        )

    def validate_connection(self) -> bool:
        try:
            import google.generativeai as genai
            genai.configure(api_key=self._api_key)
            # Simple test: list models (limited free tier, so we just check auth)
            models = genai.list_models()
            return any(m for m in models if "generateContent" in m.supported_generation_methods)
        except Exception as e:
            logger.error(f"Gemini connection test failed: {e}")
            return False


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.base_url = self.config.base_url or "http://localhost:11434"

    async def generate_async(self, prompt: str, system_prompt: Optional[str] = None,
                           temperature: Optional[float] = None, model: Optional[str] = None) -> LLMResponse:
        import time
        import aiohttp

        start = time.time()
        model_name = model or self.config.default_model

        # Build Ollama API payload
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature or self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.config.timeout,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"Ollama error {resp.status}: {text}")
                data = await resp.json()

        latency = (time.time() - start) * 1000
        content = data.get("response", "")
        total_duration = data.get("total_duration", 0)

        return LLMResponse(
            content=content,
            model=model_name,
            tokens_used=data.get("eval_count", 0),
            latency_ms=latency,
            raw_response=data,
        )

    def validate_connection(self) -> bool:
        try:
            import requests
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Ollama connection test failed: {e}")
            return False


class LLMFactory:
    """Factory for creating LLM providers"""

    _PROVIDERS = {
        "openrouter": OpenRouterProvider,
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "ollama": OllamaProvider,
        "google": GeminiProvider,
    }

    @classmethod
    def create(cls, config: LLMConfig) -> LLMProvider:
        """Create LLM provider instance"""
        provider_class = cls._PROVIDERS.get(config.provider.lower())
        if not provider_class:
            raise ValueError(f"Unsupported LLM provider: {config.provider}")
        return provider_class(config)

    @classmethod
    def list_providers(cls) -> List[str]:
        """List available providers"""
        return list(cls._PROVIDERS.keys())


class LLMCache:
    """Simple in-memory + disk cache for LLM responses (24h TTL)"""

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir or os.path.join(os.getenv("STORAGE_DIR", "storage"), "llm_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self._memory_cache: Dict[str, LLMResponse] = {}

    def _cache_key(self, prompt: str, system: Optional[str], model: str, temperature: float) -> str:
        import hashlib
        content = f"{prompt}|||{system or ''}|||{model}|||{temperature:.2f}"
        return hashlib.md5(content.encode()).hexdigest()

    def get(self, prompt: str, system: Optional[str], model: str, temperature: float) -> Optional[LLMResponse]:
        key = self._cache_key(prompt, system, model, temperature)

        # Check memory first
        if key in self._memory_cache:
            resp = self._memory_cache[key]
            # Check TTL (24h)
            if hasattr(resp, 'timestamp') and (datetime.now() - resp.timestamp).total_seconds() < 86400:
                resp.cached = True
                return resp
            else:
                del self._memory_cache[key]

        # Check disk
        cache_file = os.path.join(self.cache_dir, f"{key}.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                # Check age
                ts = datetime.fromisoformat(data.get('timestamp', ''))
                if (datetime.now() - ts).total_seconds() < 86400:
                    resp = LLMResponse(**{k: v for k, v in data.items() if k != 'timestamp'})
                    resp.cached = True
                    self._memory_cache[key] = resp
                    return resp
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")

        return None

    def set(self, prompt: str, system: Optional[str], model: str, temperature: float, response: LLMResponse):
        key = self._cache_key(prompt, system, model, temperature)
        response.timestamp = datetime.now()
        self._memory_cache[key] = response

        # Save to disk
        cache_file = os.path.join(self.cache_dir, f"{key}.json")
        try:
            data = asdict(response)
            if hasattr(response, 'timestamp'):
                data['timestamp'] = response.timestamp.isoformat()
            with open(cache_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to write cache: {e}")


class LLMManager:
    """Main entry point for LLM operations with caching and fallback support"""

    def __init__(self, config: LLMConfig, cache: Optional[LLMCache] = None):
        self.config = config
        self.provider = LLMFactory.create(config)
        self.cache = cache or LLMCache()
        self._stats = {
            "requests": 0,
            "cache_hits": 0,
            "errors": 0,
        }

    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 temperature: Optional[float] = None, model: Optional[str] = None,
                 use_cache: bool = True) -> LLMResponse:
        """Generate with caching"""
        self._stats["requests"] += 1

        # Check cache
        if use_cache:
            cached = self.cache.get(prompt, system_prompt, model or self.config.default_model,
                                  temperature or self.config.temperature)
            if cached:
                self._stats["cache_hits"] += 1
                logger.debug("LLM cache hit")
                return cached

        # Generate
        try:
            import asyncio
            response = asyncio.run(self.provider.generate_async(
                prompt, system_prompt, temperature, model
            ))
            # Cache successful responses
            if use_cache and response.content:
                self.cache.set(prompt, system_prompt, model or self.config.default_model,
                             temperature or self.config.temperature, response)
            return response
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"LLM generation failed: {e}")
            raise

    def get_stats(self) -> Dict[str, Any]:
        """Get usage statistics"""
        return {
            **self._stats,
            "hit_rate": self._stats["cache_hits"] / max(1, self._stats["requests"]),
        }

    def validate(self) -> bool:
        """Test provider connection"""
        try:
            return self.provider.validate_connection()
        except Exception as e:
            logger.error(f"LLM validation failed: {e}")
            return False
