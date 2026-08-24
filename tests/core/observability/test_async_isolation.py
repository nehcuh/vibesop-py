"""Regression tests for asyncio task isolation in ObservabilityTracer.

Verifies that concurrent ``asyncio.gather`` calls do not interleave their
span stacks. Without ``contextvars.ContextVar`` (the pre-P2 fix used
``threading.local()``), all asyncio tasks on the same thread shared one
trace context, so:

  task_a opens trace_a → trace_a is the active context
  task_b opens trace_b → trace_b OVERWRITES the active context
  task_a emits llm-span → llm-span's parent is task_b's task span (BUG)

With ContextVar, each asyncio.Task gets its own copy of the context, so
the above scenario produces correct attribution.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from vibesop.core.observability.tracer import ObservabilityTracer


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


class TestAsyncTaskIsolation:
    """Each asyncio.Task must see its own trace context (regression for
    the threading.local bug under asyncio.gather)."""

    def test_concurrent_traces_do_not_steal_parents(
        self, fresh_tracer: ObservabilityTracer, tmp_path: Path
    ) -> None:
        """Two concurrent traces: each task-span owns its llm-span."""

        async def _emit_trace(tracer: ObservabilityTracer, label: str) -> None:
            """Open a trace, emit an llm-span inside, close.

            Yields between operations to give the scheduler a chance to
            interleave with the other task — without ContextVar isolation,
            the bug shows up reliably.
            """
            with tracer.trace(f"task:{label}") as task_span:
                await asyncio.sleep(0)  # yield to scheduler
                inner = tracer.start_span(f"llm:{label}", kind="llm")
                await asyncio.sleep(0)  # yield again to maximise interleaving
                tracer.finish_span(inner)
                await asyncio.sleep(0)
                # Sanity: inner should be parented to task_span
                assert inner.parent_span_id == task_span.id, (
                    f"{label}: llm-span parent should be its own task span, "
                    f"got {inner.parent_span_id!r} expected {task_span.id!r}"
                )

        async def _run_both() -> None:
            await asyncio.gather(
                _emit_trace(fresh_tracer, "A"),
                _emit_trace(fresh_tracer, "B"),
            )

        asyncio.run(_run_both())

        spans = _read_spans(tmp_path / "spans.jsonl")
        assert len(spans) == 4, f"expected 4 spans (2 task + 2 llm), got {len(spans)}"

        # Group by trace_id
        by_trace: dict[str, list[dict]] = {}
        for s in spans:
            by_trace.setdefault(s["trace_id"], []).append(s)

        assert len(by_trace) == 2, (
            f"expected 2 distinct trace_ids, got {len(by_trace)}. "
            f"This is the asyncio isolation bug — concurrent tasks shared context."
        )

        # Each trace must have exactly 1 task span and 1 llm span,
        # with the llm parented to the task.
        for trace_id, trace_spans in by_trace.items():
            task_spans = [s for s in trace_spans if s["span_kind"] == "task"]
            llm_spans = [s for s in trace_spans if s["span_kind"] == "llm"]
            assert len(task_spans) == 1, (
                f"trace {trace_id}: expected 1 task span, got {len(task_spans)}"
            )
            assert len(llm_spans) == 1, (
                f"trace {trace_id}: expected 1 llm span, got {len(llm_spans)}"
            )
            task = task_spans[0]
            llm = llm_spans[0]
            assert llm["parent_span_id"] == task["id"], (
                f"trace {trace_id}: llm parent {llm['parent_span_id']!r} != task id {task['id']!r}"
            )

    def test_high_concurrency_eight_tasks(
        self, fresh_tracer: ObservabilityTracer, tmp_path: Path
    ) -> None:
        """Stress test: 8 concurrent traces still maintain isolation."""

        async def _emit(tracer: ObservabilityTracer, i: int) -> None:
            with tracer.trace(f"task:{i}"):
                await asyncio.sleep(0)
                inner = tracer.start_span(f"llm:{i}", kind="llm")
                await asyncio.sleep(0)
                tracer.finish_span(inner)

        async def _run_all() -> None:
            await asyncio.gather(*[_emit(fresh_tracer, i) for i in range(8)])

        asyncio.run(_run_all())

        spans = _read_spans(tmp_path / "spans.jsonl")
        assert len(spans) == 16, f"expected 16 spans, got {len(spans)}"

        by_trace: dict[str, list[dict]] = {}
        for s in spans:
            by_trace.setdefault(s["trace_id"], []).append(s)

        assert len(by_trace) == 8, f"expected 8 distinct trace_ids, got {len(by_trace)}"

        # Each trace must have exactly 1 task + 1 llm with correct parentage
        for trace_spans in by_trace.values():
            task_spans = [s for s in trace_spans if s["span_kind"] == "task"]
            llm_spans = [s for s in trace_spans if s["span_kind"] == "llm"]
            assert len(task_spans) == 1
            assert len(llm_spans) == 1
            assert llm_spans[0]["parent_span_id"] == task_spans[0]["id"]

    def test_sync_nested_spans_still_work(
        self, fresh_tracer: ObservabilityTracer, tmp_path: Path
    ) -> None:
        """Sync nested spans (no asyncio) must still produce correct parent
        linkage — regression guard for the ContextVar migration."""
        with fresh_tracer.trace("outer") as outer:
            inner = fresh_tracer.start_span("llm:inner", kind="llm")
            fresh_tracer.finish_span(inner)
            assert inner.parent_span_id == outer.id
            assert inner.trace_id == outer.trace_id

        spans = _read_spans(tmp_path / "spans.jsonl")
        assert len(spans) == 2
        outer_span = next(s for s in spans if s["name"] == "outer")
        inner_span = next(s for s in spans if s["name"] == "llm:inner")
        assert inner_span["parent_span_id"] == outer_span["id"]
        assert inner_span["trace_id"] == outer_span["trace_id"]

    def test_mixed_sync_and_async(self, fresh_tracer: ObservabilityTracer, tmp_path: Path) -> None:
        """A trace opened in sync code, then awaited async work inside it,
        should still see the trace context in the async task.

        Note: asyncio.Task copies the context at creation time, so the
        trace context IS inherited. The llm-span emitted inside the task
        should be parented to the sync-opened task span.
        """
        import contextvars

        outer_task_span_id: list[str] = []

        async def _async_work(tracer: ObservabilityTracer) -> str:
            inner = tracer.start_span("llm:async", kind="llm")
            await asyncio.sleep(0)
            tracer.finish_span(inner)
            return inner.parent_span_id or ""

        with fresh_tracer.trace("outer-sync") as outer:
            outer_task_span_id.append(outer.id)
            # Run async work — asyncio.run copies the current context
            # (which includes our trace context) into the new event loop.
            parent_id = asyncio.run(_async_work(fresh_tracer))
            assert parent_id == outer.id, (
                f"async llm-span should inherit parent from sync trace; "
                f"got {parent_id!r} expected {outer.id!r}"
            )

        spans = _read_spans(tmp_path / "spans.jsonl")
        assert len(spans) == 2
        # Sanity: we used contextvars above just to ensure the import is real
        # (defends against accidental removal in a future refactor).
        assert contextvars.ContextVar
