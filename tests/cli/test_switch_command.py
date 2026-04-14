"""Tests for vibe switch command."""

import sys
import types
from unittest.mock import MagicMock

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestSwitchCommand:
    """Test suite for switch command."""

    def test_switch_help(self) -> None:
        """Test switch help output."""
        result = runner.invoke(app, ["switch", "--help"])
        assert result.exit_code == 0
        assert "Switch platform configuration" in result.stdout

    def test_switch_invalid_platform(self) -> None:
        """Test switch with invalid platform."""
        result = runner.invoke(app, ["switch", "invalid-platform"])
        assert result.exit_code == 1
        assert "Invalid platform" in result.stdout

    def test_get_configured_platform_success(self, tmp_path, monkeypatch) -> None:
        """Test _get_configured_platform reads existing config."""
        from vibesop.cli.commands import switch as switch_mod

        monkeypatch.chdir(tmp_path)
        config_path = tmp_path / ".vibe" / "config.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("platform: opencode\n", encoding="utf-8")
        result = switch_mod._get_configured_platform()
        assert result == "opencode"

    def test_get_configured_platform_missing_file(self, tmp_path, monkeypatch) -> None:
        """Test _get_configured_platform returns None when file missing."""
        from vibesop.cli.commands import switch as switch_mod

        monkeypatch.chdir(tmp_path)
        result = switch_mod._get_configured_platform()
        assert result is None

    def test_get_configured_platform_read_error(self, tmp_path, monkeypatch) -> None:
        """Test _get_configured_platform handles read errors gracefully."""
        from vibesop.cli.commands import switch as switch_mod

        monkeypatch.chdir(tmp_path)
        config_path = tmp_path / ".vibe" / "config.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("platform: cursor\n", encoding="utf-8")

        def raise_error(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("ruamel.yaml.main.YAML.load", raise_error)
        result = switch_mod._get_configured_platform()
        assert result is None

    def test_switch_no_platform_and_no_config(self, monkeypatch) -> None:
        """Test switch without platform and no config file."""
        monkeypatch.setattr(
            "vibesop.cli.commands.switch._get_configured_platform",
            lambda: None,
        )
        result = runner.invoke(app, ["switch"])
        assert result.exit_code == 1
        assert "No platform specified" in result.stdout

    def test_switch_from_config(self, monkeypatch, tmp_path) -> None:
        """Test switch using configured platform."""
        monkeypatch.setattr(
            "vibesop.cli.commands.switch._get_configured_platform",
            lambda: "claude-code",
        )

        # Mock build
        mock_build = MagicMock()
        monkeypatch.setattr("vibesop.cli.commands.build.execute_build", mock_build)

        # Mock deploy module since it may not exist
        fake_deploy = types.ModuleType("vibesop.cli.commands.deploy")
        fake_deploy._execute_deploy = MagicMock()
        sys.modules["vibesop.cli.commands.deploy"] = fake_deploy

        # Create fake build output
        dist_dir = tmp_path / ".vibe" / "dist" / "claude-code"
        dist_dir.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["switch"])
        assert result.exit_code == 0
        assert "Switched to claude-code" in result.stdout
        mock_build.assert_called_once()
        fake_deploy._execute_deploy.assert_called_once()

    def test_switch_no_build(self, monkeypatch, tmp_path) -> None:
        """Test switch with --no-build."""
        # Mock deploy module
        fake_deploy = types.ModuleType("vibesop.cli.commands.deploy")
        fake_deploy._execute_deploy = MagicMock()
        sys.modules["vibesop.cli.commands.deploy"] = fake_deploy

        # Create fake build output
        dist_dir = tmp_path / ".vibe" / "dist" / "claude-code"
        dist_dir.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["switch", "claude-code", "--no-build"])
        assert result.exit_code == 0
        assert "Skipping build" in result.stdout
        fake_deploy._execute_deploy.assert_called_once()

    def test_switch_build_output_missing(self, monkeypatch, tmp_path) -> None:
        """Test switch when build output is missing."""
        mock_build = MagicMock()
        monkeypatch.setattr("vibesop.cli.commands.build.execute_build", mock_build)

        fake_deploy = types.ModuleType("vibesop.cli.commands.deploy")
        fake_deploy._execute_deploy = MagicMock()
        sys.modules["vibesop.cli.commands.deploy"] = fake_deploy

        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["switch", "claude-code"])
        assert result.exit_code == 1
        assert "Build output not found" in result.stdout
