#!/usr/bin/env python3
"""Command-surface E2E smoke (runs inside docker/val-base image).

Complements ``e2e_llm_routing.py`` (deep routing-path validation) with a
broad smoke pass over the ~45 top-level commands, especially the M12
observability/discovery surface and the long-running ``vibe loop``
lifecycle (create → tick → pause → resume → delete; tick executes the
real AgentRuntime.handle_query routing pipeline).

Isolation: all CLI invocations run with cwd = ``<project-root>/.smoke-project``
(an independent subdirectory with its own .vibe), so this script never
touches the project-root .vibe state that e2e_llm_routing.py depends on —
the two scripts can run back-to-back against the same /work copy. The
isolation is not just by convention: the script fingerprints
``<project-root>/.vibe`` before and after the run and FAILs on any drift
(gate25 pi F5).

A note on what the loop tick proves (gate25 pi F7): it asserts the
pipeline REALLY executed and persisted a run record — not that LLM
arbitration happened. ``/slash-route use session-end`` resolves at the
keyword layer, so a passing tick is compatible with zero LLM calls; deep
LLM arbitration coverage stays with e2e_llm_routing.py.

Usage (inside container, repo copy at /work):
    uv run --frozen python scripts/e2e_command_smoke.py --project-root /work
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


def _write_smoke_config(smoke_dir: Path) -> None:
    """Write a FRESH minimal .vibe/config.toml for the smoke project
    (gate25 pi F6: unlike e2e_llm_routing._ensure_llm_config, which merges
    into an existing file and can set api_base, this is a from-scratch
    write — the smoke project starts with no .vibe at all).

    Contents: loop kill-switch ON (default false — tick would only
    *report*, not execute) + DeepSeek LLM section."""
    vibe_dir = smoke_dir / ".vibe"
    vibe_dir.mkdir(parents=True, exist_ok=True)
    (vibe_dir / "config.toml").write_text(
        "\n".join(
            [
                "[llm]",
                'provider = "deepseek"',
                'model = "deepseek-v4-flash"',
                f'api_key = "{os.environ.get("DEEPSEEK_API_KEY", "")}"',
                "temperature = 0.0",
                "max_tokens = 512",
                "",
                "[loop]",
                "enabled = true",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _seed_spans(smoke_dir: Path) -> None:
    """Write 4 synthetic route spans (2 tasks across 2 days) so the
    observability commands have real data to chew on.

    Same-task_id recurrence gives scan-candidates a hard-grouped cluster
    even when the embedding backend is unavailable in the container.
    """
    from vibesop.core.observability.models import Span
    from vibesop.core.observability.span_writer import SpanWriter

    writer = SpanWriter(smoke_dir / ".vibe" / "observability" / "spans.jsonl")
    now = datetime.now(UTC)
    for i in range(4):
        task_id = "smoke-task-1" if i < 3 else "smoke-task-2"
        query = f"smoke 行为冒烟查询 变体{i}"
        span = Span(
            id=f"smoke-r{i}",
            trace_id=f"smoke-tr{i}",
            name=f"route:{query}",
            span_kind="task",
            task_id=task_id,
            project_id="smoke",
            started_at=now - timedelta(days=2 - (i % 3), hours=i),
            input_data={"query": query},
            metadata={"query": query, "has_match": False, "mode": "single"},
        )
        span.set_ok()
        writer.write_span(span)


def _vibe_state_fingerprint(root: Path) -> str:
    """Content fingerprint of ``<root>/.vibe`` (gate25 pi F5).

    Used to prove the smoke run left the project-root state byte-identical.
    Path list + per-file sha1, order-normalised. sha1 (not the builtin
    ``hash()``) per repo test/script hygiene convention.
    """
    vibe_dir = root / ".vibe"
    entries: list[tuple[str, str]] = []
    if vibe_dir.exists():
        for path in sorted(vibe_dir.rglob("*")):
            if path.is_file():
                digest = hashlib.sha1(path.read_bytes()).hexdigest()
                entries.append((str(path.relative_to(vibe_dir)), digest))
    return hashlib.sha1(json.dumps(entries).encode()).hexdigest()


class Smoke:
    def __init__(self, smoke_dir: Path) -> None:
        self.smoke_dir = smoke_dir

    def run(
        self,
        name: str,
        args: list[str],
        *,
        expect_rc: int | tuple[int, ...] = 0,
        expect: list[str] | None = None,
        expect_absent: list[str] | None = None,
        timeout: int = 90,
    ) -> subprocess.CompletedProcess[str]:
        """Run ``uv run --frozen vibe <args>`` in the smoke project and
        assert exit code + key output substrings. A hung command records a
        FAIL instead of raising (gate25 MAJOR-2b: one LLM stall must not
        kill the run — the summary must always print)."""
        try:
            proc = subprocess.run(
                ["uv", "run", "--frozen", "vibe", *args],
                cwd=self.smoke_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            record(name, False, f"timeout after {timeout}s")
            return subprocess.CompletedProcess(args, -1, "", f"timeout after {timeout}s")
        output = proc.stdout + proc.stderr
        allowed = (expect_rc,) if isinstance(expect_rc, int) else expect_rc
        ok = proc.returncode in allowed
        missing = [s for s in (expect or []) if s not in output]
        present = [s for s in (expect_absent or []) if s in output]
        ok = ok and not missing and not present
        detail = f"rc={proc.returncode}"
        if missing or present:
            detail += f" missing={missing} unexpected={present} out_tail={output[-200:]!r}"
        record(name, ok, detail)
        return proc

    def loop_total_runs(self, name: str) -> int:
        """Parse 'Total Runs: N' from ``vibe loop show`` (plain-text panel)."""
        proc = self.run(f"loop show {name} (parse)", ["loop", "show", name], expect=[])
        for line in proc.stdout.splitlines():
            if "Total Runs:" in line:
                digits = "".join(ch for ch in line.split("Total Runs:")[1] if ch.isdigit())
                return int(digits) if digits else -1
        return -1


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default="/work")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    smoke_dir = root / ".smoke-project"
    smoke_dir.mkdir(parents=True, exist_ok=True)

    if not os.getenv("DEEPSEEK_API_KEY"):
        # Mirror e2e_llm_routing.py's guard — the loop tick routes through
        # the keyword layer without an LLM, but scan-candidates/triage-path
        # commands are only meaningfully exercised with the key present.
        print("FATAL: DEEPSEEK_API_KEY not set")
        return 2

    _write_smoke_config(smoke_dir)
    smoke = Smoke(smoke_dir)

    # gate25 pi F5: isolation as a measurable invariant, not a convention.
    fingerprint_before = _vibe_state_fingerprint(root)

    # ---------------- Tier 1: loop lifecycle (real execution) ----------------
    # gate25 MAJOR-2a: a leftover smoke-loop from a previous interrupted run
    # would hard-fail `create` (name collision, exit 1) — best-effort clean
    # first so the suite is re-runnable.
    smoke.run(
        "loop pre-clean (best-effort)",
        ["loop", "delete", "smoke-loop", "--force"],
        expect_rc=(0, 1),
    )
    smoke.run(
        "loop create",
        ["loop", "create", "smoke-loop", "--skill", "session-end", "--schedule", "* * * * *"],
        expect=["Loop Created", "smoke-loop"],
    )
    smoke.run("loop list shows created", ["loop", "list"], expect=["smoke-loop"])
    # tick executes the real routing pipeline (AgentRuntime.handle_query);
    # allow it to be slow, but cap the wait so a hung tick fails the suite.
    # gate25 MAJOR-1: --name is mandatory — LoopStore is HOME-level, so a
    # bare tick on a non-pristine HOME would really execute UNRELATED loops
    # (real LLM cost + side effects) and flip rc=1 on their failures.
    smoke.run(
        "loop tick executes once",
        ["loop", "tick", "--name", "smoke-loop"],
        expect=["Tick 完成"],
        timeout=150,
    )
    runs_after_tick = smoke.loop_total_runs("smoke-loop")
    record(
        "loop show records the run",
        runs_after_tick == 1,
        f"total_runs={runs_after_tick}",
    )
    smoke.run("loop pause", ["loop", "pause", "smoke-loop"], expect=["已暂停"])
    # --name scopes the tick to our loop: with it paused there is nothing
    # eligible. LoopStore is HOME-level (~/.vibe/loops), so a plain
    # `loop tick` would also see unrelated loops from the host HOME —
    # scoping keeps the assertion independent of pre-existing state.
    smoke.run(
        "loop tick skips paused",
        ["loop", "tick", "--name", "smoke-loop"],
        expect=["没有可执行的 loop"],
    )
    runs_after_paused_tick = smoke.loop_total_runs("smoke-loop")
    record(
        "paused tick adds no run record",
        runs_after_paused_tick == runs_after_tick,
        f"total_runs {runs_after_tick}->{runs_after_paused_tick}",
    )
    smoke.run("loop resume", ["loop", "resume", "smoke-loop"], expect=["已恢复"])
    smoke.run(
        "loop delete --force",
        ["loop", "delete", "smoke-loop", "--force"],
        expect=["已删除"],
    )
    # LoopStore is HOME-level — assert absence of OUR loop, not an empty
    # store (the host may carry unrelated loops).
    smoke.run(
        "loop list no longer shows deleted loop",
        ["loop", "list"],
        expect_absent=["smoke-loop"],
    )

    # Failure machinery (gate25 pi F4 / claude#6): a loop whose target fails
    # reaches DEAD at max_failures=1, then `loop reset` revives it.
    # Deviation from pi's literal sketch ("skill pointing at a nonexistent
    # skill"): /slash-route prefixes turn ANY --skill value into a "use X"
    # query that the keyword layer resolves to builtin/slash-route itself —
    # a nonexistent skill id still SUCCEEDS (verified locally). A
    # --command target whose subcommand exits non-zero is the deterministic
    # failure path, and it exercises the same record/state machine.
    smoke.run(
        "loop pre-clean smoke-fail (best-effort)",
        ["loop", "delete", "smoke-fail", "--force"],
        expect_rc=(0, 1),
    )
    smoke.run(
        "loop create failing target",
        [
            "loop",
            "create",
            "smoke-fail",
            "--command",
            "skills info nonexistent-xyz",
            "--schedule",
            "* * * * *",
            "--max-failures",
            "1",
        ],
        expect=["Loop Created"],
    )
    smoke.run(
        "loop tick records the failure",
        ["loop", "tick", "--name", "smoke-fail"],
        # tick exits 1 when any loop failed (loop_cmd.py C3: external cron
        # must be able to detect total failure) — that IS the contract here.
        expect_rc=1,
        expect=["1 失败"],
        timeout=150,
    )
    smoke.run(
        "loop reaches DEAD at max_failures=1",
        ["loop", "show", "smoke-fail"],
        expect=["dead"],
    )
    smoke.run(
        "loop reset revives to ACTIVE",
        ["loop", "reset", "smoke-fail"],
        expect=["已重置为 ACTIVE"],
    )
    smoke.run(
        "loop cleanup smoke-fail",
        ["loop", "delete", "smoke-fail", "--force"],
        expect=["已删除"],
    )

    # ---------------- Tier 1: M12 observability surface ----------------
    _seed_spans(smoke_dir)
    smoke.run(
        "skill scan-candidates",
        ["skill", "scan-candidates"],
        expect=["Scanned"],
        timeout=150,
    )
    proc = smoke.run("skill candidates", ["skill", "candidates"])
    record(
        "skill candidates lists the seeded cluster",
        # gate25 claude#3 / pi F2: pin the SEEDED cluster's identity — a
        # pre-existing row in the (HOME-level) global store could otherwise
        # satisfy a bare "stable"/"unstable" check. The table wraps long
        # queries across lines, so assert on the distinctive fragment.
        proc.returncode == 0 and "行为冒烟" in proc.stdout,
        "seeded query fragment present" if proc.returncode == 0 else "rc!=0",
    )
    proc = smoke.run("skill discover", ["skill", "discover"], timeout=120)
    record(
        "skill discover renders queue or honest empty guidance",
        proc.returncode == 0 and ("Discovery queue" in proc.stdout or "暂无候选" in proc.stdout),
        "",
    )
    smoke.run("sequence status", ["sequence", "status"])
    smoke.run("instinct status", ["instinct", "status"])
    smoke.run("route-stats", ["route-stats"])
    smoke.run("trace list-traces", ["trace", "list-traces"])

    # ---------------- Tier 1: state commands (no-data tolerant) ----------------
    smoke.run("session summary", ["session", "summary"])
    smoke.run("feedback list", ["feedback", "list"])
    smoke.run("deviation summary", ["deviation", "summary"])

    # ---------------- Tier 2: read-only snapshots (exit 0) ----------------
    # gate25 pi F3: status/doctor get one cheap output marker each; the
    # rest of Tier 2 stays rc-only by design.
    smoke.run("status", ["status"], expect=["vibe route"], timeout=120)
    smoke.run("doctor", ["doctor"], expect=["All checks passed"], timeout=120)
    for name, cmd in [
        ("version", ["version"]),
        ("preferences", ["preferences"]),
        ("top-skills", ["top-skills"]),
        ("algorithms", ["algorithms"]),
        ("targets", ["targets"]),
        ("inspect", ["inspect"]),
        ("workflows list-workflows", ["workflows", "list-workflows"]),
        # bare `badges` exits 2 (typer group without default command —
        # "Missing command"); the listable form is `badges list`.
        ("badges list", ["badges", "list"]),
        ("plan list", ["plan", "list"]),
        ("matcher list", ["matcher", "list"]),
        ("pool list", ["pool", "list"]),
        # config has no `show` subcommand (only `platforms`); bare `config`
        # prints the group panel with exit 0.
        ("config (bare)", ["config"]),
        ("skills list", ["skills", "list"]),
        ("skill list", ["skill", "list"]),
        # gate25 claude#7: data/analyze are --help-level only → Tier 3.
    ]:
        smoke.run(name, cmd, timeout=120)

    # verify: exit 1 in an undeployed environment is the CORRECT signal
    # (checks failed), not a bug — assert the report renders and the exit
    # code is one of the two documented semantics.
    smoke.run(
        "verify (undeployed env → report + rc 0/1)",
        ["verify"],
        expect_rc=(0, 1),
        expect=["checks"],
        timeout=120,
    )

    # dashboard: start → poll until HTTP 200 or timeout → kill (process group).
    # gate25 claude#4 / pi F8: server output goes to a log file (bind
    # failures leave evidence), and BOTH kill paths tolerate an
    # already-exited process.
    port = _free_port()
    dash_log_path = smoke_dir / "dashboard.log"
    with dash_log_path.open("w", encoding="utf-8") as dash_log:
        dash = subprocess.Popen(
            ["uv", "run", "--frozen", "vibe", "dashboard", "--no-open", "--port", str(port)],
            cwd=smoke_dir,
            stdout=dash_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            http_code = 0
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as resp:
                        http_code = resp.status
                        break
                except Exception:  # connection refused while the server boots
                    time.sleep(1)
            record(
                "dashboard serves HTTP 200",
                http_code == 200,
                f"port={port} http={http_code} log={dash_log_path}",
            )
        finally:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(dash.pid, signal.SIGTERM)
            try:
                dash.wait(timeout=10)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(dash.pid, signal.SIGKILL)
                dash.wait(timeout=10)

    # ---------------- Tier 3: --help only (network / interactive) ----------------
    for name, cmd in [
        ("market --help", ["market", "--help"]),
        ("install --help", ["install", "--help"]),
        ("sync-registry --help", ["sync-registry", "--help"]),
        ("quickstart --help", ["quickstart", "--help"]),
        ("onboard --help", ["onboard", "--help"]),
        ("prompt-chain --help", ["prompt-chain", "--help"]),
        ("data --help", ["data", "--help"]),
        ("analyze --help", ["analyze", "--help"]),
    ]:
        smoke.run(name, cmd)

    # gate25 pi F5: the smoke project is fully self-contained — any drift
    # in the project-root .vibe means a command escaped its cwd isolation.
    fingerprint_after = _vibe_state_fingerprint(root)
    record(
        "project-root .vibe untouched by smoke run",
        fingerprint_after == fingerprint_before,
        "fingerprint match" if fingerprint_after == fingerprint_before else "DRIFT detected",
    )

    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{'=' * 60}\nSMOKE SUMMARY: {len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILED: " + json.dumps(failed, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
