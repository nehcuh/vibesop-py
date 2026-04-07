"""Tests for vibe checkpoint command.

Note: The checkpoint command is deprecated and moved to legacy.
Tests require VIBESOP_ENABLE_LEGACY=1 to run.
"""

import os
from typer.testing import CliRunner

from vibesop.cli.main import app

# Enable legacy commands for testing
os.environ["VIBESOP_ENABLE_LEGACY"] = "1"

runner = CliRunner()


class TestCheckpointCommand:
    """Test suite for checkpoint command."""

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

    def test_checkpoint_restore_no_id(self) -> None:
        """Test checkpoint restore without id."""
        result = runner.invoke(app, ["checkpoint", "restore"])
        assert result.exit_code == 1


class TestMemoryCommand:
    """Test suite for memory command."""

    def test_memory_help(self) -> None:
        """Test memory help output."""
        result = runner.invoke(app, ["memory", "--help"])
        assert result.exit_code == 0
        assert "Manage conversation memory" in result.stdout

    def test_memory_list(self) -> None:
        """Test memory list action."""
        result = runner.invoke(app, ["memory", "list"])
        assert result.exit_code == 0

    def test_memory_stats(self) -> None:
        """Test memory stats action."""
        result = runner.invoke(app, ["memory", "stats"])
        assert result.exit_code == 0


class TestInstinctCommand:
    """Test suite for instinct command."""

    def test_instinct_help(self) -> None:
        """Test instinct help output."""
        result = runner.invoke(app, ["instinct", "--help"])
        assert result.exit_code == 0
        assert "instinct" in result.stdout.lower()

    def test_instinct_stats(self) -> None:
        """Test instinct stats action."""
        result = runner.invoke(app, ["instinct", "stats"])
        assert result.exit_code == 0

    def test_instinct_learn_no_context(self) -> None:
        """Test instinct learn without context."""
        result = runner.invoke(app, ["instinct", "learn"])
        assert result.exit_code == 2  # Typer returns 2 for missing arguments
