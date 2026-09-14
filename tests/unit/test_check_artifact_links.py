"""Tests for scripts/check_artifact_links.py (dangling-link guard).

The fixture is a real throwaway git repository: the guard's verdict is defined
in terms of `git ls-files`, so faking the index would test the fake instead of
the guard. Each test asserts the process exit code as well as the classifier
output — the exit code is the contract callers consume.

Encoding policy (Lane B, vs the source commit's locale-dependent `text=True`):
- `git ls-files -z` bytes → UTF-8 + surrogateescape (lossless)
- `--tracked-list` file → UTF-8 strict; UnicodeDecodeError → exit 2
- markdown files → UTF-8 strict; OSError / UnicodeDecodeError → exit 2
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_artifact_links.py"
spec = importlib.util.spec_from_file_location("check_artifact_links", SCRIPT)
assert spec and spec.loader
chal = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = chal  # dataclasses need the module registered
spec.loader.exec_module(chal)

REPO_GITIGNORE = Path(__file__).resolve().parents[2] / ".gitignore"


def _git(root: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "lane-b",
        "GIT_AUTHOR_EMAIL": "lane-b@example.invalid",
        "GIT_COMMITTER_NAME": "lane-b",
        "GIT_COMMITTER_EMAIL": "lane-b@example.invalid",
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
    assert "docs/roadmap.md:1:" in out

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
    assert "CHANGELOG.md:1:" in out

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
    assert "stale" in out
    assert "DANGLING" not in out


def test_glob_matching_untracked_on_disk_file_is_dangling(repo: Path) -> None:
    """A glob with no tracked match but a real untracked file is dangling.

    `(root / 'foo-*').exists()` is the wrong check: it looks for a literal
    filename containing `*`. The guard must glob under `.omx/artifacts`.
    """
    (repo / ".omx" / "artifacts" / "foo-bar.md").write_text("x\n")
    (repo / "docs" / "notes.md").write_text("见 `.omx/artifacts/foo-*`。\n")
    _commit_paths(repo, "docs/notes.md")
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert "foo-bar.md" not in tracked

    code, out = _run(repo)
    assert code == 1, out
    assert "DANGLING" in out
    assert "foo-*" in out
    assert "docs/notes.md:1:" in out


def test_glob_does_not_match_outside_artifact_root(tmp_path: Path) -> None:
    """On-disk glob matching must not traverse out of `.omx/artifacts`."""
    artifact_root = tmp_path / ".omx" / "artifacts"
    artifact_root.mkdir(parents=True)
    (tmp_path / "secret.md").write_text("x\n")
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "foo-bar.md").write_text("x\n")
    tracked: set[str] = set()

    assert chal.classify(".omx/artifacts/../*", tracked, tmp_path) == "stale"
    assert chal.classify(".omx/artifacts/../outside/*", tracked, tmp_path) == "stale"
    assert chal.classify(".omx/artifacts/../secret.md", tracked, tmp_path) != "ok"

    (artifact_root / "foo-1.md").write_text("x\n")
    assert chal.classify(".omx/artifacts/foo-*", tracked, tmp_path) == "dangling"


def test_directory_symlink_inside_artifacts_is_not_a_glob_match(
    tmp_path: Path, symlink_supported: bool
) -> None:
    """A dir symlink under `.omx/artifacts` must not contribute outside files."""
    if not symlink_supported:
        pytest.skip("directory symlinks not supported on this host")
    artifact_root = tmp_path / ".omx" / "artifacts"
    artifact_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "foo-bar.md").write_text("x\n")
    (artifact_root / "escape").symlink_to(outside, target_is_directory=True)
    tracked: set[str] = set()

    assert chal.classify(".omx/artifacts/foo-*", tracked, tmp_path) == "stale"
    assert chal.classify(".omx/artifacts/escape/*", tracked, tmp_path) == "stale"
    (artifact_root / "foo-in.md").write_text("x\n")
    assert chal.classify(".omx/artifacts/foo-*", tracked, tmp_path) == "dangling"


def test_artifact_root_symlink_outside_fails_closed(
    tmp_path: Path, symlink_supported: bool
) -> None:
    """If `.omx/artifacts` itself resolves outside the repo, fail closed."""
    if not symlink_supported:
        pytest.skip("directory symlinks not supported on this host")
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    (outside / "foo-bar.md").write_text("x\n")
    (repo / ".omx").mkdir()
    (repo / ".omx" / "artifacts").symlink_to(outside, target_is_directory=True)

    with pytest.raises(chal.GuardError, match="outside"):
        chal.classify(".omx/artifacts/foo-*", set(), repo)


def test_artifact_root_symlink_outside_cli_exits_2(
    repo: Path, tmp_path: Path, symlink_supported: bool
) -> None:
    if not symlink_supported:
        pytest.skip("directory symlinks not supported on this host")
    (repo / "docs" / "notes.md").write_text("见 `.omx/artifacts/foo-*`。\n")
    _commit_paths(repo, "docs/notes.md")
    outside = tmp_path / "outside-artifacts"
    outside.mkdir()
    (outside / "foo-bar.md").write_text("x\n")
    artifacts = repo / ".omx" / "artifacts"
    artifacts.rmdir()
    artifacts.symlink_to(outside, target_is_directory=True)

    code, out = _run(repo, "--targets", "docs")
    assert code == 2, out
    assert "Traceback" not in out
    assert "outside" in out.lower()


def test_os_walk_onerror_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Listing errors during on-disk glob matching must raise GuardError."""
    (tmp_path / ".omx" / "artifacts").mkdir(parents=True)
    called = {"onerror": False}

    def fake_walk(*args: object, **kwargs: object) -> Iterator[tuple[str, list[str], list[str]]]:
        onerror = kwargs.get("onerror")
        assert onerror is not None, "os.walk must receive an onerror callback"
        assert callable(onerror)
        called["onerror"] = True
        onerror(PermissionError("permission denied"))
        yield from ()

    monkeypatch.setattr(chal.os, "walk", fake_walk)
    with pytest.raises(chal.GuardError, match="permission denied"):
        chal.classify(".omx/artifacts/foo-*", set(), tmp_path)
    assert called["onerror"] is True


