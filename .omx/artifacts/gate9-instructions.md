# Gate 9 — Dual Review: Tier3 code changes

Review the UNCOMMITTED changeset in `/Users/huchen/Projects/vibesop-py`: diff at `.omx/artifacts/gate9.diff`, new files at `.omx/artifacts/gate9-newfiles.txt`. Read-only; do NOT modify files. You may grep/read anything in the repo.

## Context

Tier3 of the routing overhaul. Three workstreams; the code delta under review is small:

1. **F1 fix** (`src/vibesop/core/observability/gold_detection.py`): `zip(..., strict=True)` in `assess_gold_status` raised ValueError on length-mismatched `cluster.task_ids`/`cluster.queries`, crashing an entire cron-scheduled scan on one malformed cluster. Replaced with WARNING log + min-length truncation, per the repo's "skip bad rows, never take down the batch" convention. `gold_rate` denominator intentionally stays `len(cluster.task_ids)`.
2. **F2 fix** (`src/vibesop/core/observability/skill_promote.py`): `assert cluster.task_keys` runtime guard is stripped under `python -O`, which would allow a zero-step shell candidate to be promoted. Replaced with explicit `if not cluster.task_keys: logger.error(...); continue`.
3. **New eval dataset** `tests/benchmark/routing_eval_oneshot.yaml` (7 entries: 3 positive oneshot-spec queries, 2 junk counterexamples, 2 adjacent must-not-route) backing the newly installed project skill `.vibe/skills/oneshot-web-spec/SKILL.md` (runtime state, not committed). Also tracked: `.vibe/skill-index.json` was updated by the real `vibe skill add` (index v1.4.0, adds oneshot-web-spec) — this file is project-committed state, include a sanity glance.

Measured results (for your BS-detection): oneshot extension set 7/7 top-1 via semantic_index; original 130-entry extended set identical before/after (top1 25/130, recall@3 34/130, zero changed primaries).

## Your task

Adversarial review:
1. F1: is truncation the right policy vs zip_longest? Can the WARNING spam a cron log (once per scan per malformed cluster)? Does the gold_rate denominator choice distort `is_gold` (e.g. all-paired-success but truncated misses failures)? Check `Cluster` construction sites — can task_ids/queries actually diverge in production, or only via hand-built fixtures?
2. F2: with the assert gone, is `continue` correct or should the cluster be marked failed/quarantined? Does anything downstream count on the candidate existing? Check the `python -O` claim holds (no other asserts guarding this path).
3. Tests: do the two new tests genuinely fail under the old code? Is the `python -O` coverage real?
4. Eval yaml: are the `reject:` semantics supported by the eval tooling (grep scripts/eval_routing.py + the mirror driver semantics), or are those entries silently scoring nothing? Are the 3 positive queries actually distinguishable from adjacent negatives by the description written into the installed SKILL.md (read `.vibe/skills/oneshot-web-spec/SKILL.md`)?
5. `.vibe/skill-index.json` committed state: any secrets/PII/absurd entries introduced by the update?

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
