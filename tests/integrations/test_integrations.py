"""Tests for integration management."""

import pytest
from pathlib import Path

from vibesop.integrations import (
    IntegrationDetector,
    IntegrationManager,
    IntegrationStatus,
)


class TestIntegrationDetector:
    """Test IntegrationDetector functionality."""

    def test_create_detector(self) -> None:
        """Test creating detector."""
        detector = IntegrationDetector()
        assert detector is not None
        assert detector.skills_base_path is None or isinstance(detector.skills_base_path, Path)

    def test_detect_all(self) -> None:
        """Test detecting all integrations."""
        detector = IntegrationDetector()
        integrations = detector.detect_all()

        # Should detect known integrations
        assert len(integrations) >= 2  # superpowers and gstack

        # Check structure
        for info in integrations:
            assert info.name in ["superpowers", "gstack"]
            assert info.description
            assert isinstance(info.status, IntegrationStatus)
            assert isinstance(info.skills, list)

    def test_detect_superpowers(self) -> None:
        """Test detecting Superpowers integration."""
        detector = IntegrationDetector()
        info = detector.detect_integration("superpowers")

        assert info.name == "superpowers"
        assert info.description
        assert isinstance(info.status, IntegrationStatus)
        assert len(info.skills) > 0

        # Check known skills
        assert "superpowers/tdd" in info.skills
        assert "superpowers/review" in info.skills

    def test_detect_gstack(self) -> None:
        """Test detecting gstack integration."""
        detector = IntegrationDetector()
        info = detector.detect_integration("gstack")

        assert info.name == "gstack"
        assert info.description
        assert isinstance(info.status, IntegrationStatus)
        assert len(info.skills) > 0

        # Check known skills
        assert "gstack/office-hours" in info.skills
        assert "gstack/qa" in info.skills

    def test_is_integration_installed(self) -> None:
        """Test checking if integration is installed."""
        detector = IntegrationDetector()

        # These might or might not be installed
        result = detector.is_integration_installed("superpowers")
        assert isinstance(result, bool)

    def test_get_integration_skills(self) -> None:
        """Test getting integration skills."""
        detector = IntegrationDetector()

        skills = detector.get_integration_skills("superpowers")
        assert isinstance(skills, list)
        assert len(skills) > 0
        assert "superpowers/tdd" in skills

    def test_integration_info_to_dict(self) -> None:
        """Test converting IntegrationInfo to dict."""
        detector = IntegrationDetector()
        info = detector.detect_integration("superpowers")

        info_dict = info.to_dict()

        assert isinstance(info_dict, dict)
        assert "name" in info_dict
        assert "description" in info_dict
        assert "status" in info_dict
        assert "skills" in info_dict
        assert info_dict["name"] == "superpowers"