def test_out_of_root_relative_target_fails_closed(repo: Path, tmp_path: Path) -> None:
    (repo / "docs" / "notes.md").write_text("clean\n")
    _commit_all(repo)
    (tmp_path / "outside.md").write_text("see `.omx/artifacts/x.md`\n")

    code, out = _run(repo, "--targets", "../outside.md")
    assert code == 2, out
    assert "Traceback" not in out
    assert "outside" in out.lower()
    assert "no markdown scanned" not in out


def test_out_of_root_missing_relative_target_fails_closed(repo: Path) -> None:
    """A missing out-of-root path is still a bad --targets argument, not a skip."""
    (repo / "docs" / "notes.md").write_text("clean\n")
    _commit_all(repo)

    code, out = _run(repo, "--targets", "../no-such-outside.md")
    assert code == 2, out
    assert "Traceback" not in out
    assert "outside" in out.lower()
    assert "no markdown scanned" not in out


def test_out_of_root_absolute_target_fails_closed(repo: Path, tmp_path: Path) -> None:
    (repo / "docs" / "notes.md").write_text("clean\n")
    _commit_all(repo)
    outside = tmp_path / "outside.md"
    outside.write_text("see `.omx/artifacts/x.md`\n")

    code, out = _run(repo, "--targets", str(outside))
    assert code == 2, out
    assert "Traceback" not in out


def test_in_root_absolute_target_still_works(repo: Path) -> None:
    (repo / "docs" / "notes.md").write_text("clean\n")
    _commit_all(repo)

    code, out = _run(repo, "--targets", str((repo / "docs").resolve()))
    assert code == 0, out
    assert "Traceback" not in out


def test_self_symlink_loop_target_fails_closed(repo: Path) -> None:
    """Path.resolve() RuntimeError on a self-symlink must be exit 2, no traceback."""
    loop = repo / "docs" / "loop.md"
    try:
        loop.symlink_to(loop)
    except OSError:
        pytest.skip("file symlinks not supported on this host")
    (repo / "docs" / "notes.md").write_text("clean\n")
    _commit_paths(repo, "docs/notes.md")

    code, out = _run(repo, "--targets", "docs/loop.md")
    assert code == 2, out
    assert "Traceback" not in out
    assert "cannot resolve" in out.lower() or "symlink" in out.lower()


