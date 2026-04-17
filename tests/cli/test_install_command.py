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
        mock_installer.install_pack.assert_called_once_with("gstack", None)

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
            "my-skills", "https://github.com/user/my-skills"
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
        mock_loader.get_supported_packs.return_value = {
            "superpowers": {"installed": True}
        }
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "superpowers"])
        assert result.exit_code == 0
        assert "already installed" in result.output
        mock_installer.install_pack.assert_not_called()

    @patch("vibesop.cli.commands.install.PackInstaller")
    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_force_reinstall(
        self, mock_loader_cls: Any, mock_installer_cls: Any
    ) -> None:
        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Reinstalled superpowers")
        mock_installer_cls.return_value = mock_installer

        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {
            "superpowers": {"installed": True}
        }
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "superpowers", "--force"])
        assert result.exit_code == 0
        mock_installer.install_pack.assert_called_once_with("superpowers", None)

    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_list(self, mock_loader_cls: Any) -> None:
        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {
            "gstack": {"installed": True},
            "superpowers": {"installed": False},
        }
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "--list"])
        assert result.exit_code == 0
        assert "gstack" in result.output
        assert "superpowers" in result.output
        assert "Installed" in result.output

    @patch("vibesop.cli.commands.install.PackInstaller")
    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_auto(self, mock_loader_cls: Any, mock_installer_cls: Any) -> None:
        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Installed")
        mock_installer_cls.return_value = mock_installer

        mock_loader = MagicMock()
        # superpowers is installed, gstack is not -> only gstack should be installed
        mock_loader.get_supported_packs.return_value = {
            "superpowers": {"installed": True},
            "gstack": {"installed": False},
        }
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "--auto"])
        assert result.exit_code == 0
        mock_installer.install_pack.assert_called_once_with("gstack", None)

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
    def test_install_verify_no_skills(
        self, mock_loader_cls: Any, mock_installer_cls: Any
    ) -> None:
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
