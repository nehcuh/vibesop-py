# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
"""Integration management for VibeSOP.

This module provides management capabilities for external
skill pack integrations.
"""

from pathlib import Path
from typing import Any

from vibesop.integrations.detector import (
    IntegrationDetector,
    IntegrationInfo,
    IntegrationStatus,
)


class IntegrationManager:
    """Manages external skill pack integrations.

    Provides high-level operations for working with integrations:
    - List all integrations
    - Get integration details
    - Check compatibility
    - Get integration skills

    Example:
        >>> manager = IntegrationManager()
        >>> integrations = manager.list_integrations()
        >>> for info in integrations:
        ...     print(f"{info.name}: {info.status.value}")
    """

    def __init__(self) -> None:
        """Initialize the integration manager."""
        self.detector = IntegrationDetector()
        self._cache: list[IntegrationInfo] | None = None

    def list_integrations(
        self,
        refresh: bool = False,
    ) -> list[IntegrationInfo]:
        """List all known integrations.

        Args:
            refresh: Force refresh of cached results

        Returns:
            List of IntegrationInfo for all known integrations
        """
        if self._cache is None or refresh:
            self._cache = self.detector.detect_all()

        return self._cache

    def get_integration(self, name: str) -> IntegrationInfo | None:
        """Get information about a specific integration.

        Args:
            name: Integration name

        Returns:
            IntegrationInfo, or None if not found
        """
        integrations = self.list_integrations()

        for info in integrations:
            if info.name == name:
                return info

        return None

    def is_installed(self, name: str) -> bool:
        """Check if an integration is installed.

        Args:
            name: Integration name

        Returns:
            True if installed, False otherwise
        """
        return self.detector.is_integration_installed(name)

    def get_skills(
        self,
        name: str | None = None,
    ) -> list[str]:
        """Get skills from integrations.

        Args:
            name: Integration name (None = all integrations)

        Returns:
            List of skill IDs
        """
        if name:
            return self.detector.get_integration_skills(name)
        else:
            all_skills: list[str] = []
            integrations = self.list_integrations()
            for info in integrations:
                if info.status == IntegrationStatus.INSTALLED:
                    all_skills.extend(info.skills)

            return all_skills

    def get_installed_integrations(self) -> list[IntegrationInfo]:
        """Get list of installed integrations.

        Returns:
            List of installed IntegrationInfo
        """
        integrations = self.list_integrations()
        return [info for info in integrations if info.status == IntegrationStatus.INSTALLED]

    def get_compatible_integrations(self) -> list[IntegrationInfo]:
        """Get list of compatible integrations.

        Returns:
            List of compatible IntegrationInfo
        """
        integrations = self.list_integrations()
        return [
            info
            for info in integrations
            if info.status
            in [
                IntegrationStatus.INSTALLED,
                IntegrationStatus.NOT_INSTALLED,
            ]
        ]

    def get_summary(self) -> dict[str, Any]:
        """Get summary of all integrations.

        Returns:
            Dictionary with integration statistics
        """
        integrations = self.list_integrations()

        installed_count = sum(
            1 for info in integrations if info.status == IntegrationStatus.INSTALLED
        )
        total_count = len(integrations)

        all_skills = self.get_skills()
        skills_count = len(all_skills)

        return {
            "total_integrations": total_count,
            "installed_integrations": installed_count,
            "available_integrations": total_count - installed_count,
            "total_skills": skills_count,
            "integrations": [
                {
                    "name": info.name,
                    "status": info.status.value,
                    "version": info.version,
                    "skill_count": len(info.skills),
                }
                for info in integrations
            ],
        }

    def refresh(self) -> None:
        """Refresh cached integration information."""
        self._cache = None
        self.list_integrations(refresh=True)

    def check_integration_compatibility(
        self,
        name: str,
    ) -> dict[str, Any]:
        """Check integration compatibility.

        Args:
            name: Integration name

        Returns:
            Dictionary with compatibility information
        """
        info = self.get_integration(name)

        if not info:
            return {
                "compatible": False,
                "reason": "Integration not found",
            }

        if info.status == IntegrationStatus.INSTALLED:
            return {
                "compatible": True,
                "reason": "Installed and compatible",
                "version": info.version,
                "path": str(info.path) if info.path else None,
            }
        elif info.status == IntegrationStatus.NOT_INSTALLED:
            return {
                "compatible": True,
                "reason": "Not installed but compatible",
                "install_hint": f"Install {name} to use its skills",
            }
        else:
            return {
                "compatible": False,
                "reason": f"Incompatible: {info.status.value}",
            }

    def get_integration_path(self, name: str) -> Path | None:
        """Get the installation path for an integration.

        Args:
            name: Integration name

        Returns:
            Path to integration, or None if not installed
        """
        info = self.get_integration(name)

        if info and info.status == IntegrationStatus.INSTALLED:
            return info.path

        return None

    def get_integration_registry(
        self,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Get integration registry for manifest generation.

        Args:
            name: Integration name (None = all integrations)

        Returns:
            Dictionary with integration registry data
        """
        if name:
            info = self.get_integration(name)
            if not info:
                return {}

            return {
                "name": info.name,
                "description": info.description,
                "skills": info.skills,
                "installed": info.status == IntegrationStatus.INSTALLED,
            }
        else:
            # Return registry for all integrations
            integrations = self.list_integrations()
            return {
                info.name: {
                    "description": info.description,
                    "skills": info.skills,
                    "installed": info.status == IntegrationStatus.INSTALLED,
                }
                for info in integrations
            }
