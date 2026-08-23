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


class TestRouteCliTopSkills:
    """gate38 L2a — CLI hit spans carry ``metadata.top_skills`` (≤3,
    primary first). Gated on the same expression as
    ``metadata["has_match"]`` — since gate40 项4 that expression is the
    hook-path verdict (primary real hit ∨ any real-skill plan step), NOT
    the mode-derived ``OrchestrationResult.has_match`` property — and
    read from the routing result object. On miss the CLI alternatives
    are fallback nearest-neighbours (result_mixin), not a router
    ranking → the key is omitted entirely.
    """

    @staticmethod
    def _metadata(span: dict) -> dict:
        meta = span.get("metadata") or {}
        return json.loads(meta) if isinstance(meta, str) else meta

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_hit_writes_top_skills_primary_first(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
        fresh_tracer: Path,
    ) -> None:
        from types import SimpleNamespace

        mock_stdin.isatty.return_value = False
        orch = mock_router._to_orchestration_result.return_value
        orch.alternatives = [
            SimpleNamespace(skill_id="alt-1"),
            SimpleNamespace(skill_id="alt-2"),
        ]
        mock_runtime_cls.return_value.router._router = mock_router

        query = "cmspark screenshot permission popup"
        mock_interceptor_cls.return_value = _make_interceptor(query)
        r = cli_runner.invoke(app, ["route", "--json", query])
        assert r.exit_code == 0, f"failed: {r.output}"

        route_spans = _read_route_spans(fresh_tracer)
        assert len(route_spans) == 1
        metadata = self._metadata(route_spans[0])
        assert metadata.get("has_match") is True
        assert metadata["top_skills"] == ["test-skill", "alt-1", "alt-2"]

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_top_skills_capped_at_three(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
        fresh_tracer: Path,
    ) -> None:
        from types import SimpleNamespace

        mock_stdin.isatty.return_value = False
        orch = mock_router._to_orchestration_result.return_value
        orch.alternatives = [SimpleNamespace(skill_id=f"alt-{i}") for i in range(4)]
        mock_runtime_cls.return_value.router._router = mock_router

        query = "cmspark screenshot permission popup"
        mock_interceptor_cls.return_value = _make_interceptor(query)
        r = cli_runner.invoke(app, ["route", "--json", query])
        assert r.exit_code == 0, f"failed: {r.output}"

        metadata = self._metadata(_read_route_spans(fresh_tracer)[0])
        assert metadata["top_skills"] == ["test-skill", "alt-0", "alt-1"]

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_miss_with_fallback_alternatives_omits_top_skills(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
        fresh_tracer: Path,
    ) -> None:
        from types import SimpleNamespace

        mock_stdin.isatty.return_value = False
        miss_orch = MagicMock()
        miss_orch.mode.value = "single"
        miss_orch.execution_plan = None
        miss_orch.primary = None
        miss_orch.has_match = False
        # Miss-path alternatives are fallback nearest-neighbours — they
        # must NOT be snapshotted as a ranking.
        miss_orch.alternatives = [SimpleNamespace(skill_id="fallback-nearest")]
        miss_orch.layer_details = []
        miss_orch.to_dict.return_value = {"mode": "single"}
        mock_router._to_orchestration_result.return_value = miss_orch
        mock_runtime_cls.return_value.router._router = mock_router

        query = "totally unroutable xyzzy query"
        mock_interceptor_cls.return_value = _make_interceptor(query)
        r = cli_runner.invoke(app, ["route", "--json", query])
        assert r.exit_code == 0, f"failed: {r.output}"

        metadata = self._metadata(_read_route_spans(fresh_tracer)[0])
        assert metadata.get("has_match") is False
        assert "top_skills" not in metadata

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_magicmock_alternative_does_not_leak(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
        fresh_tracer: Path,
    ) -> None:
        """A MagicMock alternative's auto-created skill_id (a MagicMock,
        not a str) must never reach span metadata — same guard convention
        as the layer write."""
        mock_stdin.isatty.return_value = False
        orch = mock_router._to_orchestration_result.return_value
        orch.alternatives = [MagicMock()]
        mock_runtime_cls.return_value.router._router = mock_router

        query = "cmspark screenshot permission popup"
        mock_interceptor_cls.return_value = _make_interceptor(query)
        r = cli_runner.invoke(app, ["route", "--json", query])
        assert r.exit_code == 0, f"failed: {r.output}"

        metadata = self._metadata(_read_route_spans(fresh_tracer)[0])
        assert metadata["top_skills"] == ["test-skill"]


