"""Tests for scripts/check_artifact_links.py (Lane E dangling-link guard).

The fixture is a real throwaway git repository: the guard's verdict is defined
in terms of `git ls-files`, so faking the index would test the fake instead of
the guard. Each test asserts the process exit code as well as the classifier
output — the exit code is the contract CI consumes.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_artifact_links.py"
spec = importlib.util.spec_from_file_location("check_artifact_links", SCRIPT)
assert spec and spec.loader
chal = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = chal  # dataclasses need the module registered
spec.loader.exec_module(chal)


def _git(root: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "lane-e",
        "GIT_AUTHOR_EMAIL": "lane-e@example.invalid",
        "GIT_COMMITTER_NAME": "lane-e",
        "GIT_COMMITTER_EMAIL": "lane-e@example.invalid",
        "HOME": str(root),
    }
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "-c", "init.templateDir=", *args],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """An empty git repo with a `docs/` dir and a `.omx/artifacts/` dir."""
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / ".omx" / "artifacts").mkdir(parents=True)
    _git(root, "init", "-q")
    return root


def _commit_all(root: Path) -> None:
    _git(root, "add", ".")
    _commit(root)


def _commit_paths(root: Path, *paths: str) -> None:
    """Commit only the given paths — leaves everything else untracked."""
    _git(root, "add", "--", *paths)
    _commit(root)


def _commit(root: Path) -> None:
    _git(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture")


def _run(root: Path, *args: str) -> tuple[int, str]:
    """Run the guard as a subprocess so the real exit code is exercised."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


# --------------------------------------------------------------------------
# The three cases the lane packet requires
# --------------------------------------------------------------------------


def test_tracked_artifact_reference_is_green(repo: Path) -> None:
    (repo / ".omx" / "artifacts" / "next-opt-design-v1.md").write_text("# design\n")
    (repo / "docs" / "roadmap.md").write_text(
        "> **当前锁**：`.omx/artifacts/next-opt-design-v1.md`\n"
    )
    _commit_all(repo)

    code, out = _run(repo)
    assert code == 0, out
    assert "1 ok, 0 dangling, 0 stale" in out


