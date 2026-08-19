# Gate 10 — Dual Review: eval-set relabeling + harness no-match semantics

Review the UNCOMMITTED changeset in `/Users/huchen/Projects/vibesop-py`: code diff at `.omx/artifacts/gate10.diff`, context (yaml headers, stats) at `.omx/artifacts/gate10-context.txt`. Full audit that drove it: `.omx/artifacts/tier3-eval-label-audit.md`. The relabeled dataset is `tests/benchmark/routing_eval_extended.yaml` (130 → 106 scored entries); moved-out entries are in the new `tests/benchmark/routing_eval_retention.yaml` (23 entries, retain_until 2026-09-19, not scored). Read-only review; do NOT modify files. You may run the harness (`uv run python scripts/eval_routing.py --file tests/benchmark/routing_eval_extended.yaml`) — it's slow (~minutes, loads embedding model); prefer reading unless you need evidence.

## What changed

1. **Relabeling**: external/unresolvable skill ids (mattpocock/* etc.) removed; only canonical repo-resolvable ids remain as positives (8 entries: ddo ×2, session-end ×2, superpowers ×3, omx/git-master ×1). Everything else scored is `expect: []`. riper-workflow over-labels removed per the skill's own ONLY-when-explicit contract. L464 garbage label fixed, L404/L671 deduped, ids canonicalized.
2. **Retention pool**: 13 LOW-VALUE + 10 agent-to-agent prompts moved to routing_eval_retention.yaml with purpose/retain_until/purge header. Not scored.
3. **Harness**: `scripts/eval_routing.py` — empty `expect` + empty `reject` is now a REAL no-match assertion (passes iff `not result.has_match`, where fallback-llm counts as no-match); added `--file` flag; docstring updated.
4. **Calibration**: `scripts/calibrate_index_threshold.py` now consumes audited labels; conclusion was "8 confirmed positives too thin to recalibrate", so `index_match_threshold` default stays 0.20 with an updated comment in `src/vibesop/core/config/manager.py`.
5. Deviation highlights from the audit: L132 `commit 三批改动` labeled `omx/git-master` (judgment call — router's actual match, semantically right); L161/L267/L444 kept as superpowers positives (pack installed in this env).

## Measured results (BS-check these)

- New baseline on cleaned set: top-1 55/106 = 51.9%, recall@3 53.8% (was fake 19.2%/26.2%).
- 51 residual "errors" are now honest router issues (over-triggers: riper scenario on generic workflow requests, session-end on 「帮我先关闭了」, ddo keyword on status questions) + ~15 environment-dependent matches to locally-installed packs.
- Oneshot set unchanged at 10/11. `tests/benchmark` + config tests: 48 passed.

## Your task

1. **No-match assertion semantics**: read the new logic in eval_routing.py. Is `not has_match` the right pass condition? Check what `has_match` actually means in `SkillRoute`/router result — does fallback-llm set has_match True or False? Is there a gap where a junk low-confidence REAL skill match passes the assertion?
2. **Relabeling fidelity**: sample-check ~10 entries against the audit's section C — did the coder follow it? Are the 8 remaining positive labels defensible (read the target skills' SKILL.md triggers in `core/skills/` and installed packs)? Challenge L132→omx/git-master and the superpowers keeps.
3. **Retention file**: is it genuinely excluded from all harness paths (grep for anything that globs tests/benchmark/*.yaml — would retention.yaml get swept into a scorer or test)? Is the header's purge process clear?
4. **Calibration**: is "too thin, keep 0.20" the honest call given the data? Check the precision numbers cited (0.455 @ 0.05 vs 0.750 @ 0.20) if reproducible cheaply.
5. **Environment dependence**: eval outcome now depends on locally-installed packs (~/.vibe). Is that documented? Should it block merge? (Opinion, not necessarily a fix request.)
6. Regression check: does the main default set (routing_eval.yaml, 79.4%) still behave sanely under the new no-match semantics?

Verdict format (exactly):
```
VERDICT: PASS | PASS_WITH_NITS | BLOCK
BLOCKS:
- [severity] file:line — issue — why
NITS:
- file:line — issue
NOTES:
- ...
```
