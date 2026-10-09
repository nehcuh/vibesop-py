# B5 Grok post-commit gate

- Date: 2026-10-09
- Role: independent Grok read-only post-commit gate. This session did not author the commit and did not resume the authoring session.
- Verdict: **APPROVE** `e0b83a05037bb99b4157d453f59ea3e66a603a5d`
- Patch: **APPROVE** full SHA256 `759baff7b4fad44b9e92af0694104571f43b336a06e50fdd2f2d81a7b53f1d38` (20143 bytes, parent `74f418628ba5bbf9729fb78bd22aa886b55e1132`)

No source, test, changelog, patch, receipt, Docker image, API, auth, or global lock file was edited. No commit, push, or subagent. Native Windows CI was not run and is not claimed.

## Identity

[executed] Archive `/private/tmp/vibesop-opt-20261009/snapshots/B5-grok-post` (`/tmp/vibesop-opt-20261009/snapshots/B5-grok-post`):

| Item | Value |
|---|---|
| HEAD | `e0b83a05037bb99b4157d453f59ea3e66a603a5d` |
| Parent | `74f418628ba5bbf9729fb78bd22aa886b55e1132` |
| Tree / `git write-tree` | `a9ad8b3f7f6e069d1417b2a55252c052de0c99ee` (staged diff empty) |
| Shallow | false (`rev-list --count HEAD` = 1088) |
| Subject | `fix(execution): dispatch synchronous parallel steps to worker threads` |
| Author / committer | huchen, 2026-10-09T17:03:39+08:00 |
| Trailers | `Co-authored-by: Kimi Code <noreply@moonshot.ai>` and `Co-authored-by: Claude Code (GLM-5.3) <noreply@z.ai>` |
| `git diff HEAD^ HEAD` | 20143 bytes, 417 lines, SHA256 `759baff7b4fad44b9e92af0694104571f43b336a06e50fdd2f2d81a7b53f1d38` |
| `git show --format=` | same byte count and SHA256 |
| `git archive --format=tar HEAD` | SHA256 `14c8e4d999bcd24913730b4ae752ff8c09602655990f161c9a6cbd1311596988` |

[executed] That patch SHA256 and byte count match `B5-frozen.json`, `B5-commit-receipt.json`, `B5-post-frozen.json` (`patch_sha256` and `post_diff_sha256`), and `.omx/artifacts/diagnosis-B5.diff`. `cmp` of `git diff HEAD^ HEAD` against the diagnosis diff is identical. The diagnosis diff was read in full (417 lines, three file sections, +348/−3).

[executed] `B5-post-frozen.json.post_snapshot` is this archive. `archive_sha256` recomputed from `git archive --format=tar HEAD` matches the post receipt. Parent in the frozen, commit, and post receipts is `74f418628ba5bbf9729fb78bd22aa886b55e1132`, which is `HEAD^` and the instinct commit `fix(instinct): merge concurrent evidence without crossing action identities`.

Receipt `committed_paths` is exactly `CHANGELOG.md`, `src/vibesop/agent/step_runner.py`, `tests/agent/test_step_runner.py`. Tracked worktree after this gate is still only the pre-existing untracked diagnosis paths (`.omx/artifacts/diagnosis-B5.diff`, `docs/plans/2026-10-09-diagnosis-optimization.*`, `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/`). `git status --porcelain` before and after this gate is identical.

## Blob and source SHA256

[executed] Post worktree SHA256 = receipt `source_sha256` = SHA256 of `git cat-file blob HEAD:path`. After pytest and probes those hashes were unchanged.

| Path | Parent blob | HEAD blob | Source SHA256 | Bytes |
|---|---|---|---|---|
| `src/vibesop/agent/step_runner.py` | `938cb16b086cfe15034e227c56e321856986c0a2` | `86c94b22357b1ebed68d5ca3cfb94a7aa66f54c7` | `35197e7587c8ac21edec2d3a4fff7b07d83495c8d392f02c22f16e9d518c98f8` | 47955 (parent content `4f6ffed22a26e6e42232788fb190c21dd698077e32c74691fd9e7236f39f1b00`, 46404) |
| `tests/agent/test_step_runner.py` | `35a8efe6775d3fa63784b07402dd8b76e99aeb0e` | `c3be83348c925caddb02ddae47a36c6547e58b4b` | `8dc6c7d526dc1cf418c9d762d1ff760f305439ed56bdfbd441fc75e9ba6e0074` | 87735 |
| `CHANGELOG.md` | `867aeb38585026adbedd62bfe471aa10ec96532b` | `67257acf83b89085259382a5788581a972774e6b` | `f6e679f51352bfb4fd2d522817a1dd051547b0d714d3cbebd28d1db94da6679e` | 226223 |

