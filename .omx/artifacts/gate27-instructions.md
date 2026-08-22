# Gate 27 review — LoopSpec project ownership (implementation of gate26 design)

You are an independent senior code reviewer. Review the attached diff (git diff of the working tree) for VibeSOP. The design + dual design-review revisions are in `.omx/artifacts/gate26-design.md` (read it first — the 7 revision items at the bottom are binding).

## Summary of what the diff should implement

LoopStore stays HOME-level (user-level daemon model kept). New `LoopSpec.project_root: str | None` (None = legacy/global, deliberate double meaning). Ownership pinned only by explicit verbs: create (default literal cwd, `--global` opt-out, untrusted-cwd warning), adopt, migrate-ownership (plist WorkingDirectory backfill, confirm-by-default, --dry-run). install-launchd does NOT backfill — only warns when spec.project_root set and ≠ cwd. Bare `tick` filters by `_owns` (cwd within project_root, resolve both sides) and prints a loud skip line naming skipped loops (cap 5) EVEN in the zero-triggered branch; `tick --name` bypasses (launchd shape unchanged); `tick --all` is the cron-from-~ compat hatch. Executor: CLI tick constructs `AgentRuntime(project_root=exec_root)` per spec (NO chdir — runtime freezes project_root at construction); command path passes exec_root as subprocess cwd (fixes the never-passed param at old executor.py:348); missing exec_root → pre-flight PERMANENT failure whose suggestion mandates `vibe loop adopt` + `vibe loop reset`; OSError branch distinguishes missing-cwd from missing-uv; `state.spec = spec` rebound before record_run. CHANGELOG has a precise downgrade-quarantine warning (old builds rename spec.json → .corrupt). models.py/store.py docstrings no longer promise git-tracked specs.

Tests: 33 new (tests/core/loop + tests/cli/test_loop_cmd.py). e2e_command_smoke.py loop section extended (spec pins cwd; bare tick from a second temp project skips loudly; tick --name executes with artifacts landing in the owner root).

## Known open item (being investigated in parallel — do NOT review it as part of this diff)

Container e2e currently 64/65: `skill candidates lists the seeded cluster` fails BOTH on this diff and on HEAD (agent's claim, being verified independently). Suspected embedding-availability flake de-clustering the seeded miss variants (pi's gate25 F2 predicted exactly this fragility). If confirmed pre-existing/environmental, it ships as-is with a follow-up.

## Review focus

1. Does the implementation match gate26-design.md including all 7 revision items? Any drift?
2. `_owns` correctness: resolve() both sides, None → True, one-directional (documented). Symlink/case edges acceptable?
3. tick: skip line in ALL branches (zero-eligible, zero-triggered, normal)? --name bypass intact? --all hatch?
4. Executor: per-spec runtime construction (no chdir anywhere)? pre-flight PERMANENT with mandated suggestion text? command path cwd? state.spec rebind before record_run?
5. migrate-ownership: dry-run truly side-effect free? confirm-by-default? non-macOS path? missing-plist loops listed for adopt? --global pinning documented?
6. Backward compat: legacy spec (no field) → None → identical behavior everywhere? Downgrade warning precise?
7. Test quality: do the 33 new tests lock the semantics (not just exit codes)? e2e additions real?
8. Concurrency: adopt/migrate holding the blocking tick lock — consistent with pause/resume/reset pattern? Any new race?

## Output

Verdict: PASS / PASS_WITH_NITS / BLOCK + numbered findings with severity + file:line refs + one-line residual risk. Be adversarial; do not rubber-stamp.
