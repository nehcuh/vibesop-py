"""Tests for ``set_llm`` auto-wrap behaviour (v8.2 P2 §24.5 #2).

Verifies that third-party providers injected via ``router.set_llm()`` get
auto-wrapped with ``SpanWrappedProvider`` so they emit llm-spans, while
duck-typed callers (agent runtimes passing minimal ``.call()`` objects)
pass through unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from vibesop.core.observability.tracer import ObservabilityTracer
from vibesop.core.routing.unified import UnifiedRouter, _maybe_wrap_for_spans
from vibesop.llm.base import LLMProvider, LLMResponse
from vibesop.llm.span_wrapped import SpanWrappedProvider


class _FullProvider(LLMProvider):
    """Provider with full LLMProvider surface — eligible for wrap."""

    def __init__(self) -> None:
        super().__init__(api_key="sk-test-1234567890", base_url=None)

    @property
    def provider_name(self) -> str:
        return "TestFull"

    def default_model(self) -> str:
        return "test-model"

    def call(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> LLMResponse:
        return LLMResponse(
            content="ok",
            model="test-model",
            provider="TestFull",
            tokens_used=10,
            input_tokens=8,
            output_tokens=2,
        )


class _MinimalAgentLLM:
    """Duck-typed agent runtime LLM — only has .call(). Not eligible for wrap."""

    def call(self, prompt: str, max_tokens: int = 100, temperature: float = 0.1) -> Any:
        return type("R", (), {"content": "ok"})()


class TestMaybeWrapForSpans:
    def test_full_provider_gets_wrapped(self) -> None:
        """LLMProvider-shaped objects get wrapped → spans will be emitted."""
        provider = _FullProvider()
        result = _maybe_wrap_for_spans(provider)
        assert isinstance(result, SpanWrappedProvider)
        assert result._inner is provider  # inner is the original

    def test_already_wrapped_returns_same_instance(self) -> None:
        """Wrapping an already-wrapped provider is idempotent."""
        provider = SpanWrappedProvider(_FullProvider())
        result = _maybe_wrap_for_spans(provider)
        assert result is provider

    def test_minimal_agent_llm_passes_through(self) -> None:
        """Duck-typed callers (no provider_name etc.) pass through unchanged.

        Rationale: SpanWrappedProvider requires the LLMProvider ABC; forcing
        agent runtimes to comply would break their existing integrations.
        Span emission for these is skipped, not crashed.
        """
        provider = _MinimalAgentLLM()
        result = _maybe_wrap_for_spans(provider)
        assert result is provider
        assert not isinstance(result, SpanWrappedProvider)

    def test_none_passes_through(self) -> None:
        """None injection (disabled triage) is left alone."""
        assert _maybe_wrap_for_spans(None) is None

    def test_object_missing_some_attrs_passes_through(self) -> None:
        """Has .call() and provider_name but missing default_model — pass through."""

        class Partial:
            provider_name = "Partial"

            def call(self, prompt: str) -> Any:
                return None

        provider = Partial()
        result = _maybe_wrap_for_spans(provider)
        assert result is provider


class TestSetLlmAutoWrap:
    """End-to-end: set_llm() on UnifiedRouter triggers auto-wrap."""

    @pytest.fixture
    def fresh_tracer(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        import vibesop.core.observability.tracer as tracer_mod

        span_file = tmp_path / "spans.jsonl"
        fresh = ObservabilityTracer(storage_path=span_file, enabled=True)
        monkeypatch.setattr(tracer_mod, "_tracer", fresh)
        return span_file

    def test_set_llm_with_full_provider_wraps(self, fresh_tracer: Path) -> None:
        """Injecting an LLMProvider-shaped object auto-wraps for span emission."""
        router = UnifiedRouter()
        provider = _FullProvider()
        router.set_llm(provider)

        # Both router and triage_service should see the wrapped version
        assert isinstance(router._llm, SpanWrappedProvider)
        assert isinstance(router._triage_service._llm, SpanWrappedProvider)
        # And the inner is the original provider
        assert router._llm._inner is provider

    def test_set_llm_with_minimal_agent_llm_passes_through(self, fresh_tracer: Path) -> None:
        """Injecting a duck-typed LLM passes through without wrap."""
        router = UnifiedRouter()
        provider = _MinimalAgentLLM()
        router.set_llm(provider)

        assert router._llm is provider
        assert not isinstance(router._llm, SpanWrappedProvider)

    def test_wrapped_provider_emits_span_on_call(self, fresh_tracer: Path) -> None:
        """The whole point: injecting a full provider and calling it
        produces a span, even though set_llm was used (not the factory)."""
        router = UnifiedRouter()
        router.set_llm(_FullProvider())

        # Call via the wrapped provider directly (simulates triage path)
        router._llm.call(prompt="hello", max_tokens=50)

        spans: list[dict] = []
        with fresh_tracer.open() as f:
            for raw in f:
                stripped = raw.strip()
                if stripped:
                    spans.append(json.loads(stripped))

        assert len(spans) == 1
        assert spans[0]["span_kind"] == "llm"
        assert spans[0]["name"] == "llm:TestFull:test-model"
