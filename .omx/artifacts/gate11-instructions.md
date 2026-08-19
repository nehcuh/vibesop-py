# Gate 11 — Dual Review: M8 routing error clusters + test hermeticization

Review the UNCOMMITTED changeset in `/Users/huchen/Projects/vibesop-py`: diff at `.omx/artifacts/gate11.diff` (45KB). Prior context you may consult: `.omx/artifacts/gate10-*.md` (relabeling reviews). Read-only; do NOT modify files. You may run targeted pytest files if needed.

## Two workstreams

### Track A — test hermeticization (`tests/cli/test_route_commands.py`)
The remaining 11 live-routing tests (each loading a real HF model ~10s against the developer's live `.vibe` pool) were made hermetic via two seams: IntentInterceptor/AgentRuntime patching (route/edge-case/squad tests, following the `test_route_market_suggestion.py` convention) and UnifiedRouter patching (decompose tests, hitting the deterministic `_fallback_decomposition`). File went 152s → 0.38s, zero HF loads, no live-pool dependence. No test body assertions changed in intent.

### Track B — three residual routing-error clusters (real router fixes)
Cleaned eval baseline was 56/107 (52.3%) with 51 honest errors. Fixes:
1. **riper-workflow over-trigger (6 entries)**: removed the `planning` scenario from `core/registry.yaml` (broad plan/规划/方案/架构 keywords → riper at 0.90, contradicting the skill's ONLY-when-explicit contract); `riper-workflow` is now a **guarded skill** — fuzzy layers (keyword pipeline, semantic index token+embedding) cannot select it unless the query carries a declared trigger or the distinctive token `riper`.
2. **session-end bidirectional**: added trigger `离开了` (fixes FN 「我先离开了」); extended the explicit-signal guard (previously AI-triage only) to semantic-index + matcher-pipeline acceptance so non-exit queries like 「帮我先关闭了」 can't land on session-end. Generalized as a guarded-skill mechanism in `triage_service.py` (`guarded_skill_name`/`has_explicit_guard_signal`), consumed by `_layers.py` and `unified.py`.
3. **code_review scenario hijack (12 entries)**: `try_scenario_layer` resolved bare `primary: /review` to the first installed candidate ending in `/review` (mattpocock/review on dev machines) ignoring the scenario's `primary_source` field. Now `primary_source` is enforced fail-closed (no candidate in declared source → scenario inert); registry pins `primary_source: gstack` for code_review.

Measured: extended set 56/107 → **67/107 (62.6%)**, zero regressions (per-query JSON diff); oneshot 10/11 unchanged; base set 25/34 unchanged. New tests: 4 scenario primary_source + registry guards, 9 guarded-skill, index-layer guard tests, 3 unified matcher-gate tests; 2 pre-existing tests retargeted (they asserted the removed planning→riper behavior).

## Your task

Adversarial review, hunting especially:
1. **Guarded-skill mechanism**: is the guard list hardcoded to {session-end, riper-workflow}? Where does `has_explicit_guard_signal` get its trigger phrases — does it stay in sync if a skill's SKILL.md triggers change? Can the guard produce FALSE NEGATIVES on legitimate explicit requests (e.g. 「帮我做个 session 收尾」or "run the riper workflow")? Check the matcher-pipeline rejection point in unified.py — does it correctly fall THROUGH to lower layers instead of returning no-match?
2. **primary_source fail-closed**: what happens to existing scenarios in the wild whose declared source has no installed candidate — do they silently die (acceptable?) or log? Any scenario OTHER than code_review that declares/omits primary_source and changes behavior? Check all scenarios in core/registry.yaml.
3. **registry.yaml planning-scenario removal**: grep the codebase for anything referencing the `planning` scenario id or its keywords (docs, tests, other configs) — dangling references?
4. **Track A fidelity**: do the mocked seams still exercise the real code under test (CLI rendering, JSON shape, orchestration plumbing), or did the mocks swallow the thing being tested? Does `test_route_multi_agent_squad_query_renders_squad` still pin squad rendering?
5. **Retargeted tests**: the 2 pre-existing tests that asserted planning→riper — were they correctly retargeted, or quietly weakened?
6. Overfit check: do any changes special-case the eval queries verbatim?

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
