"""Tests for orchestration_id writeback to conversation metadata (v3 Phase A Task 5).

The dashboard needs to join conversation sessions to orchestration traces
across process boundaries. ``contextvars`` does NOT cross process boundaries
(sub-agent execution runs as a separate OS process), so the join must happen
via persisted metadata: the conversation JSON file records the
``orchestration_id`` (= plan_id) + ``orchestration_trace_id`` so the DAG
rebuilder can later match conversation ↔ plan ↔ spans.

Uses short queries + disabled orchestration to avoid real LLM calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from vibesop.core.observability.tracer import ObservabilityTracer
from vibesop.core.routing import UnifiedRouter


@pytest.fixture
def fresh_tracer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ObservabilityTracer:
    """Reset the module-level observability tracer singleton to write into tmp_path."""
    import vibesop.core.observability.tracer as tracer_mod

    span_file = tmp_path / "observability" / "spans.jsonl"
    span_file.parent.mkdir(parents=True, exist_ok=True)
    fresh = ObservabilityTracer(storage_path=span_file, enabled=True)
    monkeypatch.setattr(tracer_mod, "_tracer", fresh)
    return fresh


def _read_conversation(path: Path) -> dict[str, Any]:
    assert path.exists(), f"conversation file not written: {path}"
    with path.open() as f:
        return json.load(f)


class TestOrchestrationIdWriteback:
    """orchestrate() must persist orchestration_id + trace_id into the
    conversation metadata file so the dashboard can join across processes."""

    def test_writes_orchestration_id_and_trace_id_to_conversation(
        self,
        fresh_tracer: ObservabilityTracer,
        tmp_path: Path,
    ) -> None:
        """When orchestrate() is called with conversation_id, the resulting
        conversation JSON must include orchestration_id + orchestration_trace_id
        in its metadata."""
        router = UnifiedRouter(project_root=tmp_path)
        result = router.orchestrate(
            "help",
            conversation_id="conv-abc-123",
            storage_dir=tmp_path / "conversations",
        )

        # Single-path orchestrate (short query) won't build a plan; but the
        # writeback must still record the trace_id (and orchestration_id=None
        # is acceptable when no plan was built).
        conv = _read_conversation(tmp_path / "conversations" / "conv-abc-123.json")
        assert "metadata" in conv, "conversation file must have metadata section"
        meta = conv["metadata"]
        assert "orchestration_trace_id" in meta, f"orchestration_trace_id missing from {meta}"
        assert meta["orchestration_trace_id"], f"orchestration_trace_id must be non-None: {meta}"

        # orchestration_id is only set when a plan was built (multi-intent path)
        if result.execution_plan is not None:
            assert meta["orchestration_id"] == result.execution_plan.plan_id, (
                f"orchestration_id={meta.get('orchestration_id')} "
                f"expected plan_id={result.execution_plan.plan_id}"
            )

    def test_trace_id_matches_span_trace_id(
        self,
        fresh_tracer: ObservabilityTracer,
        tmp_path: Path,
    ) -> None:
        """The orchestration_trace_id written to conversation metadata must
        equal the trace_id of the root 'orchestrate' span — otherwise the
        dashboard cannot join conversation ↔ spans."""
        router = UnifiedRouter(project_root=tmp_path)
        router.orchestrate(
            "help",
            conversation_id="conv-trace-match",
            storage_dir=tmp_path / "conversations",
        )

        # Read spans + conversation
        spans_path = tmp_path / "observability" / "spans.jsonl"
        spans = [json.loads(line) for line in spans_path.read_text().splitlines() if line.strip()]
        root_spans = [s for s in spans if s["name"] == "orchestrate"]
        assert root_spans, "root 'orchestrate' span must be emitted"
        root_trace_id = root_spans[0]["trace_id"]

        conv = _read_conversation(tmp_path / "conversations" / "conv-trace-match.json")
        assert conv["metadata"]["orchestration_trace_id"] == root_trace_id, (
            f"conversation trace_id={conv['metadata']['orchestration_trace_id']!r} "
            f"≠ span trace_id={root_trace_id!r}"
        )

    def test_no_conversation_id_skips_writeback(
        self,
        fresh_tracer: ObservabilityTracer,
        tmp_path: Path,
    ) -> None:
        """Backward-compat: orchestrate() without conversation_id must not
        write any conversation file (no behavior change for existing callers)."""
        router = UnifiedRouter(project_root=tmp_path)
        router.orchestrate("help")

        conv_dir = tmp_path / "conversations"
        if conv_dir.exists():
            files = list(conv_dir.iterdir())
            assert not files, f"unexpected conversation files written: {files}"

    def test_writeback_failure_does_not_break_orchestrate(
        self,
        fresh_tracer: ObservabilityTracer,
        tmp_path: Path,
    ) -> None:
        """If the conversation file write fails (e.g. permission denied),
        orchestrate() must still return successfully — writeback is best-effort."""
        router = UnifiedRouter(project_root=tmp_path)
        # Use an invalid storage_dir (parent is a file, not a directory)
        invalid_dir = tmp_path / "blocker"
        invalid_dir.write_text("I am a file, not a directory")

        # Must not raise
        result = router.orchestrate(
            "help",
            conversation_id="conv-robust",
            storage_dir=invalid_dir / "conversations",
        )
        assert result is not None
