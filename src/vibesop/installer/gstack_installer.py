"""gstack skill pack installer.

This module handles installation of the gstack skill pack
from GitHub, including repository cloning and symlink setup.
"""

from pathlib import Path
from typing import Optional, Dict, Any

from vibesop.installer.base import GitBasedInstaller


class GstackInstaller(GitBasedInstaller):
    """Installer for gstack skill pack.

    Clones the gstack repository and sets up symlinks
    for different platforms.
    """

    repo_urls = [
        "https://github.com/garrytan/gstack.git",
        "https://gitee.com/mirrors/gstack.git",
    ]
    repo_name = "gstack"
    unified_path = Path("~/.config/skills/gstack").expanduser()
    platform_symlink_paths = {
        "claude-code": Path("~/.config/claude/skills"),
        "opencode": Path("~/.config/opencode/skills"),
    }
    clone_timeout = 300
    max_retries = 3

    def _check_markers(self) -> bool:
        markers = [
            self.unified_path / "SKILL.md",
            self.unified_path / "VERSION",
            self.unified_path / "setup",
        ]
        return all(marker.exists() for marker in markers)

    def _find_skill_entries(self) -> list[Path]:
        entries = []
        for entry in self.unified_path.iterdir():
            if entry.is_dir() and (entry / "SKILL.md").exists():
                entries.append(entry)
        return entries

    def _count_skills(self) -> int:
        return len(self._find_skill_entries())
