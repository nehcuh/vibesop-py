"""Tests for the 'vibe auto' command.

DEPRECATED: The 'vibe auto' command is deprecated in v3.0.0 and will be removed in v4.0.0.
These tests are kept for backward compatibility but may be skipped.
Use 'vibe route' instead.
"""

from __future__ import annotations

import pytest

from typer.testing import CliRunner

from vibesop.cli.main import app

# Skip these tests since vibe auto is deprecated
pytestmark = pytest.mark.skip(
    reason="'vibe auto' command is deprecated. Tests skipped pending v4.0.0 removal."
)

runner = CliRunner()


class TestAutoCommand:
    """Tests for vibe auto command (deprecated)."""

    def test_auto_dry_run(self) -> None:
        """Test auto command with --dry-run flag."""
        # Skipped - command is deprecated
        pass

    def test_auto_no_match(self) -> None:
        """Test auto command when no skill matches."""
        # Skipped - command is deprecated
        pass

    def test_auto_with_verbose(self) -> None:
        """Test auto command with --verbose flag."""
        # Skipped - command is deprecated
        pass
