"""Tests for PlanBuilder — converts sub-tasks into ExecutionPlan with skill routing."""

from __future__ import annotations

from typing import Any

import pytest

from vibesop.core.matching import RoutingContext
from vibesop.core.models import (
    ExecutionMode,
    IntentAnalysis,
    RoutingLayer,
    RoutingResult,
    SkillRoute,
    WorkflowPattern,
)
from vibesop.core.orchestration.plan_builder import PARALLEL_KEYWORDS, PlanBuilder
from vibesop.core.orchestration.task_decomposer import SubTask


class FakeLoadedSkill:
    """Minimal stand-in for LoadedSkill with metadata attributes."""

    def __init__(self, **kwargs: Any) -> None:
        self.metadata = type("Meta", (), kwargs)()


class FakeSkillLoader:
    """Minimal skill loader returning a fixed skill catalog."""

    def __init__(self, skills: dict[str, FakeLoadedSkill]) -> None:
        self._skills = skills

    def discover_all(self, force_reload: bool = False) -> dict[str, FakeLoadedSkill]:
        return self._skills


class FakeRouter:
    """Minimal stub for UnifiedRouter with controllable _single_skill_route results."""

    def __init__(
        self, responses: dict[str, SkillRoute] | None = None, default: SkillRoute | None = None
    ) -> None:
        self._responses = responses or {}
        self._default = default
        self._calls: list[str] = []
        self._context_calls: list[RoutingContext | None] = []
        self._skill_loader: Any = None
        self._llm_factory: Any = None

    def get_skill_loader(self) -> Any:
        return self._skill_loader

    def set_llm_factory(self, factory: Any) -> None:
        self._llm_factory = factory

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
        router = FakeRouter(
            {
                "analyze_architecture": self._make_skill_route("architect"),
                "code_review": self._make_skill_route("review"),
            }
        )
        builder = PlanBuilder(router)
        sub_tasks = [
            SubTask(intent="architectural_analysis", query="analyze_architecture"),
            SubTask(intent="code_review", query="code_review"),
        ]

        plan = builder.build_plan("analyze architecture and review code", sub_tasks)

        assert len(plan.steps) == 2
        assert (
            plan.execution_mode == ExecutionMode.PARALLEL
        )  # Multiple tasks without "then" → parallel
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
        router = FakeRouter(
            {
                "analyze": self._make_skill_route("architect", confidence=0.3),
            }
        )
        builder = PlanBuilder(router)

        plan = builder.build_plan("analyze this", [SubTask(intent="analyze", query="analyze")])

        # Low-confidence steps are now included so the plan is faithful to decomposition
        assert len(plan.steps) == 1
        assert plan.steps[0].skill_id == "architect"

    def test_no_match_step_skipped(self) -> None:
        router = FakeRouter({})  # No matching route
        builder = PlanBuilder(router)

        plan = builder.build_plan(
            "something obscure", [SubTask(intent="unknown", query="something obscure")]
        )

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
        router = FakeRouter(
            {
                "a": self._make_skill_route("skill_a"),
                "b": self._make_skill_route("skill_b"),
            }
        )
        builder = PlanBuilder(router)
        sub_tasks = [
            SubTask(intent="intent_a", query="a"),
            SubTask(intent="intent_b", query="b"),
        ]

        plan = builder.build_plan(f"do a {keyword} b", sub_tasks)

        assert plan.execution_mode == ExecutionMode.PARALLEL

    def test_skip_ai_triage_context_passed(self) -> None:
        """Verify PlanBuilder passes skip_ai_triage=True through RoutingContext."""
        router = FakeRouter(
            {
                "analyze": self._make_skill_route("architect"),
            }
        )
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
            SubTask(
                intent="analyze", query="analyze architecture", skill_id="superpowers/architect"
            ),
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
            SubTask(
                intent="analyze", query="analyze architecture", skill_id="superpowers/architect"
            ),
            SubTask(intent="review", query="review security"),  # no skill_id → must route
        ]
        plan = builder.build_plan("analyze, review", sub_tasks)

        assert len(plan.steps) == 2
        assert plan.steps[0].skill_id == "superpowers/architect"
        assert plan.steps[1].skill_id == "router_default"

    def test_management_skill_filtered(self) -> None:
        """Management skills (slash-*) are replaced by the best alternative."""
        # Use a router whose _single_skill_route returns slash-orchestrate as primary
        # with superpowers/architect as an alternative.
        mgmt_route = SkillRoute(
            skill_id="builtin/slash-orchestrate",
            confidence=0.6,
            layer=RoutingLayer.KEYWORD,
            source="test",
        )
        alt_route = SkillRoute(
            skill_id="superpowers/architect",
            confidence=0.55,
            layer=RoutingLayer.KEYWORD,
            source="test",
        )
        router = FakeRouter(responses={"架构评审": mgmt_route})

        # Monkey-patch _single_skill_route to include alternatives
        original = router._single_skill_route

        def _with_alt(query, context=None, **kw):
            result = original(query, context, **kw)
            if result and result.primary and result.primary.skill_id == "builtin/slash-orchestrate":
                result.alternatives = [alt_route]
            return result

        router._single_skill_route = _with_alt  # type: ignore[method-assign]

        builder = PlanBuilder(router)
        sub_tasks = [
            SubTask(intent="架构评审", query="架构评审"),
        ]
        plan = builder.build_plan("评审架构", sub_tasks)

        assert len(plan.steps) == 1
        assert plan.steps[0].skill_id == "superpowers/architect"

    def test_pre_assigned_management_skill_rejected(self) -> None:
        """LLM-assigned management skill is rejected; falls through to routing."""
        router = FakeRouter(default=self._route("superpowers/review"))
        builder = PlanBuilder(router)

        sub_tasks = [
            SubTask(intent="review", query="review code", skill_id="builtin/slash-orchestrate"),
        ]
        plan = builder.build_plan("review code", sub_tasks)

        assert len(plan.steps) == 1
        # Pre-assigned management skill rejected → falls through to router default
        assert plan.steps[0].skill_id == "superpowers/review"
        # Exactly one routing call (for the unset sub-task).
        assert len(router._calls) == 1


