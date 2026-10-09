# W1 Kimi FINAL Pre-Commit Qualification Report (after-B5)

- **Verdict**: **APPROVE**
- **Reviewer lane**: Kimi Code CLI (lead, read-only)
- **Date**: 2026-10-09
- **Snapshot**: `/private/tmp/vibesop-opt-20261009/snapshots/W1-final-after-B5` (HEAD = parent, uncommitted)
- **Parent**: `e0b83a05037bb99b4157d453f59ea3e66a603a5d` ✓ (`git rev-parse HEAD` measured)

> This verdict is bound to the **new** patch identity below, re-derived and re-run by this lane. Nothing is carried over automatically from the earlier approval (`7454ac8f…`, parent `beda9953…`).

## 1. Patch identity — measured, not asserted

| Check | Result |
|---|---|
| `git diff <parent>` over the 8 whitelisted paths | **23685 bytes**, SHA256 **`60813ebd5d2e08db36329a2fbf4771527ab2c4372a0e949d98682686185a33d5`** ✓ (raw copy: `/tmp/w1-final-candidate.diff`) |
| `W1-frozen.json` (17:03) `patch_sha256` / `patch_bytes` | identical ✓ |
| 8/8 `source_sha256` (incl. `tests/installer/test_skill_installer.py`, unchanged by the diff) | measured, all match frozen ✓ |
| vs `patches/history/W1-approved-before-B5-7454ac8f.diff` (23783 B) | the two patches differ **only** in CHANGELOG context lines (new parent carries pending B5/B6 entries where the old parent carried B8/B2) plus a git index line. **All 7 code/test/workflow files byte-identical** to the previously approved state — only parent/CHANGELOG context moved. |

## 2. Own evidence (all re-executed this lane, raw log `W1-kimi-final-after-B5/logs/kimi-final-runs.log`)

Toolchain: `uv run --extra dev --frozen python -m pytest` → python 3.12.13, pytest 9.1.1, pluggy 1.6.0, cwd = snapshot. Forced-False lane used **this lane's own** external probe `/tmp/vibesop-opt-20261009/W1-kimi-final-after-B5/w1kimi_final_force_false_valid.py` (unique namespace, valid `pytest_configure(config)` hookspec signature, loaded via `PYTHONPATH`+`-p` only; never inside the repo). No source/test/policy change; production probe patched only in-memory for the run.

| Run | Target | Result | Exit |
|---|---|---|---|
| A0 ambient | 5 files (4 adapters + installer) | **171 passed, 0 skipped** | 0 |
| A1 forced-False (own plugin) | same 5 files | **152 passed, 19 skipped** | 0 |
| A2 forced-False | 17 archived caseids (`051b9564…`, byte-identical to corrective copy) | **1 passed, 16 skipped** — the pass is `test_real_dir_write_with_anchor_still_works` (decoupled from `symlink_supported`, runs unconditionally) | 0 |
| A3 forced-False, `-v` | 4 new fallback caseids | **4/4 PASSED** (per-nodeid PASS lines captured: test_base, claude_code, kimi_cli, pi) | 0 |
| A4 negative control | 17 caseids with the **frozen invalid** historical plugin bytes (`816d3519…`, `pytest_configure(_config)`) | `pluggy PluginValidationError` at registration, **0 tests run** | **1** |

**19-skip decomposition (A1), verified line-by-line against the archived 17-caseid list:** 16 = the B1-classified inherently-symlink cases (test_base 6 / claude_code 3 / kimi_cli 3 / pi 3 / installer 1 — exactly the 16 skips of A2) + 3 pre-existing `symlink_supported`-gated tests outside the 17 (test_base:450, claude_code:406, kimi_cli:463). This confirms the GLM corrective's explanation of the 152+19 vs projected 155+16 deviation; the projection had simply not counted the 3 legacy gates. 171 − 19 = 152 ✓.

