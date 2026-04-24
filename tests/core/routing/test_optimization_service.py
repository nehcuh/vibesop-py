"""Tests for OptimizationService session stickiness and optimizations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from vibesop.core.matching import MatchResult, RoutingContext
from vibesop.core.models import RoutingLayer
from vibesop.core.routing.optimization_service import OptimizationService


class TestSessionStickiness:
    """Test session stickiness boosting in OptimizationService."""

    def _make_service(self):
        """Create a minimal OptimizationService for testing."""
        config = MagicMock()
        config.min_confidence = 0.3
        config.max_candidates = 3
        config.session_stickiness_boost = 0.03

        optimization_config = MagicMock()
        optimization_config.enabled = False
        optimization_config.preference_boost.enabled = False

        preference_booster = MagicMock()
        cluster_index = MagicMock()
        conflict_resolver = MagicMock()
        conflict_resolver.resolve = MagicMock(
            side_effect=lambda matches, _query, **_kw: MagicMock(
                primary=matches[0].skill_id if matches else None,
                alternatives=[m.skill_id for m in matches[1:3]],
            )
        )

        return OptimizationService(
            config=config,
            optimization_config=optimization_config,
            preference_booster=preference_booster,
            cluster_index=cluster_index,
            conflict_resolver=conflict_resolver,
            get_instinct_learner=MagicMock(),
        )

    def test_no_boost_without_current_skill(self):
        """Test that no stickiness is applied when no current_skill in context."""
        service = self._make_service()
        matches = [
            MatchResult(skill_id="skill-a", confidence=0.8, matcher_type=RoutingLayer.KEYWORD),
            MatchResult(skill_id="skill-b", confidence=0.7, matcher_type=RoutingLayer.KEYWORD),
        ]

        result = service._apply_session_stickiness(matches, context=None)

        assert result[0].confidence == 0.8
        assert result[1].confidence == 0.7

    def test_boost_current_skill(self):
        """Test that current skill gets a confidence boost."""
        service = self._make_service()
        matches = [
            MatchResult(skill_id="skill-a", confidence=0.75, matcher_type=RoutingLayer.KEYWORD),
            MatchResult(skill_id="skill-b", confidence=0.80, matcher_type=RoutingLayer.KEYWORD),
        ]
        context = RoutingContext(current_skill="skill-a")

        result = service._apply_session_stickiness(matches, context)

        # skill-a should be boosted
        skill_a = next(m for m in result if m.skill_id == "skill-a")
        assert skill_a.confidence == 0.78  # 0.75 + 0.03
        assert skill_a.metadata.get("session_boost") is True

        # skill-b should remain unchanged
        skill_b = next(m for m in result if m.skill_id == "skill-b")
        assert skill_b.confidence == 0.80

    def test_boost_capped_at_1_0(self):
        """Test that boost does not exceed 1.0 confidence."""
        service = self._make_service()
        matches = [
            MatchResult(skill_id="skill-a", confidence=0.99, matcher_type=RoutingLayer.KEYWORD),
        ]
        context = RoutingContext(current_skill="skill-a")

        result = service._apply_session_stickiness(matches, context)

        assert result[0].confidence == 1.0

    def test_reordering_after_boost(self):
        """Test that boosted skill can overtake higher-confidence alternatives."""
        service = self._make_service()
        matches = [
            MatchResult(skill_id="skill-a", confidence=0.78, matcher_type=RoutingLayer.KEYWORD),  # current skill
            MatchResult(skill_id="skill-b", confidence=0.80, matcher_type=RoutingLayer.KEYWORD),  # higher but not current
        ]
        context = RoutingContext(current_skill="skill-a")

        result = service._apply_session_stickiness(matches, context)

        # After boost (0.78 + 0.03 = 0.81), skill-a should be first
        assert result[0].skill_id == "skill-a"
        assert result[0].confidence == 0.81
        assert result[1].skill_id == "skill-b"

    def test_score_breakdown_includes_stickiness(self):
        """Test that score_breakdown records the session_stickiness boost."""
        service = self._make_service()
        matches = [
            MatchResult(skill_id="skill-a", confidence=0.5, matcher_type=RoutingLayer.KEYWORD),
        ]
        context = RoutingContext(current_skill="skill-a")

        result = service._apply_session_stickiness(matches, context)

        assert "session_stickiness" in result[0].score_breakdown
        assert result[0].score_breakdown["session_stickiness"] == 0.03

    def test_configurable_stickiness_boost(self):
        """Test that session_stickiness_boost config is respected."""
        service = self._make_service()
        service._config.session_stickiness_boost = 0.08
        matches = [
            MatchResult(skill_id="skill-a", confidence=0.5, matcher_type=RoutingLayer.KEYWORD),
        ]
        context = RoutingContext(current_skill="skill-a")

        result = service._apply_session_stickiness(matches, context)

        assert result[0].confidence == 0.58
        assert result[0].score_breakdown["session_stickiness"] == 0.08

    def test_zero_stickiness_boost(self):
        """Test that boost can be disabled by setting to 0."""
        service = self._make_service()
        service._config.session_stickiness_boost = 0.0
        matches = [
            MatchResult(skill_id="skill-a", confidence=0.5, matcher_type=RoutingLayer.KEYWORD),
        ]
        context = RoutingContext(current_skill="skill-a")

        result = service._apply_session_stickiness(matches, context)

        assert result[0].confidence == 0.5
        assert result[0].metadata.get("session_boost") is None


class TestQualityBoost:
    """Test quality-based boosting from evaluator grades."""

    def _make_service(self):
        """Create a minimal OptimizationService for testing."""
        config = MagicMock()
        config.min_confidence = 0.3
        config.max_candidates = 3
        config.session_stickiness_boost = 0.03

        optimization_config = MagicMock()
        optimization_config.enabled = False
        optimization_config.preference_boost.enabled = False

        preference_booster = MagicMock()
        cluster_index = MagicMock()
        conflict_resolver = MagicMock()
        conflict_resolver.resolve = MagicMock(
            side_effect=lambda matches, _query, **_kw: MagicMock(
                primary=matches[0].skill_id if matches else None,
                alternatives=[m.skill_id for m in matches[1:3]],
            )
        )

        return OptimizationService(
            config=config,
            optimization_config=optimization_config,
            preference_booster=preference_booster,
            cluster_index=cluster_index,
            conflict_resolver=conflict_resolver,
            get_instinct_learner=MagicMock(),
        )

    def test_grade_a_gets_boost(self):
        """Test that Grade A skills receive +0.05 boost."""
        service = self._make_service()
        matches = [
            MatchResult(skill_id="skill-a", confidence=0.70, matcher_type=RoutingLayer.KEYWORD),
        ]

        mock_eval = MagicMock()
        mock_eval.total_routes = 5
        mock_eval.grade = "A"

        with patch("vibesop.core.skills.evaluator.RoutingEvaluator") as MockEval:
            MockEval.return_value.evaluate_skill = MagicMock(return_value=mock_eval)
            result = service._apply_quality_boost(matches)

        assert result[0].confidence == 0.75
        assert result[0].score_breakdown["quality_adjustment"] == 0.05
        assert result[0].metadata["grade"] == "A"

    def test_grade_f_gets_demoted(self):
        """Test that Grade F skills receive -0.05 demotion."""
        service = self._make_service()
        matches = [
            MatchResult(skill_id="skill-f", confidence=0.50, matcher_type=RoutingLayer.KEYWORD),
        ]

        mock_eval = MagicMock()
        mock_eval.total_routes = 5
        mock_eval.grade = "F"

        with patch("vibesop.core.skills.evaluator.RoutingEvaluator") as MockEval:
            MockEval.return_value.evaluate_skill = MagicMock(return_value=mock_eval)
            result = service._apply_quality_boost(matches)

        assert result[0].confidence == 0.45
        assert result[0].score_breakdown["quality_adjustment"] == -0.05
        assert result[0].metadata["grade"] == "F"

    def test_insufficient_routes_no_adjustment(self):
        """Test that skills with <3 routes are not adjusted."""
        service = self._make_service()
        matches = [
            MatchResult(skill_id="skill-new", confidence=0.70, matcher_type=RoutingLayer.KEYWORD),
        ]

        mock_eval = MagicMock()
        mock_eval.total_routes = 2
        mock_eval.grade = "F"

        with patch("vibesop.core.skills.evaluator.RoutingEvaluator") as MockEval:
            MockEval.return_value.evaluate_skill = MagicMock(return_value=mock_eval)
            result = service._apply_quality_boost(matches)

        # Should not be adjusted because total_routes < 3
        assert result[0].confidence == 0.70
        assert "quality_adjustment" not in result[0].score_breakdown

    def test_no_evaluator_skips_gracefully(self):
        """Test that missing evaluator data skips without error."""
        service = self._make_service()
        matches = [
            MatchResult(skill_id="skill-x", confidence=0.70, matcher_type=RoutingLayer.KEYWORD),
        ]

        with patch("vibesop.core.skills.evaluator.RoutingEvaluator") as MockEval:
            MockEval.return_value.evaluate_skill = MagicMock(return_value=None)
            result = service._apply_quality_boost(matches)

        assert result[0].confidence == 0.70

    def test_grade_c_no_change(self):
        """Test that Grade C skills receive 0 adjustment."""
        service = self._make_service()
        matches = [
            MatchResult(skill_id="skill-c", confidence=0.70, matcher_type=RoutingLayer.KEYWORD),
        ]

        mock_eval = MagicMock()
        mock_eval.total_routes = 5
        mock_eval.grade = "C"

        with patch("vibesop.core.skills.evaluator.RoutingEvaluator") as MockEval:
            MockEval.return_value.evaluate_skill = MagicMock(return_value=mock_eval)
            result = service._apply_quality_boost(matches)

        assert result[0].confidence == 0.70
        assert "quality_adjustment" not in result[0].score_breakdown

    def test_reordering_after_quality_boost(self):
        """Test that Grade A can overtake higher-confidence Grade C."""
        service = self._make_service()
        matches = [
            MatchResult(skill_id="grade-a", confidence=0.78, matcher_type=RoutingLayer.KEYWORD),
            MatchResult(skill_id="grade-c", confidence=0.80, matcher_type=RoutingLayer.KEYWORD),
        ]

        def mock_evaluate(skill_id):
            if skill_id == "grade-a":
                return MagicMock(total_routes=5, grade="A")
            return MagicMock(total_routes=5, grade="C")

        with patch("vibesop.core.skills.evaluator.RoutingEvaluator") as MockEval:
            MockEval.return_value.evaluate_skill = mock_evaluate
            result = service._apply_quality_boost(matches)

        # grade-a (0.78 + 0.05 = 0.83) should overtake grade-c (0.80)
        assert result[0].skill_id == "grade-a"
        assert result[0].confidence == pytest.approx(0.83)


class TestHabitBoost:
    """Test habit-based boosting from session learning."""

    def _make_service(self):
        """Create a minimal OptimizationService for testing."""
        config = MagicMock()
        config.min_confidence = 0.3
        config.max_candidates = 3
        config.session_stickiness_boost = 0.03

        optimization_config = MagicMock()
        optimization_config.enabled = False
        optimization_config.preference_boost.enabled = False

        preference_booster = MagicMock()
        cluster_index = MagicMock()
        conflict_resolver = MagicMock()
        conflict_resolver.resolve = MagicMock(
            side_effect=lambda matches, _query, **_kw: MagicMock(
                primary=matches[0].skill_id if matches else None,
                alternatives=[m.skill_id for m in matches[1:3]],
            )
        )

        return OptimizationService(
            config=config,
            optimization_config=optimization_config,
            preference_booster=preference_booster,
            cluster_index=cluster_index,
            conflict_resolver=conflict_resolver,
            get_instinct_learner=MagicMock(),
        )

    def test_habit_boost_applied(self):
        """Test that learned habit skills receive +0.08 boost."""
        service = self._make_service()
        matches = [
            MatchResult(skill_id="habit-skill", confidence=0.70, matcher_type=RoutingLayer.KEYWORD),
            MatchResult(skill_id="other", confidence=0.75, matcher_type=RoutingLayer.KEYWORD),
        ]
        context = RoutingContext(habit_boosts={"habit-skill": 0.08})

        result = service._apply_habit_boost(matches, context)

        habit = next(m for m in result if m.skill_id == "habit-skill")
        assert habit.confidence == pytest.approx(0.78)
        assert habit.metadata.get("habit_boost") is True

    def test_no_habit_boosts_skips(self):
        """Test that empty habit_boosts dict skips processing."""
        service = self._make_service()
        matches = [
            MatchResult(skill_id="skill-a", confidence=0.70, matcher_type=RoutingLayer.KEYWORD),
        ]
        context = RoutingContext(habit_boosts={})

        result = service._apply_habit_boost(matches, context)

        assert result[0].confidence == 0.70

    def test_no_context_skips(self):
        """Test that missing context skips habit boost."""
        service = self._make_service()
        matches = [
            MatchResult(skill_id="skill-a", confidence=0.70, matcher_type=RoutingLayer.KEYWORD),
        ]

        result = service._apply_habit_boost(matches, context=None)

        assert result[0].confidence == 0.70

    def test_unmatched_habit_skill_unchanged(self):
        """Test that habit boosts for non-matching skills don't affect others."""
        service = self._make_service()
        matches = [
            MatchResult(skill_id="skill-a", confidence=0.70, matcher_type=RoutingLayer.KEYWORD),
        ]
        context = RoutingContext(habit_boosts={"different-skill": 0.08})

        result = service._apply_habit_boost(matches, context)

        assert result[0].confidence == 0.70
