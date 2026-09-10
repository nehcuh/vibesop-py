"""Tests for Phase 4: LightweightRouter and CLI --minimal flag."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from vibesop.core.models import WorkflowPattern
from vibesop.core.routing.lightweight_api import LightweightRouter

# ── LightweightRouter unit tests ─────────────────────────────────────────────


class TestLightweightRouterFallback:
    def test_returns_fallback_when_router_unavailable(self):
        router = LightweightRouter()
        # Force router to None (simulating unavailable)
        router._router = None
        with patch.object(router, "_get_router", return_value=None):
            result = router.route("test query")
        assert result["mode"] == "fallback"
        assert result["skill_id"] == ""

    def test_fallback_includes_error_message(self):
        router = LightweightRouter()
        result = router._fallback_result(error="something broke")
        assert "something broke" in result["reasoning"]

    def test_fallback_result_structure(self):
        result = LightweightRouter._fallback_result()
        assert "mode" in result
        assert "skill_id" in result
        assert "confidence" in result
        assert "reasoning" in result


class TestLightweightRouterFormatResult:
    def test_format_single_result(self):
        result = LightweightRouter._format_result(_mock_single_result("test/review", 0.95))
        assert result["mode"] == "single"
        assert result["skill_id"] == "test/review"
        assert result["confidence"] == 0.95

    def test_format_orchestrated_result(self):
        result = LightweightRouter._format_result(_real_orchestrated_result(execution_ready=True))
        assert result["mode"] == "orchestrated"
        assert "steps" in result
        assert len(result["steps"]) == 2

    def test_format_orchestrated_blocked_plan_demotes(self):
        """Explicit execution_ready=False must demote to a notice-only no_match."""
        result = LightweightRouter._format_result(_real_orchestrated_result(execution_ready=False))
        assert result["mode"] == "no_match"
        assert result["has_match"] is False
        assert result["notice_only"] is True

    def test_format_orchestrated_unannotated_plan_demotes_with_warning(self, caplog):
        """A plan that was never annotated (no plan_annotator injected) must
        still demote fail-closed, and must log a warning so the wiring gap is
        diagnosable (8.3.1-P1-1 regression pin)."""
        import logging

        with caplog.at_level(logging.WARNING, logger="vibesop.core.routing.lightweight_api"):
            result = LightweightRouter._format_result(
                _real_orchestrated_result(execution_ready=None)
            )
        assert result["mode"] == "no_match"
        assert result["has_match"] is False
        assert any("execution_ready" in rec.message for rec in caplog.records)

    def test_format_no_match_result(self):
        result = LightweightRouter._format_result(_mock_no_match_result())
        assert result["mode"] == "no_match"

    def test_format_result_truncates_alternatives(self):
        """Alternatives should be limited to 5."""
        mock = _mock_single_result("test/skill", 0.8)
        mock.primary.__class__ = type("P", (), {})
        mock.alternatives = [
            type("Alt", (), {"skill_id": f"alt/{i}", "confidence": 0.5})() for i in range(10)
        ]
        result = LightweightRouter._format_result(mock)
        assert len(result.get("alternatives", [])) <= 5


class TestLightweightRouterBatch:
    def test_route_batch_returns_list(self):
        router = LightweightRouter()
        with patch.object(router, "_get_router", return_value=None):
            results = router.route_batch(["query1", "query2", "query3"])
        assert len(results) == 3
        assert all(r["mode"] == "fallback" for r in results)

    def test_route_batch_empty(self):
        router = LightweightRouter()
        results = router.route_batch([])
        assert results == []


class TestLightweightRouterJson:
    def test_route_json_returns_valid_json(self):
        router = LightweightRouter()
        with patch.object(router, "_get_router", return_value=None):
            json_str = router.route_json("test query")
        parsed = json.loads(json_str)
        assert "mode" in parsed
        assert "skill_id" in parsed


class TestLightweightRouterPlanAnnotator:
    """8.3.1-P1-1: the annotator must reach the lazily built UnifiedRouter."""

    def test_constructor_annotator_forwarded_to_router(self):
        sentinel = object()
        router = LightweightRouter(plan_annotator=sentinel)
        with patch("vibesop.core.routing.UnifiedRouter") as mock_cls:
            inner = mock_cls.return_value
            assert router._get_router() is inner
        assert inner.plan_annotator is sentinel

    def test_set_plan_annotator_updates_live_router(self):
        router = LightweightRouter()
        live = MagicMock()
        router._router = live
        router.set_plan_annotator("ann")
        assert live.plan_annotator == "ann"
        assert router._plan_annotator == "ann"


# ── AgentRuntime.route_step tests ────────────────────────────────────────────


class TestAgentRuntimeRouteStep:
    def test_route_step_returns_dict(self):
        from vibesop.agent.runtime.agent_runtime import AgentRuntime

        runtime = AgentRuntime(project_root=".")
        with patch(
            "vibesop.core.routing.lightweight_api.LightweightRouter.route",
            return_value={"mode": "single", "skill_id": "test/skill", "confidence": 0.9},
        ):
            result = runtime.route_step("debug error", step_number=1, phase=2)
        assert isinstance(result, dict)
        assert result["skill_id"] == "test/skill"

    def test_route_step_injects_plan_annotator(self):
        """8.3.1-P1-1 regression pin: route_step must wire the annotator so a
        healthy multi-intent plan is not demoted to a false blocked no_match."""
        from vibesop.agent.runtime.agent_runtime import AgentRuntime

        runtime = AgentRuntime(project_root=".")
        with patch("vibesop.core.routing.lightweight_api.LightweightRouter") as mock_lw:
            mock_lw.return_value.route.return_value = {"mode": "single"}
            runtime.route_step("debug error", step_number=1, phase=2)
        _, kwargs = mock_lw.call_args
        assert callable(kwargs.get("plan_annotator"))


# ── CLI --minimal integration tests ──────────────────────────────────────────


class TestCLIMinimalFlag:
    def test_minimal_output_is_valid_json(self, capsys):
        from vibesop.core.routing.lightweight_api import LightweightRouter

        # Test the formatting function directly (unit level)
        mock = _mock_single_result("systematic-debugging", 0.95)
        result = LightweightRouter._format_result(mock)
        json_str = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["skill_id"] == "systematic-debugging"
        assert parsed["confidence"] == 0.95


# ── Helpers ──────────────────────────────────────────────────────────────────


def _mock_single_result(skill_id: str, confidence: float) -> MagicMock:
    primary = MagicMock()
    primary.skill_id = skill_id
    primary.confidence = confidence
    primary.reasoning = "test"
    primary.layer = MagicMock()
    primary.layer.value = "keyword"

    result = MagicMock()
    result.mode = MagicMock()
    result.mode.value = "single"
    result.primary = primary
    result.alternatives = []
    return result


def _real_orchestrated_result(execution_ready: bool | None = True) -> MagicMock:
    """Build an orchestrated result around a REAL ExecutionPlan.

    The previous MagicMock plan made ``metadata.get("execution_ready", False)``
    truthy by accident, so the G-1 blocked-plan gate was never actually
    exercised (8.3.1-P1-1 fake-green). ``execution_ready=None`` simulates a
    plan that was never annotated.
    """
    from vibesop.core.models import ExecutionPlan, ExecutionStep

    metadata: dict = {}
    if execution_ready is not None:
        metadata["execution_ready"] = execution_ready
    plan = ExecutionPlan(
        plan_id="test-plan",
        original_query="do A and then do B",
        workflow_pattern=WorkflowPattern.SEQUENTIAL,
        steps=[
            ExecutionStep(
                step_id="s1",
                step_number=1,
                skill_id="test/a",
                intent="task A",
                input_query="do A",
            ),
            ExecutionStep(
                step_id="s2",
                step_number=2,
                skill_id="test/b",
                intent="task B",
                input_query="do B",
            ),
        ],
        metadata=metadata,
    )

    result = MagicMock()
    result.mode = MagicMock()
    result.mode.value = "orchestrated"
    result.execution_plan = plan
    return result


def _mock_no_match_result() -> MagicMock:
    result = MagicMock()
    result.mode = MagicMock()
    result.mode.value = "single"
    result.primary = None
    result.execution_plan = None
    return result
