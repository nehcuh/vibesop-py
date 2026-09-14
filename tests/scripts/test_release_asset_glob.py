"""GitHub Release / attest globs must not upload ``dist/.gitignore``.

v8.4.0 shipped ``default.gitignore`` because ``files: dist/*`` and
``subject-path: dist/*`` both match dotfiles (softprops and @actions/glob
use ``dot: true``). Stdlib ``glob.glob('dist/*')`` skips dotfiles and would
false-green this contract; matching uses ``fnmatch`` over ``iterdir()``.
"""

from __future__ import annotations

import fnmatch
import glob as stdlib_glob
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_YML = REPO_ROOT / ".github" / "workflows" / "release.yml"
DOTFILE_PATTERNS = {"dist/*", "dist/**", "dist/**/*"}


def _release_steps() -> list[dict[str, Any]]:
    data = yaml.safe_load(RELEASE_YML.read_text(encoding="utf-8"))
    steps = data["jobs"]["release"]["steps"]
    assert isinstance(steps, list)
    return steps


def _step_using(prefix: str) -> dict[str, Any]:
    for step in _release_steps():
        if str(step.get("uses", "")).startswith(prefix):
            return step
    raise AssertionError(f"release.yml has no step using {prefix}")


def _patterns(value: object) -> list[str]:
    assert isinstance(value, str) and value.strip(), value
    return [line.strip() for line in value.splitlines() if line.strip()]


def _github_like_match(pattern: str, dist: Path) -> set[str]:
    """Match ``dist/<glob>`` including hidden names (GitHub ``dot: true``)."""
    assert pattern.startswith("dist/"), pattern
    rel = pattern[len("dist/") :]
    names: set[str] = set()
    for path in dist.iterdir():
        if path.is_file() and fnmatch.fnmatch(path.name, rel):
            names.add(path.name)
    return names


def _fixture_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / ".gitignore").write_bytes(b"*")
    (dist / "vibesop-8.4.1-py3-none-any.whl").write_bytes(b"wheel")
    (dist / "vibesop-8.4.1.tar.gz").write_bytes(b"sdist")
    (dist / "vibesop-8.4.1-py3-none-any.whl.publish.attestation").write_bytes(b"attestation")
    (dist / "notes.txt").write_text("junk", encoding="utf-8")
    return dist


def test_stdlib_glob_skips_dotfiles_and_would_false_green(tmp_path: Path) -> None:
    """Guard the guard: stdlib ``glob.glob('dist/*')`` hides the v8.4.0 bug."""
    dist = _fixture_dist(tmp_path)
    stdlib_names = {Path(path).name for path in stdlib_glob.glob(str(dist / "*"))}
    assert ".gitignore" not in stdlib_names
    github_star = _github_like_match("dist/*", dist)
    assert ".gitignore" in github_star


def test_fnmatch_star_matches_gitignore() -> None:
    assert fnmatch.fnmatch(".gitignore", "*")
    assert not fnmatch.fnmatch(".gitignore", "*.whl")
    assert not fnmatch.fnmatch(".gitignore", "*.tar.gz")
    assert not fnmatch.fnmatch(".gitignore", "*.publish.attestation")


def test_release_files_are_structurally_dotfile_proof(tmp_path: Path) -> None:
    step = _step_using("softprops/action-gh-release@")
    patterns = _patterns(step["with"]["files"])
    assert patterns
    assert all(pattern not in DOTFILE_PATTERNS for pattern in patterns)
    dist = _fixture_dist(tmp_path)
    matched: set[str] = set()
    for pattern in patterns:
        matched |= _github_like_match(pattern, dist)
    assert ".gitignore" not in matched
    assert "notes.txt" not in matched
    assert "vibesop-8.4.1-py3-none-any.whl" in matched
    assert "vibesop-8.4.1.tar.gz" in matched
    assert "vibesop-8.4.1-py3-none-any.whl.publish.attestation" in matched


def test_attest_subject_path_excludes_dotfiles(tmp_path: Path) -> None:
    step = _step_using("actions/attest-build-provenance@")
    patterns = _patterns(step["with"]["subject-path"])
    assert patterns
    assert all(pattern not in DOTFILE_PATTERNS for pattern in patterns)
    dist = _fixture_dist(tmp_path)
    matched: set[str] = set()
    for pattern in patterns:
        matched |= _github_like_match(pattern, dist)
    assert ".gitignore" not in matched
    assert "vibesop-8.4.1-py3-none-any.whl" in matched
    assert "vibesop-8.4.1.tar.gz" in matched
    assert "vibesop-8.4.1-py3-none-any.whl.publish.attestation" not in matched


def test_release_upload_fails_closed_on_missing_assets() -> None:
    step = _step_using("softprops/action-gh-release@")
    assert step["with"].get("fail_on_unmatched_files") is True


def test_build_suppresses_uv_gitignore() -> None:
    build = next(step for step in _release_steps() if "uv build" in str(step.get("run", "")))
    assert "--no-create-gitignore" in str(build["run"])
