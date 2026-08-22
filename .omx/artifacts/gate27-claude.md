# Gate 27 Review — LoopSpec project ownership

**Verdict: PASS_WITH_NITS**

All 7 gate26 revision items are implemented and tested; I found no drift from the binding design. Verified by execution: 159 tests in the three touched files pass (35 of them new — the brief says 33, summary drift only), ruff clean on all changed files, no `chdir` anywhere in the loop subsystem.

## Findings

**1. MINOR — relative `project_root` is unvalidated and resolves against the wrong base.** `models.py:150` accepts any string; executor does `Path(spec.project_root).resolve()` (executor.py:379) and `_owns` resolves likewise (loop_cmd.py:95). A hand-edited *relative* value resolves against the tick process's ambient cwd — for a launchd `tick --name` that's the plist WorkingDirectory, so the exec root becomes cwd-dependent nondeterminism rather than a wrong-but-fixed root. The design accepted "hand-edited fake root = hand-edited plist trust", but that argument covers wrong *values*, not wrong-*shaped* ones. A one-line `Field` validator (`Path(v).is_absolute()`) closes it.
*Residual risk: low — requires hand-editing spec.json with a relative path; consequence is one mis-rooted execution, then PERMANENT/skip visibility.*

**2. MINOR — adopt/migrate vs tick TOCTOU on the spec object (accepted granularity, but worth naming).** tick enumerates specs and filters status *outside* the per-loop lock (loop_cmd.py:862, 897-902); the lock is only held around `execute_loop_tick` (950-979). If adopt re-pins in that window, the in-flight tick executes with the stale spec (legacy ambient-cwd shape) and its `state.spec = spec` rebind (executor.py:374) re-embeds the stale copy into state.json, undoing adopt's state sync until the next tick. spec.json is never clobbered; self-heals on the next enumeration. This is exactly the pause/resume/reset granularity (pause also loads spec pre-lock, loop_cmd.py:598) and the documented serial-tick v1 premise, so not a blocker — but the adopt docstring's "can't persist a stale state.json" (loop_cmd.py:725-726) overpromises vs this window. Optional hardening: re-read `store.load_spec(name)` inside `execute_loop_tick` under the lock.
*Residual risk: low — requires adopt racing a due tick within a ~ms window; worst case is one legacy-shaped execution + cosmetic stale state copy.*

**3. NIT — `_owns` docstring overpromises on case-insensitive FS.** loop_cmd.py:86 claims resolve() "survives symlinks / macOS case-insensitive FS". resolve() handles symlinks but does **not** casefold; a pinned path differing only in case from cwd on APFS still fails `_owns`. The design explicitly accepted "no casefold (accepted edge)" — the docstring should restate that instead of claiming survival.

**4. NIT — create's "LITERAL cwd (not resolved)" comment is wrong about the mechanism.** loop_cmd.py:329-330. `Path.cwd()` returns the OS-physical path (getcwd resolves symlinks), not the user's logical shell `pwd`. The *behavior* is the right one (pins physical, consistent with `_owns`'s resolve-both-sides); only the comment mischaracterizes it.

**5. NIT — CHANGELOG downgrade warning omits state.json.** store.py:174-191 quarantine fires identically for state.json on downgrade (LoopState embeds LoopSpec; both `extra="forbid"`, models.py:143/353-355) — "loop 消失" actually triggers via both files. The remediation (backup `~/.vibe/loops/`) already covers it; one clause would make the "精确化" warning fully precise.

**6. NIT — migrate-ownership's non-macOS path is code-verified only.** All six TestMigrateOwnership tests monkeypatch `_is_macos` to True; the real non-macOS branch (everything → no_plist → adopt suggestions, loop_cmd.py:784-785, 812-818) has no test, despite CI running Ubuntu where it's the *default* path. One test without the patch would lock it.

**7. NIT — `list --status` + ownership-empty hides the real cause.** loop_cmd.py:438-443: with `--status active` and all matches hidden by ownership, the early return prints "没有匹配状态" and the `hidden` hint at 478 is unreachable — ownership filtering is the actual cause but is invisible.

## Review-focus checklist (all verified)

1. **Design conformance**: all 7 revisions present — per-spec runtime, no chdir (grep-verified; only an explanatory comment remains, loop_cmd.py:959); install-launchd warns-only (1225-1235, dry-run-tested); CHANGELOG quarantine mechanism matches store.py exactly (`.corrupt` rename + rmtree deletes backup, store.py:85/181-184); pre-flight PERMANENT with mandated `adopt`+`reset` suggestion (executor.py:222-242); state rebind (374); `_is_project_root_trusted` reuse (336/718); all of nit-item 7 (cap-5 names, zero-trigger skip line, `--all` help, one-directional doc, e2e pinned-root assertion, models/store git-tracking correction, `(global)` marker).
2. **`_owns`**: resolve both sides, None→True, one-directional, OSError→False — correct; edges per findings 1/3.
3. **tick**: skip line prints before every early return except trivial no-loops (886-892, before branches at 904/914 — both branch-tested); `--name` bypass intact (878-880); `--all` hatch tested.
4. **Executor**: per-spec runtime 963-967 with `AgentRuntime()` fallback for unscoped (verified constructor at agent_runtime.py:277); command path passes resolved exec_root (417-419, test captures subprocess `cwd` kwarg); OSError branch distinguishes missing-cwd/missing-uv both directions (300-323, tested).
5. **migrate-ownership**: dry-run truly side-effect-free (no lock/save/prompt, 788-791); confirm-by-default (default=True) + `--yes`; non-macOS handled (finding 6); no-plist → adopt suggestions; `--global` pinning documented in docstring.
6. **Backward compat**: legacy no-field → None → identical behavior at every consumer (`_owns`, executor cwd, runtime), locked by round-trip + unpinned-path tests.
7. **Test quality**: semantics locked, not exit codes — state.spec sync asserted via reload, pre-flight asserts nothing-executed *and* budget advanced, suggestion text asserted verbatim. e2e additions are real: the artifact-location assertion (marker in pinned root, absent from ambient cwd) is a genuine end-to-end proof of the executor fix, with a negative control; `_write_smoke_config(other_dir)` is correctly load-bearing for the C2 kill-switch.
8. **Concurrency**: tick holds the per-loop lock across `execute_loop_tick`; adopt/migrate block on the same lock around spec+state writes — exactly the pause/resume/reset pattern. No new lock-ordering or RMW race beyond finding 2's window.

The known open e2e item (64/65 skill-candidates) was excluded per instructions. Both MINORs sit inside the design's explicitly accepted risk envelope with cheap optional fixes — neither blocks ship.
