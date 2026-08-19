# Gate 12 — Dual Review: M9 residual-cluster fixes (embedding margin gate + external token bar)

Review the UNCOMMITTED changeset in `/Users/huchen/Projects/vibesop-py`: diff at `.omx/artifacts/gate12.diff` (23KB). Context: `.omx/artifacts/gate10-*.md`, `gate11-*.md`. Read-only; do NOT modify files.

## What changed (M9)

Two mechanism-level fixes to the semantic_index layer (`src/vibesop/core/routing/_layers.py`), driven by clustering the 40 residual eval errors (39/40 were env-dependent pack matches on this dev machine: 110 indexed profiles, 96 external vs 14 builtin):

1. **Embedding-fallback margin gate** (`_try_embedding_fallback`): ranking now considers only *installed* candidates, and requires `top1_sim − top2_sim ≥ index_embedding_min_margin` (new config, default 0.05). Rationale: argmax over a large LLM-generated catalog always finds a noise-band nearest neighbor; genuine intent separates from runner-up, noise doesn't. Calibration: 24 error sims had margins mostly <0.05; the one passing hit (git-master, margin 0.071) survives. A plain absolute-threshold raise was provably impossible (passing 0.454 < failing 0.579).
2. **External namespace token bar** (`try_index_layer`): eligibility-first selection — builtin/project profiles clear `index_match_threshold` (0.20); external/uninstalled profiles must clear `max(threshold, index_external_match_threshold)` (new config, default 0.30). Confidence scaling starts at the winner's own bar. Rationale: pack profiles are LLM-generated with overlapping vocabulary; marginal bigram overlap is weaker evidence than the same overlap with curated builtin/project profiles.
3. New `_cfg_float` helper (MagicMock-safe config reads), `_TRUSTED_INDEX_NAMESPACES`, config fields with rationale docstrings, 10 new tests (all using non-eval queries).

Measured: extended 67/107 → 76/107 (zero regressions, failing-set diff verified); base 25/34 → 30/34; oneshot 10/11 unchanged. `tests/core tests/unit`: 3202 passed.

## Your task

Adversarial review:
1. **Margin gate math**: is `top1−top2 ≥ margin` on cosine sims sound for this model? What happens with exactly 2 candidates? 1 candidate? All-below-0.45-floor candidates? Can a legitimate pair of near-synonym skills (both good answers) now abstain entirely — is abstention (falling to levenshtein/fallback) actually better there? Check interplay with the existing 0.45 hard floor and the recall floor (0.25) from M7.
2. **External bar**: is `builtin/project = trusted, everything else = external` the right partition? What about user-installed *global* skills the user deliberately added (`~/.vibe/skills/`, e.g. the oneshot-web-spec project skill lives at `.vibe/skills/oneshot-web-spec` — which bucket does it land in, and is that right)? Namespace string matching — check actual profile id formats in `.vibe/skill-index.json` vs the trusted set.
3. **Config plumbing**: verify the two new knobs reach every construction site of the layer functions (grep callers), defaults sane, MagicMock-safety claim true.
4. **Regression sweep**: any currently-passing eval entry whose margin/bar is near the new cutoffs (margin ∈ [0.05, 0.07], external token score ∈ [0.30, 0.35])? A future index rebuild shifts sims slightly — how brittle is 76/107?
5. **Consistency**: M7 added recall floor config; M8 guarded skills; M9 margin+external bar — is the layering story still coherent (docs/comments), or are we stacking heuristics? Honest assessment welcome.

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
