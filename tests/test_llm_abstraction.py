"""Tests for LLM abstraction layer."""
import pytest
import os
from unittest.mock import MagicMock, patch
from finance_service.llm import LLMConfig, LLMResponse, LLMManager, OpenRouterProvider


class TestLLMConfig:
    """Test LLM configuration"""

    def test_default_values(self):
        config = LLMConfig(provider="openrouter", api_key_env="TEST_KEY")
        assert config.provider == "openrouter"
        assert config.temperature == 0.3
        assert config.max_retries == 3

    def test_environment_loading(self):
        os.environ["TEST_API_KEY"] = "secret123"
        config = LLMConfig(provider="openrouter", api_key_env="TEST_API_KEY")
        assert config._api_key == "secret123"


class TestLLMProviderMock:
    """Test with mocked provider"""

    @patch("finance_service.llm.OpenRouterProvider._init_client")
    def test_openrouter_validate(self, mock_init):
        """Test OpenRouter connection validation (mocked)"""
        config = LLMConfig(provider="openrouter", api_key_env="FAKE_KEY")
        provider = OpenRouterProvider(config)
        # Mock validate
        provider.validate_connection = MagicMock(return_value=True)
        assert provider.validate_connection() is True

    @patch("finance_service.llm.OpenRouterProvider._init_client")
    async def test_openrouter_generate(self, mock_init):
        """Test LLM generate (mocked response)"""
        from unittest.mock import AsyncMock
        config = LLMConfig(provider="openrouter", api_key_env="FAKE_KEY", default_model="test-model")
        provider = OpenRouterProvider(config)
        
        # Mock the client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello world"))]
        mock_response.model = "test-model"
        mock_response.usage = MagicMock(total_tokens=10)
        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = mock_response
        provider._client = mock_client
        
        result = await provider.generate_async("Test prompt")
        assert result.content == "Hello world"
        assert result.model == "test-model"


class TestLLMCache:
    """Test response caching"""

    def test_cache_set_get(self, tmp_path):
        from finance_service.llm import LLMCache
        cache = LLMCache(cache_dir=str(tmp_path))
        
        resp = LLMResponse(
            content="cached",
            model="test",
            tokens_used=5,
            latency_ms=100,
        )
        resp.timestamp = pytest.importorskip("datetime").datetime.now()
        
        cache.set("prompt", "system", "model", 0.3, resp)
        cached = cache.get("prompt", "system", "model", 0.3)
        assert cached is not None
        assert cached.content == "cached"
        assert cached.cached is True


class TestLLMManager:
    """Test LLM manager with mocks"""

    @patch("finance_service.llm.LLMFactory.create")
    def test_manager_generate(self, mock_factory):
        mock_provider = MagicMock()
        mock_provider.generate_async = MagicMock(return_value=LLMResponse(
            content="test", model="m", tokens_used=1, latency_ms=1
        ))
        mock_factory.return_value = mock_provider

        config = LLMConfig(provider="openrouter", api_key_env="FAKE")
        manager = LLMManager(config)
        result = manager.generate("test prompt")
        assert result.content == "test"

    def test_stats(self):
        config = LLMConfig(provider="openrouter", api_key_env="FAKE")
        # Use dummy provider that does nothing
        manager = LLMManager(config)
        assert manager.get_stats()["requests"] == 0
