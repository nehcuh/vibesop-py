"""Test LLM module."""

import os

import pytest

from vibesop.llm import create_from_env, create_provider
from vibesop.llm.anthropic import AnthropicProvider
from vibesop.llm.base import LLMProvider, LLMResponse, ProviderStats
from vibesop.llm.factory import detect_provider_from_env
from vibesop.llm.openai import OpenAIProvider


class TestLLMResponse:
    """Test LLMResponse dataclass."""

    def test_create_response(self) -> None:
        """Test creating an LLM response."""
        response = LLMResponse(
            content="Hello!",
            model="claude-3-haiku",
            provider="anthropic",
            tokens_used=100,
        )

        assert response.content == "Hello!"
        assert response.model == "claude-3-haiku"
        assert response.provider == "anthropic"
        assert response.tokens_used == 100

    def test_create_response_without_tokens(self) -> None:
        """Test creating response without token count."""
        response = LLMResponse(
            content="Hi",
            model="gpt-4o-mini",
            provider="openai",
        )

        assert response.tokens_used is None


class TestProviderStats:
    """Test ProviderStats dataclass."""

    def test_create_stats(self) -> None:
        """Test creating provider stats."""
        stats = ProviderStats(
            provider_name="anthropic",
            configured=True,
            base_url="https://api.anthropic.com",
        )

        assert stats.provider_name == "anthropic"
        assert stats.configured is True
        assert stats.total_calls == 0
        assert stats.total_tokens == 0


class TestLLMProvider:
    """Test LLMProvider base class."""

    def test_provider_requires_implementation(self) -> None:
        """Test that call method raises NotImplementedError."""

        # Create a minimal implementation
        class DummyProvider(LLMProvider):
            @property
            def provider_name(self) -> str:
                return "dummy"

            def default_model(self) -> str:
                return "dummy-model"

            def call(
                self,
                prompt: str,
                model: str | None = None,
                max_tokens: int = 500,
                temperature: float = 0.3,
            ) -> LLMResponse:
                raise NotImplementedError

        provider = DummyProvider(api_key="test-key")

        with pytest.raises(NotImplementedError):
            provider.call("test")

    def test_configured_with_api_key(self) -> None:
        """Test configured checks API key length."""

        class DummyProvider(LLMProvider):
            @property
            def provider_name(self) -> str:
                return "dummy"

            def default_model(self) -> str:
                return "dummy-model"

            def call(
                self,
                prompt: str,
                model: str | None = None,
                max_tokens: int = 500,
                temperature: float = 0.3,
            ) -> LLMResponse:
                raise NotImplementedError

        provider = DummyProvider(api_key="sk-test-key-1234567890")
        assert provider.configured() is True

        provider = DummyProvider(api_key="short")
        assert provider.configured() is False

    def test_stats(self) -> None:
        """Test getting provider stats."""

        class DummyProvider(LLMProvider):
            @property
            def provider_name(self) -> str:
                return "dummy"

            def default_model(self) -> str:
                return "dummy-model"

            def call(
                self,
                prompt: str,
                model: str | None = None,
                max_tokens: int = 500,
                temperature: float = 0.3,
            ) -> LLMResponse:
                raise NotImplementedError

        provider = DummyProvider(api_key="test-key")
        stats = provider.stats()

        assert stats.provider_name == "dummy"
        assert stats.total_calls == 0


class TestFactory:
    """Test LLM provider factory."""

    def test_create_anthropic_provider(self) -> None:
        """Test creating Anthropic provider."""
        provider = create_provider("anthropic", api_key="test-key")

        assert isinstance(provider, AnthropicProvider)
        assert provider.provider_name == "Anthropic"

    def test_create_openai_provider(self) -> None:
        """Test creating OpenAI provider."""
        provider = create_provider("openai", api_key="test-key")

        assert isinstance(provider, OpenAIProvider)
        assert provider.provider_name == "OpenAI"

    def test_create_invalid_provider(self) -> None:
        """Test creating invalid provider raises error."""
        with pytest.raises(ValueError, match="Invalid provider"):
            create_provider("invalid")  # type: ignore

    def test_detect_provider_from_env(self) -> None:
        """Test provider detection from environment."""
        # Save original values
        old_anthropic = os.getenv("ANTHROPIC_API_KEY")
        old_openai = os.getenv("OPENAI_API_KEY")
        old_vibe = os.getenv("VIBE_LLM_PROVIDER")

        try:
            # Test with VIBE_LLM_PROVIDER
            os.environ["VIBE_LLM_PROVIDER"] = "anthropic"
            assert detect_provider_from_env() == "anthropic"

            # Test with ANTHROPIC_API_KEY
            del os.environ["VIBE_LLM_PROVIDER"]
            os.environ["ANTHROPIC_API_KEY"] = "test-key"
            assert detect_provider_from_env() == "anthropic"

            # Test with OPENAI_API_KEY
            del os.environ["ANTHROPIC_API_KEY"]
            os.environ["OPENAI_API_KEY"] = "test-key"
            assert detect_provider_from_env() == "openai"

            # Test default when no keys
            del os.environ["OPENAI_API_KEY"]
            assert detect_provider_from_env() == "anthropic"

        finally:
            # Restore original values
            if old_anthropic:
                os.environ["ANTHROPIC_API_KEY"] = old_anthropic
            if old_openai:
                os.environ["OPENAI_API_KEY"] = old_openai
            if old_vibe:
                os.environ["VIBE_LLM_PROVIDER"] = old_vibe
            elif "VIBE_LLM_PROVIDER" in os.environ:
                del os.environ["VIBE_LLM_PROVIDER"]