[executed] `B5-final-after-B6`, `B5-final-after-B6-broad-target`, and `B5-final-after-B6-target` carry the same three source SHA256 values. Their HEAD is the parent `74f41862` with those three paths dirty. Every file under `src/` in `integration-candidate1` matches this commit byte for byte (821 paths same across `src/`, `tests/`, and the two workflow files; zero `src/` mismatches). Eight non-source paths differ: `CHANGELOG.md`, `.github/workflows/ci.yml`, `.github/workflows/quickstart-e2e.yml`, and five test files that contain extra W1 cases or a different artifact-link baseline (`tests/adapters/test_base.py`, `test_claude_code.py`, `test_kimi_cli.py`, `test_pi_coding_agent.py`, `tests/unit/test_check_artifact_links_baseline.py`). `tests/agent/test_step_runner.py` on that snapshot matches the frozen hash. Its mtime (2026-10-09 15:56:55) is earlier than both full-suite logs.

## Inputs re-read this session

- `B5-glm-dev-complete.md`: author lane is Claude Code CLI 2.1.153, backend **GLM-5.3**. [executed] `logs/B5-glm-dev.jsonl` line 2 init is `model=GLM-5.3`, `session_id=9177e49b-55d9-4267-b0c3-d854a77f28f3`, `claude_code_version=2.1.153`. Every model string in that log is `GLM-5.3`. Identity receipts `claude-glm-identity-config-receipt.json` / `claude-glm-identity-session-receipt.json`: explicit model `GLM-5.3`, `base_url` `https://open.bigmodel.cn/api/anthropic`, `global_settings_modified: false`, `credentials_included: false`. No Anthropic model identity. DEV_COMPLETE §六 still says the changelog was untouched; the committed patch contains the two B5 changelog bullets. That sentence is stale. The delivered file set is the approved three-path set.
- `B5-kimi-final-after-B6-report.md`: **APPROVE** on full SHA256 `759baff7b4fad44b9e92af0694104571f43b336a06e50fdd2f2d81a7b53f1d38`, with its own 834 and red/green on parent `74f41862` / content `4f6ffed2…`. This gate did not reuse that probe.
- [inspected] `logs/B5-final-after-B6-broad-target-container.log` + `.result.json`: patch `759baff7…`, image `vibesop-opt-depcache:20261009`, pytest `tests/agent` `tests/core/orchestration` `tests/core/skills/test_workflow_engine_enhanced.py -q`, **834 passed in 4.65s**, exit 0. This lane did not rerun Docker.
- [inspected] `logs/B5-final-after-B6-target-container.log` + `.result.json`: same patch SHA256, four files (`test_step_runner.py`, `test_execution_protocol.py`, `test_workflow_engine.py`, `test_workflow_engine_enhanced.py`), **101 passed in 0.36s**, exit 0. That is a different selection from the 834 run.
- [inspected] Full integration logs on `integration-candidate1`, whose `src/` matches this commit: color-fixed Docker `logs/integration-candidate1-color-fixed-container.log` **7829 passed, 26 skipped, 20 deselected**, coverage **80.95%** (TOTAL 42009 / 7162 / 13682 / 1543), exit 0, junit `tests=7855` `failures=0` `skipped=26`. Darwin host `logs/integration-candidate1-host.log` **7839 passed, 16 skipped, 20 deselected**, junit `tests=7855` `failures=0` `skipped=16`. 7829+26 and 7839+16 both equal 7855; the 10-count gap is tests skipped in Docker and passed on Darwin. An earlier retry log (`integration-candidate1-retry-container.log`, driver exit 1, 88 failed) fails on ANSI escape bytes in CLI stdout. The color-fixed log is the green run. This lane did not rerun either suite.

Receipt `changelog_note` still says the active changelog contains pending B2 changes. Parent `74f41862` already contains the B2 bullets (`7d1160f0` is an ancestor). Stale receipt wording. The B5 Changed and Fixed bullets themselves match the code. Receipts were not mutated.

## What this gate ran

Runner: snapshot `.venv` CPython 3.12.13. `vibesop.__file__` = `.../B5-grok-post/src/vibesop/__init__.py`. `HOME` / `XDG_CONFIG_HOME` / `XDG_CACHE_HOME` / `TMPDIR` were under `/tmp/vibesop-opt-20261009/probes-grok-b5-post/`. `PYTHONDONTWRITEBYTECODE=1`. Pytest used `-p no:cacheprovider`.

| Check | Result |
|---|---|
| pytest `tests/agent` `tests/core/orchestration` `tests/core/skills/test_workflow_engine_enhanced.py` `-q` | [executed] exit 0, **834 passed in 13.39s**, no skip line |
| `ruff check --no-cache` on the two Python files | [executed] exit 0, All checks passed |
| `ruff format --check --no-cache` | [executed] exit 0, 2 files already formatted |
| green probe on committed `35197e75…` | [executed] exit 0, 13/13 |
| red probe on parent blob `4f6ffed2…` loaded in a child process | [executed] exit 0, 12/12 |

Raw: `/tmp/vibesop-opt-20261009/probes-grok-b5-post/` (`grok_b5_post_probe.py`, `parent_step_runner.py`, `green.json`, `red.json`, `pytest.txt`, `ruff-check.txt`, `ruff-format.txt`, `git-status-before.txt`, `git-status-after.txt`, `home-before.json`, `home-after.json`).

