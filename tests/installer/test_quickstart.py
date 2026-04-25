"""Tests for QuickstartRunner class."""

from __future__ import annotations

import builtins
from pathlib import Path
from unittest.mock import patch

from vibesop.installer.quickstart_runner import QuickstartConfig, QuickstartRunner


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

    def test_ask_yes_no_default_yes(self) -> None:
        """Test _ask_yes_no with default yes and empty input."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", return_value=""):
            assert runner._ask_yes_no("Test?", default=True) is True

    def test_ask_yes_no_default_no(self) -> None:
        """Test _ask_yes_no with default no and empty input."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", return_value=""):
            assert runner._ask_yes_no("Test?", default=False) is False

    def test_ask_yes_no_explicit_yes(self) -> None:
        """Test _ask_yes_no with explicit yes."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", side_effect=["y"]):
            assert runner._ask_yes_no("Test?", default=False) is True

    def test_ask_yes_no_explicit_no(self) -> None:
        """Test _ask_yes_no with explicit no."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", side_effect=["n"]):
            assert runner._ask_yes_no("Test?", default=True) is False

    def test_ask_yes_no_invalid_then_valid(self) -> None:
        """Test _ask_yes_no with invalid input then valid."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", side_effect=["maybe", "yes"]):
            assert runner._ask_yes_no("Test?", default=False) is True

    def test_ask_choice_default(self) -> None:
        """Test _ask_choice with empty input returns default."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", return_value=""):
            assert runner._ask_choice("Pick", ["1", "2"], default="1") == "1"

    def test_ask_choice_explicit(self) -> None:
        """Test _ask_choice with explicit choice."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", return_value="2"):
            assert runner._ask_choice("Pick", ["1", "2"], default="1") == "2"

    def test_ask_choice_invalid_then_valid(self) -> None:
        """Test _ask_choice with invalid input then valid."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", side_effect=["3", "1"]):
            assert runner._ask_choice("Pick", ["1", "2"], default="2") == "1"

    def test_ask_platform(self) -> None:
        """Test _ask_platform returns selected platform."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", return_value="1"):
            assert runner._ask_platform() == "claude-code"

    def test_ask_install_type_global(self) -> None:
        """Test _ask_install_type returns global config."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", return_value="1"):
            config = runner._ask_install_type(Path("/tmp/project"))
            assert config.global_install is True
            assert config.install_integrations is True

    def test_ask_install_type_project(self) -> None:
        """Test _ask_install_type returns project config."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", return_value="2"):
            config = runner._ask_install_type(Path("/tmp/project"))
            assert config.global_install is False
            assert config.install_integrations is False

    def test_show_summary_does_not_raise(self) -> None:
        """Test _show_summary does not raise."""
        runner = QuickstartRunner()
        config = QuickstartConfig(
            platform="claude-code",
            install_integrations=True,
            install_hooks=False,
            project_path=Path("/tmp"),
            global_install=True,
        )
        runner._show_summary(config)  # Should not raise

    def test_show_next_steps_global(self) -> None:
        """Test _show_next_steps for global install."""
        runner = QuickstartRunner()
        config = QuickstartConfig(
            platform="claude-code",
            install_integrations=True,
            install_hooks=True,
            project_path=Path.home(),
            global_install=True,
        )
        runner._show_next_steps(config)  # Should not raise

    def test_show_next_steps_project(self) -> None:
        """Test _show_next_steps for project install."""
        runner = QuickstartRunner()
        config = QuickstartConfig(
            platform="opencode",
            install_integrations=False,
            install_hooks=False,
            project_path=Path("/tmp"),
            global_install=False,
        )
        runner._show_next_steps(config)  # Should not raise

    def test_run_cancelled_at_confirm(self, tmp_path: Path) -> None:
        """Test run cancelled by user at confirmation step."""
        runner = QuickstartRunner()
        # For global install, install_integrations/hooks are already set to True,
        # so only install type, platform, and confirm inputs are needed.
        inputs = ["1", "1", "n"]
        with patch.object(builtins, "input", side_effect=inputs):
            result = runner.run(project_path=tmp_path)
        assert result["success"] is False
        assert result["config"] is not None

    def test_execute_installation_global(self, tmp_path: Path) -> None:
        """Test _execute_installation for global install."""
        runner = QuickstartRunner()
        config = QuickstartConfig(
            platform="opencode",
            install_integrations=False,
            install_hooks=False,
            project_path=tmp_path,
            global_install=True,
        )
        success = runner._execute_installation(config)
        assert success is True

    def test_execute_installation_project(self, tmp_path: Path) -> None:
        """Test _execute_installation for project install."""
        runner = QuickstartRunner()
        config = QuickstartConfig(
            platform="opencode",
            install_integrations=False,
            install_hooks=False,
            project_path=tmp_path,
            global_install=False,
        )
        success = runner._execute_installation(config)
        assert success is True
