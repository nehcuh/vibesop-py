"""Tests for evaluation shim and re-exported logic."""

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from vibesop.core.evaluation import RoutingEvaluator, SkillEvaluation


class TestSkillEvaluation:
    """Test SkillEvaluation dataclass."""

    def test_defaults(self):
        """SkillEvaluation should use sensible defaults."""
        eval = SkillEvaluation(skill_id="test-skill")
        assert eval.skill_id == "test-skill"
        assert eval.total_routes == 0
        assert eval.routing_accuracy == 0.0
        assert eval.user_satisfaction == 0.0
        assert eval.execution_success == 0.0
        assert eval.usage_frequency == 0.0
        assert eval.health_score == 0.0
        assert eval.avg_confidence == 0.0
        assert eval.user_score == 0.0
        assert eval.last_used is None

    def test_quality_score_with_routes(self):
        """quality_score should weight all 5 dimensions when routes exist."""
        eval = SkillEvaluation(
            skill_id="s",
            total_routes=5,
            routing_accuracy=1.0,
            user_satisfaction=1.0,
            execution_success=1.0,
            usage_frequency=1.0,
            health_score=1.0,
        )
        assert eval.quality_score == pytest.approx(1.0)

    def test_quality_score_no_routes(self):
        """Zero-sample skills score 0.0 — no data is not a neutral 0.5."""
        eval = SkillEvaluation(skill_id="s", total_routes=0)
        assert eval.quality_score == 0.0
        # Atomic pair: a bare 0.0 must not flow through to a letter grade.
        assert eval.grade == "?"

    def test_quality_score_no_routes_with_confidence_and_user_score(self):
        """Zero-sample score stays 0.0 regardless of confidence/user_score."""
        eval = SkillEvaluation(skill_id="s", total_routes=0, avg_confidence=1.0, user_score=1.0)
        assert eval.quality_score == 0.0
        assert eval.grade == "?"

    def test_zero_sample_grade_is_not_a_letter(self):
        """must-NOT: zero-sample grade must never be D or F.

        A 0.0-quality skill graded F would trip the auto-deprecate rule in
        feedback_loop (F + 30d stale + ≥3 uses with routing accuracy < 50%)
        — the reason the quality_score=0.0 / grade="?" pair must land
        atomically.
        """
        eval = SkillEvaluation(skill_id="s", total_routes=0)
        assert eval.grade not in ("A", "B", "C", "D", "F")

    def test_grade_vocabulary_includes_question_mark(self):
        """The grade vocabulary is A/B/C/D/F plus "?" (no routing feedback)."""
        grades = {
            SkillEvaluation(skill_id="s", total_routes=0).grade,
            SkillEvaluation(
                skill_id="s",
                total_routes=1,
                routing_accuracy=1.0,
                user_satisfaction=1.0,
                execution_success=1.0,
                usage_frequency=1.0,
                health_score=1.0,
            ).grade,
            SkillEvaluation(skill_id="s", total_routes=1).grade,
        }
        assert "?" in grades
        assert grades == {"?", "A", "F"}

    def test_grade_boundaries(self):
        """grade should map correctly to letter boundaries."""
        assert (
            SkillEvaluation(
                skill_id="s",
                total_routes=1,
                routing_accuracy=1.0,
                user_satisfaction=1.0,
                execution_success=1.0,
                usage_frequency=1.0,
                health_score=1.0,
            ).grade
            == "A"
        )
        assert (
            SkillEvaluation(
                skill_id="s",
                total_routes=1,
                routing_accuracy=0.75,
                user_satisfaction=0.75,
                execution_success=0.75,
                usage_frequency=0.75,
                health_score=0.75,
            ).grade
            == "B"
        )
        assert (
            SkillEvaluation(
                skill_id="s",
                total_routes=1,
                routing_accuracy=0.625,
                user_satisfaction=0.625,
                execution_success=0.625,
                usage_frequency=0.625,
                health_score=0.625,
            ).grade
            == "C"
        )
        assert (
            SkillEvaluation(
                skill_id="s",
                total_routes=1,
                routing_accuracy=0.5,
                user_satisfaction=0.5,
                execution_success=0.5,
                usage_frequency=0.5,
                health_score=0.5,
            ).grade
            == "D"
        )
        assert (
            SkillEvaluation(
                skill_id="s",
                total_routes=1,
                routing_accuracy=0.0,
                user_satisfaction=0.0,
                execution_success=0.0,
                usage_frequency=0.0,
                health_score=0.0,
            ).grade
            == "F"
        )

    def test_to_dict_contains_all_fields(self):
        """to_dict should include computed properties."""
        eval = SkillEvaluation(skill_id="s", total_routes=1, routing_accuracy=1.0)
        d = eval.to_dict()
        assert d["skill_id"] == "s"
        assert d["total_routes"] == 1
        assert d["routing_accuracy"] == 1.0
        assert "quality_score" in d
        assert "grade" in d


