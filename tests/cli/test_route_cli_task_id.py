"""CLI ``vibe route`` task_id smoke — gates W0.D acceptance criterion.

Design said: "vibe route <q> 两次，spans.jsonl 新条目 100% 有 task_id，两次
同 query 同 task_id". The AgentRuntime.handle_query e2e in
``tests/core/observability/test_task_id_e2e.py`` covers the hook path;
this file covers the **CLI** path end-to-end via ``CliRunner``.

Both paths call the same ``derive_task_id`` helper, but reviewers asked
for explicit CLI execution (not just inspection of the 1-line wiring).
"""

from __future__ import annotations

import json
from pathlib import Path
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

    Also clears the agent_runtime module-level cache (``_obs_tracer``)
    which otherwise survives the tracer singleton reset and returns a
    stale instance pointing at the previous CWD/path.
    """
    import vibesop.core.observability.tracer as tracer_mod
    from vibesop.agent.runtime import agent_runtime as ar_module

    span_file = tmp_path / "spans.jsonl"
    fresh = ObservabilityTracer(storage_path=span_file, enabled=True)
    monkeypatch.setattr(tracer_mod, "_tracer", fresh)
    monkeypatch.setattr(ar_module, "_obs_tracer", None, raising=False)
    return span_file


@pytest.fixture
def mock_router() -> MagicMock:
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


def _make_interceptor(query: str, mode: InterceptionMode = InterceptionMode.SINGLE) -> MagicMock:
    decision = MagicMock()
    decision.should_route = True
    decision.mode = mode
    decision.query = query
    decision.reason = "test"
    decision.analysis = None
    interceptor = MagicMock()
    interceptor.should_intercept.return_value = decision
    return interceptor


def _read_route_spans(path: Path) -> list[dict]:
    if not path.exists():
        return []
    spans: list[dict] = []
    with path.open() as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if stripped:
                spans.append(json.loads(stripped))
    return [s for s in spans if s.get("name", "").startswith("route:")]


class TestRouteCliTaskId:
    """CLI ``vibe route`` must persist a task_id derived from the query."""

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_same_query_same_task_id_via_cli(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
        fresh_tracer: Path,
    ) -> None:
        """Two CLI invocations of the same query must produce the same task_id."""
        mock_stdin.isatty.return_value = False
        query = "CMspark screenshot permission popup keeps appearing"

        # First invocation
        mock_interceptor_cls.return_value = _make_interceptor(query)
        mock_runtime_cls.return_value.router._router = mock_router
        r1 = cli_runner.invoke(app, ["route", "--json", query])
        assert r1.exit_code == 0, f"first invoke failed: {r1.output}"

        # Second invocation — fresh interceptor with SAME query
        mock_interceptor_cls.return_value = _make_interceptor(query)
        r2 = cli_runner.invoke(app, ["route", "--json", query])
        assert r2.exit_code == 0, f"second invoke failed: {r2.output}"

        route_spans = _read_route_spans(fresh_tracer)
        assert len(route_spans) == 2, f"expected 2 route spans, got {len(route_spans)}"

        task_ids = [s.get("task_id") for s in route_spans]
        assert all(tid is not None for tid in task_ids), (
            f"some route spans missing task_id: {task_ids}"
        )
        assert len(set(task_ids)) == 1, (
            f"same query must produce same task_id across CLI invocations, got: {task_ids}"
        )

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_different_queries_different_task_ids_via_cli(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
        fresh_tracer: Path,
    ) -> None:
        mock_stdin.isatty.return_value = False
        mock_runtime_cls.return_value.router._router = mock_router

        for q in ("screenshot permission popup", "lid sleep overheating"):
            mock_interceptor_cls.return_value = _make_interceptor(q)
            r = cli_runner.invoke(app, ["route", "--json", q])
            assert r.exit_code == 0

        route_spans = _read_route_spans(fresh_tracer)
        task_ids = [s.get("task_id") for s in route_spans]
        assert all(tid is not None for tid in task_ids)
        assert len(set(task_ids)) == 2, (
            f"distinct queries must yield distinct task_ids, got: {task_ids}"
        )


class TestRouteCliLayerMetadata:
    """gate18 pi NIT-4 — CLI route spans carry ``metadata.layer``.

    Semantics: match → winning layer (``primary.layer``); miss → deepest
    cascade layer (``layer_details[-1]``). Feeds
    ``ScanSummary.miss_share_by_layer``.
    """

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_match_writes_winning_layer(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
        fresh_tracer: Path,
    ) -> None:
        from vibesop.core.models import RoutingLayer

        mock_stdin.isatty.return_value = False
        mock_router.route.return_value.primary.layer = RoutingLayer.SEMANTIC_INDEX
        mock_runtime_cls.return_value.router._router = mock_router

        query = "cmspark screenshot permission popup"
        mock_interceptor_cls.return_value = _make_interceptor(query)
        r = cli_runner.invoke(app, ["route", "--json", query])
        assert r.exit_code == 0, f"failed: {r.output}"

        route_spans = _read_route_spans(fresh_tracer)
        assert len(route_spans) == 1
        metadata = route_spans[0].get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        assert metadata.get("layer") == "semantic_index"

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_miss_writes_deepest_cascade_layer(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
        fresh_tracer: Path,
    ) -> None:
        from types import SimpleNamespace

        from vibesop.core.models import RoutingLayer

        mock_stdin.isatty.return_value = False
        # Miss: no primary, but the cascade recorded its deepest layer.
        miss_orch = MagicMock()
        miss_orch.mode.value = "single"
        miss_orch.execution_plan = None
        miss_orch.primary = None
        miss_orch.has_match = False
        miss_orch.layer_details = [
            SimpleNamespace(layer=RoutingLayer.LEVENSHTEIN),
        ]
        miss_orch.to_dict.return_value = {"mode": "single"}
        mock_router._to_orchestration_result.return_value = miss_orch
        mock_runtime_cls.return_value.router._router = mock_router

        query = "totally unroutable xyzzy query"
        mock_interceptor_cls.return_value = _make_interceptor(query)
        r = cli_runner.invoke(app, ["route", "--json", query])
        assert r.exit_code == 0, f"failed: {r.output}"

        route_spans = _read_route_spans(fresh_tracer)
        assert len(route_spans) == 1
        metadata = route_spans[0].get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        assert metadata.get("has_match") is False
        assert metadata.get("layer") == "levenshtein"
