# Project Context

## Session Handoff

<!-- handoff:start -->

### 2026-06-14 (S27) doc-hygiene-and-interceptor-hardening (v7.0.4)
**Session**: Phase 4 from S23 Multi-Agent Squad remediation plan.
**Completed**:
- `README.zh-CN.md` — top-of-file deprecation banner. Lists the 4-major-version gap (last update v5.3.0, current v7.0.3), specific drift items (CLI ~70% missing, platform list wrong, config format wrong, zero v7.0+ security feature coverage), points to README.md as single source of truth, announces v7.1.0 deletion.
- `tests/agent/runtime/test_intent_interceptor_hardening.py` (NEW) — 20 tests across 4 suites:
  - TestExtractExplicitSkillChineseHardening (5): S21 regression pin for the `isascii()` guard. Includes the actual customer-reported case `"用 高可用 的方式实现微服务"` that the S21 fix addressed.
  - TestDetectRolesContract (6): direct unit tests for `_detect_roles` covering dedup, case-insensitivity, and dict-iteration order contract.
  - TestQuickSquadProtocolPriority (7): protocol inference priority (red_team > review_gate > debate > parallel > sequential) plus per_agent_skills + handoff_points shape.
  - TestShouldInterceptEndToEndWithHardening (2): end-to-end smoke tests confirming hardened paths still flow.
- `CHANGELOG.md` — v7.0.4 section.
**Verification**: 20/20 new tests pass; 209/209 tests in tests/agent/runtime + tests/core/routing pass; S21 customer case `"用 高可用"` pinned at both unit and end-to-end levels.
**Next**: Phase 5 (path_safety symlink/TOCTOU hardening) is the last remaining item from the S23 squad plan.

