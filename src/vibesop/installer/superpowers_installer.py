"""Superpowers skill pack installer.

This module handles installation of the Superpowers skill pack
from GitHub, including repository cloning and symlink setup.
"""

from pathlib import Path
from typing import Optional, Dict, Any

from vibesop.installer.base import GitBasedInstaller


class SuperpowersInstaller(GitBasedInstaller):
    """Installer for Superpowers skill pack.

    Clones the Superpowers repository and sets up symlinks
    for different platforms.
    """

    repo_urls = [
        "https://github.com/obra/superpowers.git",
        "https://gitee.com/mirrors/superpowers.git",
    ]
    repo_name = "superpowers"
    unified_path = Path("~/.config/skills/superpowers").expanduser()
    platform_symlink_paths = {
        "claude-code": Path("~/.config/claude/skills"),
        "opencode": Path("~/.config/opencode/skills"),
    }
    clone_timeout = 300
    max_retries = 3

    def _check_markers(self) -> bool:
        skills_dir = self.unified_path / "skills"
        return self.unified_path.exists() and skills_dir.exists() and any(skills_dir.iterdir())

    def _find_skill_entries(self) -> list[Path]:
        skills_dir = self.unified_path / "skills"
        if not skills_dir.exists():
            return []
        return [e for e in skills_dir.iterdir() if e.is_dir()]

    def _count_skills(self) -> int:
        return len(self._find_skill_entries())
