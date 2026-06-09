# Overview - VibeSOP Project

**Last Updated**: 2026-06-05 (v6.2.0 — Dynamic Workflow Engine + doc sync)

---

## Goals

### Previous Week (May 24-30, 2026) — Completed

1. **4-Phase Transformation** ✅ (Completed - May 29)
   - Phase 1: Spec v3.0 (SkillSpec Pydantic model, SpecValidator, SkillType.STANDARD)
   - Phase 2: Reference (3 base classes: FileBased/HookBased/SdkBased, shared templates)
   - Phase 3: Wire (AgentRuntime wiring, shell hook elimination 221→22 lines, HookPoint.ROUTE_INTERCEPTOR)
   - Phase 4: Conformance Suite (85 tests, dead code removal, SKILL.md template unification, Pi→SdkBasedAdapter)
2. **Audit Optimization** ✅ (Completed - May 29)
   - SKILL.md template unified across all adapters
   - Pi adapter inherits from SdkBasedAdapter (~30 lines removed)
   - Shell hook template 53→22 lines

### Previous Week (April 21-22, 2026) — Completed

1. **Lint Sweep** ✅ (Completed - April 22)
2. **Badge System MVP** ✅ (Completed - April 22)
3. **UnifiedRouter Refactoring** ✅ (Completed - April 22)
4. **v4.3 Multi-Turn Support** ✅ (Completed - April 22)
5. **v4.3 Context-Aware Routing** ✅ (Completed - April 22)
6. **Custom Matchers Plugin System** ✅ (Completed - April 22)
7. **A/B Testing Framework** ✅ (Completed - April 22)
8. **Fix Flaky Tests + v4.3.0 Release** ✅ (Completed - April 22)

### Previous Week (April 23-30, 2026) — Completed

1. **Agent Runtime Layer** ✅ (Completed - April 23)
2. **v4.4 Platform Adaptation** ✅ (Completed)
3. **Code Review Defect Fixes** ✅ (Completed - April 27)
4. **CLI `vibe build --platform=all`** ✅ (Completed)

### Previous Week (May 1-3, 2026) — Completed

1. **Test Coverage Backfill** ✅ (Completed - May 3)
2. **Documentation YAML→TOML Migration** ✅ (Completed - May 3)
3. **Agent Override Protocol Cross-Platform Sync** ✅ (Completed - May 3)

### Current Week (May 4-10, 2026)

1. **Vibe Coding Article Revision** ✅ (Completed - May 5)
   - Added "Core Problems + Survival Principles" overview chapter to docs/vibe-coding-article.md
   - Structured as: answers first → story second → methodology third

2. **Routing Quality Improvements** ✅ (Completed - May 5)
   - Candidate deduplication by canonical ID
   - Management-only skill tagging (slash-* prefix exclusion from semantic matching)
   - Triage prompt v3 with office-hours/plan routing rules
   - Committed and pushed: `2380ec2`

---

## Projects Summary

### VibeSOP (vibesop-py)
**Status**: v7.0.0-dev (Dynamic Workflow Engine + Prompt Chain: 7 patterns, 4 platforms)
**Description**: AI SkillOS — skill protocol standard with Dynamic Workflow Engine, 3-pillar architecture, 4-platform support
**Coverage**: 2968+ tests passing
**Key Metrics**:
- Routing accuracy: 94%
- Performance: 44 QPS (target: 40+ QPS)
- Skills supported: 207 skills across 4 packs
- Total tests: 2968 passed
- Workflow patterns: 6 (SEQUENTIAL, PARALLEL, FAN_OUT, ADVERSARIAL, LOOP_UNTIL_DRY, TOURNAMENT)
- Platforms: Claude Code, Kimi CLI, Pi Agent, OpenCode

**Recent Changes** (2026-06-05):
- ✅ Version bumped 5.5.0 → 6.2.0, 29 files synced
- ✅ Dynamic Workflow Engine documentation (ARCHITECTURE.md, README.md, templates)
- ✅ Platform compatibility matrix documented (native sub-agent vs serial)
- ✅ Adapter templates updated with Workflow Patterns sections
- ✅ Fixed hook template test assertions and _Skill.get() AttributeError
- ✅ Commit: b6daa4d on refactor/router-orchestrator-split
- ✅ Phase 4 complete: conformance suite (85 tests), dead code removal, README sync
- ✅ SKILL.md template unification (shared template + render_skill_md function)
- ✅ Pi adapter inherits SdkBasedAdapter (~30 lines duplicated code removed)
- ✅ Shell hook template optimized 53→22 lines
- ✅ Version bumped 5.4.6→5.5.0, pyproject.toml + CHANGELOG updated

