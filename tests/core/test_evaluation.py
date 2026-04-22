"""Tests for RoutingEvaluator and skill quality metrics."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vibesop.core.evaluation import RoutingEvaluator, SkillEvaluation


class TestSkillEvaluation:
    """Test SkillEvaluation dataclass."""

    def test_quality_score_with_data(self):
        """Quality score should combine success_rate, user_score, and confidence."""
        eval = SkillEvaluation(
            skill_id="test-skill",
            total_routes=10,
            success_rate=1.0,
            avg_confidence=0.8,
            user_score=0.9,
        )
        # 1.0 * 0.4 + 0.9 * 0.4 + 0.8 * 0.2 = 0.4 + 0.36 + 0.16 = 0.92
        assert eval.quality_score == pytest.approx(0.92, rel=1e-3)

    def test_quality_score_no_routes(self):
        """Quality score should be neutral when no route data exists."""
        eval = SkillEvaluation(skill_id="test-skill", total_routes=0)
        # 0.5 + (0.0 * 0.1) = 0.5
        assert eval.quality_score == pytest.approx(0.5, rel=1e-3)

    def test_to_dict(self):
        """to_dict should include all fields."""
        eval = SkillEvaluation(
            skill_id="test-skill",
            total_routes=5,
            success_rate=0.8,
            avg_confidence=0.7,
            user_score=0.6,
        )
        d = eval.to_dict()
        assert d["skill_id"] == "test-skill"
        assert d["total_routes"] == 5
        assert d["quality_score"] == pytest.approx(0.70, rel=1e-3)


class TestRoutingEvaluator:
    """Test RoutingEvaluator integration."""

    def test_evaluate_skill_no_data(self, tmp_path):
        """Evaluate skill with no data should return neutral evaluation."""
        evaluator = RoutingEvaluator(project_root=tmp_path)
        result = evaluator.evaluate_skill("nonexistent-skill")
        assert result is not None
        assert result.skill_id == "nonexistent-skill"
        assert result.total_routes == 0
        assert result.quality_score == pytest.approx(0.5, rel=1e-3)

    def test_evaluate_skill_with_feedback(self, tmp_path):
        """Evaluate skill with feedback records."""
        evaluator = RoutingEvaluator(project_root=tmp_path)

        # Mock feedback collector
        mock_feedback = MagicMock()
        mock_feedback.get_records.return_value = [
            MagicMock(routed_skill="my-skill", was_correct=True, confidence=0.9, timestamp="2024-01-01T00:00:00"),
            MagicMock(routed_skill="my-skill", was_correct=True, confidence=0.8, timestamp="2024-01-02T00:00:00"),
            MagicMock(routed_skill="my-skill", was_correct=False, confidence=0.6, timestamp="2024-01-03T00:00:00"),
        ]
        evaluator._feedback = mock_feedback

        # Mock preference learner
        mock_prefs = MagicMock()
        mock_prefs.get_preference_score.return_value = 0.75
        evaluator._preferences = mock_prefs

        result = evaluator.evaluate_skill("my-skill")
        assert result is not None
        assert result.total_routes == 3
        assert result.success_rate == pytest.approx(2 / 3, rel=1e-3)
        assert result.avg_confidence == pytest.approx(0.766, rel=1e-2)
        assert result.user_score == 0.75
        assert result.last_used == "2024-01-03T00:00:00"

    def test_evaluate_all_skills(self, tmp_path):
        """Evaluate all skills should aggregate from feedback and preferences."""
        evaluator = RoutingEvaluator(project_root=tmp_path)

        mock_feedback = MagicMock()
        mock_feedback.get_records.return_value = [
            MagicMock(routed_skill="skill-a", was_correct=True, confidence=0.9, timestamp="2024-01-01T00:00:00"),
        ]
        evaluator._feedback = mock_feedback

        mock_prefs = MagicMock()
        mock_prefs.get_preference_score.return_value = 0.5
        evaluator._preferences = mock_prefs

        results = evaluator.evaluate_all_skills()
        assert "skill-a" in results
        assert results["skill-a"].total_routes == 1

    def test_get_low_quality_skills(self, tmp_path):
        """Low quality skills should be identified based on threshold."""
        evaluator = RoutingEvaluator(project_root=tmp_path)

        mock_feedback = MagicMock()
        mock_feedback.get_records.return_value = [
            MagicMock(routed_skill="good-skill", was_correct=True, confidence=0.9, timestamp="2024-01-01T00:00:00"),
            MagicMock(routed_skill="good-skill", was_correct=True, confidence=0.9, timestamp="2024-01-02T00:00:00"),
            MagicMock(routed_skill="good-skill", was_correct=True, confidence=0.9, timestamp="2024-01-03T00:00:00"),
            MagicMock(routed_skill="bad-skill", was_correct=False, confidence=0.3, timestamp="2024-01-01T00:00:00"),
            MagicMock(routed_skill="bad-skill", was_correct=False, confidence=0.3, timestamp="2024-01-02T00:00:00"),
            MagicMock(routed_skill="bad-skill", was_correct=False, confidence=0.3, timestamp="2024-01-03T00:00:00"),
        ]
        evaluator._feedback = mock_feedback

        mock_prefs = MagicMock()
        mock_prefs.get_preference_score.return_value = 0.5
        evaluator._preferences = mock_prefs

        low_quality = evaluator.get_low_quality_skills(threshold=0.3, min_routes=3)
        assert len(low_quality) == 1
        assert low_quality[0].skill_id == "bad-skill"

    def test_generate_report(self, tmp_path):
        """Report should contain summary statistics."""
        evaluator = RoutingEvaluator(project_root=tmp_path)

        mock_feedback = MagicMock()
        mock_feedback.get_records.return_value = [
            MagicMock(routed_skill="skill-a", was_correct=True, confidence=0.9, timestamp="2024-01-01T00:00:00"),
        ]
        evaluator._feedback = mock_feedback

        mock_prefs = MagicMock()
        mock_prefs.get_preference_score.return_value = 0.8
        evaluator._preferences = mock_prefs

        report = evaluator.generate_report()
        assert report["total_skills_evaluated"] == 1
        assert report["avg_quality_score"] > 0