class TestPlanBuilderSquadIntegration:
    """PlanBuilder integration with AgentSquadComposer and SkillComposer."""

    def _route(self, skill_id: str, confidence: float = 0.9) -> SkillRoute:
        return SkillRoute(
            skill_id=skill_id,
            confidence=confidence,
            layer=RoutingLayer.AI_TRIAGE,
            source="test",
        )

    def _make_router_with_skills(self) -> FakeRouter:
        skills = {
            "system-design": FakeLoadedSkill(
                name="System Design",
                description="Design system architecture",
                capabilities=["design", "architecture"],
            ),
            "security-audit": FakeLoadedSkill(
                name="Security Audit",
                description="Audit security",
                capabilities=["security", "audit"],
            ),
            "code-review": FakeLoadedSkill(
                name="Code Review",
                description="Review code",
                capabilities=["review"],
            ),
        }
        router = FakeRouter(default=self._route("generic"))
        router._skill_loader = FakeSkillLoader(skills)
        return router

    def test_agent_squad_pattern_replaces_steps(self) -> None:
        router = self._make_router_with_skills()
        builder = PlanBuilder(router)
        analysis = IntentAnalysis(
            complexity="multi_agent",
            facets=["architecture", "security"],
            squad_needed=True,
            suggested_roles=["architect", "red_team"],
            collaboration_protocol="red_team",
            per_agent_skills={
                "architect": ["system-design"],
                "red_team": ["security-audit"],
            },
            confidence=0.9,
        )

        plan = builder.build_plan(
            "design and audit",
            [SubTask(intent="placeholder", query="placeholder")],
            workflow_pattern=WorkflowPattern.AGENT_SQUAD,
            metadata={"intent_analysis": analysis},
        )

        assert plan.workflow_pattern == WorkflowPattern.AGENT_SQUAD
        assert len(plan.steps) == 2
        role_ids = {s.assigned_role for s in plan.steps}
        assert role_ids == {"architect", "red_team"}
        assert plan.steps[0].agent_squad_id is not None
        assert (
            "system-design" in plan.steps[0].role_skills
            or "system-design" in plan.steps[1].role_skills
        )

    def test_debate_pattern_adds_orchestrator_judge(self) -> None:
        router = self._make_router_with_skills()
        builder = PlanBuilder(router)
        analysis = IntentAnalysis(
            complexity="multi_agent",
            facets=["brainstorm"],
            squad_needed=True,
            suggested_roles=["debater"],
            collaboration_protocol="debate",
            per_agent_skills={"debater": ["code-review"]},
            confidence=0.9,
        )

        plan = builder.build_plan(
            "debate approach",
            [SubTask(intent="placeholder", query="placeholder")],
            workflow_pattern=WorkflowPattern.DEBATE,
            metadata={"intent_analysis": analysis},
        )

        roles = [s.assigned_role for s in plan.steps]
        assert "orchestrator" in roles
        assert len(roles) >= 3
        assert plan.execution_mode == ExecutionMode.SEQUENTIAL

    def test_red_team_pattern_orders_implementer_before_red_team(self) -> None:
        router = self._make_router_with_skills()
        builder = PlanBuilder(router)
        analysis = IntentAnalysis(
            complexity="multi_agent",
            facets=["implement_feature", "security_audit"],
            squad_needed=True,
            suggested_roles=["implementer", "red_team"],
            collaboration_protocol="red_team",
            per_agent_skills={
                "implementer": ["code-review"],
                "red_team": ["security-audit"],
            },
            confidence=0.9,
        )

        plan = builder.build_plan(
            "implement and challenge",
            [SubTask(intent="placeholder", query="placeholder")],
            workflow_pattern=WorkflowPattern.RED_TEAM,
            metadata={"intent_analysis": analysis},
        )

        roles = [s.assigned_role for s in plan.steps]
        assert roles.index("implementer") < roles.index("red_team")

    @pytest.mark.parametrize(
        ("pattern", "roles", "protocol"),
        [
            (WorkflowPattern.AGENT_SQUAD, ["architect", "red_team"], "red_team"),
            (WorkflowPattern.DEBATE, ["debater"], "debate"),
            (WorkflowPattern.RED_TEAM, ["implementer", "red_team"], "red_team"),
        ],
    )
    def test_squad_steps_carry_confidence_sentinel(self, pattern, roles, protocol) -> None:
        """P1-2 direct squad test (pull-20260828): squad steps are structurally
        mandated, so every one carries the 0.99 sentinel — without it,
        _needs_confirmation's all_confident fold is always False for squad
        plans and ambiguous_only auto-proceed never fires.

        Exception (P2 fix): a step whose skill assignment came back empty
        (fallback-llm) carries 0.0 instead — see
        test_squad_steps_empty_skill_ids_zero_confidence. Here every role is
        given a distinct, non-conflicting skill so all steps keep 0.99."""
        router = self._make_router_with_skills()
        builder = PlanBuilder(router)
        analysis = IntentAnalysis(
            complexity="multi_agent",
            facets=["architecture", "security"],
            squad_needed=True,
            suggested_roles=roles,
            collaboration_protocol=protocol,
            # Each parametrized case's protocol role set happens to contain
            # no shared-skill pair (debater↔implementer share code-review
            # and architect↔orchestrator share system-design, but those
            # pairs never co-occur within a single case): a shared skill
            # would lose conflict resolution on the non-lead role, leaving
            # its assignment empty (→ 0.0).
            per_agent_skills={
                "architect": ["system-design"],
                "red_team": ["security-audit"],
                "implementer": ["code-review"],
                "debater": ["code-review"],
                "orchestrator": ["system-design"],
            },
            confidence=0.9,
        )

        plan = builder.build_plan(
            "design and audit",
            [SubTask(intent="placeholder", query="placeholder")],
            workflow_pattern=pattern,
            metadata={"intent_analysis": analysis},
        )

        assert plan.steps, pattern
        for step in plan.steps:
            assert step.role_skills, (pattern, step.assigned_role, step.role_skills)
            assert step.confidence == 0.99, (pattern, step.assigned_role, step.confidence)

    def test_squad_steps_empty_skill_ids_zero_confidence(self) -> None:
        """Empty skill assignment (no catalog match → fallback-llm) must NOT
        carry the 0.99 sentinel: with confidence 0.0 the ambiguous_only
        all_confident fold stays False, so a plan with no real skills cannot
        silently auto-proceed without user confirmation."""
        router = FakeRouter(default=self._route("generic"))
        router._skill_loader = FakeSkillLoader({})
        builder = PlanBuilder(router)
        analysis = IntentAnalysis(
            complexity="multi_agent",
            facets=["architecture", "security"],
            squad_needed=True,
            suggested_roles=["architect", "red_team"],
            collaboration_protocol="red_team",
            confidence=0.9,
        )

        plan = builder.build_plan(
            "design and audit",
            [SubTask(intent="placeholder", query="placeholder")],
            workflow_pattern=WorkflowPattern.AGENT_SQUAD,
            metadata={"intent_analysis": analysis},
        )

        assert plan.steps
        for step in plan.steps:
            assert step.skill_id == "fallback-llm", (step.assigned_role, step.skill_id)
            assert step.confidence == 0.0, (step.assigned_role, step.confidence)
        # ambiguous_only auto-proceed folds
        # all(step.confidence >= auto_select_threshold) with default 0.6 —
        # confidence 0.0 keeps the fold False → confirmation is shown.
        assert not all(step.confidence >= 0.6 for step in plan.steps)

    def test_squad_step_dependencies_wired(self) -> None:
        router = self._make_router_with_skills()
        builder = PlanBuilder(router)
        analysis = IntentAnalysis(
            complexity="composite",
            facets=["implement_feature"],
            squad_needed=False,
            suggested_roles=["implementer", "reviewer"],
            collaboration_protocol="review_gate",
            per_agent_skills={
                "implementer": ["code-review"],
                "reviewer": ["code-review"],
            },
            confidence=0.9,
        )

        plan = builder.build_plan(
            "review gate",
            [SubTask(intent="placeholder", query="placeholder")],
            workflow_pattern=WorkflowPattern.AGENT_SQUAD,
            metadata={"intent_analysis": analysis},
        )

        implementer_step = next(s for s in plan.steps if s.assigned_role == "implementer")
        reviewer_step = next(s for s in plan.steps if s.assigned_role == "reviewer")
        assert (
            reviewer_step.step_id in implementer_step.dependencies
            or implementer_step.step_id in reviewer_step.dependencies
        )
