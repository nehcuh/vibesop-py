# Gate 14b Re-review — M11 fix round

## BLOCK-1 verification [executed]

Reproduced against the real pool via `UnifiedRouter(project_root=repo)` → `KeywordMatcher(MatcherConfig())` warmed on `router.get_candidates()`:

- Pool size = **239** candidates (matches calibration pool).
- `w(get) = 0.830` in the real pool — confirmed it *would* anchor (≥ 0.78); `get` is now in `ANCHOR_STOPWORDS`, as are all 15 gate14 words (get/make/can/but/will/who/there/should/would/could/because/most/same/some/such — checked in idf.py:53-294).
- `get this working on the new branch before the deadline` vs `mattpocock/grill-me` → **score 0.2500** (= the anchorless cap, matching the claimed 0.25 < 0.3 floor).
- `match()` at default `min_confidence=0.3` returns **0 results**; worst raw score across the entire pool is 0.25 — no candidate is routable on this query. Blocker is real-fixed.

## Nit fixes 1–12 [inspected + executed]

| # | Status |
|---|--------|
| 1 | `_substring_evidence` Latin word-boundary + CJK containment (idf.py:299-308), unit-tested both sides. See nit A below re: the "(commented)" sub-claim |
| 2 | sorted join at both sites (strategies.py:248, 326) |
| 3 | R5 direction corrected — routing-system.md:170-172 ("STRICTER on small pools… lower this value") + config comment |
| 4 | TFIDF `fit` ≥2-doc guard (strategies.py:396-402); single-candidate `score()` no longer poisons the gate |
| 5 | CHANGELOG says "7 new `RoutingConfig` knobs"; manager.py has exactly 7 new fields |
| 6 | Query tokenization hoisted out of the per-candidate loop (strategies.py:458-462) |
| 7 | `warm_up([])` explicit reset → `_idf=None` + cache clear (strategies.py:356-362), tested |
| 8 | [0.7, 0.78) dead-band comment present (strategies.py:255-259) |
| 9 | `TestCoverageFloorRejectsExemption` present and passing |
| 10 | Config comment corrected; design doc appendix records the re-run (m11-design-a.md:226). I independently re-ran the band: **98/107 at REF 0.4, 0.5, and 0.6** |
| 11 | test_matcher_rewarm.py present and passing (see nit B) |
| 12 | `max(cfg.keyword_coverage_ref, 1e-9)` guard (strategies.py:234) + test |

## Claimed results — independently reproduced [executed]

- base **31/34**, oneshot **10/11**, extended **98/107**; the 9 extended errors match the documented residual classes exactly (3 scenario fixed-0.9, 4 fallback recall misses, 2 semantic-index).
- New unit tests: 31/31 pass. Full suite: **5626 passed / 14 skipped / 0 failed** (4:21) — matches the implementer's claim.
- Ruff clean on all changed files.

## Nothing-new sweep

- `triage_service.py:426` builds a `KeywordMatcher` per call but never warms it → legacy path, unaffected by M11. ✓
- TFIDF gate's `r.skill_id in by_id` drop is safe (results are built from the same candidate list in the same call). Empty-`meaningful` coverage edge → gate 0 + anchorless cap; safe. Multi-anchor exemption implies anchors non-empty, so cap never conflicts. ✓
- `reload_candidates` → re-warm → `warm_up` also clears the keyword query cache, which fixes a latent stale-cache-across-pools issue as a side effect. ✓

## Nits

- **A.** strategies.py:236-243 — `substring_bonus` keeps plain containment (`qt in name or qt in keywords_text`); the gate14 sub-claim "intentionally loose semantics (commented)" is only realized via the docstring bullet ("idf-discounted per hit"), there is no comment at the site. Behavior is fine (IDF-discounted, capped 0.5, anchor gate unaffected); documentation gap only.
- **B.** tests/unit/core/routing/test_matcher_rewarm.py:27 — final assertion `km._cache == {} or km._idf is not None` is a near-tautological OR that passes under either pool state. The meaningful rewarm assertions are the `_matchers_warmed` toggles above it; the last line adds little. Test-strength nit.
- **C.** `TFIDFMatcher.warm_up([])` (strategies.py:542-544) does not reset `_fitted`/`_idf`, asymmetric with KeywordMatcher's new explicit empty-pool reset. Currently inert (empty candidate list yields no results, and the `by_id` gate drops everything), so asymmetry only — worth aligning if touched again.

All three nits are non-behavioral (docs/test-strength/consistency); the blocker fix and all 13 nit fixes are real and verified on production code, with zero regressions found.

`VERDICT: PASS_WITH_NITS` (nits A, B, C above)
