"""Tests for Anthropic LLM provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest

from vibesop.llm.anthropic import AnthropicProvider


def test_anthropic_provider_init_with_env_var(monkeypatch):
    key = "sk-ant-" + "x" * 40
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    provider = AnthropicProvider()
    assert provider.api_key == key
    assert provider.configured() is True


def test_anthropic_provider_not_configured():
    provider = AnthropicProvider(api_key="")
    assert provider.configured() is False


def test_anthropic_provider_call_success():
    key = "sk-ant-" + "x" * 40
    provider = AnthropicProvider(api_key=key)
    mock_usage = MagicMock(input_tokens=8, output_tokens=4)
    mock_msg = MagicMock(text="Hi there")
    fake_response = MagicMock(content=[mock_msg], usage=mock_usage)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_response
    provider._client = mock_client

    result = provider.call("Hello")
    assert result.content == "Hi there"
    assert result.tokens_used == 12
    assert result.model == provider.DEFAULT_MODEL


def test_anthropic_provider_call_unconfigured():
    provider = AnthropicProvider(api_key="")
    with pytest.raises(ValueError, match="not configured"):
        provider.call("Hello")


def test_anthropic_provider_call_api_error():
    key = "sk-ant-" + "x" * 40
    provider = AnthropicProvider(api_key=key)
    mock_client = MagicMock()
    err = anthropic.APIError("boom", request=MagicMock(), body=None)
    mock_client.messages.create.side_effect = err
    provider._client = mock_client

    with pytest.raises(anthropic.APIError):
        provider.call("Hello")


@pytest.mark.anyio
async def test_anthropic_provider_acall_success():
    key = "sk-ant-" + "x" * 40
    provider = AnthropicProvider(api_key=key)
    mock_usage = MagicMock(input_tokens=5, output_tokens=3)
    mock_msg = MagicMock(text="Async hi")
    fake_response = MagicMock(content=[mock_msg], usage=mock_usage)

    mock_create = AsyncMock(return_value=fake_response)
    mock_client = MagicMock()
    mock_client.messages.create = mock_create

    with patch("vibesop.llm.anthropic.AsyncAnthropic") as mock_async_cls:
        instance = mock_async_cls.return_value
        instance.__aenter__ = AsyncMock(return_value=mock_client)
        instance.__aexit__ = AsyncMock(return_value=False)
        result = await provider.acall("Hello")

    assert result.content == "Async hi"
    assert result.tokens_used == 8


def test_anthropic_provider_default_model_and_name():
    key = "sk-ant-" + "x" * 40
    provider = AnthropicProvider(api_key=key)
    assert provider.default_model() == "claude-3-5-haiku-20241022"
    assert provider.provider_name == "Anthropic"
