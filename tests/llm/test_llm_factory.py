"""Tests for LLM provider factory."""

import pytest

from vibesop.llm.anthropic import AnthropicProvider
from vibesop.llm.factory import create_from_env, create_provider, detect_provider_from_env
from vibesop.llm.openai import OpenAIProvider


def test_create_provider_anthropic():
    provider = create_provider("anthropic", api_key="sk-ant-" + "x" * 40)
    assert isinstance(provider, AnthropicProvider)


def test_create_provider_openai():
    provider = create_provider("openai", api_key="sk-" + "x" * 48)
    assert isinstance(provider, OpenAIProvider)


def test_create_provider_invalid():
    with pytest.raises(ValueError, match="Invalid provider"):
        create_provider("invalid")  # type: ignore[arg-type]


def test_create_provider_auto_detects_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-" + "x" * 40)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("VIBE_LLM_PROVIDER", raising=False)
    provider = create_provider()
    assert isinstance(provider, AnthropicProvider)


def test_create_provider_auto_detects_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "x" * 48)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VIBE_LLM_PROVIDER", raising=False)
    provider = create_provider()
    assert isinstance(provider, OpenAIProvider)


def test_detect_provider_explicit(monkeypatch):
    monkeypatch.setenv("VIBE_LLM_PROVIDER", "openai")
    assert detect_provider_from_env() == "openai"


def test_detect_provider_explicit_invalid_defaults(monkeypatch):
    monkeypatch.setenv("VIBE_LLM_PROVIDER", "bogus")
    assert detect_provider_from_env() == "anthropic"


def test_detect_provider_from_anthropic_key(monkeypatch):
    monkeypatch.delenv("VIBE_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-" + "x" * 40)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert detect_provider_from_env() == "anthropic"


def test_detect_provider_from_openai_key(monkeypatch):
    monkeypatch.delenv("VIBE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "x" * 48)
    assert detect_provider_from_env() == "openai"


def test_detect_provider_default(monkeypatch):
    monkeypatch.delenv("VIBE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert detect_provider_from_env() == "anthropic"


def test_create_from_env_prefers_preferred_when_configured(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-" + "x" * 40)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "x" * 48)
    provider = create_from_env(preferred_provider="openai")
    assert isinstance(provider, OpenAIProvider)


def test_create_from_env_fallback_when_preferred_unconfigured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "x" * 48)
    provider = create_from_env(preferred_provider="anthropic")
    assert isinstance(provider, OpenAIProvider)


def test_create_from_env_returns_unconfigured_preferred(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = create_from_env(preferred_provider="anthropic")
    assert isinstance(provider, AnthropicProvider)
    assert not provider.configured()
