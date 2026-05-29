"""Integration verification system."""

import shutil
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


_INTEGRATION_CHECKS: ClassVar[dict[str, dict[str, Any]]] = {
    "gstack": {
        "checks": ["installation_exists", "skills_present", "config_valid", "dependencies_met"],
        "required_skills": ["office-hours", "plan-eng-review", "review", "qa", "ship"],
    },
    "superpowers": {
        "checks": ["installation_exists", "skills_present", "config_valid"],
        "required_skills": ["tdd", "brainstorm", "refactor", "debug", "review"],
    },
}

_CONFIG_PATHS: ClassVar[dict[str, list[Path]]] = {
    "claude-code": [Path(".claude/skills"), Path(".vibe/skills")],
    "kimi-cli": [Path(".kimi-code/skills"), Path(".vibe/skills")],
    "opencode": [Path(".config/skills")],
}


def _result(name: str, status: VerificationStatus, msg: str, details: dict[str, Any] | None = None, suggestions: list[str] | None = None) -> VerificationResult:
    return VerificationResult(name, status, msg, details or {}, suggestions or [])


class IntegrationVerifier:
    def __init__(self) -> None:
        self._manager = IntegrationManager()

    def verify_integration(self, integration_id: str, platform: str = "claude-code") -> IntegrationReport:
        integrations = self._manager.list_integrations()
        integration = next((i for i in integrations if i.name == integration_id), None)

        if integration is None:
            return IntegrationReport(integration_id, VerificationStatus.FAILED, [], False, False, [f"Integration {integration_id} not found"])

        results: list[VerificationResult] = []
        errors: list[str] = []
        check_config = _INTEGRATION_CHECKS.get(integration_id, {})
        checks: list[str] = check_config.get("checks", ["installation_exists"])

        for check_name in checks:
            try:
                result = self._run_check(check_name, integration_id, platform, integration)
                results.append(result)
                if result.status == VerificationStatus.FAILED:
                    errors.append(f"{check_name}: {result.message}")
            except (ValueError, KeyError, AttributeError, TypeError, OSError) as e:
                errors.append(f"{check_name}: Verification failed with error: {e}")
                results.append(_result(check_name, VerificationStatus.FAILED, f"Check raised exception: {e}"))

        overall = self._determine_overall_status(results)
        return IntegrationReport(
            integration_id, overall, results,
            integration.status == IntegrationStatus.INSTALLED,
            overall in (VerificationStatus.PASSED, VerificationStatus.WARNING),
            errors,
        )

    def verify_all(self, platform: str = "claude-code") -> dict[str, IntegrationReport]:
        return {i.name: self.verify_integration(i.name, platform) for i in self._manager.list_integrations()}

    def get_quick_check(self, integration_id: str) -> dict[str, Any]:
        integration = next((i for i in self._manager.list_integrations() if i.name == integration_id), None)

        if integration is None:
            return {"integration_id": integration_id, "installed": False, "functional": False, "status": "not_found"}

        installed = integration.status == IntegrationStatus.INSTALLED
        if not installed:
            return {"integration_id": integration_id, "installed": False, "functional": False, "status": "not_installed"}
        if integration.path is None:
            return {"integration_id": integration_id, "installed": True, "functional": False, "status": "no_path"}

        skills_dir = Path(integration.path) / "skills"
        skills_exist = skills_dir.exists() and any(skills_dir.iterdir())
        return {
            "integration_id": integration_id, "installed": True, "functional": skills_exist,
            "status": "functional" if skills_exist else "no_skills",
            "skills_count": len(list(skills_dir.glob("*.md"))) if skills_exist else 0,
        }

    def _run_check(self, name: str, iid: str, platform: str, info: IntegrationInfo) -> VerificationResult:
        dispatch = {
            "installation_exists": lambda: self._check_installation(info),
            "skills_present": lambda: self._check_skills(iid, info),
            "config_valid": lambda: self._check_config(iid, platform),
            "dependencies_met": lambda: self._check_deps(iid),
        }
        handler = dispatch.get(name)
        if handler:
            return handler()
        return _result(name, VerificationStatus.SKIPPED, "Unknown check")

    def _check_installation(self, info: IntegrationInfo) -> VerificationResult:
        if info.path is None:
            return _result("installation_exists", VerificationStatus.FAILED, "Installation path is not set", {"path": None}, [f"vibe install {info.name}"])
        path = Path(info.path)
        if not path.exists():
            return _result("installation_exists", VerificationStatus.FAILED, "Installation directory does not exist", {"path": str(path)}, [f"vibe install {info.name}"])
        if not path.is_dir():
            return _result("installation_exists", VerificationStatus.FAILED, "Installation path is not a directory", {"path": str(path)}, [f"Reinstall: vibe install {info.name}"])
        return _result("installation_exists", VerificationStatus.PASSED, "Installation directory exists", {"path": str(path)})

    def _check_skills(self, iid: str, info: IntegrationInfo) -> VerificationResult:
        cfg = _INTEGRATION_CHECKS.get(iid, {})
        required: list[str] = cfg.get("required_skills", [])
        if not required:
            return _result("skills_present", VerificationStatus.SKIPPED, "No required skills defined")
        if info.path is None:
            return _result("skills_present", VerificationStatus.FAILED, "Integration path is not set", suggestions=[f"vibe install {iid}"])

        ipath = Path(info.path)
        found, missing = [], []
        for skill in required:
            if iid == "gstack":
                skill_file = ipath / skill / "SKILL.md"
            else:
                skill_file = ipath / "skills" / f"{skill}.md"
            (found if skill_file.exists() else missing).append(skill)

        if not found and missing == required:
            return _result("skills_present", VerificationStatus.FAILED, "Skills directory does not exist", {"skills_dir": str(ipath / "skills") if iid != "gstack" else str(ipath)})
        if missing:
            return _result("skills_present", VerificationStatus.WARNING, f"Missing {len(missing)} required skills", {"found": found, "missing": missing}, [f"Update {iid} to get missing skills"])
        return _result("skills_present", VerificationStatus.PASSED, f"All {len(found)} required skills present", {"skills": found})

    def _check_config(self, iid: str, platform: str) -> VerificationResult:
        checked = [str(p) for p in _CONFIG_PATHS.get(platform, []) if p.exists()]
        if checked:
            return _result("config_valid", VerificationStatus.PASSED, "Configuration paths found", {"paths": checked})
        return _result("config_valid", VerificationStatus.WARNING, "No standard configuration paths found", {"platform": platform}, [f"Ensure {iid} is properly configured for {platform}"])

    def _check_deps(self, _iid: str) -> VerificationResult:
        if shutil.which("git") is None:
            return _result("dependencies_met", VerificationStatus.FAILED, "Missing required dependencies: git", {"dependencies": [{"name": "git", "installed": False, "required": True}]}, ["Install git"])
        return _result("dependencies_met", VerificationStatus.PASSED, "All dependencies satisfied", {"dependencies": [{"name": "git", "installed": True, "required": True}]})

    @staticmethod
    def _determine_overall_status(results: list[VerificationResult]) -> VerificationStatus:
        if not results:
            return VerificationStatus.SKIPPED
        if any(r.status == VerificationStatus.FAILED for r in results):
            return VerificationStatus.FAILED
        if any(r.status == VerificationStatus.WARNING for r in results):
            return VerificationStatus.WARNING
        return VerificationStatus.PASSED
