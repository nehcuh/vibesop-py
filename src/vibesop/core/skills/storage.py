"""Central skill storage management.

This module provides functionality for managing skills in a central location
(~/.config/skills/) with platform-specific directories using symlinks.

Architecture:
    ~/.config/skills/          # Central storage (actual files)
    ├── systematic-debugging/
    │   └── SKILL.md
    ├── riper-workflow/
    │   └── SKILL.md
    └── ...

    ~/.claude/skills/          # Platform symlinks
    ├── systematic-debugging -> ~/.config/skills/systematic-debugging
    ├── riper-workflow -> ~/.config/skills/riper-workflow
    └── ...

    ~/.config/opencode/skills/ # Platform symlinks
    ├── systematic-debugging -> ~/.config/skills/systematic-debugging
    └── ...
"""

import hashlib
import json
import logging
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from vibesop.security import PathSafety
from vibesop.security.exceptions import PathTraversalError

logger = logging.getLogger(__name__)


@dataclass
class SkillSource:
    """Source location for a skill."""

    type: str  # "local", "github", "registry"
    path: str  # Local path, GitHub repo, or registry URL
    version: str | None = None
    ref: str | None = None  # Git ref (branch/tag/commit)


@dataclass
class SkillManifest:
    """Manifest for an installed skill."""

    id: str
    name: str
    description: str
    version: str
    source: SkillSource
    installed_at: str
    checksum: str


