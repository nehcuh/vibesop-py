"""Tests for PlanBuilder — converts sub-tasks into ExecutionPlan with skill routing."""

from __future__ import annotations

from typing import Any

import pytest

from vibesop.core.matching import RoutingContext
from vibesop.core.models import (
    ExecutionMode,
    RoutingLayer,
    RoutingResult,
    SkillRoute,
)
from vibesop.core.orchestration.plan_builder import PARALLEL_KEYWORDS, PlanBuilder
from vibesop.core.orchestration.task_decomposer import SubTask


class FakeRouter:
    """Minimal stub for UnifiedRouter with controllable _single_skill_route results."""

    def __init__(self, responses: dict[str, SkillRoute] | None = None, default: SkillRoute | None = None) -> None:
        self._responses = responses or {}
        self._default = default
        self._calls: list[str] = []
        self._context_calls: list[RoutingContext | None] = []

    def _single_skill_route(
        self, query: str, context: RoutingContext | None = None, **kwargs: Any
    ) -> RoutingResult:
        self._calls.append(query)
        self._context_calls.append(context)
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

    def test_low_confidence_step_included(self) -> None:
        router = FakeRouter({
            "analyze": self._make_skill_route("architect", confidence=0.3),
        })
        builder = PlanBuilder(router)

        plan = builder.build_plan("analyze this", [SubTask(intent="analyze", query="analyze")])

        # Low-confidence steps are now included so the plan is faithful to decomposition
        assert len(plan.steps) == 1
        assert plan.steps[0].skill_id == "architect"

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
        assert plan.steps[1].dependencies == [plan.steps[0].step_id]
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

    def test_skip_ai_triage_context_passed(self) -> None:
        """Verify PlanBuilder passes skip_ai_triage=True through RoutingContext."""
        router = FakeRouter({
            "analyze": self._make_skill_route("architect"),
        })
        builder = PlanBuilder(router)

        plan = builder.build_plan(
            "analyze architecture",
            [SubTask(intent="analyze", query="analyze")],
        )

        assert len(plan.steps) == 1
        # Verify skip_ai_triage was passed through context
        assert router._context_calls
        ctx = router._context_calls[0]
        assert ctx is not None
        assert ctx.skip_ai_triage is True

    def test_pre_assigned_skill_id_default(self) -> None:
        """When TaskDecomposer assigns a default skill_id (null), fallback to routing."""
        router = FakeRouter(default=self._make_skill_route("routed_skill"))
        builder = PlanBuilder(router)
        sub_task = SubTask(intent="test", query="some query", skill_id="null")

        plan = builder.build_plan("test", [sub_task])

        assert len(plan.steps) == 1
        # Should use the routed skill, not "null"
        assert plan.steps[0].skill_id == "routed_skill"

    def test_capability_match_exact(self) -> None:
        """When task_type='analysis', prefer architect over review."""
        router = FakeRouter(default=self._make_skill_route("gstack/review"))
        builder = PlanBuilder(router)
        sub_task = SubTask(intent="analyze", query="analyze architecture", task_type="analysis")

        plan = builder.build_plan("analyze architecture", [sub_task])

        assert len(plan.steps) == 1
        # FakeRouter.default is gstack/review, but with task_type=analysis
        # the capability score for gstack/review (capabilities: [review, security])
        # gives 0.0 bonus, while any analysis-capable skill would have 1.0.
        # Since no alternatives exist, primary stays.
        assert plan.steps[0].skill_id == "gstack/review"

    def test_capability_match_no_task_type(self) -> None:
        """Without task_type, capability matching is skipped."""
        default_route = self._make_skill_route("generic")
        router = FakeRouter(default=default_route)
        builder = PlanBuilder(router)
        sub_task = SubTask(intent="test", query="test", task_type="")

        plan = builder.build_plan("test", [sub_task])

        assert len(plan.steps) == 1
        assert plan.steps[0].skill_id == "generic"

    def test_capability_match_with_alternatives(self) -> None:
        """When alternatives exist, capability matching can re-rank."""
        architect = self._make_skill_route("superpowers/architect", confidence=0.75)
        reviewer = self._make_skill_route("gstack/review", confidence=0.80)
        router = FakeRouter(
            default=reviewer,
            responses={"analyze": architect},
        )
        # Test the scoring logic directly with explicit capability lists.
        builder = PlanBuilder(router)

        # Verify capability scoring (instance method, capabilities passed directly)
        arch_score = builder._capability_score(["design", "analysis", "plan"], "analysis")
        review_score = builder._capability_score(["review", "security"], "analysis")
        assert arch_score == 1.0
        assert review_score == 0.0

        # When sub-task has task_type, architect should be preferred
        sub_task = SubTask(intent="analyze", query="analyze", task_type="analysis")
        plan = builder.build_plan("analyze architecture", [sub_task])
        assert len(plan.steps) >= 1

    def test_capability_related_match(self) -> None:
        """Related capabilities get 0.5 score."""
        router = FakeRouter()
        builder = PlanBuilder(router)

        # Exact match
        score = builder._capability_score(["debug", "analysis"], "analysis")
        assert score == 1.0

        # Related match: design is related to plan
        score = builder._capability_score(["design"], "plan")
        assert score == 0.5

        # No match
        score = builder._capability_score(["deploy", "review"], "analysis")
        assert score == 0.0