def test_root_symlink_loop_cli_exits_2(tmp_path: Path, symlink_supported: bool) -> None:
    """A self-loop --root must be exit 2 with no traceback."""
    if not symlink_supported:
        pytest.skip("directory symlinks not supported on this host")
    loop = tmp_path / "loop-root"
    try:
        loop.symlink_to(loop)
    except OSError:
        pytest.skip("file symlinks not supported on this host")

    code, out = _run(loop)
    assert code == 2, out
    assert "Traceback" not in out
    assert "cannot resolve" in out.lower() or "symlink" in out.lower()


def test_artifact_root_symlink_loop_cli_exits_2(repo: Path, symlink_supported: bool) -> None:
    """A self-loop `.omx/artifacts` must be exit 2 with no traceback."""
    if not symlink_supported:
        pytest.skip("directory symlinks not supported on this host")
    (repo / "docs" / "notes.md").write_text("见 `.omx/artifacts/foo-*`。\n")
    _commit_paths(repo, "docs/notes.md")
    artifacts = repo / ".omx" / "artifacts"
    artifacts.rmdir()
    try:
        artifacts.symlink_to(artifacts, target_is_directory=True)
    except OSError:
        pytest.skip("directory self-symlinks not supported on this host")

    code, out = _run(repo, "--targets", "docs")
    assert code == 2, out
    assert "Traceback" not in out
    assert "cannot resolve" in out.lower() or "symlink" in out.lower()


def test_markdown_fragment_validates_underlying_file(repo: Path) -> None:
    (repo / ".omx" / "artifacts" / "report.md").write_text("# report\n")
    (repo / "docs" / "notes.md").write_text("[see](.omx/artifacts/report.md#section)\n")
    _commit_all(repo)

    code, out = _run(repo)
    assert code == 0, out
    assert "1 ok, 0 dangling, 0 stale" in out


@pytest.mark.parametrize("query", ["raw", "download", "raw=1"])
def test_markdown_query_string_validates_underlying_file(repo: Path, query: str) -> None:
    (repo / ".omx" / "artifacts" / "report.md").write_text("# report\n")
    (repo / "docs" / "notes.md").write_text(f"[see](.omx/artifacts/report.md?{query})\n")
    _commit_all(repo)

    code, out = _run(repo)
    assert code == 0, out
    assert "1 ok, 0 dangling, 0 stale" in out


def test_markdown_fragment_on_untracked_file_is_dangling(repo: Path) -> None:
    (repo / ".omx" / "artifacts" / "report.md").write_text("# report\n")
    (repo / "docs" / "notes.md").write_text("[see](.omx/artifacts/report.md#section)\n")
    _commit_paths(repo, "docs/notes.md")

    refs = chal.scan(repo, ["docs"], chal.list_tracked(repo))
    assert [ref.target for ref in refs] == [".omx/artifacts/report.md"]
    assert refs[0].status == "dangling"

    code, out = _run(repo)
    assert code == 1, out
    assert "DANGLING" in out
    assert "report.md" in out


@pytest.mark.parametrize("query", ["raw", "download"])
def test_query_string_without_key_value_on_untracked_file_is_dangling(
    repo: Path, query: str
) -> None:
    """Markdown link `report.md?raw` / `?download` must validate `report.md`.

    An untracked on-disk `report.md` is dangling / exit 1, not stale/green.
    Backticked lone flags are globs; this contract is for link destinations.
    """
    (repo / ".omx" / "artifacts" / "report.md").write_text("# report\n")
    (repo / "docs" / "notes.md").write_text(f"[see](.omx/artifacts/report.md?{query})\n")
    _commit_paths(repo, "docs/notes.md")
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert "report.md" not in tracked

    refs = chal.scan(repo, ["docs"], chal.list_tracked(repo))
    assert [ref.target for ref in refs] == [".omx/artifacts/report.md"]
    assert refs[0].kind == "file"
    assert refs[0].status == "dangling"

    code, out = _run(repo)
    assert code == 1, out
    assert "DANGLING" in out
    assert ".omx/artifacts/report.md" in out
    assert f"report.md?{query}" not in out
    assert "0 stale" in out


