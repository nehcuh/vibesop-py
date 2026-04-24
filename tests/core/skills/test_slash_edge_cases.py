"""Tests for slash command edge cases and error handling."""

import pytest

from vibesop.core.skills.slash_commands import SlashCommandHandler


class TestSlashCommandEdgeCases:
    """Test edge cases and error handling."""

    def test_unclosed_quotes(self) -> None:
        """Handle unclosed quotes gracefully."""
        handler = SlashCommandHandler()
        # shlex would fail, but fallback handles it
        success, msg = handler.execute('/vibe-route "unclosed quote')
        # Should not crash, may succeed or fail gracefully
        assert isinstance(success, bool)
        assert isinstance(msg, str)

    def test_empty_quoted_string(self) -> None:
        """Handle empty quoted string."""
        handler = SlashCommandHandler()
        success, msg = handler.execute('/vibe-route ""')
        assert isinstance(success, bool)

    def test_special_characters_in_query(self) -> None:
        """Handle special characters in query."""
        handler = SlashCommandHandler()
        success, msg = handler.execute('/vibe-route "test & code | pipe"')
        assert isinstance(success, bool)

    def test_unicode_in_command(self) -> None:
        """Handle unicode characters."""
        handler = SlashCommandHandler()
        success, msg = handler.execute('/vibe-route "中文查询"')
        assert isinstance(success, bool)

    def test_multiple_flags(self) -> None:
        """Handle multiple flags in various orders."""
        handler = SlashCommandHandler()
        success, msg = handler.execute(
            '/vibe-route "query" --explain --strategy parallel'
        )
        assert isinstance(success, bool)

    def test_flag_before_query(self) -> None:
        """Handle flags appearing before query text."""
        handler = SlashCommandHandler()
        success, msg = handler.execute(
            '/vibe-route --explain "query after flag"'
        )
        assert isinstance(success, bool)

    def test_install_invalid_pack_name(self) -> None:
        """Handle invalid pack name characters."""
        handler = SlashCommandHandler()
        success, msg = handler.execute('/vibe-install "invalid/name"')
        # Should fail gracefully, not crash
        assert isinstance(success, bool)

    def test_evaluate_invalid_skill_id(self) -> None:
        """Handle invalid skill ID format."""
        handler = SlashCommandHandler()
        success, msg = handler.execute('/vibe-evaluate --skill "not-a-valid-id"')
        assert isinstance(success, bool)

    def test_orchestrate_empty_strategy(self) -> None:
        """Handle --strategy with no value."""
        handler = SlashCommandHandler()
        success, msg = handler.execute('/vibe-orchestrate "query" --strategy')
        assert isinstance(success, bool)

    def test_help_returns_all_commands(self) -> None:
        """Help command lists exactly 7 commands."""
        handler = SlashCommandHandler()
        success, msg = handler.execute("/vibe-help")

        assert success is True
        # Count command names in help text
        commands_found = [line for line in msg.split('\n') if line.strip().startswith('/vibe-')]
        assert len(commands_found) == 7

    def test_whitespace_only_input(self) -> None:
        """Handle whitespace-only input."""
        handler = SlashCommandHandler()
        success, msg = handler.execute("   ")
        assert success is False

    def test_case_sensitivity(self) -> None:
        """Commands are case-sensitive."""
        handler = SlashCommandHandler()
        success, msg = handler.execute("/VIBE-ROUTE test")
        # Should fail - commands are lowercase
        assert success is False


class TestSlashCommandErrorPaths:
    """Test error handling scenarios."""

    def test_route_empty_query(self) -> None:
        """Route command with empty query shows usage."""
        handler = SlashCommandHandler()
        success, msg = handler.execute('/vibe-route ""')
        assert success is False
        assert "query" in msg.lower()

    def test_install_no_args(self) -> None:
        """Install command without pack name shows usage."""
        handler = SlashCommandHandler()
        success, msg = handler.execute("/vibe-install")
        assert success is False
        assert "Usage" in msg

    def test_evaluate_no_skill_data(self) -> None:
        """Evaluate without data returns appropriate message."""
        handler = SlashCommandHandler()
        # Using a skill ID that likely has no data
        success, msg = handler.execute("/vibe-evaluate --skill builtin/nonexistent")
        # Should handle gracefully
        assert isinstance(success, bool)
        assert isinstance(msg, str)

    def test_analyze_empty_project(self) -> None:
        """Analyze on empty project directory."""
        handler = SlashCommandHandler()
        success, msg = handler.execute("/vibe-analyze")
        # Should analyze current directory (tests dir)
        assert isinstance(success, bool)

    def test_list_no_platforms(self) -> None:
        """List works without any platforms configured."""
        handler = SlashCommandHandler()
        success, msg = handler.execute("/vibe-list")
        assert isinstance(success, bool)

    def test_orchestrate_invalid_strategy(self) -> None:
        """Orchestrate with invalid strategy handled gracefully."""
        handler = SlashCommandHandler()
        success, msg = handler.execute('/vibe-orchestrate "test" --strategy invalid')
        assert isinstance(success, bool)
        assert isinstance(msg, str)
