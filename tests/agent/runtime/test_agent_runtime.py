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
        # Post-fix (miss blind spot): the span now carries the router's
        # real verdict via router_matched — a router-level miss writes
        # has_match=False even though the mode-derived property stays True.
        assert metadata.get("has_match") is False
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


class TestRouterMatchedSpanVerdict:
    """M12 hook-path miss blind-spot fix — spans carry the router's real
    verdict (``router_matched``), so ``is_route_miss_span`` can see
    hook-path misses. The mode-derived ``has_match`` property is
    unchanged for its existing consumers.
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

    def _route_span(self, span_file) -> dict:
        import json

        spans = []
        with span_file.open() as f:
            for raw in f:
                if raw.strip():
                    spans.append(json.loads(raw))
        route_spans = [s for s in spans if str(s.get("name", "")).startswith("route:")]
        assert len(route_spans) == 1, f"expected 1 route span, got {len(route_spans)}"
        return route_spans[0]

    @staticmethod
    def _metadata(span: dict) -> dict:
        import json

        meta = span.get("metadata") or {}
        return json.loads(meta) if isinstance(meta, str) else meta

    def _miss_router(self, *, matched: bool):
        from unittest.mock import MagicMock

        routing_result = MagicMock()
        routing_result.has_match = matched
        routing_result.primary = None
        routing_result.layer_details = []
        if matched:
            from types import SimpleNamespace

            from vibesop.core.models import RoutingLayer

            routing_result.primary = SimpleNamespace(
                skill_id="some-skill",
                skill_name="Some Skill",
                confidence=0.9,
                layer=RoutingLayer.KEYWORD,
            )
            routing_result.alternatives = []
            routing_result.plan = None
        router = MagicMock()
        router.route.return_value = routing_result
        return router

    def test_hook_miss_enters_miss_predicate(self, fresh_tracer, tmp_path) -> None:
        from vibesop.core.observability.gold_detection import is_route_miss_span

        runtime = AgentRuntime(project_root=tmp_path)
        runtime._router = self._miss_router(matched=False)
        runtime.handle_query("review my code")

        span = self._route_span(fresh_tracer)
        metadata = self._metadata(span)
        assert metadata.get("has_match") is False
        # Genuine hook-path miss: mode stays "single" (set from the
        # interception decision before routing) — NOT "not_intercepted",
        # so the miss predicate accepts it without any predicate widening.
        assert metadata.get("mode") == "single"
        assert is_route_miss_span(span) is True

    def test_hook_match_stays_out_of_miss_pool(self, fresh_tracer, tmp_path) -> None:
        from vibesop.core.observability.gold_detection import is_route_miss_span

        runtime = AgentRuntime(project_root=tmp_path)
        runtime._router = self._miss_router(matched=True)
        runtime.handle_query("review my code")

        span = self._route_span(fresh_tracer)
        metadata = self._metadata(span)
        assert metadata.get("has_match") is True
        assert is_route_miss_span(span) is False

    def _orchestrate_runtime(self, tmp_path, orch_result: dict):
        from unittest.mock import MagicMock

        from vibesop.agent.runtime import InterceptionMode

        decision = MagicMock()
        decision.should_route = True
        decision.mode = InterceptionMode.ORCHESTRATE
        decision.analysis = None
        decision.query = "orchestrate this"
        decision.reason = "test"
        interceptor = MagicMock()
        interceptor.should_intercept.return_value = decision

        router = MagicMock()
        router.orchestrate.return_value = orch_result

        runtime = AgentRuntime(project_root=tmp_path)
        runtime._interceptor = interceptor
        runtime._router = router
        return runtime

    def test_orchestrate_single_miss(self, fresh_tracer, tmp_path) -> None:
        """single_result with empty skill_id (agent/__init__ builds it as
        ``primary.skill_id if has_match else None``) → real miss."""
        from vibesop.core.observability.gold_detection import is_route_miss_span

        runtime = self._orchestrate_runtime(
            tmp_path,
            {
                "is_multi_intent": False,
                "single_result": {"skill_id": None, "confidence": 0.0, "layer": None},
            },
        )
        runtime.handle_query("orchestrate this")

        span = self._route_span(fresh_tracer)
        metadata = self._metadata(span)
        assert metadata.get("has_match") is False
        assert metadata.get("mode") == "single"
        assert is_route_miss_span(span) is True

    def test_orchestrate_single_match(self, fresh_tracer, tmp_path) -> None:
        runtime = self._orchestrate_runtime(
            tmp_path,
            {
                "is_multi_intent": False,
                "single_result": {"skill_id": "some-skill", "confidence": 0.9, "layer": "keyword"},
            },
        )
        runtime.handle_query("orchestrate this")

        metadata = self._metadata(self._route_span(fresh_tracer))
        assert metadata.get("has_match") is True
        assert metadata.get("layer") == "keyword"

    def test_orchestrate_multi_intent_plan_is_a_match(self, fresh_tracer, tmp_path) -> None:
        """Multi-intent: a non-empty step list is the match verdict."""
        runtime = self._orchestrate_runtime(
            tmp_path,
            {
                "is_multi_intent": True,
                "plan": {"steps": [{"skill_id": "step-skill", "intent": "do the thing"}]},
            },
        )
        runtime.handle_query("orchestrate this")

        metadata = self._metadata(self._route_span(fresh_tracer))
        assert metadata.get("has_match") is True
        assert metadata.get("mode") == "orchestrate"

    def test_property_semantics_unchanged(self, tmp_path) -> None:
        """The mode-derived has_match property is NOT changed: existing
        consumers (instinct bridge, hook JSON) keep their semantics."""
        from vibesop.agent.runtime.agent_runtime import AgentRuntimeResult

        result = AgentRuntimeResult()
        result.intercepted = True
        result.mode = "single"
        # Mode-derived property stays True even when the router missed…
        assert result.has_match is True
        # …while the router's verdict is carried separately.
        assert result.router_matched is False

    def test_orchestrate_multi_intent_empty_steps_is_miss(self, fresh_tracer, tmp_path) -> None:
        """gate20 pi NIT-2: empty plan steps → bool(steps) False side —
        the predicate must see the miss."""
        from vibesop.core.observability.gold_detection import is_route_miss_span

        runtime = self._orchestrate_runtime(
            tmp_path,
            {"is_multi_intent": True, "plan": {"steps": []}},
        )
        runtime.handle_query("orchestrate this")

        span = self._route_span(fresh_tracer)
        metadata = self._metadata(span)
        assert metadata.get("has_match") is False
        assert metadata.get("mode") == "orchestrate"
        assert is_route_miss_span(span) is True

    def test_orchestrate_all_fallback_plan_is_miss(self, fresh_tracer, tmp_path) -> None:
        """gate20 claude NIT-1: PlanBuilder steps can carry
        skill_id="fallback-llm" — an all-fallback plan is a MISS, same
        verdict the single-intent branch gives fallback-llm.
        gate40 项4: the SPAN must also write skill_id="" (never the
        sentinel) and omit top_skills — the result object itself keeps
        steps[0].skill_id (result contract, untouched)."""
        from vibesop.core.observability.gold_detection import is_route_miss_span

        runtime = self._orchestrate_runtime(
            tmp_path,
            {
                "is_multi_intent": True,
                "plan": {
                    "steps": [
                        {"skill_id": "fallback-llm", "intent": "answer generally"},
                        {"skill_id": "fallback-llm", "intent": "summarize"},
                    ]
                },
            },
        )
        result = runtime.handle_query("orchestrate this")

        span = self._route_span(fresh_tracer)
        metadata = self._metadata(span)
        assert metadata.get("has_match") is False
        assert metadata.get("skill_id") == ""
        assert "top_skills" not in metadata
        assert is_route_miss_span(span) is True
        # Result contract pin: result.skill_id is UNTOUCHED (steps[0]) —
        # the injection gate (:653) and instinct bridge (:780) consume it.
        assert result.skill_id == "fallback-llm"

    def test_orchestrate_all_fallback_plan_zeroes_confidence(self, fresh_tracer, tmp_path) -> None:
        """gate41 项3: an all-fallback orchestrated plan must write
        has_match=False ∧ confidence=0.0 on the span — the fixed 0.8 the
        :562 branch stamps on the result no longer leaks into miss rows."""
        runtime = self._orchestrate_runtime(
            tmp_path,
            {
                "is_multi_intent": True,
                "plan": {
                    "steps": [
                        {"skill_id": "fallback-llm", "intent": "answer generally"},
                        {"skill_id": "fallback-llm", "intent": "summarize"},
                    ]
                },
            },
        )
        result = runtime.handle_query("orchestrate this")

        metadata = self._metadata(self._route_span(fresh_tracer))
        assert metadata.get("has_match") is False
        assert metadata.get("confidence") == 0.0
        # Result contract pin: the result object itself still carries the
        # branch-stamped 0.8 — only the SPAN confidence is zeroed.
        assert result.confidence == 0.8

    def test_match_preserves_router_confidence(self, fresh_tracer, tmp_path) -> None:
        """gate41 项3: a REAL hit keeps has_match=True and the router's
        confidence unchanged on the span (the unified predicate is a
        no-op on genuine matches)."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        routing_result = MagicMock()
        routing_result.has_match = True
        routing_result.primary = SimpleNamespace(
            skill_id="some-skill", skill_name="Some Skill", confidence=0.9, layer=None
        )
        routing_result.alternatives = []
        routing_result.plan = None

        router = MagicMock()
        router.route.return_value = routing_result
        runtime = AgentRuntime(project_root=tmp_path)
        runtime._router = router
        runtime.handle_query("review my code")

        metadata = self._metadata(self._route_span(fresh_tracer))
        assert metadata.get("has_match") is True
        assert metadata.get("confidence") == 0.9
        assert metadata.get("skill_id") == "some-skill"

    def test_router_matched_without_real_skill_is_span_miss(self, fresh_tracer, tmp_path) -> None:
        """gate41 项3 invariant pin: router_matched=True but NO real
        skill in the span candidates (primary is the fallback-llm
        sentinel, filtered out of _span_skill_ids) → the span writes
        has_match=False ∧ confidence=0.0. The router's raw verdict on
        the RESULT object (router_matched) stays True — only the span
        verdict is narrowed by the unified predicate."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        routing_result = MagicMock()
        routing_result.has_match = True
        routing_result.primary = SimpleNamespace(
            skill_id="fallback-llm", skill_name="Fallback", confidence=0.8, layer=None
        )
        routing_result.alternatives = []
        routing_result.plan = None

        router = MagicMock()
        router.route.return_value = routing_result
        runtime = AgentRuntime(project_root=tmp_path)
        runtime._router = router
        result = runtime.handle_query("review my code")

        # Router's raw verdict is preserved on the result object…
        assert result.router_matched is True
        # …while the span verdict follows the unified matched predicate.
        metadata = self._metadata(self._route_span(fresh_tracer))
        assert metadata.get("has_match") is False
        assert metadata.get("confidence") == 0.0
        assert metadata.get("skill_id") == ""
        assert "top_skills" not in metadata

    def test_orchestrate_mixed_plan_is_match(self, fresh_tracer, tmp_path) -> None:
        """A plan with at least one REAL skill step is a match even if
        other steps fell back. gate40 项4: the span attributes the FIRST
        REAL step — skill_id=次步, top_skills[0]=次步 (the result object
        still carries steps[0], the fallback sentinel)."""
        runtime = self._orchestrate_runtime(
            tmp_path,
            {
                "is_multi_intent": True,
                "plan": {
                    "steps": [
                        {"skill_id": "fallback-llm", "intent": "answer generally"},
                        {"skill_id": "real-skill", "intent": "do the thing"},
                    ]
                },
            },
        )
        result = runtime.handle_query("orchestrate this")

        metadata = self._metadata(self._route_span(fresh_tracer))
        assert metadata.get("has_match") is True
        assert metadata.get("skill_id") == "real-skill"
        assert metadata["top_skills"] == ["real-skill"]
        # Result contract pin: steps[0] still flows into result.skill_id.
        assert result.skill_id == "fallback-llm"

    def test_orchestrate_plan_beyond_five_steps(self, fresh_tracer, tmp_path) -> None:
        """gate40 impl-review MAJOR: the span write must scan ALL plan
        steps, not just the steps[0] + steps[1:5] window that
        result.skill_id / result.alternatives cover. A >5-step plan whose
        first five steps are all fallback used to leak has_match=true ∧
        skill_id="" — the exact hole gate40 项4 set out to close."""
        runtime = self._orchestrate_runtime(
            tmp_path,
            {
                "is_multi_intent": True,
                "plan": {
                    "steps": [
                        *[{"skill_id": "fallback-llm", "intent": f"step {i}"} for i in range(5)],
                        {"skill_id": "late-real-skill", "intent": "do it"},
                    ]
                },
            },
        )
        runtime.handle_query("orchestrate this")

        metadata = self._metadata(self._route_span(fresh_tracer))
        assert metadata.get("has_match") is True
        assert metadata.get("skill_id") == "late-real-skill"
        assert metadata["top_skills"] == ["late-real-skill"]

    def test_routing_exception_span_is_unknown_not_miss(self, fresh_tracer, tmp_path) -> None:
        """gate20 pi NIT-2: routing raises → early return BEFORE the
        metadata write → the span carries NO has_match key → both
        predicates treat it as unknown, never a miss."""
        from unittest.mock import MagicMock

        from vibesop.core.observability.gold_detection import is_route_miss_span
        from vibesop.core.observability.tool_call_bridge import _as_route_span, _is_miss

        router = MagicMock()
        router.route.side_effect = RuntimeError("boom")

        runtime = AgentRuntime(project_root=tmp_path)
        runtime._router = router
        result = runtime.handle_query("review my code")
        assert result.errors  # routing failure recorded

        span = self._route_span(fresh_tracer)
        metadata = self._metadata(span)
        assert "has_match" not in metadata
        assert is_route_miss_span(span) is False  # unknown, not miss
        bridge_span = _as_route_span(span)
        assert bridge_span.has_match is None
        assert _is_miss(bridge_span) is False


class TestTopSkillsSpanMetadata:
    """gate38 L2a — hook-path hit spans carry ``metadata.top_skills``
    (≤3, primary first). Written ONLY on a real router hit
    (``result.router_matched``, the same expression as
    ``metadata["has_match"]``) — NOT on the mode-derived ``has_match``
    property, which stays True on intercepted misses.
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

    def _route_span(self, span_file) -> dict:
        import json

        spans = []
        with span_file.open() as f:
            for raw in f:
                if raw.strip():
                    spans.append(json.loads(raw))
        route_spans = [s for s in spans if str(s.get("name", "")).startswith("route:")]
        assert len(route_spans) == 1, f"expected 1 route span, got {len(route_spans)}"
        return route_spans[0]

    @staticmethod
    def _metadata(span: dict) -> dict:
        import json

        meta = span.get("metadata") or {}
        return json.loads(meta) if isinstance(meta, str) else meta

    def _runtime_with_router(self, tmp_path, routing_result):
        from unittest.mock import MagicMock

        router = MagicMock()
        router.route.return_value = routing_result
        runtime = AgentRuntime(project_root=tmp_path)
        runtime._router = router
        return runtime

    @staticmethod
    def _hit_result(alternatives):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        routing_result = MagicMock()
        routing_result.has_match = True
        routing_result.primary = SimpleNamespace(
            skill_id="some-skill", skill_name="Some Skill", confidence=0.9, layer=None
        )
        routing_result.alternatives = alternatives
        routing_result.plan = None
        return routing_result

    def test_hit_writes_top_skills_primary_first(self, fresh_tracer, tmp_path) -> None:
        from types import SimpleNamespace

        routing_result = self._hit_result(
            [
                SimpleNamespace(skill_id="alt-1", confidence=0.7),
                SimpleNamespace(skill_id="alt-2", confidence=0.6),
            ]
        )
        self._runtime_with_router(tmp_path, routing_result).handle_query("review my code")

        metadata = self._metadata(self._route_span(fresh_tracer))
        assert metadata.get("has_match") is True
        assert metadata["top_skills"] == ["some-skill", "alt-1", "alt-2"]

    def test_top_skills_capped_at_three(self, fresh_tracer, tmp_path) -> None:
        from types import SimpleNamespace

        routing_result = self._hit_result(
            [SimpleNamespace(skill_id=f"alt-{i}", confidence=0.5) for i in range(4)]
        )
        self._runtime_with_router(tmp_path, routing_result).handle_query("review my code")

        metadata = self._metadata(self._route_span(fresh_tracer))
        assert metadata["top_skills"] == ["some-skill", "alt-0", "alt-1"]

    def test_intercepted_miss_omits_top_skills(self, fresh_tracer, tmp_path) -> None:
        """Latent pin for the grok-NIT gate choice (``router_matched`` over
        the mode-derived ``has_match`` property, which stays True on
        intercepted misses). Today miss paths also leave ``skill_id`` /
        ``alternatives`` empty, so swapping the gate to the property stays
        green — this test only goes red once miss paths start filling
        alternatives. The live fallback-garbage defense is the CLI-side
        ``test_miss_with_fallback_alternatives_omits_top_skills``."""
        from unittest.mock import MagicMock

        routing_result = MagicMock()
        routing_result.has_match = False
        routing_result.primary = None
        routing_result.layer_details = []
        self._runtime_with_router(tmp_path, routing_result).handle_query("review my code")

        metadata = self._metadata(self._route_span(fresh_tracer))
        assert metadata.get("has_match") is False
        assert "top_skills" not in metadata

    def test_magicmock_alternative_does_not_leak(self, fresh_tracer, tmp_path) -> None:
        """A MagicMock alternative's auto-created skill_id (a MagicMock,
        not a str) must never reach span metadata — same guard convention
        as the layer write."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        routing_result = self._hit_result(
            [MagicMock(), SimpleNamespace(skill_id="alt-1", confidence=0.7)]
        )
        self._runtime_with_router(tmp_path, routing_result).handle_query("review my code")

        metadata = self._metadata(self._route_span(fresh_tracer))
        assert metadata["top_skills"] == ["some-skill", "alt-1"]
        # The metadata round-tripped through SpanWriter JSON — a leaked
        # MagicMock would have failed serialization already.

    def test_skill_health_reader_unaffected_by_top_skills_key(self, tmp_path) -> None:
        """skill_health fire counts are identical for old spans (no
        top_skills key) and new spans (with it) — additive metadata must
        not move the gate37 reader."""
        import json as _json
        from datetime import UTC, datetime, timedelta

        from vibesop.core.skills.skill_health import count_skill_fires

        now = datetime.now(UTC)

        def _span_meta(extra: dict) -> dict:
            meta = {"skill_id": "demo/skill", "has_match": True, **extra}
            return {
                "span_kind": "task",
                "name": "route:demo",
                "metadata": _json.dumps(meta),
                "started_at": (now - timedelta(days=1)).isoformat(),
            }

        path = tmp_path / ".vibe" / "observability" / "spans.dev.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            _json.dumps(_span_meta({}))
            + "\n"
            + _json.dumps(_span_meta({"top_skills": ["demo/skill", "alt-1"]}))
            + "\n",
            encoding="utf-8",
        )
        assert count_skill_fires(tmp_path, now=now) == {"demo/skill": 2}
