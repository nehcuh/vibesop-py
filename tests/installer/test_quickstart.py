"""Tests for QuickstartRunner class."""

from __future__ import annotations

from vibesop.installer.quickstart_runner import QuickstartRunner


class TestQuickstartRunner:
    """Tests for the quickstart wizard."""

    def test_create_runner(self) -> None:
        """Test creating a QuickstartRunner."""
        runner = QuickstartRunner()
        assert runner is not None
        assert "claude-code" in runner._supported_platforms
        assert "opencode" in runner._supported_platforms

    def test_supported_platforms(self) -> None:
        """Test that supported platforms are defined."""
        runner = QuickstartRunner()
        assert len(runner._supported_platforms) >= 2
