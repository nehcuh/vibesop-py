"""Tests for vibe inspect command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestInspectCommand:
    """Test suite for inspect command."""

    @patch("vibesop.cli.commands.inspect.VibeSOPInstaller")
    @patch("vibesop.cli.commands.inspect.ConfigManager")
    @patch("vibesop.cli.commands.inspect.InitSupport")
    def test_inspect_full(self, mock_init_cls, mock_config_cls, mock_installer_cls, monkeypatch, tmp_path) -> None:
        """Test full inspect output."""
        monkeypatch.chdir(tmp_path)
        mock_init = MagicMock()
        mock_init.verify_init.return_value = {
            "vibe_dir_exists": True,
            "config_exists": True,
            "skills_dir_exists": True,
        }
        mock_init_cls.return_value = mock_init

        mock_config = MagicMock()
        mock_config.load_registry.return_value = {
            "platform": "claude-code",
            "routing": {"semantic_threshold": 0.5, "enable_fuzzy": True},
            "security": {"threat_level": "low"},
        }
        mock_config.get_all_skills.return_value = [
            {"id": "debug", "name": "Debug"},
        ]
        mock_config_cls.return_value = mock_config

        mock_installer = MagicMock()
        mock_installer.list_platforms.return_value = [{"name": "claude-code"}]
        mock_installer.verify.return_value = {"installed": True}
        mock_installer_cls.return_value = mock_installer

        result = runner.invoke(app, ["inspect"])
        assert result.exit_code == 0
        assert "VibeSOP Configuration Inspector" in result.stdout
        assert "claude-code" in result.stdout

    @patch("vibesop.cli.commands.inspect.ConfigManager")
    @patch("vibesop.cli.commands.inspect.InitSupport")
    def test_inspect_skills_only(self, mock_init_cls, mock_config_cls, monkeypatch, tmp_path) -> None:
        """Test inspect --skills."""
        monkeypatch.chdir(tmp_path)
        mock_config = MagicMock()
        mock_config.get_all_skills.return_value = [
            {"id": "debug", "name": "Debug"},
        ]
        mock_config_cls.return_value = mock_config

        result = runner.invoke(app, ["inspect", "--skills"])
        assert result.exit_code == 0
        assert "Total:" in result.stdout

    @patch("vibesop.cli.commands.inspect.ConfigManager")
    @patch("vibesop.cli.commands.inspect.InitSupport")
    def test_inspect_config_only(self, mock_init_cls, mock_config_cls, monkeypatch, tmp_path) -> None:
        """Test inspect --config."""
        monkeypatch.chdir(tmp_path)
        mock_config = MagicMock()
        mock_config.load_registry.return_value = {"platform": "opencode"}
        mock_config_cls.return_value = mock_config

        result = runner.invoke(app, ["inspect", "--config"])
        assert result.exit_code == 0
        assert "opencode" in result.stdout

    @patch("vibesop.cli.commands.inspect.ConfigManager")
    @patch("vibesop.cli.commands.inspect.InitSupport")
    def test_inspect_verbose(self, mock_init_cls, mock_config_cls, monkeypatch, tmp_path) -> None:
        """Test inspect --verbose."""
        monkeypatch.chdir(tmp_path)
        mock_config = MagicMock()
        mock_config.load_registry.return_value = {
            "platform": "claude-code",
            "routing": {"semantic_threshold": 0.5, "enable_fuzzy": True},
            "security": {"threat_level": "low"},
        }
        mock_config.get_all_skills.return_value = [
            {"id": f"skill-{i}", "name": f"Skill {i}"} for i in range(12)
        ]
        mock_config_cls.return_value = mock_config

        result = runner.invoke(app, ["inspect", "--verbose"])
        assert result.exit_code == 0
        assert "Semantic threshold" in result.stdout
        assert "and 2 more" in result.stdout

    @patch("vibesop.cli.commands.inspect.ConfigManager")
    @patch("vibesop.cli.commands.inspect.InitSupport")
    def test_inspect_config_error(self, mock_init_cls, mock_config_cls, monkeypatch, tmp_path) -> None:
        """Test inspect when config loading fails."""
        monkeypatch.chdir(tmp_path)
        mock_config = MagicMock()
        mock_config.load_registry.side_effect = RuntimeError("Config corrupted")
        mock_config_cls.return_value = mock_config

        result = runner.invoke(app, ["inspect", "--config"])
        assert result.exit_code == 0
        assert "Error loading config" in result.stdout

    @patch("vibesop.cli.commands.inspect.ConfigManager")
    @patch("vibesop.cli.commands.inspect.InitSupport")
    def test_inspect_skills_error(self, mock_init_cls, mock_config_cls, monkeypatch, tmp_path) -> None:
        """Test inspect when skills loading fails."""
        monkeypatch.chdir(tmp_path)
        mock_config = MagicMock()
        mock_config.get_all_skills.side_effect = RuntimeError("Skills corrupted")
        mock_config_cls.return_value = mock_config

        result = runner.invoke(app, ["inspect", "--skills"])
        assert result.exit_code == 0
        assert "Error loading skills" in result.stdout

    @patch("vibesop.cli.commands.inspect.VibeSOPInstaller")
    @patch("vibesop.cli.commands.inspect.ConfigManager")
    @patch("vibesop.cli.commands.inspect.InitSupport")
    def test_inspect_installer_error(self, mock_init_cls, mock_config_cls, mock_installer_cls, monkeypatch, tmp_path) -> None:
        """Test inspect when installer check fails."""
        monkeypatch.chdir(tmp_path)
        mock_init = MagicMock()
        mock_init.verify_init.return_value = {}
        mock_init_cls.return_value = mock_init

        mock_config = MagicMock()
        mock_config.load_registry.return_value = {}
        mock_config.get_all_skills.return_value = []
        mock_config_cls.return_value = mock_config

        mock_installer = MagicMock()
        mock_installer.list_platforms.side_effect = RuntimeError("Installer broken")
        mock_installer_cls.return_value = mock_installer

        result = runner.invoke(app, ["inspect"])
        assert result.exit_code == 0
        assert "Error checking installation" in result.stdout