# Inline / reference Markdown destinations that the adjacent-`](` guard missed.
# `{query}` is substituted with `raw` or `download`.
_MD_DESTINATION_FORMS = (
    "[x](./.omx/artifacts/report.md?{query})",
    "[x]( .omx/artifacts/report.md?{query})",
    "[x]( ./.omx/artifacts/report.md?{query})",
    "[x](<./.omx/artifacts/report.md?{query}>)",
    "[x]( <.omx/artifacts/report.md?{query}> )",
    "[x]( <./.omx/artifacts/report.md?{query}> )",
    "[x](< .omx/artifacts/report.md?{query}>)",
    "[r]: .omx/artifacts/report.md?{query}",
    "[r]: ./.omx/artifacts/report.md?{query}",
    "[r]: <.omx/artifacts/report.md?{query}>",
    "[r]: <./.omx/artifacts/report.md?{query}>",
    "[r]:.omx/artifacts/report.md?{query}",
    "  [r]: .omx/artifacts/report.md?{query}",
    "   [r]: .omx/artifacts/report.md?{query}",
)


@pytest.mark.parametrize("form", _MD_DESTINATION_FORMS)
@pytest.mark.parametrize("query", ["raw", "download"])
def test_untracked_file_cited_via_markdown_destination_form_is_dangling(
    repo: Path, form: str, query: str
) -> None:
    """Each Markdown destination/definition form must fail closed on untracked files.

    `report.md?raw` / `?download` as a glob against on-disk `report.md` is a
    miss, so a missed destination classification degrades DANGLING/exit 1
    into stale/exit 0.
    """
    (repo / ".omx" / "artifacts" / "report.md").write_text("# report\n")
    (repo / "docs" / "notes.md").write_text(form.format(query=query) + "\n")
    _commit_paths(repo, "docs/notes.md")
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert "report.md" not in tracked

    refs = chal.scan(repo, ["docs"], chal.list_tracked(repo))
    assert [ref.target for ref in refs] == [".omx/artifacts/report.md"]
    assert refs[0].kind == "file"
    assert refs[0].status == "dangling"

    code, out = _run(repo)
    assert code == 1, out
    assert "DANGLING" in out
    assert ".omx/artifacts/report.md" in out
    assert f"report.md?{query}" not in out
    assert "0 stale" in out


@pytest.mark.parametrize(
    "form",
    [
        "[x](./.omx/artifacts/report.md?{query})",
        "[x]( .omx/artifacts/report.md?{query})",
        "[r]: .omx/artifacts/report.md?{query}",
    ],
)
@pytest.mark.parametrize("query", ["raw", "download"])
def test_tracked_file_cited_via_markdown_destination_form_is_green(
    repo: Path, form: str, query: str
) -> None:
    (repo / ".omx" / "artifacts" / "report.md").write_text("# report\n")
    (repo / "docs" / "notes.md").write_text(form.format(query=query) + "\n")
    _commit_all(repo)

    refs = chal.scan(repo, ["docs"], chal.list_tracked(repo))
    assert [ref.target for ref in refs] == [".omx/artifacts/report.md"]
    assert refs[0].kind == "file"
    assert refs[0].status == "ok"

    code, out = _run(repo)
    assert code == 0, out
    assert "1 ok, 0 dangling, 0 stale" in out


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
    assert "Traceback" not in out


def test_tracked_list_injection_bypasses_git(repo: Path, tmp_path: Path) -> None:
    (repo / "docs" / "notes.md").write_text("see `.omx/artifacts/ghost.md`\n")
    (repo / ".omx" / "artifacts" / "ghost.md").write_text("x\n")
    _commit_all(repo)

    injected = tmp_path / "ls-files.txt"
    injected.write_text(".omx/artifacts/ghost.md\ndocs/notes.md\n")
    code, out = _run(repo, "--tracked-list", str(injected))
    assert code == 0, out


