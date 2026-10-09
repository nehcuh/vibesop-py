"""Skill installer for individual skill installation."""

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from vibesop.security import PathSafety
from vibesop.security.exceptions import SecurityError

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
        self._path_safety = PathSafety()

    def _validate_skill_id(self, skill_id: str) -> None:
        """Validate a logical skill id before any filesystem mutation.

        Per-segment validation keeps legal pack-style namespace ids
        (``demo-scope/demo``) working; a blanket ``validate_filename`` on the
        whole id would reject those. Rejects empty ids, absolute paths,
        empty segments, ``.``/``..`` segments, and backslashes. Each segment
        additionally goes through the project's existing cross-platform
        filename validation so Windows-illegal special characters
        (``<>|*?`` etc.) are rejected per segment while the pack/skill
        namespace shape is preserved.

        Pure validation: no directories are created and no path is joined
        here, so it is safe to call before dependency handling (R3/B1
        early-reject ordering).
        """
        if not skill_id or not skill_id.strip():
            raise ValueError("Skill id must not be empty")
        if "\\" in skill_id:
            raise ValueError(f"Skill id must not contain backslashes: {skill_id!r}")
        if Path(skill_id).is_absolute() or skill_id.startswith(("~", "/")):
            raise ValueError(f"Skill id must be a relative namespace path: {skill_id!r}")
        for segment in skill_id.split("/"):
            if not segment:
                raise ValueError(f"Skill id contains an empty namespace segment: {skill_id!r}")
            if segment in (".", ".."):
                raise ValueError(f"Skill id segment must not be '{segment}': {skill_id!r}")
            try:
                self._path_safety.validate_filename(segment)
            except ValueError as e:
                msg = f"Skill id segment contains illegal characters: {skill_id!r} ({e})"
                raise ValueError(msg) from e

    @staticmethod
    def _normalize_project_root(project_path: Path) -> Path:
        """Normalize the project root once, to a consistent absolute path.

        ``ensure_safe_output_path`` resolves its ``base_dir`` but joins a
        *relative* path argument onto that resolved base — passing a
        relative project root therefore used to double-join (``project``
        became ``<cwd>/project/project/...``) and split the install dir from
        the registry. Normalizing at the public entry points keeps exactly
        one join and one absolute trusted root for target, registry, and
        marker alike (R3/B1).
        """
        return Path(project_path).expanduser().resolve()

    def _validated_skill_dir(
        self,
        skill_id: str,
        project_path: Path,
        create_parents: bool = False,
    ) -> Path:
        """Validate a logical skill id and return its target inside the project.

        ``ensure_safe_output_path`` anchors the resolved containment check at
        the project root and refuses symlinks anywhere in the target chain
        (an intermediate namespace segment symlinked outside the project
        would otherwise let the copy land outside the install root).
        """
        self._validate_skill_id(skill_id)
        root = self._normalize_project_root(project_path)
        target_dir = root / self._skills_dir / skill_id
        return self._path_safety.ensure_safe_output_path(
            target_dir,
            root,
            create_parents=create_parents,
        )

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

            project_path = self._normalize_project_root(project_path)

            manifest = self._load_skill_manifest(skill_path)
            result["skill_id"] = manifest.id

            # R3/B1: reject a malicious id before any dependency handling,
            # and without creating directories — the pure validator runs
            # before the first filesystem mutation of this install.
            self._validate_skill_id(manifest.id)

            dep_result: dict[str, Any] = self._install_dependencies(
                manifest.dependencies, project_path
            )
            if not dep_result["success"]:
                result["errors"].extend(dep_result["errors"])
                return result

            result["dependencies_installed"] = dep_result["installed"]

            target_dir = self._validated_skill_dir(manifest.id, project_path, create_parents=True)
            if target_dir.exists() and not force:
                result["warnings"].append(f"Skill already installed at {target_dir}")
                result["success"] = True
                result["installed_path"] = str(target_dir)
                return result

            self._copy_skill_files(skill_path, target_dir)
            self._update_registry(manifest, project_path)

            # gate37 L1: advisory lint rides warnings[] — never blocks,
            # never feeds the security audit (修订 A mounting contract).
            skill_md = skill_path / "SKILL.md"
            if skill_md.exists():
                from vibesop.core.skills.skill_lint import lint_skill

                for finding in lint_skill(skill_md):
                    result["warnings"].append(f"lint: {finding}")

            result["success"] = True
            result["installed_path"] = str(target_dir)

        except Exception as e:
            result["errors"].append(f"Installation failed: {e!s}")

        return result

    def uninstall_skill(self, skill_id: str, project_path: Path) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "skill_id": skill_id,
            "removed_files": [],
            "errors": [],
        }

        try:
            project_path = self._normalize_project_root(project_path)
            skill_dir = self._validated_skill_dir(skill_id, project_path)

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
        project_path = self._normalize_project_root(project_path)
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

    def verify_skill(self, skill_id: str, project_path: Path) -> dict[str, Any]:
        result: dict[str, Any] = {
            "skill_id": skill_id,
            "installed": False,
            "files_present": False,
            "in_registry": False,
            "dependencies_met": True,
            "errors": [],
        }

        try:
            project_path = self._normalize_project_root(project_path)
            skill_dir = self._validated_skill_dir(skill_id, project_path)
        except (ValueError, SecurityError) as e:
            result["errors"].append(f"Invalid skill id: {e}")
            return result

        if not skill_dir.exists():
            result["errors"].append(f"Skill directory not found: {skill_dir}")
            return result

        result["installed"] = True
        result["files_present"] = (skill_dir / "SKILL.md").exists()

        registry_path = project_path / ".vibe" / "skills" / "registry.yaml"
        result["in_registry"] = registry_path.exists() and skill_id in registry_path.read_text(
            encoding="utf-8"
        )

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

    def _install_dependencies(self, dependencies: list[str], project_path: Path) -> dict[str, Any]:
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
            registry_path.write_text(
                f"# Skill Registry\nskills:\n  - {manifest.id}\n", encoding="utf-8"
            )
        else:
            content = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
            skills = content.get("skills", [])
            if manifest.id not in skills:
                skills.append(manifest.id)
                content["skills"] = skills
                registry_path.write_text(
                    yaml.safe_dump(content, default_flow_style=False, allow_unicode=True),
                    encoding="utf-8",
                )

        marker = project_path / ".vibe" / ".skills_reload"
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("", encoding="utf-8")
        except OSError:
            pass

    def _remove_from_registry(self, skill_id: str, project_path: Path) -> None:
        registry_path = project_path / ".vibe" / "skills" / "registry.yaml"
        if registry_path.exists():
            content = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
            skills = content.get("skills", [])
            if skill_id in skills:
                skills.remove(skill_id)
                content["skills"] = skills
                registry_path.write_text(
                    yaml.safe_dump(content, default_flow_style=False, allow_unicode=True),
                    encoding="utf-8",
                )