class SkillStorage:
    """Manage central skill storage.

    Handles:
    - Installing skills to ~/.config/skills/
    - Creating symlinks from platform directories
    - Managing skill updates and removal

    Usage:
        storage = SkillStorage()

        # Install skill from local path
        storage.install_skill(
            skill_id="systematic-debugging",
            source_path=Path("core/skills/systematic-debugging"),
        )

        # Link skill to platform
        storage.link_to_platform(
            skill_id="systematic-debugging",
            platform="claude-code",
        )
    """

    # Central storage location
    CENTRAL_SKILLS_DIR = Path.home() / ".config" / "skills"

    # Platform skill directories
    PLATFORM_SKILLS_DIRS: ClassVar[dict[str, Path]] = {
        "claude-code": Path.home() / ".claude" / "skills",
        "kimi-cli": Path.home() / ".kimi" / "skills",
        "opencode": Path.home() / ".config" / "opencode" / "skills",
        "cursor": Path.home() / ".config" / "cursor" / "skills",
    }

    def __init__(self, dry_run: bool = False) -> None:
        """Initialize skill storage.

        Args:
            dry_run: If True, don't make actual changes
        """
        self.dry_run = dry_run
        self._path_safety = PathSafety()

    def get_skill_path(self, skill_id: str) -> Path:
        """Get the central storage path for a skill.

        Args:
            skill_id: Skill identifier (e.g., "systematic-debugging")

        Returns:
            Path to skill directory in central storage
        """
        return self.CENTRAL_SKILLS_DIR / skill_id

    def get_platform_skill_path(self, skill_id: str, platform: str) -> Path:
        """Get the platform-specific path for a skill.

        Args:
            skill_id: Skill identifier
            platform: Platform name (claude-code, kimi-cli, opencode, etc.)

        Returns:
            Path to skill directory in platform
        """
        if platform not in self.PLATFORM_SKILLS_DIRS:
            raise ValueError(f"Unknown platform: {platform}")
        return self.PLATFORM_SKILLS_DIRS[platform] / skill_id

    def skill_exists(self, skill_id: str) -> bool:
        """Check if a skill exists in central storage.

        Args:
            skill_id: Skill identifier

        Returns:
            True if skill exists
        """
        skill_path = self.get_skill_path(skill_id)
        return skill_path.exists() and (skill_path / "SKILL.md").exists()

    def install_skill(
        self,
        skill_id: str,
        source_path: Path,
        overwrite: bool = False,
    ) -> tuple[bool, str]:
        """Install a skill to central storage.

        Args:
            skill_id: Skill identifier
            source_path: Path to skill source directory
            overwrite: Overwrite if already exists

        Returns:
            Tuple of (success, message)
        """
        skill_path = self.get_skill_path(skill_id)
        source_path = Path(source_path).expanduser().resolve()

        if not source_path.exists():
            return False, f"Source path not found: {source_path}"

        # Path traversal check
        try:
            self._path_safety.check_traversal(str(source_path), Path.cwd())
        except PathTraversalError:
            return False, f"Unsafe source path: {source_path}"

        # Check if already exists
        if skill_path.exists() and not overwrite:
            return False, f"Skill already exists: {skill_id}"

        if self.dry_run:
            return True, f"Would install {skill_id} from {source_path}"

        # Create central storage directory
        self.CENTRAL_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

        # Remove existing if overwriting
        if skill_path.exists():
            shutil.rmtree(skill_path)

        # Copy skill directory
        shutil.copytree(source_path, skill_path)

        # Write metadata
        self._write_metadata(skill_id, source_path)

        return True, f"Installed {skill_id} to central storage"

    def install_from_remote(
        self,
        skill_id: str,
        url: str,
        overwrite: bool = False,
    ) -> tuple[bool, str]:
        """Install a skill from a remote URL.

        Args:
            skill_id: Skill identifier
            url: URL to skill archive or raw file
            overwrite: Overwrite if already exists

        Returns:
            Tuple of (success, message)
        """
        if self.dry_run:
            return True, f"Would download {skill_id} from {url}"

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                archive_path = tmpdir_path / "skill.tar.gz"

                # Download
                urllib.request.urlretrieve(url, archive_path)

                # Extract
                import tarfile

                with tarfile.open(archive_path) as tar:
                    tar.extractall(tmpdir_path)

                # Find extracted directory
                extracted_dirs = [d for d in tmpdir_path.iterdir() if d.is_dir()]
                if not extracted_dirs:
                    return False, "No directory found in archive"

                source_path = extracted_dirs[0]
                return self.install_skill(skill_id, source_path, overwrite)

        except Exception as e:
            return False, f"Failed to download {skill_id}: {e}"

    def link_to_platform(
        self,
        skill_id: str,
        platform: str,
        force: bool = False,
    ) -> tuple[bool, str]:
        """Create symlink from platform to central storage.

        Args:
            skill_id: Skill identifier
            platform: Platform name
            force: Remove existing file/link before creating symlink

        Returns:
            Tuple of (success, message)
        """
        if platform not in self.PLATFORM_SKILLS_DIRS:
            return False, f"Unknown platform: {platform}"

        # Check skill exists in central storage
        skill_path = self.get_skill_path(skill_id)
        if not skill_path.exists():
            return False, f"Skill not found in central storage: {skill_id}"

        # Get platform path
        platform_path = self.get_platform_skill_path(skill_id, platform)
        platform_path.parent.mkdir(parents=True, exist_ok=True)

        # Handle existing file/link
        if platform_path.exists():
            if platform_path.is_symlink():
                # Symlink already exists, check if it points to right place
                target = platform_path.resolve()
                if target == skill_path.resolve():
                    return True, f"Already linked: {skill_id} -> {platform}"
                elif force:
                    platform_path.unlink()
                else:
                    return False, f"Symlink exists but points elsewhere: {platform_path}"
            elif force:
                if platform_path.is_dir():
                    shutil.rmtree(platform_path)
                else:
                    platform_path.unlink()
            else:
                return False, f"File exists: {platform_path} (use --force to overwrite)"

        if self.dry_run:
            return True, f"Would link {skill_id} -> {platform}"

        # Create symlink
        try:
            platform_path.symlink_to(skill_path)
            return True, f"Linked {skill_id} -> {platform}"
        except OSError:
            # Fallback to copy if symlinks not supported (Windows)
            try:
                shutil.copytree(skill_path, platform_path)
                return True, f"Copied {skill_id} -> {platform} (symlinks not supported)"
            except Exception as e:
                return False, f"Failed to link/copy: {e}"

    def unlink_from_platform(
        self,
        skill_id: str,
        platform: str,
    ) -> tuple[bool, str]:
        """Remove symlink from platform.

        Args:
            skill_id: Skill identifier
            platform: Platform name

        Returns:
            Tuple of (success, message)
        """
        platform_path = self.get_platform_skill_path(skill_id, platform)

        if not platform_path.exists():
            return True, f"Nothing to unlink: {skill_id} from {platform}"

        if self.dry_run:
            return True, f"Would unlink {skill_id} from {platform}"

        try:
            if platform_path.is_symlink():
                platform_path.unlink()
            elif platform_path.is_dir():
                shutil.rmtree(platform_path)
            else:
                platform_path.unlink()
            return True, f"Unlinked {skill_id} from {platform}"
        except Exception as e:
            return False, f"Failed to unlink: {e}"

    def remove_skill(self, skill_id: str, unlink_all: bool = False) -> tuple[bool, str]:
        """Remove a skill from central storage.

        Args:
            skill_id: Skill identifier
            unlink_all: Also remove from all platforms

        Returns:
            Tuple of (success, message)
        """
        skill_path = self.get_skill_path(skill_id)

        if not skill_path.exists():
            return False, f"Skill not found: {skill_id}"

        if self.dry_run:
            return True, f"Would remove {skill_id}"

        # Unlink from all platforms first
        if unlink_all:
            for platform_name in self.PLATFORM_SKILLS_DIRS:
                self.unlink_from_platform(skill_id, platform_name)

        # Remove from central storage
        shutil.rmtree(skill_path)
        return True, f"Removed {skill_id} from central storage"

    def list_skills(self) -> dict[str, SkillManifest]:
        """List all installed skills.

        Returns:
            Dictionary mapping skill_id to SkillManifest
        """
        skills = {}

        if not self.CENTRAL_SKILLS_DIR.exists():
            return skills

        for skill_dir in self.CENTRAL_SKILLS_DIR.iterdir():
            if not skill_dir.is_dir():
                continue

            manifest = self._read_metadata(skill_dir.name)
            if manifest:
                skills[skill_dir.name] = manifest

        return skills

    def get_linked_skills(self, platform: str) -> list[str]:
        """Get list of skills linked to a platform.

        Args:
            platform: Platform name

        Returns:
            List of skill IDs linked to the platform
        """
        if platform not in self.PLATFORM_SKILLS_DIRS:
            raise ValueError(f"Unknown platform: {platform}")

        platform_dir = self.PLATFORM_SKILLS_DIRS[platform]
        if not platform_dir.exists():
            return []

        linked = []
        for skill_path in platform_dir.iterdir():
            if skill_path.is_symlink() or skill_path.is_dir():
                linked.append(skill_path.name)

        return linked

    def sync_project_skills(
        self,
        project_root: Path,
        platform: str,
        force: bool = False,
    ) -> tuple[int, int, list[str]]:
        """Sync all skills from project to platform.

        Args:
            project_root: Path to VibeSOP project root
            platform: Target platform
            force: Force overwrite existing links

        Returns:
            Tuple of (installed_count, linked_count, messages)
        """
        from pathlib import Path as StdPath

        project_root = StdPath(project_root).resolve()
        skills_source = project_root / "core" / "skills"

        if not skills_source.exists():
            return 0, 0, ["Skills source not found"]

        installed = 0
        linked = 0
        messages = []

        for skill_dir in skills_source.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_id = skill_dir.name

            # Install to central storage
            success, msg = self.install_skill(
                skill_id=skill_id,
                source_path=skill_dir,
                overwrite=force,
            )
            if success:
                installed += 1
                messages.append(f"✓ {msg}")
            elif "already exists" in msg:
                installed += 1
            else:
                messages.append(f"✗ {msg}")
                continue

            # Link to platform
            success, msg = self.link_to_platform(
                skill_id=skill_id,
                platform=platform,
                force=force,
            )
            if success:
                linked += 1
            else:
                messages.append(f"✗ {msg}")

        return installed, linked, messages

    def _write_metadata(self, skill_id: str, source_path: Path) -> None:
        """Write skill metadata.

        Args:
            skill_id: Skill identifier
            source_path: Source path
        """
        skill_path = self.get_skill_path(skill_id)
        metadata_path = skill_path / ".vibe-manifest.json"

        skill_file = skill_path / "SKILL.md"
        checksum = ""
        if skill_file.exists():
            checksum = hashlib.sha256(skill_file.read_bytes()).hexdigest()[:16]

        from datetime import datetime

        source_obj = SkillSource(
            type="local",
            path=str(source_path),
            version=None,
            ref=None,
        )

        manifest = SkillManifest(
            id=skill_id,
            name=skill_id.replace("-", " ").title(),
            description="",
            version="1.0.0",
            source=source_obj,
            installed_at=datetime.now().isoformat(),
            checksum=checksum,
        )

        # Convert to dict for JSON serialization
        manifest_dict = {
            "id": manifest.id,
            "name": manifest.name,
            "description": manifest.description,
            "version": manifest.version,
            "source": {
                "type": manifest.source.type,
                "path": manifest.source.path,
                "version": manifest.source.version,
                "ref": manifest.source.ref,
            },
            "installed_at": manifest.installed_at,
            "checksum": manifest.checksum,
        }

        with metadata_path.open("w") as f:
            json.dump(manifest_dict, f, indent=2)

    def _read_metadata(self, skill_id: str) -> SkillManifest | None:
        """Read skill metadata.

        Args:
            skill_id: Skill identifier

        Returns:
            SkillManifest or None
        """
        skill_path = self.get_skill_path(skill_id)
        metadata_path = skill_path / ".vibe-manifest.json"

        if not metadata_path.exists():
            return None

        try:
            with metadata_path.open() as f:
                data = json.load(f)

            # Reconstruct SkillSource from dict
            if "source" in data and isinstance(data["source"], dict):
                source_data = data["source"]
                data["source"] = SkillSource(
                    type=source_data.get("type", "local"),
                    path=source_data.get("path", ""),
                    version=source_data.get("version"),
                    ref=source_data.get("ref"),
                )

            return SkillManifest(**data)
        except Exception as e:
            logger.debug(f"Failed to parse skill manifest from {metadata_path}: {e}")
            return None


# Convenience functions
def get_storage() -> SkillStorage:
    """Get the global skill storage instance."""
    return SkillStorage()


def install_skill_from_project(
    skill_id: str,
    project_root: str | Path = ".",
) -> tuple[bool, str]:
    """Install a skill from the project.

    Args:
        skill_id: Skill identifier
        project_root: Path to VibeSOP project root

    Returns:
        Tuple of (success, message)
    """
    storage = SkillStorage()
    source_path = Path(project_root) / "core" / "skills" / skill_id
    return storage.install_skill(skill_id, source_path)


def link_all_to_platform(
    platform: str,
    project_root: str | Path = ".",
    force: bool = False,
) -> tuple[int, int, list[str]]:
    """Link all project skills to a platform.

    Args:
        platform: Target platform
        project_root: Path to VibeSOP project root
        force: Force overwrite existing links

    Returns:
        Tuple of (installed_count, linked_count, messages)
    """
    storage = SkillStorage()
    return storage.sync_project_skills(Path(project_root), platform, force)
