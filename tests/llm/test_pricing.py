"""Tests for ``vibesop.llm.pricing`` — per-model cost lookup.

Covers:
* Exact model ID match
* Longest-prefix match for versioned model IDs
* Cross-provider fallback when provider hint is wrong
* Unknown model returns ``None`` (no exception)
* Cost calculation math
* ``SpanWrappedProvider`` populates ``cost_usd`` when pricing is known
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibesop.core.observability.tracer import ObservabilityTracer
from vibesop.llm.base import LLMProvider, LLMResponse
from vibesop.llm.pricing import LAST_UPDATED, ModelPrice, get_pricing, last_updated
from vibesop.llm.span_wrapped import SpanWrappedProvider


class _FakeProvider(LLMProvider):
    """Provider that reports a specific model + provider name for pricing tests."""

    def __init__(self, *, model: str, provider_name: str) -> None:
        # Set instance attrs BEFORE super().__init__ — base class reads
        # provider_name during init to build _stats.
        self._model = model
        self._provider_name = provider_name
        super().__init__(api_key="sk-fake-key-1234567890", base_url=None)

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def default_model(self) -> str:
        return self._model

    def call(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> LLMResponse:
        return LLMResponse(
            content="ok",
            model=self._model,
            provider=self._provider_name,
            tokens_used=120,
            input_tokens=100,
            output_tokens=20,
        )


class TestPricingLookup:
    def test_exact_match_deepseek(self) -> None:
        p = get_pricing("deepseek-v4-flash", provider="deepseek")
        assert p is not None
        assert p.input_per_mtok == 0.14
        assert p.output_per_mtok == 0.28

    def test_exact_match_anthropic(self) -> None:
        p = get_pricing("claude-sonnet-4-6", provider="anthropic")
        assert p is not None
        assert p.input_per_mtok == 3.0
        assert p.output_per_mtok == 15.0

    def test_prefix_match_versioned_model(self) -> None:
        """``gpt-4o-mini-2024-07-18`` should match ``gpt-4o-mini`` (longest
        prefix wins over ``gpt-4``)."""
        p = get_pricing("gpt-4o-mini-2024-07-18", provider="openai")
        assert p is not None
        assert p.input_per_mtok == 0.15
        assert p.output_per_mtok == 0.60

    def test_prefix_match_longest_wins(self) -> None:
        """``gpt-4o`` and ``gpt-4o-mini`` both prefix-match ``gpt-4o-mini-XXX``;
        the longer prefix wins."""
        p = get_pricing("gpt-4o-mini", provider="openai")
        assert p is not None
        assert p.input_per_mtok == 0.15  # gpt-4o-mini, not gpt-4o ($2.50)

    def test_cross_provider_fallback(self) -> None:
        """Without provider hint, scan all providers."""
        p = get_pricing("gpt-4o", provider=None)
        assert p is not None
        assert p.input_per_mtok == 2.50

    def test_unknown_model_returns_none(self) -> None:
        assert get_pricing("totally-fake-model-xyz", provider="openai") is None
        assert get_pricing("totally-fake-model-xyz", provider=None) is None

    def test_empty_model_returns_none(self) -> None:
        assert get_pricing("", provider="openai") is None

    def test_unknown_provider_falls_back_to_none(self) -> None:
        """Unknown provider string doesn't crash — returns None."""
        assert get_pricing("any-model", provider="unknown-provider") is None

    def test_ollama_is_zero_cost(self) -> None:
        """Ollama (local) has empty pricing table — returns None, not zero.

        Callers treat None as cost=0 + 'unavailable' marker."""
        assert get_pricing("llama3", provider="ollama") is None

    def test_last_updated_is_date_string(self) -> None:
        assert isinstance(LAST_UPDATED, str)
        assert len(LAST_UPDATED) == 10  # YYYY-MM-DD
        assert last_updated() == LAST_UPDATED