def test_missing_tracked_list_fails_closed(repo: Path, tmp_path: Path) -> None:
    (repo / "docs" / "notes.md").write_text("clean\n", encoding="utf-8")
    _commit_all(repo)
    missing = tmp_path / "no-such-list.txt"
    code, out = _run(repo, "--tracked-list", str(missing))
    assert code == 2, out
    assert "Traceback" not in out


def test_unreadable_tracked_list_fails_closed(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo / "docs" / "notes.md").write_text("clean\n", encoding="utf-8")
    _commit_all(repo)
    injected = tmp_path / "ls-files.txt"
    injected.write_text("docs/notes.md\n", encoding="utf-8")
    target = injected.resolve()
    original = Path.read_text

    def fake_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.resolve() == target:
            raise OSError("permission denied")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    assert chal.main(["--root", str(repo), "--tracked-list", str(injected)]) == 2


def test_invalid_utf8_tracked_list_fails_closed(repo: Path, tmp_path: Path) -> None:
    (repo / "docs" / "notes.md").write_text("clean\n", encoding="utf-8")
    _commit_all(repo)
    injected = tmp_path / "ls-files.txt"
    injected.write_bytes(b".omx/artifacts/\xff.md\n")
    code, out = _run(repo, "--tracked-list", str(injected))
    assert code == 2, out
    assert "UTF-8" in out
    assert "Traceback" not in out


def test_invalid_utf8_markdown_fails_closed(repo: Path) -> None:
    (repo / "docs" / "notes.md").write_bytes(b"see `.omx/artifacts/a.md` \xff\xfe")
    _commit_all(repo)
    code, out = _run(repo)
    assert code == 2, out
    assert "UTF-8" in out
    assert "Traceback" not in out


def test_unreadable_markdown_fails_closed(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo / "docs" / "notes.md").write_text("clean\n", encoding="utf-8")
    _commit_all(repo)
    target = (repo / "docs" / "notes.md").resolve()
    original = Path.read_text

    def fake_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.resolve() == target:
            raise OSError("permission denied")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    assert chal.main(["--root", str(repo)]) == 2


def test_git_ls_files_failure_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "not-a-repo"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "notes.md").write_text("clean\n", encoding="utf-8")
    code, out = _run(root)
    assert code == 2, out
    assert "Traceback" not in out


