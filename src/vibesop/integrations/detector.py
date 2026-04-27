# pyright: reportMissingTypeArgument=false
"""Integration detection for VibeSOP.

This module detects external skill pack integrations
like Superpowers and gstack.
"""

import logging
from enum import Enum
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class IntegrationStatus(Enum):
    """Status of an integration.

    Attributes:
        INSTALLED: Integration is installed and available
        NOT_INSTALLED: Integration is not installed
        INCOMPATIBLE: Integration is installed but incompatible
        UNKNOWN: Status could not be determined
    """

    INSTALLED = "installed"
    NOT_INSTALLED = "not_installed"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


class IntegrationInfo(BaseModel):
    """Information about an integration.

    Attributes:
        name: Integration name
        description: Human-readable description
        status: Installation status
        version: Version (if available)
        path: Installation path (if available)
        skills: List of skills provided by this integration
    """

    name: str = Field(..., description="Integration name")
    description: str = Field(..., description="Human-readable description")
    status: IntegrationStatus = Field(..., description="Installation status")
    version: str | None = Field(default=None, description="Version string")
    path: Path | None = Field(default=None, description="Installation path")
    skills: list[str] = Field(default_factory=list, description="List of skill IDs")

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "version": self.version,
            "path": str(self.path) if self.path else None,
            "skills": self.skills,
        }


class IntegrationDetector:
    """Detects external skill pack integrations.

    Checks for installed integrations like:
    - Superpowers skill pack
    - gstack skill pack
    - Custom user integrations

    Example:
        >>> detector = IntegrationDetector()
        >>> integrations = detector.detect_all()
        >>> for info in integrations:
        ...     print(f"{info.name}: {info.status.value}")
    """

    # Known integration paths
    # IMPORTANT: Order matters! We prioritize paths that contain actual skill pack directories
    # (gstack/, superpowers/) over paths with fine-grained symlinks (gstack-browse/, etc.)
    SKILLS_BASE_PATHS: ClassVar[list[Path]] = [
        Path.home() / ".config" / "skills",  # ← Contains gstack/, superpowers/ dirs
        Path.home() / ".claude" / "skills",  # ← Contains gstack/, superpowers/ symlinks
        Path.home()
        / ".config"
        / "claude"
        / "skills",  # ← Contains fine-grained symlinks (gstack-browse/, etc.)
    ]

    # Known integrations
    KNOWN_INTEGRATIONS: ClassVar[dict[str, dict]] = {
        "superpowers": {
            "description": "General-purpose productivity skills",
            "paths": ["superpowers"],
            "skills": [
                "superpowers/tdd",
                "superpowers/brainstorm",
                "superpowers/refactor",
                "superpowers/debug",
                "superpowers/architect",
                "superpowers/review",
                "superpowers/optimize",
            ],
        },
        "gstack": {
            "description": "Virtual engineering team skills",
            "paths": ["gstack"],
            "skills": [
                "gstack/office-hours",
                "gstack/plan-ceo-review",
                "gstack/plan-eng-review",
                "gstack/review",
                "gstack/investigate",
                "gstack/qa",
                "gstack/ship",
                "gstack/careful",
            ],
        },
    }

    def __init__(self) -> None:
        """Initialize the integration detector."""
        self._skills_base_path: Path | None = None

    @property
    def skills_base_path(self) -> Path | None:
        """Get the detected skills base path.

        Returns:
            Path to skills directory, or None if not found
        """
        if self._skills_base_path is None:
            self._skills_base_path = self._find_skills_base_path()
        return self._skills_base_path

    def detect_all(self) -> list[IntegrationInfo]:
        """Detect all known integrations.

        Returns:
            List of IntegrationInfo for all known integrations
        """
        integrations = []

        for name, config in self.KNOWN_INTEGRATIONS.items():
            info = self.detect_integration(name, config)
            integrations.append(info)

        return integrations

    def detect_integration(
        self,
        name: str,
        config: dict | None = None,
    ) -> IntegrationInfo:
        """Detect a specific integration.

        Args:
            name: Integration name
            config: Integration configuration (uses KNOWN_INTEGRATIONS if None)

        Returns:
            IntegrationInfo with detection results
        """
        if config is None:
            config = self.KNOWN_INTEGRATIONS.get(name, {})
        description = config.get("description", "Unknown integration")
        expected_paths = config.get("paths", [])
        skills = config.get("skills", [])

        # Check if integration is installed
        integration_path, status = self._check_integration_paths(expected_paths)

        # Try to get version
        version = self._get_integration_version(name, integration_path)

        return IntegrationInfo(
            name=name,
            description=description,
            status=status,
            version=version,
            path=integration_path,
            skills=skills,
        )

    def is_integration_installed(self, name: str) -> bool:
        """Check if an integration is installed.

        Args:
            name: Integration name

        Returns:
            True if installed, False otherwise
        """
        info = self.detect_integration(name)
        return info.status == IntegrationStatus.INSTALLED

    def get_integration_skills(self, name: str) -> list[str]:
        """Get skills provided by an integration.

        Args:
            name: Integration name

        Returns:
            List of skill IDs
        """
        config = self.KNOWN_INTEGRATIONS.get(name, {})
        skills = config.get("skills", [])
        return skills if isinstance(skills, list) else []

    def _find_skills_base_path(self) -> Path | None:
        """Find the skills base directory.

        Returns:
            Path to skills directory, or None if not found
        """
        for base_path in self.SKILLS_BASE_PATHS:
            if base_path.exists() and base_path.is_dir():
                return base_path
        return None

    def _check_integration_paths(
        self,
        expected_paths: list[str],
    ) -> tuple[Path | None, IntegrationStatus]:
        """Check if integration paths exist.

        Args:
            expected_paths: List of expected path components

        Returns:
            Tuple of (found_path, status)
        """
        if not self.skills_base_path:
            return None, IntegrationStatus.NOT_INSTALLED

        for path_component in expected_paths:
            integration_path = self.skills_base_path / path_component

            if integration_path.exists() and integration_path.is_dir():
                return integration_path, IntegrationStatus.INSTALLED

        return None, IntegrationStatus.NOT_INSTALLED

    def _get_integration_version(
        self,
        _name: str,
        path: Path | None,
    ) -> str | None:
        """Get integration version.

        Args:
            name: Integration name
            path: Integration path

        Returns:
            Version string, or None if not available
        """
        if not path:
            return None

        # Try to read version from package.json or similar
        version_files = [
            path / "package.json",
            path / "version.txt",
            path / ".version",
        ]

        for version_file in version_files:
            if version_file.exists():
                try:
                    content = version_file.read_text()
                    # Try to extract version
                    import json

                    if version_file.suffix == ".json":
                        data = json.loads(content)
                        return data.get("version")
                    else:
                        return content.strip()
                except Exception as e:
                    logger.debug(f"Failed to read version from {version_file}: {e}")
                    continue

        return None
