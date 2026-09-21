"""Frozen-debt baseline for scripts/check_artifact_links.py.

A fresh CI checkout cannot see a developer-local untracked artifact, so the
same citation that is dangling locally is stale (exit 0) in CI. The baseline
is the exact multiset of currently non-tracked citations; check mode makes
any drift from that snapshot fatal.

Keys are (source, target) with an occurrence count — never line numbers,
timestamps, absolute paths, or commit SHAs.
"""

from __future__ import annotations

import errno
import importlib.util
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_artifact_links.py"
ROOT = SCRIPT.parents[1]
spec = importlib.util.spec_from_file_location("check_artifact_links", SCRIPT)
assert spec and spec.loader
chal = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = chal
spec.loader.exec_module(chal)

BASELINE_REL = "ci/artifact-links-baseline.json"
LIVE_BASELINE = ROOT / BASELINE_REL
LIVE_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
LIVE_REGISTRY = ROOT / "ci" / "decision-source.yaml"

# Independently observed at this checkpoint over every tracked *.md
# by `scripts/check_artifact_links.py` (no --targets):
# 1146 refs, 684 ok, 0 dangling (fresh clone), 462 stale occurrences / 454 keys.
# Re-observed 2026-09-21 after distill landing docs + T+21 measure: +35 ok
# citations; stale multiset unchanged.
# Re-observed 2026-09-21 after merging the local session memory: +3 stale
# citations from memory/session.md; ok citations unchanged.
FROZEN_REF_TOTAL = 1146
FROZEN_OK = 684
FROZEN_STALE_OCCURRENCES = 462
FROZEN_STALE_KEYS = 454


def _git(root: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "baseline",
        "GIT_AUTHOR_EMAIL": "baseline@example.invalid",
        "GIT_COMMITTER_NAME": "baseline",
        "GIT_COMMITTER_EMAIL": "baseline@example.invalid",
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
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / ".omx" / "artifacts").mkdir(parents=True)
    (root / "ci").mkdir(parents=True)
    _git(root, "init", "-q")
    return root


