# Gate 14 Review — M11: Evidence-based keyword/TFIDF scoring

## Verification performed

- `[executed]` New tests: `test_idf.py` + `test_evidence_scoring.py` — 24 passed. Matching + routing suites: 412 passed, 2 skipped.
- `[executed]` Eval artifacts `/tmp/m11-baseline.json` / `/tmp/m11-after.json`: baseline 81/107 (75.7%), after 98/107 (91.6%) — matches claims exactly.
- `[executed]` Pool-size math spot-check (see Finding 1).
- `[inspected]` Full diff against `idf.py`, `strategies.py`, `router_factory.py`, `unified.py`, `manager.py`, tokenizers, design doc `m11-design-a.md`, eval diff `m11-eval-diff.md`.

## By review focus

**1. Scoring math correctness** — sound. `IDFTable` normalization is correct (df=0 → exactly 1.0; empty pool → weight 1.0, and both construction sites guard `if candidates:`); no zero-denominator (`or 1.0` fallback when query has no meaningful tokens); `score()` dispatches to evidence scoring when warmed (pinned by `test_generic_single_token_name_gets_no_bonus`, which exercises the single-candidate path); warm_up clears `_cache` (pinned). `hit_weight` precedence (`best / 0.15 * 0.6 if best else 0.0`) parses correctly.

**2. Anchor/IDF mechanism** — the five mechanisms are coherent and the stopword list rationale is verified ("not" df=3 → w=0.786 in the calibration pool would indeed anchor without it; matchers run CJK mode where `DEFAULT_STOP_WORDS` is not applied). One substantive structural risk the eval set structurally **cannot** cover:

- **Finding 1 — anchor eligibility is pool-size gated, with a cliff.** `[executed]` df=1 tokens anchor only at N≥8, df=2 at N≥54, df=3 at N≥200. Builtin-only install = **14 skills**: every term appearing in ≥2 builtin catalogs cannot anchor — e.g. "instinct" (in both `instinct` and `instinct-learning` names): w=0.704 at N=14 vs 0.83 at N=239. On such pools, keyword scores cap at 0.25 and the TFIDF gate drops everything for those queries. The design doc's own protected positive (「查看一下我的 instinct 学习状态」, §5) survives only on the 239-pool. Design doc §7 R5 acknowledges small pools but states the **wrong direction** ("多数 token w→1，闸门形同虚设" — only *unseen* tokens go to 1.0, and they can't anchor for lack of evidence; *evidenced* tokens compress down and the gate over-blocks). Failure mode is conservative (abstain → fallback), config-retunable, and absent from the calibrated environment — but a fresh pack-less install is the out-of-box experience, so this deserves a follow-up (pool-size floor below which legacy scoring is kept, or an N-scaled anchor_min) and an R5 correction.

- **Finding 2 — anchor evidence uses raw substring across word boundaries** (`idf.py:148`): `token in keywords_text` lets "art" anchor against "smart …" (unseen token → w=1.0, non-stopword, meaningful). This looseness is pre-existing for the +0.25 substring bonus, but M11 newly grants substring hits cap-lifting and gate-saturation (`nk_anchor`) powers. Two such hits + cov ≥ 0.08 reach g=1. Not observed on this pool (eval is clean), but it's the most plausible residual mis-fire path ≥0.6 — suggest a word-boundary check for non-CJK tokens.

**3. Backward compat** — verified. Un-warmed fallback is verbatim legacy (tested); all 7 knobs plumbed through `RouterFactory.build_matchers` with defaults identical in `MatcherConfig` and `RoutingConfig`; `reload_candidates()` correctly resets `_matchers_warmed` **before** reload (unified.py:385-390), fixing staleness for both the new IDF table and the pre-existing TFIDF fit; covered end-to-end by tests/integration/test_third_party_skill_pack.py:74. TFIDF gate flag on/off both tested.

**4. Tests** — genuinely pin all five mechanisms plus lifecycle and IDF primitives, with synthetic vocabulary (zephyrloom/quilting), satisfying the anti-overfit rule. Verified the test-pool weight claims (0.256/0.830) are arithmetically right. Minor gaps: no test for the small-pool behavior (Finding 1 — unrecognized edge) and `reload_candidates` re-warm has only indirect integration coverage.

**5. Calibration notes** — consistent with the design doc: REF 0.4–0.6 insensitivity band, anchor interval (0.724, 0.78] with type/模式 anchors, cov floor (0.049, 0.139) with 0.08 ≈ log-midpoint (√(0.049·0.139)=0.0825), name guard 0.7 between design(0.465)/instinct(0.83). The "meeting-notes misroute (0.049)" = routing_eval_extended.yaml:470 = design E25 — consistent.

**6. Scope** — clean. Only matching/, config, routing glue, docs, CHANGELOG, tests. No scenario/semantic_index touch.

## Nits

1. (Finding 1) Pool-size anchor cliff + wrong R5 direction — recommend follow-up guard; fix design doc §7 R5.
2. (Finding 2) `find_anchors` substring evidence crosses Latin word boundaries — harden with word-boundary check for non-CJK tokens.
3. `query_lower = " ".join(query_tokens)` (strategies.py:244) joins a **set** — order varies per process hash seed, so multi-token name containment (`name in query_lower`) can flip across processes. Pre-existing verbatim in legacy (line 315), replicated into the new path — not a regression, but worth fixing while touching this code.
4. `TFIDFMatcher.score()` standalone path fits `[candidate]`, leaving a 1-doc IDFTable (all evidenced tokens w=0.59) — a later `match()` skips re-fit and the gate drops *all* results. Unreachable via UnifiedRouter (warm_up precedes), pre-existing staleness pattern, but the gate amplifies the consequence.
5. CHANGELOG says "6 new RoutingConfig knobs" — there are 7 (and the sentence lists 7).
6. `_has_anchor` re-tokenizes the query per candidate (strategies.py:455) — hoistable above the filter loop.
7. `warm_up([])` after a real warm silently keeps the stale IDF table and stale cache — harmless in the current call graph, but the guard's semantics ("skip" vs "reset") are non-obvious.
8. Name-bonus guard band w ∈ [0.7, 0.78) is dead weight: the anchor cap (0.25) dominates any name bonus there, so a single-token name in that band can never route via keyword. Conservative, just incoherent thresholds — worth a one-line comment.

The milestone does what it claims, the eval evidence is real and internally consistent, the mechanisms are properly pinned by non-overfit tests, and compat paths hold. The nits above are hardening/robustness items, none invalidating on the calibrated environment.

VERDICT: PASS_WITH_NITS
