Usage: vibe route [OPTIONS] {query}
Try 'vibe route --help' for help.
╭─ Error ──────────────────────────────────────────────────────────────────────╮
│ Got unexpected extra argument(s) (the riper workflow\)? Check the            │
│ matcher-pipeline rejection point in unified.py — does it correctly fall      │
│ THROUGH to lower layers instead of returning no-match? 2. **primary_source   │
│ fail-closed**: what happens to existing scenarios in the wild whose declared │
│ source has no installed candidate — do they silently die (acceptable?) or    │
│ log? Any scenario OTHER than code_review that declares/omits primary_source  │
│ and changes behavior? Check all scenarios in core/registry.yaml. 3.          │
│ **registry.yaml planning-scenario removal**: grep the codebase for anything  │
│ referencing the `planning` scenario id or its keywords (docs, tests, other   │
│ configs) — dangling references? 4. **Track A fidelity**: do the mocked seams │
│ still exercise the real code under test (CLI rendering, JSON shape,          │
│ orchestration plumbing), or did the mocks swallow the thing being tested?    │
│ Does `test_route_multi_agent_squad_query_renders_squad` still pin squad      │
│ rendering? 5. **Retargeted tests**: the 2 pre-existing tests that asserted   │
│ planning→riper — were they correctly retargeted, or quietly weakened? 6.     │
│ Overfit check: do any changes special-case the eval queries verbatim?        │
│ Verdict format (exactly): ``` VERDICT: PASS | PASS_WITH_NITS | BLOCK BLOCKS: │
│ - [severity] file:line — issue — why NITS: - file:line — issue NOTES: - ...  │
│ ``` diff --git a/core/registry.yaml b/core/registry.yaml index               │
│ 50db96f..74d32c9 100644 --- a/core/registry.yaml +++ b/core/registry.yaml @@ │
│ -106,15 +106,11 @@ conflict_resolution:        - \头脑风暴\        - \idea\  │
│ - \想法\ -    planning: -      - \plan\ -      - \规划\ -      - \计划\ -    │
│ - \方案\ -      - \design\ -      - \设计\ -      - \architect\ -      -     │
│ \架构\ +    # \planning\ keywords removed (2026-08): the planning scenario   │
│ routed broad +    # plan/design/方案 keywords to builtin/riper-workflow at a │
│ fixed 0.9, +    # contradicting that skill's explicit-intent-only contract   │
│ and hijacking +    # generic design/planning queries. RIPER now routes only  │
│ via its own +    # explicit triggers.      refactoring:        - \refactor\  │
│ - \重构\ @@ -190,9 +186,12 @@ conflict_resolution:          - \用            │
│ superpowers\        # Code review: prefer gstack for pre-landing (SQL        │
│ safety, auto-fixes) +    # primary_source is enforced fail-closed: without   │
│ an installed gstack +    # candidate the scenario stays inert instead of     │
│ hijacking an unrelated +    # pack's review skill at the fixed scenario      │
│ confidence.      - scenario: code_review        primary: /review -#          │
│ primary_source: gstack +      primary_source: gstack        alternatives:    │
│ - skill: /receiving-code-review            source: superpowers @@ -214,29    │
│ +213,12 @@ conflict_resolution:        override_keywords:          - \用     │
│ superpowers\   -    # Planning: builtin fallback, gstack/omx for specific    │
│ angles -    - scenario: planning -      primary: riper-workflow -            │
│ primary_source: builtin -      alternatives: -        - skill:               │
│ /plan-ceo-review -#           source: gstack -          trigger:             │
│ \CEO/产品角度\ -        - skill: /plan-eng-review -#           source:       │
│ gstack -          trigger: \架构技术角度\ -        - skill:                  │
│ /plan-design-review -#           source: gstack -          trigger: \设计/UX │
│ 角度\ -        - skill: /autoplan -#           source: gstack -              │
│ trigger: \完整自动审查\ -        - skill: /writing-plans -          source:  │
│ superpowers -          trigger: \创建设计文档\ -      override_keywords: -#  │
│ - \用 gstack\ -        - \用 superpowers\ +    # Planning: REMOVED           │
│ (2026-08). The scenario coupled broad planning +    # keywords               │
│ (plan/design/方案/计划) to builtin/riper-workflow at a fixed +    # 0.9      │
│ confidence, but that skill's contract is explicit-RIPER-intent +    # only — │
│ generic planning queries were systematically misrouted to it. +    # RIPER   │
│ remains reachable via its own triggers (\use riper\, +    # \riper           │
│ workflow\, \五阶段工作流\, ...) and the guarded-skill rule.        #         │
│ Refactoring: prefer superpowers      - scenario: refactoring diff --git      │
│ a/core/skills/session-end/SKILL.md b/core/skills/session-end/SKILL.md index  │
│ 968a934..ed504cf 100644 --- a/core/skills/session-end/SKILL.md +++           │
│ b/core/skills/session-end/SKILL.md @@ -12,6 +12,7 @@ triggers:    - \Im      │
│ done\\"    - \\"gotta go\\"    - \\"我要离开了\\" +  - \\"离开了\\"    -     │
│ \\"先走了\\"    - \\"收工\\"    - \\"拜拜\\" diff --git                      │
│ a/src/vibesop/core/routing/_layers.py b/src/vibesop/core/routing/_layers.py  │
│ index bcc499d..f467244 100644 --- a/src/vibesop/core/routing/_layers.py +++  │
│ b/src/vibesop/core/routing/_layers.py @@ -88,28 +88,61 @@ def                │
│ try_scenario_layer(              diagnostics={\\"scenario\\":                │
│ scenario.get(\\"scenario\\")},          )   -    candidate = next((c for c   │
│ in candidates if c[\\"id\\"] == target_skill), None) +    # Honor the        │
│ scenarios declared primary_source: when a scenario pins its +)               │
╰──────────────────────────────────────────────────────────────────────────────╯
All checks complete. Here is the adversarial review.

