# Gate 14 Review — M11: Evidence-based keyword/TFIDF scoring

You are reviewing a milestone change to the VibeSOP routing system (repo: /Users/huchen/Projects/vibesop-py). The full diff is appended after these instructions. You may read any file in the repo for context, but DO NOT modify anything.

## What the change does

Problem: the keyword matcher scored by purely additive bonuses (substring +0.25/token cap 0.5, name containment +0.4) with no relation to query coverage or token specificity. Generic tokens ("design", "review", 「复审」) appearing in a pack skill's name/keywords gave 0.82–0.98 confidence on long unrelated queries. 15 of 26 residual eval errors were keyword-layer mis-fires that should have been no-match.

Fix (design: .omx/artifacts/m11-design-a.md, chosen over an aggregation-gate alternative after adversarial reproduction, see .omx/artifacts/m11-design-b.md v2):

1. Corpus-level IDF over the candidate pool (`src/vibesop/core/matching/idf.py`, built in `warm_up`, normalized w(t) ∈ (0,1]).
2. IDF-weighted coverage gating: bonuses scaled by g = min(1, cov/ref).
3. Anchor gate: without a specific anchor (w ≥ 0.78, non-stopword, exact-hit or in name/keywords), score capped at 0.25.
4. Multi-anchor exemption: ≥2 anchors in name/keywords and cov ≥ 0.08 → g = 1.
5. name_bonus guard: single-token generic names (w < 0.7) no longer earn +0.4.
6. partial_bonus is per-query-token-best, not cumulative.
7. TFIDF result-level anchor gate (config-flagged).
8. Un-warmed KeywordMatcher degrades to the legacy formula.
9. New RoutingConfig knobs with calibration notes; unified.py reload_candidates resets matcher warm state.

## Verified results (run by implementer, spot-checked by me)

- base eval 31/34 (was 31/34), oneshot 10/11 (was 10/11), extended 98/107 (was 81/107); per-query diff: 17 error→OK (all become clean fallback abstentions), 0 OK→BAD. Baseline /tmp/m11-baseline.json, after /tmp/m11-after.json, diff doc .omx/artifacts/m11-eval-diff.md.
- Full pytest: 5619 passed / 14 skipped / 0 failed.

## Review focus

1. Correctness of the new scoring math (idf.py, strategies.py `_score_evidence`): edge cases (empty query tokens, missing warm_up, zero-weight denominators, cache invalidation on warm_up, `score()` single-candidate path).
2. The anchor/IDF mechanism: is the stopword list sane? Any way a mis-fire still reaches ≥0.6? Any obvious way a legitimate query gets capped below its old score (the 81 pre-existing extended passes and 31 base passes must survive — they did in eval, but look for structural risks the eval set may not cover)?
3. Backward compatibility: un-warmed fallback to legacy formula; MatcherConfig/RoutingConfig defaults; reload_candidates behavior; TFIDF gate flag.
4. Tests: do the new tests actually pin the five mechanisms? Any mechanism left untested? Do tests avoid eval-set queries (anti-overfit rule)?
5. Config calibration notes: are the claimed calibration intervals consistent with the design doc?
6. Anything in the diff that is out of scope (this milestone must not touch scenario/semantic_index layers).

## Verdict format

End with exactly one of: `VERDICT: PASS`, `VERDICT: PASS_WITH_NITS` (list nits), `VERDICT: BLOCK` (list blocking issues with file:line and reasoning).
