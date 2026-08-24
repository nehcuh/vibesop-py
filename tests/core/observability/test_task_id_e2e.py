"""W0.D end-to-end gate — verify vibe route writes task_id to spans.

This is the acceptance test for the v3 W0.D task: same query → same task_id
on the produced span, across two separate CLI invocations (simulating that
contextvars cannot carry across processes).

Uses AgentRuntime.handle_query directly (avoids full CLI boot, which would
require project init + LLM mocking) — same code path that the hook uses
and the same task_id derivation that main.py uses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibesop.agent.runtime import agent_runtime as _ar_module
from vibesop.agent.runtime.agent_runtime import AgentRuntime
from vibesop.core.observability import tracer as _tracer_module


@pytest.fixture(autouse=True)
def _fresh_tracer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset BOTH tracer singletons before each test.

    Two layers cache the tracer:
    1. ``tracer._tracer`` — the actual singleton
    2. ``agent_runtime._obs_tracer`` — module-level lazy cache that
       survives even after ``tracer._tracer`` is reset, returning a
       stale instance pointing at the old CWD/path.

    Resetting only #1 leaves #2 holding a dead reference, so tests that
    exercise AgentRuntime see spans routed to wherever the FIRST test
    in the session happened to chdir. Both must go.
    """
    _tracer_module._reset_tracer_for_tests()
    _ar_module._obs_tracer = None
    yield
    _tracer_module._reset_tracer_for_tests()
    _ar_module._obs_tracer = None


class TestTaskIdPropagation:
    def test_same_query_same_task_id_across_calls(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Force prod mode so spans go to spans.jsonl (not spans.dev.jsonl)
        monkeypatch.setenv("VIBESOP_OBSERVABILITY_MODE", "prod")
        monkeypatch.chdir(tmp_path)

        runtime = AgentRuntime(project_root=tmp_path)
        query = "CMspark.app screenshot permission popup keeps appearing"

        # Two separate handle_query calls — like two CLI invocations
        runtime.handle_query(query, platform="claude-code")
        runtime.handle_query(query, platform="claude-code")

        spans_file = tmp_path / ".vibe" / "observability" / "spans.jsonl"
        assert spans_file.exists(), f"spans file not created at {spans_file}"

        records: list[dict] = []
        with spans_file.open() as f:
            for raw_line in f:
                line = raw_line.strip()
                if line:
                    records.append(json.loads(line))

        # Find route spans (top-level task spans)
        route_spans = [r for r in records if r.get("name", "").startswith("route:")]
        assert len(route_spans) >= 2, f"expected ≥2 route spans, got {len(route_spans)}"

        # The W0.D contract: every route span has a task_id, and both are equal
        task_ids = [r.get("task_id") for r in route_spans]
        assert all(tid is not None for tid in task_ids), (
            f"some route spans missing task_id: {task_ids}"
        )
        assert len(set(task_ids)) == 1, f"expected same task_id across calls, got: {task_ids}"

    def test_different_queries_different_task_ids(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VIBESOP_OBSERVABILITY_MODE", "prod")
        monkeypatch.chdir(tmp_path)

        runtime = AgentRuntime(project_root=tmp_path)

        runtime.handle_query("screenshot permission popup", platform="claude-code")
        runtime.handle_query("lid sleep overheating issue", platform="claude-code")

        spans_file = tmp_path / ".vibe" / "observability" / "spans.jsonl"
        records: list[dict] = []
        with spans_file.open() as f:
            for raw_line in f:
                line = raw_line.strip()
                if line:
                    records.append(json.loads(line))

        route_spans = [r for r in records if r.get("name", "").startswith("route:")]
        task_ids = [r.get("task_id") for r in route_spans]

        assert all(tid is not None for tid in task_ids)
        assert len(set(task_ids)) == 2, (
            f"expected 2 distinct task_ids for different queries, got: {task_ids}"
        )

    def test_task_id_is_16_hex_chars(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VIBESOP_OBSERVABILITY_MODE", "prod")
        monkeypatch.chdir(tmp_path)

        runtime = AgentRuntime(project_root=tmp_path)
        runtime.handle_query("some test query for task_id format", platform="claude-code")

        spans_file = tmp_path / ".vibe" / "observability" / "spans.jsonl"
        with spans_file.open() as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                r = json.loads(line)
                if r.get("name", "").startswith("route:"):
                    tid = r.get("task_id")
                    assert tid is not None
                    assert len(tid) == 16, f"task_id not 16 chars: {tid!r}"
                    assert all(c in "0123456789abcdef" for c in tid), f"task_id not hex: {tid!r}"
                    return

        pytest.fail("no route span found in output")


# Note: dev/prod routing is covered by test_span_writer_dev_routing.py at the
# unit level. Verifying it end-to-end through AgentRuntime requires resetting
# the tracer singleton (its path is captured at first construction), which
# would couple this gate test to internal lifecycle. The unit test is the
# right place for that assertion.
