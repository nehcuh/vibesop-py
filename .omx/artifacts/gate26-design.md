# Gate 26 (design review) — LoopStore 跨项目归属设计定稿

You are reviewing a DESIGN (not code) for VibeSOP's `vibe loop` subsystem. Three independent designers produced proposals; B and C independently converged on the same core. This document is the synthesis to review. Code refs: src/vibesop/core/loop/{store,models,executor,launchd}.py, src/vibesop/cli/commands/loop_cmd.py.

## Problem (corrected by designer C's fact-check)

- LoopStore is HOME-level (`~/.vibe/loops/`), `LoopSpec.name` is globally unique BY DESIGN, launchd plists pin WorkingDirectory to the project root — the "user-level daemon" model is coherent and `loop list` showing all loops from any cwd is NOT a bug (like `crontab -l`).
- THE REAL BUG: `LoopSpec` never records project ownership, and the executor falls back to ambient cwd (`_run_command_target(project_root=None)` → subprocess inherits cwd; routing path uses AgentRuntime in cwd). install-launchd validates the project root at install time but writes it ONLY into the plist, never into the spec. So a bare `vibe loop tick` (manual / system crontab) in project B executes project A's DUE loop with B's context, and the resulting failure is recorded against A's loop — burning its DEAD budget (state pollution).

## Synthesized design (B+C convergence)