class TestCostCalculation:
    def test_cost_math_simple(self) -> None:
        p = ModelPrice(input_per_mtok=1.0, output_per_mtok=2.0)
        # 1M input + 1M output = $1 + $2 = $3
        assert p.cost_usd(tokens_in=1_000_000, tokens_out=1_000_000) == 3.0

    def test_cost_math_typical_triage(self) -> None:
        """Typical AI_TRIAGE call: 500 input + 7 output tokens."""
        p = get_pricing("deepseek-v4-flash", provider="deepseek")
        assert p is not None
        cost = p.cost_usd(tokens_in=500, tokens_out=7)
        # (500 * 0.14 + 7 * 0.28) / 1_000_000 = 71.96 / 1_000_000 ≈ $0.00007196
        assert cost == pytest.approx(0.00007196, abs=1e-9)

    def test_cost_math_zero_tokens(self) -> None:
        p = ModelPrice(input_per_mtok=10.0, output_per_mtok=30.0)
        assert p.cost_usd(tokens_in=0, tokens_out=0) == 0.0


@pytest.fixture
def fresh_tracer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Reset tracer singleton; return span file path."""
    import vibesop.core.observability.tracer as tracer_mod

    span_file = tmp_path / "spans.jsonl"
    fresh = ObservabilityTracer(storage_path=span_file, enabled=True)
    monkeypatch.setattr(tracer_mod, "_tracer", fresh)
    return span_file


def _read_spans(path: Path) -> list[dict]:
    if not path.exists():
        return []
    spans: list[dict] = []
    with path.open() as f:
        for raw in f:
            stripped = raw.strip()
            if stripped:
                spans.append(json.loads(stripped))
    # SpanWriter serialises metadata + input/output_data to JSON strings.
    # Decode them back to dicts for ergonomic assertions.
    import contextlib

    for span in spans:
        for key in ("metadata", "input_data", "output_data"):
            val = span.get(key)
            if isinstance(val, str):
                with contextlib.suppress(json.JSONDecodeError):
                    span[key] = json.loads(val)
    return spans


class TestSpanWrappedCostApplication:
    def test_known_model_gets_nonzero_cost(self, fresh_tracer: Path) -> None:
        """SpanWrappedProvider with a real-model name should populate
        ``cost_usd`` and set ``cost_estimation="measured"``."""
        provider = SpanWrappedProvider(
            _FakeProvider(model="deepseek-v4-flash", provider_name="OpenAI")
        )
        provider.call("hello")

        spans = _read_spans(fresh_tracer)
        assert len(spans) == 1
        span = spans[0]

        # Cost should be non-zero (100 in + 20 out at $0.14/$0.28 per Mtok)
        expected_cost = (100 * 0.14 + 20 * 0.28) / 1_000_000
        assert span["cost_usd"] == pytest.approx(expected_cost, rel=1e-9)

        meta = span["metadata"]
        assert meta["cost_estimation"] == "measured"

    def test_unknown_model_keeps_zero_cost(
        self, fresh_tracer: Path
    ) -> None:
        """SpanWrappedProvider with an unknown model keeps cost_usd=0
        and uses ``cost_estimation="unavailable"``."""
        provider = SpanWrappedProvider(
            _FakeProvider(model="totally-unknown-xyz", provider_name="FakeProvider")
        )
        provider.call("hello")

        spans = _read_spans(fresh_tracer)
        assert len(spans) == 1
        span = spans[0]
        assert span["cost_usd"] == 0.0

        meta = span["metadata"]
        assert meta["cost_estimation"] == "unavailable"

    def test_free_model_has_zero_cost_with_measured_marker(
        self, fresh_tracer: Path
    ) -> None:
        """GLM-4-Flash is free (rate=0) — cost_usd=0 but marker="measured"
        so aggregator knows the cost is genuinely zero, not unknown."""
        provider = SpanWrappedProvider(
            _FakeProvider(model="glm-4-flash", provider_name="Zhipu")
        )
        provider.call("hello")

        spans = _read_spans(fresh_tracer)
        span = spans[0]
        assert span["cost_usd"] == 0.0

        meta = span["metadata"]
        # The critical distinction: 0 because we KNOW it's free vs 0 because unknown.
        assert meta["cost_estimation"] == "measured"
