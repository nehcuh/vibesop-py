"""Tests for session context tracking and intelligent re-routing."""

import time

import pytest

from vibesop.core.sessions import (
    ContextChange,
    RoutingSuggestion,
    SessionContext,
    ToolUseEvent,
)


class TestToolUseEvent:
    """Test ToolUseEvent data class."""

    def test_create_event(self):
        """Test creating a tool use event."""
        event = ToolUseEvent(
            tool_name="read", timestamp=time.time(), skill="systematic-debugging"
        )

        assert event.tool_name == "read"
        assert event.skill == "systematic-debugging"
        assert isinstance(event.timestamp, float)


class TestSessionContext:
    """Test SessionContext class."""

    def test_init(self):
        """Test SessionContext initialization."""
        ctx = SessionContext(project_root=".")

        assert ctx._current_skill is None
        assert ctx._tool_history == []
        assert isinstance(ctx._session_start_time, float)

    def test_record_tool_use(self):
        """Test recording tool usage."""
        ctx = SessionContext(project_root=".")

        ctx.record_tool_use("read", skill="systematic-debugging")
        ctx.record_tool_use("bash", skill="systematic-debugging")

        assert len(ctx._tool_history) == 2
        assert ctx._tool_history[0].tool_name == "read"
        assert ctx._tool_history[1].tool_name == "bash"

    def test_set_current_skill(self):
        """Test setting current skill."""
        ctx = SessionContext(project_root=".")

        ctx.set_current_skill("systematic-debugging")

        assert ctx._current_skill == "systematic-debugging"

    def test_history_window_limit(self):
        """Test that history is limited to window size."""
        ctx = SessionContext(project_root=".", tool_use_window=3)

        # Record more than window size
        for i in range(10):
            ctx.record_tool_use(f"tool_{i}", skill="test")

        # Should only keep recent tools
        assert len(ctx._tool_history) <= 6  # window * 2

    def test_check_reroute_needed_no_history(self):
        """Test re-routing check with no history."""
        ctx = SessionContext(project_root=".")
        ctx.set_current_skill("systematic-debugging")

        suggestion = ctx.check_reroute_needed("design new architecture")

        # Should return a suggestion, even with no history
        assert isinstance(suggestion, RoutingSuggestion)

    def test_check_reroute_same_skill(self):
        """Test re-routing check when same skill is recommended."""
        ctx = SessionContext(project_root=".")
        ctx.set_current_skill("systematic-debugging")

        # Message that should match systematic-debugging
        suggestion = ctx.check_reroute_needed("help me debug this error")

        # Should not re-route if same skill recommended
        if suggestion.should_reroute:
            assert suggestion.recommended_skill != "systematic-debugging"
        else:
            assert suggestion.current_skill == "systematic-debugging"

    def test_check_reroute_cooldown(self):
        """Test that re-routing checks respect cooldown period."""
        ctx = SessionContext(project_root=".", reroute_cooldown=10.0)
        ctx.set_current_skill("systematic-debugging")

        # First check
        suggestion1 = ctx.check_reroute_needed("test message")

        # Immediate second check should be blocked by cooldown
        suggestion2 = ctx.check_reroute_needed("test message")

        # Second check should be blocked if cooldown active
        assert not suggestion2.should_reroute
        assert "cooldown" in suggestion2.reason.lower()

    def test_get_session_summary(self):
        """Test getting session summary."""
        ctx = SessionContext(project_root=".")
        ctx.set_current_skill("systematic-debugging")
        ctx.record_tool_use("read", skill="systematic-debugging")
        ctx.record_tool_use("bash", skill="systematic-debugging")

        summary = ctx.get_session_summary()

        assert "duration_seconds" in summary
        assert summary["current_skill"] == "systematic-debugging"
        assert summary["tool_use_count"] == 2
        assert "tool_breakdown" in summary
        assert summary["tool_breakdown"]["read"] == 1
        assert summary["tool_breakdown"]["bash"] == 1


