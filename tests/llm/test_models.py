"""Tests for the centralised LLM model-ID registry + validation."""

from __future__ import annotations

from unittest.mock import patch


def test_provider_default_models_covers_openai_compatible() -> None:
    from vibesop.llm.models import PROVIDER_DEFAULT_MODELS

    # The OpenAI-compatible providers the factory routes must all have a default.
    for provider in ("deepseek", "kimi", "zhipu"):
        assert provider in PROVIDER_DEFAULT_MODELS
        assert PROVIDER_DEFAULT_MODELS[provider]


def test_canonical_model_constants_are_current() -> None:
    """Guard against stale snapshots creeping back in (claude-3-*, bare gpt-4)."""
    from vibesop.llm.models import (
        ANTHROPIC_DEFAULT_MODEL,
        ANTHROPIC_FAST_MODEL,
        ANTHROPIC_SMART_MODEL,
        OPENAI_DEFAULT_MODEL,
        OPENAI_SMART_MODEL,
    )

    assert ANTHROPIC_DEFAULT_MODEL == "claude-sonnet-4-6"
    assert ANTHROPIC_SMART_MODEL == "claude-opus-4-8"
    assert ANTHROPIC_FAST_MODEL == "claude-haiku-4-5"
    assert OPENAI_DEFAULT_MODEL == "gpt-4o-mini"
    assert OPENAI_SMART_MODEL == "gpt-4o"
    # none of the canonical IDs are the known-stale snapshots
    stale = {
        "claude-3-5-sonnet-20241022",
        "claude-3-opus-20240229",
        "claude-3-haiku-20240307",
        "gpt-4",
    }
    for m in (
        ANTHROPIC_DEFAULT_MODEL,
        ANTHROPIC_SMART_MODEL,
        ANTHROPIC_FAST_MODEL,
        OPENAI_DEFAULT_MODEL,
        OPENAI_SMART_MODEL,
    ):
        assert m not in stale


def test_validate_provider_model_is_fail_safe_on_network_error() -> None:
    """A network/HTTP error must NOT fail the check (returns ok=True, skipped)."""
    from vibesop.llm.models import validate_provider_model

    with (
        patch("vibesop.llm.models.os.getenv", return_value="fake-key"),
        patch("httpx.get", side_effect=OSError("network down")),
    ):
        ok, msg = validate_provider_model("deepseek", "deepseek-v4-flash")
    assert ok is True
    assert "skipped" in msg


def test_validate_provider_model_skips_without_key() -> None:
    from vibesop.llm.models import validate_provider_model

    with patch("vibesop.llm.models.os.getenv", return_value=None):
        ok, msg = validate_provider_model("deepseek", "deepseek-v4-flash")
    assert ok is True
    assert "no api key" in msg