class TestRouteCliFallbackSentinel:
    """gate40 项4 — CLI span metadata follows the hook-path verdict.

    The mode-derived ``OrchestrationResult.has_match`` property stays
    True on all-fallback orchestrated plans (result contract — JSON
    output / confirmation flow); the SPAN must instead write the real
    routing verdict: primary real hit ∨ any real-skill plan step.
    Miss rows always write ``skill_id=""`` — never the ``fallback-llm``
    sentinel.
    """

    @staticmethod
    def _metadata(span: dict) -> dict:
        meta = span.get("metadata") or {}
        return json.loads(meta) if isinstance(meta, str) else meta

    @staticmethod
    def _orchestrated_result(step_skill_ids: list[str]):
        from vibesop.core.models import (
            ExecutionPlan,
            ExecutionStep,
            OrchestrationMode,
            OrchestrationResult,
        )

        return OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            original_query="orchestrate this",
            execution_plan=ExecutionPlan(
                plan_id="plan-1",
                steps=[
                    ExecutionStep(
                        step_id=f"step-{i}",
                        step_number=i,
                        skill_id=sid,
                        intent=f"step {i}",
                    )
                    for i, sid in enumerate(step_skill_ids, start=1)
                ],
            ),
        )

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_all_fallback_orchestrated_writes_miss(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
        fresh_tracer: Path,
    ) -> None:
        """All-fallback plan → span has_match=False, skill_id="",
        top_skills absent — while the RESULT property stays True
        (property-unchanged pin: OrchestrationResult.has_match is the
        untouched result contract)."""
        mock_stdin.isatty.return_value = False
        orch_result = self._orchestrated_result(["fallback-llm", "fallback-llm"])
        mock_router.orchestrate.return_value = orch_result
        mock_runtime_cls.return_value.router._router = mock_router

        query = "deploy then notify the team"
        mock_interceptor_cls.return_value = _make_interceptor(
            query, mode=InterceptionMode.ORCHESTRATE
        )
        r = cli_runner.invoke(app, ["route", "--json", query])
        assert r.exit_code == 0, f"failed: {r.output}"

        route_spans = _read_route_spans(fresh_tracer)
        assert len(route_spans) == 1
        metadata = self._metadata(route_spans[0])
        assert metadata.get("has_match") is False
        assert metadata.get("skill_id") == ""
        assert "top_skills" not in metadata
        # Property pin: the result contract is deliberately unchanged —
        # the mode-derived property still says True on all-fallback plans.
        assert orch_result.has_match is True

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_first_fallback_then_real_step_writes_real_step(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
        fresh_tracer: Path,
    ) -> None:
        """First step fallback + second step real → span attributes the
        FIRST REAL step: skill_id=次步, top_skills[0]=次步, has_match=True."""
        mock_stdin.isatty.return_value = False
        orch_result = self._orchestrated_result(["fallback-llm", "real-skill"])
        mock_router.orchestrate.return_value = orch_result
        mock_runtime_cls.return_value.router._router = mock_router

        query = "deploy then notify the team"
        mock_interceptor_cls.return_value = _make_interceptor(
            query, mode=InterceptionMode.ORCHESTRATE
        )
        r = cli_runner.invoke(app, ["route", "--json", query])
        assert r.exit_code == 0, f"failed: {r.output}"

        metadata = self._metadata(_read_route_spans(fresh_tracer)[0])
        assert metadata.get("has_match") is True
        assert metadata.get("skill_id") == "real-skill"
        assert metadata["top_skills"][0] == "real-skill"

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_single_mode_miss_writes_empty_skill_id(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        mock_router: MagicMock,
        cli_runner: CliRunner,
        fresh_tracer: Path,
    ) -> None:
        """Single-mode miss: primary is the fallback-llm sentinel route
        (result_mixin) — the span must write skill_id="" (miss rows never
        carry the sentinel) with has_match=False."""
        from vibesop.core.models import (
            OrchestrationMode,
            OrchestrationResult,
            RoutingLayer,
            SkillRoute,
        )

        mock_stdin.isatty.return_value = False
        miss_orch = OrchestrationResult(
            mode=OrchestrationMode.SINGLE,
            original_query="totally unroutable xyzzy query",
            primary=SkillRoute(
                skill_id="fallback-llm",
                confidence=1.0,
                layer=RoutingLayer.FALLBACK_LLM,
                source="builtin",
            ),
        )
        mock_router._to_orchestration_result.return_value = miss_orch
        mock_runtime_cls.return_value.router._router = mock_router

        query = "totally unroutable xyzzy query"
        mock_interceptor_cls.return_value = _make_interceptor(query)
        r = cli_runner.invoke(app, ["route", "--json", query])
        assert r.exit_code == 0, f"failed: {r.output}"

        metadata = self._metadata(_read_route_spans(fresh_tracer)[0])
        assert metadata.get("has_match") is False
        assert metadata.get("skill_id") == ""
        assert "top_skills" not in metadata
