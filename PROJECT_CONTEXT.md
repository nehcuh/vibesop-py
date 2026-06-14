# Project Context

## Session Handoff

<!-- handoff:start -->

### 2026-06-14 (S23) prompt-chain-validator-skill-integration
**Session**: Packaged the dynamic-workflow + container-validation pattern as a reusable cross-cutting skill + CLI.
**Completed**:
- `.vibe/skills/cross-cutting/prompt-chain-validator.skill/SKILL.md` — type: cross-cutting, 4 depends_on, 4 steps; auto-discovered by `vibe workflows list-workflows`.
- `src/vibesop/core/prompt_chain/{__init__,generator,validator}.py` — `PromptChainGenerator` (Phase 0 glob fan-out + Phase 1-6 markdown rendering, ASCII slug with `phase-N` fallback for Chinese titles) + `ContainerValidator` (orbstack→docker→lima→local runtime detection, 5-bucket pipeline: imports / unit_tests / cli_modes / hook_path / build, JSON report).
- `src/vibesop/cli/commands/prompt_chain_cmd.py` + registration in `cli/main.py` and `cli/commands/__init__.py` — `vibe prompt-chain {diagnose,generate,validate,run}`.
- `tests/core/prompt_chain/` — 28 tests (slug rules, glob expansion, 7-file generation, ASCII filename guarantee, runtime detection mocks, report serialization, local-mode validate).
**Verification**: 28/28 prompt_chain tests; 1867 passed total; basedpyright 0 errors on new modules; `vibe workflows list-workflows` lists the new skill.
**Next**: README + ROADMAP + ARCHITECTURE docs to surface the new CLI.

### 2026-06-14 (S22) prompt-injection-path-traversal-hardening
**Session**: Pure security hardening — no business logic change.
**Completed**:
- `semantic_intent_analyzer.py:_escape_query` — added C0 control char filter (regex `[\x00-\x08\x0b\x0c\x0d\x0e-\x1f]`, preserves `\n` `\t`); `</` replacement applied twice to defeat `<</` reassembly; prompt trailer gains JSON fallback directive for unparseable input.
- `prompt_chain_generator.py:write_files` — NUL byte early reject; `startswith` check now uses `os.sep`-suffixed prefix to defeat `/tmp/foo` vs `/tmp/foobar` prefix collision.
- Tests: `TestEscapeQuery` (7 cases) + `TestWriteFiles` traversal/NUL/prefix-collision (3 cases).
**Verification**: 139 security-related tests pass; full regression 1840 passed (3 pre-existing skills failures unrelated, verified via `git stash`).
**Next**: Promote to v7.0 in CHANGELOG.

### 2026-06-14 (S21) multi-agent-squad-auto-trigger
**Session**: Closed the gap between IntentInterceptor's `MULTI_AGENT_SQUAD` decision and PlanBuilder's squad branch.
**Completed**:
- `intent_interceptor.py` — `ROLE_KEYWORDS` dictionary + `_detect_roles()` + `_build_quick_squad_analysis()`; ≥2 distinct roles short-circuits to `MULTI_AGENT_SQUAD` without LLM. `_extract_explicit_skill` rejects non-ASCII captures (fixes "高可用" hijacking the "用 X" pattern).
- `agent/__init__.py` — `AgentRouter.orchestrate(query, callbacks, context)` accepts routing context; `build_plan` picks `AGENT_SQUAD`/`DEBATE`/`RED_TEAM` workflow pattern from `collaboration_protocol`.
- `agent_runtime.py:handle_query` — `MULTI_AGENT_SQUAD` now flows through orchestrate (was: single-route); `has_match` accepts `multi_agent_squad` mode.
- `routing/orchestrator.py` — reads `context.metadata["intent_analysis"]` and forces squad pattern when `_interception_mode=multi_agent_squad` (was: silently dropped context).
- `skill_composer.py` — `ROLE_DEFAULT_SKILLS` + public `infer_skills_for_role()`.
- `semantic_intent_analyzer.py` — LLM prompt rewritten with explicit role-keyword matrix + 4 worked examples.
**Verification**: 588 tests pass (+10 new). Container e2e: A4 "设计架构、实现、安全审查" now renders full squad summary (架构师/实现者/审查者/红队 + red_team protocol + 4-step plan); hook returns full plan JSON.
**Next**: Hook path still drops analysis in some flows — confirmed via S20.

### 2026-06-14 (S20) hook-path-p0-fix
**Session**: End-to-end verification revealed 2 P0 bugs blocking the hook path; fixed both.
**Completed**:
- `agent/__init__.py` — `AgentRouter.orchestrate` signature gains `callbacks: Any | None = None` (default None for backward compat). Was: `agent_runtime.py:371` passed `callbacks=` to a signature that didn't accept it, raising TypeError that was swallowed by try/except, causing hook to return "No matching skill" on every orchestrate.
- `adapters/templates/shared/vibesop-route.sh.j2` — `export PATH` adds `~/.local/bin` / `~/.cargo/bin` / `/opt/homebrew/bin` so non-interactive shells find uv; hook walks up from `${BASH_SOURCE[0]}` looking for `pyproject.toml` with `name = "vibesop"`, falling back through `$CLAUDE_PROJECT_DIR` / `$PWD` / `$VIBESOP_PROJECT_ROOT`.
**Verification**: 584 tests pass. Hook from `/tmp` with `PATH=/usr/bin:/bin` now correctly returns `🔀 VibeSOP detected multiple intents. Execution plan injected.` for orchestrate queries.
**Next**: A3/A4 in container still fell through to FALLBACK_LLM — squad path not yet wired (→ S21).

### 2026-06-09 (S19) final-phase-review-branch
**Session**: Added conditional review-task branching to `_generate_final_phase()`
**Completed**:
- models.py: Added `metadata: dict[str, Any]` field to `ExecutionPlan` (+ `to_dict()` serialization) for passing classification context downstream
- prompt_chain_generator.py: `_generate_final_phase()` now checks `plan.metadata.get("review_type") == "multi_dimensional"` — review tasks get red team + cross-dimension validation + scoring + action items; non-review tasks get simple functional verification checklist
- `verification_checklist` also branches: review tasks get 5 items (incl. red team + scoring); non-review gets 3 items (security + compilation + functional)
**Verification**: basedpyright 0 new errors, all changes are purely additive
**Next**: e2e verification with `vibe route` multi-dimensional review query to confirm Final Phase content

### 2026-06-09 (S18) prompt-chain-quality-fix-round-2
**Session**: Fixed 3 remaining PromptChainGenerator quality issues
**Completed**:
- plan_builder.py: `_resolve_step_files()` returns project source dirs as fallback for external skills instead of empty list
- prompt_chain_generator.py: `_generate_key_points()` rewritten to prioritize `step_type` over keyword matching — 6 analysis subcategories
- prompt_chain_generator.py: `_generate_final_phase()` enhanced with red team + scoring + action items
**Verification**: 35/35 prompt_chain tests, 196/196 orchestration tests
**Next**: S19 completed the conditional branching

<!-- handoff:end -->
