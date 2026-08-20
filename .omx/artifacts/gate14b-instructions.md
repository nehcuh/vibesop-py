# Gate 14b Re-review — M11 fix round (BLOCK-1 + 13 nits)

You are re-reviewing the M11 milestone (repo: /Users/huchen/Projects/vibesop-py) after a fix round. The appended diff is the FULL current diff vs HEAD (supersedes gate14). Gate 14 verdicts were: claude PASS_WITH_NITS (8 nits), pi BLOCK (1 blocker + 5 nits). All items were addressed. Your job: verify the fixes are real and correct, and check the fix round introduced nothing new. DO NOT modify anything.

## What gate14 found and what was done

**BLOCK-1 (pi, independently reproduced by the orchestrator at 0.332 vs grill-me)**: `ANCHOR_STOPWORDS` incomplete — function words rare in the skill corpus (get/make/can/but/will/who/there/should/would/could/because/most/same/some/such, w≥0.78) could anchor. Query `get this working on the new branch before the deadline` scored 0.332 > default floor 0.3 vs mattpocock/grill-me via a description-only `get` anchor.
Fix: stopword set expanded to a self-contained superset (tokenizer DEFAULT_STOP_WORDS ∪ full function-word classes); unit tests pin get/make/because/should/some/there never anchor. Post-fix score claimed 0.25 (< 0.3). VERIFY this yourself: reproduce the query against the real 239-candidate pool with default MatcherConfig, warmed.

**Nits fixed (verify each in the diff)**:
1. find_anchors word-boundary check for Latin tokens ("art" must not anchor "smart"); CJK keeps plain containment; substring_bonus intentionally keeps loose semantics (commented).
2. `" ".join(query_tokens)` set-order fragility — now sorted join in BOTH the new path and legacy (strategies.py two sites).
3. Design doc R5 direction corrected (small pool = gate gets stricter, not "gate becomes decorative"); config comment + docs/architecture/routing-system.md small-pool note.
4. TFIDF IDF table only built with ≥2 candidates (single-candidate `score()` no longer poisons the gate).
5. CHANGELOG "6 knobs" → 7.
6. `_has_anchor` query tokenization hoisted out of the per-candidate loop.
7. `warm_up([])` now explicitly resets (clears table → legacy path + clears cache), with test.
8. Comment noting the [0.7, 0.78) name-guard dead band (incoherent but conservative).
9. New unit test: cov-floor refusal side (2 anchors, cov < 0.08 must NOT exempt).
10. config `keyword_coverage_ref` comment corrected; TG1-on REF band {0.4..0.6} re-run on production code, all 98/107, recorded in design doc appendix.
11. Direct unit test for reload_candidates → matcher re-warm (tests/unit/core/routing/test_matcher_rewarm.py).
12. MatcherConfig(keyword_coverage_ref=0.0) ZeroDivisionError guarded.

## Post-fix verified results (implementer-run; spot-check what you can)

- base 31/34, oneshot 10/11, extended 98/107 — per-query diff vs /tmp/m11-baseline.json: 17 error→OK, 0 OK→BAD; zero per-query diff vs the pre-fix M11 state.
- Full pytest: 5626 passed / 14 skipped / 0 failed.

## Verdict format

End with exactly one of: `VERDICT: PASS`, `VERDICT: PASS_WITH_NITS` (list nits), `VERDICT: BLOCK` (file:line + reasoning).