1. **Keep HOME store.** No file moves, no registry, no walk-up infra, no launchd label changes. (Designer A's project-level storage was rejected: 20x cost, fixes mostly the non-bug, self-admitted migration blind spot for crontab-driven legacy loops, and `vibe init` gitignores all of `.vibe/` so "spec becomes git-trackable" needs template surgery anyway.)
2. **Add `project_root: str | None = None` to LoopSpec.** None = unscoped (global): visible and runnable from any cwd — deliberately covers BOTH legacy specs (behavior unchanged) and explicit `vibe loop create --global`. The None double-meaning (legacy-unknown vs deliberate-global) is consciously accepted: a third sentinel would force every consumer to answer "what does unknown mean" and the honest answer is always "current behavior".
3. **Ownership is pinned only by explicit user action** — create (default cwd, `--global` opts out), `vibe loop adopt <name>` (pins cwd, soft trust warning), `vibe loop migrate-ownership [--dry-run]` (reads `~/Library/LaunchAgents/com.vibesop.loop.*.plist` WorkingDirectory → backfills), install-launchd (backfills if None). NO auto-backfill on tick — enumerating ticks would mis-attribute every None loop to whatever project happened to run first; mis-attribution persisted is worse than none.
4. **CLI semantics**: `list` defaults to owned (current-project via `_owns`: None or cwd-is-within-project_root, resolve() both sides) + `--all` with a Project column. Bare `tick` executes only owned loops + prints a loud skip line ("N loop(s) belong to other projects, skipped — use --all"); `tick --name X` bypasses ownership filtering (that is the launchd call shape — unchanged); `tick --all` is the compat hatch for system-cron-from-~ users. show/pause/resume/reset/delete address by globally-unique name WITHOUT ownership filtering (legit cross-project ops) but `show` gains a Project line. `create` name-collision error names the conflicting loop's project.
5. **Executor consumes ownership**: `execute_loop_tick` resolves `exec_root = spec.project_root or None`; command path passes it as subprocess cwd (fixing the existing never-passed `project_root` param at executor.py:348); routing path wraps `runtime.handle_query` in os.chdir(exec_root) + try/finally restore (serial-tick is already a documented v1 premise — the docstring's "callers must serialise" upgrades from convention to PRECONDITION). Missing exec_root directory → PERMANENT failure via the existing record/state path (loud, consumes DEAD budget deliberately — observable signal for `adopt` re-pinning) instead of silently running in the wrong cwd.
6. **Compatibility & risks**: `ConfigDict(extra="forbid")` means old vibe builds REFUSE spec.json with the new field → CHANGELOG carries a prominent no-downgrade warning. state.json embeds a spec copy — reads always go through load_spec, stale copies harmless. macOS case-insensitive FS / symlinks: resolve() both sides, no casefold (accepted edge). Hand-edited fake project_root: same trust model as hand-edited plists.
7. **Tests**: list/tick ownership filtering, --name bypass, --all, legacy-spec (no field) round-trip, executor cwd fix on command path + chdir restore on routing path, missing exec_root → PERMANENT, adopt/migrate-ownership, name-collision message, downgrade-warning doc check.
8. **e2e**: extend scripts/e2e_command_smoke.py loop section — create pins cwd; bare tick from a second temp project skips the smoke loop (loud skip line asserted); tick --name still executes.

## Review focus

1. Is rejecting project-level storage (A) sound? Any real requirement A serves that B+C doesn't (git-tracked specs as project CI resource? same-name loops in two projects?)?
2. The None double-meaning — acceptable, or should legacy vs deliberate-global be distinguishable?
3. Executor chdir on the routing path — process-global mutation; is the serial-tick precondition enforceable/documented enough? Alternative you'd prefer?
4. Missing-exec_root → PERMANENT consumes DEAD budget deliberately — right call vs TRANSIENT vs skip-with-warning?
5. tick behavior change (bare tick no longer runs other-project loops) is loud but is a behavior change — is the loud skip line + --all hatch enough for system-cron users?
6. Anything in the synthesis that contradicts the code facts above.

Output: verdict PASS / PASS_WITH_NITS / BLOCK + numbered findings with severity + one-line residual risk. Be adversarial.

---

# Gate 26 复审修订（claude 2 MAJOR + 6 MINOR/NIT,pi BLOCK + 6 findings,双路独立收敛)

1. **路由路径废弃 chdir**(双路共识 BLOCK/MAJOR-1):AgentRuntime 构造时冻结 project_root(agent_runtime.py:277),chdir 无效。改为 **CLI tick 循环内按 spec 构造 `AgentRuntime(project_root=exec_root)`**(组件懒加载,成本可忽略);无进程全局突变,串行前提无需升级。command 路径:修 executor.py:348 从不传参的缺口,subprocess cwd=exec_root。
2. **install-launchd 移除回填**(claude MAJOR-2 选 b + pi#3):归属写入只允许显式动词(create 默认钉 cwd + `--global`  opt-out / adopt / migrate-ownership confirm-by-default + --dry-run);install-launchd 只在 spec.project_root 已设且 ≠ cwd 时警告。migrate-ownership 文档写明会钉住 --global loop。
3. **降级警告精确化**(双路):旧版 vibe 读新 spec.json 不是"拒绝"而是**隔离**——_load_model 改名 .corrupt,loop 消失、launchd 每分钟 spam、delete 会 rmtree 备份。CHANGELOG 写明机制 + "降级前备份 ~/.vibe/loops/"。
4. **missing exec_root 机制明确**(pi#5):executor 加 pre-flight is_dir() 检查,构造 PERMANENT FailureInfo,suggestion 强制为 "vibe loop adopt <name> + vibe loop reset <name>"(claude MINOR-4);command 路径 OSError 分支区分 missing-cwd 与 missing-uv(现误导文案)。
5. **state.spec 陈旧副本**(claude MINOR-5 + pi#6):execute_loop_tick 在 record_run 前重绑 `state.spec = spec`(单行);adopt/migrate 顺手 save_state。
6. **create/adopt 复用 _is_project_root_trusted**(claude MINOR-6 + pi#4):untrusted cwd → 警告(--global 逃生);不拒绝(create 只是写 JSON);钉字面 cwd,文档写明。
7. nit 项:跳过行列名字(上限 5)+ 零触发分支也要打印;tick --all 写进 help;`_owns` 单向性文档化;e2e 断言 tick --name 在归属项目根执行;models.py:17-19 "git 可追踪"虚假承诺改正;list 的 None loop 标 "(global)"。
