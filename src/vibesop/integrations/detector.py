"""Integration detection for VibeSOP.

This module detects external skill pack integrations
like Superpowers and gstack.
"""

from pathlib import Path
from typing import Dict, List, Optional
from enum import Enum


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


class IntegrationInfo:
    """Information about an integration.

    Attributes:
        name: Integration name
        description: Human-readable description
        status: Installation status
        version: Version (if available)
        path: Installation path (if available)
        skills: List of skills provided by this integration
    """

    def __init__(
        self,
        name: str,
        description: str,
        status: IntegrationStatus,
        version: Optional[str] = None,
        path: Optional[Path] = None,
        skills: Optional[List[str]] = None,
    ) -> None:
        """Initialize integration info.

        Args:
            name: Integration name
            description: Human-readable description
            status: Installation status
            version: Version (if available)
            path: Installation path (if available)
            skills: List of skills provided by this integration
        """
        self.name = name
        self.description = description
        self.status = status
        self.version = version
        self.path = path
        self.skills = skills or []

    def to_dict(self) -> Dict:
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
    SKILLS_BASE_PATHS = [
        Path.home() / ".config" / "claude" / "skills",
        Path.home() / ".config" / "skills",
        Path.home() / ".claude" / "skills",
    ]

    # Known integrations
    KNOWN_INTEGRATIONS = {
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
        self._skills_base_path: Optional[Path] = None

    @property
    def skills_base_path(self) -> Optional[Path]:
        """Get the detected skills base path.

        Returns:
            Path to skills directory, or None if not found
        """
        if self._skills_base_path is None:
            self._skills_base_path = self._find_skills_base_path()
        return self._skills_base_path

    def detect_all(self) -> List[IntegrationInfo]:
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
        config: Optional[Dict] = None,
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

    def get_integration_skills(self, name: str) -> List[str]:
        """Get skills provided by an integration.

        Args:
            name: Integration name

        Returns:
            List of skill IDs
        """
        config = self.KNOWN_INTEGRATIONS.get(name, {})
        return config.get("skills", [])

    def _find_skills_base_path(self) -> Optional[Path]:
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
        expected_paths: List[str],
    ) -> tuple[Optional[Path], IntegrationStatus]:
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
        name: str,
        path: Optional[Path],
    ) -> Optional[str]:
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
                except Exception:
                    continue

        return None
