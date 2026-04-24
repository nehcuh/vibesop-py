"""Skill pack installer for third-party skill packs.

This module handles installation of skill packs from Git URLs or
trusted pack names, including repository analysis, installation planning,
and post-install security auditing.

Architecture:
    1. Clone to central storage: ~/.config/skills/<pack>/
    2. Create symlinks in platform directories: ~/.claude/skills/<pack> -> ~/.config/skills/<pack>/
    3. Audit installed skills
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import ClassVar

from vibesop.constants import TRUSTED_PACKS
from vibesop.core.skills.storage import SkillStorage
from vibesop.installer.analyzer import RepoAnalyzer
from vibesop.installer.planner import InstallPlanner
from vibesop.security import SkillSecurityAuditor

logger = logging.getLogger(__name__)


class PackInstaller:
    """Installer for skill packs from trusted names or Git URLs.

    Uses central storage (~/.config/skills/) with platform symlinks
    for unified skill management across all AI tools.

    Example:
        >>> installer = PackInstaller()
        >>> success, msg = installer.install_pack("superpowers")
        >>> print(f"Installed: {success}, {msg}")
    """

    # Central storage for all external skills
    CENTRAL_STORAGE: ClassVar[Path] = Path.home() / ".config" / "skills"

    # Platform directories that receive symlinks
    PLATFORM_PATHS: ClassVar[list[Path]] = [
        Path.home() / ".claude" / "skills",
        Path.home() / ".config" / "opencode" / "skills",
        Path.home() / ".kimi" / "skills",
        Path.home() / ".config" / "cursor" / "skills",
    ]

    def __init__(
        self,
        external_paths: list[Path] | None = None,
        central_storage: Path | None = None,
        platform_paths: list[Path] | None = None,
        strict_mode: bool = True,
        project_root: str | Path | None = None,
    ):
        """Initialize the pack installer.

        Args:
            external_paths: Legacy parameter - first path used as central_storage,
                           remaining paths used as platform_paths (for backward compatibility)
            central_storage: Central storage directory (default: ~/.config/skills)
            platform_paths: Platform directories to create symlinks in
            strict_mode: Whether to use strict security mode for auditing
            project_root: Project root (for security auditor context)
        """
        # Handle backward compatibility with external_paths
        if external_paths is not None:
            self.central_storage = central_storage or external_paths[0]
            self.platform_paths = platform_paths or external_paths[1:]
        else:
            self.central_storage = central_storage or self.CENTRAL_STORAGE
            self.platform_paths = platform_paths or self.PLATFORM_PATHS.copy()

        self._strict_mode = strict_mode
        self._auditor = SkillSecurityAuditor(
            strict_mode=strict_mode,
            project_root=project_root or Path.cwd(),
        )
        # Allow auditing in central storage and platform directories
        self.central_storage.mkdir(parents=True, exist_ok=True)
        self._auditor.add_allowed_path(self.central_storage)
        for path in self.platform_paths:
            if path.exists():
                self._auditor.add_allowed_path(path)

    def install_pack(
        self,
        pack_name: str,
        pack_url: str | None = None,
        _version: str | None = None,
        platforms: list[str] | None = None,
    ) -> tuple[bool, str]:
        """Install a skill pack from a Git URL using central storage + symlinks.

        Args:
            pack_name: Name of the pack (e.g., "superpowers")
            pack_url: URL to install from (optional)
            version: Specific version to install (optional)
            platforms: List of platform names to link (default: all supported platforms)

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

        # Generate install plan targeting central storage
        planner = InstallPlanner(base_target=self.central_storage)
        plan = planner.plan(analysis)

        # Execute installation
        try:
            target_path = plan.target_path
            target_path.mkdir(parents=True, exist_ok=True)

            # git clone cannot target an existing non-empty directory.
            # Remove the old directory if it already exists and has contents.
            if target_path.exists() and any(target_path.iterdir()):
                shutil.rmtree(target_path)

            # Clone to central storage
            clone_ok = analyzer.git_clone(pack_url, target_path)
            if not clone_ok:
                return False, f"Failed to clone {pack_url} to {target_path}"

            # Optionally remove .git to save space
            git_dir = target_path / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir)

            # Audit installed skills
            audit_results = []
            installed_skill_files = list(target_path.rglob("SKILL.md"))
            for skill_file in installed_skill_files:
                audit = self._auditor.audit_skill_file(skill_file)
                audit_results.append(
                    f"{skill_file.parent.name}: {'PASS' if audit.is_safe else 'WARN'}"
                )

            # Create symlinks in platform directories
            symlink_results = self._create_symlinks(pack_name, platforms)

            msg_parts = [
                f"Installed {pack_name} to {target_path}",
                f"Skills found: {len(installed_skill_files)}",
                f"Audit: {', '.join(audit_results)}",
            ]

            if symlink_results:
                msg_parts.append("Symlinks:")
                for platform, status in symlink_results:
                    icon = "✓" if status.startswith("Linked") or status.startswith("Already") else "✗"
                    msg_parts.append(f"  {icon} {platform}: {status}")

            return True, "\n".join(msg_parts)

        except Exception as e:
            return False, f"Failed to install {pack_name}: {e}"

    def _create_symlinks(
        self,
        pack_name: str,
        platforms: list[str] | None = None,
    ) -> list[tuple[str, str]]:
        """Create symlinks from platform directories to central storage.

        Args:
            pack_name: Name of the pack
            platforms: Specific platforms to link (None = all)

        Returns:
            List of (platform, status) tuples
        """
        results: list[tuple[str, str]] = []
        storage = SkillStorage()
        central_path = self.central_storage / pack_name

        if not central_path.exists():
            return results

        # Determine which platforms to link
        platforms_to_link = platforms or list(storage.PLATFORM_SKILLS_DIRS.keys())

        for platform in platforms_to_link:
            if platform not in storage.PLATFORM_SKILLS_DIRS:
                results.append((platform, "Unknown platform"))
                continue

            platform_dir = storage.PLATFORM_SKILLS_DIRS[platform]
            platform_path = platform_dir / pack_name

            try:
                platform_dir.mkdir(parents=True, exist_ok=True)

                # If platform already has a real directory (legacy install), remove it
                if platform_path.exists() and not platform_path.is_symlink():
                    if platform_path.is_dir():
                        shutil.rmtree(platform_path)
                    else:
                        platform_path.unlink()

                # Create or update symlink
                if platform_path.is_symlink():
                    current_target = platform_path.resolve()
                    if current_target == central_path.resolve():
                        results.append((platform, f"Already linked to {platform}"))
                        continue
                    platform_path.unlink()

                platform_path.symlink_to(central_path)
                results.append((platform, f"Linked to {platform}"))

            except OSError as e:
                # Fallback: copy if symlinks not supported
                try:
                    if platform_path.exists():
                        if platform_path.is_symlink():
                            platform_path.unlink()
                        elif platform_path.is_dir():
                            shutil.rmtree(platform_path)
                        else:
                            platform_path.unlink()
                    shutil.copytree(central_path, platform_path)
                    results.append((platform, f"Copied to {platform} (symlinks not supported)"))
                except Exception as copy_err:
                    results.append((platform, f"Failed: {copy_err}"))

        return results
