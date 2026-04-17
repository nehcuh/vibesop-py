"""Skill pack installer for third-party skill packs.

This module handles installation of skill packs from Git URLs or
trusted pack names, including repository analysis, installation planning,
and post-install security auditing.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import ClassVar

from vibesop.constants import TRUSTED_PACKS
from vibesop.installer.analyzer import RepoAnalyzer
from vibesop.installer.planner import InstallPlanner
from vibesop.security import SkillSecurityAuditor

logger = logging.getLogger(__name__)


class PackInstaller:
    """Installer for skill packs from trusted names or Git URLs.

    This installer analyzes repositories, generates installation plans,
    clones skill packs, and performs post-install security audits.

    Example:
        >>> installer = PackInstaller()
        >>> success, msg = installer.install_pack("superpowers")
        >>> print(f"Installed: {success}, {msg}")
    """

    # External skill installation paths
    EXTERNAL_PATHS: ClassVar[list[Path]] = [
        Path.home() / ".claude" / "skills",
        Path.home() / ".config" / "skills",
        Path.home() / ".vibe" / "skills",
    ]

    def __init__(
        self,
        external_paths: list[Path] | None = None,
        strict_mode: bool = True,
        project_root: str | Path | None = None,
    ):
        """Initialize the pack installer.

        Args:
            external_paths: Paths to install external skills to
            strict_mode: Whether to use strict security mode for auditing
            project_root: Project root (for security auditor context)
        """
        self.external_paths = external_paths or self.EXTERNAL_PATHS.copy()
        self._strict_mode = strict_mode
        self._auditor = SkillSecurityAuditor(
            strict_mode=strict_mode,
            project_root=project_root or Path.cwd(),
        )
        for path in self.external_paths:
            if path.exists():
                self._auditor.add_allowed_path(path)

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
        pack_url = pack_url or TRUSTED_PACKS.get(pack_name)
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
        target_base = self.external_paths[0]
        planner = InstallPlanner(base_target=target_base)
        plan = planner.plan(analysis)

        # Execute installation
        try:
            target_path = plan.target_path
            target_path.mkdir(parents=True, exist_ok=True)

            # For git-cloned repos, we need the actual repo root on disk.
            # Re-clone directly to target to avoid temp-dir lifetime issues.
            clone_ok = analyzer.git_clone(pack_url, target_path)
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
                audit_results.append(
                    f"{skill_file.parent.name}: {'PASS' if audit.is_safe else 'WARN'}"
                )

            msg = (
                f"Installed {pack_name} to {target_path}\n"
                f"Skills found: {len(installed_skill_files)}\n"
                f"Audit: {', '.join(audit_results)}"
            )
            return True, msg

        except Exception as e:
            return False, f"Failed to install {pack_name}: {e}"