### 2026-06-14 (S26) routing-context-first-class-fields (v7.0.3)
**Session**: P1 fix from S23 Multi-Agent Squad deep analysis (implementer technical-debt #1).
**Trigger**: S23 implementer flagged `_interception_mode` and `intent_analysis` riding RoutingContext.metadata backchannel — fragile, type-unsafe, dead-code field already existed for one of them.
**Completed**:
- `src/vibesop/core/matching/base.py` — `RoutingContext` gains first-class field `intent_analysis: dict[str, Any] | None = None`. Updated docstring to explain field-first / metadata-fallback policy and the deprecation plan. `to_dict()` now serializes `intent_analysis`.
- `src/vibesop/core/routing/orchestrator.py:202-216` — reader now consults `context.interception_mode` field first, falls back to `context.metadata["_interception_mode"]` only when the field is absent. Same policy for `intent_analysis`.
- `src/vibesop/agent/runtime/agent_runtime.py:382-389` — MULTI_AGENT_SQUAD branch now sets `squad_ctx.interception_mode` and `squad_ctx.intent_analysis` as fields, while keeping the metadata backchannel write for backward compatibility.
- `src/vibesop/cli/main.py:223-249` — `_build_single_agent_context` and `_build_multi_agent_squad_context` follow the same dual-write policy.
- `tests/core/routing/test_routing_context_interception_mode.py` (NEW) — 11 tests across 3 suites pinning the new contract.
- `CHANGELOG.md` — v7.0.3 section with migration plan (v7.1 removes backchannel).
**Verification**: 11/11 new tests pass; 885/885 tests in tests/core/routing + tests/core/orchestration + tests/agent + tests/hooks + tests/installer + tests/security + tests/adapters pass; basedpyright 0 new errors on touched files (pre-existing `original_query` argument warning at orchestrator.py:277 is line-shifted from :269, not introduced by this change — verified via `git stash`).
**Next**: Phase 4 (README.zh-CN.md deprecation + intent_interceptor tests) and Phase 5 (path_safety symlink/TOCTOU) remain pending from S23 squad plan.

### 2026-06-14 (S25) jinja2-shell-python-injection-hardening (v7.0.2)
**Session**: Second P0/P1 fix from S23 Multi-Agent Squad deep analysis.
**Trigger**: S23 red-team flagged that `vibesop-route.sh.j2` rendered `{{ platform }}` into a Python single-quoted string literal inside `python3 -c "..."` — a Python code injection vector (not shell injection).
**Completed**:
- `src/vibesop/utils/jinja_safety.py` (NEW) — centralized helper exposing 4 filters (`pyquote`, `shellquote`, `shellvar`, `safe_text`) plus `make_shell_safe_env(**kwargs)` factory that registers all filters + a `None→""` finalize hook.
  - `pyquote`: escapes `\\` and `'`; rejects newline/CR/NUL with `ValueError` (would break out of single-line Python literal).
  - `safe_text`: strips `; & | $ \` " < >` and control chars; keeps spaces, dots, `~`, `#` for readability in comments.
- 9 Environment instantiations switched to `make_shell_safe_env`:
  - `hooks/installer.py`, `hooks/base.py`
  - `adapters/_shared.py` (route hook + SKILL.md renderers), `adapters/hook_based.py`, `adapters/sdk_based.py`
  - `builder/dynamic_renderer.py`
  - `builder/docs.py` left untouched (Markdown-only, no shell surface).
- Template hardening:
  - `vibesop-route.sh.j2`: `{{ platform }}|pyquote` and `{{ hook_event_name }}|pyquote` (Python literal context); `{{ platform_name }}|safe_text`, `{{ purpose }}|safe_text`, `{{ version }}|safe_text` (comment header).
  - `pre-tool-use.sh.j2`, `pre-session-end.sh.j2`, `post-session-start.sh.j2`: all `{{ platform }}` and `{{ hook_point }}` use `|safe_text` (comment + double-quoted echo args).
  - `vibesop-track.sh.j2`: `{{ version }}|safe_text`.
- `tests/hooks/test_shell_injection.py` (NEW) — 28 tests across 6 suites (TestPyquoteFilter, TestShellquoteFilter, TestShellvarFilter, TestSafeTextFilter, TestMakeShellSafeEnv, TestRouteHookTemplateInjection) including the PoC verification that `'claude'; __import__('os').system('pwned'); x='` no longer injects.
- `CHANGELOG.md` — v7.0.2 section.
**Verification**: 520/520 tests in tests/hooks + tests/installer + tests/security + tests/adapters + tests/builder pass; basedpyright 0 errors on all touched files; classic Python injection PoC verified neutralized.
**Next**: Phase 3 (`_interception_mode` → RoutingContext first-class field) and Phase 4 (README.zh-CN.md deprecation + intent_interceptor tests) remain pending from the S23 squad plan.

### 2026-06-14 (S24) pack-install-security-ordering-fix (v7.0.1)
**Session**: P0 RCE fix from Multi-Agent Squad deep analysis (S23 → S24).
**Trigger**: S23 squad red-team flagged `PackInstaller._run_post_install` running BUILD.sh with local privileges BEFORE `SkillSecurityAuditor` ever saw the file.
**Completed**:
- `src/vibesop/security/skill_auditor.py` — added `PackAuditResult` dataclass, `SHELL_THREAT_PATTERNS` (5 patterns: curl|sh, reverse shell, process substitution, SSH authorized_keys, cron/launch agent), `JS_THREAT_PATTERNS` (2 patterns: eval(remote), child_process), `PACK_FILE_SIZE_LIMIT=1MiB`, `PACK_AUDITED_EXTENSIONS` frozenset, and `audit_pack_files(pack_dir, pack_name)` method scanning all .sh/.bash/.js/.mjs/.cjs/.py/.md/.yaml/.yml/.json files. CRITICAL never downgraded; HIGH downgrades only for trusted packs.
- `src/vibesop/installer/pack_installer.py` — `PackInstaller.__init__` gains `sandbox_builds=True` + `allow_unsafe_build=False` flags. `install_pack` reordered: pre-audit → reject CRITICAL or untrusted+HIGH → `_run_post_install(sandbox=...)` → existing post-install SKILL.md audit. `_run_post_install` split into `_detect_container_runtime` / `_run_build_in_container` (`--network=none --memory=512m --cpus=0.5`, read-only mount) / `_run_build_local` (legacy fallback). `_build_install_msg` shows pre-audit summary.
- `tests/installer/test_pack_install_order.py` (NEW) — 13 tests: TestPreInstallAuditGate, TestSandboxedBuild (3 tests), TestPackAuditResult (4 tests), TestAuditPackFiles (4 tests: curl|sh detection, clean pack pass, oversized file skip, JS eval remote detection).
- `tests/installer/test_pack_installer.py` — updated 3 existing tests to mock `audit_pack_files` with `_clean_pack_audit()` helper; added `sandbox_builds=False, allow_unsafe_build=True` to BUILD.sh tests to preserve original semantics.
- `CHANGELOG.md` — v7.0.1 section with full background, threat model, fix description, verification matrix.
**Verification**: 13/13 new tests pass; 228/228 tests/installer + tests/security pass; basedpyright 0 new errors on touched files; 9 unrelated failures (tests/{integration,integrations,core/skills}) confirmed via `git stash` to pre-exist on main.
**Next**: Phase 2 (jinja hooks `autoescape`/`shlex.quote` hardening) and Phase 3 (`_interception_mode` → RoutingContext first-class field) from the S23 squad plan remain pending.

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