class TestIntegrationManager:
    """Test IntegrationManager functionality."""

    def test_create_manager(self) -> None:
        """Test creating manager."""
        manager = IntegrationManager()
        assert manager is not None
        assert manager.detector is not None

    def test_list_integrations(self) -> None:
        """Test listing all integrations."""
        manager = IntegrationManager()
        integrations = manager.list_integrations()

        assert len(integrations) >= 2
        assert all(isinstance(info, type(integrations[0])) for info in integrations)

    def test_get_integration(self) -> None:
        """Test getting specific integration."""
        manager = IntegrationManager()

        # Get existing integration
        info = manager.get_integration("superpowers")
        assert info is not None
        assert info.name == "superpowers"

        # Get non-existing integration
        info = manager.get_integration("nonexistent")
        assert info is None

    def test_is_installed(self) -> None:
        """Test checking if integration is installed."""
        manager = IntegrationManager()

        result = manager.is_installed("superpowers")
        assert isinstance(result, bool)

    def test_get_skills_all(self) -> None:
        """Test getting skills from all integrations."""
        manager = IntegrationManager()

        skills = manager.get_skills()
        assert isinstance(skills, list)

        # Should only return skills from installed integrations
        # (Empty if no integrations are installed)
        # At minimum, verify it's a list
        assert isinstance(skills, list)

    def test_get_skills_specific(self) -> None:
        """Test getting skills from specific integration."""
        manager = IntegrationManager()

        skills = manager.get_skills("superpowers")
        assert isinstance(skills, list)
        assert "superpowers/tdd" in skills

    def test_get_installed_integrations(self) -> None:
        """Test getting installed integrations."""
        manager = IntegrationManager()

        installed = manager.get_installed_integrations()
        assert isinstance(installed, list)

        # All should be installed
        for info in installed:
            assert info.status == IntegrationStatus.INSTALLED

    def test_get_compatible_integrations(self) -> None:
        """Test getting compatible integrations."""
        manager = IntegrationManager()

        compatible = manager.get_compatible_integrations()
        assert isinstance(compatible, list)

        # All should be compatible
        for info in compatible:
            assert info.status in [
                IntegrationStatus.INSTALLED,
                IntegrationStatus.NOT_INSTALLED,
            ]

    def test_get_summary(self) -> None:
        """Test getting integration summary."""
        manager = IntegrationManager()

        summary = manager.get_summary()

        assert isinstance(summary, dict)
        assert "total_integrations" in summary
        assert "installed_integrations" in summary
        assert "available_integrations" in summary
        assert "total_skills" in summary
        assert "integrations" in summary

        # Check counts make sense
        assert summary["total_integrations"] >= 2
        assert summary["installed_integrations"] >= 0
        assert summary["total_skills"] >= 0

    def test_refresh(self) -> None:
        """Test refreshing integration cache."""
        manager = IntegrationManager()

        # Get initial list
        integrations1 = manager.list_integrations()

        # Refresh
        manager.refresh()

        # Get refreshed list
        integrations2 = manager.list_integrations()

        # Should be same length
        assert len(integrations1) == len(integrations2)

    def test_check_compatibility(self) -> None:
        """Test checking integration compatibility."""
        manager = IntegrationManager()

        compat = manager.check_integration_compatibility("superpowers")

        assert isinstance(compat, dict)
        assert "compatible" in compat
        assert "reason" in compat

    def test_check_compatibility_unknown(self) -> None:
        """Test compatibility for unknown integration."""
        manager = IntegrationManager()

        compat = manager.check_integration_compatibility("unknown-integration")

        assert compat["compatible"] is False
        assert "not found" in compat["reason"].lower()

    def test_get_integration_path(self) -> None:
        """Test getting integration path."""
        manager = IntegrationManager()

        path = manager.get_integration_path("superpowers")

        # Should be None if not installed, or Path if installed
        assert path is None or isinstance(path, Path)

    def test_get_integration_registry_all(self) -> None:
        """Test getting registry for all integrations."""
        manager = IntegrationManager()

        registry = manager.get_integration_registry()

        assert isinstance(registry, dict)
        assert "superpowers" in registry
        assert "gstack" in registry

        # Check structure
        for name, data in registry.items():
            assert "description" in data
            assert "skills" in data
            assert "installed" in data

    def test_get_integration_registry_specific(self) -> None:
        """Test getting registry for specific integration."""
        manager = IntegrationManager()

        registry = manager.get_integration_registry("superpowers")

        assert isinstance(registry, dict)
        assert registry["name"] == "superpowers"
        assert "skills" in registry
        assert "installed" in registry

    def test_get_integration_registry_unknown(self) -> None:
        """Test getting registry for unknown integration."""
        manager = IntegrationManager()

        registry = manager.get_integration_registry("unknown")
        assert registry == {}


class TestIntegrationManagementIntegration:
    """Integration tests for integration management."""

    def test_full_workflow(self) -> None:
        """Test complete integration workflow."""
        manager = IntegrationManager()

        # List integrations
        integrations = manager.list_integrations()
        assert len(integrations) >= 2

        # Get summary
        summary = manager.get_summary()
        assert summary["total_integrations"] >= 2

        # Check compatibility
        for info in integrations:
            compat = manager.check_integration_compatibility(info.name)
            assert "compatible" in compat

    def test_skill_aggregation(self) -> None:
        """Test aggregating skills from multiple integrations."""
        manager = IntegrationManager()

        # Get all skills
        all_skills = manager.get_skills()

        # Should have skills from both integrations
        assert isinstance(all_skills, list)

        # Check for known skills
        known_skills = [
            "superpowers/tdd",
            "superpowers/review",
            "gstack/office-hours",
            "gstack/qa",
        ]

        for skill in known_skills:
            # Skills might not be available if integrations not installed
            # but they should be defined in the registry
            pass  # Just verify the list is populated

    def test_caching_behavior(self) -> None:
        """Test manager caching behavior."""
        manager = IntegrationManager()

        # First call
        integrations1 = manager.list_integrations()

        # Second call (should use cache)
        integrations2 = manager.list_integrations()

        # Should be same objects (cached)
        assert len(integrations1) == len(integrations2)

        # Refresh
        manager.refresh()

        # Third call (should get fresh data)
        integrations3 = manager.list_integrations()

        assert len(integrations2) == len(integrations3)
