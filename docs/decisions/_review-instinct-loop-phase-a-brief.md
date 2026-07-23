# Phase A Milestone Review Brief — LoopSpec `command_args` + Executor Subprocess Branch

**Date:** 2026-07-23
**Plan:** `/Users/huchen/.claude/plans/starry-herding-stream.md` (v2)
**Phase A scope:** Core extension only — `LoopSpec.command_args` field + executor subprocess branch. No CLI/launchd/instinct changes yet (those are Phases B-E).

## What changed

| File | Lines | Change |
|------|-------|--------|
| `src/vibesop/core/loop/models.py` | ~30 | Add `command_args: list[str]` + `timeout_s: float` fields; extend `_exactly_one_target` from 3-way to 4-way xor |
| `src/vibesop/core/loop/executor.py` | ~150 | Add `_COMMAND_PERMANENT_KEYWORDS`, `_classify_command_failure`, `_run_command_target`; thread command branch into existing `execute_loop_tick` while-loop with retry/state-machine reuse |
| `tests/core/loop/test_models.py` | ~75 | 6 new tests for `command_args` xor + JSON round-trip |
| `tests/core/loop/test_executor.py` | ~300 | 11 new tests for `_run_command_target` + `execute_loop_tick` command path |

## Verification status

```
163 passed, 1 skipped   # tests/core/loop/
All checks passed!       # ruff
0 errors, 0 warnings     # basedpyright
```

## Key design decisions made

1. **`command_args` as flat field, not subclass.** Project precedent (commit 553622d added `MetricCondition` as flat field). Pydantic `extra="forbid"` accepts new declared fields fine.

2. **`_run_command_target` does NOT raise.** It mutates `record` in place; success/error/timeout are written to fields. The retry while-loop in `execute_loop_tick` reads `record.success` and `record.failure_info`, falling through to the existing retry logic + DEAD/FAILING state machine. This is the merged kimi/pi fix for "don't bypass state machine."

3. **Unknown command failures default to TRANSIENT.** pi's MUST-FIX from plan v2 — command-target failures are usually environmental (uv not on PATH, locked .venv, file races). Only explicit usage/permission/file-not-found keywords → PERMANENT. `_COMMAND_PERMANENT_KEYWORDS` is separate from routing's `_PERMANENT_KEYWORDS` to keep semantics clean.

4. **VIBESOP_RUN_PREFIX parsed via `shlex.split`.** Adversarial review caught that plain `.split()` would break `"/path/with space/uv"` into 2 args. Users must quote paths with spaces.

5. **Retry error accumulation.** Adversarial review §2 — across retries, `attempt_errors` list captures each attempt's error; final record.error includes them as `"attempt 1: ... | attempt 2: ... | final: ..."`.

6. **`failure: FailureInfo | None = None` defensive init.** Adversarial review §1 — latent `NameError` risk for future maintainers adding branches.

## What's deferred (with docstring caveats)

- **stdout OOM**: `capture_output=True` buffers full stdout in memory. Bounded by user-authored commands, but flagged. Defer to Phase B if needed.
- **Global tick-duration cap**: with `max_retries=10`, worst case ≈ 2.3h per tick. Documented in `max_retries` docstring.
- **`timeout_s=1.0` minimum too low**: documented in `timeout_s` docstring; users should set 30+ for real commands.

## Diff for review

The full 320-line source diff is at `/tmp/phase_a_diff.txt` (or run `git diff src/vibesop/core/loop/{models,executor}.py` in the project root).

## Questions for kimi + pi

### Q1 — State machine integration correctness

Verify by reading the modified `execute_loop_tick` while-loop (executor.py:327-391):
- Does the command branch correctly feed into `state.record_run(record)` + `store.save_state(state)`?
- With `max_failures=2`, PERMANENT command failure: ticks 1→FAILING, 2→DEAD. Test covers this; do you agree the path is correct?

### Q2 — Failure classification inversion

Routing path: unknown → PERMANENT (conservative).
Command path: unknown → TRANSIENT (pi's recommendation).

Both have separate keyword sets. Is this asymmetry justified? Or should both share the same default?

### Q3 — Retry error accumulation

`record.error` after retries = `"attempt 1: err1 | attempt 2: err2 | final: err3"`. This bloats the field. Should it instead:
- (a) keep as-is (debugging > tidiness)
- (b) move to a separate `attempt_history` field on LoopRunRecord (cleaner, but model change)
- (c) keep only last attempt (loses debugging)

### Q4 — Subprocess scope creep in core layer

`core/loop/executor.py` now imports `subprocess` + `os` + `shlex`. Precedent: `core/prompt_chain/validator.py:6` already imports subprocess. Do you accept this layering, or should `_run_command_target` move to CLI layer (which would require injecting it as a callback)?

### Q5 — Test gaps remaining

After adversarial review, 5 new tests were added (retry success, retry exhausted, env_overrides, prefix-with-spaces, stdout truncation). What's still untested?
- Concurrency: two `execute_loop_tick` calls on the same spec in parallel threads — guarded by `loop_cmd.py` advisory lock, but not unit-tested.
- Windows `fcntl.flock` fallback — Phase B work, but no placeholder test.
- `_run_command_target` directly with `spec.command_args` containing unicode.

### Q6 — Overall verdict for Phase A

- SHIP TO PHASE B
- FIX BEFORE PHASE B (specify which items)
- REWORK (something fundamental missed)

Keep response under 800 words. Cite file:line for any specific findings. If everything is fine, just say so — no need to invent concerns.

## Output

中文回答，按 P1 评审格式（参考 `docs/decisions/_review-p2-pi.md`）。Bottom line first, then per-question verdicts.
