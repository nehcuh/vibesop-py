"""Tests for SpanWrappedProvider — verifies GAP-1 wrap emits llm-spans.

These tests cover:
* Wrap transparently delegates non-call methods to inner
* Sync ``call()`` emits a span with tokens + output metadata on success
* Async ``acall()`` emits a span the same way
* Exceptions propagate AND the span is marked ``status="error"``
* Disabled tracer = pass-through, no span emission
* Token fallback when response only has ``tokens_used``
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from vibesop.core.observability.models import CURRENT_SPAN_SCHEMA_VERSION
from vibesop.core.observability.tracer import ObservabilityTracer
from vibesop.llm.base import LLMProvider, LLMResponse
from vibesop.llm.span_wrapped import SpanWrappedProvider


class _FakeProvider(LLMProvider):
    """In-memory provider — no network. Returns deterministic content."""

    def __init__(
        self,
        *,
        response: LLMResponse | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        super().__init__(api_key="sk-fake-key-1234567890", base_url=None)
        self._response = response or LLMResponse(
            content="hello world",
            model="fake-model",
            provider="FakeProvider",
            tokens_used=100,
            input_tokens=80,
            output_tokens=20,
        )
        self._raise = raise_exc
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "FakeProvider"

    def default_model(self) -> str:
        return "fake-model"

    def call(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> LLMResponse:
        self.call_count += 1
        if self._raise:
            raise self._raise
        return self._response


@pytest.fixture
def tmp_span_file(tmp_path: Path) -> Path:
    return tmp_path / "spans.jsonl"


@pytest.fixture
def enabled_tracer(tmp_span_file: Path, monkeypatch: pytest.MonkeyPatch) -> ObservabilityTracer:
    """Patch the module-level tracer singleton with a fresh enabled instance."""
    import vibesop.core.observability.tracer as tracer_mod

    fresh = ObservabilityTracer(storage_path=tmp_span_file, enabled=True)
    monkeypatch.setattr(tracer_mod, "_tracer", fresh)
    return fresh


@pytest.fixture
def disabled_tracer(tmp_span_file: Path, monkeypatch: pytest.MonkeyPatch) -> ObservabilityTracer:
    import vibesop.core.observability.tracer as tracer_mod

    fresh = ObservabilityTracer(storage_path=tmp_span_file, enabled=False)
    monkeypatch.setattr(tracer_mod, "_tracer", fresh)
    return fresh


def _read_spans(path: Path) -> list[dict]:
    if not path.exists():
        return []
    spans = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    # SpanWriter serialises metadata + input/output_data to JSON strings.
    # Decode them back to dicts for ergonomic assertions.
    for span in spans:
        for key in ("metadata", "input_data", "output_data"):
            val = span.get(key)
            if isinstance(val, str):
                with contextlib.suppress(json.JSONDecodeError):
                    span[key] = json.loads(val)
    return spans


class TestDelegation:
    def test_provider_name_delegates(self) -> None:
        inner = _FakeProvider()
        wrapped = SpanWrappedProvider(inner)
        assert wrapped.provider_name == "FakeProvider"

    def test_default_model_delegates(self) -> None:
        wrapped = SpanWrappedProvider(_FakeProvider())
        assert wrapped.default_model() == "fake-model"

    def test_configured_delegates(self) -> None:
        wrapped = SpanWrappedProvider(_FakeProvider())
        assert wrapped.configured() is True

    def test_stats_delegates(self) -> None:
        wrapped = SpanWrappedProvider(_FakeProvider())
        stats = wrapped.stats()
        assert stats.provider_name == "FakeProvider"


class TestSyncCallEmitsSpan:
    def test_call_emits_llm_span_on_success(
        self, enabled_tracer: ObservabilityTracer, tmp_span_file: Path
    ) -> None:
        wrapped = SpanWrappedProvider(_FakeProvider())

        wrapped.call("hello prompt", model="fake-model", max_tokens=100, temperature=0.5)

        spans = _read_spans(tmp_span_file)
        assert len(spans) == 1
        span = spans[0]
        assert span["span_kind"] == "llm"
        assert span["status"] == "ok"
        assert span["name"] == "llm:FakeProvider:fake-model"
        assert span["schema_version"] == CURRENT_SPAN_SCHEMA_VERSION
        assert span["tokens_input"] == 80
        assert span["tokens_output"] == 20

    def test_call_metadata_records_call_params(
        self, enabled_tracer: ObservabilityTracer, tmp_span_file: Path
    ) -> None:
        wrapped = SpanWrappedProvider(_FakeProvider())

        wrapped.call("x" * 100, max_tokens=200, temperature=0.7)

        spans = _read_spans(tmp_span_file)
        meta = spans[0]["metadata"]
        assert meta["provider"] == "FakeProvider"
        assert meta["model"] == "fake-model"
        assert meta["max_tokens"] == 200
        assert meta["temperature"] == 0.7
        assert meta["prompt_chars"] == 100
        # fake-model isn't in the pricing table → cost stays 0 with
        # "unavailable" marker (was "p1_not_available" pre-P2-3).
        assert meta["cost_estimation"] == "unavailable"

    def test_call_input_preview_truncated(
        self, enabled_tracer: ObservabilityTracer, tmp_span_file: Path
    ) -> None:
        wrapped = SpanWrappedProvider(_FakeProvider())
        long_prompt = "x" * 1000

        wrapped.call(long_prompt)

        spans = _read_spans(tmp_span_file)
        assert len(spans[0]["input_data"]["prompt_preview"]) <= 500

    def test_call_output_records_response(
        self, enabled_tracer: ObservabilityTracer, tmp_span_file: Path
    ) -> None:
        wrapped = SpanWrappedProvider(_FakeProvider())

        wrapped.call("hello")

        spans = _read_spans(tmp_span_file)
        out = spans[0]["output_data"]
        assert out["model"] == "fake-model"
        assert out["provider"] == "FakeProvider"
        assert "content_preview" in out


class TestTokenFallback:
    def test_tokens_used_splits_when_in_out_missing(
        self, enabled_tracer: ObservabilityTracer, tmp_span_file: Path
    ) -> None:
        """When input/output_tokens missing but tokens_used present, split 50/50."""
        response = LLMResponse(
            content="legacy",
            model="legacy-model",
            provider="LegacyProvider",
            tokens_used=99,
            input_tokens=None,
            output_tokens=None,
        )
        wrapped = SpanWrappedProvider(_FakeProvider(response=response))

        wrapped.call("hi")

        spans = _read_spans(tmp_span_file)
        # 99 // 2 = 49 in, 50 out
        assert spans[0]["tokens_input"] == 49
        assert spans[0]["tokens_output"] == 50

    def test_token_estimation_flagged_in_metadata(
        self, enabled_tracer: ObservabilityTracer, tmp_span_file: Path
    ) -> None:
        """Estimated token split must be flagged so aggregators can filter it."""
        response = LLMResponse(
            content="legacy",
            model="legacy-model",
            provider="LegacyProvider",
            tokens_used=99,
            input_tokens=None,
            output_tokens=None,
        )
        wrapped = SpanWrappedProvider(_FakeProvider(response=response))

        wrapped.call("hi")

        spans = _read_spans(tmp_span_file)
        meta = spans[0]["metadata"]
        assert meta["token_accounting"] == "estimated_50_50_from_tokens_used"

    def test_measured_tokens_flagged_as_measured(
        self, enabled_tracer: ObservabilityTracer, tmp_span_file: Path
    ) -> None:
        """When tokens come from provider directly, flag as 'measured'."""
        wrapped = SpanWrappedProvider(_FakeProvider())  # default response has in/out
        wrapped.call("hi")
        spans = _read_spans(tmp_span_file)
        assert spans[0]["metadata"]["token_accounting"] == "measured"


class TestTaskAttribution:
    """v8.2 GAP-1 attribution fix: llm-span must inherit task_id from active trace."""

    def test_llm_span_inherits_task_id_from_active_trace(
        self, enabled_tracer: ObservabilityTracer, tmp_span_file: Path
    ) -> None:
        wrapped = SpanWrappedProvider(_FakeProvider())

        with enabled_tracer.trace("outer-task", task_id="task-xyz"):
            wrapped.call("hello")

        spans = _read_spans(tmp_span_file)
        # Two spans: root task span + nested llm span
        assert len(spans) == 2
        llm_span = next(s for s in spans if s["span_kind"] == "llm")
        task_span = next(s for s in spans if s["span_kind"] == "task")
        assert llm_span["task_id"] == "task-xyz"
        assert llm_span["trace_id"] == task_span["trace_id"]
        assert llm_span["parent_span_id"] == task_span["id"]

    def test_llm_span_without_active_trace_is_orphan(
        self, enabled_tracer: ObservabilityTracer, tmp_span_file: Path
    ) -> None:
        """No active trace → llm-span gets fresh trace_id, no task_id, no parent.

        This is the hook-path case (Pi's B1 / Kimi's B2). The span still lands
        in spans.jsonl (GAP-1 literally closed) but is not attributable until
        M3 aggregator adds trace_id-based fallback grouping.
        """
        wrapped = SpanWrappedProvider(_FakeProvider())

        wrapped.call("orphan hello")

        spans = _read_spans(tmp_span_file)
        assert len(spans) == 1
        span = spans[0]
        assert span["span_kind"] == "llm"
        assert span["task_id"] is None
        assert span["parent_span_id"] is None


class TestErrorPropagation:
    def test_call_emits_error_span_and_reraises(
        self, enabled_tracer: ObservabilityTracer, tmp_span_file: Path
    ) -> None:
        err = RuntimeError("upstream failure")
        wrapped = SpanWrappedProvider(_FakeProvider(raise_exc=err))

        with pytest.raises(RuntimeError, match="upstream failure"):
            wrapped.call("hello")

        spans = _read_spans(tmp_span_file)
        assert len(spans) == 1
        assert spans[0]["status"] == "error"
        assert "upstream failure" in spans[0]["error_message"]
        assert spans[0]["span_kind"] == "llm"


class TestDisabledTracer:
    def test_disabled_tracer_pass_through(
        self, disabled_tracer: ObservabilityTracer, tmp_span_file: Path
    ) -> None:
        inner = _FakeProvider()
        wrapped = SpanWrappedProvider(inner)

        result = wrapped.call("hello")

        assert result.content == "hello world"
        assert inner.call_count == 1
        assert not tmp_span_file.exists()


class TestAsyncCall:
    @pytest.mark.asyncio
    async def test_acall_emits_llm_span(
        self, enabled_tracer: ObservabilityTracer, tmp_span_file: Path
    ) -> None:
        inner = _FakeProvider()
        # Force async path by overriding acall directly
        inner_acall = MagicMock(return_value=_FakeProvider()._response)

        async def fake_acall(prompt, **kwargs):
            return inner_acall(prompt, **kwargs)

        inner.acall = fake_acall  # type: ignore[assignment]
        wrapped = SpanWrappedProvider(inner)

        await wrapped.acall("async hello", model="fake-model")

        spans = _read_spans(tmp_span_file)
        assert len(spans) == 1
        span = spans[0]
        assert span["span_kind"] == "llm"
        assert span["status"] == "ok"
        assert span["tokens_input"] == 80
        assert span["tokens_output"] == 20

    @pytest.mark.asyncio
    async def test_acall_disabled_tracer_no_span(
        self, disabled_tracer: ObservabilityTracer, tmp_span_file: Path
    ) -> None:
        inner = _FakeProvider()
        wrapped = SpanWrappedProvider(inner)

        result = await wrapped.acall("async hello")

        assert result.content == "hello world"
        assert not tmp_span_file.exists()
