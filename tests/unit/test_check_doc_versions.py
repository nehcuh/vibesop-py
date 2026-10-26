"""Tests for scripts/check_doc_versions.py (the CI doc-versions gate).

Every fixture case builds a throwaway repo (pyproject.toml + markdown tree)
under ``tmp_path`` and repoints the script's module globals at it — the
script has no CLI path override by design. The real repository tree is only
ever read.

The load-bearing cases: ``--fix`` must rewrite stale current-version
declarations but must NEVER reach historical/record files (rewriting them
would falsify point-in-time records), and the fixture-pack skip must keep
foreign skill frontmatter out of the app-version check.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_doc_versions.py"
spec = importlib.util.spec_from_file_location("check_doc_versions", SCRIPT)
assert spec and spec.loader
cdv = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cdv  # argparse/dataclasses need the module registered
spec.loader.exec_module(cdv)

EXPECTED = "9.9.9"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "pyproject.toml").write_text(f'version = "{EXPECTED}"\n', encoding="utf-8")
    monkeypatch.setattr(cdv, "PROJECT_ROOT", root)
    monkeypatch.setattr(cdv, "SOURCE_OF_TRUTH", root / "pyproject.toml")
    # main() parses sys.argv directly — never inherit pytest's own argv.
    monkeypatch.setattr(sys, "argv", ["check_doc_versions.py"])
    return root


def _run_check(repo: Path) -> int:
    return cdv.main()


def _run_fix(repo: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "argv", ["check_doc_versions.py", "--fix"])
    return cdv.main()


# --------------------------------------------------------------------------
# Real repository: the CI contract is exit 0 on the live tree.
# --------------------------------------------------------------------------


def test_real_repo_is_green(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["check_doc_versions.py"])
    assert cdv.main() == 0
    assert "PASS" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Check-side truth table.
# --------------------------------------------------------------------------


def test_stale_declaration_is_red(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "docs" / "guide.md").write_text("> **Version**: 8.0.0\n", encoding="utf-8")
    assert _run_check(repo) == 1
    out = capsys.readouterr().out
    # Substring without path separators: Windows prints docs\guide.md.
    assert "MISMATCH" in out and "guide.md:1" in out


def test_matching_declaration_is_green(repo: Path) -> None:
    (repo / "docs" / "guide.md").write_text(f"> **Version**: {EXPECTED}\n", encoding="utf-8")
    assert _run_check(repo) == 0


def test_since_annotation_is_exempt(repo: Path) -> None:
    """``(v5.3.0+)`` is a since-annotation, not a current-version claim."""
    (repo / "docs" / "guide.md").write_text("Available since (v5.3.0+).\n", encoding="utf-8")
    assert _run_check(repo) == 0


def test_fenced_code_examples_are_ignored(repo: Path) -> None:
    (repo / "docs" / "guide.md").write_text(
        "```bash\npip install pkg@v1.0.0\n```\n", encoding="utf-8"
    )
    assert _run_check(repo) == 0


def test_historical_record_tree_is_exempt(repo: Path) -> None:
    reviews = repo / "docs" / "reviews"
    reviews.mkdir()
    (reviews / "gate1.md").write_text("> **Version**: 8.0.0\n", encoding="utf-8")
    assert _run_check(repo) == 0


def test_fixture_pack_frontmatter_is_skipped(repo: Path) -> None:
    """Foreign skill frontmatter ``version:`` is fixture config, not app version."""
    pack = repo / "tests" / "fixtures" / "benchmark-pack" / "quokka-todo"
    pack.mkdir(parents=True)
    (pack / "SKILL.md").write_text(
        "---\nid: benchpack/quokka-todo\nversion: 1.0.0\n---\n", encoding="utf-8"
    )
    assert _run_check(repo) == 0


def test_generated_files_are_exempt(repo: Path) -> None:
    (repo / "AGENTS.md").write_text("> **Version**: 1.0.0\n", encoding="utf-8")
    assert _run_check(repo) == 0


# --------------------------------------------------------------------------
# Fix-side: narrow rewrites, historical files untouchable.
# --------------------------------------------------------------------------


def test_fix_rewrites_stale_declaration(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    guide = repo / "docs" / "guide.md"
    guide.write_text("> **Version**: 8.0.0\n", encoding="utf-8")
    assert _run_fix(repo, monkeypatch) == 0
    assert f"> **Version**: {EXPECTED}\n" == guide.read_text(encoding="utf-8")


def test_fix_strips_dev_suffix(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    guide = repo / "docs" / "guide.md"
    guide.write_text("> **Version**: 8.0.0.dev0\n", encoding="utf-8")
    assert _run_fix(repo, monkeypatch) == 0
    assert f"> **Version**: {EXPECTED}\n" == guide.read_text(encoding="utf-8")


def test_fix_never_touches_historical_files(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The safety boundary: --fix must not falsify point-in-time records."""
    review = repo / "docs" / "reviews" / "gate1.md"
    original = "> **Version**: 8.0.0\n\nDated gate record.\n"
    review.parent.mkdir(parents=True, exist_ok=True)
    review.write_text(original, encoding="utf-8")

    assert _run_fix(repo, monkeypatch) == 0
    assert original == review.read_text(encoding="utf-8")


def test_fix_never_touches_since_annotations(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    guide = repo / "docs" / "guide.md"
    original = "Available since (v5.3.0+).\n"
    guide.write_text(original, encoding="utf-8")

    assert _run_fix(repo, monkeypatch) == 0
    assert original == guide.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Input failures fail closed.
# --------------------------------------------------------------------------


def test_missing_pyproject_version_exits(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    monkeypatch.setattr(cdv, "SOURCE_OF_TRUTH", repo / "empty.toml")
    (repo / "empty.toml").write_text("", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        cdv.get_expected_version()
    assert exc.value.code == 1
    assert "Could not find version" in capsys.readouterr().err
