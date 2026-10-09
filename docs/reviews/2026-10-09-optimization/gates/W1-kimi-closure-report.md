# W1 Kimi Lead Final Batch Closure Report

- **Verdict**: **BATCH_CLOSE_APPROVE**
- **Lane**: Kimi Code CLI (lead, final closure, strict read-only)
- **Date**: 2026-10-09
- **Snapshot**: `/private/tmp/vibesop-opt-20261009/snapshots/W1-grok-post`
- **Commit**: `bb0d1147e95019fb3550df76a3fbfe85fd0d4124`
- **Parent**: `e0b83a05037bb99b4157d453f59ea3e66a603a5d`
- **Canonical patch**: `git diff HEAD^ HEAD` = **23685 bytes**, SHA256 **`60813ebd5d2e08db36329a2fbf4771527ab2c4372a0e949d98682686185a33d5`**

Everything below was **personally re-measured in this lane** from raw artifacts. Prior lane numbers are cited only where this lane opened the raw logs/receipts and confirmed them.

## 1. Chain verification (measured this lane)

| Check | Measured | Claimed | Match |
|---|---|---|---|
| `git rev-parse HEAD` | `bb0d1147e95019fb3550df76a3fbfe85fd0d4124` | same | ✓ |
| `git rev-parse HEAD^` | `e0b83a05037bb99b4157d453f59ea3e66a603a5d` | same | ✓ |
| `git diff HEAD^ HEAD` bytes / SHA256 | 23685 / `60813ebd…a33d5` | same | ✓ |
| Committed paths | 7 (2 workflows, CHANGELOG, 4 test files); **no `src/` path** | same | ✓ |
| 8 frozen source SHA256 at HEAD blobs | all match `W1-frozen.json` / `W1-post-frozen.json` values | same | ✓ |
| `git status` before vs after this review | identical (4 pre-existing untracked diagnosis paths; zero tracked modifications; `git diff HEAD` empty) | unchanged | ✓ |

`W1-frozen.json`, `W1-post-frozen.json`, `W1-commit-receipt.json` agree with each other and with the measured patch identity. Integration receipt `final-source-integration-match-bb0d1147.json`: `head=bb0d1147…`, `changed_source_tests_workflows=[]`, docker **7829 passed / 26 skipped**, host **7839 passed / 16 skipped**, coverage **80.95** — a **prior** receipt, not re-run by this lane or the Grok lane.

## 2. Workflow diff read (full)

- **ci.yml**: both Windows pytest commands are the parent's commands with only ` -ra --junitxml=test-results-windows-{boundary,full}-py${{ matrix.python-version }}.xml` appended. `--reruns 2 --reruns-delay 1` and the marker filter `-m "not benchmark and not slow"` retained verbatim. **No `-rR` anywhere in the workflow** — confirmed by grep; with the default rerun plugin, RERUN lines print only under `-rR`, so the new evidence provides **final per-test-ID status** (via `-ra` + standard JUnit XML), **not per-ID rerun history**. No claim is made that unknown reruns are recoverable; with `--reruns 2`, a flaked-then-passed ID appears as a bare PASS, and the current collector's conservative totals (0 needed for a clean pass) are the honest reading. Two new upload steps: `if: always()`, no `continue-on-error`, unique names per matrix lane, reuses the workflow's existing `actions/upload-artifact@ea165f8d…` pin (census 1→3, no new pin). Uploads gate nothing.
- **quickstart-e2e.yml**: one observation step inserted between spaced-home and the injection probe. Prints only `bash --version` first line and LF/CRLF/bare-CR/byte counts; every command `|| true`; no `cat`/content printing; env limited to HOME/USERPROFILE/SPACED_HOME; the only `secrets` substring is the comment "never secrets." — no `${{ secrets` expression. Surrounding steps byte-unchanged; observation never gates.
- **CHANGELOG.md**: exactly one new W1 bullet at the top of Changed; it explicitly claims evidence collection and copy-fallback qualification **without** claiming symlink or Windows ACL proof. No other entry touched.

## 3. Per-ID status (final, from raw logs — kept, not re-run here)

Toolchain across lanes: python 3.12.13, pytest 9.1.1, pluggy 1.6.0. Three independent lanes (GLM corrective, Kimi after-B5, Grok post-commit) each executed their own valid unique external probe (`pytest_configure(config)` signature, `PYTHONPATH`+`-p` only, never inside the repo) and each preserved the original invalid frozen plugin **only as a labeled negative control**.

**Ambient (no plugin), 5 files (4 adapters + installer): 171 passed, 0 skipped** — confirmed in Grok raw log `A-ambient.txt` and Kimi `kimi-final-runs.log`.

**Forced-False, 5 files: 152 passed, 19 skipped** — confirmed line-by-line in Grok `B-five-forcefalse.txt`: 19 SKIPPED lines = 16 archived-caseid skips + 3 pre-existing `symlink_supported`-gated tests outside the 17 (`test_base.py:450`, `test_claude_code.py:406`, `test_kimi_cli.py:463` — def lines verified in HEAD source). 171 − 19 = 152 ✓. The 3 legacy gates explain the 152+19 vs projected 155+16 deviation; the projection had simply not counted them.

