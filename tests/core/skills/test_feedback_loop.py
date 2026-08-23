"""Tests for FeedbackLoop — quality-based retention and auto-deprecation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from vibesop.core.models import SkillLifecycle
from vibesop.core.skills.config_manager import SkillConfig
from vibesop.core.skills.evaluator import SkillEvaluation
from vibesop.core.skills.feedback_loop import FeedbackLoop


class TestFeedbackLoop:
    """Test FeedbackLoop retention analysis and auto-deprecation."""

    def _make_evaluation(
        self,
        skill_id: str,
        grade: str,
        total_routes: int = 5,
        last_used: str | None = None,
        quality: float = 0.5,
    ) -> SkillEvaluation:
        """Create SkillEvaluation with given quality score.

        quality < 0.4 → F, 0.4-0.59 → D, 0.6-0.74 → C,
        0.75-0.89 → B, >= 0.9 → A.
        """
        return SkillEvaluation(
            skill_id=skill_id,
            total_routes=total_routes,
            routing_accuracy=quality,
            user_satisfaction=quality,
            execution_success=quality,
            usage_frequency=quality,
            health_score=quality,
            avg_confidence=0.7,
            user_score=0.5,
            last_used=last_used,
        )

    def test_f_grade_deprecates(self) -> None:
        """F-grade + 30+ days unused + < 3 uses → deprecate."""
        evaluator = MagicMock()
        evaluator.evaluate_all_skills.return_value = {
            "test/skill": self._make_evaluation(
                "test/skill",
                "F",
                total_routes=1,
                quality=0.3,
                last_used="2026-04-01T00:00:00",
            ),
        }
        loop = FeedbackLoop(evaluator=evaluator)
        suggestions = loop.analyze_all(auto_deprecate=False)
        assert len(suggestions) == 1
        assert suggestions[0].action == "deprecate"
        assert suggestions[0].grade == "F"

    def test_d_grade_warns(self) -> None:
        """D-grade + 60+ days unused → warn."""
        evaluator = MagicMock()
        evaluator.evaluate_all_skills.return_value = {
            "test/skill": self._make_evaluation(
                "test/skill",
                "D",
                total_routes=5,
                quality=0.45,
                last_used="2026-03-01T00:00:00",
            ),
        }
        loop = FeedbackLoop(evaluator=evaluator)
        suggestions = loop.analyze_all(auto_deprecate=False)
        assert len(suggestions) == 1
        assert suggestions[0].action == "warn"
        assert suggestions[0].grade == "D"

    def test_a_grade_boosts(self) -> None:
        evaluator = MagicMock()
        evaluator.evaluate_all_skills.return_value = {
            "test/skill": self._make_evaluation("test/skill", "A", total_routes=5, quality=0.95),
        }
        loop = FeedbackLoop(evaluator=evaluator)
        suggestions = loop.analyze_all(auto_deprecate=False)
        assert len(suggestions) == 1
        assert suggestions[0].action == "boost"
        assert suggestions[0].grade == "A"

    def test_stale_skill_archives(self) -> None:
        evaluator = MagicMock()
        evaluator.evaluate_all_skills.return_value = {
            "test/stale": self._make_evaluation(
                "test/stale",
                "C",
                total_routes=3,
                last_used="2025-12-01T00:00:00",
                quality=0.65,
            ),
        }
        loop = FeedbackLoop(evaluator=evaluator)
        suggestions = loop.analyze_all(auto_deprecate=False)
        # More than 90 days since 2025-12-01
        assert len(suggestions) == 1
        assert suggestions[0].action == "archive"

    def test_recently_used_skill_not_archived(self) -> None:
        evaluator = MagicMock()
        evaluator.evaluate_all_skills.return_value = {
            "test/active": self._make_evaluation(
                "test/active",
                "C",
                total_routes=10,
                # FeedbackLoop parses last_used as a naive datetime, so
                # strip tzinfo. Relative "now" keeps this test from
                # rotting into the 90-day archive window.
                last_used=datetime.now(UTC).replace(tzinfo=None).isoformat(),
                quality=0.7,
            ),
        }
        loop = FeedbackLoop(evaluator=evaluator)
        suggestions = loop.analyze_all(auto_deprecate=False)
        # Used today — should not trigger archive
        assert len(suggestions) == 0

    def test_b_grade_no_action(self) -> None:
        evaluator = MagicMock()
        evaluator.evaluate_all_skills.return_value = {
            "test/good": self._make_evaluation("test/good", "B", total_routes=5, quality=0.8),
        }
        loop = FeedbackLoop(evaluator=evaluator)
        suggestions = loop.analyze_all(auto_deprecate=False)
        assert len(suggestions) == 0

    def test_low_routes_f_grade_not_deprecated(self) -> None:
        evaluator = MagicMock()
        evaluator.evaluate_all_skills.return_value = {
            "test/new": self._make_evaluation("test/new", "F", total_routes=1, quality=0.3),
        }
        loop = FeedbackLoop(evaluator=evaluator)
        suggestions = loop.analyze_all(auto_deprecate=False)
        # F-grade with only 1 route (below F_MIN_ROUTES=3) — no action
        assert len(suggestions) == 0

    def test_auto_deprecate_applies(self) -> None:
        evaluator = MagicMock()
        evaluator.evaluate_all_skills.return_value = {
            "test/bad": self._make_evaluation(
                "test/bad",
                "F",
                total_routes=1,
                quality=0.3,
                last_used="2026-04-01T00:00:00",
            ),
        }
        loop = FeedbackLoop(evaluator=evaluator)
        with patch.object(loop, "_apply_deprecation") as mock_apply:
            loop.analyze_all(auto_deprecate=True)
            mock_apply.assert_called_once()

    def test_suggestions_sorted_by_quality(self) -> None:
        evaluator = MagicMock()
        evaluator.evaluate_all_skills.return_value = {
            "test/good": self._make_evaluation("test/good", "A", total_routes=5, quality=0.95),
            "test/bad": self._make_evaluation(
                "test/bad",
                "F",
                total_routes=1,
                quality=0.3,
                last_used="2026-04-01T00:00:00",
            ),
        }
        loop = FeedbackLoop(evaluator=evaluator)
        suggestions = loop.analyze_all(auto_deprecate=False)
        # Sorted by quality_score ascending (worst first)
        assert suggestions[0].skill_id == "test/bad"
        assert suggestions[1].skill_id == "test/good"

    def test_generate_report(self) -> None:
        evaluator = MagicMock()
        evaluator.evaluate_all_skills.return_value = {
            "test/a": self._make_evaluation("test/a", "A", total_routes=5, quality=0.95),
            "test/f": self._make_evaluation(
                "test/f",
                "F",
                total_routes=1,
                quality=0.3,
                last_used="2026-04-01T00:00:00",
            ),
        }
        loop = FeedbackLoop(evaluator=evaluator)
        report = loop.generate_report()
        assert report["total_skills_analyzed"] == 2
        assert report["actions"]["deprecate"] == 1
        assert report["actions"]["boost"] == 1


class TestFeedbackLoopOptIn:
    """gate38: lifecycle writes are strictly opt-in (auto_deprecate=True)."""

    _SET_LIFECYCLE = "vibesop.core.skills.feedback_loop.SkillConfigManager.set_lifecycle"
    _GET_CONFIG = "vibesop.core.skills.feedback_loop.SkillConfigManager.get_skill_config"

    @staticmethod
    def _f_grade_eval(skill_id: str = "test/bad") -> SkillEvaluation:
        """Real F-grade evaluation: 30+ days unused, < 3 uses."""
        last_used = (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=45)).isoformat()
        return SkillEvaluation(
            skill_id=skill_id,
            total_routes=1,
            routing_accuracy=0.3,
            user_satisfaction=0.3,
            execution_success=0.3,
            usage_frequency=0.3,
            health_score=0.3,
            last_used=last_used,
        )

    def _loop_with(self, evaluations: dict[str, SkillEvaluation]) -> FeedbackLoop:
        evaluator = MagicMock()
        evaluator.evaluate_all_skills.return_value = evaluations
        return FeedbackLoop(evaluator=evaluator)

    def test_analyze_all_default_writes_nothing(self) -> None:
        loop = self._loop_with({"test/bad": self._f_grade_eval()})
        with patch(self._SET_LIFECYCLE) as mock_set:
            suggestions = loop.analyze_all()
            assert [s.action for s in suggestions] == ["deprecate"]
            mock_set.assert_not_called()
            assert loop.last_applied_skill_ids == []

    def test_generate_report_writes_nothing(self) -> None:
        loop = self._loop_with({"test/bad": self._f_grade_eval()})
        with patch(self._SET_LIFECYCLE) as mock_set:
            loop.generate_report()
            mock_set.assert_not_called()

    def test_end_of_session_check_writes_nothing(self) -> None:
        loop = self._loop_with({"test/bad": self._f_grade_eval()})
        with patch(self._SET_LIFECYCLE) as mock_set:
            loop.end_of_session_check()
            mock_set.assert_not_called()

    def test_zero_sample_never_disposed_even_with_auto(self) -> None:
        """Joint must-NOT: a zero-sample skill graded "?" produces no
        suggestion at all (no deprecate, no warn) and no lifecycle write,
        even under analyze_all(auto_deprecate=True)."""
        last_used = (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=90)).isoformat()
        evaluation = SkillEvaluation(skill_id="test/zero", total_routes=0, last_used=last_used)
        assert evaluation.grade == "?"
        loop = self._loop_with({"test/zero": evaluation})
        with patch(self._SET_LIFECYCLE) as mock_set:
            suggestions = loop.analyze_all(auto_deprecate=True)
            assert suggestions == []
            mock_set.assert_not_called()
            assert loop.last_applied_skill_ids == []

    def test_explicit_auto_still_deprecates_real_f(self) -> None:
        loop = self._loop_with({"test/bad": self._f_grade_eval()})
        with patch(self._SET_LIFECYCLE) as mock_set:
            suggestions = loop.analyze_all(auto_deprecate=True)
            assert [s.action for s in suggestions] == ["deprecate"]
            mock_set.assert_called_once_with("test/bad", "deprecated")
            assert loop.last_applied_skill_ids == ["test/bad"]

    def test_failed_apply_not_counted(self) -> None:
        """A set_lifecycle failure swallowed by _apply_* must not count
        as applied."""
        loop = self._loop_with({"test/bad": self._f_grade_eval()})
        with patch(self._SET_LIFECYCLE, side_effect=OSError("disk gone")):
            suggestions = loop.analyze_all(auto_deprecate=True)
            assert [s.action for s in suggestions] == ["deprecate"]
            assert loop.last_applied_skill_ids == []

    def test_boost_not_applied_without_auto(self) -> None:
        """A deprecated A-grade skill is not restored to active when
        auto_deprecate=False."""
        evaluation = SkillEvaluation(
            skill_id="test/great",
            total_routes=5,
            routing_accuracy=0.95,
            user_satisfaction=0.95,
            execution_success=0.95,
            usage_frequency=0.95,
            health_score=0.95,
        )
        loop = self._loop_with({"test/great": evaluation})
        deprecated_config = SkillConfig(skill_id="test/great", lifecycle=SkillLifecycle.DEPRECATED)
        with (
            patch(self._SET_LIFECYCLE) as mock_set,
            patch(self._GET_CONFIG, return_value=deprecated_config),
        ):
            suggestions = loop.analyze_all(auto_deprecate=False)
            assert [s.action for s in suggestions] == ["boost"]
            mock_set.assert_not_called()
            assert loop.last_applied_skill_ids == []

    def test_boost_restores_deprecated_with_auto(self) -> None:
        evaluation = SkillEvaluation(
            skill_id="test/great",
            total_routes=5,
            routing_accuracy=0.95,
            user_satisfaction=0.95,
            execution_success=0.95,
            usage_frequency=0.95,
            health_score=0.95,
        )
        loop = self._loop_with({"test/great": evaluation})
        deprecated_config = SkillConfig(skill_id="test/great", lifecycle=SkillLifecycle.DEPRECATED)
        with (
            patch(self._SET_LIFECYCLE) as mock_set,
            patch(self._GET_CONFIG, return_value=deprecated_config),
        ):
            loop.analyze_all(auto_deprecate=True)
            mock_set.assert_called_once_with("test/great", "active")
            assert loop.last_applied_skill_ids == ["test/great"]

    def test_boost_on_active_skill_not_counted(self) -> None:
        """must-NOT: a boost suggestion for an already-active skill is a
        no-op — no lifecycle write and it must not appear in applied ids."""
        evaluation = SkillEvaluation(
            skill_id="test/active",
            total_routes=5,
            routing_accuracy=0.95,
            user_satisfaction=0.95,
            execution_success=0.95,
            usage_frequency=0.95,
            health_score=0.95,
        )
        loop = self._loop_with({"test/active": evaluation})
        active_config = SkillConfig(skill_id="test/active", lifecycle=SkillLifecycle.ACTIVE)
        with (
            patch(self._SET_LIFECYCLE) as mock_set,
            patch(self._GET_CONFIG, return_value=active_config),
        ):
            suggestions = loop.analyze_all(auto_deprecate=True)
            assert [s.action for s in suggestions] == ["boost"]
            mock_set.assert_not_called()
            assert loop.last_applied_skill_ids == []
