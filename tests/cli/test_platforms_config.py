"""Tests for cross-platform skill install scoping (vibe config platforms + install resolver).

Covers:
- ``_validate_platform`` accepts comma-separated values and the ``all`` sentinel
- ``_resolve_platforms`` honors CLI flag > project config > user config > default
- ``vibe config platforms`` CLI command: show / set user / set project / clear
"""

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from vibesop.cli.commands._utils import resolve_platforms as _resolve_platforms, validate_platform as _validate_platform
from vibesop.cli.main import app

runner = CliRunner()


class TestValidatePlatform:
    def test_none_returns_none(self):
        assert _validate_platform(None) is None

    def test_single_platform(self):
        assert _validate_platform("claude-code") == ["claude-code"]

    def test_comma_separated(self):
        assert _validate_platform("claude-code,kimi-cli") == ["claude-code", "kimi-cli"]

    def test_comma_separated_with_spaces(self):
        assert _validate_platform("claude-code, kimi-cli , opencode") == [
            "claude-code",
            "kimi-cli",
            "opencode",
        ]

    def test_all_sentinel_returns_none(self):
        assert _validate_platform("all") is None

    def test_unknown_platform_exits(self):
        with pytest.raises(typer.Exit):
            _validate_platform("not-a-real-platform")

    def test_unknown_in_comma_list_exits(self):
        with pytest.raises(typer.Exit):
            _validate_platform("claude-code,bogus")


