# W1 EVIDENCE CORRECTIVE — forced-False reproducibility defect found, explained, and repaired

- **Status**: **DEV_EVIDENCE_COMPLETE**
- **Executor lane**: Claude Code CLI agent powered by **GLM-5.3** (same lane that authored the original W1 DEV run; see §7 of the original report)
- **Date**: 2026-10-09
- **Clone**: `/private/tmp/vibesop-opt-20261009/snapshots/W1-glm-dev`, HEAD `d9d7804ffd1dfb92f6a82138e5a07f5304a11df0` (unchanged)
- **Scope**: narrow evidence corrective only, per `prompts/W1-glm-evidence-corrective.txt`

## 0. Supersession statement (exact)

This document **supersedes the reproducibility evidence for the forced-capability-False lanes** of `W1-glm-dev-complete.md`:

- Superseded: **§6** of the original report (the embedded "Forced-False scratch plugin" with `pytest_configure(_config)` and its `-p` load instruction) — those archived bytes **cannot load** under pytest 9.1.1 / pluggy 1.6.0 (registration-time `PluginValidationError`; parent and this lane both reproduced, §2). Anyone following §6 as written gets zero tests run.
- Superseded: the implicit claim of §5's two forced-False rows ("1 passed, 16 skipped", "4 passed") that they are reproducible via the §6 artifact. They are reproducible — but only via the **valid unique external probe** introduced here (§3), which re-establishes both results with full raw stdout/stderr, exit codes, and nodeids (§4).
- **Not rewritten, not retracted**: the original report file, its counts, its history, the six frozen product/test/workflow files, CHANGELOG, patch, and all receipts. The original counts are *re-established*, not altered (see §1: the runs genuinely happened, with a plugin whose signature was valid at run time).

## 1. Factual run order — what actually happened (from the original session log, no invention)

All facts below are extracted from the original session's own JSONL log, `/tmp/vibesop-opt-20261009/logs/W1-glm-dev.jsonl` (line numbers cited; timestamps UTC as recorded by the harness):

