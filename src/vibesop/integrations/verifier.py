"""Integration verification system.

This module provides verification capabilities for installed
integrations to ensure they are correctly set up and functional.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar

from vibesop.integrations import IntegrationInfo, IntegrationManager, IntegrationStatus


class VerificationStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class VerificationResult:
    check_name: str
    status: VerificationStatus
    message: str
    details: dict[str, Any]
    suggestions: list[str]


@dataclass
class IntegrationReport:
    integration_id: str
    overall_status: VerificationStatus
    results: list[VerificationResult]
    installed: bool
    functional: bool
    errors: list[str]


class IntegrationVerifier:
    VERIFICATION_CHECKS: ClassVar[dict[str, dict[str, Any]]] = {
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
        self._manager = IntegrationManager()

    def verify_integration(
        self,
        integration_id: str,
        platform: str = "claude-code",
    ) -> IntegrationReport:
        results: list[VerificationResult] = []
        errors: list[str] = []

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

        check_config = self.VERIFICATION_CHECKS.get(integration_id, {})
        checks: list[str] = check_config.get("checks", ["installation_exists"])

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

            except (ValueError, KeyError, AttributeError, TypeError, OSError) as e:
                errors.append(f"{check_name}: Verification failed with error: {e}")
                results.append(
                    VerificationResult(
                        check_name=check_name,
                        status=VerificationStatus.FAILED,
                        message=f"Check raised exception: {e}",
                        details={},
                        suggestions=[],
                    )
                )

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
    ) -> dict[str, IntegrationReport]:
        reports: dict[str, IntegrationReport] = {}

        integrations = self._manager.list_integrations()
        for integration in integrations:
            report = self.verify_integration(integration.name, platform)
            reports[integration.name] = report

        return reports

    def get_quick_check(
        self,
        integration_id: str,
    ) -> dict[str, Any]:
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

        if not installed:
            return {
                "integration_id": integration_id,
                "installed": False,
                "functional": False,
                "status": "not_installed",
            }

        if integration.path is None:
            return {
                "integration_id": integration_id,
                "installed": True,
                "functional": False,
                "status": "no_path",
            }

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
        if integration.path is None:
            return VerificationResult(
                check_name="installation_exists",
                status=VerificationStatus.FAILED,
                message="Installation path is not set",
                details={"path": None},
                suggestions=[f"Install the integration: vibe install {integration.name}"],
            )

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
        check_cfg = self.VERIFICATION_CHECKS.get(integration_id, {})
        required_skills: list[str] = check_cfg.get("required_skills", [])

        if not required_skills:
            return VerificationResult(
                check_name="skills_present",
                status=VerificationStatus.SKIPPED,
                message="No required skills defined",
                details={},
                suggestions=[],
            )

        if integration.path is None:
            return VerificationResult(
                check_name="skills_present",
                status=VerificationStatus.FAILED,
                message="Integration path is not set",
                details={},
                suggestions=[f"Install the integration: vibe install {integration_id}"],
            )

        integration_path = Path(integration.path)

        if integration_id == "gstack":
            skills_found: list[str] = []
            skills_missing: list[str] = []

            for skill in required_skills:
                skill_dir = integration_path / skill
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    skills_found.append(skill)
                else:
                    skills_missing.append(skill)

            if skills_missing:
                return VerificationResult(
                    check_name="skills_present",
                    status=VerificationStatus.WARNING,
                    message=f"Missing {len(skills_missing)} required skills",
                    details={
                        "found": skills_found,
                        "missing": skills_missing,
                    },
                    suggestions=[
                        f"Update {integration_id} to get missing skills",
                        "Some functionality may be limited",
                    ],
                )

            return VerificationResult(
                check_name="skills_present",
                status=VerificationStatus.PASSED,
                message=f"All {len(skills_found)} required skills present",
                details={"skills": skills_found},
                suggestions=[],
            )

        skills_dir = integration_path / "skills"
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

        found_skills: list[str] = []
        missing_skills: list[str] = []

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
        config_paths: dict[str, list[Path]] = {
            "claude-code": [
                Path(".claude/skills"),
                Path(".vibe/skills"),
            ],
            "opencode": [
                Path(".config/skills"),
            ],
        }

        checked_paths: list[str] = []
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
        _integration_id: str,
    ) -> VerificationResult:
        import shutil

        dependencies: list[dict[str, Any]] = []

        git_available = shutil.which("git") is not None
        dependencies.append(
            {
                "name": "git",
                "installed": git_available,
                "required": True,
            }
        )

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

    def _determine_overall_status(self, results: list[VerificationResult]) -> VerificationStatus:
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
