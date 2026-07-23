"""Regression tests for CLI ``vibe route`` observability wrap.

Verifies that ``vibe route`` opens a top-level trace span so that:
1. A task span is persisted with skill_id / mode metadata after dispatch.
2. Any llm-span emitted inside the routing flow is nested under the task
   span (not orphaned).

Regression for the v8.2 P2 finding: CLI path originally skipped
``tracer.trace()`` (only the hook path via ``agent_runtime.handle_query``
opened one), so CLI-routed llm-spans had no task parent and SpanAggregator
couldn't attribute them to a skill via trace_id.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from vibesop.agent.runtime import InterceptionMode
from vibesop.cli.main import app
from vibesop.core.observability.tracer import ObservabilityTracer


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def fresh_tracer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Reset the tracer singleton to write into tmp_path.

    Returns the spans.jsonl path so tests can read back what was written.
    """
    import vibesop.core.observability.tracer as tracer_mod

    span_file = tmp_path / "spans.jsonl"
    fresh = ObservabilityTracer(storage_path=span_file, enabled=True)
    monkeypatch.setattr(tracer_mod, "_tracer", fresh)
    return span_file


@pytest.fixture
def mock_router() -> MagicMock:
    """Mock UnifiedRouter-like object returning a controlled routing result."""
    router = MagicMock()

    routing_result = MagicMock()
    routing_result.primary = MagicMock(skill_id="test-skill")
    routing_result.alternatives = []
    routing_result.routing_path = []
    routing_result.layer_details = []
    routing_result.duration_ms = 0.0
    router.route.return_value = routing_result

    single_orch = MagicMock()
    single_orch.mode.value = "single"
    single_orch.execution_plan = None
    single_orch.primary = routing_result.primary
    single_orch.has_match = True
    single_orch.to_dict.return_value = {"mode": "single"}
    router._to_orchestration_result.return_value = single_orch
    return router


def _make_interceptor_mock(mode: InterceptionMode) -> MagicMock:
    decision = MagicMock()
    decision.should_route = True
    decision.mode = mode
    decision.query = "test query for trace"
    decision.reason = "test"
    decision.analysis = None
    interceptor = MagicMock()
    interceptor.should_intercept.return_value = decision
    return interceptor


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


class TestRouteCliTraceWrap:
    """CLI vibe route must open a task span around the routing dispatch."""

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_single_mode_emits_task_span_with_skill(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
        fresh_tracer: Path,
    ) -> None:
        """SINGLE dispatch must persist a task span with skill_id metadata."""
        mock_stdin.isatty.return_value = False
        mock_interceptor_cls.return_value = _make_interceptor_mock(InterceptionMode.SINGLE)
        mock_runtime_cls.return_value.router._router = mock_router

        result = cli_runner.invoke(app, ["route", "--json", "test query for trace"])

        assert result.exit_code == 0
        spans = _read_spans(fresh_tracer)
        task_spans = [s for s in spans if s["span_kind"] == "task"]
        assert len(task_spans) == 1, f"expected 1 task span, got {len(task_spans)}"

        task = task_spans[0]
        assert task["name"].startswith("route:"), (
            f'task name should start with "route:", got {task["name"]!r}'
        )
        assert task["agent_id"] == "vibe-cli"
        meta = json.loads(task.get("metadata") or "{}")
        assert meta.get("skill_id") == "test-skill", (
            f'skill_id should be set after dispatch, got {meta.get("skill_id")!r}'
        )
        assert meta.get("source") == "cli"
        assert meta.get("mode") == "single"

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_llm_span_inside_routing_is_nested(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
        fresh_tracer: Path,
    ) -> None:
        """An llm-span emitted inside the routing flow must have the task
        span as parent (not be orphaned).

        Simulates an inner LLM call by manually emitting a span via the
        same tracer inside a wrapped router.route() — the cheapest way to
        prove the parent linkage without a real LLM round-trip.
        """
        from vibesop.core.observability.tracer import get_tracer

        mock_stdin.isatty.return_value = False
        mock_interceptor_cls.return_value = _make_interceptor_mock(InterceptionMode.SINGLE)
        mock_runtime_cls.return_value.router._router = mock_router

        def _route_with_inner_llm(*_args: Any, **_kwargs: Any) -> Any:
            # Simulate SpanWrappedProvider's emission path: this is exactly
            # what happens when an llm-span is opened while a trace is active.
            tracer = get_tracer()
            inner = tracer.start_span("llm:fake:model", kind="llm")
            try:
                tracer.finish_span(inner)
            except Exception:
                tracer.fail_span(inner, "test error")
                raise
            return mock_router.route.return_value

        mock_router.route.side_effect = _route_with_inner_llm

        result = cli_runner.invoke(app, ["route", "--json", "test query for trace"])

        assert result.exit_code == 0
        spans = _read_spans(fresh_tracer)

        task_spans = [s for s in spans if s["span_kind"] == "task"]
        llm_spans = [s for s in spans if s["span_kind"] == "llm"]
        assert len(task_spans) == 1
        assert len(llm_spans) == 1

        task = task_spans[0]
        llm = llm_spans[0]

        # Critical assertion: llm-span's parent must be the task span.
        assert llm["parent_span_id"] == task["id"], (
            f"llm-span should be nested under task span. "
            f"llm.parent={llm['parent_span_id']!r} task.id={task['id']!r}"
        )
        # And both spans share the same trace_id (attribution linkage).
        assert llm["trace_id"] == task["trace_id"], (
            f"llm-span and task span should share trace_id. "
            f"llm.trace_id={llm['trace_id']!r} task.trace_id={task['trace_id']!r}"
        )

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_no_route_decision_does_not_emit_task_span(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
        fresh_tracer: Path,
    ) -> None:
        """When the interceptor decides NOT to route (should_route=False),
        no task span should be emitted — the early-exit precedes the trace."""
        mock_stdin.isatty.return_value = False

        decision = MagicMock()
        decision.should_route = False
        decision.mode = InterceptionMode.SINGLE
        decision.query = "test"
        decision.reason = "fallback"
        interceptor = MagicMock()
        interceptor.should_intercept.return_value = decision
        mock_interceptor_cls.return_value = interceptor
        mock_runtime_cls.return_value.router._router = mock_router

        result = cli_runner.invoke(app, ["route", "--json", "test"])

        assert result.exit_code == 0
        spans = _read_spans(fresh_tracer)
        assert spans == [], (
            f"no task span expected when should_route=False, got {len(spans)} spans"
        )
