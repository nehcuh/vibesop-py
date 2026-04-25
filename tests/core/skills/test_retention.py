"""Tests for RetentionPolicy."""

from unittest.mock import MagicMock

from vibesop.core.skills.retention import RetentionPolicy


class TestRetentionPolicy:
    """Test retention policy recommendations."""

    def test_analyze_skill_no_data(self):
        """Skill with no data should return 'none' action."""
        policy = RetentionPolicy()
        policy._evaluator.evaluate_skill = MagicMock(return_value=None)

        result = policy.analyze_skill("unknown-skill")
        assert result.action == "none"
        assert result.grade == "?"

    def test_suggest_removal_for_grade_f(self):
        """Grade F + 30+ days + <3 uses should suggest removal."""
        from vibesop.core.skills.evaluator import SkillEvaluation

        policy = RetentionPolicy()
        policy._evaluator.evaluate_skill = MagicMock(return_value=SkillEvaluation(
            skill_id="bad-skill",
            total_routes=2,
            routing_accuracy=0.0,
            user_satisfaction=0.0,
            execution_success=0.0,
            usage_frequency=0.0,
            health_score=0.0,
            last_used="2020-01-01T00:00:00",
        ))

        result = policy.analyze_skill("bad-skill")
        assert result.action == "remove"
        assert result.grade == "F"
        assert result.total_uses == 2

    def test_warn_for_grade_d(self):
        """Grade D + 60+ days should warn."""
        from vibesop.core.skills.evaluator import SkillEvaluation

        policy = RetentionPolicy()
        policy._evaluator.evaluate_skill = MagicMock(return_value=SkillEvaluation(
            skill_id="stale-skill",
            total_routes=5,
            routing_accuracy=0.5,
            user_satisfaction=0.5,
            execution_success=0.5,
            usage_frequency=0.5,
            health_score=0.5,
            last_used="2020-01-01T00:00:00",
        ))

        result = policy.analyze_skill("stale-skill")
        assert result.action == "warn"
        assert result.grade == "D"

    def test_highlight_for_grade_a(self):
        """Grade A + recent use should highlight."""
        from datetime import datetime

        from vibesop.core.skills.evaluator import SkillEvaluation

        policy = RetentionPolicy()
        recent = datetime.now().isoformat()
        policy._evaluator.evaluate_skill = MagicMock(return_value=SkillEvaluation(
            skill_id="great-skill",
            total_routes=50,
            routing_accuracy=1.0,
            user_satisfaction=1.0,
            execution_success=1.0,
            usage_frequency=1.0,
            health_score=1.0,
            last_used=recent,
        ))

        result = policy.analyze_skill("great-skill")
        assert result.action == "highlight"
        assert result.grade == "A"

    def test_analyze_all_filters_none(self):
        """analyze_all should only return actionable suggestions."""
        from vibesop.core.skills.evaluator import SkillEvaluation

        policy = RetentionPolicy()

        def mock_eval(skill_id):
            if skill_id == "bad":
                return SkillEvaluation(
                    skill_id="bad", total_routes=1,
                    routing_accuracy=0.0, user_satisfaction=0.0,
                    execution_success=0.0, usage_frequency=0.0,
                    health_score=0.0, last_used="2020-01-01T00:00:00",
                )
            return SkillEvaluation(
                skill_id="good", total_routes=10,
                routing_accuracy=0.9, user_satisfaction=0.9,
                execution_success=0.9, usage_frequency=0.8,
                health_score=0.8, last_used="2024-01-01T00:00:00",
            )

        policy._evaluator.evaluate_skill = mock_eval
        policy._evaluator.evaluate_all_skills = MagicMock(return_value={
            "good": mock_eval("good"),
            "bad": mock_eval("bad"),
        })

        results = policy.analyze_all()
        assert len(results) == 1
        assert results[0].skill_id == "bad"
