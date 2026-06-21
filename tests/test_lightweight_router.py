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
        result = LightweightRouter._format_result(_mock_orchestrated_result())
        assert result["mode"] == "orchestrated"
        assert "steps" in result
        assert len(result["steps"]) == 2

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


def _mock_orchestrated_result() -> MagicMock:
    step1 = MagicMock()
    step1.step_number = 1
    step1.skill_id = "test/a"
    step1.intent = "task A"
    step1.input_query = "do A"

    step2 = MagicMock()
    step2.step_number = 2
    step2.skill_id = "test/b"
    step2.intent = "task B"
    step2.input_query = "do B"

    plan = MagicMock()
    plan.workflow_pattern = WorkflowPattern.SEQUENTIAL
    plan.plan_id = "test-plan"
    plan.steps = [step1, step2]

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
