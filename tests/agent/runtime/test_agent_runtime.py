"""Tests for AgentRuntime async dispatch (Phase 4)."""

from __future__ import annotations

import pytest

from vibesop.agent.runtime.agent_runtime import AgentRuntime, AgentRuntimeResult
from vibesop.agent.runtime.intent_interceptor import InterceptionMode


class TestAgentRuntimeProcessQuery:
    """Async process_query dispatch by InterceptionMode."""

    @pytest.mark.asyncio
    async def test_process_query_not_intercepted(self) -> None:
        runtime = AgentRuntime()
        result = await runtime.process_query("hi")

        assert result["intercepted"] is False
        assert result["query"] == "hi"

    @pytest.mark.asyncio
    async def test_process_query_single(self) -> None:
        runtime = AgentRuntime()
        result = await runtime.process_query("review my code")

        assert result["intercepted"] is True
        assert result["mode"] == InterceptionMode.SINGLE.value
        assert "primary" in result

    @pytest.mark.asyncio
    async def test_process_query_single_agent(self) -> None:
        runtime = AgentRuntime()
        # Short query with architect role promotes to SINGLE_AGENT
        result = await runtime.process_query("Design the architecture for a new service")

        assert result["intercepted"] is True
        assert result["mode"] == InterceptionMode.SINGLE_AGENT.value
        assert "role" in result
        assert "skills" in result
        assert result["role"] == "architect"
        assert isinstance(result["skills"], list)

    @pytest.mark.asyncio
    async def test_process_query_multi_agent_squad(self) -> None:
        runtime = AgentRuntime()
        # Explicit multi-agent keyword with multiple facets
        result = await runtime.process_query(
            "multi-agent: design the payment architecture, implement the service, and perform a security audit"
        )

        assert result["intercepted"] is True
        assert result["mode"] == InterceptionMode.MULTI_AGENT_SQUAD.value
        assert "analysis" in result
        assert result["analysis"]["squad_needed"] is True
        assert len(result["analysis"]["suggested_roles"]) >= 2

    @pytest.mark.asyncio
    async def test_process_query_orchestrate(self) -> None:
        runtime = AgentRuntime()
        # Multi-intent marker should keep legacy ORCHESTRATE behavior
        result = await runtime.process_query("分析项目架构并优化整体性能")

        assert result["intercepted"] is True
        assert result["mode"] == InterceptionMode.ORCHESTRATE.value
        assert "is_multi_intent" in result

    @pytest.mark.asyncio
    async def test_orchestrate_path_backward_compatible(self) -> None:
        runtime = AgentRuntime()
        result = await runtime.process_query("分析项目架构并优化整体性能")

        # Should not raise and should contain expected keys
        assert isinstance(result, dict)
        assert "intercepted" in result
        assert "mode" in result


class TestAgentRuntimeBackwardCompat:
    """Existing handle_query API remains unchanged."""

    def test_handle_query_still_works(self) -> None:
        runtime = AgentRuntime()
        result = runtime.handle_query("review my code")

        from vibesop.agent.runtime.agent_runtime import AgentRuntimeResult

        assert isinstance(result, AgentRuntimeResult)
        assert isinstance(result.to_hook_json(), str)

    def test_handle_query_short_query_not_intercepted(self) -> None:
        runtime = AgentRuntime()
        result = runtime.handle_query("hi")

        assert result.intercepted is False
        assert result.mode == "none"

    def test_handle_query_slash_command(self) -> None:
        runtime = AgentRuntime()
        result = runtime.handle_query("/vibe-help")

        assert result.intercepted is True
        assert result.mode == "slash_command"


class TestAgentRuntimeHookResponseHintPath:
    """NEXT STEP hint in to_hook_response must match real on-disk layout."""

    def _make_result(self, skill_id: str) -> AgentRuntimeResult:
        from vibesop.agent.runtime.agent_runtime import AgentRuntimeResult

        return AgentRuntimeResult(
            intercepted=True,
            mode="single",
            skill_id=skill_id,
            confidence=0.54,
        )

    def test_hint_path_for_builtin_skill(self) -> None:
        """builtin/xxx → core/skills/{xxx}/SKILL.md (no 'builtin-' prefix)."""
        result = self._make_result("builtin/deep-diagnosis-optimization")
        response = result.to_hook_response(no_match_message=False)
        assert "core/skills/deep-diagnosis-optimization/SKILL.md" in response
        assert "builtin-deep-diagnosis-optimization" not in response

    def test_hint_path_for_builtin_uses_absolute_path_from_bundle(
        self, tmp_path, monkeypatch
    ) -> None:
        """When project_root/core/skills/ is absent, hint must point to the
        bundled data dir via sys.path scan — and be absolute so Claude can
        Read it from any CWD."""

        site_packages = tmp_path / "site-packages"
        bundled = (
            site_packages
            / "vibesop"
            / "builtin_skills"
            / "deep-diagnosis-optimization"
            / "SKILL.md"
        )
        bundled.parent.mkdir(parents=True)
        bundled.write_text("# bundled", encoding="utf-8")
        monkeypatch.syspath_prepend(str(site_packages))

        from vibesop.agent.runtime.agent_runtime import AgentRuntimeResult

        result = AgentRuntimeResult(
            intercepted=True,
            mode="single",
            skill_id="builtin/deep-diagnosis-optimization",
            confidence=0.55,
            project_root=tmp_path / "user_project",  # has no core/skills
        )
        response = result.to_hook_response(no_match_message=False)
        assert bundled.as_posix() in response
        # Sanity: still mentions the skill name
        assert "deep-diagnosis-optimization" in response

    def test_hint_path_for_external_pack_keeps_flat(self) -> None:
        """gstack/yyy → skills/{gstack-yyy}/SKILL.md (pack-prefixed flat dir)."""
        result = self._make_result("gstack/review")
        response = result.to_hook_response(no_match_message=False)
        assert "skills/gstack-review/SKILL.md" in response

    def test_hint_path_for_bare_id(self) -> None:
        """Bare id (no namespace) → skills/{id}/SKILL.md."""
        result = self._make_result("diagnose")
        response = result.to_hook_response(no_match_message=False)
        assert "skills/diagnose/SKILL.md" in response


