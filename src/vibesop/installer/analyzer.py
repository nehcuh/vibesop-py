"""Repository analyzer for intelligent skill pack installation.

Analyzes Git repositories to discover skills, parse README instructions,
and identify setup requirements before installation.
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from vibesop.core.skills.parser import parse_skill_md

logger = logging.getLogger(__name__)


@dataclass
class RepoAnalysis:
    """Result of analyzing a skill pack repository."""

    pack_name: str
    source_url: str
    skill_files: list[Path] = field(default_factory=list)
    readme_path: Path | None = None
    readme_install_hint: str = ""
    setup_scripts: list[str] = field(default_factory=list)
    detected_namespace: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def skill_count(self) -> int:
        return len(self.skill_files)

    @property
    def has_readme(self) -> bool:
        return self.readme_path is not None

    def skill_ids(self) -> list[str]:
        """Extract skill IDs from discovered SKILL.md files."""
        ids = []
        for sf in self.skill_files:
            meta = parse_skill_md(sf)
            if meta:
                ids.append(meta.id)
            else:
                ids.append(sf.parent.name)
        return ids


class RepoAnalyzer:
    """Analyze a Git repository to extract skill pack metadata."""

    def analyze(self, url: str, pack_name: str | None = None) -> RepoAnalysis:
        """Clone and analyze a repository.

        Args:
            url: Git URL or HTTP(S) URL to repository
            pack_name: Optional pack name override

        Returns:
            RepoAnalysis with discovered information
        """
        inferred_name = pack_name or self._infer_pack_name(url)
        result = RepoAnalysis(pack_name=inferred_name, source_url=url)

        with tempfile.TemporaryDirectory(prefix="vibe-install-") as tmpdir:
            tmpdir_path = Path(tmpdir)
            clone_ok = self._git_clone(url, tmpdir_path)
            if not clone_ok:
                result.errors.append(f"Failed to clone repository: {url}")
                return result

            # Find README
            for readme_name in ("README.md", "README.rst", "README.txt", "README"):
                readme = tmpdir_path / readme_name
                if readme.exists():
                    result.readme_path = readme
                    result.readme_install_hint = self._extract_install_hint(readme)
                    break

            # Find SKILL.md files recursively
            result.skill_files = list(tmpdir_path.rglob("SKILL.md"))

            # Detect setup scripts
            for script_name in ("setup.py", "pyproject.toml", "package.json", "Makefile", "requirements.txt"):
                if (tmpdir_path / script_name).exists():
                    result.setup_scripts.append(script_name)

            # Infer namespace from first skill or directory structure
            if result.skill_files:
                meta = parse_skill_md(result.skill_files[0])
                if meta and meta.namespace and meta.namespace != "builtin":
                    result.detected_namespace = meta.namespace
                else:
                    result.detected_namespace = inferred_name

        return result

    def _git_clone(self, url: str, dest: Path) -> bool:
        """Shallow clone a Git repository."""
        try:
            # Support both git URLs and HTTPS URLs
            cmd = ["git", "clone", "--depth", "1", url, str(dest)]
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.debug(f"Git clone failed for {url}: {e.stderr}")
            return False
        except FileNotFoundError:
            result_msg = "git command not found"
            logger.debug(result_msg)
            return False
        except subprocess.TimeoutExpired:
            logger.debug(f"Git clone timed out for {url}")
            return False

    def _infer_pack_name(self, url: str) -> str:
        """Infer pack name from URL."""
        # Remove trailing .git and trailing slash
        clean = url.rstrip("/").removesuffix(".git")
        # Take last path segment
        if "/" in clean:
            return clean.split("/")[-1]
        return clean or "unknown-pack"

    def _extract_install_hint(self, readme_path: Path) -> str:
        """Extract installation instructions from README."""
        try:
            content = readme_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

        # Look for Installation section
        match = re.search(
            r"#+\s*[Ii]nstallation.*?(?:\n#+\s*|\Z)",
            content,
            re.DOTALL,
        )
        if match:
            section = match.group(0)
            # Limit length
            lines = section.split("\n")
            hint = "\n".join(lines[:10]).strip()
            return hint

        # Fallback: look for setup or usage mentions
        match = re.search(
            r"`pip install[^`]+`|`make[^`]+`|`npm install[^`]+`",
            content,
        )
        if match:
            return f"Setup command detected: {match.group(0)}"

        return "No explicit installation instructions found."