---

## Verification summary

- Ran all changed test files: `test_route_commands.py` (19 passed, 0.35s — hermeticization confirmed), `test_scenario_layer.py` + `test_index_layer.py` (46), `test_unified_router_branches.py` (25+2 skip), `test_triage_service.py` (53). Full routing suite: **663 passed, 2 skipped in 51.67s**.
- Empirically confirmed: `vibesop_dev` project pattern (`.vibe/skill-routing.yaml`, pre-existing, merged into the scenario layer) routes `改进路由`/`优化 vibesop 的路由` → `builtin/riper-workflow` at 0.9 with **no guard**; code_review/refactoring/architecture fail closed without their declared sources; `帮我做个 session 收尾`/`wrap up the session please`/`把会话结束了吧`/`今天先这样吧` → session-end signal **False** at every layer; `我先离开了` → **True**.

```
VERDICT: PASS_WITH_NITS
BLOCKS:
NITS:
- src/vibesop/core/routing/_layers.py:88-155 — the guarded-skill mechanism does NOT cover the scenario layer. try_scenario_layer resolves and returns matches with no has_explicit_guard_signal check, and this repo's live `.vibe/skill-routing.yaml` `vibesop_dev` pattern (target riper-workflow, no primary_source) routes 「改进路由」/「优化 vibesop 的路由」 → builtin/riper-workflow at fixed 0.9 with no RIPER trigger (verified). The diff's claim "fuzzy layers cannot select it" enumerates only keyword/index/embedding — accurate as written, but the same fixed-0.9 fuzzy route the planning-scenario removal was meant to kill is still reachable via any scenario_pattern→riper. If the explicit-intent-only contract is to hold globally, the scenario layer needs the same guard (and this repo's own project pattern would then need an explicit-signal gate).
- src/vibesop/core/routing/triage_service.py:494-515 — FALSE NEGATIVES on legitimate explicit session-end requests, at every layer (fast path unified.py:900, index, embedding, matcher gate, and AI triage all use is_explicit_session_end_signal). Verified: 「帮我做个 session 收尾」, "wrap up the session please", 「把会话结束了吧」, 「今天先这样吧」 all signal=False. Pre-change, the keyword matcher could hit these (same 0.65 会话-tag mechanism as the 「帮我先关闭了」 false positive this diff fixes). Conservative-by-intent for a high-side-effect skill, but the FN class is real and common — consider adding 收尾/wrap-up-style triggers to the SKILL.md list.
- src/vibesop/core/routing/triage_service.py:443-472 — guard registry is hardcoded to {session-end, riper-workflow}: `is_session_end_skill` id-set + `_GUARDED_SKILL_EXTRA_TOKENS` keyed on the short skill id. Not data-driven from registry `trigger_mode: manual` or SKILL.md intent; a renamed skill silently loses its guard, a new explicit-only skill silently never gets one (e.g. autonomous-experiment is trigger_mode: manual but unguarded).
- src/vibesop/core/routing/triage_service.py:463-464,507 — trigger-sync is partial: candidate `triggers` (populated from SKILL.md frontmatter, candidate_manager.py:162) are used when present — good — but `_GUARDED_SKILL_FALLBACK_TRIGGERS` is a hardcoded duplicate that omits "use riper"/"5 phase workflow"/"structured workflow" (all in core/skills/riper-workflow/SKILL.md); only the "riper" extra-token partially covers. session-end has a SKILL.md-tie test (test_session_end_real_skill_md_covers_leaving); riper has no such tie.
- src/vibesop/core/routing/unified.py:763-780 + src/vibesop/core/routing/result_mixin.py:284-288 — matcher-gate rejection correctly falls to `_finalize_no_match` → fallback-llm (default transparent) without promoting the runner-up (defensible), BUT the fallback/silent paths re-run the matcher pipeline UNGATED and surface the guarded skill as a "nearest" ALTERNATIVE — the guard leaks into fallback suggestions. Suggestion-only, so low harm; inconsistent with the guard's intent.
- src/vibesop/core/routing/_layers.py:101-107,126-155 — primary_source enforcement is global, not code_review-only: refactoring/architecture (superpowers) and requirements_clarification/persistent_execution/structured_planning/parallel_execution/qa_cycling (omx) now fail closed on pack-less machines — correct philosophy, but (a) the diff's scope statement says "code_review", (b) it's silent at the routing level (LayerDetail only, no logger.warning), and (c) code_review pins gstack, which is REMOVED from this registry (namespaces + skills sections commented out) and not installed anywhere — so code_review is inert in the default config everywhere, by design (AI triage/matcher handle review queries; eval +12). Also note debugging/product_thinking keep `primary_source` commented out → legacy first-match, now inconsistent with the other 8.
- tests/core/routing/test_unified_router_branches.py:57-86 — retargeted `test_scenario_planning_query` is weakened: asserts only `primary is None or primary.skill_id != "builtin/riper-workflow"`, which passes even if routing returns nothing at all; it no longer pins what a generic planning query SHOULD do (e.g. no-match or an unguarded skill). `test_keyword_routing_fallback` retarget is faithful (preserves the original long-query-still-matches intent on an unguarded candidate).
- tests/cli/test_route_commands.py:287-293 — squad rendering assertion is a loose OR-chain ("Agent Squad" or "Squad" or "🔍 Semantic Analysis"); the data flow is real (OrchestrationResult → _extract_squad_from_result → _format_squad_summary), so squad rendering is pinned, but the fallback term could mask a squad-rendering regression.
NOTES:
- planning-scenario removal: no dangling references. Grep across src/core/tests/docs/.vibe finds no routing reference to the removed `planning` scenario id; the "planning" string elsewhere (clustering.py, understander.py, context.py, featured_registry.py tags) is a generic task-category label, unrelated.
- Overfit: none in production code. The eval queries (「帮我先关闭了」, 「使用合适的 workflow…」) appear only as regression fixtures in tests — standard practice. The guard rules ("riper" token, 「离开了」 trigger) are generic.
- Track A is faithful: the seams patch the IntentInterceptor/AgentRuntime/UnifiedRouter construction boundary; the CLI body (mode dispatch, OrchestrationResult.to_dict JSON, Rich rendering, squad extraction/formatting, missed-query loop) runs real code against real OrchestrationResult objects. Only the routing DECISION is mocked, which is the correct seam (routing logic is covered by the unit suites). `test_route_multi_agent_squad_query_renders_squad` still pins squad rendering.
- The "zero regressions / 67/107" eval claim was not independently re-run (harness loads the HF embedding model); the routing unit suite (663 passed) and the code-level consistency with the claimed mechanism are the evidence here.
- The `.pi/skills/builtin-session-end/SKILL.md` path requested in the prompt does not exist (`.pi/skills/` is empty); reviewed against the closest equivalent `.vibe/dist/claude-code/skills/builtin-session-end/SKILL.md` and the source `core/skills/session-end/SKILL.md`. Its instructions concern session-lifecycle wrap-up and don't override this review's read-only mandate.
```
