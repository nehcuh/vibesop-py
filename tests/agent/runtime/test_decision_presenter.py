"""Tests for DecisionPresenter."""

from __future__ import annotations

from vibesop.agent.runtime.decision_presenter import DecisionPresenter
from vibesop.core.models import (
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
    LayerDetail,
    OrchestrationMode,
    OrchestrationResult,
    RejectedCandidate,
    RoutingLayer,
    RoutingResult,
    SkillRoute,
)


class TestDecisionPresenter:
    """Test routing decision presentation."""

    def test_single_result_basic(self) -> None:
        presenter = DecisionPresenter()
        result = RoutingResult(
            primary=SkillRoute(
                skill_id="gstack/review",
                confidence=0.85,
                layer=RoutingLayer.KEYWORD,
                source="builtin",
                description="Code review skill",
            ),
            alternatives=[
                SkillRoute(
                    skill_id="superpowers-debug",
                    confidence=0.65,
                    layer=RoutingLayer.TFIDF,
                    source="builtin",
                ),
            ],
            routing_path=[RoutingLayer.KEYWORD],
            query="review my code",
        )

        present = presenter.present_single_result(result)

        assert "gstack/review" in present.message
        assert "85%" in present.message
        assert "keyword" in present.message
        assert "superpowers-debug" in present.message
        assert "65%" in present.message
        assert "accept" in present.actions

    def test_single_result_with_boosts(self) -> None:
        presenter = DecisionPresenter()
        result = RoutingResult(
            primary=SkillRoute(
                skill_id="gstack/review",
                confidence=0.88,
                layer=RoutingLayer.KEYWORD,
                source="builtin",
                metadata={"session_boost": True, "grade": "A"},
                score_breakdown={"base": 0.83, "session_stickiness": 0.05},
            ),
            routing_path=[RoutingLayer.KEYWORD],
            query="review my code",
        )

        present = presenter.present_single_result(result)

        assert "会话粘性" in present.message
        assert "💡" in present.message

    def test_fallback_result(self) -> None:
        presenter = DecisionPresenter()
        result = RoutingResult(
            primary=SkillRoute(
                skill_id="fallback-llm",
                confidence=1.0,
                layer=RoutingLayer.FALLBACK_LLM,
                source="builtin",
            ),
            routing_path=[RoutingLayer.FALLBACK_LLM],
            query="nonsense query",
        )

        present = presenter.present_single_result(result)

        assert "Fallback" in present.message or "fallback" in present.message
        assert "未找到" in present.message or "No" in present.message

    def test_no_match_result(self) -> None:
        presenter = DecisionPresenter()
        result = RoutingResult(
            primary=None,
            routing_path=[],
            query="something",
        )

        present = presenter.present_single_result(result)

        assert "未找到" in present.message or "Fallback" in present.message

    def test_orchestration_result(self) -> None:
        presenter = DecisionPresenter()
        plan = ExecutionPlan(
            plan_id="plan-123",
            original_query="analyze and optimize",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="superpowers-architect",
                    intent="Analyze architecture",
                    input_query="Analyze",
                ),
                ExecutionStep(
                    step_id="s2",
                    step_number=2,
                    skill_id="superpowers-optimize",
                    intent="Optimize performance",
                    input_query="Optimize",
                ),
            ],
            execution_mode=ExecutionMode.SEQUENTIAL,
        )

        result = OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            original_query="analyze and optimize",
            execution_plan=plan,
            single_fallback=SkillRoute(
                skill_id="superpowers-architect",
                confidence=0.87,
                layer=RoutingLayer.AI_TRIAGE,
                source="builtin",
            ),
        )

        present = presenter.present_orchestration_result(result)

        assert "多意图" in present.message or "multi" in present.message.lower()
        assert "superpowers-architect" in present.message
        assert "superpowers-optimize" in present.message
        assert "execute_plan" in present.actions
        assert "use_single" in present.actions

    def test_orchestration_single_fallback(self) -> None:
        presenter = DecisionPresenter()
        result = OrchestrationResult(
            mode=OrchestrationMode.SINGLE,
            original_query="review code",
            primary=SkillRoute(
                skill_id="gstack/review",
                confidence=0.92,
                layer=RoutingLayer.KEYWORD,
                source="builtin",
            ),
        )

        present = presenter.present_orchestration_result(result)

        assert "gstack/review" in present.message
        assert "92%" in present.message

    def test_rejected_candidates_shown(self) -> None:
        presenter = DecisionPresenter()
        result = RoutingResult(
            primary=SkillRoute(
                skill_id="gstack/review",
                confidence=0.82,
                layer=RoutingLayer.KEYWORD,
                source="builtin",
            ),
            routing_path=[RoutingLayer.KEYWORD, RoutingLayer.TFIDF],
            layer_details=[
                LayerDetail(
                    layer=RoutingLayer.KEYWORD,
                    matched=True,
                    reason="Direct keyword match",
                ),
                LayerDetail(
                    layer=RoutingLayer.TFIDF,
                    matched=False,
                    reason="No match above threshold",
                    rejected_candidates=[
                        RejectedCandidate(
                            skill_id="superpowers-debug",
                            confidence=0.55,
                            layer=RoutingLayer.TFIDF,
                            reason="below threshold (0.6)",
                        ),
                    ],
                ),
            ],
            query="review code",
        )

        present = presenter.present_single_result(result)

        assert "superpowers-debug" in present.message
        assert "55%" in present.message
        assert "below threshold" in present.message

    def test_structured_output(self) -> None:
        presenter = DecisionPresenter()
        result = RoutingResult(
            primary=SkillRoute(
                skill_id="test/skill",
                confidence=0.9,
                layer=RoutingLayer.EXPLICIT,
                source="builtin",
            ),
            routing_path=[RoutingLayer.EXPLICIT],
            query="test",
        )

        present = presenter.present_single_result(result)

        assert "primary" in present.structured
        assert present.structured["primary"]["skill_id"] == "test/skill"
        assert present.structured["primary"]["confidence"] == 0.9
