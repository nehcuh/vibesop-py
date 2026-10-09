# B4 Kimi Closure Report — Final Batch Closure (read-only)

- **Batch**: B4 — `fix(installer): publish isolated sandbox builds and preserve overlay policy`
- **HEAD**: `3305bcc9aff72320db57e99e04f58c80cec6b62f` (verified `git rev-parse HEAD`)
- **Parent**: `beda9953c981336f6e2da1989307da0e94490c56` (verified `git rev-parse HEAD^`)
- **Patch**: `git diff HEAD^ HEAD` = **70772 bytes, SHA256 `1dd4a88029e4600e0e42f66bca0aff7abc2a17a7fe2b999bab7c999b4af77429`** (recomputed independently this session; matches the canonical value)
- **Verdict**: **BATCH_CLOSE_APPROVE**
- **Date**: 2026-10-09

All checks below are read-only; the only write is this report file. No source/tests/CHANGELOG/receipts/auth/global-state/Docker/API/commit/push mutations were made.

## 1. Patch / frozen / commit receipt binding (all independently recomputed)

| Claim | Proof (this session) |
|---|---|
| Canonical patch SHA256 `1dd4a880…7429`, 70772 bytes | `git diff HEAD^ HEAD` recomputed: exact match; equals `patch_sha256`/`patch_bytes` in `B4-frozen.json`, `B4-post-frozen.json`, `B4-commit-receipt.json` |
| Frozen source bytes = committed bytes | All 8 `source_sha256` entries in `B4-post-frozen.json` recomputed via `git show HEAD:<path>`: **all match** |
| Commit receipt | `B4-commit-receipt.json` `commit` field == `git rev-parse HEAD`; `committed_paths` ⊆ frozen paths |
| Untracked clean at freeze | `git status --porcelain` shows no modified tracked files (only unrelated untracked diagnosis docs) |

Note: `src/vibesop/builder/manifest.py` is in the frozen path set but is not in the diff — the commit touches 7 files; frozen source hash for `manifest.py` still matches HEAD (unchanged), consistent.

## 2. Named pre-reports — verdicts and evidence verified

| Report | Verdict | Key claims verified |
|---|---|---|
| `B4-kimi-final-context-report.md` | **APPROVE** | 82 passed/1 skipped (raw `B4-kimi-final-context-tests-stdout.txt` matches); isolated probe (raw probe stdout shows scoped HOME, isolated locks dir); conditions R1/R4 closed |
| `B4-glm-final-context-report.md` | **APPROVE** (blocking lane, actual run) | Raw raws `-00-reconcile` ALL PASSED, `-01-tests` 82/1, `-02-probe` 39/39 checks with global lock dir untouched, `-03-ruff` exists |
| `B4-final-context-target-container` | fresh container run | `logs/B4-final-context-target-container.log.result.json`: exit_code 0, `patch_sha256` = canonical `1dd4a880…`, image `vibesop-opt-depcache:20261009`; log tail: `82 passed, 1 skipped in 1.86s`. The 1 skip = opt-in Docker-guard test (`tests/installer/test_pack_install_order.py:894`), not counted as pass |
| `B4-windows-source-real-docker` | actual real-Docker run | `B4-windows-source-real-docker-receipt.json`: exit_code 0, `1 passed in 0.79s`; source binding `pack_installer.py` = `72551cbd…` ("pack725"), `test_pack_install_order.py` = `d18e3c58…` ("testd18") — both match frozen `source_sha256` exactly; log exists and matches; `native_windows: false` honestly recorded |
| `B4-grok-post-report.md` | **APPROVE** (independent) | Own actual producer: saved `subprocess.run([sys.executable, grok_b4_post_producer.py, …])` executed (no fabricated CompletedProcess; required-fail used real exit 7); public guards `reject_root_home_live`, `reject_socket_mount`, `reject_socket_argv`, `reject_host_root_argv`, `child_was_real_python` all PASS in `probes-grok-b4-post/probe-stdout.txt`; all 10 cited raw files exist; pytest.txt: 82 passed, 1 skipped |

## 3. Low findings register — consistent across all three lanes

