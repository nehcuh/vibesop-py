# Gate 25 Review — `scripts/e2e_command_smoke.py`

## Verdict: **PASS_WITH_NITS**

Every output marker, exit-code semantic, and model signature asserted by the script was verified against source. The assertion net is genuinely tighter than it looks on the surface (details below), but two robustness issues would make me require a small follow-up before this becomes a repeated CI gate.

---

## Findings

**1. MAJOR — Suite is not rerunnable after any mid-run failure (no pre-clean + unhandled timeout).**
`vibe loop create` hard-fails on an existing name (`loop_cmd.py:327-331`, exit 1), and `Smoke.run` (line ~111) lets `subprocess.TimeoutExpired` propagate — so one hung command (LLM stall > 150s, dashboard weirdness) kills the script with a traceback, **no summary**, and `smoke-loop` left in `~/.vibe/loops/`. Every subsequent run then false-fails at case 2 with "已存在". Fix: best-effort `loop delete smoke-loop --force` (ignore rc) before create, and catch `TimeoutExpired` in `run()` → `record(name, False, "timeout")`.

**2. MAJOR — First `loop tick` (line ~167) is unscoped, contradicting the script's own isolation comment.**
The paused tick gets a three-line comment justifying `--name` scoping against HOME-level store pollution, but the *executing* tick is bare. On any non-fresh HOME (e.g., accidentally run on the dev machine, which has launchd loop presets installed per project memory) it would execute unrelated real loops — real LLM spend, real side effects — and any unrelated loop's failure flips rc to 1 (`loop_cmd.py:743-744`) = false red. Coverage loss from adding `--name` is just the name-filter branch; the kill-switch/execute paths are identical. Either scope it or comment why not.

**3. NIT — "skill candidates lists the seeded cluster" (line ~218) doesn't pin the seeded cluster.**
Any candidate row satisfies it, including pre-existing global-store rows (`~/.vibe/observability`, read unconditionally per `skill_commands.py:1636-1648`). Note the empty state is *not* a false green — "No candidates in pool" (`skill_commands.py:1682-1684`) contains neither bucket word — but asserting the representative query text (`"smoke 行为冒烟查询"`) would make it airtight.

**4. NIT — Dashboard failure paths are undiagnosable / slightly racy.**
`_free_port()` (line ~141) has the classic bind-then-release TOCTOU race, and `stdout/stderr=DEVNULL` (line ~268) means a bind failure costs a silent 45s stall with zero evidence. Also the second `os.killpg` (SIGKILL path, line ~286) isn't wrapped in `suppress(ProcessLookupError)` — a process that dies between `wait()` timeout and SIGKILL crashes the script before the summary prints. The SIGTERM `killpg` itself is correct (`start_new_session=True` → pgid == pid).

**5. NIT — No upfront `DEEPSEEK_API_KEY` guard.**
Missing key silently writes `api_key = ""` (line ~54), defusing later into a confusing tick auth failure. `e2e_llm_routing.py:157-159` has the `FATAL` / rc=2 convention; mirror it for consistency.

**6. NIT — `reset` path uncovered with no conscious-skip comment.**
Fair to skip (reset only acts on DEAD loops, `loop_cmd.py:609-614`, and driving a loop DEAD first is out of scope for a smoke) — but the script is otherwise meticulous about documenting degraded tiers; add one comment here too.

**7. NIT — `data --help` / `analyze --help` are filed under Tier 2 "read-only snapshots"** though they're help-tier by the script's own taxonomy. Cosmetic.

---

## Verified sound (adversarial checks that did NOT break)

- **"loop tick executes once" is transitively strong**, not exit-code-only: `Total Runs` increments even on *failed* runs (`executor.py:415` persists unconditionally), but rc=0 requires `failure_count == 0` (`loop_cmd.py:743-744`) and `"Tick 完成"` requires ≥1 triggered (the empty-trigger path prints `本轮无可触发 loop` instead, :676-679). Together they assert the routing pipeline actually succeeded with a match — this is the suite's best assertion.
- **No cron-minute flake**: `should_run` is minute-granularity and `CronDaemon.run_once` is stateless with no same-minute dedup (`scheduler.py:213-234, 260-297`), so `* * * * *` is deterministically due; the paused tick exits via the status filter before cron evaluation.
- **All CJK/markers match source exactly**: `Loop Created` (:337), `Total Runs:` (:437, parse survives the Panel border — Rich emits no ANSI under captured pipes), `已暂停`/`已恢复`/`已删除` (:551/:590/:510), `没有可执行的 loop` (:668), `Scanned` (`skill_commands.py:1468`), `Discovery queue` (:2393) / `暂无候选` (:2380) — both discover branches real.
- **Span seeding is type-correct**: `SpanKind` is a `Literal`, not an enum (`models.py:21`), all kwargs match dataclass fields, `SpanWriter(storage_path)` positional ✓, `set_ok()` ✓.
- **Honesty sites check out**: verify rc∈{0,1} with explicit comment (and "checks" appears in both outcomes, `main.py:1685-1688`); kill-switch necessity is real (`LoopConfig.enabled` defaults false, `manager.py:516-519`, and a disabled tick prints neither `Tick 完成` nor failure — the expect would catch it); badges/config comments match typer behavior; `dashboard --no-open/--port` flags exist (`dashboard_cmd.py:22,28`).
- **Cross-script isolation is real**: separate `.vibe` trees, config writes scoped to `.smoke-project`; `uv run` walks up to `/work` for the lockfile while the child cwd stays in the smoke dir.
- **Conventions consistent** with `e2e_llm_routing.py`: `--project-root` default `/work`, `PASS/FAIL` record lines, `SUMMARY: x/y` marker, exit 1 on failure.

**Residual risk**: until finding 1 is fixed, a single mid-run failure poisons every subsequent smoke run (stale `smoke-loop` in the HOME-level store), and until finding 2 is fixed, running the script anywhere but a fresh container executes whatever real loops it finds.
