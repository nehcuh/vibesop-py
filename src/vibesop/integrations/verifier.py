"""Integration verification system.

This module provides verification capabilities for installed
integrations to ensure they are correctly set up and functional.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from vibesop.integrations import IntegrationManager, IntegrationInfo, IntegrationStatus


class VerificationStatus(Enum):
    """Verification status.

    Attributes:
        PASSED: Verification passed
        FAILED: Verification failed
        WARNING: Verification passed with warnings
        SKIPPED: Verification skipped
    """
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class VerificationResult:
    """Result of a verification check.

    Attributes:
        check_name: Name of the verification check
        status: Verification status
        message: Result message
        details: Additional details
        suggestions: Suggestions for fixing failures
    """
    check_name: str
    status: VerificationStatus
    message: str
    details: Dict[str, Any]
    suggestions: List[str]


@dataclass
class IntegrationReport:
    """Complete verification report for an integration.

    Attributes:
        integration_id: Integration identifier
        overall_status: Overall verification status
        results: List of verification results
        installed: Whether integration is installed
        functional: Whether integration is functional
        errors: List of error messages
    """
    integration_id: str
    overall_status: VerificationStatus
    results: List[VerificationResult]
    installed: bool
    functional: bool
    errors: List[str]


class IntegrationVerifier:
    """Verify integration installations.

    Performs comprehensive checks on installed integrations
    to ensure they are correctly set up and functional.

    Example:
        >>> verifier = IntegrationVerifier()
        >>> report = verifier.verify_integration("gstack")
        >>> if report.functional:
        ...     print("Integration is working correctly")
    """

    # Verification checks for each integration
    VERIFICATION_CHECKS = {
        "gstack": {
            "checks": [
                "installation_exists",
                "skills_present",
                "config_valid",
                "dependencies_met",
            ],
            "required_skills": [
                "office-hours",
                "plan-eng-review",
                "review",
                "qa",
                "ship",
            ],
        },
        "superpowers": {
            "checks": [
                "installation_exists",
                "skills_present",
                "config_valid",
            ],
            "required_skills": [
                "tdd",
                "brainstorm",
                "refactor",
                "debug",
                "review",
            ],
        },
    }

    def __init__(self) -> None:
        """Initialize the integration verifier."""
        self._manager = IntegrationManager()

    def verify_integration(
        self,
        integration_id: str,
        platform: str = "claude-code",
    ) -> IntegrationReport:
        """Verify a single integration.

        Args:
            integration_id: Integration to verify
            platform: Target platform

        Returns:
            IntegrationReport with verification results
        """
        results = []
        errors = []

        # Get integration info
        integrations = self._manager.list_integrations()
        integration = next(
            (i for i in integrations if i.name == integration_id),
            None,
        )

        if integration is None:
            return IntegrationReport(
                integration_id=integration_id,
                overall_status=VerificationStatus.FAILED,
                results=[],
                installed=False,
                functional=False,
                errors=[f"Integration {integration_id} not found"],
            )

        installed = integration.status == IntegrationStatus.INSTALLED

        # Get verification checks for this integration
        checks = self.VERIFICATION_CHECKS.get(
            integration_id,
            {}).get("checks", ["installation_exists"])

        # Run each check
        for check_name in checks:
            try:
                result = self._run_check(
                    check_name,
                    integration_id,
                    platform,
                    integration,
                )
                results.append(result)

                if result.status == VerificationStatus.FAILED:
                    errors.append(f"{check_name}: {result.message}")

            except Exception as e:
                errors.append(f"{check_name}: Verification failed with error: {e}")
                results.append(VerificationResult(
                    check_name=check_name,
                    status=VerificationStatus.FAILED,
                    message=f"Check raised exception: {e}",
                    details={},
                    suggestions=[],
                ))

        # Determine overall status
        overall_status = self._determine_overall_status(results)
        functional = overall_status in [VerificationStatus.PASSED, VerificationStatus.WARNING]

        return IntegrationReport(
            integration_id=integration_id,
            overall_status=overall_status,
            results=results,
            installed=installed,
            functional=functional,
            errors=errors,
        )

    def verify_all(
        self,
        platform: str = "claude-code",
    ) -> Dict[str, IntegrationReport]:
        """Verify all installed integrations.

        Args:
            platform: Target platform

        Returns:
            Dictionary mapping integration IDs to reports
        """
        reports = {}

        integrations = self._manager.list_integrations()
        for integration in integrations:
            report = self.verify_integration(integration.name, platform)
            reports[integration.name] = report

        return reports

    def get_quick_check(
        self,
        integration_id: str,
    ) -> Dict[str, Any]:
        """Perform a quick check on an integration.

        Args:
            integration_id: Integration to check

        Returns:
            Quick check result dictionary
        """
        integrations = self._manager.list_integrations()
        integration = next(
            (i for i in integrations if i.name == integration_id),
            None,
        )

        if integration is None:
            return {
                "integration_id": integration_id,
                "installed": False,
                "functional": False,
                "status": "not_found",
            }

        installed = integration.status == IntegrationStatus.INSTALLED

        # Quick functional check
        if not installed:
            return {
                "integration_id": integration_id,
                "installed": False,
                "functional": False,
                "status": "not_installed",
            }

        # Check if skills directory exists
        skills_dir = Path(integration.path) / "skills"
        skills_exist = skills_dir.exists() and any(skills_dir.iterdir())

        return {
            "integration_id": integration_id,
            "installed": True,
            "functional": skills_exist,
            "status": "functional" if skills_exist else "no_skills",
            "skills_count": len(list(skills_dir.glob("*.md"))) if skills_exist else 0,
        }

    def _run_check(
        self,
        check_name: str,
        integration_id: str,
        platform: str,
        integration: IntegrationInfo,
    ) -> VerificationResult:
        """Run a single verification check.

        Args:
            check_name: Name of the check to run
            integration_id: Integration being verified
            platform: Target platform
            integration: Integration info

        Returns:
            VerificationResult
        """
        if check_name == "installation_exists":
            return self._check_installation_exists(integration)
        elif check_name == "skills_present":
            return self._check_skills_present(integration_id, integration)
        elif check_name == "config_valid":
            return self._check_config_valid(integration_id, platform)
        elif check_name == "dependencies_met":
            return self._check_dependencies_met(integration_id)
        else:
            return VerificationResult(
                check_name=check_name,
                status=VerificationStatus.SKIPPED,
                message="Unknown check",
                details={},
                suggestions=[],
            )

    def _check_installation_exists(self, integration: IntegrationInfo) -> VerificationResult:
        """Check if installation directory exists.

        Args:
            integration: Integration info

        Returns:
            VerificationResult
        """
        path = Path(integration.path)

        if not path.exists():
            return VerificationResult(
                check_name="installation_exists",
                status=VerificationStatus.FAILED,
                message="Installation directory does not exist",
                details={"path": str(path)},
                suggestions=[f"Install the integration: vibe install {integration.name}"],
            )

        if not path.is_dir():
            return VerificationResult(
                check_name="installation_exists",
                status=VerificationStatus.FAILED,
                message="Installation path is not a directory",
                details={"path": str(path)},
                suggestions=[f"Reinstall the integration: vibe install {integration.name}"],
            )

        return VerificationResult(
            check_name="installation_exists",
            status=VerificationStatus.PASSED,
            message="Installation directory exists",
            details={"path": str(path)},
            suggestions=[],
        )

    def _check_skills_present(
        self,
        integration_id: str,
        integration: IntegrationInfo,
    ) -> VerificationResult:
        """Check if required skills are present.

        Args:
            integration_id: Integration ID
            integration: Integration info

        Returns:
            VerificationResult
        """
        required_skills = self.VERIFICATION_CHECKS.get(
            integration_id,
            {}).get("required_skills", [])

        if not required_skills:
            return VerificationResult(
                check_name="skills_present",
                status=VerificationStatus.SKIPPED,
                message="No required skills defined",
                details={},
                suggestions=[],
            )

        skills_dir = Path(integration.path) / "skills"
        if not skills_dir.exists():
            return VerificationResult(
                check_name="skills_present",
                status=VerificationStatus.FAILED,
                message="Skills directory does not exist",
                details={"skills_dir": str(skills_dir)},
                suggestions=[
                    f"Reinstall {integration_id} to restore skills directory",
                    f"Check if {integration_id} installation is complete",
                ],
            )

        # Check for required skill files
        found_skills = []
        missing_skills = []

        for skill in required_skills:
            skill_file = skills_dir / f"{skill}.md"
            if skill_file.exists():
                found_skills.append(skill)
            else:
                missing_skills.append(skill)

        if missing_skills:
            return VerificationResult(
                check_name="skills_present",
                status=VerificationStatus.WARNING,
                message=f"Missing {len(missing_skills)} required skills",
                details={
                    "found": found_skills,
                    "missing": missing_skills,
                },
                suggestions=[
                    f"Update {integration_id} to get missing skills",
                    "Some functionality may be limited",
                ],
            )

        return VerificationResult(
            check_name="skills_present",
            status=VerificationStatus.PASSED,
            message=f"All {len(found_skills)} required skills present",
            details={"skills": found_skills},
            suggestions=[],
        )

    def _check_config_valid(
        self,
        integration_id: str,
        platform: str,
    ) -> VerificationResult:
        """Check if integration configuration is valid.

        Args:
            integration_id: Integration ID
            platform: Target platform

        Returns:
            VerificationResult
        """
        # For now, just check if config file exists
        # In a full implementation, this would validate the config structure

        config_paths = {
            "claude-code": [
                Path(".claude/skills"),
                Path(".vibe/skills"),
            ],
            "opencode": [
                Path(".config/skills"),
            ],
        }

        checked_paths = []
        for config_path in config_paths.get(platform, []):
            if config_path.exists():
                checked_paths.append(str(config_path))

        if checked_paths:
            return VerificationResult(
                check_name="config_valid",
                status=VerificationStatus.PASSED,
                message="Configuration paths found",
                details={"paths": checked_paths},
                suggestions=[],
            )

        return VerificationResult(
            check_name="config_valid",
            status=VerificationStatus.WARNING,
            message="No standard configuration paths found",
            details={"platform": platform},
            suggestions=[
                "Integration may work but configuration paths are non-standard",
                f"Ensure {integration_id} is properly configured for {platform}",
            ],
        )

    def _check_dependencies_met(
        self,
        integration_id: str,
    ) -> VerificationResult:
        """Check if integration dependencies are met.

        Args:
            integration_id: Integration ID

        Returns:
            VerificationResult
        """
        # For now, just check for common dependencies
        # In a full implementation, this would check specific requirements

        import shutil

        dependencies = []

        # Check for git (most integrations need it)
        git_available = shutil.which("git") is not None
        dependencies.append({
            "name": "git",
            "installed": git_available,
            "required": True,
        })

        missing = [d for d in dependencies if not d["installed"] and d["required"]]

        if missing:
            return VerificationResult(
                check_name="dependencies_met",
                status=VerificationStatus.FAILED,
                message=f"Missing required dependencies: {', '.join(d['name'] for d in missing)}",
                details={"dependencies": dependencies},
                suggestions=[
                    f"Install missing dependencies: {' '.join(d['name'] for d in missing)}",
                ],
            )

        return VerificationResult(
            check_name="dependencies_met",
            status=VerificationStatus.PASSED,
            message="All dependencies satisfied",
            details={"dependencies": dependencies},
            suggestions=[],
        )

    def _determine_overall_status(self, results: List[VerificationResult]) -> VerificationStatus:
        """Determine overall status from verification results.

        Args:
            results: List of verification results

        Returns:
            Overall VerificationStatus
        """
        if not results:
            return VerificationStatus.SKIPPED

        has_failed = any(r.status == VerificationStatus.FAILED for r in results)
        has_warning = any(r.status == VerificationStatus.WARNING for r in results)

        if has_failed:
            return VerificationStatus.FAILED
        elif has_warning:
            return VerificationStatus.WARNING
        else:
            return VerificationStatus.PASSED
