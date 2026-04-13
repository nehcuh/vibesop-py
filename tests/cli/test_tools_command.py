"""Tests for vibe tools command."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from vibesop.cli.main import app
from vibesop.utils.external_tools import ToolInfo, ToolStatus

runner = CliRunner()


def _make_tool(name: str, status: ToolStatus, optional: bool = False, version: str | None = "1.0.0", path: str | None = "/usr/bin/name") -> ToolInfo:
    return ToolInfo(
        name=name,
        command=name,
        version_command=f"{name} --version",
        min_version=None,
        optional=optional,
        status=status,
        version=version,
        path=path,
    )


class TestToolsCommand:
    """Test suite for tools command."""

    @patch("vibesop.cli.commands.tools_cmd.ExternalToolsDetector")
    def test_tools_list(self, mock_detector_cls) -> None:
        """Test tools list action."""
        mock_detector = MagicMock()
        mock_detector.detect_all.return_value = {
            "git": _make_tool("git", ToolStatus.AVAILABLE, optional=False),
            "node": _make_tool("node", ToolStatus.NOT_AVAILABLE, optional=True),
        }
        mock_detector_cls.return_value = mock_detector

        result = runner.invoke(app, ["tools", "list"])
        assert result.exit_code == 0
        assert "External Tools" in result.stdout
        assert "git" in result.stdout
        assert "node" in result.stdout

    @patch("vibesop.cli.commands.tools_cmd.ExternalToolsDetector")
    def test_tools_show(self, mock_detector_cls) -> None:
        """Test tools show action."""
        mock_detector = MagicMock()
        mock_detector.detect_tool.return_value = _make_tool("git", ToolStatus.AVAILABLE, version="2.40.0", path="/usr/bin/git")
        mock_detector_cls.return_value = mock_detector

        result = runner.invoke(app, ["tools", "show", "git"])
        assert result.exit_code == 0
        assert "git" in result.stdout
        assert "available" in result.stdout
        assert "/usr/bin/git" in result.stdout

    @patch("vibesop.cli.commands.tools_cmd.ExternalToolsDetector")
    def test_tools_show_missing_name(self, mock_detector_cls) -> None:
        """Test tools show without tool name."""
        mock_detector = MagicMock()
        mock_detector_cls.return_value = mock_detector

        result = runner.invoke(app, ["tools", "show"])
        assert result.exit_code == 1
        assert "Tool name required" in result.stdout

    @patch("vibesop.cli.commands.tools_cmd.ExternalToolsDetector")
    def test_tools_show_unknown(self, mock_detector_cls) -> None:
        """Test tools show for unknown tool."""
        mock_detector = MagicMock()
        mock_detector.detect_tool.return_value = None
        mock_detector_cls.return_value = mock_detector

        result = runner.invoke(app, ["tools", "show", "unknown"])
        assert result.exit_code == 1
        assert "Unknown tool" in result.stdout

    @patch("vibesop.cli.commands.tools_cmd.ExternalToolsDetector")
    def test_tools_verify_available(self, mock_detector_cls) -> None:
        """Test tools verify for available tool."""
        mock_detector = MagicMock()
        mock_detector.detect_tool.return_value = _make_tool("git", ToolStatus.AVAILABLE, version="2.40.0")
        mock_detector_cls.return_value = mock_detector

        result = runner.invoke(app, ["tools", "verify", "git"])
        assert result.exit_code == 0
        assert "git is available" in result.stdout

    @patch("vibesop.cli.commands.tools_cmd.ExternalToolsDetector")
    def test_tools_verify_missing_name(self, mock_detector_cls) -> None:
        """Test tools verify without tool name."""
        mock_detector = MagicMock()
        mock_detector_cls.return_value = mock_detector

        result = runner.invoke(app, ["tools", "verify"])
        assert result.exit_code == 1
        assert "Tool name required" in result.stdout

    @patch("vibesop.cli.commands.tools_cmd.ExternalToolsDetector")
    def test_tools_verify_not_available(self, mock_detector_cls) -> None:
        """Test tools verify for unavailable tool."""
        mock_detector = MagicMock()
        mock_detector.detect_tool.return_value = _make_tool("node", ToolStatus.NOT_AVAILABLE)
        mock_detector_cls.return_value = mock_detector

        result = runner.invoke(app, ["tools", "verify", "node"])
        assert result.exit_code == 1
        assert "node is not available" in result.stdout

    @patch("vibesop.cli.commands.tools_cmd.ExternalToolsDetector")
    def test_tools_verify_unknown(self, mock_detector_cls) -> None:
        """Test tools verify for unknown tool."""
        mock_detector = MagicMock()
        mock_detector.detect_tool.return_value = None
        mock_detector_cls.return_value = mock_detector

        result = runner.invoke(app, ["tools", "verify", "unknown"])
        assert result.exit_code == 1
        assert "Unknown tool" in result.stdout

    @patch("vibesop.cli.commands.tools_cmd.ExternalToolsDetector")
    def test_tools_check_all_ok(self, mock_detector_cls) -> None:
        """Test tools check when all required tools are available."""
        mock_detector = MagicMock()
        mock_detector.detect_all.return_value = {
            "git": _make_tool("git", ToolStatus.AVAILABLE, optional=False),
            "uv": _make_tool("uv", ToolStatus.AVAILABLE, optional=False),
        }
        mock_detector_cls.return_value = mock_detector

        result = runner.invoke(app, ["tools", "check"])
        assert result.exit_code == 0
        assert "All required tools are available" in result.stdout

    @patch("vibesop.cli.commands.tools_cmd.ExternalToolsDetector")
    def test_tools_check_missing_required(self, mock_detector_cls) -> None:
        """Test tools check when a required tool is missing."""
        mock_detector = MagicMock()
        mock_detector.detect_all.return_value = {
            "git": _make_tool("git", ToolStatus.AVAILABLE, optional=False),
            "docker": _make_tool("docker", ToolStatus.NOT_AVAILABLE, optional=False),
        }
        mock_detector_cls.return_value = mock_detector

        result = runner.invoke(app, ["tools", "check"])
        assert result.exit_code == 1
        assert "Some required tools are missing" in result.stdout

    def test_tools_unknown_action(self) -> None:
        """Test tools with invalid action."""
        result = runner.invoke(app, ["tools", "invalid"])
        assert result.exit_code == 1
        assert "Unknown action" in result.stdout
