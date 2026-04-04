"""Tests for IntegrationDetector class."""

from __future__ import annotations

from vibesop.integrations.detector import IntegrationDetector


class TestIntegrationDetector:
    """Tests for integration detection."""

    def test_create_detector(self) -> None:
        """Test creating an IntegrationDetector."""
        detector = IntegrationDetector()
        assert detector is not None

    def test_detect_all(self) -> None:
        """Test detecting all integrations."""
        detector = IntegrationDetector()
        integrations = detector.detect_all()

        assert isinstance(integrations, list)
