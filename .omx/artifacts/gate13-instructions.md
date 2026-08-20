# Gate 13 — Dual Review: M10 (pack arbitration + suite hermeticization)

Review the UNCOMMITTED changeset in `/Users/huchen/Projects/vibesop-py`: diff at `.omx/artifacts/gate13.diff`. Context: `.omx/artifacts/gate12-*.md` (M9 review), `docs/architecture/routing-system.md` (M9/M10 gate docs). Read-only; do NOT modify files.

## Track A — pack-level arbitration (routing behavior change)

After M9's per-layer gates, the remaining hard cluster was strong-overlap pack wins: pack profiles (omx/plan etc.) clearing every per-layer bar legitimately on generic queries. The separability investigation (absolute band, margin, trusted-gap hypotheses all provably inverted on the one must-keep pack positive git-master @ 0.454/trusted 0.274) produced this rule, implemented in `_try_embedding_fallback` (`src/vibesop/core/routing/_layers.py`):

**An external pack winner is accepted only when NO trusted-namespace profile clears `index_external_trusted_floor` (new config, default 0.35).** Trusted-above-floor ⇒ the query has curated-catalog content and the pack win is crowd-out ⇒ abstain (defer to AI triage; never promote the sub-floor trusted runner-up). Trusted-below-floor ⇒ the query isn't about anything curated ⇒ pack win stands.

Measured: extended 76 → 81/107 (+5, byte-level zero regressions); base 31/34 unchanged; oneshot 10/11 unchanged. New tests: TestPackTrustedArbitration (5, non-eval queries) + config bounds. Docstring carries the fragility note (lowest cluster member at 0.352, 0.002 above floor).

## Track B — test-suite hermeticization (no production behavior)

Profiling found the remaining real-model/network loads in the suite (the 17min wall time). Fixes stub `sentence_transformers`/model loads where incidental and use fake models where embedding behavior is under test. Files touched are visible in the diff (tests/**). Claimed: big per-file wall-time drops, zero intent changes.

## Your task

1. **Arbitration rule soundness**: trace `_try_embedding_fallback` — does the trusted-floor check run AFTER the margin gate, only on external winners? What if the trusted best is ALSO above floor but the winner is trusted (no arbitration — verify)? What if NO candidate is installed (empty ranking)? Is 0.35 vs the M7 recall floor 0.25 / M9 embedding floor 0.45 ordering coherent? Can a query about a trusted-domain topic where the trusted skill is genuinely absent (e.g. git questions with only pack git skills installed) now abstain wrongly — is triage deferral the right landing?
2. **Fragility**: the floor's justification rests on cluster member 0.352 vs positive 0.274 — an index rebuild shifts these. Is the docstring warning adequate, or should the floor be lower (e.g. 0.32)? Opinion.
3. **Track B fidelity**: for each touched test file, verify the stub doesn't neuter the test's actual assertion target. Any test whose purpose WAS embedding behavior but got blanket-stubbed (should use a fake model instead)?
4. **Conftest changes**: if tests/conftest.py changed, check the blast radius — does it affect every test in the suite? Any fixture that could mask real integration coverage (e.g. tests that SHOULD hit the model in CI)?
5. Overfit check on the eval numbers; confirm no eval-query text in production code.

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
