"""Tests for Phase 3 commands (quickstart, onboard, toolchain, scan, skill-craft, tools).

Note: The toolchain command is deprecated and moved to legacy.
Tests require VIBESOP_ENABLE_LEGACY=1 to run.
"""

import os

from typer.testing import CliRunner

from vibesop.cli.main import app

# Enable legacy commands for testing
os.environ["VIBESOP_ENABLE_LEGACY"] = "1"

runner = CliRunner()


class TestQuickstartCommand:
    """Test suite for quickstart command."""

    def test_quickstart_help(self) -> None:
        """Test quickstart help output."""
        result = runner.invoke(app, ["quickstart", "--help"])
        assert result.exit_code == 0
        assert "interactive setup" in result.stdout.lower()


class TestOnboardCommand:
    """Test suite for onboard command."""

    def test_onboard_help(self) -> None:
        """Test onboard help output."""
        result = runner.invoke(app, ["onboard", "--help"])
        assert result.exit_code == 0
        assert "onboarding" in result.stdout.lower()

    def test_onboard_skips(self) -> None:
        """Test onboard with skip options."""
        result = runner.invoke(
            app, ["onboard", "--skip-deploy", "--skip-hooks", "--skip-integrations"]
        )
        assert result.exit_code == 0


class TestToolchainCommand:
    """Test suite for toolchain command."""

    def test_toolchain_help(self) -> None:
        """Test toolchain help output."""
        result = runner.invoke(app, ["toolchain", "--help"])
        assert result.exit_code == 0
        assert "toolchain" in result.stdout.lower()

    def test_toolchain_list(self) -> None:
        """Test toolchain list action."""
        result = runner.invoke(app, ["toolchain", "list"])
        assert result.exit_code == 0

    def test_toolchain_status(self) -> None:
        """Test toolchain status action."""
        result = runner.invoke(app, ["toolchain", "status"])
        assert result.exit_code == 0

    def test_toolchain_verify_no_tool(self) -> None:
        """Test toolchain verify without tool."""
        result = runner.invoke(app, ["toolchain", "verify"])
        assert result.exit_code == 1


class TestScanCommand:
    """Test suite for scan command (now merged into analyze security)."""

    def test_scan_help(self) -> None:
        """Test analyze security help output (scan command merged here)."""
        result = runner.invoke(app, ["analyze", "security", "--help"])
        assert result.exit_code == 0
        assert "security" in result.stdout.lower()


class TestSkillCraftCommand:
    """Test suite for skill-craft command."""

    def test_skill_craft_help(self) -> None:
        """Test skill-craft help output."""
        result = runner.invoke(app, ["skill-craft", "--help"])
        assert result.exit_code == 0
        assert "skill" in result.stdout.lower()

    def test_skill_craft_templates(self) -> None:
        """Test skill-craft templates action."""
        result = runner.invoke(app, ["skill-craft", "templates"])
        assert result.exit_code == 0

    def test_skill_craft_create_no_name(self) -> None:
        """Test skill-craft create without name."""
        result = runner.invoke(app, ["skill-craft", "create"])
        # Should exit with 0 (shows usage) or provide guidance
        assert result.exit_code in (0, 1)


class TestToolsCommand:
    """Test suite for tools command."""

    def test_tools_help(self) -> None:
        """Test tools help output."""
        result = runner.invoke(app, ["tools", "--help"])
        assert result.exit_code == 0
        assert "external tools" in result.stdout.lower()

    def test_tools_list(self) -> None:
        """Test tools list action."""
        result = runner.invoke(app, ["tools", "list"])
        assert result.exit_code == 0

    def test_tools_check(self) -> None:
        """Test tools check action."""
        result = runner.invoke(app, ["tools", "check"])
        assert result.exit_code in (0, 1)  # May fail if tools missing