def _commit(root: Path) -> None:
    _git(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture")


def _commit_all(root: Path) -> None:
    _git(root, "add", ".")
    _commit(root)


def _commit_paths(root: Path, *paths: str) -> None:
    _git(root, "add", "--", *paths)
    _commit(root)


def _run(root: Path, *args: str) -> tuple[int, str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _baseline_bytes(entries: list[tuple[str, str, int]]) -> bytes:
    payload = {
        "schema_version": 1,
        "nontracked": [
            {"source": source, "target": target, "count": count}
            for source, target, count in entries
        ],
    }
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _write_baseline(path: Path, entries: list[tuple[str, str, int]]) -> None:
    path.write_bytes(_baseline_bytes(entries))


def _stale_repo(repo: Path, text: str = "see `.omx/artifacts/missing.md`\n") -> None:
    (repo / "docs" / "notes.md").write_text(text, encoding="utf-8")
    _commit_all(repo)


_STALE_COUNTS: dict[tuple[str, str], int] = {("docs/a.md", ".omx/artifacts/x.md"): 1}


def _tmp_leftovers(directory: Path, *keep: Path) -> list[Path]:
    keep_names = {p.name for p in keep}
    return sorted(
        p for p in directory.iterdir() if p.name.endswith(".tmp") and p.name not in keep_names
    )


def _run_in(cwd: Path, *args: str) -> tuple[int, str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(cwd), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


# --------------------------------------------------------------------------
# Check mode: exact match / new stale / count / drift / dangling
# --------------------------------------------------------------------------


def test_exact_baseline_passes_in_fresh_clone_semantics(repo: Path) -> None:
    """Tracked docs cite a missing artifact: stale locally and in a fresh clone."""
    _stale_repo(repo)
    baseline = repo / "ci" / "artifact-links-baseline.json"
    _write_baseline(baseline, [("docs/notes.md", ".omx/artifacts/missing.md", 1)])

    code, out = _run(repo, "--check-baseline", str(baseline))
    assert code == 0, out
    assert "NEW_STALE" not in out
    assert "COUNT_INCREASE" not in out
    assert "BASELINE_DRIFT" not in out
    assert "DANGLING" not in out


def test_new_stale_citation_is_fatal(repo: Path) -> None:
    _stale_repo(repo, "see `.omx/artifacts/missing.md` and `.omx/artifacts/extra.md`\n")
    baseline = repo / "ci" / "artifact-links-baseline.json"
    _write_baseline(baseline, [("docs/notes.md", ".omx/artifacts/missing.md", 1)])

    code, out = _run(repo, "--check-baseline", str(baseline))
    assert code == 1, out
    assert "NEW_STALE" in out
    assert ".omx/artifacts/extra.md" in out


def test_stale_count_increase_is_fatal(repo: Path) -> None:
    _stale_repo(repo, "see `.omx/artifacts/missing.md` and again `.omx/artifacts/missing.md`\n")
    baseline = repo / "ci" / "artifact-links-baseline.json"
    _write_baseline(baseline, [("docs/notes.md", ".omx/artifacts/missing.md", 1)])

    code, out = _run(repo, "--check-baseline", str(baseline))
    assert code == 1, out
    assert "COUNT_INCREASE" in out
    assert ".omx/artifacts/missing.md" in out


def test_removed_stale_citation_is_baseline_drift(repo: Path) -> None:
    (repo / "docs" / "notes.md").write_text("clean prose, no artifacts.\n", encoding="utf-8")
    _commit_all(repo)
    baseline = repo / "ci" / "artifact-links-baseline.json"
    _write_baseline(baseline, [("docs/notes.md", ".omx/artifacts/missing.md", 1)])

    code, out = _run(repo, "--check-baseline", str(baseline))
    assert code == 1, out
    assert "BASELINE_DRIFT" in out
    assert ".omx/artifacts/missing.md" in out


def test_resolved_stale_by_tracking_target_is_baseline_drift(repo: Path) -> None:
    (repo / ".omx" / "artifacts" / "missing.md").write_text("# now tracked\n", encoding="utf-8")
    (repo / "docs" / "notes.md").write_text("see `.omx/artifacts/missing.md`\n", encoding="utf-8")
    _commit_all(repo)
    baseline = repo / "ci" / "artifact-links-baseline.json"
    _write_baseline(baseline, [("docs/notes.md", ".omx/artifacts/missing.md", 1)])

    code, out = _run(repo, "--check-baseline", str(baseline))
    assert code == 1, out
    assert "BASELINE_DRIFT" in out
    assert "DANGLING" not in out


def test_stale_count_decrease_is_baseline_drift(repo: Path) -> None:
    _stale_repo(repo, "see `.omx/artifacts/missing.md`\n")
    baseline = repo / "ci" / "artifact-links-baseline.json"
    _write_baseline(baseline, [("docs/notes.md", ".omx/artifacts/missing.md", 2)])

    code, out = _run(repo, "--check-baseline", str(baseline))
    assert code == 1, out
    assert "BASELINE_DRIFT" in out


def test_new_dangling_is_fatal_even_when_key_is_baselined(repo: Path) -> None:
    """Baseline must not launder a local untracked artifact into a CI-green stale."""
    (repo / "docs" / "notes.md").write_text(
        "see `.omx/artifacts/local-only.md`\n", encoding="utf-8"
    )
    _commit_paths(repo, "docs/notes.md")
    (repo / ".omx" / "artifacts" / "local-only.md").write_text("untracked\n", encoding="utf-8")
    baseline = repo / "ci" / "artifact-links-baseline.json"
    _write_baseline(baseline, [("docs/notes.md", ".omx/artifacts/local-only.md", 1)])

    code, out = _run(repo, "--check-baseline", str(baseline))
    assert code == 1, out
    assert "DANGLING" in out
    assert "local-only.md" in out


# --------------------------------------------------------------------------
# Writer
# --------------------------------------------------------------------------


def test_write_baseline_is_deterministic_sorted_json(repo: Path) -> None:
    (repo / "docs" / "z.md").write_text("`.omx/artifacts/z.md`\n", encoding="utf-8")
    (repo / "docs" / "a.md").write_text(
        "`.omx/artifacts/b.md` then `.omx/artifacts/a.md` then `.omx/artifacts/a.md`\n",
        encoding="utf-8",
    )
    _commit_all(repo)
    path = repo / "ci" / "artifact-links-baseline.json"

    code1, out1 = _run(repo, "--write-baseline", str(path))
    assert code1 == 0, out1
    first = path.read_bytes()
    path.unlink()
    code2, out2 = _run(repo, "--write-baseline", str(path))
    assert code2 == 0, out2
    second = path.read_bytes()

    assert first == second
    assert first.endswith(b"\n")
    assert first == first.replace(b"\r\n", b"\n")
    text = first.decode("utf-8")
    assert str(repo) not in text
    assert "generated" not in text.lower()
    assert "timestamp" not in text.lower()
    payload = json.loads(text)
    assert list(payload) == ["schema_version", "nontracked"]
    assert payload["schema_version"] == 1
    sources_targets = [(entry["source"], entry["target"]) for entry in payload["nontracked"]]
    assert sources_targets == sorted(sources_targets)
    assert payload["nontracked"] == [
        {"source": "docs/a.md", "target": ".omx/artifacts/a.md", "count": 2},
        {"source": "docs/a.md", "target": ".omx/artifacts/b.md", "count": 1},
        {"source": "docs/z.md", "target": ".omx/artifacts/z.md", "count": 1},
    ]
    for entry in payload["nontracked"]:
        assert list(entry) == ["source", "target", "count"]


def test_write_baseline_refuses_dangling(repo: Path) -> None:
    (repo / "docs" / "notes.md").write_text(
        "see `.omx/artifacts/local-only.md`\n", encoding="utf-8"
    )
    _commit_paths(repo, "docs/notes.md")
    (repo / ".omx" / "artifacts" / "local-only.md").write_text("untracked\n", encoding="utf-8")
    path = repo / "ci" / "artifact-links-baseline.json"

    code, out = _run(repo, "--write-baseline", str(path))
    assert code == 1, out
    assert "dangling" in out.lower()
    assert not path.exists()


def test_write_then_check_round_trip(repo: Path) -> None:
    _stale_repo(
        repo,
        "`.omx/artifacts/a.md` `.omx/artifacts/a.md` `.omx/artifacts/b.md`\n",
    )
    path = repo / "ci" / "artifact-links-baseline.json"
    write_code, write_out = _run(repo, "--write-baseline", str(path))
    assert write_code == 0, write_out
    check_code, check_out = _run(repo, "--check-baseline", str(path))
    assert check_code == 0, check_out


def test_check_and_write_together_is_refused(repo: Path) -> None:
    _stale_repo(repo)
    path = repo / "ci" / "artifact-links-baseline.json"
    code, out = _run(repo, "--check-baseline", str(path), "--write-baseline", str(path))
    assert code == 2, out
    assert not path.exists()


def test_check_baseline_with_strict_is_refused(repo: Path) -> None:
    _stale_repo(repo)
    path = repo / "ci" / "artifact-links-baseline.json"
    _write_baseline(path, [("docs/notes.md", ".omx/artifacts/missing.md", 1)])
    code, out = _run(repo, "--check-baseline", str(path), "--strict")
    assert code == 2, out
    assert "strict" in out.lower()


@pytest.mark.parametrize("dest", [".", "/", ""])
def test_cli_write_baseline_invalid_destination_exits_2(repo: Path, dest: str) -> None:
    """Malformed --write-baseline destinations are exit 2, not a traceback."""
    _stale_repo(repo)
    sentinel = repo / "docs" / "notes.md"
    before = sentinel.read_bytes()
    extra = [dest] if dest != "" else [""]
    code, out = _run_in(repo, "--write-baseline", *extra)
    assert code == 2, out
    assert "Traceback" not in out
    assert "cannot write baseline" in out
    assert sentinel.read_bytes() == before
    assert sentinel.exists()
    assert (repo / "docs").is_dir()
    assert Path("/").is_dir()
    assert _tmp_leftovers(repo) == []
    assert _tmp_leftovers(repo / "docs") == []
    assert _tmp_leftovers(repo / "ci") == []


@pytest.mark.parametrize("dest", [Path("."), Path("/"), Path("")])
def test_write_baseline_invalid_destination_is_guard_error(
    tmp_path: Path, dest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    marker = tmp_path / "marker.txt"
    marker.write_text("keep\n", encoding="utf-8")
    with pytest.raises(chal.GuardError, match="cannot write baseline"):
        chal.write_baseline(dest, _STALE_COUNTS)
    assert marker.read_text(encoding="utf-8") == "keep\n"
    assert _tmp_leftovers(tmp_path) == []


def test_write_baseline_unencodable_source_is_guard_error(tmp_path: Path) -> None:
    dest = tmp_path / "baseline.json"
    with pytest.raises(chal.GuardError, match="cannot write baseline"):
        chal.write_baseline(dest, {("docs/\udc80.md", ".omx/artifacts/x.md"): 1})
    assert not dest.exists()
    assert _tmp_leftovers(tmp_path) == []


@pytest.mark.parametrize(
    "target",
    [
        ".omx/artifacts/x.md:12",
        ".omx/artifacts/y.md\\",
        ".omx/artifacts/z.md(注:1",
        ".omx/artifacts/foo\\..\\secret.md",
        ".omx/artifacts/../secret.md",
        ".omx/artifacts/gate10.diff\\\\",
    ],
)
def test_write_baseline_rejects_annotation_fragments_and_path_escape(
    tmp_path: Path, target: str
) -> None:
    """Baseline targets stay normalized POSIX artifact paths, not scanner junk."""
    dest = tmp_path / "baseline.json"
    with pytest.raises(chal.GuardError, match="invalid target"):
        chal.write_baseline(dest, {("docs/a.md", target): 1})
    assert not dest.exists()
    assert _tmp_leftovers(tmp_path) == []


@pytest.mark.parametrize(
    "citation",
    [
        ".omx/artifacts/../x.md",
        ".omx/artifacts/./x.md",
        ".omx/artifacts//x.md",
    ],
)
def test_cli_non_normalized_extracted_target_fails_closed_with_source_line(
    repo: Path, citation: str
) -> None:
    """Dot-segment / empty-segment citations are exit 2 at the citing line.

    extract_targets still emits them (no silent normalize). scan must reject
    before classify or baseline write, with repo-relative source:line, so a
    default scan cannot warn-only green and --write-baseline cannot hide
    behind a global invalid-target error after a full scan.
    """
    (repo / "docs" / "notes.md").write_text(
        f"ok `.omx/artifacts/missing.md`\nbad `{citation}`\n",
        encoding="utf-8",
    )
    _commit_all(repo)
    dest = repo / "ci" / "artifact-links-baseline.json"

    code, out = _run(repo, "--targets", "docs")
    assert code == 2, out
    assert "docs/notes.md:2:" in out
    assert citation in out
    assert "invalid artifact target" in out
    assert "Traceback" not in out
    assert "cannot write baseline" not in out

    write_code, write_out = _run(repo, "--targets", "docs", "--write-baseline", str(dest))
    assert write_code == 2, write_out
    assert "docs/notes.md:2:" in write_out
    assert citation in write_out
    assert "invalid artifact target" in write_out
    assert "cannot write baseline" not in write_out
    assert not dest.exists()
    assert _tmp_leftovers(repo / "ci") == []


def test_write_baseline_unencodable_target_is_guard_error(tmp_path: Path) -> None:
    dest = tmp_path / "baseline.json"
    with pytest.raises(chal.GuardError, match="cannot write baseline"):
        chal.write_baseline(dest, {("docs/a.md", ".omx/artifacts/\udc80.md"): 1})
    assert not dest.exists()
    assert _tmp_leftovers(tmp_path) == []


def test_write_baseline_does_not_follow_predictable_tmp_symlink(
    tmp_path: Path, symlink_supported: bool
) -> None:
    if not symlink_supported:
        pytest.skip("symlinks not supported")
    dest = tmp_path / "artifact-links-baseline.json"
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"do-not-clobber\n")
    predictable = dest.with_name(f".{dest.name}.tmp")
    predictable.symlink_to(victim)

    chal.write_baseline(dest, _STALE_COUNTS)

    assert victim.read_bytes() == b"do-not-clobber\n"
    assert predictable.is_symlink()
    assert predictable.resolve() == victim.resolve()
    assert dest.is_file()
    assert not dest.is_symlink()
    assert chal.load_baseline(dest).as_counts() == _STALE_COUNTS
    assert dest.read_bytes() == chal.render_baseline(_STALE_COUNTS).encode("utf-8")
    assert _tmp_leftovers(tmp_path, predictable) == []


def test_write_baseline_replaces_destination_symlink_not_followed(
    tmp_path: Path, symlink_supported: bool
) -> None:
    if not symlink_supported:
        pytest.skip("symlinks not supported")
    victim = tmp_path / "victim.json"
    victim.write_bytes(b'{"schema_version": 1, "nontracked": []}\n')
    dest = tmp_path / "baseline.json"
    dest.symlink_to(victim)

    chal.write_baseline(dest, _STALE_COUNTS)

    assert victim.read_bytes() == b'{"schema_version": 1, "nontracked": []}\n'
    assert not dest.is_symlink()
    assert chal.load_baseline(dest).as_counts() == _STALE_COUNTS
    assert _tmp_leftovers(tmp_path) == []


def test_concurrent_write_baseline_leaves_valid_content(tmp_path: Path) -> None:
    dest = tmp_path / "baseline.json"
    expected = chal.render_baseline(_STALE_COUNTS).encode("utf-8")
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            barrier.wait(timeout=5)
            chal.write_baseline(dest, _STALE_COUNTS)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert dest.read_bytes() == expected
    assert chal.load_baseline(dest).as_counts() == _STALE_COUNTS
    assert _tmp_leftovers(tmp_path) == []


def test_cli_concurrent_write_baseline_does_not_clobber(repo: Path) -> None:
    _stale_repo(repo)
    path = repo / "ci" / "artifact-links-baseline.json"
    cmd = [sys.executable, str(SCRIPT), "--root", str(repo), "--write-baseline", str(path)]

    def run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(cmd, capture_output=True, text=True, check=False)

    barrier = threading.Barrier(2)
    results: list[subprocess.CompletedProcess[str]] = []

    def worker() -> None:
        barrier.wait(timeout=5)
        results.append(run())

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == 2
    for proc in results:
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, out
        assert "Traceback" not in out
    baseline = chal.load_baseline(path)
    assert baseline.as_counts() == {("docs/notes.md", ".omx/artifacts/missing.md"): 1}
    assert path.read_bytes() == chal.render_baseline(baseline.as_counts()).encode("utf-8")
    assert _tmp_leftovers(repo / "ci") == []


@pytest.mark.parametrize("attr", ["write", "fsync", "replace"])
def test_write_baseline_oserror_closes_fd_and_removes_own_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, attr: str
) -> None:
    dest = tmp_path / "baseline.json"
    original = b"original-bytes\n"
    dest.write_bytes(original)
    created_names: list[str] = []
    created_fds: list[int] = []
    assert hasattr(chal, "tempfile"), "write_baseline must use tempfile.mkstemp"
    real_mkstemp = chal.tempfile.mkstemp

    def tracking_mkstemp(*args: object, **kwargs: object) -> tuple[int, str]:
        fd, name = real_mkstemp(*args, **kwargs)
        created_fds.append(fd)
        created_names.append(name)
        return fd, name

    def boom(*_args: object, **_kwargs: object) -> object:
        raise OSError("injected failure")

    monkeypatch.setattr(chal.tempfile, "mkstemp", tracking_mkstemp)
    monkeypatch.setattr(chal, f"_os_{attr}", boom)

    with pytest.raises(chal.GuardError, match="cannot write baseline"):
        chal.write_baseline(dest, _STALE_COUNTS)

    assert dest.read_bytes() == original
    assert created_names
    for name in created_names:
        assert not os.path.lexists(name)
    for fd in created_fds:
        with pytest.raises(OSError) as excinfo:
            os.fstat(fd)
        assert excinfo.value.errno == errno.EBADF
    assert _tmp_leftovers(tmp_path) == []


# --------------------------------------------------------------------------
# Fail-closed parsing
# --------------------------------------------------------------------------


def test_missing_baseline_exits_2(repo: Path) -> None:
    _stale_repo(repo)
    missing = repo / "ci" / "no-such-baseline.json"
    code, out = _run(repo, "--check-baseline", str(missing))
    assert code == 2, out
    assert "Traceback" not in out


def test_invalid_utf8_baseline_exits_2(repo: Path) -> None:
    _stale_repo(repo)
    path = repo / "ci" / "artifact-links-baseline.json"
    path.write_bytes(b'{"schema_version":1,"nontracked":[\xff]}')
    code, out = _run(repo, "--check-baseline", str(path))
    assert code == 2, out
    assert "UTF-8" in out
    assert "Traceback" not in out


@pytest.mark.parametrize(
    ("raw", "needle"),
    [
        ('{"schema_version":1,"schema_version":1,"nontracked":[]}\n', "duplicate"),
        (
            '{"schema_version":1,"nontracked":[{"source":"docs/a.md","source":"docs/b.md",'
            '"target":".omx/artifacts/x.md","count":1}]}\n',
            "duplicate",
        ),
        ('{"schema_version":true,"nontracked":[]}\n', "schema_version"),
        ('{"schema_version":1.0,"nontracked":[]}\n', "schema_version"),
        ('{"schema_version":2,"nontracked":[]}\n', "schema_version"),
        ('{"schema_version":1,"nontracked":[],"extra":1}\n', "key"),
        ('{"schema_version":1}\n', "key"),
        ("[]\n", "object"),
        ('{"schema_version":1,"nontracked":{"source":"docs/a.md"}}\n', "list"),
        (
            '{"schema_version":1,"nontracked":[{"source":"docs/a.md",'
            '"target":".omx/artifacts/x.md","count":1,"lineno":4}]}\n',
            "key",
        ),
        (
            '{"schema_version":1,"nontracked":['
            '{"source":"docs/a.md","target":".omx/artifacts/x.md","count":true}]}\n',
            "count",
        ),
        (
            '{"schema_version":1,"nontracked":['
            '{"source":"docs/a.md","target":".omx/artifacts/x.md","count":1.0}]}\n',
            "count",
        ),
        (
            '{"schema_version":1,"nontracked":['
            '{"source":"docs/a.md","target":".omx/artifacts/x.md","count":0}]}\n',
            "count",
        ),
        (
            '{"schema_version":1,"nontracked":['
            '{"source":"docs/a.md","target":".omx/artifacts/x.md","count":-1}]}\n',
            "count",
        ),
        (
            '{"schema_version":1,"nontracked":['
            '{"source":"../docs/a.md","target":".omx/artifacts/x.md","count":1}]}\n',
            "source",
        ),
        (
            '{"schema_version":1,"nontracked":['
            '{"source":"/docs/a.md","target":".omx/artifacts/x.md","count":1}]}\n',
            "source",
        ),
        (
            '{"schema_version":1,"nontracked":['
            '{"source":"docs\\\\a.md","target":".omx/artifacts/x.md","count":1}]}\n',
            "source",
        ),
        (
            '{"schema_version":1,"nontracked":['
            '{"source":"docs/a.md","target":".omx/artifacts/../secret.md","count":1}]}\n',
            "target",
        ),
        (
            '{"schema_version":1,"nontracked":['
            '{"source":"docs/a.md","target":".omx/artifacts/x.md:12","count":1}]}\n',
            "target",
        ),
        (
            '{"schema_version":1,"nontracked":['
            '{"source":"docs/a.md","target":".omx/artifacts/y.md\\\\","count":1}]}\n',
            "target",
        ),
        (
            '{"schema_version":1,"nontracked":['
            '{"source":"docs/a.md","target":".omx/artifacts/foo\\\\..\\\\secret.md","count":1}]}\n',
            "target",
        ),
        (
            '{"schema_version":1,"nontracked":['
            '{"source":"docs/a.md","target":"/etc/passwd","count":1}]}\n',
            "target",
        ),
        (
            '{"schema_version":1,"nontracked":['
            '{"source":"docs/a.md","target":"docs/a.md","count":1}]}\n',
            "target",
        ),
        (
            '{"schema_version":1,"nontracked":['
            '{"source":"docs/a.md","target":".omx/artifacts/x.md","count":1},'
            '{"source":"docs/a.md","target":".omx/artifacts/x.md","count":2}]}\n',
            "duplicate",
        ),
    ],
)
def test_malformed_baseline_exits_2(repo: Path, raw: str, needle: str) -> None:
    _stale_repo(repo)
    path = repo / "ci" / "artifact-links-baseline.json"
    path.write_text(raw, encoding="utf-8")
    code, out = _run(repo, "--check-baseline", str(path))
    assert code == 2, out
    assert needle.lower() in out.lower()
    assert "Traceback" not in out


def test_load_baseline_rejects_bool_and_float_schema_version(tmp_path: Path) -> None:
    for raw in (
        '{"schema_version":true,"nontracked":[]}',
        '{"schema_version":1.0,"nontracked":[]}',
    ):
        path = tmp_path / "b.json"
        path.write_text(raw, encoding="utf-8")
        with pytest.raises(chal.GuardError, match="schema_version"):
            chal.load_baseline(path)


# --------------------------------------------------------------------------
# Live wiring: committed baseline, CI job, decision-source registry
# --------------------------------------------------------------------------


def test_committed_baseline_matches_current_stale_multiset() -> None:
    """The frozen file is the live scan, not a hand-edited guess.

    Occurrence total is pinned to the independently observed 462 at this
    checkpoint so a silent scan-set change cannot hide inside a matching pair.
    """
    tracked = chal.list_tracked(ROOT)
    refs = chal.scan(ROOT, None, tracked)
    dangling = [ref for ref in refs if ref.status == "dangling"]
    stale = [ref for ref in refs if ref.status == "stale"]
    ok = [ref for ref in refs if ref.status == "ok"]
    assert dangling == []
    assert len(refs) == FROZEN_REF_TOTAL
    assert len(ok) == FROZEN_OK
    assert all(chal._is_normalized_artifact_target(ref.target) for ref in refs)
    current: dict[tuple[str, str], int] = {}
    for ref in stale:
        key = (ref.source, ref.target)
        current[key] = current.get(key, 0) + 1
    baseline = chal.load_baseline(LIVE_BASELINE)
    assert baseline.as_counts() == current
    assert sum(current.values()) == FROZEN_STALE_OCCURRENCES
    assert len(current) == FROZEN_STALE_KEYS
    text = LIVE_BASELINE.read_bytes()
    assert text.endswith(b"\n")
    assert b"\r\n" not in text
    decoded = text.decode("utf-8")
    assert "generated" not in decoded.lower()
    assert str(ROOT) not in decoded
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "ci/artifact-links-baseline.json text eol=lf" in attrs


def test_ci_workflow_and_registry_wire_artifact_links_job() -> None:
    workflow = yaml.safe_load(LIVE_WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert "artifact-links" in jobs
    job = jobs["artifact-links"]
    assert job.get("continue-on-error") is not True
    runs = "\n".join(step.get("run", "") for step in job["steps"] if isinstance(step, dict))
    assert "uv run python scripts/check_artifact_links.py" in runs
    assert f"--check-baseline {BASELINE_REL}" in runs
    registry = yaml.safe_load(LIVE_REGISTRY.read_text(encoding="utf-8"))
    entry = registry["jobs"]["artifact-links"]
    assert entry["decision_source"] == "deterministic"