class TestContextChangeDetection:
    """Test context change detection logic."""

    def test_detect_context_change_no_tools(self):
        """Test context change with no tool history."""
        ctx = SessionContext(project_root=".")

        change = ctx._detect_context_change("design new architecture", [])

        # Should suggest checking with no history
        assert change in [ContextChange.MODERATE, ContextChange.NONE]

    def test_phase_transition_detection(self):
        """Test detection of phase transitions."""
        ctx = SessionContext(project_root=".")
        ctx.record_tool_use("edit", skill="systematic-debugging")
        ctx.record_tool_use("bash", skill="systematic-debugging")

        # Transition to planning
        change = ctx._detect_context_change(
            "now let's plan the architecture", ctx._get_recent_tools()
        )

        # Should detect moderate to significant change
        assert change in [ContextChange.MODERATE, ContextChange.SIGNIFICANT]

    def test_tool_pattern_analysis(self):
        """Test tool usage pattern analysis."""
        ctx = SessionContext(project_root=".")
        ctx.record_tool_use("read", skill="test")
        ctx.record_tool_use("read", skill="test")
        ctx.record_tool_use("edit", skill="test")

        patterns = ctx._analyze_tool_patterns(ctx._tool_history)

        assert patterns["read"] == 2
        assert patterns["edit"] == 1

    def test_phase_inference_from_tools(self):
        """Test inferring phase from tool usage."""
        ctx = SessionContext(project_root=".")
        ctx.record_tool_use("edit", skill="test")
        ctx.record_tool_use("edit", skill="test")
        ctx.record_tool_use("write", skill="test")

        phase = ctx._infer_phase_from_tools({"edit": 2, "write": 1})

        # Should infer implementation phase
        assert phase == "implementation"


class TestRoutingSuggestion:
    """Test RoutingSuggestion data class."""

    def test_create_suggestion(self):
        """Test creating a routing suggestion."""
        suggestion = RoutingSuggestion(
            should_reroute=True,
            recommended_skill="planning-with-files",
            confidence=0.85,
            reason="Phase transition detected",
            current_skill="systematic-debugging",
        )

        assert suggestion.should_reroute is True
        assert suggestion.recommended_skill == "planning-with-files"
        assert suggestion.confidence == 0.85
        assert suggestion.reason == "Phase transition detected"
        assert suggestion.current_skill == "systematic-debugging"

    def test_create_suggestion_minimal(self):
        """Test creating suggestion with minimal fields."""
        suggestion = RoutingSuggestion(should_reroute=False)

        assert suggestion.should_reroute is False
        assert suggestion.recommended_skill is None
        assert suggestion.confidence == 0.0
        assert suggestion.reason == ""
        assert suggestion.current_skill is None


class TestIntegrationScenarios:
    """Integration tests for common scenarios."""

    def test_debugging_to_planning_transition(self):
        """Test transition from debugging to planning."""
        ctx = SessionContext(project_root=".")
        ctx.set_current_skill("systematic-debugging")

        # Simulate debugging phase
        for _ in range(5):
            ctx.record_tool_use("bash", skill="systematic-debugging")
            ctx.record_tool_use("read", skill="systematic-debugging")

        # Now user wants to plan
        suggestion = ctx.check_reroute_needed(
            "now let's plan the refactoring approach"
        )

        # Should suggest re-routing to planning
        if suggestion.should_reroute:
            assert "planning" in suggestion.recommended_skill.lower()

    def test_review_to_brainstorm_transition(self):
        """Test transition from review to brainstorming."""
        ctx = SessionContext(project_root=".")
        ctx.set_current_skill("gstack/review")

        # Simulate review phase
        for _ in range(3):
            ctx.record_tool_use("read", skill="gstack/review")

        # Now user wants to brainstorm
        suggestion = ctx.check_reroute_needed("let's brainstorm some solutions")

        # Should suggest re-routing to brainstorming
        if suggestion.should_reroute:
            assert "brainstorm" in suggestion.recommended_skill.lower()

    def test_implementation_to_testing_transition(self):
        """Test transition from implementation to testing."""
        ctx = SessionContext(project_root=".")
        ctx.set_current_skill("planning-with-files")

        # Simulate implementation phase
        for _ in range(5):
            ctx.record_tool_use("edit", skill="planning-with-files")

        # Now user encounters errors
        suggestion = ctx.check_reroute_needed("the tests are failing")

        # Should suggest re-routing to debugging/testing
        if suggestion.should_reroute:
            assert any(
                keyword in suggestion.recommended_skill.lower()
                for keyword in ["debug", "test", "systematic-debugging"]
            )
