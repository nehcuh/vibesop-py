# Overview - VibeSOP Project

**Last Updated**: 2026-04-28 (Hook Template Fixes + Slash-Route Architecture)

---

## Goals

### Previous Week (April 21-22, 2026) — Completed

1. **Lint Sweep** ✅ (Completed - April 22)
2. **Badge System MVP** ✅ (Completed - April 22)
3. **UnifiedRouter Refactoring** ✅ (Completed - April 22)
4. **v4.3 Multi-Turn Support** ✅ (Completed - April 22)
5. **v4.3 Context-Aware Routing** ✅ (Completed - April 22)
6. **Custom Matchers Plugin System** ✅ (Completed - April 22)
7. **A/B Testing Framework** ✅ (Completed - April 22)
8. **Fix Flaky Tests + v4.3.0 Release** ✅ (Completed - April 22)

### Current Week (April 23-30, 2026)

1. **Agent Runtime Layer** ✅ (Completed - April 23)
   - 4 core modules: IntentInterceptor, SkillInjector, DecisionPresenter, PlanExecutor
   - 36 unit tests, 13 E2E tests, all passing

2. **v4.4 Platform Adaptation** 🔄 (In Progress)
   - Phase 1-2 complete (core + adapters)

3. **Code Review Defect Fixes** ✅ (Completed - April 27)
   - 9 P0/P1 fixes from KIMI review: IndexError, rejected_candidates mismatch, Chinese AI Triage bypass, ConfigSource sentinel, CLI feedback method, context=None, prefilter warmup, resolve cache, SkillRecommender dedup
   - 218 core tests passing, committed `6c50373`

3. **CLI `vibe build --platform=all`** ⏳ (Pending)
   - Support building all platform configs in one command

---

## Projects Summary

### VibeSOP (vibesop-py)
**Status**: v5.2.0 (Code Review Defects Fixed)
**Description**: AI-assisted development intelligent routing engine with skill-level LLM configuration and Agent Runtime layer
**Coverage**: 75%+ (218+ core routing tests passing)
**Key Metrics**:
- Routing accuracy: 94%
- Performance: 44 QPS (target: 40+ QPS)
- Skills supported: 91 skills across 4 packs
- Test speed: 39s fast suite / ~4.5min full suite

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
- Use new `skill_loader` injection to unify SkillManager/UnifiedRouter loader paths
- Consider Builder pattern for UnifiedRouter __init__ (~110 lines)
- Monitor test suite health (current: 1687 passed)
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
