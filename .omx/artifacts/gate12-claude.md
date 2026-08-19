All evidence gathered. Compiling the verdict.

**Verification summary**: 76/107 extended and 30/34 base reproduced exactly [executed]; touched test files 67 passed in 0.21s (hermetic) [executed]; calibration tables show extended positives have **0.000 token-path coverage at any threshold ≥ 0.10** — the pack positives ride the embedding path, so the 0.20→0.30 external bar could not have regressed any of them [executed].

```
VERDICT: PASS_WITH_NITS
BLOCKS:
- none
NITS:
- src/vibesop/core/routing/_layers.py:568 — `index_match_threshold` is read directly
  while the two new knobs go through `_cfg_float`; a MagicMock test config that
  forgets it now dies inside `max()` (TypeError) before the token loop, with a
  less obvious error than the old comparison site. Asymmetric robustness for no
  reason — route it through `_cfg_float` too, or through none of them.
- src/vibesop/core/routing/_layers.py:579-594 vs 417-433 — the two paths now
  treat uninstalled profiles inconsistently: embedding ranks installed-only,
  but the token loop still lets a stale high-scoring profile (e.g. 0.5 overlap)
  win and then kill the layer at the candidate check (:606-613) without ever
  trying the embedding fallback. Pre-existing behavior, but the new comment
  "no benefit of the doubt" (:563-566) oversells — a stale profile still gets
  plenty of benefit of the doubt. Same invariant ("only installed candidates
  compete") in both paths would be cleaner.
- src/vibesop/core/routing/_layers.py:452,571 — `_cfg_float` fallback defaults
  (0.05 / 0.30) duplicate the RoutingConfig Field defaults; change one without
  the other and they silently diverge (only MagicMock tests would notice).
- src/vibesop/core/skills/parser.py:276-280 (pre-existing, outside diff) —
  `infer_source` maps `~/.kimi/skills` and `~/.config/opencode/skills` to
  namespace "builtin", which M9's `_TRUSTED_INDEX_NAMESPACES` now treats as
  curated: those agent-dir catalogs get the 0.20 trusted bar. Latent on this
  machine (dirs effectively empty) but it re-opens exactly the channel M9
  closes, on machines that do use those agents. Follow-up: extend infer_source
  or derive the trusted set from the candidate source, not the namespace string.
- src/vibesop/core/routing/_layers.py:435 — EMBEDDING_THRESHOLD stays a
  hardcoded 0.45 while its two neighbors became config knobs; the margin
  calibration (errors in 0.45-0.55 band) is tied to that constant.
- docs/ has zero mention of any index-layer threshold (grep clean); the gate
  order (trusted bar → external bar → 0.45 floor → margin → guarded-signal →
  uninstalled-exclusion) lives only in code comments and config descriptions.
  Six gates in one layer is past what comments can carry.
NOTES:
- Q1 (margin math): sound. 1 installed candidate → second_similarity stays 0.0,
  margin ≥ 0.45, gate inert (correct). Exactly 2 → normal gap check; exact tie
  → margin 0 → abstain (correct for ambiguity). All-below-floor → the 0.45
  floor fires first; margin is only evaluated above it (correct ordering).
  Legitimate near-synonym pairs do now abstain from this layer and fall to the
  keyword/TF-IDF/levenshtein pipeline — when both answers are good, either pick
  was fine, so the cost is soft; measured effect is +9 extended / +5 base with
  zero regressions. The M7 0.25 floor is the AI-triage prefilter (different
  layer); the only interplay is the documented 0.25 < 0.45 ordering, which
  holds.
- Q2 (partition): oneshot-web-spec lives at <project>/.vibe/skills →
  infer_source "project" → trusted bar — correct (project-curated). The gate
  prompt's ~/.vibe/skills premise is off: that dir is in no search path
  (candidate_manager.py:239-245 scans project .vibe/skills, ~/.config/skills,
  ~/.config/opencode, ~/.claude, ~/.kimi). User-global skills land at
  ~/.config/skills (loose → namespace "external", pack subdir → pack name) —
  both external bar. Defensible: every indexed profile is LLM-generated; a
  lone deliberate global skill scoring 0.25-0.29 was precisely the marginal
  band M9 targets. Index keys are namespace-prefixed and align with candidate
  ids (live routing to omx/* and mattpocock/* through this path proves it).
  Uninstalled/stale profiles miss the ns lookup → external bar ✓.
- Q3 (plumbing): single production caller (unified.py:865,879) reads
  router._config; knobs are pydantic fields with defaults → present at every
  RoutingConfig construction, no bypass sites. MagicMock-safety claim verified
  in practice: the new tests set only index_match_threshold, pass hermetically.
- Q4 (brittleness): 76/107 and 30/34 reproduced exactly [executed]. Calibration
  on the real 110-profile index: extended positives have 0.000 token coverage
  at every threshold ≥ 0.10 — no pack positive rides the token path, so the
  external bar regression risk is structurally zero for them. The one
  load-bearing near-cutoff is git-master's embedding margin 0.071 vs cutoff
  0.05 (~0.021 headroom); an index regen (new LLM profiles → new embeddings)
  can flip that single entry → worst case 75/107. Main set: only one query has
  token top-1 ≥ 0.30 (cov 0.032); base-set winners ride the unchanged 0.20
  builtin bar or other layers. Mildly brittle, single-entry exposure —
  acceptable.
- Q5 (layering): honest answer — this is stacked heuristics, but each layer has
  a mechanism story and calibration provenance in its config description, and
  the eval validates the combination. The residual errors show where the stack
  stops working: omx/plan ×3 at 66-73% confidence (token scores ~0.40-0.46,
  far above any bar) and mattpocock/review at 65% (score ≈ 0.31 — a marginal
  external accept that still clears the new 0.30 bar). The next cluster is
  strong-overlap pack profiles, which threshold bars cannot fix; don't add a
  seventh gate before consolidating the story in docs/ and considering
  pack-level demotion at the arbitration stage instead.
- Off-scope residual observed while running: 「用 RIPER 流程来做这个功能」
  falls to fallback-llm despite containing "RIPER" — M8 guard appears
  case-sensitive; and 2 scenario-layer hijacks by the project skill
  fuck-my-shit-mountain (no primary_source declared). Both pre-date M9.
- Test-claims check: exactly 10 new tests (4 external-bar + 4 margin + 2 config
  bounds), all non-eval queries (acme-pack/ship-release, "zq wv xk"); the
  weak-overlap arithmetic in the test comment (2/max(3,8)=0.25) is correct.
  gate12.diff matches the working tree for all four files.
```
