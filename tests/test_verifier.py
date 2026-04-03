"""Tests for integration verification system."""

import pytest
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

from vibesop.integrations import (
    IntegrationVerifier,
    VerificationResult,
    VerificationStatus,
    IntegrationReport,
    IntegrationStatus,
)


class TestVerificationStatus:
    """Test VerificationStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert VerificationStatus.PASSED.value == "passed"
        assert VerificationStatus.FAILED.value == "failed"
        assert VerificationStatus.WARNING.value == "warning"
        assert VerificationStatus.SKIPPED.value == "skipped"


class TestVerificationResult:
    """Test VerificationResult dataclass."""

    def test_create_result(self) -> None:
        """Test creating a verification result."""
        result = VerificationResult(
            check_name="test_check",
            status=VerificationStatus.PASSED,
            message="Check passed",
            details={"key": "value"},
            suggestions=["suggestion1"],
        )
        assert result.check_name == "test_check"
        assert result.status == VerificationStatus.PASSED
        assert result.message == "Check passed"
        assert result.details == {"key": "value"}
        assert len(result.suggestions) == 1


class TestIntegrationReport:
    """Test IntegrationReport dataclass."""

    def test_create_report(self) -> None:
        """Test creating an integration report."""
        results = [
            VerificationResult(
                check_name="check1",
                status=VerificationStatus.PASSED,
                message="Passed",
                details={},
                suggestions=[],
            )
        ]
        report = IntegrationReport(
            integration_id="test-integration",
            overall_status=VerificationStatus.PASSED,
            results=results,
            installed=True,
            functional=True,
            errors=[],
        )
        assert report.integration_id == "test-integration"
        assert report.overall_status == VerificationStatus.PASSED
        assert len(report.results) == 1
        assert report.installed
        assert report.functional
        assert len(report.errors) == 0


class TestIntegrationVerifier:
    """Test IntegrationVerifier functionality."""

    def test_create_verifier(self) -> None:
        """Test creating verifier."""
        verifier = IntegrationVerifier()
        assert verifier is not None

    def test_verify_integration_not_found(self) -> None:
        """Test verifying non-existent integration."""
        verifier = IntegrationVerifier()

        with patch.object(
            verifier._manager,
            'list_integrations',
            return_value=[],
        ):
            report = verifier.verify_integration("nonexistent")

            assert report.integration_id == "nonexistent"
            assert report.overall_status == VerificationStatus.FAILED
            assert not report.installed
            assert not report.functional
            assert len(report.errors) > 0
            assert "not found" in report.errors[0].lower()

    def test_verify_integration_installed(self) -> None:
        """Test verifying installed integration."""
        verifier = IntegrationVerifier()

        mock_integration = MagicMock()
        mock_integration.name = "gstack"
        mock_integration.status = IntegrationStatus.INSTALLED
        mock_integration.path = "/tmp/test"

        with patch.object(
            verifier._manager,
            'list_integrations',
            return_value=[mock_integration],
        ):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.is_dir", return_value=True):
                    with patch("shutil.which", return_value="/usr/bin/git"):
                        report = verifier.verify_integration("gstack")

                        assert report.integration_id == "gstack"
                        assert report.installed
                        # May not be fully functional without all files

    def test_verify_integration_not_installed(self) -> None:
        """Test verifying not installed integration."""
        verifier = IntegrationVerifier()

        mock_integration = MagicMock()
        mock_integration.name = "gstack"
        mock_integration.status = IntegrationStatus.NOT_INSTALLED
        mock_integration.path = "/tmp/test"

        with patch.object(
            verifier._manager,
            'list_integrations',
            return_value=[mock_integration],
        ):
            report = verifier.verify_integration("gstack")

            assert report.integration_id == "gstack"
            assert not report.installed

    def test_verify_all_empty(self) -> None:
        """Test verifying all integrations with none installed."""
        verifier = IntegrationVerifier()

        with patch.object(
            verifier._manager,
            'list_integrations',
            return_value=[],
        ):
            reports = verifier.verify_all()
            assert isinstance(reports, dict)
            assert len(reports) == 0

    def test_verify_all_with_integrations(self) -> None:
        """Test verifying all integrations."""
        verifier = IntegrationVerifier()

        mock_integration = MagicMock()
        mock_integration.name = "gstack"
        mock_integration.status = IntegrationStatus.INSTALLED
        mock_integration.path = "/tmp/test"

        with patch.object(
            verifier._manager,
            'list_integrations',
            return_value=[mock_integration],
        ):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.is_dir", return_value=True):
                    reports = verifier.verify_all()

                    assert "gstack" in reports
                    assert isinstance(reports["gstack"], IntegrationReport)

    def test_get_quick_check_not_found(self) -> None:
        """Test quick check for non-existent integration."""
        verifier = IntegrationVerifier()

        with patch.object(
            verifier._manager,
            'list_integrations',
            return_value=[],
        ):
            result = verifier.get_quick_check("nonexistent")

            assert result["integration_id"] == "nonexistent"
            assert not result["installed"]
            assert not result["functional"]
            assert result["status"] == "not_found"

    def test_get_quick_check_not_installed(self) -> None:
        """Test quick check for not installed integration."""
        verifier = IntegrationVerifier()

        mock_integration = MagicMock()
        mock_integration.name = "gstack"
        mock_integration.status = IntegrationStatus.NOT_INSTALLED
        mock_integration.path = "/tmp/test"

        with patch.object(
            verifier._manager,
            'list_integrations',
            return_value=[mock_integration],
        ):
            result = verifier.get_quick_check("gstack")

            assert result["integration_id"] == "gstack"
            assert not result["installed"]
            assert not result["functional"]
            assert result["status"] == "not_installed"

    def test_get_quick_check_installed(self) -> None:
        """Test quick check for installed integration."""
        verifier = IntegrationVerifier()

        mock_integration = MagicMock()
        mock_integration.name = "gstack"
        mock_integration.status = IntegrationStatus.INSTALLED
        mock_integration.path = "/tmp/test"

        # Mock skills directory
        mock_skills_dir = MagicMock()
        mock_skills_dir.exists.return_value = True
        mock_skills_dir.iterdir.return_value = []

        with patch.object(
            verifier._manager,
            'list_integrations',
            return_value=[mock_integration],
        ):
            with patch("pathlib.Path.__truediv__", return_value=mock_skills_dir):
                with patch("pathlib.Path.glob", return_value=[]):
                    result = verifier.get_quick_check("gstack")

                    assert result["integration_id"] == "gstack"
                    assert result["installed"]
                    # May or may not be functional depending on skills

    def test_check_installation_exists_pass(self) -> None:
        """Test installation exists check passes."""
        verifier = IntegrationVerifier()

        mock_integration = MagicMock()
        mock_integration.path = "/tmp/test"
        mock_integration.name = "test"

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_dir", return_value=True):
                result = verifier._check_installation_exists(mock_integration)

                assert result.status == VerificationStatus.PASSED
                assert "exists" in result.message.lower()

    def test_check_installation_exists_not_exists(self) -> None:
        """Test installation exists check fails."""
        verifier = IntegrationVerifier()

        mock_integration = MagicMock()
        mock_integration.path = "/tmp/nonexistent"
        mock_integration.name = "test"

        with patch("pathlib.Path.exists", return_value=False):
            result = verifier._check_installation_exists(mock_integration)

            assert result.status == VerificationStatus.FAILED
            assert "does not exist" in result.message.lower()
            assert len(result.suggestions) > 0

    def test_check_installation_exists_not_dir(self) -> None:
        """Test installation exists check fails when not a directory."""
        verifier = IntegrationVerifier()

        mock_integration = MagicMock()
        mock_integration.path = "/tmp/test_file"
        mock_integration.name = "test"

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_dir", return_value=False):
                result = verifier._check_installation_exists(mock_integration)

                assert result.status == VerificationStatus.FAILED
                assert "not a directory" in result.message.lower()

    def test_determine_overall_status_all_passed(self) -> None:
        """Test overall status with all passed."""
        verifier = IntegrationVerifier()

        results = [
            VerificationResult(
                check_name="check1",
                status=VerificationStatus.PASSED,
                message="Passed",
                details={},
                suggestions=[],
            ),
            VerificationResult(
                check_name="check2",
                status=VerificationStatus.PASSED,
                message="Passed",
                details={},
                suggestions=[],
            ),
        ]

        status = verifier._determine_overall_status(results)
        assert status == VerificationStatus.PASSED

    def test_determine_overall_status_with_failed(self) -> None:
        """Test overall status with failed check."""
        verifier = IntegrationVerifier()

        results = [
            VerificationResult(
                check_name="check1",
                status=VerificationStatus.PASSED,
                message="Passed",
                details={},
                suggestions=[],
            ),
            VerificationResult(
                check_name="check2",
                status=VerificationStatus.FAILED,
                message="Failed",
                details={},
                suggestions=[],
            ),
        ]

        status = verifier._determine_overall_status(results)
        assert status == VerificationStatus.FAILED

    def test_determine_overall_status_with_warning(self) -> None:
        """Test overall status with warning."""
        verifier = IntegrationVerifier()

        results = [
            VerificationResult(
                check_name="check1",
                status=VerificationStatus.PASSED,
                message="Passed",
                details={},
                suggestions=[],
            ),
            VerificationResult(
                check_name="check2",
                status=VerificationStatus.WARNING,
                message="Warning",
                details={},
                suggestions=[],
            ),
        ]

        status = verifier._determine_overall_status(results)
        assert status == VerificationStatus.WARNING

    def test_determine_overall_status_empty(self) -> None:
        """Test overall status with no results."""
        verifier = IntegrationVerifier()

        status = verifier._determine_overall_status([])
        assert status == VerificationStatus.SKIPPED