class TestRoutingEvaluator:
    """Test RoutingEvaluator via the evaluation shim."""

    def test_init_creates_collectors(self, tmp_path):
        """Evaluator should initialize default collectors."""
        evaluator = RoutingEvaluator(project_root=tmp_path)
        assert evaluator._feedback is not None
        assert evaluator._execution is not None
        assert evaluator._preferences is not None

    def test_init_with_explicit_collectors(self, tmp_path):
        """Evaluator should accept pre-configured collectors."""
        mock_feedback = MagicMock()
        mock_exec = MagicMock()
        mock_prefs = MagicMock()
        evaluator = RoutingEvaluator(
            project_root=tmp_path,
            feedback_collector=mock_feedback,
            execution_collector=mock_exec,
            preference_learner=mock_prefs,
        )
        assert evaluator._feedback is mock_feedback
        assert evaluator._execution is mock_exec
        assert evaluator._preferences is mock_prefs

    def test_evaluate_skill_no_data(self, tmp_path):
        """Evaluating a skill with no data returns a zero-sample result."""
        evaluator = RoutingEvaluator(project_root=tmp_path)
        result = evaluator.evaluate_skill("unknown-skill")
        assert result is not None
        assert result.skill_id == "unknown-skill"
        assert result.total_routes == 0
        assert result.quality_score == 0.0
        assert result.grade == "?"

    def test_evaluate_skill_with_feedback(self, tmp_path):
        """Evaluating a skill with feedback records computes metrics."""
        evaluator = RoutingEvaluator(project_root=tmp_path)

        mock_feedback = MagicMock()
        mock_feedback.get_records.return_value = [
            MagicMock(
                routed_skill="my-skill",
                was_correct=True,
                confidence=0.9,
                timestamp="2024-01-01T00:00:00",
            ),
            MagicMock(
                routed_skill="my-skill",
                was_correct=False,
                confidence=0.5,
                timestamp="2024-01-02T00:00:00",
            ),
        ]
        evaluator._feedback = mock_feedback

        mock_exec = MagicMock()
        mock_exec.get_skill_summary.return_value = {
            "total": 0,
            "helpful_rate": None,
            "success_rate": None,
        }
        evaluator._execution = mock_exec

        mock_prefs = MagicMock()
        mock_prefs.get_preference_score.return_value = 0.8
        evaluator._preferences = mock_prefs

        result = evaluator.evaluate_skill("my-skill")
        assert result is not None
        assert result.total_routes == 2
        assert result.routing_accuracy == pytest.approx(0.5)
        assert result.avg_confidence == pytest.approx(0.7)
        assert result.last_used == "2024-01-02T00:00:00"
        assert result.user_score == 0.8

    def test_evaluate_all_skills(self, tmp_path):
        """evaluate_all_skills should return results for all known skills."""
        evaluator = RoutingEvaluator(project_root=tmp_path)

        mock_feedback = MagicMock()
        mock_feedback.get_records.return_value = [
            MagicMock(
                routed_skill="skill-a",
                was_correct=True,
                confidence=0.9,
                timestamp="2024-01-01T00:00:00",
            ),
            MagicMock(
                routed_skill="skill-b",
                was_correct=False,
                confidence=0.3,
                timestamp="2024-01-01T00:00:00",
            ),
        ]
        evaluator._feedback = mock_feedback

        mock_exec = MagicMock()
        mock_exec.get_skill_summary.return_value = {
            "total": 0,
            "helpful_rate": None,
            "success_rate": None,
        }
        evaluator._execution = mock_exec

        mock_prefs = MagicMock()
        mock_prefs.get_preference_score.return_value = 0.5
        evaluator._preferences = mock_prefs

        results = evaluator.evaluate_all_skills()
        assert "skill-a" in results
        assert "skill-b" in results
        assert results["skill-a"].total_routes == 1
        assert results["skill-b"].total_routes == 1

    def test_evaluate_all_skills_single_pass_scaling(self, tmp_path, monkeypatch):
        """Synthetic-scale regression for the per-skill Counter rebuild.

        200 skills x 2000 routing records must complete well under 5s.
        The pre-fix per-skill O(distinct x records) recount took ~1.06s on
        this scale locally (post-fix ~0.012s); the loose bound guards CI
        jitter while still catching a quadratic regression.
        """
        from vibesop.core.skills.config_manager import SkillConfigManager

        n_skills, n_records = 200, 2000
        records = [
            SimpleNamespace(
                routed_skill=f"skill-{i % n_skills}",
                was_correct=True,
                confidence=0.8,
                timestamp=f"2026-08-{(i % 28) + 1:02d}T00:00:00",
            )
            for i in range(n_records)
        ]

        evaluator = RoutingEvaluator(project_root=tmp_path)

        mock_feedback = MagicMock()
        mock_feedback.get_records.return_value = records
        evaluator._feedback = mock_feedback

        mock_exec = MagicMock()
        mock_exec.get_skill_summary.return_value = {
            "total": 0,
            "helpful_rate": None,
            "success_rate": None,
        }
        mock_exec.get_records.return_value = []
        evaluator._execution = mock_exec

        mock_prefs = MagicMock()
        mock_prefs.get_preference_score.return_value = 0.5
        evaluator._preferences = mock_prefs

        # Isolate the counting hot path from unrelated per-skill I/O.
        monkeypatch.setattr(evaluator, "_get_health_score", lambda skill_id: 0.5)
        monkeypatch.setattr(
            SkillConfigManager, "get_skill_config", classmethod(lambda cls, skill_id: None)
        )

        start = time.perf_counter()
        results = evaluator.evaluate_all_skills()
        elapsed = time.perf_counter() - start

        assert len(results) == n_skills
        assert results["skill-0"].total_routes == n_records // n_skills
        assert results["skill-0"].usage_frequency == 1.0
        assert elapsed < 5.0

    def test_get_low_quality_skills(self, tmp_path):
        """get_low_quality_skills should filter by threshold and min_routes."""
        evaluator = RoutingEvaluator(project_root=tmp_path)

        mock_feedback = MagicMock()
        mock_feedback.get_records.return_value = [
            MagicMock(
                routed_skill="good",
                was_correct=True,
                confidence=0.9,
                timestamp="2024-01-01T00:00:00",
            ),
            MagicMock(
                routed_skill="good",
                was_correct=True,
                confidence=0.9,
                timestamp="2024-01-02T00:00:00",
            ),
            MagicMock(
                routed_skill="good",
                was_correct=True,
                confidence=0.9,
                timestamp="2024-01-03T00:00:00",
            ),
            MagicMock(
                routed_skill="bad",
                was_correct=False,
                confidence=0.2,
                timestamp="2024-01-01T00:00:00",
            ),
            MagicMock(
                routed_skill="bad",
                was_correct=False,
                confidence=0.2,
                timestamp="2024-01-02T00:00:00",
            ),
            MagicMock(
                routed_skill="bad",
                was_correct=False,
                confidence=0.2,
                timestamp="2024-01-03T00:00:00",
            ),
        ]
        evaluator._feedback = mock_feedback

        mock_exec = MagicMock()
        mock_exec.get_skill_summary.return_value = {
            "total": 0,
            "helpful_rate": None,
            "success_rate": None,
        }
        evaluator._execution = mock_exec

        mock_prefs = MagicMock()
        mock_prefs.get_preference_score.return_value = 0.5
        evaluator._preferences = mock_prefs

        low = evaluator.get_low_quality_skills(threshold=0.3, min_routes=3)
        assert len(low) == 1
        assert low[0].skill_id == "bad"

    def test_generate_report_empty(self, tmp_path):
        """generate_report with no skills should return zeros."""
        evaluator = RoutingEvaluator(project_root=tmp_path)
        report = evaluator.generate_report()
        assert report["total_skills_evaluated"] == 0
        assert report["avg_quality_score"] == 0.0
        assert report["low_quality_skills"] == []

    def test_generate_report_with_data(self, tmp_path):
        """generate_report should summarize evaluated skills."""
        evaluator = RoutingEvaluator(project_root=tmp_path)

        mock_feedback = MagicMock()
        mock_feedback.get_records.return_value = [
            MagicMock(
                routed_skill="skill-a",
                was_correct=True,
                confidence=0.9,
                timestamp="2024-01-01T00:00:00",
            ),
        ]
        evaluator._feedback = mock_feedback

        mock_exec = MagicMock()
        mock_exec.get_skill_summary.return_value = {
            "total": 0,
            "helpful_rate": None,
            "success_rate": None,
        }
        evaluator._execution = mock_exec

        mock_prefs = MagicMock()
        mock_prefs.get_preference_score.return_value = 0.8
        evaluator._preferences = mock_prefs

        report = evaluator.generate_report()
        assert report["total_skills_evaluated"] == 1
        assert report["avg_quality_score"] > 0


class TestModuleExports:
    """Test that the evaluation shim exports the expected names."""

    def test_all_exports(self):
        """__all__ should contain RoutingEvaluator and SkillEvaluation."""
        from vibesop.core import evaluation as eval_module

        assert set(eval_module.__all__) == {"RoutingEvaluator", "SkillEvaluation"}
