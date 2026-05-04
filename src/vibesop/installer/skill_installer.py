"""Skill installer for individual skill installation."""

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SkillManifest:
    id: str
    name: str
    description: str
    version: str
    author: str
    dependencies: list[str]
    trigger_when: str

    @classmethod
    def from_file(cls, path: Path) -> "SkillManifest":
        """Load skill manifest from SKILL.md using unified parser."""
        from vibesop.core.skills.parser import parse_skill_md

        id_ = path.parent.name
        name = id_.replace("-", " ").title()
        description = ""
        version = "1.0.0"
        author = "Unknown"
        dependencies: list[str] = []
        trigger_when = "Manual"

        meta = parse_skill_md(path)
        if meta:
            id_ = meta.id or id_
            name = meta.name or name
            description = meta.description or description
            version = meta.version or version
            author = meta.author or author
            trigger_when = meta.trigger_when or trigger_when

        return cls(
            id=id_,
            name=name,
            description=description,
            version=version,
            author=author,
            dependencies=dependencies,
            trigger_when=trigger_when,
        )


class SkillInstaller:
    def __init__(self) -> None:
        self._skills_dir = Path(".vibe/skills")

    def install_skill(
        self,
        skill_path: Path,
        project_path: Path,
        force: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "skill_id": skill_path.name,
            "installed_path": "",
            "dependencies_installed": [],
            "errors": [],
            "warnings": [],
        }

        try:
            if not skill_path.exists():
                result["errors"].append(f"Skill path not found: {skill_path}")
                return result

            manifest = self._load_skill_manifest(skill_path)
            result["skill_id"] = manifest.id

            dep_result: dict[str, Any] = self._install_dependencies(
                manifest.dependencies, project_path
            )
            if not dep_result["success"]:
                result["errors"].extend(dep_result["errors"])
                return result

            result["dependencies_installed"] = dep_result["installed"]

            target_dir = project_path / self._skills_dir / manifest.id
            if target_dir.exists() and not force:
                result["warnings"].append(f"Skill already installed at {target_dir}")
                result["success"] = True
                result["installed_path"] = str(target_dir)
                return result

            self._copy_skill_files(skill_path, target_dir)
            self._update_registry(manifest, project_path)

            result["success"] = True
            result["installed_path"] = str(target_dir)

        except Exception as e:
            result["errors"].append(f"Installation failed: {e!s}")

        return result

    def uninstall_skill(
        self, skill_id: str, project_path: Path
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "skill_id": skill_id,
            "removed_files": [],
            "errors": [],
        }

        try:
            skill_dir = project_path / self._skills_dir / skill_id

            if not skill_dir.exists():
                result["errors"].append(f"Skill not found: {skill_id}")
                return result

            shutil.rmtree(skill_dir)
            result["removed_files"].append(str(skill_dir))
            self._remove_from_registry(skill_id, project_path)
            result["success"] = True

        except Exception as e:
            result["errors"].append(f"Uninstallation failed: {e}")

        return result

    def list_skills(self, project_path: Path) -> list[dict[str, Any]]:
        skills: list[dict[str, Any]] = []
        skills_dir = project_path / self._skills_dir

        if not skills_dir.exists():
            return skills

        for skill_path in skills_dir.iterdir():
            if skill_path.is_dir():
                try:
                    manifest = self._load_skill_manifest(skill_path)
                    skills.append(
                        {
                            "id": manifest.id,
                            "name": manifest.name,
                            "description": manifest.description,
                            "version": manifest.version,
                            "path": str(skill_path),
                        }
                    )
                except Exception as e:
                    logger.debug(f"Failed to load skill manifest from {skill_path}: {e}")

        return skills

    def verify_skill(
        self, skill_id: str, project_path: Path
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "skill_id": skill_id,
            "installed": False,
            "files_present": False,
            "in_registry": False,
            "dependencies_met": True,
            "errors": [],
        }

        skill_dir = project_path / self._skills_dir / skill_id
        if not skill_dir.exists():
            result["errors"].append(f"Skill directory not found: {skill_dir}")
            return result

        result["installed"] = True
        result["files_present"] = (skill_dir / "SKILL.md").exists()

        registry_path = project_path / ".vibe" / "skills" / "registry.yaml"
        result["in_registry"] = registry_path.exists() and skill_id in registry_path.read_text()

        return result

    def _load_skill_manifest(self, skill_path: Path) -> SkillManifest:
        skill_md = skill_path / "SKILL.md"
        if skill_md.exists():
            return SkillManifest.from_file(skill_md)

        return SkillManifest(
            id=skill_path.name,
            name=skill_path.name.replace("-", " ").title(),
            description="No description",
            version="1.0.0",
            author="Unknown",
            dependencies=[],
            trigger_when="Manual",
        )

    def _install_dependencies(
        self, dependencies: list[str], project_path: Path
    ) -> dict[str, Any]:
        result: dict[str, Any] = {"success": True, "installed": [], "errors": []}

        for dep_id in dependencies:
            dep_verify = self.verify_skill(dep_id, project_path)
            if not dep_verify["installed"]:
                result["errors"].append(f"Dependency not installed: {dep_id}")
                result["success"] = False
            else:
                result["installed"].append(dep_id)

        return result

    def _copy_skill_files(self, src: Path, dst: Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))

    def _update_registry(self, manifest: SkillManifest, project_path: Path) -> None:
        registry_path = project_path / ".vibe" / "skills" / "registry.yaml"
        registry_path.parent.mkdir(parents=True, exist_ok=True)

        if not registry_path.exists():
            registry_path.write_text(f"# Skill Registry\nskills:\n  - {manifest.id}\n")
        else:
            content = registry_path.read_text()
            if manifest.id not in content:
                with registry_path.open("a") as f:
                    f.write(f"  - {manifest.id}\n")

        marker = project_path / ".vibe" / ".skills_reload"
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("")
        except OSError:
            pass

    def _remove_from_registry(self, skill_id: str, project_path: Path) -> None:
        registry_path = project_path / ".vibe" / "skills" / "registry.yaml"
        if registry_path.exists():
            content = registry_path.read_text()
            filtered_lines = [l for l in content.split("\n") if skill_id not in l]
            registry_path.write_text("\n".join(filtered_lines))
