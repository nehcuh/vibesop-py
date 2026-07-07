"""Tests for Anthropic LLM provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest

from vibesop.core.exceptions import LLMError
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


def test_anthropic_provider_call_api_error_wraps_llmerror():
    """F-22: Anthropic API errors surface as LLMError (not bare SDK error).

    Callers write `except LLMError` for uniform provider error handling; a raw
    anthropic.APIError would skip that path and surface an opaque SDK traceback.
    Matches the OpenAI/Ollama contract.
    """
    key = "sk-ant-" + "x" * 40
    provider = AnthropicProvider(api_key=key)
    mock_client = MagicMock()
    err = anthropic.APIError("boom", request=MagicMock(), body=None)
    mock_client.messages.create.side_effect = err
    provider._client = mock_client

    with pytest.raises(LLMError, match="Anthropic API error") as raised:
        provider.call("Hello")
    assert raised.value.provider == "Anthropic"
    assert raised.value.__cause__ is err


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
    assert provider.default_model() == "claude-haiku-4-5"
    assert provider.provider_name == "Anthropic"


@pytest.mark.anyio
async def test_anthropic_provider_acall_api_error_wraps_llmerror():
    """F-22: async Anthropic API errors also surface as LLMError."""
    key = "sk-ant-" + "x" * 40
    provider = AnthropicProvider(api_key=key)
    err = anthropic.APIError("boom", request=MagicMock(), body=None)
    mock_create = AsyncMock(side_effect=err)
    mock_client = MagicMock()
    mock_client.messages.create = mock_create

    with patch("vibesop.llm.anthropic.AsyncAnthropic") as mock_async_cls:
        instance = mock_async_cls.return_value
        instance.__aenter__ = AsyncMock(return_value=mock_client)
        instance.__aexit__ = AsyncMock(return_value=False)
        with pytest.raises(LLMError, match="Anthropic API error") as raised:
            await provider.acall("Hello")

    assert raised.value.provider == "Anthropic"
    assert raised.value.__cause__ is err


def test_anthropic_provider_call_oserror_wraps_llmerror():
    """F-22 (review fixup): transient non-APIError errors (OSError) also wrap to LLMError.

    Matches OpenAI's `(APIError, OSError, ValueError)` catch tuple so a
    connection reset can't leak past a caller's `except LLMError`.
    """
    key = "sk-ant-" + "x" * 40
    provider = AnthropicProvider(api_key=key)
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = OSError("connection reset")
    provider._client = mock_client

    with pytest.raises(LLMError, match="Anthropic API error") as raised:
        provider.call("Hello")
    assert isinstance(raised.value.__cause__, OSError)


@pytest.mark.anyio
async def test_anthropic_provider_acall_oserror_wraps_llmerror():
    """F-22 (review fixup): async path also wraps transient OSError to LLMError."""
    key = "sk-ant-" + "x" * 40
    provider = AnthropicProvider(api_key=key)
    mock_create = AsyncMock(side_effect=OSError("connection reset"))
    mock_client = MagicMock()
    mock_client.messages.create = mock_create

    with patch("vibesop.llm.anthropic.AsyncAnthropic") as mock_async_cls:
        instance = mock_async_cls.return_value
        instance.__aenter__ = AsyncMock(return_value=mock_client)
        instance.__aexit__ = AsyncMock(return_value=False)
        with pytest.raises(LLMError, match="Anthropic API error") as raised:
            await provider.acall("Hello")

    assert isinstance(raised.value.__cause__, OSError)


def test_anthropic_sync_client_uses_timeout():
    """F-24: sync Anthropic client is constructed with TIMEOUT (sanity)."""
    key = "sk-ant-" + "x" * 40
    with patch("vibesop.llm.anthropic.Anthropic") as mock_cls:
        AnthropicProvider(api_key=key)
    assert AnthropicProvider.TIMEOUT == 30.0
    assert mock_cls.call_args.kwargs["timeout"] == AnthropicProvider.TIMEOUT


@pytest.mark.anyio
async def test_anthropic_async_client_uses_timeout():
    """F-24: AsyncAnthropic constructed with timeout (previously missing — could hang)."""
    key = "sk-ant-" + "x" * 40
    provider = AnthropicProvider(api_key=key)
    mock_create = AsyncMock(
        return_value=MagicMock(
            content=[MagicMock(text="x")], usage=MagicMock(input_tokens=1, output_tokens=1)
        )
    )
    mock_client = MagicMock()
    mock_client.messages.create = mock_create

    with patch("vibesop.llm.anthropic.AsyncAnthropic") as mock_async_cls:
        instance = mock_async_cls.return_value
        instance.__aenter__ = AsyncMock(return_value=mock_client)
        instance.__aexit__ = AsyncMock(return_value=False)
        await provider.acall("Hi")

    assert mock_async_cls.call_args.kwargs["timeout"] == AnthropicProvider.TIMEOUT
