"""External tools detection and verification.

This module provides capabilities for detecting and verifying
the availability of external tools required by VibeSOP.
"""

import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from vibesop.security.scanner import SecurityScanner


class ToolStatus(Enum):
    """Status of an external tool.

    Attributes:
        AVAILABLE: Tool is installed and accessible
        NOT_AVAILABLE: Tool is not installed
        VERSION_MISMATCH: Tool is installed but version is incompatible
        PERMISSION_DENIED: Tool exists but cannot be executed
        UNKNOWN: Unable to determine status
    """
    AVAILABLE = "available"
    NOT_AVAILABLE = "not_available"
    VERSION_MISMATCH = "version_mismatch"
    PERMISSION_DENIED = "permission_denied"
    UNKNOWN = "unknown"


@dataclass
class ToolInfo:
    """Information about an external tool.

    Attributes:
        name: Tool name
        command: Command to check availability
        version_command: Command to get version
        min_version: Minimum required version (optional)
        optional: Whether tool is optional or required
        status: Tool status
        version: Detected version (if available)
        path: Path to tool executable
    """
    name: str
    command: str
    version_command: Optional[str]
    min_version: Optional[str]
    optional: bool
    status: ToolStatus
    version: Optional[str]
    path: Optional[str]


class ExternalToolsDetector:
    """Detect and verify external tools.

    Scans for external tools required by VibeSOP and
    provides detailed status information.

    Example:
        >>> detector = ExternalToolsDetector()
        >>> tools = detector.detect_all()
        >>> for tool in tools:
        ...     print(f"{tool.name}: {tool.status}")
    """

    # Known tools and their detection methods
    KNOWN_TOOLS = {
        "git": {
            "command": "git",
            "version_command": "git --version",
            "min_version": "2.0.0",
            "optional": False,
            "description": "Version control system",
        },
        "node": {
            "command": "node",
            "version_command": "node --version",
            "min_version": "18.0.0",
            "optional": True,
            "description": "Node.js runtime",
        },
        "bun": {
            "command": "bun",
            "version_command": "bun --version",
            "min_version": "1.0.0",
            "optional": True,
            "description": "Bun runtime",
        },
        "python": {
            "command": "python3",
            "version_command": "python3 --version",
            "min_version": "3.12",
            "optional": False,
            "description": "Python runtime",
        },
        "pip": {
            "command": "pip3",
            "version_command": "pip3 --version",
            "min_version": None,
            "optional": False,
            "description": "Python package manager",
        },
        "gh": {
            "command": "gh",
            "version_command": "gh --version",
            "min_version": "2.0.0",
            "optional": True,
            "description": "GitHub CLI",
        },
        "rtk": {
            "command": "rtk",
            "version_command": "rtk --version",
            "min_version": None,
            "optional": True,
            "description": "RTK token optimizer",
        },
        "curl": {
            "command": "curl",
            "version_command": "curl --version",
            "min_version": None,
            "optional": True,
            "description": "HTTP client",
        },
        "wget": {
            "command": "wget",
            "version_command": "wget --version",
            "min_version": None,
            "optional": True,
            "description": "HTTP client",
        },
        "docker": {
            "command": "docker",
            "version_command": "docker --version",
            "min_version": None,
            "optional": True,
            "description": "Container runtime",
        },
    }

    def __init__(self) -> None:
        """Initialize the external tools detector."""
        self._scanner = SecurityScanner()

    def detect_all(self) -> Dict[str, ToolInfo]:
        """Detect all known tools.

        Returns:
            Dictionary mapping tool names to ToolInfo
        """
        tools = {}

        for tool_name, tool_config in self.KNOWN_TOOLS.items():
            tool_info = self._detect_tool(tool_name, tool_config)
            tools[tool_name] = tool_info

        return tools

    def detect_tool(self, tool_name: str) -> Optional[ToolInfo]:
        """Detect a specific tool.

        Args:
            tool_name: Name of the tool to detect

        Returns:
            ToolInfo if tool is known, None otherwise
        """
        if tool_name not in self.KNOWN_TOOLS:
            return None

        tool_config = self.KNOWN_TOOLS[tool_name]
        return self._detect_tool(tool_name, tool_config)

    def check_requirements(
        self,
        required_tools: List[str],
    ) -> Dict[str, Any]:
        """Check if required tools are available.

        Args:
            required_tools: List of required tool names

        Returns:
            Dictionary with check results
        """
        result = {
            "all_available": True,
            "missing_tools": [],
            "version_mismatches": [],
            "tool_status": {},
        }

        for tool_name in required_tools:
            tool_info = self.detect_tool(tool_name)

            if tool_info is None:
                result["tool_status"][tool_name] = {
                    "status": "unknown",
                    "message": f"Tool {tool_name} is not in known tools list",
                }
                continue

            status_info = {
                "status": tool_info.status.value,
                "version": tool_info.version,
                "path": tool_info.path,
            }

            if tool_info.status == ToolStatus.NOT_AVAILABLE:
                result["all_available"] = False
                result["missing_tools"].append(tool_name)
                status_info["message"] = f"Tool {tool_name} is not installed"

            elif tool_info.status == ToolStatus.VERSION_MISMATCH:
                result["all_available"] = False
                result["version_mismatches"].append(tool_name)
                status_info["message"] = (
                    f"Tool {tool_name} version {tool_info.version} "
                    f"is below minimum {tool_info.min_version}"
                )

            else:
                status_info["message"] = f"Tool {tool_name} is available"

            result["tool_status"][tool_name] = status_info

        return result

    def get_installation_instructions(
        self,
        tool_name: str,
    ) -> Optional[str]:
        """Get installation instructions for a tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Installation instructions, or None if tool is unknown
        """
        instructions = {
            "git": "Install Git from https://git-scm.com/downloads or use your package manager",
            "node": "Install Node.js from https://nodejs.org/ or use: brew install node",
            "bun": "Install Bun from https://bun.sh/ or use: curl -fsSL https://bun.sh/install | bash",
            "python": "Install Python 3.12+ from https://python.org/ or use your package manager",
            "pip": "Pip is usually installed with Python. If missing: python3 -m ensurepip --upgrade",
            "gh": "Install GitHub CLI from https://cli.github.com/ or use: brew install gh",
            "rtk": "Install RTK: npm install -g @rtk-cli/rtk or cargo install rtk",
            "curl": "Install curl from https://curl.se/ or use your package manager",
            "wget": "Install wget from https://www.gnu.org/software/wget/ or use your package manager",
            "docker": "Install Docker from https://docs.docker.com/get-docker/",
        }

        return instructions.get(tool_name)

    def _detect_tool(self, tool_name: str, tool_config: Dict) -> ToolInfo:
        """Detect a single tool.

        Args:
            tool_name: Name of the tool
            tool_config: Tool configuration dictionary

        Returns:
            ToolInfo with detection results
        """
        command = tool_config["command"]
        version_command = tool_config.get("version_command")
        min_version = tool_config.get("min_version")
        optional = tool_config.get("optional", False)

        # Check if command is available
        tool_path = shutil.which(command)

        if tool_path is None:
            return ToolInfo(
                name=tool_name,
                command=command,
                version_command=version_command,
                min_version=min_version,
                optional=optional,
                status=ToolStatus.NOT_AVAILABLE,
                version=None,
                path=None,
            )

        # Try to get version
        version = None
        status = ToolStatus.AVAILABLE

        if version_command:
            try:
                result = subprocess.run(
                    version_command.split(),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                if result.returncode == 0:
                    version = self._parse_version(result.stdout)

                    # Check minimum version if specified
                    if min_version and version:
                        if not self._check_version(version, min_version):
                            status = ToolStatus.VERSION_MISMATCH

            except subprocess.TimeoutExpired:
                status = ToolStatus.UNKNOWN
            except Exception:
                status = ToolStatus.UNKNOWN

        return ToolInfo(
            name=tool_name,
            command=command,
            version_command=version_command,
            min_version=min_version,
            optional=optional,
            status=status,
            version=version,
            path=tool_path,
        )

    def _parse_version(self, version_output: str) -> Optional[str]:
        """Parse version from command output.

        Args:
            version_output: Output from version command

        Returns:
            Version string, or None if not found
        """
        import re

        # Common version patterns
        patterns = [
            r"\d+\.\d+\.\d+",  # x.y.z
            r"\d+\.\d+",       # x.y
            r"v\d+\.\d+\.\d+", # vx.y.z
        ]

        for pattern in patterns:
            match = re.search(pattern, version_output)
            if match:
                version = match.group(0)
                # Remove 'v' prefix if present
                return version.lstrip("v")

        return None

    def _check_version(self, current: str, minimum: str) -> bool:
        """Check if current version meets minimum requirement.

        Args:
            current: Current version string
            minimum: Minimum required version string

        Returns:
            True if current >= minimum, False otherwise
        """
        try:
            from packaging import version as pkg_version

            return pkg_version.parse(current) >= pkg_version.parse(minimum)

        except Exception:
            # Fallback: simple string comparison
            return current >= minimum

    def get_tool_summary(self) -> Dict[str, Any]:
        """Get a summary of all tools status.

        Returns:
            Dictionary with summary information
        """
        tools = self.detect_all()

        required_available = sum(
            1 for t in tools.values()
            if not t.optional and t.status == ToolStatus.AVAILABLE
        )
        required_total = sum(
            1 for t in tools.values()
            if not t.optional
        )
        optional_available = sum(
            1 for t in tools.values()
            if t.optional and t.status == ToolStatus.AVAILABLE
        )
        optional_total = sum(
            1 for t in tools.values()
            if t.optional
        )

        return {
            "required_tools": {
                "available": required_available,
                "total": required_total,
                "percentage": (required_available / required_total * 100) if required_total > 0 else 100,
            },
            "optional_tools": {
                "available": optional_available,
                "total": optional_total,
                "percentage": (optional_available / optional_total * 100) if optional_total > 0 else 100,
            },
            "all_tools": {
                "available": required_available + optional_available,
                "total": required_total + optional_total,
            },
            "missing_required": [
                t.name for t in tools.values()
                if not t.optional and t.status != ToolStatus.AVAILABLE
            ],
            "missing_optional": [
                t.name for t in tools.values()
                if t.optional and t.status != ToolStatus.AVAILABLE
            ],
        }