- **F1 (Low)**: `_index_pack_tree` (`src/vibesop/installer/pack_installer.py:1018-1042`) buffers whole file bytes via `path.read_bytes()`, no size cap, held twice (before/after snapshots). Registered by GLM §6, Grok line 98, Kimi §8 (worded "内存索引无上限" — same finding, label drift only).
- **F2 (Low)**: first-colon vs last-colon asymmetry on the `:/work:rw` volume split (`_assert_container_command_safe`, pack_installer.py:1001-1016) vs fixture `rsplit`; pathological input **fails closed** via `_reject_unsafe_build_mount` (pack_installer.py:984-999). My own diff review confirms the production parse fails closed and containment checks are prefix-collision resistant.
- **F3 (Low)**: BUILD-skip notices remain success-with-notice. **Pre-existing**: identical strings present at `HEAD^` (`git show HEAD^:src/vibesop/installer/pack_installer.py` lines ~405/415/420), not a B4 regression.
- **No new blocking findings**: all three reports state no P0/P1/P2; my own read of the full 1688-line diff found no blocking issue (subprocess path is argv-list only, no shell=True, 60s timeouts, self-validating container argv, atomic verified persistence, fail-closed cleanup).

## 4. Probe isolation and lock hygiene

- **HOME / PackLockStore isolation**: all three lanes set HOME to a scoped temp **before** any vibesop import and monkeypatch `PackLockStore.LOCKS_DIR` to an isolated dir; raw transcripts (`B4-kimi-final-context-probe-stdout.txt`, `B4-glm-final-context-raw-02-probe.txt`, `probes-grok-b4-post/probe-stdout.txt` + `locks-before/after.json`) corroborate. Repo-side, the patch adds layered autouse isolation: `tests/installer/conftest.py:12-16` (`_isolate_pack_locks`) and `tests/conftest.py:253-279` (`_isolated_home` + `_redirect_frozen_home_paths`).
- **Historical locks**: user-global `~/.config/skills/.pack-locks` before/after = only `ui-ux-pro-max-skill.json` (317 bytes, mtime Jul 24, SHA `69da52eb…`). The two historical Kimi probe-mistake locks (`template-pack`, `pack-copy` — named in `B4-kimi-windows-pre-report.md:63`) were already deleted; all three final reports confirm they did not reappear and the original user lock is intact. No false history rewrite; the patch itself removes no locks (it only defers lock write until after build success).
- The patch-side check confirms: no lock-entry deletion, no migration code.

## 5. Windows boundary — no overclaim

All three reports and the real-Docker receipt state: host is Darwin, `native_windows: false`; Docker Desktop on a Windows host + Linux containers = **unverified, not unsupported**; no native-Windows verification is claimed anywhere; final proof routes to pending Windows CI. Consistent with `windows-baseline-*` CI evidence files present in the batch directory.

## 6. Full integration candidate 1 (frozen)

- `integration-candidate1-validation-summary.json`: **7829 passed, 26 skipped, 20 deselected, coverage 80.95%, types "0 errors, 0 warnings, 0 notes"**; `logs/integration-candidate1-color-fixed-container.log` tail confirms the real run (`7829 passed, 26 skipped… PYTEST_RETURN {'exit_code': 0}`), 594-line log on disk.
- `integration-candidate1-host-result.json` (Darwin): **7839 passed, 16 skipped**, exit_code 0.
- **Source bytes include B4**: all 8 B4 frozen `source_sha256` entries match `integration-candidate1-frozen.json` for the 7 code/test paths; only `CHANGELOG.md` differs — by design, since the integration changelog accumulates sibling-batch entries (B4 frozen itself notes "active changelog contains pending B2 changes"). Not a drift.

## 7. Non-blocking evidentiary imprecisions (registered for traceability, do not affect closure)

1. Grok report says "81/81 PASS"; its own raw trailer says `ALL_CHECKS_PASSED 84` (81 PASS lines in the transcript). Count-label inconsistency only.
2. Kimi report says probe "22/22 通过"; raw transcript shows 21 PASS lines. Off-by-one label only.
3. GLM report says diff is "1642 lines"; actual `git diff HEAD^ HEAD` = **1688 lines** (Kimi and Grok both state 1688 correctly). Cosmetic error in a "read in full" claim; the SHA it approved is the correct canonical one.

None of these touches a substantive claim (verdicts, hashes, isolation, locks, test counts all verified against raw evidence above).

## 8. Scope discipline

Read-only audit: no mutations to source, tests, CHANGELOG, receipts, auth config, global state, Docker objects, API resources; no commit/push. Sole artifact: this report.

---

**BATCH_CLOSE_APPROVE** — all frozen bindings, receipt claims, report verdicts, Low-finding registers, isolation/lock-hygiene evidence, and integration numbers verify against independently recomputed hashes and on-disk raw logs. Remaining action outside this batch: pending native Windows CI, correctly tracked as pending (not unsupported).