[executed] User-global `~/.config/skills/.pack-locks` before and after: only `ui-ux-pro-max-skill.json` (same size, mtime, SHA256). `~/.vibe` direct children: same names, sizes, and mtimes. Zero new global writes.

## Independent probe

Public `ExecutionPlan` / `ExecutionStep` / `StepRunner.execute_all` only. `track_state=False`, `project_root` under the probe temp dir. Barrier timeout is 3s and exists so a serial implementation fails fast. No sleep and no wall-clock threshold.

[executed] Green, committed module `35197e75…`:

- Barrier(2), `max_parallel=2`: peak 2, events `enter, enter, exit, exit`, barrier not broken, completed 2 / failed 0 / `final_status=completed`, outputs `OK step-1` and `OK step-2`. Two worker threads, both distinct from the caller and from each other. Each executor received the plan's own `ExecutionStep` (`is`).
- `max_parallel=1`: peak 1, events `step-1 enter/exit` then `step-2 enter/exit`, completed 2 / failed 0, both calls on worker threads.
- ContextVar set to `grok-post-context-7f3a` in the caller was read back on a non-caller thread for both steps (thread-pool reuse put both fast reads on one worker ident). The barrier case is the two-thread proof.
- `async def` executor: body ran for `step-1` and `step-2`, outputs `ASYNC step-1` / `ASYNC step-2`, completed 2 / failed 0, no `<coroutine` repr.
- Worker `RuntimeError("grok-b5-worker-boom")`: `on_step_error` received that same object and `plan.steps[0]`, on the caller thread. completed 1 / failed 1 / blocked 0 / `partial`, output None, error text preserved, `outcome_status=failed`.
- Raw blocked dict `{"status":"blocked","reason":"grok-b5-need-evidence"}`: the result entry holds that same object, `outcome_status=blocked`, legacy `status=failed`, failed 1 and blocked 1, `partial`. `PlanExecutionResult.from_step_runner_dict(result, plan)` maps step-1 to `BLOCKED` and step-2 to `SUCCESS`. The same mapping holds after `outcome_status` is stripped, so the dict-only fallback still sees the preserved raw dict.

[executed] Red, parent blob `4f6ffed2…` (46404 bytes) substituted on `sys.modules` only inside the probe process. The archive file was not replaced.

- Source has zero `await asyncio.to_thread(` calls and still has `asyncio.Semaphore(self._max_parallel)`.
- Barrier(2): peak 1, all on the caller thread, barrier broken, completed 0 / failed 2 / `final_status=failed`, events `enter, exit, enter, exit`. `str(BrokenBarrierError)` is empty, so the stored error text is `""`.
- `max_parallel=1`: peak 1 and nested enter/exit, on the caller thread.
- ContextVar value is visible because the executor runs inline on the caller thread (ident equals the caller).
- `async def` executor: body did not run; both outputs are `<coroutine object ...>` strings; completed 2 with the unawaited-coroutine warning.
- Exception identity and the blocked-dict / default-adapter result match the green guard (same exception object, same step, same dict object, `BLOCKED` with and without `outcome_status`).

[executed] Parallel-only scope on the committed file: one `await asyncio.to_thread(` call, inside the `len(batch) != 1` branch. The `len(batch) == 1` branch contains neither `to_thread` nor `iscoroutinefunction`.

## Registered debt (same on parent and HEAD, out of scope)

These are the pre-approved boundaries. Red and green observations match. This gate did not treat them as new defects and did not change code.

- Serial one-step `async def`: the body does not run. `mark_completed` sets `completed` and then `output[:200]` raises `TypeError: 'coroutine' object is not subscriptable`. The public dict is completed 1 / failed 1, output None, that error, plus the unawaited-coroutine warning. The synchronous one-step contract is unchanged.
- Async callable object (`async def __call__`): `inspect.iscoroutinefunction` is false. A parallel batch stores the coroutine repr as a successful string. The body does not run.
- Sync executor returning a custom awaitable: `__await__` is not called. The parallel success path stringifies the object and counts the step completed.
- Nested `execute_all` from a running loop: `RuntimeError: Cannot run the event loop while another loop is running`. The loop setup in this commit is the previous setup.

## Windows boundary

This host is Darwin. **No native Windows proof.** Windows native CI remains pending for final CI. Docker Desktop on a Windows host with Linux containers is unverified here.

## Verdict

**APPROVE** `e0b83a05037bb99b4157d453f59ea3e66a603a5d`  
**APPROVE** patch SHA256 `759baff7b4fad44b9e92af0694104571f43b336a06e50fdd2f2d81a7b53f1d38`

No P0/P1/P2. The parallel dispatch is real on this commit and absent on the parent blob. Semaphore limits, context propagation, coroutine-function await, exception identity, and the raw blocked dict plus default adapter all held under this gate's own probe. The 834-test broad suite passed on this archive. Serial async, async callable objects, custom awaitables, and the nested-loop entry stay registered debt.
