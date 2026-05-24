# Overview - VibeSOP Project

**Last Updated**: 2026-05-24 (Pi agent skill conflict cleanup)

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
**Status**: v5.4.1 (Routing refinements + docs)
**Description**: AI SkillOS — full skill lifecycle management (discovery, routing, orchestration, evaluation, retention) with Agent Runtime layer
**Coverage**: TBD — 341 new tests added, threshold temporarily at 0%
**Key Metrics**:
- Routing accuracy: 94%
- Performance: 44 QPS (target: 40+ QPS)
- Skills supported: 91 skills across 4 packs
- Test speed: 39s fast suite / ~4.5min full suite
- Total tests: ~2300+ (including 341 new)

**Recent Changes** (2026-05-05):
- ✅ vibe-coding-article.md: added core problems + survival principles overview
- ✅ Routing: candidate dedup, management-only skill exclusion, triage prompt v3
- ✅ Committed and pushed: `2380ec2`

**Recent Changes** (2026-05-03):
- ✅ 341 new tests added across 24 test files
- ✅ Fixed pytest basename collisions (3 test files renamed)
- ✅ Document YAML→TOML migration complete (15+ files)
- ✅ Session storage path confusion clarified

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