**17 archived case IDs (`051b9564…`, hash re-verified, identical in GLM and Grok namespaces): 1 passed, 16 skipped.**
- PASS: `tests/adapters/test_base.py::TestWriteFileAtomicAncestorSymlink::test_real_dir_write_with_anchor_still_works` — decoupled from `symlink_supported`, def at HEAD line 725 confirmed to take only `tmp_path`; progress line in Grok `C-caseids17.txt` is `sss.sssssssssssss` (4th nodeid passes), matching the archived list order.
- 16 SKIPs: the malicious-symlink refusal cases (test_base 6, claude_code 3, kimi_cli 3, pi 3, installer 1), all with reason "directory symlinks not supported on this host". **These skips are not passes** and must never be counted as such.
- All 17 nodeids resolve to existing test functions at HEAD (per-ID grep, zero missing).

**4 new fallback case IDs: 4/4 PASSED** — per-nodeid PASSED lines in Grok `D-fallback4.txt` match the patch's new tests exactly: `TestRenderCopyFallbackWithoutSymlinkCapability` (base, pi), `TestSkillCopyFallbackWithoutSymlinkCapability` (claude_code), `TestKimiSkillRenderBoundary::test_copy_fallback_real_dir_and_central_untouched` (kimi_cli). None of the 4 is in the 16-skip list.

**Negative control (invalid frozen plugin `816d3519…`, hash re-verified in both namespaces): `pluggy PluginValidationError` at registration, 0 tests run, exit 1** — confirmed in the preserved parent log `W1-original-forced-plugin-validation.log`, GLM `R0` log, Kimi `A4` (exit 1), and Grok `E-invalid-control` (exit 1). The invalid bytes are never used as pass evidence.

**Public IO probe (forced-False): ok=true** — all four adapters + base `_render_skill_content`: real-dir (not link) output, flattened namespace, `.vibe-copy-source` / `.vibe-manifest.json` (`source.type=pack-copy`) markers, central and user content untouched, idempotent second render.

**Gates**: `ruff check` on the 4 modified test files — All checks passed (raw `ruff.txt`). `scripts/check_ci_decision_source.py` — 10 jobs / 10 entries, all deterministic|human, exit 0 (per Kimi/Grok raw runs).

## 4. GLM evidence corrective — adopted and registered with scope honesty

`W1-glm-evidence-corrective-complete.md` preserves the original invalid frozen plugin (`pytest_configure(_config)`) as a **negative control only**: proven non-runnable by two independent reproductions (parent log + GLM R0, both exit 1, 0 tests). The corrective re-established every forced-False result through a valid unique external probe, sourced its timeline from the original session JSONL (valid `(config)` signature at run time; post-run ruff-motivated `_config` rewrite; no `-p` invocation after the rewrite), and **did not rewrite the original report, counts, history, or the six frozen files**. This lane confirms: no retrospective fake PASS anywhere; the six frozen product/test/workflow files plus the audited installer test are byte-identical to frozen hashes; archived artifacts (`816d3519…`, `051b9564…`) unmodified. Existing W1 report wording that could read broadly (e.g. early "reproducible via §6 artifact" implications) is documented as superseded by the corrective — this closure adopts the corrective's narrower, evidenced wording.

## 5. Scope and constraints honored by this closure lane

Strict read-only: no edits to source/tests/workflows/CHANGELOG/receipts/patch; no commit, push, PR, CI trigger; no Docker; no provider/API/model calls; no subagents. Only this report file was written. The Grok lane likewise: probes/temp homes confined to `/tmp/vibesop-opt-20261009/probes-grok-w1-post/`. No Docker Desktop-on-Windows-host claim exists or is made; no Docker executions occurred in the Grok lane or this lane.

## 6. Honest boundaries (registered, not closed)

1. **Native Windows final CI is still pending and is a separate gate.** The 3 Windows jobs (boundary + full × py3.12/3.13) and the quickstart Windows job have not run on real `windows-latest`. Required Windows items awaiting that run: msvcrt behavior, the 17 required case IDs, the 4 copy-fallback tests, 2 Python versions, and the wheel quickstart. **Nothing here is a Windows PASS from Linux/Mac.**
2. forced-False remains a **darwin branch simulation** of the unprivileged-Windows probe, not Windows privilege proof. The ambient 171-pass run proves this host can create directory symlinks; darwin passes do not pass Windows.
3. The **16 malicious-symlink assertions remain Windows-UNVERIFIED**; on a native Windows lane lacking symlink privilege they will legitimately skip and must never be counted as PASS.
4. `-ra` + standard JUnit gives final per-ID status only; **per-ID rerun history is not recoverable** from these reports (no `-rR`), and no unknown-rerun recovery is claimed. Rerun-flake visibility awaits the native Windows run's artifacts.
5. Source-exact integration counts (docker 7829/26, host 7839/16, coverage 80.95) are **prior receipts** matching final `bb0d1147`, not re-run here.
6. Baseline per-testid comparison remains unavailable (baseline logs 0 bytes) — single-side new-run verification only.

## 7. Outstanding (not part of this verdict)

- Final docs index work is still unperformed.
- Actual native Windows CI run is still unperformed (separate gate).

**This closure approves batch W1 at commit `bb0d1147e95019fb3550df76a3fbfe85fd0d4124` (parent `e0b83a05037bb99b4157d453f59ea3e66a603a5d`, patch SHA256 `60813ebd5d2e08db36329a2fbf4771527ab2c4372a0e949d98682686185a33d5`, 23685 bytes) with all findings above registered at face value and all boundaries above carried forward. It does not claim the whole project is done.**
