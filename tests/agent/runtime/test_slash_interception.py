"""Tests for IntentInterceptor slash command detection."""

import pytest

from vibesop.agent.runtime.intent_interceptor import (
    IntentInterceptor,
    InterceptionContext,
    InterceptionMode,
)


class TestIntentInterceptorSlashCommands:
    """Test slash command detection in IntentInterceptor."""

    def test_slash_command_detection(self) -> None:
        """Detect /vibe-* prefix and route to SLASH_COMMAND mode."""
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("/vibe-route 'review code'")

        assert decision.should_route is True
        assert decision.mode == InterceptionMode.SLASH_COMMAND
        assert "slash command" in decision.reason.lower()

    def test_slash_command_install(self) -> None:
        """Detect /vibe-install command."""
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("/vibe-install gstack")

        assert decision.should_route is True
        assert decision.mode == InterceptionMode.SLASH_COMMAND

    def test_slash_command_help(self) -> None:
        """Detect /vibe-help command."""
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("/vibe-help")

        assert decision.should_route is True
        assert decision.mode == InterceptionMode.SLASH_COMMAND

    def test_non_slash_command_routed_normally(self) -> None:
        """Non-slash commands go through normal routing."""
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("帮我review这段代码")

        assert decision.should_route is True
        assert decision.mode != InterceptionMode.SLASH_COMMAND

    def test_slash_command_priority_over_explicit_skill(self) -> None:
        """Slash commands take priority over explicit skill patterns.

        The pattern r"^/(\w+)" would match /vibe-route as explicit skill,
        but slash command check comes first.
        """
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("/vibe-route 'query'")

        # Should be SLASH_COMMAND, not SINGLE
        assert decision.mode == InterceptionMode.SLASH_COMMAND
        assert "vibe-route" in decision.reason

    def test_slash_command_preserves_full_query(self) -> None:
        """Full query including args is preserved in decision."""
        interceptor = IntentInterceptor()
        query = '/vibe-route "帮我review代码" --explain'
        decision = interceptor.should_intercept(query)

        assert decision.query == query

    def test_empty_slash_command(self) -> None:
        """Bare /vibe- without subcommand still detected."""
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("/vibe-")

        assert decision.should_route is True
        assert decision.mode == InterceptionMode.SLASH_COMMAND

    def test_slash_command_with_context(self) -> None:
        """Slash commands work with session context."""
        interceptor = IntentInterceptor()
        context = InterceptionContext(
            session_id="test-session",
            platform="claude-code",
        )
        decision = interceptor.should_intercept("/vibe-list", context=context)

        assert decision.should_route is True
        assert decision.mode == InterceptionMode.SLASH_COMMAND


class TestExtractQueryAndFlags:
    """Test the _extract_query_and_flags helper."""

    def test_basic_extraction(self) -> None:
        """Extract query and simple flags."""
        from vibesop.core.skills.slash_commands import _extract_query_and_flags

        query, flags = _extract_query_and_flags(
            ("--explain", "review", "code"),
        )
        assert query == "review code"
        assert flags == {"--explain": True}

    def test_flag_with_value(self) -> None:
        """Extract flag that takes a value."""
        from vibesop.core.skills.slash_commands import _extract_query_and_flags

        query, flags = _extract_query_and_flags(
            ("--strategy", "parallel", "review", "code"),
            {"--strategy"},
        )
        assert query == "review code"
        assert flags == {"--strategy": "parallel"}

    def test_mixed_flags(self) -> None:
        """Mix of boolean flags and value flags."""
        from vibesop.core.skills.slash_commands import _extract_query_and_flags

        query, flags = _extract_query_and_flags(
            ("--explain", "--strategy", "sequential", "analyze", "code"),
            {"--strategy"},
        )
        assert query == "analyze code"
        assert flags == {"--explain": True, "--strategy": "sequential"}

    def test_quoted_args(self) -> None:
        """Quoted arguments preserved in query."""
        from vibesop.core.skills.slash_commands import _extract_query_and_flags

        query, flags = _extract_query_and_flags(
            ('"complex query with spaces"', "--explain"),
        )
        assert query == '"complex query with spaces"'
        assert flags == {"--explain": True}

    def test_no_flags(self) -> None:
        """Arguments without flags."""
        from vibesop.core.skills.slash_commands import _extract_query_and_flags

        query, flags = _extract_query_and_flags(("review", "code"))
        assert query == "review code"
        assert flags == {}

    def test_only_flags(self) -> None:
        """Only flags, no query."""
        from vibesop.core.skills.slash_commands import _extract_query_and_flags

        query, flags = _extract_query_and_flags(("--explain",))
        assert query == ""
        assert flags == {"--explain": True}

    def test_flag_without_value_at_end(self) -> None:
        """Value flag at end with no value provided."""
        from vibesop.core.skills.slash_commands import _extract_query_and_flags

        query, flags = _extract_query_and_flags(
            ("review", "--strategy"),
            {"--strategy"},
        )
        # --strategy at end with no value is treated as boolean
        assert query == "review"
        assert "--strategy" in flags