class TestPreAssignedSkillIdPropagation:
    """Verify decomposer-supplied skill_id wins over the (skip_ai_triage) router.

    This is the P1-B regression guard: when the decomposer LLM has been given the
    skill catalog and assigns skill_id per sub-task, PlanBuilder MUST honor those
    assignments instead of falling back to SCENARIO/INDEX which routes everything
    to whichever skill scores highest in the cheap matchers.
    """

    @staticmethod
    def _route(skill_id: str, confidence: float = 0.5) -> SkillRoute:
        return SkillRoute(
            skill_id=skill_id,
            confidence=confidence,
            layer=RoutingLayer.SCENARIO,
            source="test",
        )

    def test_pre_assigned_skill_bypasses_router(self) -> None:
        """When skill_id is set, the router is not consulted at all."""
        router = FakeRouter(default=self._route("wrong_skill"))
        builder = PlanBuilder(router)

        sub_task = SubTask(
            intent="review code",
            query="review the new auth flow",
            skill_id="gstack/review",
        )
        plan = builder.build_plan("review the new auth flow", [sub_task])

        assert len(plan.steps) == 1
        assert plan.steps[0].skill_id == "gstack/review"
        # No routing call should have been issued for this sub-task.
        assert router._calls == []

    def test_pre_assigned_skill_high_confidence(self) -> None:
        """Pre-assigned sub-tasks land at 0.99 confidence in the reasoning."""
        router = FakeRouter()
        builder = PlanBuilder(router)

        sub_task = SubTask(intent="debug", query="debug auth", skill_id="gstack/debug")
        plan = builder.build_plan("debug auth", [sub_task])

        assert len(plan.steps) == 1
        # Confidence is logged via reasoning string at percent precision.
        assert "99%" in plan.reasoning

    def test_multi_sub_task_distinct_skills(self) -> None:
        """Each sub-task with its own skill_id reaches its own skill — no shared default.

        This is the symptom from the issue: every sub-task previously ended up at the
        SCENARIO winner. With skill_id pre-assigned, each step is independent.
        """
        router = FakeRouter(default=self._route("scenario_winner"))
        builder = PlanBuilder(router)

        sub_tasks = [
            SubTask(intent="analyze", query="analyze architecture", skill_id="superpowers/architect"),
            SubTask(intent="review", query="review security", skill_id="gstack/review"),
            SubTask(intent="test", query="run tests", skill_id="gstack/test"),
        ]
        plan = builder.build_plan("analyze, review, test", sub_tasks)

        assert len(plan.steps) == 3
        assigned = [step.skill_id for step in plan.steps]
        assert assigned == ["superpowers/architect", "gstack/review", "gstack/test"]
        # Sanity: router was never invoked for any sub-task.
        assert router._calls == []

    def test_mixed_pre_assigned_and_routed(self) -> None:
        """When some sub-tasks have skill_id and others don't, only the unset ones route."""
        router = FakeRouter(default=self._route("router_default"))
        builder = PlanBuilder(router)

        sub_tasks = [
            SubTask(intent="analyze", query="analyze architecture", skill_id="superpowers/architect"),
            SubTask(intent="review", query="review security"),  # no skill_id → must route
        ]
        plan = builder.build_plan("analyze, review", sub_tasks)

        assert len(plan.steps) == 2
        assert plan.steps[0].skill_id == "superpowers/architect"
        assert plan.steps[1].skill_id == "router_default"
        # Exactly one routing call (for the unset sub-task).
        assert len(router._calls) == 1