**17-caseid linkage:** all 17 archived nodeids exist, resolve to the claimed test functions, and split into 16 capability-gated skips + 1 unconditional pass under forced-False — no fake link, no copy passing as a malicious-symlink refusal. 4 new fallback nodeids match the patch's new tests exactly.

**A4 significance:** the preserved original plugin bytes are proven non-runnable (0 tests). The corrective's treatment — keep them only as a labeled negative control, re-establish results via a valid unique external probe — is correct, and this lane did **not** approve the invalid historical artifact as evidence; every number above comes from runs executed now.

## 3. Scope audit (full patch read, plus parent comparison)

- **ci.yml**: both Windows pytest commands are the parent's verbatim commands with only ` -ra --junitxml=test-results-windows-{boundary,full}-py${{ matrix.python-version }}.xml` appended — marker filter, `--reruns 2 --reruns-delay 1`, and all other gates untouched (parent lines 221/237 compared). Two new upload steps: `if: always()`, no continue-on-error, artifact names unique per matrix lane, pinned `actions/upload-artifact@ea165f8d…` (v4.6.2) — the same SHA as the workflow's pre-existing upload step (census 1→3, no new pin). Uploads gate nothing.
- **quickstart-e2e.yml**: one observation step inserted between spaced-home and the injection probe; prints only `bash --version` first line and LF/CRLF/bare-CR/byte counts; no `cat`/content printing, no `secrets.` references (only the comment "never secrets"), env limited to HOME/USERPROFILE/SPACED_HOME, every command `|| true`. Surrounding parent steps byte-unchanged.
- **Tests**: real-dir write test decoupled and unconditional; Windows execute-bit dual-branch asserts a real non-empty file (no ACL masquerade); 4 new copy-fallback tests exercise the real product fallback and assert real-dir-not-link, `.vibe-copy-source`/`.vibe-manifest.json` markers, central/user content untouched, flattened namespace boundary, idempotence, and output side effects. capability=False lane honestly does not stand in for the malicious-symlink refusals.
- **CHANGELOG**: single isolated W1 entry at the top of Changed; no other entries touched.
- **Gates re-run this lane**: `scripts/check_ci_decision_source.py` → 10 jobs / 10 entries, all deterministic|human, exit 0. `ruff check` on the 4 modified test files → clean.
- No secrets in the diff; no coverage/filter/rerun/pin changes.

## 4. Integrity

- sha256 of all 8 in-scope files identical before and after every run (log § BEFORE/AFTER).
- No repo file written (pytest touched only gitignored caches); no commit/push; no Docker/provider/API calls; probe and logs live only in this lane's namespace `/tmp/vibesop-opt-20261009/W1-kimi-final-after-B5/` plus this report.

## 5. Honest boundaries (unchanged; do not read as completed)

1. **Native Windows CI still pending** — the 3 Windows jobs (boundary+full × py3.12/3.13, quickstart Windows) have not run on real Windows; per-testid `-ra`/JUnit evidence and Git Bash LF/CRLF byte counts await that run (W-RISK-2).
2. forced-False remains a **darwin branch simulation** of the unprivileged-Windows probe, not Windows proof.
3. The **16 required malicious-symlink assertions remain Windows-UNVERIFIED**; if native Windows lacks symlink privilege they will legitimately skip and must never be counted as PASS.
4. Baseline per-testid comparison remains **unavailable** (baseline logs 0 bytes) — single-side new-run verification only.
5. Metadata only: `W1-copyback-receipt.json` `changed_paths` omits CHANGELOG.md (known P2-1); `W1-frozen.json` is authoritative and matches measured bytes. Cosmetic, no source effect.

**Kimi final pre-commit qualification: APPROVE** — object: parent `e0b83a05037bb99b4157d453f59ea3e66a603a5d` + patch SHA256 `60813ebd5d2e08db36329a2fbf4771527ab2c4372a0e949d98682686185a33d5` (23685 bytes, re-derived and hash-verified this lane), 8/8 frozen source hashes measured, 171 ambient / 152+19 forced-False / 1+16 caseids / 4+0 fallback / invalid-plugin R0 = all personally reproduced.
