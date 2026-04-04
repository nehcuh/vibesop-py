"""Skill installer for individual skill installation.

This module handles installation of individual skills
to projects, including dependency management and registry updates.
"""

import shutil
from pathlib import Path
from typing import Any, Dict, List
from dataclasses import dataclass


@dataclass
class SkillManifest:
    """Skill manifest data.

    Attributes:
        id: Skill identifier
        name: Skill name
        description: Skill description
        version: Skill version
        author: Skill author
        dependencies: List of skill dependencies
        trigger_when: Trigger conditions
    """

    id: str
    name: str
    description: str
    version: str
    author: str
    dependencies: List[str]
    trigger_when: str

    @classmethod
    def from_file(cls, path: Path) -> "SkillManifest":
        """Load skill manifest from file.

        Args:
            path: Path to SKILL.md file

        Returns:
            SkillManifest instance
        """
        # Parse SKILL.md format
        content = path.read_text()

        # Extract metadata from frontmatter or headers
        id_ = path.parent.name
        name = id_.replace("-", " ").title()
        description = ""
        version = "1.0.0"
        author = "Unknown"
        dependencies = []
        trigger_when = "Manual"

        # Simple parsing (can be enhanced)
        for line in content.split("\n"):
            if line.startswith("# Description:"):
                description = line.replace("# Description:", "").strip()
            elif line.startswith("# Version:"):
                version = line.replace("# Version:", "").strip()
            elif line.startswith("# Author:"):
                author = line.replace("# Author:", "").strip()
            elif line.startswith("# Depends:"):
                deps = line.replace("# Depends:", "").strip()
                dependencies = [d.strip() for d in deps.split(",") if d.strip()]
            elif line.startswith("# Trigger:"):
                trigger_when = line.replace("# Trigger:", "").strip()

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
    """Installer for individual skills.

    Installs skills to projects with dependency management
    and registry updates.

    Example:
        >>> installer = SkillInstaller()
        >>> result = installer.install_skill(
        ...     skill_path=Path("skills/my-skill"),
        ...     project_path=Path(".")
        ... )
    """

    def __init__(self) -> None:
        """Initialize the skill installer."""
        self._skills_dir = Path(".vibe/skills")

    def install_skill(
        self,
        skill_path: Path,
        project_path: Path,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Install a skill to a project.

        Args:
            skill_path: Path to skill directory
            project_path: Project root directory
            force: Force reinstall if already installed

        Returns:
            Dictionary with installation results
        """
        result: Dict[str, Any] = {
            "success": False,
            "skill_id": skill_path.name,
            "installed_path": "",
            "dependencies_installed": [],
            "errors": [],
            "warnings": [],
        }

        try:
            # Validate skill path
            if not skill_path.exists():
                result["errors"].append(f"Skill path not found: {skill_path}")
                return result

            # Load skill manifest
            manifest = self._load_skill_manifest(skill_path)
            result["skill_id"] = manifest.id

            # Check dependencies
            dep_result: Dict[str, Any] = self._install_dependencies(
                manifest.dependencies,
                project_path,
            )
            if not dep_result["success"]:
                result["errors"].extend(dep_result["errors"])
                return result

            result["dependencies_installed"] = dep_result["installed"]

            # Install skill files
            target_dir = project_path / self._skills_dir / manifest.id
            if target_dir.exists() and not force:
                result["warnings"].append(f"Skill already installed at {target_dir}")
                result["success"] = True
                result["installed_path"] = str(target_dir)
                return result

            # Copy skill files
            self._copy_skill_files(skill_path, target_dir)

            # Update registry
            self._update_registry(manifest, project_path)

            result["success"] = True
            result["installed_path"] = str(target_dir)

        except Exception as e:
            result["errors"].append(f"Installation failed: {e!s}")

        return result

    def uninstall_skill(
        self,
        skill_id: str,
        project_path: Path,
    ) -> Dict[str, Any]:
        """Uninstall a skill from a project.

        Args:
            skill_id: Skill identifier
            project_path: Project root directory

        Returns:
            Dictionary with uninstallation results
        """
        result: Dict[str, Any] = {
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

            # Remove skill directory
            shutil.rmtree(skill_dir)
            result["removed_files"].append(str(skill_dir))

            # Update registry
            self._remove_from_registry(skill_id, project_path)

            result["success"] = True

        except Exception as e:
            result["errors"].append(f"Uninstallation failed: {e}")

        return result

    def list_skills(self, project_path: Path) -> List[Dict[str, Any]]:
        """List installed skills in a project.

        Args:
            project_path: Project root directory

        Returns:
            List of skill information dictionaries
        """
        skills: List[Dict[str, Any]] = []
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
                except Exception:
                    # Skip invalid skills
                    continue

        return skills

    def verify_skill(
        self,
        skill_id: str,
        project_path: Path,
    ) -> Dict[str, Any]:
        """Verify a skill installation.

        Args:
            skill_id: Skill identifier
            project_path: Project root directory

        Returns:
            Dictionary with verification results
        """
        result: Dict[str, Any] = {
            "skill_id": skill_id,
            "installed": False,
            "files_present": False,
            "in_registry": False,
            "dependencies_met": True,
            "errors": [],
        }

        skill_dir = project_path / self._skills_dir / skill_id

        # Check if directory exists
        if not skill_dir.exists():
            result["errors"].append(f"Skill directory not found: {skill_dir}")
            return result

        result["installed"] = True

        # Check for required files
        skill_md = skill_dir / "SKILL.md"
        result["files_present"] = skill_md.exists()

        # Check registry
        result["in_registry"] = self._check_registry(skill_id, project_path)

        return result

    def _load_skill_manifest(self, skill_path: Path) -> SkillManifest:
        """Load skill manifest from skill directory.

        Args:
            skill_path: Path to skill directory

        Returns:
            SkillManifest instance
        """
        skill_md = skill_path / "SKILL.md"

        if skill_md.exists():
            return SkillManifest.from_file(skill_md)

        # Create default manifest
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
        self,
        dependencies: List[str],
        project_path: Path,
    ) -> Dict[str, Any]:
        """Install skill dependencies.

        Args:
            dependencies: List of skill IDs
            project_path: Project root directory

        Returns:
            Dictionary with installation results
        """
        result: Dict[str, Any] = {
            "success": True,
            "installed": [],
            "errors": [],
        }

        for dep_id in dependencies:
            # Check if dependency is already installed
            dep_verify: Dict[str, Any] = self.verify_skill(dep_id, project_path)

            if not dep_verify["installed"]:
                # Dependency not installed
                result["errors"].append(f"Dependency not installed: {dep_id}")
                result["success"] = False
            else:
                result["installed"].append(dep_id)

        return result

    def _copy_skill_files(self, src: Path, dst: Path) -> None:
        """Copy skill files to destination.

        Args:
            src: Source skill directory
            dst: Destination directory
        """
        # Create destination directory
        dst.mkdir(parents=True, exist_ok=True)

        # Copy all files
        for item in src.iterdir():
            if item.is_file():
                shutil.copy2(item, dst / item.name)
            elif item.is_dir() and item.name != "__pycache__":
                # Recursively copy subdirectories
                self._copy_skill_files(item, dst / item.name)

    def _update_registry(self, manifest: SkillManifest, project_path: Path) -> None:
        """Update skill registry.

        Args:
            manifest: Skill manifest
            project_path: Project root directory
        """
        registry_path = project_path / ".vibe" / "skills" / "registry.yaml"

        # Simple registry update (can be enhanced)
        registry_path.parent.mkdir(parents=True, exist_ok=True)

        if not registry_path.exists():
            registry_path.write_text(f"# Skill Registry\nskills:\n  - {manifest.id}\n")
        else:
            content = registry_path.read_text()
            if manifest.id not in content:
                with open(registry_path, "a") as f:
                    f.write(f"  - {manifest.id}\n")

    def _remove_from_registry(self, skill_id: str, project_path: Path) -> None:
        """Remove skill from registry.

        Args:
            skill_id: Skill identifier
            project_path: Project root directory
        """
        registry_path = project_path / ".vibe" / "skills" / "registry.yaml"

        if registry_path.exists():
            content = registry_path.read_text()
            lines = content.split("\n")
            filtered_lines = [line for line in lines if skill_id not in line]
            registry_path.write_text("\n".join(filtered_lines))

    def _check_registry(self, skill_id: str, project_path: Path) -> bool:
        """Check if skill is in registry.

        Args:
            skill_id: Skill identifier
            project_path: Project root directory

        Returns:
            True if in registry, False otherwise
        """
        registry_path = project_path / ".vibe" / "skills" / "registry.yaml"

        if not registry_path.exists():
            return False

        content = registry_path.read_text()
        return skill_id in content
