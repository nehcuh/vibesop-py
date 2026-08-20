# Gate 16b Confirmation Review — M12 M0+M1 fix round

Repo: /Users/huchen/Projects/vibesop-py. The appended diff is the FULL current diff vs HEAD (supersedes gate16.diff). Gate16 verdicts: BOTH reviewers BLOCKed on the same flaky test, plus nits. All items addressed. Verify the fixes and check for new issues. DO NOT modify anything.

## gate16 BLOCK (both reviewers, independently) — flaky test

`tests/core/observability/test_clustering.py` `test_cluster_queries_extracts_from_metadata` used `_angle_embedding` derived from built-in `hash()` (PYTHONHASHSEED-randomized) → ~17-20% fresh-process failure. Orchestrator reproduced (2/6 runs failed) and fixed: `_angle_embedding` now derives the angle from `hashlib.sha1` (deterministic across processes). Post-fix: 6 consecutive full-file runs, 28/28 passed each time. VERIFY by running the file a few times yourself.

## Nits fixed

1. claude nit 1 — `_matches_accepted` prefix over-match: prefix fallback now only enabled when the span query is actually at the 200-char truncation cap (genuine truncation), and only in the pend⊒span direction; short queries require exact task_id match. Tests: 2 new cases.
2. claude nit 2 — write-once outcomes: docstring now states it is a deliberate weak signal and M2 must not treat outcomes as ground truth.
3. pi nit — `clear_tool_sequences` now also deletes `tool_sequences.last`; module docstring clarifies purge domain (outcomes/bridge-state/spans belong to observability, not --tool-sequences). Test added.
4. pi nit 2 — CLI spans now excluded from outcome derivation too (`_is_miss` reuses the join's is_cli check), preventing vacuous weak_positive inflation. Test added.

## Design doc update (no code)

`.omx/artifacts/m12-product-design.md` risk section now carries an M2-prerequisite note: fastembed 0.8.0 rejects the un-namespaced default model name (soft-merge never fires — both reviewers reproduced), the one-line fix (`sentence-transformers/` prefix) plus an `embed() is not None` smoke are M2 prerequisites; also folded in: `_extract_step_names` dict-only metadata, min_cluster_size=3 vs 6-key miss pool, spans.jsonl 50MB rotation, purge domain split.

## Not done (by design, honestly reported)

- M1 dogfood activation (hook redeploy to ~/.claude) — after this gate passes.
- Full pytest was re-running at packet time; target 0 failures.

## Verdict format

End with exactly one of: `VERDICT: PASS`, `VERDICT: PASS_WITH_NITS` (list nits), `VERDICT: BLOCK` (file:line + reasoning).
