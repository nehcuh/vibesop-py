"""Tests for OptimizationService — preference boost, instinct boost, conflict resolution."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from vibesop.core.matching.base import MatchResult, MatcherType
from vibesop.core.routing.conflict import ConflictResolution
from vibesop.core.routing.optimization_service import OptimizationService


def _make_match(
    skill_id: str,
    confidence: float,
    matcher_type: MatcherType = MatcherType.KEYWORD,
    matched_keywords: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    score_breakdown: dict[str, float] | None = None,
) -> MatchResult:
    """Factory for test MatchResult objects."""
    return MatchResult(
        skill_id=skill_id,
        confidence=confidence,
        matcher_type=matcher_type,
        matched_keywords=matched_keywords or [],
        metadata=metadata or {},
        score_breakdown=score_breakdown or {},
    )


def _make_service(
    *,
    enabled: bool = True,
    preference_boost_enabled: bool = True,
    clustering_enabled: bool = True,
    min_skills_for_clustering: int = 3,
    session_stickiness_boost: float = 0.03,
    max_candidates: int = 3,
) -> OptimizationService:
    """Factory for an OptimizationService with mocked dependencies."""
    config = MagicMock()
    config.session_stickiness_boost = session_stickiness_boost
    config.max_candidates = max_candidates

    optimization_config = MagicMock()
    optimization_config.enabled = enabled
    optimization_config.preference_boost = MagicMock()
    optimization_config.preference_boost.enabled = preference_boost_enabled
    optimization_config.clustering = MagicMock()
    optimization_config.clustering.enabled = clustering_enabled
    optimization_config.clustering.min_skills_for_clustering = min_skills_for_clustering

    preference_booster = MagicMock()
    preference_booster.boost.side_effect = lambda matches, query: matches
    cluster_index = MagicMock()
    conflict_resolver = MagicMock()
    get_instinct_learner = MagicMock()

    return OptimizationService(
        config=config,
        optimization_config=optimization_config,
        preference_booster=preference_booster,
        cluster_index=cluster_index,
        conflict_resolver=conflict_resolver,
        get_instinct_learner=get_instinct_learner,
    )


class TestApplyOptimizations:
    """Test the main apply_optimizations pipeline."""

    def test_empty_matches_raises_value_error(self) -> None:
        """Empty matches list after boosts should raise ValueError."""
        svc = _make_service()
        with pytest.raises(ValueError, match="empty matches"):
            svc.apply_optimizations([], "query")

    def test_single_match_returns_match_and_empty_alternatives(self) -> None:
        """Single match bypasses conflict resolution and returns directly."""
        svc = _make_service()
        svc._preference_booster.boost.side_effect = lambda matches, query: matches
        match = _make_match("a", 0.9)
        primary, alternatives = svc.apply_optimizations([match], "query")
        assert primary.skill_id == "a"
        assert alternatives == []

    def test_full_pipeline_with_all_boosts(self) -> None:
        """All enabled boosts run and then conflict resolution is invoked."""
        svc = _make_service()
        svc._preference_booster.boost.side_effect = lambda matches, query: matches
        matches = [
            _make_match("a", 0.80),
            _make_match("b", 0.75),
        ]

        resolution = ConflictResolution(
            primary="a",
            alternatives=["b"],
            reason="test resolution",
        )
        svc._conflict_resolver.resolve.return_value = resolution

        primary, alternatives = svc.apply_optimizations(matches, "query")

        assert primary.skill_id == "a"
        assert [m.skill_id for m in alternatives] == ["b"]
        svc._conflict_resolver.resolve.assert_called_once()

    def test_pipeline_with_optimization_disabled(self) -> None:
        """When optimization is disabled, preference boost is skipped."""
        svc = _make_service(enabled=False, preference_boost_enabled=True)
        matches = [
            _make_match("a", 0.80),
            _make_match("b", 0.75),
        ]

        resolution = ConflictResolution(
            primary="a",
            alternatives=["b"],
            reason="test",
        )
        svc._conflict_resolver.resolve.return_value = resolution

        svc.apply_optimizations(matches, "query")

        svc._preference_booster.boost.assert_not_called()
        svc._conflict_resolver.resolve.assert_called_once()

    def test_preference_boost_failure_handled_gracefully(self) -> None:
        """Exception in preference boost is caught and pipeline continues."""
        svc = _make_service()
        svc._preference_booster.boost.side_effect = RuntimeError("boom")

        matches = [
            _make_match("a", 0.80),
            _make_match("b", 0.75),
        ]

        resolution = ConflictResolution(
            primary="a",
            alternatives=["b"],
            reason="test",
        )
        svc._conflict_resolver.resolve.return_value = resolution

        primary, _alternatives = svc.apply_optimizations(matches, "query")

        assert primary.skill_id == "a"
        svc._preference_booster.boost.assert_called_once()
        svc._conflict_resolver.resolve.assert_called_once()


class TestApplySessionStickiness:
    """Test _apply_session_stickiness."""

    def test_no_current_skill_no_change(self) -> None:
        """When context has no current_skill, matches are returned unchanged."""
        svc = _make_service(session_stickiness_boost=0.03)
        matches = [
            _make_match("a", 0.80),
            _make_match("b", 0.75),
        ]
        context = MagicMock()
        context.current_skill = None

        result = svc._apply_session_stickiness(matches, context)

        assert [m.skill_id for m in result] == ["a", "b"]
        assert result[0].confidence == pytest.approx(0.80)

    def test_current_skill_boosted_and_capped(self) -> None:
        """Current skill gets boosted; confidence is capped at 1.0."""
        svc = _make_service(session_stickiness_boost=0.10)
        matches = [
            _make_match("a", 0.96),
            _make_match("b", 0.80),
        ]
        context = MagicMock()
        context.current_skill = "a"

        result = svc._apply_session_stickiness(matches, context)

        assert result[0].skill_id == "a"
        assert result[0].confidence == pytest.approx(1.0)
        assert result[0].metadata.get("session_boost") is True
        assert result[0].score_breakdown.get("session_stickiness") == pytest.approx(0.10)

    def test_re_sorting_after_boost(self) -> None:
        """Boosted skill can overtake the top match."""
        svc = _make_service(session_stickiness_boost=0.10)
        matches = [
            _make_match("a", 0.80),
            _make_match("b", 0.75),
        ]
        context = MagicMock()
        context.current_skill = "b"

        result = svc._apply_session_stickiness(matches, context)

        assert result[0].skill_id == "b"
        assert result[0].confidence == pytest.approx(0.85)
        assert result[1].skill_id == "a"

    def test_zero_boost_returns_unchanged(self) -> None:
        """Zero or negative stickiness boost is a no-op."""
        svc = _make_service(session_stickiness_boost=0.0)
        matches = [
            _make_match("a", 0.80),
            _make_match("b", 0.75),
        ]
        context = MagicMock()
        context.current_skill = "b"

        result = svc._apply_session_stickiness(matches, context)

        assert [m.skill_id for m in result] == ["a", "b"]


class TestApplyHabitBoost:
    """Test _apply_habit_boost."""

    def test_no_habits_no_change(self) -> None:
        """When context has no habit_boosts, matches are returned unchanged."""
        svc = _make_service()
        matches = [
            _make_match("a", 0.80),
            _make_match("b", 0.75),
        ]
        context = MagicMock()
        context.habit_boosts = {}

        result = svc._apply_habit_boost(matches, context)

        assert [m.skill_id for m in result] == ["a", "b"]
        assert result[0].confidence == pytest.approx(0.80)

    def test_habit_boost_applied(self) -> None:
        """Skills with habit boosts receive confidence increase."""
        svc = _make_service()
        matches = [
            _make_match("a", 0.80),
            _make_match("b", 0.75),
        ]
        context = MagicMock()
        context.habit_boosts = {"b": 0.10}

        result = svc._apply_habit_boost(matches, context)

        assert result[0].skill_id == "b"
        assert result[0].confidence == pytest.approx(0.85)
        assert result[0].metadata.get("habit_boost") is True
        assert result[0].score_breakdown.get("habit_boost") == pytest.approx(0.10)

    def test_re_sorting_after_habit_boost(self) -> None:
        """Re-sorting places highest confidence first after habit boost."""
        svc = _make_service()
        matches = [
            _make_match("a", 0.90),
            _make_match("b", 0.85),
            _make_match("c", 0.80),
        ]
        context = MagicMock()
        context.habit_boosts = {"c": 0.15}

        result = svc._apply_habit_boost(matches, context)

        assert result[0].skill_id == "c"
        assert result[0].confidence == pytest.approx(0.95)


class TestApplyQualityBoost:
    """Test _apply_quality_boost."""

    def test_evaluator_lazy_loaded(self) -> None:
        """RoutingEvaluator is imported and instantiated on first call."""
        svc = _make_service()
        matches = [_make_match("a", 0.80)]

        mock_eval = MagicMock()
        mock_eval.evaluate_skill.return_value = MagicMock(total_routes=5, grade="A")

        svc._evaluator = mock_eval
        svc._apply_quality_boost(matches)

        assert svc._evaluator is mock_eval
        mock_eval.evaluate_skill.assert_called_once_with("a")

    def test_a_grade_plus_0_05(self) -> None:
        """Grade A skills receive +0.05 boost."""
        svc = _make_service()
        matches = [_make_match("a", 0.80)]

        mock_eval = MagicMock()
        mock_eval.evaluate_skill.return_value = MagicMock(total_routes=5, grade="A")

        svc._evaluator = mock_eval
        result = svc._apply_quality_boost(matches)

        assert result[0].confidence == pytest.approx(0.85)
        assert result[0].score_breakdown.get("quality_adjustment") == pytest.approx(0.05)
        assert result[0].metadata.get("grade") == "A"

    def test_f_grade_minus_0_05(self) -> None:
        """Grade F skills receive -0.05 demotion."""
        svc = _make_service()
        matches = [_make_match("a", 0.80)]

        mock_eval = MagicMock()
        mock_eval.evaluate_skill.return_value = MagicMock(total_routes=10, grade="F")

        svc._evaluator = mock_eval
        result = svc._apply_quality_boost(matches)

        assert result[0].confidence == pytest.approx(0.75)
        assert result[0].score_breakdown.get("quality_adjustment") == pytest.approx(-0.05)

    def test_insufficient_routes_ignored(self) -> None:
        """Skills with total_routes < 3 are not adjusted."""
        svc = _make_service()
        matches = [_make_match("a", 0.80)]

        mock_eval = MagicMock()
        mock_eval.evaluate_skill.return_value = MagicMock(total_routes=2, grade="A")

        svc._evaluator = mock_eval
        result = svc._apply_quality_boost(matches)

        assert result[0].confidence == pytest.approx(0.80)
        assert "quality_adjustment" not in result[0].score_breakdown

    def test_exception_caught_gracefully(self) -> None:
        """Exceptions during evaluation are caught and skill is left unchanged."""
        svc = _make_service()
        matches = [
            _make_match("a", 0.80),
            _make_match("b", 0.75),
        ]

        mock_eval = MagicMock()
        mock_eval.evaluate_skill.side_effect = [ValueError("bad eval"), None]

        svc._evaluator = mock_eval
        result = svc._apply_quality_boost(matches)

        assert result[0].confidence == pytest.approx(0.80)
        assert result[1].confidence == pytest.approx(0.75)

    def test_import_error_returns_unchanged(self) -> None:
        """If RoutingEvaluator cannot be imported, matches are returned unchanged."""
        svc = _make_service()
        matches = [_make_match("a", 0.80)]

        def _import_error(name, *args, **kwargs):
            if name == "vibesop.core.skills.evaluator":
                raise ImportError("No module named 'vibesop.core.skills.evaluator'")
            return __import__(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_import_error):
            result = svc._apply_quality_boost(matches)

        assert result[0].confidence == pytest.approx(0.80)


class TestApplyProjectContextBoost:
    """Test _apply_project_context_boost."""

    def test_no_project_type_no_change(self) -> None:
        """When context has no project_type, matches are returned unchanged."""
        svc = _make_service()
        matches = [_make_match("a", 0.80, matched_keywords=["python"])]
        context = MagicMock()
        context.project_type = None
        context.recent_files = []

        result = svc._apply_project_context_boost(matches, context)

        assert result[0].confidence == pytest.approx(0.80)

    def test_project_type_match_plus_0_04(self) -> None:
        """Skill keywords containing project_type receive +0.04."""
        svc = _make_service()
        matches = [
            _make_match("a", 0.80, matched_keywords=["python", "testing"]),
        ]
        context = MagicMock()
        context.project_type = "python"
        context.recent_files = []

        result = svc._apply_project_context_boost(matches, context)

        assert result[0].confidence == pytest.approx(0.84)
        assert result[0].score_breakdown.get("project_context") == pytest.approx(0.04)
        assert result[0].metadata.get("project_boost") is True

    def test_tech_stack_match_plus_0_02_each(self) -> None:
        """Each matched tech in recent_files adds +0.02."""
        svc = _make_service()
        matches = [
            _make_match("a", 0.80, matched_keywords=["pytest", "docker"]),
        ]
        context = MagicMock()
        context.project_type = "python"
        context.recent_files = ["pytest", "docker"]

        result = svc._apply_project_context_boost(matches, context)

        assert result[0].confidence == pytest.approx(0.84)
        assert result[0].score_breakdown.get("project_context") == pytest.approx(0.04)

    def test_re_sorting_after_project_boost(self) -> None:
        """Project boost can re-order matches."""
        svc = _make_service()
        matches = [
            _make_match("a", 0.80, matched_keywords=["rust"]),
            _make_match("b", 0.78, matched_keywords=["python"]),
        ]
        context = MagicMock()
        context.project_type = "python"
        context.recent_files = []

        result = svc._apply_project_context_boost(matches, context)

        assert result[0].skill_id == "b"
        assert result[0].confidence == pytest.approx(0.82)


class TestResolveConflicts:
    """Test resolve_conflicts delegation."""

    def test_successful_resolution(self) -> None:
        """Conflict resolver returns a resolution → primary and alternatives extracted."""
        svc = _make_service(max_candidates=3)
        matches = [
            _make_match("a", 0.90),
            _make_match("b", 0.80),
            _make_match("c", 0.70),
        ]

        resolution = ConflictResolution(
            primary="b",
            alternatives=["a", "c"],
            reason="test",
        )
        svc._conflict_resolver.resolve.return_value = resolution

        primary, alternatives = svc.resolve_conflicts(matches, "query")

        assert primary.skill_id == "b"
        assert [m.skill_id for m in alternatives] == ["a", "c"]

    def test_fallback_on_exception(self) -> None:
        """Exception in conflict resolver falls back to raw matches."""
        svc = _make_service(max_candidates=2)
        matches = [
            _make_match("a", 0.90),
            _make_match("b", 0.80),
            _make_match("c", 0.70),
        ]

        svc._conflict_resolver.resolve.side_effect = RuntimeError("boom")

        primary, alternatives = svc.resolve_conflicts(matches, "query")

        assert primary.skill_id == "a"
        assert [m.skill_id for m in alternatives] == ["b", "c"]

    def test_fallback_no_alternatives_when_max_candidates_zero(self) -> None:
        """Fallback respects max_candidates=0."""
        svc = _make_service(max_candidates=0)
        matches = [
            _make_match("a", 0.90),
            _make_match("b", 0.80),
        ]

        svc._conflict_resolver.resolve.side_effect = OSError("disk")

        primary, alternatives = svc.resolve_conflicts(matches, "query")

        assert primary.skill_id == "a"
        assert alternatives == []

    def test_resolution_with_no_primary(self) -> None:
        """When resolution.primary is None, fallback to first match."""
        svc = _make_service(max_candidates=2)
        matches = [
            _make_match("a", 0.90),
            _make_match("b", 0.80),
        ]

        resolution = ConflictResolution(
            primary=None,
            alternatives=["a", "b"],
            reason="no clear winner",
        )
        svc._conflict_resolver.resolve.return_value = resolution

        primary, alternatives = svc.resolve_conflicts(matches, "query")

        assert primary.skill_id == "a"
        assert [m.skill_id for m in alternatives] == ["b"]


class TestApplyInstinctBoost:
    """Test apply_instinct_boost."""

    def test_short_query_augmented_with_recent_queries(self) -> None:
        """Short queries (< 15 chars) are augmented with recent queries."""
        svc = _make_service()
        matches = [_make_match("a", 0.80)]

        instinct = type("Instinct", (), {"action": "suggest a", "confidence": 0.8})()

        learner = MagicMock()
        learner.find_matching.return_value = [instinct]
        svc._get_instinct_learner.return_value = learner

        context = MagicMock()
        context.recent_queries = ["previous query", "another query"]

        svc.apply_instinct_boost(matches, "short", context)

        learner.find_matching.assert_called_once()
        call_args = learner.find_matching.call_args
        assert "short" in call_args[0][0]
        assert "another query" in call_args[0][0]
        assert call_args[1]["min_confidence"] == pytest.approx(0.6)

    def test_cjk_follow_up_markers_trigger_augmentation(self) -> None:
        """CJK follow-up markers in query trigger augmentation even if not short."""
        svc = _make_service()
        matches = [_make_match("a", 0.80)]

        instinct = type("Instinct", (), {"action": "suggest a", "confidence": 0.8})()

        learner = MagicMock()
        learner.find_matching.return_value = [instinct]
        svc._get_instinct_learner.return_value = learner

        context = MagicMock()
        context.recent_queries = ["previous"]

        svc.apply_instinct_boost(matches, "还是继续", context)

        learner.find_matching.assert_called_once()
        call_args = learner.find_matching.call_args
        assert "previous" in call_args[0][0]
        assert "还是继续" in call_args[0][0]

    def test_instinct_match_boosts_skill(self) -> None:
        """Instinct that mentions a skill_id boosts that skill."""
        svc = _make_service()
        matches = [
            _make_match("systematic-debugging", 0.80),
            _make_match("other", 0.75),
        ]

        instinct = type(
            "Instinct",
            (),
            {"action": "suggest systematic-debugging skill", "confidence": 0.8},
        )()

        learner = MagicMock()
        learner.find_matching.return_value = [instinct]
        svc._get_instinct_learner.return_value = learner

        result = svc.apply_instinct_boost(matches, "debug", None)

        # The boosted skill should now be on top
        assert result[0].skill_id == "systematic-debugging"
        assert result[0].confidence > 0.80
        assert result[0].metadata.get("boosted") is True
        assert result[0].metadata.get("boost_source") == "instinct"

    def test_no_instincts_no_change(self) -> None:
        """When find_matching returns nothing, matches are returned unchanged."""
        svc = _make_service()
        matches = [_make_match("a", 0.80)]

        learner = MagicMock()
        learner.find_matching.return_value = []
        svc._get_instinct_learner.return_value = learner

        result = svc.apply_instinct_boost(matches, "query", None)

        assert result[0].confidence == pytest.approx(0.80)
        assert result[0].skill_id == "a"

    def test_instinct_lookup_exception_caught(self) -> None:
        """Exception during instinct lookup is caught and returns original matches."""
        svc = _make_service()
        matches = [_make_match("a", 0.80)]

        svc._get_instinct_learner.side_effect = RuntimeError("boom")

        result = svc.apply_instinct_boost(matches, "query", None)

        assert result[0].confidence == pytest.approx(0.80)

    def test_slash_skill_id_in_action(self) -> None:
        """Instinct action with slash-style skill ID is matched."""
        svc = _make_service()
        matches = [
            _make_match("gstack/review", 0.80),
        ]

        instinct = type("Instinct", (), {"action": "use gstack/review", "confidence": 0.8})()

        learner = MagicMock()
        learner.find_matching.return_value = [instinct]
        svc._get_instinct_learner.return_value = learner

        result = svc.apply_instinct_boost(matches, "review", None)

        assert result[0].confidence > 0.80

    def test_boost_map_no_match(self) -> None:
        """Instinct action that does not reference any candidate skill is ignored."""
        svc = _make_service()
        matches = [_make_match("xyz", 0.80)]

        instinct = type("Instinct", (), {"action": "do something unrelated", "confidence": 0.9})()

        learner = MagicMock()
        learner.find_matching.return_value = [instinct]
        svc._get_instinct_learner.return_value = learner

        result = svc.apply_instinct_boost(matches, "query", None)

        assert result[0].confidence == pytest.approx(0.80)


class TestEnsureClusterIndex:
    """Test ensure_cluster_index lazy building."""

    def test_disabled_no_op(self) -> None:
        """When clustering is disabled, build is never called."""
        svc = _make_service(clustering_enabled=False)
        svc.ensure_cluster_index([{"id": "a"}, {"id": "b"}, {"id": "c"}])
        svc._cluster_index.build.assert_not_called()
        assert svc._cluster_built is False

    def test_already_built_no_op(self) -> None:
        """When cluster index is already built, build is not called again."""
        svc = _make_service(clustering_enabled=True, min_skills_for_clustering=2)
        svc._cluster_built = True
        svc.ensure_cluster_index([{"id": "a"}, {"id": "b"}, {"id": "c"}])
        svc._cluster_index.build.assert_not_called()

    def test_builds_when_conditions_met(self) -> None:
        """Builds cluster index when enabled, not built, and enough candidates."""
        svc = _make_service(clustering_enabled=True, min_skills_for_clustering=3)
        candidates = [{"id": "a"}, {"id": "b"}, {"id": "c"}]

        svc.ensure_cluster_index(candidates)

        svc._cluster_index.build.assert_called_once_with(candidates)
        assert svc._cluster_built is True

    def test_not_enough_candidates_no_build(self) -> None:
        """When candidates are below min_skills_for_clustering, build is skipped."""
        svc = _make_service(clustering_enabled=True, min_skills_for_clustering=5)
        candidates = [{"id": "a"}, {"id": "b"}]

        svc.ensure_cluster_index(candidates)

        svc._cluster_index.build.assert_not_called()
        assert svc._cluster_built is False

    def test_optimization_disabled_no_build(self) -> None:
        """When optimization is disabled overall, clustering does not build."""
        svc = _make_service(enabled=False, clustering_enabled=True, min_skills_for_clustering=2)
        candidates = [{"id": "a"}, {"id": "b"}, {"id": "c"}]

        svc.ensure_cluster_index(candidates)

        svc._cluster_index.build.assert_not_called()
