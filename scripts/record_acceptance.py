#!/usr/bin/env python3
"""Record one machine-acceptance run as reproducible evidence.

Motivation (docs/templates/agent-task-brief.md): a delivery must be
traceable to an actual executed result, and "机器验收与人的需求验收分开
记录。没有执行、环境失败、验收失败、验收通过是不同状态" -- this tool
records machine acceptance only, never LLM/human business acceptance.
The given command runs directly (no shell, argv verbatim); a JSON record
plus raw stdout/stderr logs are written into a brand-new output directory.
The recorder calls no model and writes its evidence only in the output directory;
the caller-provided command can write elsewhere or call other services;
the environment is not recorded. Cost / manual-rework are unknown here and
are left absent from the record (absent != 0).

Status vocabulary:
  passed  exit code 0 and every declared artifact exists (or none declared)
  failed  command ran but exited non-zero, or an artifact is missing
  error   the run never completed meaningfully: command not found, timeout,
          invalid arguments, or output directory already exists
The tool exits 0 only for ``passed``; ``failed`` -> 1, ``error`` -> 2. Once the output directory is created, failed/error runs leave a record.
Invalid CLI inputs and an existing output directory are rejected before execution.

Usage (argv after ``--`` runs verbatim):

    python scripts/record_acceptance.py --task-id T --condition checklist \
        --out-dir /tmp/acc/T --cwd . --timeout 60 \
        --artifact dist/result.json -- python3 -c "print('ok')"

condition is one of: none, checklist, skill, history.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 1
RECORD_TYPE = "machine-acceptance"
CONDITIONS = ("none", "checklist", "skill", "history")
EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_ERROR = 2


def _utc_iso(moment: datetime) -> str:
    return moment.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _utc_now() -> str:
    return _utc_iso(datetime.now(UTC))


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_revision(cwd: Path) -> str | None:
    """Best-effort HEAD sha of the run cwd; None when unavailable."""
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def git_dirty(cwd: Path) -> bool | None:
    """Snapshot before execution; HEAD alone does not identify uncommitted code."""
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "status", "--porcelain", "--untracked-files=normal"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        return bool(result.stdout.strip()) if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def run_command(argv: list[str], cwd: Path, timeout: float, out_dir: Path) -> dict[str, object]:
    """Stream raw bytes to files; bound the run without pipe-memory/deadlock risks."""
    start = datetime.now(UTC)
    start_clock = time.monotonic()
    timed_out = False
    spawn_error = None
    proc = None
    with (
        (out_dir / "stdout.log").open("wb") as stdout,
        (out_dir / "stderr.log").open("wb") as stderr,
    ):
        try:
            proc = subprocess.Popen(
                argv,
                cwd=str(cwd),
                stdout=stdout,
                stderr=stderr,
                start_new_session=os.name == "posix",
            )
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            assert proc is not None
            if os.name == "posix":
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
            proc.wait()
        except OSError as exc:
            spawn_error = str(exc)
    return {
        "started_utc": _utc_iso(start),
        "ended_utc": _utc_now(),
        "duration_seconds": round(time.monotonic() - start_clock, 3),
        "timed_out": timed_out,
        "spawn_error": spawn_error,
        "exit_code": None if proc is None else proc.returncode,
    }


def hash_artifacts(paths: list[str], cwd: Path) -> tuple[dict[str, str | None], list[str]]:
    """A read failure must leave an error record after the command has run."""
    hashes: dict[str, str | None] = {}
    errors = []
    for raw in paths:
        target = Path(raw)
        if not target.is_absolute():
            target = cwd / target
        try:
            hashes[raw] = sha256_of(target) if target.is_file() else None
        except OSError as exc:
            hashes[raw] = None
            errors.append(f"{raw}: {exc}")
    return hashes, errors


def save_record(out_dir: Path, record: dict[str, object]) -> None:
    (out_dir / "acceptance.json").write_text(
        json.dumps(record, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record one machine-acceptance run as reproducible evidence."
    )
    parser.add_argument("--task-id", required=True, help="task identifier from the brief")
    parser.add_argument(
        "--condition",
        required=True,
        choices=CONDITIONS,
        help="acceptance condition this run exercises",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        type=Path,
        help="brand-new output directory (must not exist; never overwritten)",
    )
    parser.add_argument("--cwd", required=True, type=Path, help="directory the command runs in")
    parser.add_argument("--timeout", required=True, type=float, help="run timeout in seconds")
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        help="artifact path to SHA256 after the run (repeatable; relative to --cwd)",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="argv executed verbatim; put after --",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # argparse keeps the literal "--" separator inside REMAINDER; drop it so
    # ``-- python3 -c ...`` records argv starting at python3.
    command = args.command[1:] if args.command[:1] == ["--"] else args.command

    def fail(message: str) -> int:
        print(f"record_acceptance: error: {message}", file=sys.stderr)
        return EXIT_ERROR

    if not command:
        return fail("no command given after --; an un-run record can never be 'passed'")
    if not args.cwd.is_dir():
        return fail(f"--cwd is not a directory: {args.cwd}")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        return fail(f"--timeout must be positive, got {args.timeout}")
    args.cwd = args.cwd.resolve()
    args.out_dir = args.out_dir.absolute()
    if args.out_dir.exists():
        return fail(f"--out-dir already exists; refusing to overwrite: {args.out_dir}")
    revision, dirty = git_revision(args.cwd), git_dirty(args.cwd)
    try:
        args.out_dir.parent.mkdir(parents=True, exist_ok=True)
        args.out_dir.mkdir(exist_ok=False)
    except OSError as exc:
        return fail(f"cannot create --out-dir {args.out_dir}: {exc}")

    run = run_command(command, args.cwd, args.timeout, args.out_dir)

    timed_out = bool(run["timed_out"])
    spawn_error = run["spawn_error"]
    exit_code = run["exit_code"]
    artifact_hashes, artifact_errors = hash_artifacts(args.artifact, args.cwd)
    missing_artifacts = [p for p, digest in artifact_hashes.items() if digest is None]

    if spawn_error is not None:
        status, reason = "error", f"command could not start: {spawn_error}"
    elif timed_out:
        status, reason = "error", f"timed out after {args.timeout}s; result unknown"
    elif exit_code != 0:
        status, reason = "failed", f"exit code {exit_code}"
    elif artifact_errors:
        status, reason = (
            "error",
            "could not read declared artifact(s): " + "; ".join(artifact_errors),
        )
    elif missing_artifacts:
        status = "failed"
        reason = "declared artifact(s) missing after run: " + ", ".join(missing_artifacts)
    else:
        status, reason = "passed", "exit code 0 and declared artifacts present"

    record: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "record_type": RECORD_TYPE,
        "note": "machine acceptance only; not an LLM/human business-acceptance claim",
        "task_id": args.task_id,
        "condition": args.condition,
        "created_utc": _utc_now(),
        "command": {"argv": command, "cwd": str(args.cwd), "timeout_seconds": args.timeout},
        "git_revision": revision,
        "git_dirty": dirty,
        "run": {
            "started_utc": run["started_utc"],
            "ended_utc": run["ended_utc"],
            "duration_seconds": run["duration_seconds"],
            "exit_code": exit_code,
            "timed_out": timed_out,
            "spawn_error": spawn_error,
        },
        "result": {"status": status, "reason": reason},
        "logs": {"stdout": "stdout.log", "stderr": "stderr.log"},
        "artifacts": artifact_hashes,
        "artifact_errors": artifact_errors,
    }
    save_record(args.out_dir, record)

    print(f"status={status} reason={reason} record={args.out_dir / 'acceptance.json'}")
    if status == "passed":
        return EXIT_PASSED
    return EXIT_FAILED if status == "failed" else EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
