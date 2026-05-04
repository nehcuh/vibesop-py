"""Repository analyzer for intelligent skill pack installation."""

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
        ids = []
        for sf in self.skill_files:
            meta = parse_skill_md(sf)
            ids.append(meta.id if meta else sf.parent.name)
        return ids


class RepoAnalyzer:
    def analyze(self, url: str, pack_name: str | None = None) -> RepoAnalysis:
        inferred_name = pack_name or self.infer_pack_name(url)
        result = RepoAnalysis(pack_name=inferred_name, source_url=url)

        with tempfile.TemporaryDirectory(prefix="vibe-install-") as tmpdir:
            tmpdir_path = Path(tmpdir)
            if not self.git_clone(url, tmpdir_path):
                result.errors.append(f"Failed to clone repository: {url}")
                return result

            for readme_name in ("README.md", "README.rst", "README.txt", "README"):
                readme = tmpdir_path / readme_name
                if readme.exists():
                    result.readme_path = readme
                    result.readme_install_hint = self._extract_install_hint(readme)
                    break

            result.skill_files = list(tmpdir_path.rglob("SKILL.md"))

            for script_name in (
                "setup.py", "pyproject.toml", "package.json",
                "Makefile", "requirements.txt",
            ):
                if (tmpdir_path / script_name).exists():
                    result.setup_scripts.append(script_name)

            for build_script in (".vibesop-build", "BUILD.sh", "setup.sh"):
                script_path = tmpdir_path / build_script
                if script_path.exists() and script_path.is_file():
                    result.setup_scripts.append(build_script)

            if result.skill_files:
                meta = parse_skill_md(result.skill_files[0])
                if meta and meta.namespace and meta.namespace != "builtin":
                    result.detected_namespace = meta.namespace
                else:
                    result.detected_namespace = inferred_name

        return result

    def git_clone(self, url: str, dest: Path) -> bool:
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", url, str(dest)],
                check=True, capture_output=True, text=True, timeout=60,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.debug(f"Git clone failed for {url}: {e.stderr}")
        except FileNotFoundError:
            logger.debug("git command not found")
        except subprocess.TimeoutExpired:
            logger.debug(f"Git clone timed out for {url}")
        return False

    def infer_pack_name(self, url: str) -> str:
        clean = url.rstrip("/").removesuffix(".git")
        if "/" in clean:
            return clean.split("/")[-1]
        return clean or "unknown-pack"

    def _extract_install_hint(self, readme_path: Path) -> str:
        try:
            content = readme_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

        match = re.search(
            r"#+\s*[Ii]nstallation.*?(?:\n#+\s*|\Z)", content, re.DOTALL,
        )
        if match:
            return "\n".join(match.group(0).split("\n")[:10]).strip()

        match = re.search(
            r"`pip install[^`]+`|`make[^`]+`|`npm install[^`]+`", content,
        )
        if match:
            return f"Setup command detected: {match.group(0)}"

        return "No explicit installation instructions found."
