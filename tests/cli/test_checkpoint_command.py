"""Tests for checkpoint command - DEPRECATED.

Note: The checkpoint command is deprecated and moved to legacy.
Tests require VIBESOP_ENABLE_LEGACY=1 to run.

Note: Memory and instinct commands were completely removed in v4.1.0.
These features are now internal to the routing engine.
"""

import os
from typer.testing import CliRunner

from vibesop.cli.main import app

# Enable legacy commands for testing
os.environ["VIBESOP_ENABLE_LEGACY"] = "1"

runner = CliRunner()


class TestCheckpointCommand:
    """Test suite for checkpoint command (legacy)."""

    def test_checkpoint_help(self) -> None:
        """Test checkpoint help output."""
        result = runner.invoke(app, ["checkpoint", "--help"])
        assert result.exit_code == 0
        assert "Manage work state checkpoints" in result.stdout

    def test_checkpoint_list(self) -> None:
        """Test checkpoint list action."""
        result = runner.invoke(app, ["checkpoint", "list"])
        assert result.exit_code == 0

    def test_checkpoint_save_no_name(self) -> None:
        """Test checkpoint save without name."""
        result = runner.invoke(app, ["checkpoint", "save"])
        assert result.exit_code == 1


class TestMemoryCommand:
    """Memory command tests - REMOVED in v4.1.0."""

    def test_memory_command_removed(self) -> None:
        """Test that memory command no longer exists."""
        result = runner.invoke(app, ["memory"])
        assert result.exit_code != 0


class TestInstinctCommand:
    """Instinct command tests - REMOVED in v4.1.0."""

    def test_instinct_command_removed(self) -> None:
        """Test that instinct command no longer exists."""
        result = runner.invoke(app, ["instinct"])
        assert result.exit_code != 0
