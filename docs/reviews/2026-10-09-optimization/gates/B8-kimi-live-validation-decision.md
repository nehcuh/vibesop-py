# B8 final validation-contract reconciliation — Kimi technical lead (read-only)

**Decision: B8_VALIDATION_CONTRACT_APPROVE** — the amended D15 implementation acceptance is satisfied. Live API wiring is proved by a real Deepseek-API run (6/7, exit 1); last-good decay/threshold semantics are proved separately by the controlled 7/7; the live T4 positive branch remains **explicitly UNVERIFIED** and is preserved as such. No condition of the C1–C6 contract is breached.

Date: 2026-10-09. Reviewer role: Kimi technical lead. Read-only final interpretation: no source/test/CHANGELOG/patch modifications, no commit/push, no Docker/API/auth calls, no models/subagents/delegation, no redefinition of any historical result.

## 1. Question answered

Does the new evidence satisfy the amended D15 implementation acceptance — live API wiring proved separately from last-good semantic controlled proof, with the live positive branch still explicitly UNVERIFIED at 6/7? **Yes.** The amended contract (B8-kimi-contract-decision.md, CONTRACT_AMEND_APPROVE) explicitly anticipates and accepts exactly this outcome: A2 requires that on model re-abstain "T4 FAIL 且 detail 含 `PRECONDITION_MISSING`；summary 仍为 6/7 exit 1", and forbids rewriting it to 7/7 even when controlled passes.

## 2. Evidence read (all in this pass)

| Evidence | What it shows |
|---|---|
| `B8-kimi-contract-decision.md` | CONTRACT_AMEND_APPROVE with conditions C1–C6, acceptance A1–A6 |
| `B8-kimi-confidence-pre-report.md` | Kimi gate APPROVE on patch SHA `96f6c21b…`; 52/52 probe, 118/118 tests, 7/7 controlled CLI; T4 precondition discipline with real `_run_live_t4` subprocess (no deadbeef, no blackhole staging, cache bytes unchanged) |
| `B8-confidence-native-review.md` (new Codex auxiliary) | 24 negative mutations (`.01`/bool/nan/inf/-inf/delete-confidence/wrong-skill/delete-metadata × 3 accept-family cases) all rejected; reject branch independent of scenario confidence; 7 controlled cases via real `SkillRoute.to_dict → TriageCache.store → UnifiedRouter.route` with throwing transport; production byte-identity SHAs; original live log SHA `a11deb55…` preserved |
| `logs/B8-confidence-target-container.log` (+`.result.json`) | Fresh Docker: **118 passed** on `vibesop-next-val:node24`, patch SHA `96f6c21b…` |
| `logs/B8-confidence2-controlled-container.log` (+`.result.json`) | Fresh Docker: **CONTROLLED SUMMARY 7/7 marker=controlled**, `LIVE SUMMARY: not run`, exit 0, all 7 branches (accept .9→.63, reject .8→.56, equality gate/.7→.6, negative, no-entry, same-skill-two-query `.8` vs `.9` via distinct captured keys, context-key augmented-query), `confidence_source=controlled_fixture` |
| `logs/B8-confidence2-live-container.log` (+`.result.json`) | Fresh Docker, real Deepseek API (key by env name only, redacted): T0–T3, T5 PASS; **T1 real LLM call** (provider=SpanWrappedProvider, triage_log 0->1, 0.9s); T2 captured augmented key `7cf26d05…`, explicitly `cache_row=negative positive_persistent_hit=false`; **T4 FAIL `PRECONDITION_MISSING cache_row=negative`** at the same captured key; `E2E SUMMARY: 6/7`, `SCRIPT_EXIT 1` |
| `logs/B8-confidence1-*-container.log` | Both attempts failed on dependency downloads (numpy / tomlkit timeouts) **before any script executed** — environmental, preserved as-is, correctly counted as neither pass nor fail |
| Independent SHA re-check (this pass) | In `snapshots/B8-confidence2-live-docker`: script `81b8d696…`, `triage_service.py` `0e87fbef…`, `triage_cache.py` `e8150cbe…`, `unified.py` `39e840c3…`, `config/manager.py` `992ad90a…` — all byte-identical to the values in both prior reviews; `LAST_GOOD_CONFIDENCE_DECAY = 0.7`, production default `min_confidence = 0.3` (controlled gate .6 is harness config, not a production change) |

## 3. Contract condition check (C1–C6 / A1–A6)