1. **2026-10-09T07:16:36.810Z** (log lines 264–265): `w1glm_force_capability_false.py` was **written** at the clone root with the hook signature `def pytest_configure(config):` — **valid**. (The Write call's full content, including the valid signature, is embedded verbatim in the log.)
2. **Run A** (line 268, result line 269): `uv run --extra dev --frozen python -m pytest -q -ra -p w1glm_force_capability_false @w1glm_b1_caseids.txt 2>&1 | tail -24` → **"1 passed, 16 skipped in 0.24s"**, skip reason "directory symlinks not supported on this host". Executed while the file still had the valid `(config)` signature.
3. **Run B** (line 272, result line 273, ts 07:17:06.562Z): `uv run --extra dev --frozen python -m pytest -q -ra -p w1glm_force_capability_false "tests/adapters/test_base.py::TestRenderCopyFallbackWithoutSymlinkCapability" "tests/adapters/test_claude_code.py::TestSkillCopyFallbackWithoutSymlinkCapability" "tests/adapters/test_kimi_cli.py::TestKimiSkillRenderBoundary::test_copy_fallback_real_dir_and_central_untouched" "tests/adapters/test_pi_coding_agent.py::TestRenderCopyFallbackWithoutSymlinkCapability" 2>&1 | tail -6` → **"4 passed in 0.18s"**. Same valid-signature file.
4. 07:17:11.742Z / 07:17:27.862Z (lines 276–281): `rm` of the two scratch files **denied twice**; cross-directory `mv` also blocked (line 284). The scratch plugin therefore had to *remain inside the repo*.
5. **07:20:04.305Z** (line 327): `ruff check .` failed with exactly one error: `ARG001 Unused function argument: 'config'` at `w1glm_force_capability_false.py:13:22`, quoting the on-disk body `def pytest_configure(config):` — independent proof the file **still had the valid signature at this moment**, i.e. after both runs.
6. 07:20:20.371Z (line 331): `git clean -f -- w1glm_force_capability_false.py w1glm_b1_caseids.txt` — approval required, **not executed**.
7. **07:20:37.810Z** (lines 334–335): the plugin was **rewritten**. The log's own recorded diff shows the one-line signature change `-def pytest_configure(config):` → `+def pytest_configure(_config):` (plus a docstring expansion). Motive, from the session's recorded reasoning: with deletion blocked and `ruff check .` having to pass over the repo, the unused-argument name was underscored — the standard ruff ARG001 idiom. This edit is what made the hookimpl **invalid**: pluggy validates hookimpl argument names against the `pytest_configure(config)` hookspec and rejects `_config`.
8. After 07:20:37Z there is **no further `-p w1glm_force_capability_false` invocation anywhere in the log** — the only two `-p` usages are runs A and B above. The DEV report §6 then embedded the **post-rewrite** (`_config`) bytes, and those are the bytes that got frozen (`reports/W1-author-w1glm_force_capability_false.py.txt`, sha256 `816d3519…`).

**Conclusion (evidenced, not inferred):** the reported forced-False results were produced by the pre-rewrite plugin with the valid `(config)` signature; the archived/frozen bytes are a post-run lint-motivated rewrite that never executed a single test. The defect is archival validity (wrong bytes preserved, valid bytes never archived), not fabricated counts. The pre-rewrite bytes that actually ran are recoverable from the session log (lines 264/265) and are functionally preserved by the corrective probe in §3.

## 2. Independent confirmations that the frozen bytes cannot run

| Reproduction | By | Artifact |
|---|---|---|
| Exact archived bytes → `pluggy._manager.PluginValidationError: … pytest_configure(_config) … Argument(s) {'_config'} are declared in the hookimpl but can not be found in the hookspec` at plugin registration | Parent (stdin-registration variant) | `/tmp/vibesop-opt-20261009/W1-original-forced-plugin-validation.log` |
| Same bytes, copied byte-identically (sha256 `816d3519…`) into the corrective namespace, loaded via `-p` under the clone's own locked toolchain → identical `PluginValidationError`, **exit code 1, zero tests collected/run** | This lane (R0, negative control) | `W1-glm-evidence-corrective/logs/R0-invalid-frozen-control.log` |

Both raw logs are preserved; the frozen invalid bytes and archived artifacts were **not modified** (sha256 re-verified after all runs).

## 3. Corrective probe — unique, valid, external

File: `/tmp/vibesop-opt-20261009/W1-glm-evidence-corrective/w1glm_corrective_force_false_valid.py`
sha256: `8f020d4cf500936595d7f28686049c644c0f71b2a0602c5314e1559b09e78fd7` (1519 bytes)

```python
"""W1 evidence-corrective probe plugin (VALID hookimpl, unique external probe).

… (full provenance docstring in the file: background, archived-bytes history,
external-load-only contract) …
"""

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    del config  # ruff ARG001: signature must match the hookspec exactly
    import vibesop.utils.symlinks as _symlinks

    _symlinks.can_create_dir_symlink = lambda _directory: False
```

Properties:
- **Valid hookimpl**: signature `pytest_configure(config)` matches the hookspec; `del config` keeps ruff ARG001 quiet **without** renaming the argument — the exact trap that produced the frozen invalid bytes.
- **Same control as the original runs**: patches the **production** probe `vibesop.utils.symlinks.can_create_dir_symlink` (module actually imported by the tests; editable venv resolves to this clone's `src/vibesop/utils/symlinks.py`) to return `False`; `tryfirst=True`; same lambda semantics as the pre-rewrite plugin embedded in the session log.
- **Unique and external**: new module name, new namespace dir; never placed inside any clone, never collected, never committed; loaded only via explicit `-p w1glm_corrective_force_false_valid` with `PYTHONPATH=/tmp/vibesop-opt-20261009/W1-glm-evidence-corrective` (actual external import).
- The byte-exact frozen copy `w1glm_invalid_frozen_copy.py` (sha256 `816d3519…`) exists in the same namespace **only** as the R0 negative-control input; it is clearly named and never used as a probe.

## 4. Corrective re-runs on the actual current W1 source clone (all re-executed, nothing asserted from old data)

Toolchain: `uv run --extra dev --frozen python -m pytest` → python 3.12.13, pytest 9.1.1, pluggy 1.6.0; cwd = the clone; plugin imported externally via `PYTHONPATH` + `-p`. Full raw stdout/stderr, exit codes, commands, and UTC timestamps saved under `/tmp/vibesop-opt-20261009/W1-glm-evidence-corrective/logs/`.

| Run | Target | Result | Exit | Raw log |
|---|---|---|---|---|
| R0 (control) | 17 caseids, **invalid frozen bytes** via `-p` | `PluginValidationError` at registration, **0 tests run** | **1** | `logs/R0-invalid-frozen-control.log` |
| R1 | **five full target files** (`test_base`, `test_claude_code`, `test_kimi_cli`, `test_pi_coding_agent`, `tests/installer/test_skill_installer.py`) + valid probe | **152 passed, 19 skipped (171 total)** | **0** | `logs/R1-five-files-forced-false.log` |
| C1 | same five files, `--collect-only -q` | **171 tests collected** (exact nodeid list saved) | **0** | `logs/C1-five-files-collect-only.log` |
| R2 | **17 original exact nodeids** (byte-identical archived list, sha256 `051b9564…`) + valid probe | **1 passed, 16 skipped** — pass = `test_real_dir_write_with_anchor_still_works`; the 16 skips are exactly the §5 skip set, same reason string | **0** | `logs/R2-caseids17-forced-false.log` |
| R3 | **four new fallback caseids** + valid probe | **4 passed** (all four §4-of-original nodeids, per-nodeid PASS lines captured) | **0** | `logs/R3-fallback4-forced-false.log` |

**R1 deviation from the predicted "155 passed + 16 skipped", explained:** total 171 matches, but actual is **152 + 19**. The corrective prompt's 155+16 extrapolated the B1 17-caseid classification to the whole five-file set; the files additionally contain **three pre-existing `symlink_supported`-gated tests outside the 17-caseid set**, which legitimately skip once the production probe is forced False:

- `tests/adapters/test_base.py::TestPlatformAdapterEdgeCases::test_clean_orphan_skills_symlink` (skip at :450)
- `tests/adapters/test_claude_code.py::TestSkillContentRender::test_symlink_preserved_on_second_build` (skip at :406)
- `tests/adapters/test_kimi_cli.py::TestKimiCLISkillContentRender::test_symlink_preserved_on_second_build` (skip at :463)

16 (B1-classified) + 3 (pre-existing gates) = 19 skips, 171 − 19 = 152 passed. These three tests pass under ambient capability=True (they are inside the original 171-pass ambient run) and were never part of the B1 forced-False claim; the old report never ran a five-file forced-False lane, so no old count contradicts this. Recorded as-found; this is precisely why the corrective re-executes instead of asserting.

Honest recording note: the original runs A/B piped through `tail` and recorded no exit codes; the corrective runs record true exit codes (EXIT_CODE lines in every log).

## 5. Integrity — before/after identical

- Six whitelist files + audited `tests/installer/test_skill_installer.py`: sha256 **identical before and after** all runs, and equal to the `W1-frozen.json` / original §1 baselines (values in `logs/env-versions-and-sha-integrity.log`).
- HEAD `d9d7804f…` unchanged; `git status` unchanged (only the six pre-existing modifications + pre-existing untracked user docs); **no file added inside the clone** (pytest wrote only to gitignored caches).
- Frozen/archived artifacts untouched, sha256 re-verified post-run: plugin `.txt` `816d3519…`, caseids `.txt` `051b9564…`; parent raw log `W1-original-forced-plugin-validation.log` untouched; `W1-owned-scratch-cleanup-receipt.json`, `W1-copyback-receipt.json`, `W1-frozen.json`, old `W1-glm-dev-complete.md` untouched.
- All new files live only in the unique namespace `/tmp/vibesop-opt-20261009/W1-glm-evidence-corrective/` (4 inputs + 6 logs) plus this report file.

## 6. Constraints respected

No production/test/workflow/doc/auth changes; no CHANGELOG edit; no commit, push, PR, CI trigger, provider/API/model call, Docker, or subagent use; no global-home writes; no modification of the six frozen files, the frozen patch, receipts, the Kimi review inputs, or the old DEV report; original counts and history not rewritten.

## 7. Honest boundaries (unchanged by this corrective)

1. Everything still ran on darwin; forced-False remains a **branch simulation** of the unprivileged-Windows probe, not Windows proof.
2. The 16 inherently-symlink cases remain **required, Windows-unverified** — skips under forced False are the expected legitimate outcome, never counted as pass.
3. This corrective repairs **reproducibility evidence only**; it does not add coverage, does not touch the pending native-Windows items (§8 of the original report), and does not upgrade the lane-identity scope of §7 there.

**For Kimi review (pre-close read):** the §1 timeline is fully sourced from `logs/W1-glm-dev.jsonl` line references; the §4 table is fully sourced from the saved raw logs; the only deviation from the corrective prompt's expectations (R1: 152+19 vs 155+16) is explained with nodeid-level evidence and does not touch any frozen artifact or original claim.
