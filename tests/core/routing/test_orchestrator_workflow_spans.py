"""Tests for orchestrator trace context wrapping (Phase A Task 2).

Verifies that ``Orchestrator.orchestrate()`` opens a trace context so all
spans emitted during orchestration (root task span + future phase spans +
downstream LLM spans via SpanWrappedProvider) share a single ``trace_id``.

Uses short queries + disabled orchestration to avoid real LLM calls —
Task 13's fixture-based E2E covers the multi-intent path with stubs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibesop.core.config.manager import RoutingConfig
from vibesop.core.observability.tracer import ObservabilityTracer
from vibesop.core.routing import UnifiedRouter


@pytest.fixture
def fresh_tracer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> ObservabilityTracer:
    """Reset the module-level observability tracer singleton to write into tmp_path."""
    import vibesop.core.observability.tracer as tracer_mod

    span_file = tmp_path / "observability" / "spans.jsonl"
    span_file.parent.mkdir(parents=True, exist_ok=True)
    fresh = ObservabilityTracer(storage_path=span_file, enabled=True)
    monkeypatch.setattr(tracer_mod, "_tracer", fresh)
    return fresh


def _read_spans(path: Path) -> list[dict]:
    if not path.exists():
        return []
    spans: list[dict] = []
    with path.open() as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if stripped:
                spans.append(json.loads(stripped))
    return spans


class TestOrchestratorTraceContext:
    """orchestrate() must open a trace context that groups all emitted spans
    under a single trace_id."""

    def test_orchestrate_opens_trace_context(
        self, fresh_tracer: ObservabilityTracer, tmp_path: Path
    ) -> None:
        """Calling orchestrate() must emit a root 'orchestrate' task span
        with a unique trace_id."""
        router = UnifiedRouter(project_root=tmp_path)
        router.orchestrate("help")  # short query → single path, no LLM

        spans = _read_spans(tmp_path / "observability" / "spans.jsonl")
        assert spans, "orchestrate() must emit at least the root span"
        trace_ids = {s["trace_id"] for s in spans}
        assert len(trace_ids) == 1, (
            f"all spans must share one trace_id, got {trace_ids}"
        )
        root_spans = [s for s in spans if s["name"] == "orchestrate"]
        assert root_spans, "must emit a root 'orchestrate' task span"
        assert root_spans[0]["span_kind"] == "task"

    def test_orchestrate_disabled_still_opens_trace(
        self, fresh_tracer: ObservabilityTracer, tmp_path: Path
    ) -> None:
        """Even with orchestration disabled, the trace context must still open
        so any spans emitted during the (early-return) routing path are grouped."""
        config = RoutingConfig(enable_orchestration=False)
        router = UnifiedRouter(project_root=tmp_path, config=config)
        router.orchestrate("review my code")

        spans = _read_spans(tmp_path / "observability" / "spans.jsonl")
        assert spans, "trace must open even when orchestration is disabled"
        trace_ids = {s["trace_id"] for s in spans}
        assert len(trace_ids) == 1

    def test_two_orchestrate_calls_have_distinct_trace_ids(
        self, fresh_tracer: ObservabilityTracer, tmp_path: Path
    ) -> None:
        """Each orchestrate() call must produce a fresh trace_id (not reused)."""
        router = UnifiedRouter(project_root=tmp_path)
        router.orchestrate("help")
        router.orchestrate("help")

        spans = _read_spans(tmp_path / "observability" / "spans.jsonl")
        root_spans = [s for s in spans if s["name"] == "orchestrate"]
        assert len(root_spans) == 2
        assert root_spans[0]["trace_id"] != root_spans[1]["trace_id"]