- **C1 / A1 production invariant — satisfied.** All four production files byte-identical to HEAD across both confidence2 Docker snapshots (independently re-hashed this pass); decay 0.7, default 0.3, config unchanged. Diff scope is the four allowed files (script + two test files + isolated CHANGELOG entry).
- **C2 / A2 live default path — satisfied.** No-flag live run: T0/T1/T1b/T2/T3/T5 pass; T2 located the row by the real captured augmented key and **explicitly labelled it negative** (`positive_persistent_hit=false`); T4 judged the precondition **before** any cache mutation, recorded `PRECONDITION_MISSING cache_row=negative`, stayed FAIL (not PASS, not SKIP-as-pass), and per the pre-report's real-subprocess probe performed no `deadbeef` write and no blackhole staging; summary 6/7 exit 1, matching A2 verbatim. The historical 6/7 logs (old live `a11deb55…`) are untouched.
- **C3 / A3 controlled fixtures — satisfied.** 7/7 in fresh Docker with `marker=controlled`; fixtures from real `SkillRoute(..., layer=AI_TRIAGE, source_file=<real temp SKILL.md>).to_dict()` through real `TriageCache.store` into `TemporaryDirectory` sandboxes; staleness from real candidate-set change; LLM failure via configured transport stub consumed by the real `UnifiedRouter` path; expectations computed from real router config and the production decay constant.
- **C4 / A4 oracle identity — satisfied.** Row identity by lookup-boundary observer at the real augmented query/key; the live run captured key `7cf26d05…` matches T2↔T4; the same-skill two-query controlled case returns the actual `.8` row for its query with `other_original=0.9` and no cross-contamination; no full-cache `skill_id in reason` scan remains.
- **C5 controlled honesty — satisfied.** Every controlled line carries `marker=controlled` / `confidence_source=controlled_fixture`; the controlled container prints `LIVE SUMMARY: not run`; controlled 7/7 is nowhere presented as a live result and does not upgrade the historical 6/7.
- **C6 / A5 / A6 — satisfied.** Post-corrective re-review done on the new snapshot (this report plus the native review); 118/118 targeted tests in Docker (and 118 passed natively); no new dependencies, no new script files.
- **Negative-branch honesty — satisfied.** 24 negative mutations all correctly rejected on accept/equality/context; reject branch verified independent of scenario fallback confidence; negative-cache and no-entry rows remain non-PASS by production semantics (`_last_good_route` refuses skill_id-null rows).

## 4. What is proved vs. what is not

**Proved now:**
- Live API wiring after the corrective: the default path reaches the real Deepseek API and parses its response (T0/T1, 0.9s live call), the real cache path serves a captured augmented-key row with zero LLM calls (T2), and the corrected oracle reports a negative-row precondition honestly instead of a false pass (T4) — this is precisely the D15 scope "真实 API 只验传输/解析".
- Last-good decay/threshold semantics deterministically: accept .9→.63 ≥ gate, reject .8→.56 < gate, equality boundary, negative/no-entry non-pass, same-skill key disambiguation, context-key augmentation — via the real router, cache, and throwing transport.
- The core-public live T1 negative row is a legitimate upstream model response (abstain on the minimal fallback prompt), not a product defect; the negative cache making the repeat call zero-LLM is legal production behavior.

**Explicitly NOT proved / unchanged status (no redefinition):**
- The live T4 **positive** branch (live positive row → deadbeef staleness → blackhole degradation end-to-end) remains **UNVERIFIED**; the live outcome stands at **6/7, exit 1**, permanently. No 6/7→7/7 rewriting, no skip-as-pass occurred anywhere in the evidence chain.
- Native Windows suite: still pending; no Windows behavior is claimed.
- confidence1 Docker failures: environmental (dependency downloads before UV/script execution), preserved as historical non-results.

## 5. Boundaries

This report is **only the final validation interpretation of the amended D15 contract**. It is not a commit-gate substitute: the source-commit gate still requires the actual GLM cross-verification and the Kimi post-closure report as its own steps, tracked separately. No production/provider/prompt widening was performed or requested to force a live positive row — the live abstain is accepted as nondeterminism and the FAIL is the contract-correct result.

## 6. Verdict

**B8_VALIDATION_CONTRACT_APPROVE.** All six contract conditions and all six acceptance criteria hold on fresh-Docker evidence plus two independent native verifications; live wiring (6/7, real API) and controlled semantics (7/7) are proved as separate contracts exactly as amended; the live positive branch remains explicitly unverified with the historical 6/7 intact. Remaining items — native Windows suite, GLM cross + Kimi post-closure commit gate — are out of scope here and tracked separately.
