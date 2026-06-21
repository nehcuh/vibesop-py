"""Integration management for VibeSOP."""

from pathlib import Path
from typing import Any

from vibesop.integrations.detector import (
    IntegrationDetector,
    IntegrationInfo,
    IntegrationStatus,
)


class IntegrationManager:
    def __init__(self) -> None:
        self.detector = IntegrationDetector()
        self._cache: list[IntegrationInfo] | None = None

    def list_integrations(self, refresh: bool = False) -> list[IntegrationInfo]:
        if self._cache is None or refresh:
            self._cache = self.detector.detect_all()
        return self._cache

    def get_integration(self, name: str) -> IntegrationInfo | None:
        return next((i for i in self.list_integrations() if i.name == name), None)

    def is_installed(self, name: str) -> bool:
        return self.detector.is_integration_installed(name)

    def get_skills(self, name: str | None = None) -> list[str]:
        if name:
            return self.detector.get_integration_skills(name)
        skills: list[str] = []
        for info in self.list_integrations():
            if info.status == IntegrationStatus.INSTALLED:
                skills.extend(info.skills)
        return skills

    def get_installed_integrations(self) -> list[IntegrationInfo]:
        return [i for i in self.list_integrations() if i.status == IntegrationStatus.INSTALLED]

    def get_compatible_integrations(self) -> list[IntegrationInfo]:
        ok = {IntegrationStatus.INSTALLED, IntegrationStatus.NOT_INSTALLED}
        return [i for i in self.list_integrations() if i.status in ok]

    def get_summary(self) -> dict[str, Any]:
        integrations = self.list_integrations()
        installed = sum(1 for i in integrations if i.status == IntegrationStatus.INSTALLED)
        return {
            "total_integrations": len(integrations),
            "installed_integrations": installed,
            "available_integrations": len(integrations) - installed,
            "total_skills": len(self.get_skills()),
            "integrations": [
                {
                    "name": i.name,
                    "status": i.status.value,
                    "version": i.version,
                    "skill_count": len(i.skills),
                }
                for i in integrations
            ],
        }

    def refresh(self) -> None:
        self._cache = None
        self.list_integrations(refresh=True)

    def check_integration_compatibility(self, name: str) -> dict[str, Any]:
        info = self.get_integration(name)
        if not info:
            return {"compatible": False, "reason": "Integration not found"}
        if info.status == IntegrationStatus.INSTALLED:
            return {
                "compatible": True,
                "reason": "Installed and compatible",
                "version": info.version,
                "path": str(info.path) if info.path else None,
            }
        if info.status == IntegrationStatus.NOT_INSTALLED:
            return {
                "compatible": True,
                "reason": "Not installed but compatible",
                "install_hint": f"Install {name} to use its skills",
            }
        return {"compatible": False, "reason": f"Incompatible: {info.status.value}"}

    def get_integration_path(self, name: str) -> Path | None:
        info = self.get_integration(name)
        return info.path if info and info.status == IntegrationStatus.INSTALLED else None

    def get_integration_registry(self, name: str | None = None) -> dict[str, Any]:
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
        return {
            i.name: {
                "description": i.description,
                "skills": i.skills,
                "installed": i.status == IntegrationStatus.INSTALLED,
            }
            for i in self.list_integrations()
        }
