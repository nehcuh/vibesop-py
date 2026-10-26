"""Tests for scripts/check_docs.py (the CI doc-links gate).

Every fixture case builds a throwaway repo (docs/ + README.md) under
``tmp_path`` and repoints the script's ``ROOT`` global at it. The real
repository tree is only ever read.

Load-bearing cases: anchors follow GitHub slug rules, fenced code blocks
and Rich console markup must not parse as links, and link resolution is
confined to the repo root — an out-of-root target is reported as broken
instead of being resolved against the runner's filesystem.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_docs.py"
spec = importlib.util.spec_from_file_location("check_docs", SCRIPT)
assert spec and spec.loader
cds = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cds
spec.loader.exec_module(cds)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "README.md").write_text("# Repo\n", encoding="utf-8")
    monkeypatch.setattr(cds, "ROOT", root)
    return root


def _posix(broken: list[str]) -> list[str]:
    """The checker prints ``Path`` objects — Windows uses backslashes."""
    return [item.replace("\\", "/") for item in broken]


def _doc(repo: Path, name: str, text: str) -> Path:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Real repository: the CI contract is zero broken references.
# --------------------------------------------------------------------------


def test_real_repo_has_no_broken_references() -> None:
    assert cds.check_broken_file_references() == []
    assert cds.check_readme_references() == []


# --------------------------------------------------------------------------
# File-existence truth table.
# --------------------------------------------------------------------------


def test_valid_relative_link_passes(repo: Path) -> None:
    _doc(repo, "docs/a.md", "[b](b.md)\n")
    _doc(repo, "docs/b.md", "# B\n")
    assert cds.check_broken_file_references() == []


def test_broken_relative_link_is_flagged(repo: Path) -> None:
    _doc(repo, "docs/a.md", "[b](missing.md)\n")
    assert _posix(cds.check_broken_file_references()) == ["docs/a.md: missing.md"]


def test_broken_root_absolute_link_is_flagged(repo: Path) -> None:
    _doc(repo, "docs/a.md", "[b](/docs/missing.md)\n")
    assert _posix(cds.check_broken_file_references()) == ["docs/a.md: /docs/missing.md"]


def test_http_and_fragment_links_are_skipped(repo: Path) -> None:
    _doc(repo, "docs/a.md", "[x](https://example.com/a.md) [y](#section)\n")
    assert cds.check_broken_file_references() == []


def test_readme_links_resolve_from_root(repo: Path) -> None:
    _doc(repo, "README.md", "[docs](docs/b.md)\n")
    _doc(repo, "docs/b.md", "# B\n")
    assert cds.check_readme_references() == []


# --------------------------------------------------------------------------
# Anchor truth table (GitHub slug rules).
# --------------------------------------------------------------------------


def test_existing_anchor_passes(repo: Path) -> None:
    _doc(repo, "docs/b.md", "## Real Heading\n")
    _doc(repo, "docs/a.md", "[b](b.md#real-heading)\n")
    assert cds.check_broken_file_references() == []


def test_missing_anchor_is_flagged(repo: Path) -> None:
    _doc(repo, "docs/b.md", "## Real Heading\n")
    _doc(repo, "docs/a.md", "[b](b.md#nope)\n")
    assert _posix(cds.check_broken_file_references()) == ["docs/a.md: b.md#nope (missing anchor)"]


# --------------------------------------------------------------------------
# False-positive guards.
# --------------------------------------------------------------------------


def test_rich_markup_is_not_a_link(repo: Path) -> None:
    _doc(repo, "docs/a.md", "[yellow](见上) [dim]({category})\n")
    assert cds.check_broken_file_references() == []


def test_fenced_markup_is_ignored(repo: Path) -> None:
    _doc(
        repo,
        "docs/a.md",
        "```python\nprint('[fake](missing.md)')\n```\n",
    )
    assert cds.check_broken_file_references() == []


def test_archive_dir_is_exempt(repo: Path) -> None:
    _doc(repo, "docs/archive/old.md", "[dead](missing.md)\n")
    assert cds.check_broken_file_references() == []


# --------------------------------------------------------------------------
# Repo-root confinement: out-of-root targets are broken, not resolved.
# --------------------------------------------------------------------------


def test_relative_escape_outside_root_is_flagged(repo: Path) -> None:
    """`../../../..` must be reported, not resolved against the runner fs."""
    escape = "../" * 8 + "etc/passwd"
    _doc(repo, "docs/a.md", f"[x]({escape})\n")
    assert _posix(cds.check_broken_file_references()) == [
        f"docs/a.md: {escape} (outside repo root)"
    ]


def test_root_absolute_escape_outside_root_is_flagged(repo: Path) -> None:
    escape = "/" + "../" * 6 + "etc/passwd"
    _doc(repo, "docs/a.md", f"[x]({escape})\n")
    assert _posix(cds.check_broken_file_references()) == [
        f"docs/a.md: {escape} (outside repo root)"
    ]


def test_symlinked_out_of_tree_target_is_allowed(repo: Path, tmp_path: Path) -> None:
    """Confinement is lexical by design: experiment records link targets
    that sit inside the tree lexically but symlink out to local data."""
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    try:
        (repo / "docs" / "data.md").symlink_to(outside)
    except OSError:
        pytest.skip("file symlinks not supported on this host")
    _doc(repo, "docs/a.md", "[x](data.md#outside)\n")
    assert cds.check_broken_file_references() == []