class TestAgentRuntimeLayerMetadata:
    """gate18 pi NIT-4 — hook-path route spans carry ``metadata.layer``.

    Match → winning layer (``primary.layer``); miss → deepest cascade
    layer (``layer_details[-1]``). Mirrors the CLI-path tests in
    ``tests/cli/test_route_cli_task_id.py``.
    """

    @pytest.fixture
    def fresh_tracer(self, tmp_path, monkeypatch):
        """Point the tracer singleton (and the agent_runtime cache) at tmp_path."""
        import vibesop.core.observability.tracer as tracer_mod
        from vibesop.agent.runtime import agent_runtime as ar_module
        from vibesop.core.observability.tracer import ObservabilityTracer

        span_file = tmp_path / "spans.jsonl"
        fresh = ObservabilityTracer(storage_path=span_file, enabled=True)
        monkeypatch.setattr(tracer_mod, "_tracer", fresh)
        monkeypatch.setattr(ar_module, "_obs_tracer", None, raising=False)
        return span_file

    def _route_spans(self, span_file) -> list[dict]:
        import json

        spans = []
        with span_file.open() as f:
            for raw in f:
                if raw.strip():
                    span = json.loads(raw)
                    # SpanWriter serialises metadata as a JSON string.
                    meta = span.get("metadata")
                    if isinstance(meta, str):
                        span["metadata"] = json.loads(meta)
                    spans.append(span)
        return [s for s in spans if str(s.get("name", "")).startswith("route:")]

    def _mock_router(self, routing_result) -> None:
        from unittest.mock import MagicMock

        router = MagicMock()
        router.route.return_value = routing_result
        return router

    def test_match_writes_winning_layer(self, fresh_tracer, tmp_path) -> None:
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from vibesop.core.models import RoutingLayer

        routing_result = MagicMock()
        routing_result.has_match = True
        routing_result.primary = SimpleNamespace(
            skill_id="some-skill",
            skill_name="Some Skill",
            confidence=0.9,
            layer=RoutingLayer.KEYWORD,
        )
        routing_result.alternatives = []
        routing_result.plan = None

        runtime = AgentRuntime(project_root=tmp_path)
        runtime._router = self._mock_router(routing_result)
        runtime.handle_query("review my code")

        spans = self._route_spans(fresh_tracer)
        assert len(spans) == 1
        metadata = spans[0].get("metadata") or {}
        assert metadata.get("has_match") is True
        assert metadata.get("layer") == "keyword"

    def test_miss_writes_deepest_cascade_layer(self, fresh_tracer, tmp_path) -> None:
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from vibesop.core.models import RoutingLayer

        routing_result = MagicMock()
        routing_result.has_match = False
        routing_result.primary = None
        routing_result.layer_details = [SimpleNamespace(layer=RoutingLayer.EMBEDDING)]

        runtime = AgentRuntime(project_root=tmp_path)
        runtime._router = self._mock_router(routing_result)
        runtime.handle_query("review my code")

        spans = self._route_spans(fresh_tracer)
        assert len(spans) == 1
        metadata = spans[0].get("metadata") or {}
        # NOTE: metadata.has_match comes from AgentRuntimeResult.has_match,
        # which is mode-derived (intercepted + single) — not from the
        # router's no-match. Pre-existing semantics, out of scope here;
        # what gate18 adds is the layer attribution on router-level miss.
        assert metadata.get("layer") == "embedding"

    def test_miss_without_layer_details_omits_field(self, fresh_tracer, tmp_path) -> None:
        """No layer info at all → field omitted (consumer buckets as unknown)."""
        from unittest.mock import MagicMock

        routing_result = MagicMock()
        routing_result.has_match = False
        routing_result.primary = None
        routing_result.layer_details = []

        runtime = AgentRuntime(project_root=tmp_path)
        runtime._router = self._mock_router(routing_result)
        runtime.handle_query("review my code")

        spans = self._route_spans(fresh_tracer)
        assert len(spans) == 1
        metadata = spans[0].get("metadata") or {}
        assert "layer" not in metadata
