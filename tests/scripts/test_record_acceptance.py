"""Real-run regression tests for scripts/record_acceptance.py.

Every scenario executes the actual CLI as a subprocess against small real
Python programs. Expected values are derived from what those programs and
the tool really emit (a baseline stdout captured by running the helper
directly, hashes recomputed from the real artifact bytes, git HEAD read
from the live worktree), never from hand-fabricated fixtures.

The tool never uses a shell and only ever writes inside a fresh --out-dir,
so tests are safe to run in parallel with the rest of the suite.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "record_acceptance.py"
PY = sys.executable

PASS_ARTIFACT = "result.txt"
CONDITIONS = ("none", "checklist", "skill", "history")


def _write(tmp: Path, name: str, body: str) -> Path:
    path = tmp / name
    path.write_text(body, encoding="utf-8")
    return path


def run_tool(
    task_id: str,
    condition: str,
    out_dir: Path,
    cwd: Path,
    timeout: float,
    command: list[str],
    artifacts: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    argv = [
        PY,
        str(SCRIPT),
        "--task-id",
        task_id,
        "--condition",
        condition,
        "--out-dir",
        str(out_dir),
        "--cwd",
        str(cwd),
        "--timeout",
        str(timeout),
    ]
    for artifact in artifacts or []:
        argv += ["--artifact", artifact]
    argv += ["--", *command]
    return subprocess.run(argv, capture_output=True, text=True, timeout=120, check=False)


def record_of(out_dir: Path) -> dict:
    return json.loads((out_dir / "acceptance.json").read_text(encoding="utf-8"))


@pytest.fixture
def happy_helper(tmp_path: Path) -> Path:
    """Real helper: prints to both streams and builds the declared artifact."""
    return _write(
        tmp_path,
        "happy_helper.py",
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text('built-by-helper\\n')\n"
        "print('helper stdout ok')\n"
        "print('helper stderr note', file=sys.stderr)\n",
    )


@pytest.fixture
def happy_out(tmp_path: Path, happy_helper: Path) -> Path:
    """Run the tool once and keep the resulting output dir as ground truth."""
    out_dir = tmp_path / "happy-record"
    result = run_tool(
        "t-happy",
        "checklist",
        out_dir,
        tmp_path,
        30,
        [PY, str(happy_helper), PASS_ARTIFACT],
        artifacts=[PASS_ARTIFACT],
    )
    assert result.returncode == 0, result.stderr
    return out_dir


def test_passed_record_holds_full_evidence(happy_out: Path) -> None:
    record = record_of(happy_out)
    assert record["schema_version"] == 1
    assert record["record_type"] == "machine-acceptance"
    assert "not an LLM/human business-acceptance claim" in record["note"]
    assert record["task_id"] == "t-happy"
    assert record["condition"] == "checklist"
    assert record["command"]["argv"] == [
        PY,
        str(happy_out.parent / "happy_helper.py"),
        PASS_ARTIFACT,
    ]
    assert record["result"]["status"] == "passed"
    assert record["run"]["exit_code"] == 0
    assert record["run"]["timed_out"] is False
    assert record["run"]["duration_seconds"] >= 0
    assert record["logs"] == {"stdout": "stdout.log", "stderr": "stderr.log"}


def test_recorded_logs_match_real_program_output(tmp_path: Path, happy_helper: Path) -> None:
    """stdout.log equals what the helper really prints when run directly."""
    baseline = subprocess.run(
        [PY, str(happy_helper), PASS_ARTIFACT],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    out_dir = tmp_path / "logs"
    run_tool("t-logs", "none", out_dir, tmp_path, 30, [PY, str(happy_helper), PASS_ARTIFACT])
    assert (out_dir / "stdout.log").read_text(encoding="utf-8") == baseline.stdout
    assert (out_dir / "stderr.log").read_text(encoding="utf-8") == baseline.stderr


def test_artifact_sha256_matches_real_bytes(happy_out: Path) -> None:
    artifact = happy_out.parent / PASS_ARTIFACT
    expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
    record = record_of(happy_out)
    assert record["artifacts"] == {PASS_ARTIFACT: expected}
    assert artifact.read_text(encoding="utf-8") == "built-by-helper\n"


@pytest.mark.parametrize("condition", CONDITIONS)
def test_every_condition_token_is_accepted(tmp_path: Path, condition: str) -> None:
    result = run_tool("t-cond", condition, tmp_path / "out", tmp_path, 30, [PY, "-c", "print(1)"])
    assert result.returncode == 0, result.stderr
    assert record_of(tmp_path / "out")["condition"] == condition


def test_nonzero_exit_is_failed_not_passed(tmp_path: Path) -> None:
    out_dir = tmp_path / "fail"
    result = run_tool(
        "t-fail", "checklist", out_dir, tmp_path, 30, [PY, "-c", "import sys; sys.exit(7)"]
    )
    assert result.returncode == 1
    record = record_of(out_dir)
    assert record["result"]["status"] == "failed"
    assert "exit code 7" in record["result"]["reason"]
    assert record["run"]["exit_code"] == 7


def test_timeout_is_error_with_evidence(tmp_path: Path) -> None:
    out_dir = tmp_path / "timeout"
    started = time.monotonic()
    result = run_tool(
        "t-timeout", "history", out_dir, tmp_path, 1, [PY, "-c", "import time; time.sleep(60)"]
    )
    elapsed = time.monotonic() - started
    assert result.returncode == 2
    assert elapsed < 30, "process was not killed promptly"
    record = record_of(out_dir)
    assert record["result"]["status"] == "error"
    assert "timed out" in record["result"]["reason"]
    assert record["run"]["timed_out"] is True
    assert record["run"]["exit_code"] is not None
    assert record["run"]["exit_code"] != 0


def test_missing_declared_artifact_is_failed(tmp_path: Path) -> None:
    out_dir = tmp_path / "missing"
    result = run_tool(
        "t-missing",
        "skill",
        out_dir,
        tmp_path,
        30,
        [PY, "-c", "print('ran, no file')"],
        artifacts=["absent.txt"],
    )
    assert result.returncode == 1
    record = record_of(out_dir)
    assert record["result"]["status"] == "failed"
    assert "absent.txt" in record["result"]["reason"]
    assert record["artifacts"] == {"absent.txt": None}
    assert (out_dir / "stdout.log").read_text(encoding="utf-8") == "ran, no file\n"


def test_metacharacter_argv_passed_verbatim(tmp_path: Path) -> None:
    helper = _write(
        tmp_path,
        "echo_args.py",
        "import sys\nprint(repr(sys.argv[1:]))\n",
    )
    tricky = ["a b", "*", "$HOME", "x;y", 'quote"d', "back\\slash"]
    out_dir = tmp_path / "meta"
    result = run_tool("t-meta", "none", out_dir, tmp_path, 30, [PY, str(helper), *tricky])
    assert result.returncode == 0, result.stderr
    record = record_of(out_dir)
    assert record["command"]["argv"] == [PY, str(helper), *tricky]
    assert record["result"]["status"] == "passed"
    assert (out_dir / "stdout.log").read_text(encoding="utf-8") == repr(tricky) + "\n"


def test_existing_out_dir_is_never_overwritten(tmp_path: Path) -> None:
    out_dir = tmp_path / "exists"
    out_dir.mkdir()
    sentinel = _write(out_dir, "sentinel.txt", "keep me")
    result = run_tool("t-exists", "none", out_dir, tmp_path, 30, [PY, "-c", "print('x')"])
    assert result.returncode == 2
    assert "refusing to overwrite" in result.stderr
    assert sentinel.read_text(encoding="utf-8") == "keep me"
    assert not (out_dir / "acceptance.json").exists()


def test_command_not_found_is_error_but_still_recorded(tmp_path: Path) -> None:
    out_dir = tmp_path / "notfound"
    result = run_tool("t-nf", "none", out_dir, tmp_path, 30, ["definitely-not-a-real-command-xyz"])
    assert result.returncode == 2
    record = record_of(out_dir)
    assert record["result"]["status"] == "error"
    assert "could not start" in record["result"]["reason"]
    assert record["run"]["spawn_error"]


def test_empty_command_is_rejected_as_unrun(tmp_path: Path) -> None:
    out_dir = tmp_path / "empty"
    argv = [
        PY,
        str(SCRIPT),
        "--task-id",
        "t-empty",
        "--condition",
        "none",
        "--out-dir",
        str(out_dir),
        "--cwd",
        str(tmp_path),
        "--timeout",
        "30",
    ]
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert "can never be 'passed'" in result.stderr
    assert not out_dir.exists()


def test_git_revision_read_from_run_cwd(tmp_path: Path) -> None:
    # Inside a git worktree the tool records the live HEAD...
    out_dir = tmp_path / "repo"
    result = run_tool("t-git", "checklist", out_dir, ROOT, 30, [PY, "-c", "print(1)"])
    assert result.returncode == 0, result.stderr
    expected = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    assert record_of(out_dir)["git_revision"] == expected
    # ...and records null in a plain directory that is not a repo.
    plain = tmp_path / "plain"
    plain.mkdir()
    result = run_tool(
        "t-git2", "checklist", tmp_path / "plain-out", plain, 30, [PY, "-c", "print(1)"]
    )
    assert result.returncode == 0, result.stderr
    assert record_of(tmp_path / "plain-out")["git_revision"] is None


def test_no_environment_dump_in_record(happy_out: Path) -> None:
    serialized = json.dumps(record_of(happy_out))
    assert "PYTHONPATH" not in serialized
    assert "VIRTUAL_ENV" not in serialized
    assert "PATH" not in serialized


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_timeout_never_starts_command(tmp_path, timeout):
    marker = tmp_path / "should-not-exist"
    result = run_tool(
        "invalid",
        "none",
        tmp_path / "out",
        tmp_path,
        timeout,
        [PY, "-c", "from pathlib import Path; Path('should-not-exist').touch()"],
    )
    assert result.returncode == 2
    assert not marker.exists()
    assert not (tmp_path / "out").exists()


def test_logs_preserve_non_utf8_bytes(tmp_path):
    output = tmp_path / "raw-output"
    result = run_tool(
        "raw",
        "none",
        output,
        tmp_path,
        10,
        [PY, "-c", "import os; os.write(1, bytes([255, 0, 10])); os.write(2, bytes([254]))"],
    )
    assert result.returncode == 0
    assert (output / "stdout.log").read_bytes() == bytes([255, 0, 10])
    assert (output / "stderr.log").read_bytes() == bytes([254])


def test_git_revision_is_captured_before_the_command(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.check_output(
            [
                "git",
                "-C",
                str(repo),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                *args,
            ],
            text=True,
        ).strip()

    git("init", "--quiet")
    git("commit", "--allow-empty", "-m", "before", "--quiet")
    before = git("rev-parse", "HEAD")
    out = tmp_path / "out"
    result = run_tool(
        "revision",
        "none",
        out,
        repo,
        10,
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "after",
        ],
    )
    assert result.returncode == 0
    record = record_of(out)
    assert record["git_revision"] == before
    assert record["git_revision"] != git("rev-parse", "HEAD")
    assert record["git_dirty"] is False
    assert Path(record["command"]["cwd"]).is_absolute()


@pytest.mark.skipif(os.name != "posix", reason="process-group termination is POSIX-specific")
def test_timeout_stops_descendant_that_inherits_logs(tmp_path):
    child = _write(
        tmp_path,
        "child.py",
        "import os, pathlib, time\n"
        "pathlib.Path('child.pid').write_text(str(os.getpid()))\n"
        "time.sleep(1.5)\npathlib.Path('late-write').touch()\n",
    )
    parent = _write(
        tmp_path,
        "parent.py",
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, sys.argv[1]])\ntime.sleep(60)\n",
    )
    try:
        started = time.monotonic()
        result = run_tool(
            "tree", "none", tmp_path / "out", tmp_path, 0.7, [PY, str(parent), str(child)]
        )
        assert result.returncode == 2
        assert time.monotonic() - started < 10
        assert (tmp_path / "child.pid").exists(), "descendant must actually start"
        time.sleep(1.1)  # Pass its write deadline; a surviving descendant would leave evidence.
        assert not (tmp_path / "late-write").exists()
        assert record_of(tmp_path / "out")["run"]["timed_out"] is True
    finally:
        pidfile = tmp_path / "child.pid"
        if pidfile.exists():
            with contextlib.suppress(ProcessLookupError):
                os.kill(int(pidfile.read_text()), signal.SIGKILL)