class TestResolvePlatformsWithoutConfig:
    """Resolver behavior when no config file exists (isolated $HOME)."""

    def test_cli_flag_wins(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        project_root = tmp_path / "project"
        project_root.mkdir()
        platforms, source = _resolve_platforms("kimi-cli", project_root)
        assert platforms == ["kimi-cli"]
        assert source == "cli-flag"

    def test_cli_flag_all_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        project_root = tmp_path / "project"
        project_root.mkdir()
        platforms, source = _resolve_platforms("all", project_root)
        assert platforms is None
        assert source == "cli-flag"

    def test_no_flag_no_config_defaults_to_claude_code(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        project_root = tmp_path / "project"
        project_root.mkdir()
        platforms, source = _resolve_platforms(None, project_root)
        assert platforms == ["claude-code"]
        assert source == "default"


class TestResolvePlatformsWithConfig:
    def test_user_config_is_used(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        user_config = tmp_path / ".vibe" / "config.yaml"
        user_config.parent.mkdir(parents=True)
        user_config.write_text(
            "platforms:\n  install_targets:\n    - claude-code\n    - kimi-cli\n",
            encoding="utf-8",
        )
        # Project root distinct from $HOME so only user config applies
        project_root = tmp_path / "project"
        project_root.mkdir()
        platforms, source = _resolve_platforms(None, project_root)
        assert platforms == ["claude-code", "kimi-cli"]
        assert source == "user-config"

    def test_project_config_overrides_user_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        user_config = tmp_path / ".vibe" / "config.yaml"
        user_config.parent.mkdir(parents=True)
        user_config.write_text(
            "platforms:\n  install_targets:\n    - claude-code\n    - kimi-cli\n",
            encoding="utf-8",
        )
        project_root = tmp_path / "project"
        project_root.mkdir()
        proj_config = project_root / ".vibe" / "config.yaml"
        proj_config.parent.mkdir(parents=True)
        proj_config.write_text("platforms:\n  install_targets:\n    - opencode\n", encoding="utf-8")
        platforms, source = _resolve_platforms(None, project_root)
        assert platforms == ["opencode"]
        assert source == "project-config"

    def test_cli_flag_overrides_all_configs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        user_config = tmp_path / ".vibe" / "config.yaml"
        user_config.parent.mkdir(parents=True)
        user_config.write_text("platforms:\n  install_targets:\n    - kimi-cli\n", encoding="utf-8")
        project_root = tmp_path / "project"
        project_root.mkdir()
        platforms, source = _resolve_platforms("cursor", project_root)
        assert platforms == ["cursor"]
        assert source == "cli-flag"

    def test_invalid_platform_in_config_is_filtered(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        user_config = tmp_path / ".vibe" / "config.yaml"
        user_config.parent.mkdir(parents=True)
        user_config.write_text(
            "platforms:\n  install_targets:\n    - claude-code\n    - bogus-platform\n",
            encoding="utf-8",
        )
        project_root = tmp_path / "project"
        project_root.mkdir()
        platforms, source = _resolve_platforms(None, project_root)
        assert platforms == ["claude-code"]
        assert source == "user-config"


class TestConfigPlatformsCommand:
    """End-to-end CLI tests for ``vibe config platforms``."""

    def test_show_with_no_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        project_root = tmp_path / "project"
        project_root.mkdir()
        monkeypatch.chdir(project_root)
        result = runner.invoke(app, ["config", "platforms"])
        assert result.exit_code == 0
        assert "claude-code" in result.stdout
        assert "default" in result.stdout

    def test_set_user_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        project_root = tmp_path / "project"
        project_root.mkdir()
        monkeypatch.chdir(project_root)
        result = runner.invoke(app, ["config", "platforms", "claude-code", "kimi-cli"])
        assert result.exit_code == 0
        assert "User platforms set" in result.stdout
        written = (tmp_path / ".vibe" / "config.yaml").read_text(encoding="utf-8")
        assert "claude-code" in written
        assert "kimi-cli" in written

    def test_set_project_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        project_root = tmp_path / "project"
        project_root.mkdir()
        monkeypatch.chdir(project_root)
        result = runner.invoke(app, ["config", "platforms", "claude-code", "--project"])
        assert result.exit_code == 0
        assert "Project platforms set" in result.stdout
        written = (project_root / ".vibe" / "config.yaml").read_text(encoding="utf-8")
        assert "claude-code" in written

    def test_set_with_comma_value(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        project_root = tmp_path / "project"
        project_root.mkdir()
        monkeypatch.chdir(project_root)
        result = runner.invoke(app, ["config", "platforms", "claude-code,kimi-cli"])
        assert result.exit_code == 0
        written = (tmp_path / ".vibe" / "config.yaml").read_text(encoding="utf-8")
        assert "claude-code" in written
        assert "kimi-cli" in written

    def test_unknown_platform_exits(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        project_root = tmp_path / "project"
        project_root.mkdir()
        monkeypatch.chdir(project_root)
        result = runner.invoke(app, ["config", "platforms", "bogus"])
        assert result.exit_code != 0
        assert "Unknown platform" in result.stdout

    def test_clear_user_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        project_root = tmp_path / "project"
        project_root.mkdir()
        monkeypatch.chdir(project_root)
        cfg = tmp_path / ".vibe" / "config.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("platforms:\n  install_targets:\n    - kimi-cli\n", encoding="utf-8")
        result = runner.invoke(app, ["config", "platforms", "--clear"])
        assert result.exit_code == 0
        assert "Cleared" in result.stdout
        assert "install_targets" not in cfg.read_text(encoding="utf-8")

    def test_clear_when_no_config_is_noop(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        project_root = tmp_path / "project"
        project_root.mkdir()
        monkeypatch.chdir(project_root)
        result = runner.invoke(app, ["config", "platforms", "--clear"])
        assert result.exit_code == 0
        assert "nothing to clear" in result.stdout

    def test_show_reads_back_what_was_set(self, tmp_path, monkeypatch):
        # Use distinct home and project roots so the resolver reports the
        # user-config source rather than project-config.
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        project_root = tmp_path / "project"
        project_root.mkdir()
        monkeypatch.chdir(project_root)
        runner.invoke(app, ["config", "platforms", "claude-code", "kimi-cli"])
        result = runner.invoke(app, ["config", "platforms"])
        assert result.exit_code == 0
        assert "claude-code" in result.stdout
        assert "kimi-cli" in result.stdout
        assert "user-config" in result.stdout
