# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-05-17 16:00
**Session**: Test coverage improvement — 172 new tests + config fix + adapter refactor + push

**Completed**:
- Fixed `config_manager._load_skill_config_file()` cross-format TOML loading bug (isinstance guard)
- Fixed Kimi CLI E2E tests for slim AGENTS.md format
- 172 new tests: instinct learner (36), skills loader (47 new file), external_loader (25), storage (9), matching strategies (55 new file)
- Adapter refactoring: slim AGENTS.md index, routing-protocol/session-lifecycle migrated to docs/
- Coverage: 72.61 → 73.75%, 2647 → 2766 passing tests
- Committed + pushed: `335c082`

**Key Learnings**:
- `SkillMetadata` requires `intent` as positional arg (not defaulted) — test instantiations need all 4 required fields
- `PromptSkill._prompt_template` is private (underscore prefix)
- `SkillLoader` coverage went from 0 tests to 47 tests — most impactful new file

**Files Modified**:
- `src/vibesop/core/skills/config_manager.py`
- `tests/core/skills/test_loader.py` (new)
- `tests/core/matching/test_strategies.py` (new)
- `tests/core/skills/test_external_loader.py`
- `tests/core/skills/test_skill_storage.py`
- `tests/core/test_instinct_learner.py`
- `tests/e2e/test_agent_runtime.py`
- Adapter files: `_shared.py`, `claude_code.py`, `kimi_cli.py`, `opencode.py`, templates

**Next Steps**: Phase 3 complete; next session could target integration/e2e tests or remaining low-coverage modules

---

### 2026-05-15 15:30
**Session**: Fix `vibe skills list` + PyPI release v5.4.5

**Completed**:
- Diagnosed `SkillStorage.list_skills()` bug: non-recursive + manifest-dependent, missing pack skills
- Fix: resolve platform symlinks backwards to discover pack-installed skills
- `vibe skills list`: 13 → 209 skills
- All 46 related tests pass
- Version bump: 5.4.4 → 5.4.5, pushed tag v5.4.5 for PyPI release via GitHub Actions OIDC

**Key Learnings**:
- Two divergent skill discovery mechanisms in same codebase: `SkillStorage.list_skills()` (manifest-based, non-recursive) vs `SkillLoader` (recursive rglob)
- Pack skills have varying directory structures: gstack flat, omx/superpowers nested under `skills/`

**Files Modified**:
- `src/vibesop/core/skills/storage.py`

**Next Steps**: Monitor CI for v5.4.5 PyPI publish
<!-- handoff:end -->
