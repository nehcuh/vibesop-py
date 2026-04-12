"""Tests for OpenAI LLM provider."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vibesop.llm.openai import OpenAIProvider


class FakeCompletion:
    def __init__(self, content, usage=None):
        self.choices = [MagicMock(message=MagicMock(content=content))]
        self.usage = usage


class FakeUsage:
    def __init__(self):
        self.prompt_tokens = 10
        self.completion_tokens = 5
        self.total_tokens = 15


def test_openai_provider_init_with_env_var(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "x" * 48)
    provider = OpenAIProvider()
    assert provider.api_key is not None
    assert provider.configured() is True


def test_openai_provider_not_configured():
    provider = OpenAIProvider(api_key="")
    assert provider.configured() is False


def test_openai_provider_call_success():
    provider = OpenAIProvider(api_key="sk-" + "x" * 48)
    fake_response = FakeCompletion("Hello", usage=FakeUsage())

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_response
    provider._client = mock_client

    result = provider.call("Say hello")
    assert result.content == "Hello"
    assert result.model == provider.DEFAULT_MODEL
    assert result.tokens_used == 15
    assert result.input_tokens == 10
    assert result.output_tokens == 5


def test_openai_provider_call_no_usage():
    provider = OpenAIProvider(api_key="sk-" + "x" * 48)
    fake_response = FakeCompletion("Hello", usage=None)

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_response
    provider._client = mock_client

    result = provider.call("Say hello")
    assert result.content == "Hello"
    assert result.tokens_used is None


def test_openai_provider_call_unconfigured():
    provider = OpenAIProvider(api_key="")
    with pytest.raises(ValueError, match="not configured"):
        provider.call("Say hello")


def test_openai_provider_acall_success():
    provider = OpenAIProvider(api_key="sk-" + "x" * 48)
    fake_response = FakeCompletion("Hello async", usage=FakeUsage())

    async def _run():
        with patch("vibesop.llm.openai.AsyncOpenAI") as mock_async:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
            instance = mock_async.return_value
            instance.__aenter__ = AsyncMock(return_value=mock_client)
            instance.__aexit__ = AsyncMock(return_value=False)
            result = await provider.acall("Say hello")
            assert result.content == "Hello async"

    asyncio.run(_run())


def test_openai_provider_default_model():
    provider = OpenAIProvider(api_key="sk-" + "x" * 48)
    assert provider.default_model() == "gpt-4o-mini"
    assert provider.provider_name == "OpenAI"