# --------------------------------------------------------------------------
# Extraction / classification units
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("`.omx/artifacts/a.md`", [".omx/artifacts/a.md"]),
        ("[x](.omx/artifacts/b.md)", [".omx/artifacts/b.md"]),
        ("[x](.omx/artifacts/report.md#section)", [".omx/artifacts/report.md"]),
        ("[x](.omx/artifacts/report.md?raw=1)", [".omx/artifacts/report.md"]),
        ("[x](.omx/artifacts/report.md?raw)", [".omx/artifacts/report.md"]),
        ("[x](.omx/artifacts/report.md?download)", [".omx/artifacts/report.md"]),
        ("[x](<.omx/artifacts/report.md?raw>)", [".omx/artifacts/report.md"]),
        ("[x](./.omx/artifacts/report.md?raw)", [".omx/artifacts/report.md"]),
        ("[x]( .omx/artifacts/report.md?raw)", [".omx/artifacts/report.md"]),
        ("[x]( ./.omx/artifacts/report.md?raw)", [".omx/artifacts/report.md"]),
        ("[x](<./.omx/artifacts/report.md?raw>)", [".omx/artifacts/report.md"]),
        ("[x]( <.omx/artifacts/report.md?raw> )", [".omx/artifacts/report.md"]),
        ("[x]( <./.omx/artifacts/report.md?raw> )", [".omx/artifacts/report.md"]),
        ("[x](< .omx/artifacts/report.md?raw >)", [".omx/artifacts/report.md"]),
        ("[r]: .omx/artifacts/report.md?raw", [".omx/artifacts/report.md"]),
        ("[r]: ./.omx/artifacts/report.md?raw", [".omx/artifacts/report.md"]),
        ("[r]: <.omx/artifacts/report.md?raw>", [".omx/artifacts/report.md"]),
        ("[r]: <./.omx/artifacts/report.md?raw>", [".omx/artifacts/report.md"]),
        ("[r]:.omx/artifacts/report.md?raw", [".omx/artifacts/report.md"]),
        ("  [r]: .omx/artifacts/report.md?raw", [".omx/artifacts/report.md"]),
        ("   [r]: .omx/artifacts/report.md?download", [".omx/artifacts/report.md"]),
        ("详见 .omx/artifacts/c.md。", [".omx/artifacts/c.md"]),
        ("按 `.omx/artifacts/gate34-*` 定稿", [".omx/artifacts/gate34-*"]),
        # Backtick/bare: a lone '?' is a glob, even after a file extension or
        # dotted stem. Only an explicit key=value query is stripped.
        ("`.omx/artifacts/gate7-?.md`", [".omx/artifacts/gate7-?.md"]),
        ("`.omx/artifacts/v1.2-?.md`", [".omx/artifacts/v1.2-?.md"]),
        ("`.omx/artifacts/v1.2?.md`", [".omx/artifacts/v1.2?.md"]),
        ("`.omx/artifacts/report.v2?.md`", [".omx/artifacts/report.v2?.md"]),
        ("`.omx/artifacts/report.md?raw`", [".omx/artifacts/report.md?raw"]),
        ("`.omx/artifacts/report.md?raw=1`", [".omx/artifacts/report.md"]),
        (".omx/artifacts/v1.2?.md", [".omx/artifacts/v1.2?.md"]),
        (".omx/artifacts/report.v2?.md", [".omx/artifacts/report.v2?.md"]),
        ("见 .omx/artifacts/report.md?raw。", [".omx/artifacts/report.md?raw"]),
        ("./.omx/artifacts/report.md?raw", [".omx/artifacts/report.md?raw"]),
        ("<.omx/artifacts/report.md?raw>", [".omx/artifacts/report.md?raw"]),
        ("[r] .omx/artifacts/report.md?raw", [".omx/artifacts/report.md?raw"]),
        ("see [r]: .omx/artifacts/report.md?raw", [".omx/artifacts/report.md?raw"]),
        ("    [r]: .omx/artifacts/report.md?raw", [".omx/artifacts/report.md?raw"]),
        ("label: .omx/artifacts/report.md?raw", [".omx/artifacts/report.md?raw"]),
        ("见 .omx/artifacts/report.md?foo=bar。", [".omx/artifacts/report.md"]),
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


