"""Tests for the unified vibe install command."""

import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestExplicitOmxCli:
    @pytest.mark.parametrize(
        "args",
        [
            ["omx", "--scope", "project", "--with-cli"],
            ["superpowers", "--with-cli"],
            ["https://github.com/unrelated-owner/omx", "--with-cli"],
            ["https://github.com/Yeachan-Heo/oh-my-codex/", "--with-cli"],
            ["--auto", "--with-cli"],
            ["--list", "--with-cli"],
            ["--with-cli"],
        ],
    )
    def test_rejected_flags_cannot_create_installer_or_run_npm(self, args: list[str]) -> None:
        with (
            patch("vibesop.cli.commands.install.PackInstaller") as installer,
            patch("vibesop.cli.commands.install.ExternalSkillLoader") as loader,
            patch("vibesop.cli.commands.install.ensure_omx_cli") as cli,
            patch("vibesop.cli.commands.install._resolve_platforms") as platforms,
        ):
            result = runner.invoke(app, ["install", *args])
        assert result.exit_code == 2
        assert "--with-cli" in result.output
        installer.assert_not_called()
        loader.assert_not_called()
        cli.assert_not_called()
        platforms.assert_not_called()

    @pytest.mark.parametrize("already_installed", [False, True])
    @pytest.mark.parametrize("opt_in", [False, True])
    def test_cli_install_is_explicit_and_covers_installed_packs(
        self, already_installed: bool, opt_in: bool
    ) -> None:
        from vibesop.installer.omx_cli import OmxCliResult

        with (
            patch("vibesop.cli.commands.install.PackInstaller") as installer,
            patch("vibesop.cli.commands.install.ExternalSkillLoader") as loader,
            patch("vibesop.cli.commands.install.ensure_omx_cli") as cli,
        ):
            installer.return_value.install_pack.return_value = (True, "Installed omx")
            loader.return_value.get_supported_packs.return_value = {
                "omx": {"installed": already_installed}
            }
            cli.return_value = OmxCliResult("failed", "omx CLI install failed [unclosed-tag]")
            args = ["install", "omx", "--skip-verify"]
            if opt_in:
                args.append("--with-cli")
            result = runner.invoke(app, args)
        assert result.exit_code == 0
        assert cli.call_count == int(opt_in)
        assert installer.return_value.install_pack.call_count == int(not already_installed)
        if opt_in:
            assert "omx CLI install failed [unclosed-tag]" in result.output

    def test_pack_failure_never_installs_cli(self) -> None:
        with (
            patch("vibesop.cli.commands.install.PackInstaller") as installer,
            patch("vibesop.cli.commands.install.ExternalSkillLoader") as loader,
            patch("vibesop.cli.commands.install.ensure_omx_cli") as cli,
        ):
            loader.return_value.get_supported_packs.return_value = {}
            installer.return_value.install_pack.return_value = (False, "Pack rejected")
            result = runner.invoke(app, ["install", "omx", "--with-cli"])
        assert result.exit_code == 1
        assert "Failed to install" in result.output
        cli.assert_not_called()

    def test_exact_trusted_url_installs_cli(self) -> None:
        from vibesop.constants import TRUSTED_PACKS
        from vibesop.installer.omx_cli import OmxCliResult

        with (
            patch("vibesop.cli.commands.install.PackInstaller") as installer,
            patch("vibesop.cli.commands.install.ExternalSkillLoader"),
            patch("vibesop.cli.commands.install.ensure_omx_cli") as cli,
        ):
            installer.return_value.install_pack.return_value = (True, "Installed OMX")
            cli.return_value = OmxCliResult("present", "omx CLI already on PATH")
            result = runner.invoke(
                app, ["install", TRUSTED_PACKS["omx"], "--with-cli", "--skip-verify"]
            )
        assert result.exit_code == 0
        cli.assert_called_once()
        assert installer.return_value.install_pack.call_args.args == (
            "oh-my-codex",
            TRUSTED_PACKS["omx"],
        )

    def test_real_helper_prefix_error_keeps_cli_skill_success(self) -> None:
        from vibesop.installer import omx_cli

        with (
            patch("vibesop.cli.commands.install.PackInstaller") as installer,
            patch("vibesop.cli.commands.install.ExternalSkillLoader") as loader,
            patch.object(omx_cli, "_WINDOWS", False),
            patch.object(omx_cli.shutil, "which", side_effect={"npm": "/bin/npm"}.get),
            patch.object(
                omx_cli.subprocess,
                "run",
                side_effect=[
                    subprocess.CompletedProcess([], 0, "installed", ""),
                    UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid"),
                ],
            ) as npm,
        ):
            loader.return_value.get_supported_packs.return_value = {}
            installer.return_value.install_pack.return_value = (True, "Installed omx")
            result = runner.invoke(app, ["install", "omx", "--with-cli", "--skip-verify"])
        assert result.exit_code == 0
        assert "omx installed successfully" in result.output
        assert "not on PATH" in result.output
        installer.return_value.install_pack.assert_called_once()
        assert npm.call_args_list[0].args[0] == [
            "/bin/npm",
            "install",
            "-g",
            "oh-my-codex",
            "--ignore-scripts",
        ]
        assert npm.call_args_list[1].args[0] == ["/bin/npm", "prefix", "-g"]

    @pytest.mark.parametrize("scope", ["global", "project"])
    def test_auto_install_remains_skills_only(self, scope: str) -> None:
        with (
            patch("vibesop.cli.commands.install.PackInstaller") as installer,
            patch("vibesop.cli.commands.install.ExternalSkillLoader") as loader,
            patch("vibesop.cli.commands.install.ensure_omx_cli") as cli,
        ):
            loader.return_value.get_supported_packs.return_value = {}
            installer.return_value.install_pack.return_value = (True, "Installed skills")
            result = runner.invoke(app, ["install", "--auto", "--scope", scope])
        assert result.exit_code == 0
        cli.assert_not_called()

    def test_help_discloses_global_writes_and_disabled_scripts(self) -> None:
        result = runner.invoke(app, ["install", "--help"])
        assert result.exit_code == 0
        assert "--with-cli" in result.output
        assert "globally" in result.output
        assert "lifecycle scripts disabled" in " ".join(result.output.split())


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
