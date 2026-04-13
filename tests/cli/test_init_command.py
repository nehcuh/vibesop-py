"""Tests for vibe init command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from vibesop.cli.main import app
from vibesop.integrations import IntegrationStatus

runner = CliRunner()


class TestInitCommand:
    """Test suite for init command."""

    def test_init_invalid_platform(self) -> None:
        """Test init with invalid platform."""
        result = runner.invoke(app, ["init", "--platform", "invalid"])
        assert result.exit_code == 1
        assert "Invalid platform" in result.stdout

    @patch("vibesop.cli.commands.init.InitSupport")
    def test_init_verify_initialized(self, mock_support_cls) -> None:
        """Test init --verify when project is initialized."""
        mock_support = MagicMock()
        mock_support.verify_init.return_value = {
            "vibe_dir_exists": True,
            "config_exists": True,
            "skills_dir_exists": True,
            "initialized": True,
        }
        mock_support_cls.return_value = mock_support

        result = runner.invoke(app, ["init", "--verify"])
        assert result.exit_code == 0
        assert "Project is properly initialized" in result.stdout

    @patch("vibesop.cli.commands.init.InitSupport")
    def test_init_verify_not_initialized(self, mock_support_cls) -> None:
        """Test init --verify when project is not initialized."""
        mock_support = MagicMock()
        mock_support.verify_init.return_value = {
            "vibe_dir_exists": False,
            "config_exists": False,
            "skills_dir_exists": False,
            "initialized": False,
        }
        mock_support_cls.return_value = mock_support

        result = runner.invoke(app, ["init", "--verify"])
        assert result.exit_code == 1
        assert "Project is not fully initialized" in result.stdout

    def test_init_dry_run(self, monkeypatch, tmp_path) -> None:
        """Test init --dry-run."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init", "--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "Preview Mode" in result.stdout
        assert "config.yaml" in result.stdout

    def test_init_dry_run_existing_vibe(self, monkeypatch, tmp_path) -> None:
        """Test init --dry-run when .vibe already exists."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".vibe").mkdir()
        result = runner.invoke(app, ["init", "--dry-run"])
        assert result.exit_code == 0
        assert ".vibe directory already exists" in result.stdout

    @patch("vibesop.cli.commands.init.InitSupport")
    @patch("vibesop.cli.commands.init.IntegrationManager")
    def test_init_success(self, mock_mgr_cls, mock_support_cls, monkeypatch, tmp_path) -> None:
        """Test successful initialization."""
        monkeypatch.chdir(tmp_path)
        mock_support = MagicMock()
        mock_support.init_project.return_value = {
            "success": True,
            "warnings": [],
            "errors": [],
            "created_dirs": [str(tmp_path / ".vibe"), str(tmp_path / ".skills")],
            "created_files": [str(tmp_path / ".vibe" / "config.yaml")],
        }
        mock_support_cls.return_value = mock_support

        mock_mgr = MagicMock()
        integration = MagicMock()
        integration.name = "gstack"
        integration.status = IntegrationStatus.INSTALLED
        integration.description = "Virtual team"
        mock_mgr.list_integrations.return_value = [integration]
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(app, ["init", "--platform", "opencode"])
        assert result.exit_code == 0
        assert "Initialization complete" in result.stdout
        assert "Directories created" in result.stdout
        assert "Files created" in result.stdout

    @patch("vibesop.cli.commands.init.InitSupport")
    def test_init_with_errors(self, mock_support_cls, monkeypatch, tmp_path) -> None:
        """Test initialization with errors."""
        monkeypatch.chdir(tmp_path)
        mock_support = MagicMock()
        mock_support.init_project.return_value = {
            "success": False,
            "errors": ["Permission denied"],
            "warnings": [],
        }
        mock_support_cls.return_value = mock_support

        result = runner.invoke(app, ["init"])
        assert result.exit_code == 1
        assert "Permission denied" in result.stdout

    @patch("vibesop.cli.commands.init.InitSupport")
    @patch("vibesop.cli.commands.init.IntegrationManager")
    def test_init_with_warnings(self, mock_mgr_cls, mock_support_cls, monkeypatch, tmp_path) -> None:
        """Test initialization with warnings but success."""
        monkeypatch.chdir(tmp_path)
        mock_support = MagicMock()
        mock_support.init_project.return_value = {
            "success": True,
            "warnings": ["Directory already exists"],
            "errors": [],
        }
        mock_support_cls.return_value = mock_support

        mock_mgr = MagicMock()
        mock_mgr.list_integrations.return_value = []
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Directory already exists" in result.stdout

    @patch("vibesop.cli.commands.init.InitSupport")
    @patch("vibesop.cli.commands.init.IntegrationManager")
    def test_init_success_no_created_items(self, mock_mgr_cls, mock_support_cls, monkeypatch, tmp_path) -> None:
        """Test successful initialization with no created dirs/files."""
        monkeypatch.chdir(tmp_path)
        mock_support = MagicMock()
        mock_support.init_project.return_value = {
            "success": True,
            "warnings": [],
            "errors": [],
        }
        mock_support_cls.return_value = mock_support

        mock_mgr = MagicMock()
        mock_mgr.list_integrations.return_value = []
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Initialization complete" in result.stdout
