"""Tests for the unified vibe install command."""

from typing import Any
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestInstallCommand:
    """Test vibe install with unified intelligent installer."""

    @patch("vibesop.cli.commands.install.PackInstaller")
    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_trusted_pack_by_name(
        self, mock_loader_cls: Any, mock_installer_cls: Any
    ) -> None:
        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Installed gstack")
        mock_installer_cls.return_value = mock_installer

        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {}
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "gstack"])
        assert result.exit_code == 0
        assert "gstack installed successfully" in result.output
        mock_installer.install_pack.assert_called_once_with(
            "gstack", None, platforms=["claude-code"], upgrade=False, scope="global"
        )

    @patch("vibesop.cli.commands.install.PackInstaller")
    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    @patch("vibesop.installer.analyzer.RepoAnalyzer")
    def test_install_from_url(
        self, mock_analyzer_cls: Any, mock_loader_cls: Any, mock_installer_cls: Any
    ) -> None:
        mock_analyzer = MagicMock()
        mock_analyzer.infer_pack_name.return_value = "my-skills"
        mock_analyzer_cls.return_value = mock_analyzer

        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Installed my-skills")
        mock_installer_cls.return_value = mock_installer

        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {}
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "https://github.com/user/my-skills"])
        assert result.exit_code == 0
        assert "my-skills installed successfully" in result.output
        mock_installer.install_pack.assert_called_once_with(
            "my-skills",
            "https://github.com/user/my-skills",
            platforms=["claude-code"],
            upgrade=False,
            scope="global",
        )

    @patch("vibesop.cli.commands.install.PackInstaller")
    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_already_installed_skipped(
        self, mock_loader_cls: Any, mock_installer_cls: Any
    ) -> None:
        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Already there")
        mock_installer_cls.return_value = mock_installer

        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {"superpowers": {"installed": True}}
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "superpowers"])
        assert result.exit_code == 0
        assert "already installed" in result.output
        mock_installer.install_pack.assert_not_called()

    @patch("vibesop.cli.commands.install.PackInstaller")
    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_force_reinstall(self, mock_loader_cls: Any, mock_installer_cls: Any) -> None:
        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Reinstalled superpowers")
        mock_installer_cls.return_value = mock_installer

        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {"superpowers": {"installed": True}}
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "superpowers", "--force"])
        assert result.exit_code == 0
        mock_installer.install_pack.assert_called_once_with(
            "superpowers", None, platforms=["claude-code"], upgrade=False, scope="global"
        )

    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_list(self, mock_loader_cls: Any) -> None:
        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {
            "superpowers": {"installed": True},
            "omx": {"installed": False},
        }
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "--list"])
        assert result.exit_code == 0
        assert "superpowers" in result.output
        assert "omx" in result.output
        assert "Installed" in result.output

    @patch("vibesop.cli.commands.install.PackInstaller")
    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_auto(self, mock_loader_cls: Any, mock_installer_cls: Any) -> None:
        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Installed")
        mock_installer_cls.return_value = mock_installer

        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {
            "superpowers": {"installed": True},
            "gstack": {"installed": True},
            "omx": {"installed": False},
            "mattpocock": {"installed": True},
        }
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "--auto"])
        assert result.exit_code == 0
        mock_installer.install_pack.assert_called_once_with(
            "omx", None, platforms=["claude-code"], upgrade=False, scope="global"
        )

    @patch("vibesop.cli.commands.install.PackInstaller")
    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_auto_skips_installed(
        self, mock_loader_cls: Any, mock_installer_cls: Any
    ) -> None:
        mock_installer = MagicMock()
        mock_installer_cls.return_value = mock_installer

        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {
            "gstack": {"installed": True},
            "superpowers": {"installed": True},
            "omx": {"installed": True},
            "mattpocock": {"installed": True},
        }
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "--auto"])
        assert result.exit_code == 0
        assert "already installed, skipping" in result.output
        mock_installer.install_pack.assert_not_called()

    def test_install_no_args(self) -> None:
        result = runner.invoke(app, ["install"])
        assert result.exit_code == 1
        assert "No pack name or URL specified" in result.output

    @patch("vibesop.cli.commands.install.PackInstaller")
    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_failure(self, mock_loader_cls: Any, mock_installer_cls: Any) -> None:
        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (False, "Network error")
        mock_installer_cls.return_value = mock_installer

        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {}
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "gstack"])
        assert result.exit_code == 1
        assert "Failed to install" in result.output

    @patch("vibesop.cli.commands.install.PackInstaller")
    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_verify_no_skills(self, mock_loader_cls: Any, mock_installer_cls: Any) -> None:
        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Installed gstack")
        mock_installer_cls.return_value = mock_installer

        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {}
        mock_loader.external_paths = [MagicMock()]
        mock_loader.discover_from_pack.return_value = []
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "gstack"])
        assert result.exit_code == 0
        assert "gstack installed successfully" in result.output
        assert "No skills discovered" in result.output

    @patch("vibesop.cli.commands.install.PackInstaller")
    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_with_platform_flag(
        self, mock_loader_cls: Any, mock_installer_cls: Any
    ) -> None:
        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Installed gstack for claude-code")
        mock_installer_cls.return_value = mock_installer

        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {}
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "gstack", "--platform", "claude-code"])
        assert result.exit_code == 0
        assert "gstack installed successfully" in result.output
        assert "Platform: claude-code" in result.output
        mock_installer.install_pack.assert_called_once_with(
            "gstack", None, platforms=["claude-code"], upgrade=False, scope="global"
        )

    @patch("vibesop.cli.commands.install.PackInstaller")
    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_with_platform_flag_cursor(
        self, mock_loader_cls: Any, mock_installer_cls: Any
    ) -> None:
        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Installed gstack for cursor")
        mock_installer_cls.return_value = mock_installer

        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {}
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "gstack", "--platform", "cursor"])
        assert result.exit_code == 0
        mock_installer.install_pack.assert_called_once_with(
            "gstack", None, platforms=["cursor"], upgrade=False, scope="global"
        )

    def test_install_invalid_platform(self) -> None:
        result = runner.invoke(app, ["install", "gstack", "--platform", "vscode"])
        assert result.exit_code == 1
        assert "Unknown platform: vscode" in result.output

    @patch("vibesop.cli.commands.install.PackInstaller")
    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_auto_with_platform(
        self, mock_loader_cls: Any, mock_installer_cls: Any
    ) -> None:
        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Installed")
        mock_installer_cls.return_value = mock_installer

        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {
            "superpowers": {"installed": True},
            "gstack": {"installed": True},
            "omx": {"installed": False},
            "mattpocock": {"installed": True},
        }
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "--auto", "--platform", "opencode"])
        assert result.exit_code == 0
        mock_installer.install_pack.assert_called_once_with(
            "omx", None, platforms=["opencode"], upgrade=False, scope="global"
        )

    @patch("vibesop.cli.commands.install.PackInstaller")
    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_with_project_scope(
        self, mock_loader_cls: Any, mock_installer_cls: Any
    ) -> None:
        """--scope project threads the scope through and skips platform resolution."""
        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Installed gstack")
        mock_installer_cls.return_value = mock_installer

        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {}
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "gstack", "--scope", "project"])
        assert result.exit_code == 0
        assert "gstack installed successfully" in result.output
        # Project scope skips platform symlinks, so no platform messaging.
        assert "No platform preference found" not in result.output
        mock_installer.install_pack.assert_called_once_with(
            "gstack", None, platforms=None, upgrade=False, scope="project"
        )

    def test_install_invalid_scope(self) -> None:
        result = runner.invoke(app, ["install", "gstack", "--scope", "bogus"])
        assert result.exit_code == 1
        assert "--scope must be 'global' or 'project'" in result.output
