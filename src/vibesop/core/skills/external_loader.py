"""External skill loader for dynamic skill discovery.

This module provides functionality for discovering and loading skills from
external sources like:
- ~/.claude/skills/ (Claude Code skills)
- ~/.config/skills/ (Central skill storage)
- Third-party skill packs (superpowers, gstack, etc.)

All external skills go through security validation before being loaded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from vibesop.core.skills.parser import parse_skill_md
from vibesop.security import AuditResult, SkillSecurityAuditor

if TYPE_CHECKING:
    from vibesop.core.skills.base import SkillMetadata


class SkillSource(StrEnum):
    """Sources of skills."""

    BUILTIN = "builtin"  # core/skills/
    PROJECT = "project"  # .vibe/skills/
    EXTERNAL = "external"  # ~/.claude/skills/, ~/.config/skills/
    PACK = "pack"  # Third-party skill pack


@dataclass
class ExternalSkillMetadata:
    """Extended metadata for external skills.

    Attributes:
        base_metadata: Core skill metadata
        source: Where the skill came from
        pack_name: Name of the pack (if from a pack)
        pack_version: Version of the pack
        install_path: Path to skill directory
        audit_result: Security audit result
        is_trusted: Whether this skill is trusted (whitelisted)
    """

    base_metadata: SkillMetadata
    source: SkillSource
    pack_name: str | None = None
    pack_version: str | None = None
    install_path: Path | None = None
    audit_result: AuditResult | None = None
    is_trusted: bool = False

    @property
    def is_safe(self) -> bool:
        """Whether the skill passed security audit."""
        return self.audit_result is not None and self.audit_result.is_safe

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.base_metadata.id,
            "name": self.base_metadata.name,
            "description": self.base_metadata.description,
            "source": self.source.value,
            "pack_name": self.pack_name,
            "pack_version": self.pack_version,
            "install_path": str(self.install_path) if self.install_path else None,
            "is_safe": self.is_safe,
            "is_trusted": self.is_trusted,
        }


class ExternalSkillLoader:
    """Loader for external skills.

    This loader discovers skills from external sources and validates
    them through security auditing before allowing them to be used.

    Example:
        >>> loader = ExternalSkillLoader()
        >>> skills = loader.discover_all()
        >>> for skill in skills:
        ...     if skill.is_safe:
        ...         print(f"Safe to load: {skill.base_metadata.id}")
    """

    # External skill search paths
    EXTERNAL_PATHS: ClassVar[list[Path]] = [
        Path.home() / ".claude" / "skills",
        Path.home() / ".config" / "skills",
        Path.home() / ".vibe" / "skills",
    ]

    # Trusted skill pack namespaces
    TRUSTED_PACKS: ClassVar[dict[str, str]] = {
        "superpowers": "https://github.com/obra/superpowers",
        "gstack": "https://github.com/garrytan/gstack",
    }

    def __init__(
        self,
        external_paths: list[Path] | None = None,
        require_audit: bool = True,
        strict_mode: bool = True,
        project_root: str | Path | None = None,
    ):
        """Initialize the external skill loader.

        Args:
            external_paths: Paths to search for external skills
            require_audit: Whether to require passing security audit
            strict_mode: Whether to use strict security mode
            project_root: Project root (for including project skills)
        """
        self._external_paths = external_paths or self.EXTERNAL_PATHS.copy()
        self._require_audit = require_audit
        self._strict_mode = strict_mode

        # Initialize components
        self._auditor = SkillSecurityAuditor(
            strict_mode=strict_mode,
            project_root=project_root or Path.cwd(),
        )

        # Add external paths to auditor's allowed paths
        for path in self._external_paths:
            if path.exists():
                self._auditor.add_allowed_path(path)

        # Cache for discovered skills
        self._cache: dict[str, ExternalSkillMetadata] = {}

    def discover_all(self, force_reload: bool = False) -> dict[str, ExternalSkillMetadata]:
        """Discover all external skills.

        Args:
            force_reload: Force re-discovery even if cached

        Returns:
            Dictionary mapping skill_id to ExternalSkillMetadata
        """
        if self._cache and not force_reload:
            return self._cache

        skills = {}

        # Discover from each external path
        for search_path in self._external_paths:
            if not search_path.exists():
                continue

            # Search for skill directories (containing SKILL.md)
            for skill_dir in search_path.iterdir():
                if not skill_dir.is_dir():
                    continue

                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    continue

                # Parse and audit the skill
                metadata = self._parse_and_audit(skill_dir, skill_file)
                if metadata:
                    skills[metadata.base_metadata.id] = metadata

        self._cache = skills
        return skills

    def discover_from_pack(
        self,
        pack_name: str,
        pack_path: Path,
    ) -> dict[str, ExternalSkillMetadata]:
        """Discover skills from a specific pack.

        Args:
            pack_name: Name of the pack (e.g., "superpowers")
            pack_path: Path to the pack directory

        Returns:
            Dictionary mapping skill_id to ExternalSkillMetadata
        """
        pack_path = Path(pack_path)
        if not pack_path.exists():
            return {}

        skills = {}
        pack_version = self._get_pack_version(pack_path, pack_name)

        # Check if pack is trusted
        is_trusted = pack_name in self.TRUSTED_PACKS

        for skill_dir in pack_path.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            metadata = self._parse_and_audit(
                skill_dir,
                skill_file,
                pack_name=pack_name,
                pack_version=pack_version,
                is_trusted=is_trusted,
            )
            if metadata:
                skills[metadata.base_metadata.id] = metadata

        return skills

    def load_skill(
        self,
        skill_id: str,
        fallback_to_builtin: bool = True,
    ) -> ExternalSkillMetadata | None:
        """Load an external skill by ID.

        Args:
            skill_id: Skill identifier
            fallback_to_builtin: Whether to fall back to builtin skills

        Returns:
            ExternalSkillMetadata if found and safe
        """
        # Discover if not cached
        if not self._cache:
            self.discover_all()

        skill = self._cache.get(skill_id)
        if skill:
            # Check if safe
            if self._require_audit and not skill.is_safe:
                return None
            return skill

        # Try fallback
        if fallback_to_builtin:
            # Could integrate with builtin skill loader here
            pass

        return None

    def is_safe_to_load(self, skill_id: str) -> bool:
        """Check if a skill is safe to load.

        Args:
            skill_id: Skill identifier

        Returns:
            True if skill exists and passed security audit
        """
        skill = self.load_skill(skill_id, fallback_to_builtin=False)
        return skill is not None and skill.is_safe

    def get_unsafe_skills(self) -> list[ExternalSkillMetadata]:
        """Get list of skills that failed security audit.

        Returns:
            List of unsafe skills
        """
        all_skills = self.discover_all()
        return [s for s in all_skills.values() if not s.is_safe and s.audit_result is not None]

    def _parse_and_audit(
        self,
        skill_dir: Path,
        skill_file: Path,
        pack_name: str | None = None,
        pack_version: str | None = None,
        is_trusted: bool = False,
    ) -> ExternalSkillMetadata | None:
        """Parse skill file and perform security audit.

        Args:
            skill_dir: Directory containing the skill
            skill_file: Path to SKILL.md
            pack_name: Name of the pack
            pack_version: Version of the pack
            is_trusted: Whether the pack is trusted

        Returns:
            ExternalSkillMetadata or None if parsing failed
        """
        # Parse skill file
        base_metadata = parse_skill_md(skill_file)
        if not base_metadata:
            return None

        # Security audit
        audit_result = self._auditor.audit_skill_file(skill_file)

        # Check if safe
        is_safe = audit_result.is_safe

        # For trusted packs in non-strict mode, allow through with warning
        if is_trusted and not is_safe and not self._strict_mode:
            # Still mark as unsafe but allow with warning
            pass

        # Determine source
        source = SkillSource.PACK if pack_name else SkillSource.EXTERNAL

        return ExternalSkillMetadata(
            base_metadata=base_metadata,
            source=source,
            pack_name=pack_name,
            pack_version=pack_version,
            install_path=skill_dir,
            audit_result=audit_result,
            is_trusted=is_trusted,
        )

    def _get_pack_version(self, pack_path: Path, _pack_name: str) -> str | None:
        """Get version of a skill pack.

        Args:
            pack_path: Path to the pack directory
            pack_name: Name of the pack

        Returns:
            Version string or None
        """
        # Check for pack manifest
        manifest_file = pack_path / "pack.json"
        if manifest_file.exists():
            try:
                with manifest_file.open() as f:
                    manifest = json.load(f)
                return manifest.get("version")
            except (OSError, json.JSONDecodeError):
                pass

        # Check for package.json
        pkg_file = pack_path / "package.json"
        if pkg_file.exists():
            try:
                with pkg_file.open() as f:
                    pkg = json.load(f)
                return pkg.get("version")
            except (OSError, json.JSONDecodeError):
                pass

        return None

    def get_supported_packs(self) -> dict[str, dict[str, Any]]:
        """Get information about supported skill packs.

        Returns:
            Dictionary mapping pack name to pack info
        """
        packs = {}

        for pack_name, url in self.TRUSTED_PACKS.items():
            # Check if pack is installed
            pack_path = None
            for search_path in self._external_paths:
                potential_path = search_path / pack_name
                if potential_path.exists():
                    pack_path = potential_path
                    break

            packs[pack_name] = {
                "url": url,
                "installed": pack_path is not None,
                "path": str(pack_path) if pack_path else None,
            }

        return packs

    def install_pack(
        self,
        pack_name: str,
        pack_url: str | None = None,
        _version: str | None = None,
    ) -> tuple[bool, str]:
        """Install a skill pack from a Git URL using intelligent analysis.

        Args:
            pack_name: Name of the pack (e.g., "superpowers")
            pack_url: URL to install from (optional)
            version: Specific version to install (optional)

        Returns:
            Tuple of (success, message)
        """
        import shutil

        from vibesop.installer.analyzer import RepoAnalyzer
        from vibesop.installer.planner import InstallPlanner

        pack_url = pack_url or self.TRUSTED_PACKS.get(pack_name)
        if not pack_url:
            return False, f"Unknown pack: {pack_name}"

        # Analyze repository
        analyzer = RepoAnalyzer()
        analysis = analyzer.analyze(pack_url, pack_name)

        if analysis.errors:
            return False, analysis.errors[0]

        if not analysis.skill_files:
            return False, f"No SKILL.md files found in {pack_name} repository"

        # Generate install plan
        target_base = self._external_paths[0]
        planner = InstallPlanner(base_target=target_base)
        plan = planner.plan(analysis)

        # Execute installation
        try:
            target_path = plan.target_path
            target_path.mkdir(parents=True, exist_ok=True)

            # For git-cloned repos, we need the actual repo root on disk.
            # Re-clone directly to target to avoid temp-dir lifetime issues.
            clone_ok = analyzer._git_clone(pack_url, target_path)
            if not clone_ok:
                return False, f"Failed to clone {pack_url} to {target_path}"

            # Optionally remove .git to save space
            git_dir = target_path / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir)

            # Audit installed skills (scan target path, not temp dir)
            audit_results = []
            installed_skill_files = list(target_path.rglob("SKILL.md"))
            for skill_file in installed_skill_files:
                audit = self._auditor.audit_skill_file(skill_file)
                audit_results.append(f"{skill_file.parent.name}: {'PASS' if audit.is_safe else 'WARN'}")

            msg = (
                f"Installed {pack_name} to {target_path}\n"
                f"Skills found: {len(installed_skill_files)}\n"
                f"Audit: {', '.join(audit_results)}"
            )
            return True, msg

        except Exception as e:
            return False, f"Failed to install {pack_name}: {e}"


# Convenience functions


def discover_external_skills(
    require_audit: bool = True,
) -> dict[str, ExternalSkillMetadata]:
    """Convenience function to discover all external skills.

    Args:
        require_audit: Whether to require passing security audit

    Returns:
        Dictionary of external skills

    Example:
        >>> skills = discover_external_skills()
        >>> safe_skills = {k: v for k, v in skills.items() if v.is_safe}
    """
    loader = ExternalSkillLoader(require_audit=require_audit)
    return loader.discover_all()


def is_skill_safe(skill_id: str) -> bool:
    """Check if an external skill is safe to load.

    Args:
        skill_id: Skill identifier

    Returns:
        True if skill exists and is safe
    """
    loader = ExternalSkillLoader()
    return loader.is_safe_to_load(skill_id)


__all__ = [
    "ExternalSkillLoader",
    "ExternalSkillMetadata",
    "SkillSource",
    "discover_external_skills",
    "is_skill_safe",
]