@pytest.mark.parametrize(
    ("text", "expected", "kind"),
    [
        ("[x](.omx/artifacts/report.md?raw)", ".omx/artifacts/report.md", "file"),
        ("[x](.omx/artifacts/report.md?download)", ".omx/artifacts/report.md", "file"),
        ("[x](./.omx/artifacts/report.md?raw)", ".omx/artifacts/report.md", "file"),
        ("[x]( .omx/artifacts/report.md?raw)", ".omx/artifacts/report.md", "file"),
        ("[x]( ./.omx/artifacts/report.md?download)", ".omx/artifacts/report.md", "file"),
        ("[x](<./.omx/artifacts/report.md?raw>)", ".omx/artifacts/report.md", "file"),
        ("[x]( <.omx/artifacts/report.md?raw> )", ".omx/artifacts/report.md", "file"),
        ("[x]( <./.omx/artifacts/report.md?download> )", ".omx/artifacts/report.md", "file"),
        ("[x](< .omx/artifacts/report.md?raw >)", ".omx/artifacts/report.md", "file"),
        ("[r]: .omx/artifacts/report.md?raw", ".omx/artifacts/report.md", "file"),
        ("[r]: ./.omx/artifacts/report.md?download", ".omx/artifacts/report.md", "file"),
        ("[r]: <.omx/artifacts/report.md?raw>", ".omx/artifacts/report.md", "file"),
        ("[r]: <./.omx/artifacts/report.md?raw>", ".omx/artifacts/report.md", "file"),
        ("[r]:.omx/artifacts/report.md?raw", ".omx/artifacts/report.md", "file"),
        ("  [r]: .omx/artifacts/report.md?raw", ".omx/artifacts/report.md", "file"),
        ("   [r]: .omx/artifacts/report.md?download", ".omx/artifacts/report.md", "file"),
        ("`.omx/artifacts/report.md?raw`", ".omx/artifacts/report.md?raw", "glob"),
        ("./.omx/artifacts/report.md?raw", ".omx/artifacts/report.md?raw", "glob"),
        ("<.omx/artifacts/report.md?raw>", ".omx/artifacts/report.md?raw", "glob"),
        ("[r] .omx/artifacts/report.md?raw", ".omx/artifacts/report.md?raw", "glob"),
        ("see [r]: .omx/artifacts/report.md?raw", ".omx/artifacts/report.md?raw", "glob"),
        ("    [r]: .omx/artifacts/report.md?raw", ".omx/artifacts/report.md?raw", "glob"),
        ("label: .omx/artifacts/report.md?raw", ".omx/artifacts/report.md?raw", "glob"),
        ("`.omx/artifacts/gate7-?.md`", ".omx/artifacts/gate7-?.md", "glob"),
        ("`.omx/artifacts/v1.2?.md`", ".omx/artifacts/v1.2?.md", "glob"),
        ("`.omx/artifacts/report.v2?.md`", ".omx/artifacts/report.v2?.md", "glob"),
        ("`.omx/artifacts/report.md?raw=1`", ".omx/artifacts/report.md", "file"),
    ],
)
def test_query_stripping_is_context_aware(text: str, expected: str, kind: str) -> None:
    """Markdown links strip lone query flags; backtick/bare keep them as globs."""
    found = chal.extract_targets(text)
    assert found == [expected]
    assert chal._kind(found[0]) == kind