def test_untracked_artifact_reference_is_red(repo: Path) -> None:
    # The R3/R4 prereg incident: the artifact is written and cited, but only
    # the doc made it into the index (the old workflow needed `git add -f`).
    (repo / ".omx" / "artifacts" / "r4-prereg.md").write_text("# prereg\n")
    (repo / "docs" / "roadmap.md").write_text("see `.omx/artifacts/r4-prereg.md` for criteria\n")
    _commit_paths(repo, "docs/roadmap.md")
    assert (
        "r4-prereg.md"
        not in subprocess.run(
            ["git", "ls-files"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout
    )

    code, out = _run(repo)
    assert code == 1, out
    assert "DANGLING" in out
    assert "r4-prereg.md" in out

    # Tracking the artifact repairs it — no `git add -f` needed.
    _commit_paths(repo, ".omx/artifacts/r4-prereg.md")
    assert _run(repo)[0] == 0


def test_docs_without_artifact_references_are_green(repo: Path) -> None:
    (repo / "docs" / "notes.md").write_text("No artifacts here, just prose.\n")
    (repo / "README.md").write_text("# repo\n")
    _commit_all(repo)

    code, out = _run(repo)
    assert code == 0, out
    assert "no artifact references" in out


# --------------------------------------------------------------------------
# Verdict tiers, roots, and injection
# --------------------------------------------------------------------------


def test_stale_reference_warns_by_default_and_fails_under_strict(repo: Path) -> None:
    # A historical citation whose target is gone from both index and disk:
    # not repairable by `git add`, so it must not be fatal by default.
    (repo / "CHANGELOG.md").write_text("按 `.omx/artifacts/gate44-synthesis.md` v2.1 终稿实施。\n")
    _commit_all(repo)

    code, out = _run(repo)
    assert code == 0, out
    assert "stale" in out and "gate44-synthesis.md" in out

    strict_code, strict_out = _run(repo, "--strict")
    assert strict_code == 1, strict_out


def test_glob_reference_matching_a_tracked_file_is_green(repo: Path) -> None:
    (repo / ".omx" / "artifacts" / "gate7-review-claude.md").write_text("x\n")
    (repo / "docs" / "notes.md").write_text("全部材料在 `.omx/artifacts/gate7-*`。\n")
    _commit_all(repo)

    code, out = _run(repo)
    assert code == 0, out
    assert "0 dangling" in out


def test_glob_reference_predating_any_tracked_file_is_stale(repo: Path) -> None:
    (repo / "docs" / "notes.md").write_text("见 `.omx/artifacts/ask-grok-panel-*.md`。\n")
    _commit_all(repo)

    code, out = _run(repo)
    assert code == 0, out
    assert "ask-grok-panel-*.md" in out


def test_directory_reference_needs_a_tracked_file_under_it(repo: Path) -> None:
    (repo / ".omx" / "artifacts" / "health-20260909").mkdir()
    (repo / ".omx" / "artifacts" / "health-20260909" / "summary.md").write_text("x\n")
    (repo / "docs" / "check.md").write_text("见 `.omx/artifacts/health-20260909/`。\n")
    _commit_all(repo)

    # Tracked (committed) -> green.
    assert _run(repo)[0] == 0

    # Same shape, but the artifact never made it into the index.
    (repo / ".omx" / "artifacts" / "health-20260910").mkdir()
    (repo / ".omx" / "artifacts" / "health-20260910" / "summary.md").write_text("x\n")
    (repo / "docs" / "check.md").write_text("见 `.omx/artifacts/health-20260910/`。\n")
    _commit_paths(repo, "docs/check.md")
    code, out = _run(repo)
    assert code == 1, out
    assert "DANGLING" in out


def test_targets_restrict_the_scan(repo: Path) -> None:
    (repo / "docs" / "clean.md").write_text("nothing here\n")
    (repo / "README.md").write_text("see `.omx/artifacts/missing.md`\n")
    (repo / ".omx" / "artifacts" / "missing.md").write_text("x\n")
    _commit_paths(repo, "docs/clean.md", "README.md")

    code, out = _run(repo)
    assert code == 1, out
    assert "README.md" in out
    assert _run(repo, "--targets", "docs")[0] == 0


def test_untracked_markdown_is_not_scanned_by_default(repo: Path) -> None:
    # An uncommitted draft cannot fail the guard; the verdict equals what a
    # fresh clone would see.
    (repo / "docs" / "tracked.md").write_text("clean\n")
    _commit_all(repo)
    (repo / "docs" / "draft.md").write_text("see `.omx/artifacts/not-yet.md`\n")
    (repo / ".omx" / "artifacts" / "not-yet.md").write_text("x\n")

    assert _run(repo)[0] == 0
    code, out = _run(repo, "--include-untracked")
    assert code == 1, out
    assert "draft.md" in out


def test_missing_root_fails_closed(repo: Path) -> None:
    # Nothing scanned must not read as green.
    code, out = _run(repo, "--targets", "nowhere")
    assert code == 2, out
    assert "no markdown scanned" in out


def test_tracked_list_injection_bypasses_git(repo: Path, tmp_path: Path) -> None:
    (repo / "docs" / "notes.md").write_text("see `.omx/artifacts/ghost.md`\n")
    (repo / ".omx" / "artifacts" / "ghost.md").write_text("x\n")
    _commit_all(repo)

    injected = tmp_path / "ls-files.txt"
    injected.write_text(".omx/artifacts/ghost.md\ndocs/notes.md\n")
    code, out = _run(repo, "--tracked-list", str(injected))
    assert code == 0, out


# --------------------------------------------------------------------------
# Extraction / classification units
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("`.omx/artifacts/a.md`", [".omx/artifacts/a.md"]),
        ("[x](.omx/artifacts/b.md)", [".omx/artifacts/b.md"]),
        ("详见 .omx/artifacts/c.md。", [".omx/artifacts/c.md"]),
        ("按 `.omx/artifacts/gate34-*` 定稿", [".omx/artifacts/gate34-*"]),
        ("见 `.omx/artifacts/health-20260909/`", [".omx/artifacts/health-20260909/"]),
        # Template placeholder names no file -> skipped.
        ("`.omx/artifacts/evo-lane-<id>-handback.md`", []),
        # Bare directory mention -> skipped.
        ("`.omx/artifacts` 是落点", []),
        ("`.omx/tmp/x` 是短命目录", []),
    ],
)
def test_extract_targets(text: str, expected: list[str]) -> None:
    assert chal.extract_targets(text) == expected


