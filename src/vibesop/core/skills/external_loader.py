"""External skill loader for dynamic skill discovery."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from vibesop.constants import TRUSTED_PACKS
from vibesop.core.skills.parser import parse_skill_md
from vibesop.spec.models import SkillSpec

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from vibesop.security import AuditResult


class SkillSource(StrEnum):
    """Sources of skills."""

    BUILTIN = "builtin"  # core/skills/
    PROJECT = "project"  # .vibe/skills/
    EXTERNAL = "external"  # ~/.claude/skills/, ~/.config/skills/
    PACK = "pack"  # Third-party skill pack


@dataclass
class ExternalSkillMetadata:
    """Extended metadata for external skills."""

    base_metadata: SkillSpec
    source: SkillSource
    pack_name: str | None = None
    pack_version: str | None = None
    install_path: Path | None = None
    audit_result: AuditResult | None = None
    is_trusted: bool = False

    @property
    def is_safe(self) -> bool:
        return self.audit_result is not None and self.audit_result.is_safe

    def to_dict(self) -> dict[str, Any]:
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
    """Loader for external skills."""

    # External skill search paths
    EXTERNAL_PATHS: ClassVar[list[Path]] = [
        Path.home() / ".claude" / "skills",
        Path.home() / ".config" / "skills",
        Path.home() / ".vibe" / "skills",
    ]

    # Trusted skill pack namespaces (canonical source in vibesop.constants)
    TRUSTED_PACKS: ClassVar[dict[str, str]] = TRUSTED_PACKS

    _default_auditor_factory: ClassVar[Any] = None

    def __init__(
        self,
        external_paths: list[Path] | None = None,
        require_audit: bool = True,
        strict_mode: bool = True,
        project_root: str | Path | None = None,
        auditor: Any | None = None,
    ):
        self.external_paths = external_paths or self.EXTERNAL_PATHS.copy()
        self._require_audit = require_audit
        self._strict_mode = strict_mode
        self._project_root = project_root or Path.cwd()

        if auditor is not None:
            self._auditor = auditor
        elif type(self)._default_auditor_factory is not None:
            self._auditor = type(self)._default_auditor_factory(strict_mode, self._project_root)
        else:
            self._auditor = None

        if self._auditor is not None:
            for path in self.external_paths:
                if path.exists():
                    self._auditor.add_allowed_path(path)

        self._cache: dict[str, ExternalSkillMetadata] = {}

    @classmethod
    def set_default_auditor_factory(cls, factory: Any) -> None:
        cls._default_auditor_factory = factory

    def _ensure_auditor(self) -> Any:
        if self._auditor is not None:
            return self._auditor
        try:
            from vibesop.security import SkillSecurityAuditor

            self._auditor = SkillSecurityAuditor(
                strict_mode=self._strict_mode, project_root=self._project_root,
            )
            for path in self.external_paths:
                if path.exists():
                    self._auditor.add_allowed_path(path)
        except ImportError:
            pass
        return self._auditor

    def discover_all(self, force_reload: bool = False) -> dict[str, ExternalSkillMetadata]:
        if self._cache and not force_reload:
            return self._cache

        skills = {}

        # Discover from each external path
        for search_path in self.external_paths:
            if not search_path.exists():
                continue

            # Search for skill directories (containing SKILL.md) recursively
            for skill_file in search_path.rglob("SKILL.md"):
                if skill_file.is_symlink():
                    logger.warning("Skipping symlinked skill file: %s", skill_file)
                    continue

                skill_dir = skill_file.parent

                # Infer pack name from directory structure.
                # Only treat as a pack if the skill is nested inside a pack
                # directory (depth >= 3). Direct installs at depth == 2 are
                # standalone external skills with no pack namespace.
                # e.g., ~/.config/skills/awesome-skills/skills/my-audit/SKILL.md
                #       -> pack_name = "awesome-skills"
                # e.g., ~/.config/skills/systematic-debugging/SKILL.md
                #       -> pack_name = None
                pack_name = self._resolve_pack_name(search_path, skill_file)

                # Parse and audit the skill
                is_trusted = pack_name in self.TRUSTED_PACKS if pack_name else False
                metadata = self._parse_and_audit(
                    skill_dir, skill_file, pack_name=pack_name, is_trusted=is_trusted
                )
                if metadata:
                    skill_key = metadata.base_metadata.id
                    if pack_name and not skill_key.startswith(f"{pack_name}/"):
                        skill_key = f"{pack_name}/{skill_key}"
                    skills[skill_key] = metadata

        self._cache = skills
        return skills

    def discover_from_pack(
        self,
        pack_name: str,
        pack_path: Path,
    ) -> dict[str, ExternalSkillMetadata]:
        pack_path = Path(pack_path)
        if not pack_path.exists():
            return {}

        skills = {}
        pack_version = self._get_pack_version(pack_path, pack_name)

        # Check if pack is trusted
        is_trusted = pack_name in self.TRUSTED_PACKS

        for skill_file in pack_path.rglob("SKILL.md"):
            if skill_file.is_symlink():
                logger.warning("Skipping symlinked skill file: %s", skill_file)
                continue

            skill_dir = skill_file.parent

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
        skill = self.load_skill(skill_id, fallback_to_builtin=False)
        return skill is not None and skill.is_safe

    def get_unsafe_skills(self) -> list[ExternalSkillMetadata]:
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
        """Audit skill file first, then parse only if safe."""
        auditor = self._ensure_auditor()
        if auditor is not None:
            audit_result = auditor.audit_skill_file(skill_file, pack_name=pack_name)

            if not audit_result.is_safe and not is_trusted:
                has_high = any(t.level.value == "high" for t in audit_result.threats)
                if has_high:
                    logger.debug(
                        "Security audit rejected: %s (%s)",
                        skill_file,
                        [t.name for t in audit_result.threats if t.level.value == "high"],
                    )
                    return None
        else:
            audit_result = None

        # Parse skill file only after passing audit
        base_metadata = parse_skill_md(skill_file)
        if not base_metadata:
            return None

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

    def _resolve_pack_name(self, search_path: Path, skill_file: Path) -> str | None:
        """Infer pack name from directory structure, falling back to manifest files.

        If the directory name itself is not in TRUSTED_PACKS, we:
        1. Walk up looking for pack.json or package.json and match repository URLs
        2. Match directory names against known trusted repo names extracted from URLs

        This handles cases like:
            ~/.claude/skills/omx-plugins/oh-my-codex/skills/ultraqa/SKILL.md
        where the outer folder (omx-plugins) is not trusted, but the inner
        oh-my-codex repo belongs to the trusted "omx" pack.
        """
        try:
            rel_path = skill_file.relative_to(search_path)
            if len(rel_path.parts) < 3:
                return None
            candidate = rel_path.parts[0]
            if candidate in self.TRUSTED_PACKS:
                return candidate

            # Walk up and inspect manifest files for repository URL matches
            current = skill_file.parent
            while current != search_path and search_path in current.parents:
                for manifest_name in ("pack.json", "package.json"):
                    manifest_path = current / manifest_name
                    if manifest_path.exists():
                        try:
                            with manifest_path.open() as f:
                                data = json.load(f)
                            repo = data.get("repository")
                            repo_url = repo.get("url") if isinstance(repo, dict) else repo
                            homepage = data.get("homepage")
                            for trusted_name, trusted_url in self.TRUSTED_PACKS.items():
                                if repo_url and trusted_url in repo_url:
                                    return trusted_name
                                if homepage and trusted_url in homepage:
                                    return trusted_name
                        except (OSError, json.JSONDecodeError):
                            pass
                current = current.parent

            # Fallback: match directory names against trusted repo names from URLs
            from urllib.parse import urlparse
            for trusted_name, trusted_url in self.TRUSTED_PACKS.items():
                repo_name = urlparse(trusted_url).path.rstrip("/").split("/")[-1]
                if repo_name and repo_name in rel_path.parts:
                    return trusted_name

            return candidate
        except ValueError:
            return None

    def get_supported_packs(self) -> dict[str, dict[str, Any]]:
        packs = {}

        for pack_name, url in TRUSTED_PACKS.items():
            # Check if pack is installed
            pack_path = None
            for search_path in self.external_paths:
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


# Convenience functions


def discover_external_skills(
    require_audit: bool = True,
) -> dict[str, ExternalSkillMetadata]:
    loader = ExternalSkillLoader(require_audit=require_audit)
    return loader.discover_all()


def is_skill_safe(skill_id: str) -> bool:
    loader = ExternalSkillLoader()
    return loader.is_safe_to_load(skill_id)


__all__ = [
    "ExternalSkillLoader",
    "ExternalSkillMetadata",
    "SkillSource",
    "discover_external_skills",
    "is_skill_safe",
]
