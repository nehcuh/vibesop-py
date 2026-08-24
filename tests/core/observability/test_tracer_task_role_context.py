"""Tests for ``bind_task_context`` — bind task_id + role_id to the active trace
context so descendant spans carry attribution without call-site plumbing.

Regression for v3 Phase A Task 1: extend existing ``current_task_id`` path
to carry ``role_id`` (single context path, no parallel ContextVar).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibesop.core.observability.tracer import ObservabilityTracer, bind_task_context


@pytest.fixture
def fresh_tracer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ObservabilityTracer:
    """Reset the module-level tracer singleton to write into tmp_path."""
    import vibesop.core.observability.tracer as tracer_mod

    span_file = tmp_path / "spans.jsonl"
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


class TestBindTaskContext:
    """bind_task_context must propagate task_id + role_id to descendant spans
    emitted inside the with-block, and must not leak after exit."""

    def test_propagates_task_and_role_to_child_span(
        self, fresh_tracer: ObservabilityTracer, tmp_path: Path
    ) -> None:
        """Inside bind_task_context(task_id="t1", role_id="r1"), a child span
        emitted via tracer.span() must have task_id="t1" and role_id="r1"."""
        with fresh_tracer.trace("root", task_id="outer-task", role_id="outer-role"):
            with bind_task_context(task_id="task-abc", role_id="role-implementer"):
                with fresh_tracer.span("child", "llm"):
                    pass

        spans = _read_spans(tmp_path / "spans.jsonl")
        child = next(s for s in spans if s["name"] == "child")
        assert child["task_id"] == "task-abc"
        assert child["role_id"] == "role-implementer"

    def test_does_not_leak_after_exit(
        self, fresh_tracer: ObservabilityTracer, tmp_path: Path
    ) -> None:
        """After exiting bind_task_context, new spans revert to the outer
        trace's task_id/role_id (not the bound values)."""
        with fresh_tracer.trace("root", task_id="outer-task", role_id="outer-role"):
            with bind_task_context(task_id="task-abc", role_id="role-implementer"):
                with fresh_tracer.span("inside", "llm"):
                    pass
            # Outside the bind block — must revert
            with fresh_tracer.span("outside", "llm"):
                pass

        spans = _read_spans(tmp_path / "spans.jsonl")
        outside = next(s for s in spans if s["name"] == "outside")
        assert outside["task_id"] == "outer-task"
        assert outside["role_id"] == "outer-role"

    def test_nested_bind_restores_outer_on_exit(
        self, fresh_tracer: ObservabilityTracer, tmp_path: Path
    ) -> None:
        """Nested bind_task_context: inner exit restores outer bind values,
        not the trace root."""
        with fresh_tracer.trace("root", task_id="root-task", role_id="root-role"):
            with bind_task_context(task_id="step-1", role_id="reviewer"):
                with bind_task_context(task_id="step-1a", role_id="implementer"):
                    with fresh_tracer.span("inner", "llm"):
                        pass
                # Inner exit — should restore to step-1 / reviewer
                with fresh_tracer.span("mid", "llm"):
                    pass

        spans = _read_spans(tmp_path / "spans.jsonl")
        inner = next(s for s in spans if s["name"] == "inner")
        mid = next(s for s in spans if s["name"] == "mid")
        assert inner["task_id"] == "step-1a"
        assert inner["role_id"] == "implementer"
        assert mid["task_id"] == "step-1"
        assert mid["role_id"] == "reviewer"

    def test_outside_trace_is_noop(self, fresh_tracer: ObservabilityTracer, tmp_path: Path) -> None:
        """Calling bind_task_context with no active trace must not raise.
        Spans emitted inside will be standalone (no task_id)."""
        with bind_task_context(task_id="orphan-task", role_id="orphan-role"):
            with fresh_tracer.span("standalone", "llm"):
                pass

        spans = _read_spans(tmp_path / "spans.jsonl")
        standalone = next(s for s in spans if s["name"] == "standalone")
        assert standalone["task_id"] is None
        assert standalone["role_id"] is None

    def test_role_only_bind_keeps_outer_task(
        self, fresh_tracer: ObservabilityTracer, tmp_path: Path
    ) -> None:
        """bind_task_context(task_id=None) should keep the outer task_id but
        override role_id. This supports the 'change role mid-step' case."""
        with fresh_tracer.trace("root", task_id="root-task", role_id="root-role"):
            with bind_task_context(task_id="root-task", role_id="reviewer"):
                with fresh_tracer.span("child", "llm"):
                    pass

        spans = _read_spans(tmp_path / "spans.jsonl")
        child = next(s for s in spans if s["name"] == "child")
        assert child["task_id"] == "root-task"
        assert child["role_id"] == "reviewer"

    def test_bind_propagates_via_start_span(
        self, fresh_tracer: ObservabilityTracer, tmp_path: Path
    ) -> None:
        """bind_task_context must propagate task_id/role_id to spans created
        via start_span()/finish_span() (manual API), not just the span()
        context manager.

        Regression for pi Q2 review: SpanWrappedProvider uses start_span
        (span_wrapped.py:150 / :196), not span(). Without this test, a future
        refactor that breaks start_span's ctx inheritance would pass all
        existing tests but break production LLM call attribution.
        """
        with fresh_tracer.trace("root", task_id="outer-task", role_id="outer-role"):
            with bind_task_context(task_id="step-1", role_id="implementer"):
                span = fresh_tracer.start_span("llm-call", "llm")
                fresh_tracer.finish_span(span)

        spans = _read_spans(tmp_path / "spans.jsonl")
        llm_span = next(s for s in spans if s["name"] == "llm-call")
        assert llm_span["task_id"] == "step-1"
        assert llm_span["role_id"] == "implementer"