def test_resolve_value_error_is_invalid_root_or_invalid_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ValueError from Path.resolve is owned by _resolve_path.

    Roots map to invalid_root; every other `what` maps to invalid_target.
    The dead `root / target` join try/except is gone — this is the boundary.
    """

    def boom(self: Path, strict: bool = False) -> Path:
        raise ValueError("embedded NUL")

    monkeypatch.setattr(Path, "resolve", boom)

    with pytest.raises(chal.GuardError, match=r"invalid_root") as root_exc:
        chal._resolve_path(tmp_path, what="repository root")
    assert "invalid_target" not in str(root_exc.value)

    with pytest.raises(chal.GuardError, match=r"invalid_target") as target_exc:
        chal._resolve_path(tmp_path / "docs", what="target 'docs'")
    assert "invalid_root" not in str(target_exc.value)


def test_classify_kinds(tmp_path: Path) -> None:
    tracked = {".omx/artifacts/a.md", ".omx/artifacts/sub/b.md"}
    assert chal.classify(".omx/artifacts/a.md", tracked, tmp_path) == "ok"
    assert chal.classify(".omx/artifacts/sub/", tracked, tmp_path) == "ok"
    assert chal.classify(".omx/artifacts/*.md", tracked, tmp_path) == "ok"
    assert chal.classify(".omx/artifacts/nope.md", tracked, tmp_path) == "stale"

    (tmp_path / ".omx" / "artifacts").mkdir(parents=True)
    (tmp_path / ".omx" / "artifacts" / "here.md").write_text("x")
    assert chal.classify(".omx/artifacts/here.md", tracked, tmp_path) == "dangling"
    (tmp_path / ".omx" / "artifacts" / "foo-bar.md").write_text("x")
    assert chal.classify(".omx/artifacts/foo-*", tracked, tmp_path) == "dangling"
    assert chal.classify(".omx/artifacts/nope-*", tracked, tmp_path) == "stale"


def test_scan_is_green_on_empty_reference_set(repo: Path) -> None:
    (repo / "docs" / "a.md").write_text("nothing to see\n")
    _commit_all(repo)
    tracked = chal.list_tracked(repo)
    assert chal.scan(repo, ["docs"], tracked) == []


# --------------------------------------------------------------------------
# Unicode paths: real git repo + Windows cp1252 locale regression
# --------------------------------------------------------------------------


def test_unicode_artifact_filename_in_real_git_repo_is_green(repo: Path) -> None:
    artifact = repo / ".omx" / "artifacts" / "设计文档.md"
    artifact.write_text("# 设计\n", encoding="utf-8")
    (repo / "docs" / "notes.md").write_text("见 `.omx/artifacts/设计文档.md`\n", encoding="utf-8")
    _commit_all(repo)

    tracked = chal.list_tracked(repo)
    assert ".omx/artifacts/设计文档.md" in tracked

    code, out = _run(repo)
    assert code == 0, out
    assert "1 ok, 0 dangling, 0 stale" in out


def test_list_tracked_uses_binary_git_output_and_utf8_decode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`text=True` would decode via the locale (cp1252 on Windows) and drop CJK.

    A mock returning UTF-8 bytes of a path that cannot encode as cp1252 proves
    `list_tracked` is binary-mode + UTF-8, independent of the host locale.
    """
    rel = ".omx/artifacts/设计文档.md"
    with pytest.raises(UnicodeEncodeError):
        rel.encode("cp1252")

    recorded: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        recorded["args"] = args
        recorded["kwargs"] = kwargs
        payload = rel.encode("utf-8") + b"\0"
        cmd = args[0] if args else kwargs.get("args")
        return subprocess.CompletedProcess(cmd, 0, stdout=payload, stderr=b"")  # type: ignore[arg-type]

    monkeypatch.setattr(chal.subprocess, "run", fake_run)
    tracked = chal.list_tracked(tmp_path)
    assert tracked == {rel}

    kwargs = recorded["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs.get("text") is not True
    assert kwargs.get("text") is False
    assert kwargs.get("encoding") is None

    cmd = recorded["args"][0] if recorded["args"] else kwargs.get("args")
    assert isinstance(cmd, (list, tuple))
    assert "ls-files" in cmd
    assert "-z" in cmd


# --------------------------------------------------------------------------
# Gitignore boundary: ephemeral OMX ignored; artifacts and .omx/ are not.
# Current policy still ignores the whole `.claude/` directory.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "ignored"),
    [
        # Cited artifacts must be addable without `git add -f`.
        (".omx/artifacts/next-opt-design-v1.md", False),
        (".omx/artifacts/new-evidence.json", False),
        # Short-lived OMX scratch stays out of the tree.
        (".omx/tmp/scratch.md", True),
        (".omx/scratch/scratch.md", True),
        (".omx/cache/blob.json", True),
        (".omx/runtime/state.json", True),
        (".omx/logs/run.log", True),
        (".omx/state/state.json", True),
        # Current policy: the whole `.claude/` directory is ignored.
        (".claude/commands/r3-r4-impl.md", True),
        (".claude/hooks/guard_protected_paths.py", True),
        (".claude/settings.local.json", True),
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


def test_repo_gitignore_does_not_ignore_omx_root() -> None:
    """A blanket `.omx/` (or `.omx/artifacts/`) rule is a regression."""
    rules = [
        line.strip()
        for line in REPO_GITIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert ".omx/" not in rules
    assert ".omx/artifacts/" not in rules
    assert ".omx" not in rules
    # Current policy: `.claude/` stays ignored as a whole directory.
    assert ".claude/" in rules
    assert ".claude/settings.local.json" not in rules
    assert ".claude/worktrees/" not in rules
    assert ".claude/scheduled_tasks.json" not in rules


def test_repo_gitignore_keeps_claude_directory_policy() -> None:
    """The existing `.claude/` block must stay byte-for-byte."""
    text = REPO_GITIGNORE.read_text(encoding="utf-8")
    assert "# Claude Code local state (sessions, memory, worktrees)\n.claude/\n" in text


def test_repo_gitignore_documents_local_exclude_and_citation_contract() -> None:
    """Shared ignore comments must match the settled artifact policy."""
    text = REPO_GITIGNORE.read_text(encoding="utf-8")
    assert ".git/info/exclude" in text
    assert "check_artifact_links" in text
    lowered = text.lower()
    assert "cited" in lowered or "citation" in lowered
