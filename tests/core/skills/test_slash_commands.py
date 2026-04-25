"""Tests for slash command system."""

from vibesop.core.skills.slash_commands import SlashCommandHandler, SlashCommandRegistry


class TestSlashCommandRegistry:
    """Test SlashCommandRegistry functionality."""

    def test_parse_valid_command(self) -> None:
        """Parse a valid slash command."""
        registry = SlashCommandRegistry()
        cmd, args = registry.parse('/vibe-route "帮我review代码" --explain')

        assert cmd == "/vibe-route"
        assert "帮我review代码" in args
        assert "--explain" in args

    def test_parse_non_command(self) -> None:
        """Non-slash commands return None."""
        registry = SlashCommandRegistry()
        cmd, args = registry.parse("帮我review代码")

        assert cmd is None
        assert args == []

    def test_parse_empty_input(self) -> None:
        """Empty input returns None."""
        registry = SlashCommandRegistry()
        cmd, args = registry.parse("")

        assert cmd is None
        assert args == []


class TestSlashCommandHandler:
    """Test SlashCommandHandler execution."""

    def test_help_command(self) -> None:
        """/vibe-help returns list of all commands."""
        handler = SlashCommandHandler()
        success, msg = handler.execute("/vibe-help")

        assert success is True
        assert "/vibe-route" in msg
        assert "/vibe-install" in msg
        assert "/vibe-analyze" in msg

    def test_unknown_command(self) -> None:
        """Unknown command returns error with available commands."""
        handler = SlashCommandHandler()
        success, msg = handler.execute("/vibe-unknown")

        assert success is False
        assert "Unknown command" in msg
        assert "/vibe-route" in msg

    def test_list_command_empty(self) -> None:
        """/vibe-list with no skills installed."""
        handler = SlashCommandHandler()
        success, _msg = handler.execute("/vibe-list")

        # May succeed but show no skills, or show installed skills
        assert success is True

    def test_non_slash_input(self) -> None:
        """Non-slash input is rejected."""
        handler = SlashCommandHandler()
        success, msg = handler.execute("帮我review代码")

        assert success is False
        assert "Not a valid" in msg

    def test_route_without_query(self) -> None:
        """/vibe-route without query shows usage."""
        handler = SlashCommandHandler()
        success, msg = handler.execute("/vibe-route")

        assert success is False
        assert "Usage" in msg

    def test_orchestrate_without_query(self) -> None:
        """/vibe-orchestrate without query shows usage."""
        handler = SlashCommandHandler()
        success, msg = handler.execute("/vibe-orchestrate")

        assert success is False
        assert "Usage" in msg

    def test_command_with_quoted_args(self) -> None:
        """Commands with quoted arguments parse correctly."""
        handler = SlashCommandHandler()

        # Test that parsing doesn't crash on quoted args
        success, msg = handler.execute('/vibe-route "complex query with spaces"')
        # Should attempt routing (may succeed or fail depending on router state)
        assert isinstance(success, bool)
        assert isinstance(msg, str)

    def test_all_commands_registered(self) -> None:
        """All expected commands are registered."""
        handler = SlashCommandHandler()
        registry = handler._registry

        expected_commands = [
            "/vibe-route",
            "/vibe-install",
            "/vibe-analyze",
            "/vibe-evaluate",
            "/vibe-orchestrate",
            "/vibe-list",
            "/vibe-help",
        ]

        registered = [cmd.name for cmd in registry.list_commands()]
        for cmd in expected_commands:
            assert cmd in registered, f"Command {cmd} not registered"