class TestCreateFromEnv:
    """Test create_from_env function."""

    def test_create_from_env_with_key(self) -> None:
        """Test creating provider with explicit key."""
        old_key = os.getenv("ANTHROPIC_API_KEY")
        try:
            os.environ["ANTHROPIC_API_KEY"] = "sk-test-key-1234567890"

            provider = create_from_env("anthropic")

            assert isinstance(provider, AnthropicProvider)
            assert provider.api_key == "sk-test-key-1234567890"

        finally:
            if old_key:
                os.environ["ANTHROPIC_API_KEY"] = old_key
            elif "ANTHROPIC_API_KEY" in os.environ:
                del os.environ["ANTHROPIC_API_KEY"]

    def test_create_from_env_auto_detect(self) -> None:
        """Test creating provider without key (auto-detect)."""
        provider = create_from_env()

        # Should return a provider even if not configured
        assert provider is not None
        # In this case, it will be unconfigured
        # (we don't have real API keys in test environment)

    def test_create_from_env_fallback(self) -> None:
        """Test fallback to other provider when preferred is unavailable."""
        old_anthropic = os.getenv("ANTHROPIC_API_KEY")
        old_openai = os.getenv("OPENAI_API_KEY")

        try:
            # Only OpenAI key available
            if "ANTHROPIC_API_KEY" in os.environ:
                del os.environ["ANTHROPIC_API_KEY"]

            # Use valid OpenAI key length (>= 40 chars)
            os.environ["OPENAI_API_KEY"] = "sk-test-key-" + "x" * 35

            provider = create_from_env("anthropic")

            # Should fallback to OpenAI since Anthropic has no key
            assert isinstance(provider, OpenAIProvider)

        finally:
            # Restore
            if old_anthropic or "ANTHROPIC_API_KEY" in os.environ:
                os.environ["ANTHROPIC_API_KEY"] = old_anthropic  # type: ignore[assignment]
            if old_openai:
                os.environ["OPENAI_API_KEY"] = old_openai
            elif "OPENAI_API_KEY" in os.environ:
                del os.environ["OPENAI_API_KEY"]


class TestAnthropicProvider:
    """Test Anthropic LLM provider."""

    def test_provider_name(self) -> None:
        """Test provider name property."""
        provider = AnthropicProvider(api_key="test-key")

        assert provider.provider_name == "Anthropic"

    def test_default_model(self) -> None:
        """Test default model method."""
        provider = AnthropicProvider(api_key="test-key")

        assert provider.default_model() == "claude-3-5-haiku-20241022"

    def test_base_url(self) -> None:
        """Test base URL handling."""
        custom_url = "https://custom.anthropic.com"
        provider = AnthropicProvider(api_key="test-key", base_url=custom_url)

        assert provider.base_url == custom_url

    def test_default_base_url(self) -> None:
        """Test default base URL."""
        provider = AnthropicProvider(api_key="test-key")

        assert provider.base_url == "https://api.anthropic.com"

    def test_configured_with_key(self) -> None:
        """Test configured with valid API key."""
        # Anthropic keys need sk-ant- prefix and >= 40 chars
        provider = AnthropicProvider(api_key="sk-ant-" + "x" * 40)

        assert provider.configured() is True

    def test_configured_without_key(self) -> None:
        """Test configured without API key."""
        provider = AnthropicProvider(api_key="")

        assert provider.configured() is False


class TestOpenAIProvider:
    """Test OpenAI LLM provider."""

    def test_provider_name(self) -> None:
        """Test provider name property."""
        provider = OpenAIProvider(api_key="test-key")

        assert provider.provider_name == "OpenAI"

    def test_default_model(self) -> None:
        """Test default model method."""
        provider = OpenAIProvider(api_key="test-key")

        assert provider.default_model() == "gpt-4o-mini"

    def test_base_url(self) -> None:
        """Test base URL handling."""
        custom_url = "https://custom.openai.com"
        provider = OpenAIProvider(api_key="test-key", base_url=custom_url)

        assert provider.base_url == custom_url

    def test_default_base_url(self) -> None:
        """Test default base URL."""
        provider = OpenAIProvider(api_key="test-key")

        assert provider.base_url == "https://api.openai.com/v1"

    def test_configured_with_key(self) -> None:
        """Test configured with valid API key."""
        # OpenAI keys need sk- prefix and >= 40 chars
        provider = OpenAIProvider(api_key="sk-" + "x" * 40)

        assert provider.configured() is True

    def test_configured_without_key(self) -> None:
        """Test configured without API key."""
        provider = OpenAIProvider(api_key="")

        assert provider.configured() is False


class TestLLMIntegration:
    """Integration tests for LLM providers."""

    def test_anthropic_provider_interface(self) -> None:
        """Test AnthropicProvider implements LLMProvider interface."""
        provider = AnthropicProvider(api_key="test-key")

        assert isinstance(provider, LLMProvider)
        assert hasattr(provider, "call")
        assert hasattr(provider, "provider_name")
        assert hasattr(provider, "default_model")
        assert hasattr(provider, "configured")

    def test_openai_provider_interface(self) -> None:
        """Test OpenAIProvider implements LLMProvider interface."""
        provider = OpenAIProvider(api_key="test-key")

        assert isinstance(provider, LLMProvider)
        assert hasattr(provider, "call")
        assert hasattr(provider, "provider_name")
        assert hasattr(provider, "default_model")
        assert hasattr(provider, "configured")

    def test_stats_tracking(self) -> None:
        """Test stats tracking across calls."""
        provider = AnthropicProvider(api_key="test-key")

        # Initial stats
        stats = provider.stats()
        assert stats.total_calls == 0

        # We can't test actual API calls without keys,
        # but we can verify the stats structure
        assert stats.provider_name == "Anthropic"
        assert "total_calls" in stats.__dict__
        assert "total_tokens" in stats.__dict__