**Recent Changes** (2026-04-27):
- ✅ 9 P0/P1 routing/feedback defects fixed (IndexError, Chinese bypass, ConfigSource, etc.)
- ✅ Context-aware optimization now works for all routing layers
- ✅ Matcher prefilter warmup re-activated
- ✅ Scope defaults corrected (project→global) for builtin skills

**Recent Changes** (2026-04-23):
- ✅ Agent Runtime layer: IntentInterceptor + SkillInjector + DecisionPresenter + PlanExecutor
- ✅ Platform adaptation: Claude Code (hooks), Kimi CLI (AGENTS.md), OpenCode (plugin template)
- ✅ E2E validation: 13 tests covering full chain + platform artifacts + cross-platform consistency

**Recent Changes** (2026-04-21):
- ✅ Code review optimization plan: P0-1/P0-2/P0-3/H1/H4/M3/M4 all complete
- ✅ 27 bare `except Exception` narrowed to specific types
- ✅ `LayerResult` unified to Pydantic BaseModel
- ✅ Duplicate `RoutingConfig` resolved (adapters → `RoutingPolicy`)
- ✅ `UnifiedRouter` supports `skill_loader` injection
- ✅ `fallback_mode`/`default_strategy` now Literal-validated
- ✅ `_edit_execution_plan` empty plan guard added
- ✅ `_handle_single_result` split from 213 lines to 6 focused functions

**Recent Changes** (2026-04-21):
- ✅ Architecture review with professional assessment
- ✅ Document version sync (PHILOSOPHY/ARCHITECTURE/ROADMAP/PROJECT_STATUS → 4.2.0)
- ✅ UnifiedRouter extracted RouterStatsMixin (-49 lines)
- ✅ pytest-xdist parallel testing (make test-fast ~39s)
- ✅ Fixed 3 pre-existing test failures
- ✅ Eliminated test warnings, fixed ruff issues
- ✅ Added TECH DEBT annotations for known issues

**Recent Changes** (2026-04-20):
- ✅ Implemented skill-level LLM configuration system
- ✅ Created `SkillConfigManager` with CRUD operations
- ✅ Added CLI commands for config management
- ✅ Integrated auto-configuration with skill install
- ✅ Fixed dataclass bug in understander.py
- ✅ Improved keyword extraction (added stop words)
- ✅ All tests passing (1000+ lines of new code, fully tested)

**Next Steps**:
- Restore coverage threshold to 75%+ after verifying new test coverage impact
- Continue backfill: builder/*, hooks/*, adapters/* remaining blind spots
- Use new `skill_loader` injection to unify SkillManager/UnifiedRouter loader paths
- Consider Builder pattern for UnifiedRouter __init__ (~110 lines)
- Version bump automation (avoid future doc version drift)

---

### Kimi CLI Integration
**Status**: Active
**Description**: VibeSOP configuration adapter for Kimi Code CLI
**Provider**: Moonshot (Kimi)
**Recent Changes**:
- Fixed configuration fragment generation
- Corrected provider value to 'moonshot'
- Resolved vibe doctor issues

---

## Quick Reference

### Development Commands
```bash
# Type checking
uv run basedpyright

# Linting
uv run ruff check

# Testing
uv run pytest

# Test coverage
uv run pytest --cov=src/vibesop --cov-report=html

# Run specific test
uv run pytest tests/path/to/test.py
```

### Key Files
- **Router**: `src/vibesop/core/routing/unified.py`
- **Skill Loader**: `src/vibesop/core/skills/loader.py`
- **Security**: `src/vibesop/security/skill_auditor.py`
- **Tests**: `tests/integration/test_external_skill_execution.py`

### Important Paths
- **Memory**: `memory/` (session.md, project-knowledge.md, overview.md)
- **Session State**: `.vibe/state/sessions/`
- **Configuration**: `.vibe/config.yaml`