def test_extract_targets_handles_multiple_and_punctuation() -> None:
    text = "见 `.omx/artifacts/a.md`、`.omx/artifacts/b.json`, (`.omx/artifacts/c.diff`)。"
    assert chal.extract_targets(text) == [
        ".omx/artifacts/a.md",
        ".omx/artifacts/b.json",
        ".omx/artifacts/c.diff",
    ]


def test_classify_kinds(tmp_path: Path) -> None:
    tracked = {".omx/artifacts/a.md", ".omx/artifacts/sub/b.md"}
    assert chal.classify(".omx/artifacts/a.md", tracked, tmp_path) == "ok"
    assert chal.classify(".omx/artifacts/sub/", tracked, tmp_path) == "ok"
    assert chal.classify(".omx/artifacts/*.md", tracked, tmp_path) == "ok"
    assert chal.classify(".omx/artifacts/nope.md", tracked, tmp_path) == "stale"

    (tmp_path / ".omx" / "artifacts").mkdir(parents=True)
    (tmp_path / ".omx" / "artifacts" / "here.md").write_text("x")
    assert chal.classify(".omx/artifacts/here.md", tracked, tmp_path) == "dangling"


def test_scan_is_green_on_empty_reference_set(repo: Path) -> None:
    (repo / "docs" / "a.md").write_text("nothing to see\n")
    _commit_all(repo)
    tracked = chal.list_tracked(repo)
    assert chal.scan(repo, ["docs"], tracked) == []


# --------------------------------------------------------------------------
# E1 boundary: the repo's own .gitignore, replayed in an isolated repo
# --------------------------------------------------------------------------
#
# This lives here because it is the same mechanism as the guard: it pins the
# persistence boundary so a future edit cannot silently reintroduce a blanket
# `.omx/` or `.claude/` ignore. Replaying the rules in a throwaway repo is
# also the only way to observe them without the machine-local
# `.git/info/exclude` that grok owns and removes separately.

REPO_GITIGNORE = Path(__file__).resolve().parents[2] / ".gitignore"


@pytest.mark.parametrize(
    ("path", "ignored"),
    [
        # Cited artifacts must be addable without `git add -f`.
        (".omx/artifacts/next-opt-design-v1.md", False),
        (".omx/artifacts/new-evidence.json", False),
        # Team-shared Claude Code config is now trackable.
        (".claude/commands/r3-r4-impl.md", False),
        (".claude/hooks/guard_protected_paths.py", False),
        # Short-lived OMX scratch stays out of the tree.
        (".omx/tmp/scratch.md", True),
        (".omx/scratch/scratch.md", True),
        (".omx/cache/blob.json", True),
        (".omx/runtime/state.json", True),
        (".omx/logs/run.log", True),
        (".omx/state/state.json", True),
        # Machine-local Claude Code state stays out of the tree.
        (".claude/settings.local.json", True),
        (".claude/worktrees/some-worktree/file.md", True),
        (".claude/scheduled_tasks.json", True),
    ],
)
def test_repo_gitignore_boundary(tmp_path: Path, path: str, ignored: bool) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".gitignore").write_text(REPO_GITIGNORE.read_text(encoding="utf-8"))
    _git(root, "init", "-q")

    proc = subprocess.run(
        ["git", "check-ignore", "-q", "--", path],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode in (0, 1), proc.stderr
    assert (proc.returncode == 0) is ignored, (
        f"{path}: expected ignored={ignored}, got exit {proc.returncode}"
    )


def test_repo_gitignore_does_not_ignore_omx_root(tmp_path: Path) -> None:
    """A blanket `.omx/` (or `.omx/artifacts/`) rule is a regression."""
    rules = [
        line.strip()
        for line in REPO_GITIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert ".omx/" not in rules
    assert ".omx/artifacts/" not in rules
    assert ".omx" not in rules
