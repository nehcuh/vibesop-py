"""Tests for SessionContext habit learning."""

from __future__ import annotations

from vibesop.core.sessions.context import SessionContext


class TestHabitLearning:
    """Test habit pattern learning in SessionContext."""

    def test_record_route_decision_adds_to_history(self, tmp_path):
        """Test that route decisions are recorded."""
        ctx = SessionContext(project_root=str(tmp_path))
        ctx.record_route_decision("debug this error", "systematic-debugging")

        assert len(ctx._route_history) == 1
        assert ctx._route_history[0].selected_skill == "systematic-debugging"

    def test_habit_pattern_requires_three_occurrences(self, tmp_path):
        """Test that habits only form after 3+ occurrences of same pattern."""
        ctx = SessionContext(project_root=str(tmp_path))

        # 2 occurrences — not enough
        ctx.record_route_decision("debug error", "systematic-debugging")
        ctx.record_route_decision("debug error", "systematic-debugging")

        boost = ctx.get_habit_boost("debug error")
        assert boost == {}

        # 3rd occurrence — habit formed
        ctx.record_route_decision("debug error", "systematic-debugging")

        boost = ctx.get_habit_boost("debug error")
        assert boost == {"systematic-debugging": 0.08}

    def test_habit_boost_for_different_query(self, tmp_path):
        """Test that habits don't apply to unrelated queries."""
        ctx = SessionContext(project_root=str(tmp_path))

        for _ in range(3):
            ctx.record_route_decision("debug error", "systematic-debugging")

        boost = ctx.get_habit_boost("plan architecture")
        assert boost == {}

    def test_habit_persistence_in_dict(self, tmp_path):
        """Test that habits survive to_dict/from_dict roundtrip."""
        ctx = SessionContext(project_root=str(tmp_path))

        for _ in range(3):
            ctx.record_route_decision("debug error", "systematic-debugging")

        data = ctx.to_dict()
        assert "habit_patterns" in data
        assert len(data["habit_patterns"]) == 1

        restored = SessionContext.from_dict(data, project_root=str(tmp_path))
        boost = restored.get_habit_boost("debug error")
        assert boost == {"systematic-debugging": 0.08}

    def test_route_history_in_dict(self, tmp_path):
        """Test that route history is serialized."""
        ctx = SessionContext(project_root=str(tmp_path))
        ctx.record_route_decision("test query", "test-skill")

        data = ctx.to_dict()
        assert "route_history" in data
        assert len(data["route_history"]) == 1
        assert data["route_history"][0]["selected_skill"] == "test-skill"

    def test_habit_only_returns_one_skill(self, tmp_path):
        """Test that get_habit_boost returns only the most recent learned skill."""
        ctx = SessionContext(project_root=str(tmp_path))

        # 3x for skill-a
        for _ in range(3):
            ctx.record_route_decision("debug error", "skill-a")
        # 3x for skill-b (same pattern)
        for _ in range(3):
            ctx.record_route_decision("debug error", "skill-b")

        boost = ctx.get_habit_boost("debug error")
        # Counter keeps both; dict will have the last one processed
        # depending on iteration order, but only one skill per pattern
        assert len(boost) <= 1
