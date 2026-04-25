"""Tests for PlanBuilder — converts sub-tasks into ExecutionPlan with skill routing."""

from __future__ import annotations

from typing import Any

import pytest

from vibesop.core.models import (
    ExecutionMode,
    RoutingLayer,
    RoutingResult,
    SkillRoute,
)
from vibesop.core.orchestration.plan_builder import PARALLEL_KEYWORDS, PlanBuilder
from vibesop.core.orchestration.task_decomposer import SubTask


class FakeRouter:
    """Minimal stub for UnifiedRouter with controllable route() results."""

    def __init__(self, responses: dict[str, SkillRoute] | None = None, default: SkillRoute | None = None) -> None:
        self._responses = responses or {}
        self._default = default
        self._calls: list[str] = []

    def route(self, query: str, **kwargs: Any) -> RoutingResult:
        self._calls.append(query)
        # Try exact match first, then prefix match (PlanBuilder adds context text)
        match = self._responses.get(query)
        if match is None:
            for prefix, route in self._responses.items():
                if query.startswith(prefix):
                    match = route
                    break
        if match is None:
            match = self._default
        if match:
            return RoutingResult(
                primary=match,
                alternatives=[],
                routing_path=[match.layer],
                layer_details=[],
                query=query,
                duration_ms=1.0,
            )
        return RoutingResult(
            primary=None,
            alternatives=[],
            routing_path=[],
            layer_details=[],
            query=query,
            duration_ms=1.0,
        )


class TestPlanBuilder:
    """Core plan builder tests."""

    def _make_skill_route(self, skill_id: str, confidence: float = 0.9) -> SkillRoute:
        return SkillRoute(
            skill_id=skill_id,
            confidence=confidence,
            layer=RoutingLayer.AI_TRIAGE,
            source="test",
        )

    def test_build_sequential_plan(self) -> None:
        router = FakeRouter({
            "analyze_architecture": self._make_skill_route("architect"),
            "code_review": self._make_skill_route("review"),
        })
        builder = PlanBuilder(router)
        sub_tasks = [
            SubTask(intent="architectural_analysis", query="analyze_architecture"),
            SubTask(intent="code_review", query="code_review"),
        ]

        plan = builder.build_plan("analyze architecture and review code", sub_tasks)

        assert len(plan.steps) == 2
        assert plan.execution_mode == ExecutionMode.PARALLEL  # Multiple tasks without "then" → parallel
        assert plan.steps[0].skill_id == "architect"
        assert plan.steps[1].skill_id == "review"
        assert plan.detected_intents == ["architectural_analysis", "code_review"]
        assert plan.status.value == "pending"

    def test_build_parallel_plan_with_keywords(self) -> None:
        default_route = self._make_skill_route("generic")
        router = FakeRouter(default=default_route)
        builder = PlanBuilder(router)
        sub_tasks = [
            SubTask(intent="test", query="test module a"),
            SubTask(intent="review", query="review module b"),
        ]

        plan = builder.build_plan("test module A simultaneously review module B", sub_tasks)

        assert len(plan.steps) == 2
        assert plan.execution_mode == ExecutionMode.PARALLEL

    def test_build_sequential_plan_with_then(self) -> None:
        default_route = self._make_skill_route("generic")
        router = FakeRouter(default=default_route)
        builder = PlanBuilder(router)
        sub_tasks = [
            SubTask(intent="analyze", query="analyze"),
            SubTask(intent="review", query="review after that"),
        ]

        plan = builder.build_plan("analyze then review", sub_tasks)

        assert len(plan.steps) == 2
        assert plan.execution_mode == ExecutionMode.SEQUENTIAL

    def test_single_task_returns_sequential(self) -> None:
        router = FakeRouter({"debug": self._make_skill_route("debug")})
        builder = PlanBuilder(router)

        plan = builder.build_plan("debug this", [SubTask(intent="debug", query="debug")])

        assert len(plan.steps) == 1
        assert plan.execution_mode == ExecutionMode.SEQUENTIAL

    def test_low_confidence_step_skipped(self) -> None:
        router = FakeRouter({
            "analyze": self._make_skill_route("architect", confidence=0.3),
        })
        builder = PlanBuilder(router)

        plan = builder.build_plan("analyze this", [SubTask(intent="analyze", query="analyze")])

        assert len(plan.steps) == 0

    def test_no_match_step_skipped(self) -> None:
        router = FakeRouter({})  # No matching route
        builder = PlanBuilder(router)

        plan = builder.build_plan("something obscure", [SubTask(intent="unknown", query="something obscure")])

        assert len(plan.steps) == 0
        assert plan.detected_intents == []

    def test_plan_steps_have_unique_ids(self) -> None:
        default_route = self._make_skill_route("generic")
        router = FakeRouter(default=default_route)
        builder = PlanBuilder(router)
        sub_tasks = [
            SubTask(intent="intent_a", query="a"),
            SubTask(intent="intent_b", query="b"),
        ]

        plan = builder.build_plan("a and b", sub_tasks)

        assert len(plan.steps) == 2
        assert plan.steps[0].step_id != plan.steps[1].step_id

    def test_contextual_query_chaining(self) -> None:
        default_route = self._make_skill_route("generic")
        router = FakeRouter(default=default_route)
        builder = PlanBuilder(router)
        sub_tasks = [
            SubTask(intent="intent_a", query="step1"),
            SubTask(intent="intent_b", query="step2"),
        ]

        plan = builder.build_plan("do step1 then step2", sub_tasks)

        assert len(plan.steps) == 2
        # The second step query should include context from first step
        assert "Context from previous steps" in router._calls[-1]

    def test_sequential_dependency_chaining(self) -> None:
        default_route = self._make_skill_route("generic")
        router = FakeRouter(default=default_route)
        builder = PlanBuilder(router)
        sub_tasks = [
            SubTask(intent="analyze", query="task1"),
            SubTask(intent="review", query="task2"),
        ]

        plan = builder.build_plan("do task1 then task2", sub_tasks)

        assert len(plan.steps) == 2
        assert plan.execution_mode == ExecutionMode.SEQUENTIAL
        # In sequential mode, step 2 should depend on step 1
        assert plan.steps[0].dependencies == []
        assert plan.steps[1].dependencies == ["step_1"]
        assert plan.steps[0].can_parallel is True
        assert plan.steps[1].can_parallel is False

    @pytest.mark.parametrize("keyword", PARALLEL_KEYWORDS)
    def test_parallel_keywords_detection(self, keyword: str) -> None:
        router = FakeRouter({
            "a": self._make_skill_route("skill_a"),
            "b": self._make_skill_route("skill_b"),
        })
        builder = PlanBuilder(router)
        sub_tasks = [
            SubTask(intent="intent_a", query="a"),
            SubTask(intent="intent_b", query="b"),
        ]

        plan = builder.build_plan(f"do a {keyword} b", sub_tasks)

        assert plan.execution_mode == ExecutionMode.PARALLEL
