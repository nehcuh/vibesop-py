"""Tests for external tools detection system."""

from unittest.mock import patch

from vibesop.utils import (
    ExternalToolsDetector,
    ToolInfo,
    ToolStatus,
)


class TestToolStatus:
    """Test ToolStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert ToolStatus.AVAILABLE.value == "available"
        assert ToolStatus.NOT_AVAILABLE.value == "not_available"
        assert ToolStatus.VERSION_MISMATCH.value == "version_mismatch"
        assert ToolStatus.PERMISSION_DENIED.value == "permission_denied"
        assert ToolStatus.UNKNOWN.value == "unknown"


class TestToolInfo:
    """Test ToolInfo dataclass."""

    def test_create_tool_info(self) -> None:
        """Test creating tool info."""
        info = ToolInfo(
            name="git",
            command="git",
            version_command="git --version",
            min_version="2.0.0",
            optional=False,
            status=ToolStatus.AVAILABLE,
            version="2.30.0",
            path="/usr/bin/git",
        )
        assert info.name == "git"
        assert info.status == ToolStatus.AVAILABLE
        assert info.version == "2.30.0"


class TestExternalToolsDetector:
    """Test ExternalToolsDetector functionality."""

    def test_create_detector(self) -> None:
        """Test creating detector."""
        detector = ExternalToolsDetector()
        assert detector is not None

    def test_detect_all(self) -> None:
        """Test detecting all tools."""
        detector = ExternalToolsDetector()
        tools = detector.detect_all()

        assert isinstance(tools, dict)
        assert len(tools) > 0
        # git should almost always be available
        if "git" in tools:
            assert isinstance(tools["git"], ToolInfo)

    def test_detect_tool_known(self) -> None:
        """Test detecting a known tool."""
        detector = ExternalToolsDetector()
        tool_info = detector.detect_tool("git")

        assert tool_info is not None
        assert isinstance(tool_info, ToolInfo)
        assert tool_info.name == "git"

    def test_detect_tool_unknown(self) -> None:
        """Test detecting an unknown tool."""
        detector = ExternalToolsDetector()
        tool_info = detector.detect_tool("nonexistent_tool")

        assert tool_info is None

    def test_check_requirements_all_available(self) -> None:
        """Test checking requirements when all available."""
        detector = ExternalToolsDetector()

        # Test with git which should be available in most environments
        result = detector.check_requirements(["git"])

        assert "all_available" in result
        assert "missing_tools" in result
        assert "tool_status" in result

    def test_check_requirements_missing(self) -> None:
        """Test checking requirements with missing tools."""
        detector = ExternalToolsDetector()

        # Test with docker which might not be available in all environments
        result = detector.check_requirements(["docker"])

        # Result depends on whether docker is installed
        assert "all_available" in result
        assert "docker" in result["tool_status"]

        # If not available, should be in missing_tools
        if not result["all_available"]:
            assert "docker" in result["missing_tools"] or result["tool_status"]["docker"]["status"] != "available"

    def test_get_installation_instructions_known(self) -> None:
        """Test getting installation instructions for known tool."""
        detector = ExternalToolsDetector()
        instructions = detector.get_installation_instructions("git")

        assert instructions is not None
        assert isinstance(instructions, str)
        assert len(instructions) > 0

    def test_get_installation_instructions_unknown(self) -> None:
        """Test getting installation instructions for unknown tool."""
        detector = ExternalToolsDetector()
        instructions = detector.get_installation_instructions("unknown_tool")

        assert instructions is None

    def test_parse_version_valid(self) -> None:
        """Test parsing valid version strings."""
        detector = ExternalToolsDetector()

        # Test various version formats
        assert detector._parse_version("git version 2.30.0") in ["2.30.0", "2.30"]
        assert detector._parse_version("v1.2.3") == "1.2.3"
        assert detector._parse_version("Node.js v18.0.0") in ["18.0.0", "18.0"]

    def test_parse_version_invalid(self) -> None:
        """Test parsing invalid version strings."""
        detector = ExternalToolsDetector()

        assert detector._parse_version("no version here") is None
        assert detector._parse_version("") is None

    def test_check_version_valid(self) -> None:
        """Test version comparison."""
        detector = ExternalToolsDetector()

        # Test with packaging library if available
        from importlib.util import find_spec

        if find_spec("packaging") is not None:
            assert detector._check_version("2.0.0", "1.0.0") is True
            assert detector._check_version("1.0.0", "2.0.0") is False
            assert detector._check_version("1.5.0", "1.5.0") is True
        else:
            # Fallback to string comparison
            assert detector._check_version("2.0.0", "1.0.0") is True
            assert detector._check_version("1.0.0", "2.0.0") is False

    def test_get_tool_summary(self) -> None:
        """Test getting tool summary."""
        detector = ExternalToolsDetector()
        summary = detector.get_tool_summary()

        assert "required_tools" in summary
        assert "optional_tools" in summary
        assert "all_tools" in summary

        required = summary["required_tools"]
        assert "available" in required
        assert "total" in required
        assert "percentage" in required

        optional = summary["optional_tools"]
        assert "available" in optional
        assert "total" in optional

    def test_detect_tool_not_available(self) -> None:
        """Test detecting a tool that is not available."""
        detector = ExternalToolsDetector()

        with patch("shutil.which", return_value=None):
            tool_info = detector._detect_tool(
                "test_tool",
                {
                    "command": "test_tool",
                    "version_command": None,
                    "min_version": None,
                    "optional": True,
                }
            )

            assert tool_info.status == ToolStatus.NOT_AVAILABLE
            assert tool_info.path is None

    def test_detect_tool_available_no_version(self) -> None:
        """Test detecting a tool without version checking."""
        detector = ExternalToolsDetector()

        with patch("shutil.which", return_value="/usr/bin/test"):
            tool_info = detector._detect_tool(
                "test_tool",
                {
                    "command": "test_tool",
                    "version_command": None,
                    "min_version": None,
                    "optional": True,
                }
            )

            assert tool_info.status == ToolStatus.AVAILABLE
            assert tool_info.path == "/usr/bin/test"
