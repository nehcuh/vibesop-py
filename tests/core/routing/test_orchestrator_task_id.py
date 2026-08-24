"""Test that ``Orchestrator.orchestrate()`` opens its root span with a
derived task_id (W5.0.A.5).

Pre-W5.0 the orchestrate root span had task_id=None → all child spans
(llm, phase workflow_node) inherited None → recall couldn't attribute
orchestrate-path spans to a task_id.

W5.0.A.5 fix: derive_task_id(query) at the trace() call. session_id and
project_id default via process_identity (set by CLI entry point in the
production path; in tests they fall back to None / "default").
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibesop.core.observability import process_identity
from vibesop.core.observability.task_id import derive_task_id
from vibesop.core.observability.tracer import ObservabilityTracer
from vibesop.core.routing import UnifiedRouter


@pytest.fixture
def fresh_tracer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ObservabilityTracer:
    """Reset the tracer singleton to write into tmp_path."""
    import vibesop.core.observability.tracer as tracer_mod

    span_file = tmp_path / "observability" / "spans.jsonl"
    span_file.parent.mkdir(parents=True, exist_ok=True)
    fresh = ObservabilityTracer(storage_path=span_file, enabled=True)
    monkeypatch.setattr(tracer_mod, "_tracer", fresh)
    return fresh


@pytest.fixture(autouse=True)
def reset_process_identity():
    """Clear process_identity between tests so state doesn't leak."""
    saved_session = process_identity._process_session_id
    saved_project = process_identity._process_project_id
    process_identity._process_session_id = None
    process_identity._process_project_id = None
    yield
    process_identity._process_session_id = saved_session
    process_identity._process_project_id = saved_project


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


def test_orchestrate_root_span_carries_derived_task_id(
    fresh_tracer: ObservabilityTracer, tmp_path: Path
) -> None:
    """orchestrate(query) must emit root span with task_id = derive_task_id(query).

    Without this, all child spans (phases, llm calls) inherit task_id=None,
    breaking recall attribution for the orchestrate code path.
    """
    router = UnifiedRouter(project_root=tmp_path)
    query = "review my code"
    expected_task_id = derive_task_id(query)

    router.orchestrate(query)

    spans = _read_spans(tmp_path / "observability" / "spans.jsonl")
    root = next(s for s in spans if s["name"] == "orchestrate")
    assert root["task_id"] == expected_task_id


def test_orchestrate_child_spans_inherit_task_id(
    fresh_tracer: ObservabilityTracer, tmp_path: Path
) -> None:
    """Phase workflow_node spans emitted under orchestrate() must inherit
    the derived task_id from TraceContext."""
    router = UnifiedRouter(project_root=tmp_path)
    query = "refactor my module"
    expected_task_id = derive_task_id(query)

    router.orchestrate(query)

    spans = _read_spans(tmp_path / "observability" / "spans.jsonl")
    phase_spans = [s for s in spans if s["span_kind"] == "workflow_node"]
    assert phase_spans, "expected at least one phase workflow_node span"
    for s in phase_spans:
        assert s["task_id"] == expected_task_id
