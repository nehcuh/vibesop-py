# ADR-004: Deprecated Skill Metadata Types Cleanup

> **Date**: 2026-06-14
> **Status**: Phase 1 ✅ shipped (v7.1.0). Phase 2 ❌ withdrawn after architect review. Phase 3 ✅ shipped (v7.3.0).
> **Context**: VibeSOP currently maintains **four parallel skill metadata
> models** — `vibesop.spec.SkillSpec` (the v5.5.0 canonical source of
> truth) plus three deprecated predecessors that are still on hot
> production paths:
> - `core.skills.base.SkillMetadata`
> - `core.skills.config_manager.SkillConfig` — **undeprecated 2026-06-14**: see Phase 2 withdrawal below.
> - `core.models.SkillDefinition` (Pydantic v2 variant) — ✅ removed v7.1.0
>
> The deprecation comments all promise "removed in v6.0"; current
> version is v7.0.12. Two major-version windows have passed without
> the cleanup landing. The S23 + S29 architect reports both flagged
> this as the #1 architectural debt.

## Decision

Adopt a **phased migration** that removes genuinely-redundant deprecated
types, with each release independently revertible if a missed call site
surfaces. The order is chosen by call-site count (smallest blast radius
first). **Phase 2 was withdrawn after architect review determined
`SkillConfig` is not actually redundant with `SkillSpec` — see below.**

### Phase 1 — v7.1: Remove `core.models.SkillDefinition` ✅ SHIPPED

**Actual blast radius** (originally claimed "3 import sites"):
- `src/`: 5 modules, ~14 sites (`adapters/models.py`, `builder/{manifest,overlay,renderer}.py`, `core/models.py` SkillRegistry)
- `tests/`: 6 files, ~25 sites (conftest + 4 adapter tests + perf test + e2e test)
- **Hidden re-export**: `vibesop/__init__.py:55` exports `SkillRegistry` which embeds `dict[str, SkillDefinition]`

**Why first**: Pydantic v2 variant has the fewest production references
and is the easiest to mechanically translate to `SkillSpec` (both are
Pydantic models, just different field sets).

**Migration** (shipped in v7.1.0):
```python
# Before
from vibesop.core.models import SkillDefinition
sd = SkillDefinition(id="x", ...)

# After — direct class substitution, no factory method needed
from vibesop.spec import SkillSpec
sd = SkillSpec(id="x", ...)
```

`SkillSpec` is a strict superset of `SkillDefinition`'s fields and uses
`populate_by_name=True`, so the `model_dump()` → `SkillSpec(**dumped)`
round-trip in `OverlayMerger._dict_to_manifest()` works without a
`from_legacy_dict()` factory (the original ADR draft referenced one
that does not exist on `SkillSpec`).

**Acceptance gate**: ✅ `grep -rn "SkillDefinition" src/` returns 0 hits
(remaining matches are docstrings referencing the historical name).

### Phase 2 — v7.2: ~~Remove `core.skills.config_manager.SkillConfig`~~ WITHDRAWN

**Original plan**: Replace `SkillConfig` with `SkillSpec`, claiming
"SkillSpec already has the same fields plus extras."

**Withdrawal rationale** (2026-06-14 architect review): The premise
that `SkillSpec` is a strict superset of `SkillConfig` is **factually
wrong**. `SkillConfig` has 5 fields with no `SkillSpec` equivalent:

| SkillConfig field | Read by | Purpose |
|---|---|---|
| `usage_stats: dict[str, Any]` | `loader.py:135`, `candidate_manager.py:292`, `evaluator.py:179` | Runtime usage state (last_used, route counts); persisted to `.vibe/skills/auto-config.yaml` |
| `evaluation_context: dict[str, Any]` | `loader.py:154`, `cli/commands/skills_commands/_config.py:108,125` | Project-scope isolation (project_hash) |
| `version_history: list[dict]` | (none) | Write-only at config-save sites; future read site |
| `requires_llm: bool` | `config_manager.py:105` | Gate on skill-level LLM config |
| `llm_provider`/`llm_model`/`llm_temperature`/`llm_api_key`/`llm_api_base` | `config_manager.py:109-113` | Individual LLM fields (SkillSpec nests these in `llm_config: LLMConfigSpec`) |

**Architectural correction**: `SkillSpec` and `SkillConfig` serve
**different concerns**:
- `SkillSpec`: Immutable spec — loaded from SKILL.md frontmatter at startup. Describes *what a skill is*.
- `SkillConfig`: Runtime persistence — written by `SkillConfigManager` to `.vibe/skills/auto-config.yaml`. Tracks *how a skill is configured at runtime* (usage state, project scope, LLM choice).

Forcing SkillConfig into SkillSpec (or its `metadata` dict) would either
pollute the spec layer with mutable runtime state, or break 6 read
sites + 4 test assertions for zero spec-coherence gain.

**Action**: Undeprecate `SkillConfig` (remove `.. deprecated:: 5.5.0`
from its docstring). Update docstring to state the spec/persistence
split explicitly. Phase 2 is dropped from the cleanup roadmap.

### Phase 3 — v7.3: Remove `core.skills.base.SkillMetadata`

**Blast radius**: largest — `parser.build_metadata()` is called from
### Phase 3 — v7.3: Remove `core.skills.base.SkillMetadata` ✅ SHIPPED

**Actual blast radius** (largest of the three phases):
- `src/`: 6 modules, ~14 sites
  - `core/skills/parser.py`: `parse_skill_md()` return type → SkillSpec; `build_metadata()` is now a thin alias for `build_spec()`; `SkillParser` return types updated; `__all__` updated
  - `core/skills/base.py`: deleted `SkillMetadata` class (55 LOC) + local `SkillType` enum; `Skill`/`PromptSkill`/`WorkflowSkill.__init__` metadata param now typed `SkillSpec`
  - `core/skills/loader.py`: `LoadedSkill.metadata: SkillSpec`; `_convert_external_skill` simplified (was 30 LOC manual field copy, now `model_copy(update={...})`); imports local SkillType replaced with spec SkillType
  - `core/skills/understander.py`: 6 SkillMetadata param hints → SkillSpec; SkillType import from spec
  - `core/skills/external_loader.py`: `ExternalSkillMetadata.base_metadata: SkillSpec` (real import, not TYPE_CHECKING)
  - `core/skills/__init__.py`: removed SkillMetadata + SkillType from `__all__`
  - `cli/commands/skill_commands.py`: CLI fallback construction uses SkillSpec
- `tests/`: 8 files, ~30 sites
- Bonus fixes (bugs exposed by SkillSpec.intent being `Optional[str]` whereas
  SkillMetadata.intent was required `str`): `.get("intent", "")` patterns
  in `optimization/clustering.py`, `skills/manager.py`, `config/manager.py`,
  `routing/unified.py` changed to `.get("intent") or ""` to handle None.

**Why last**: SkillMetadata is the dataclass form that parser/loader
use directly; replacing it touches the most production code.

**Migration approach** (shipped in v7.3.0, single release):
1. `parse_skill_md()` returns SkillSpec directly (was: returned SkillMetadata built via `build_metadata()`)
2. `build_metadata()` kept as a thin deprecated alias for `build_spec()` (callers transition gradually)
3. `SkillMetadata` class + local `SkillType` enum deleted
4. `DeprecationWarning` for SkillMetadata is gone (no class to warn about)

**Acceptance gate**: ✅ `grep -rn "SkillMetadata\b" src/` returns 0 hits
(remaining matches are docstrings referencing the historical name).
No `DeprecationWarning` for SkillMetadata appears in test output.

## Alternatives Considered

### A. One-shot big-bang migration (single PR)

**Rejected**: 14 import sites + 3 hot-path call sites + tests = ~2000
LOC change. PR review burden too high; revertibility poor if a missed
edge case surfaces in production.

### B. Keep all four types indefinitely

**Rejected**: Each new field added to `SkillSpec` requires a parallel
field in the legacy types, or the legacy types silently lag. This is
exactly the schema-drift pattern that bit `ExecutionPlan` (fixed in
v7.0.10 — see commit d81d0b4).

### C. Auto-generate legacy types from SkillSpec via Pydantic

**Rejected**: Three of the four types are dataclasses (not Pydantic
models), so generation would require type-system unification first.
More work than direct migration.

## Risks

1. **Hidden dynamic imports**: `importlib.import_module` callers might
   reference the deprecated names. Mitigation: grep -r includes
   `getattr(...)` patterns; CI test gate.
2. **Plugin / external skill packs** that import the deprecated types
   will break. Mitigation: v7.1-v7.3 release notes carry migration
   guide; bump major version only at v7.3 (the final removal).
3. **Test fixtures** may construct `SkillMetadata(...)` directly.
   Mitigation: each phase updates tests in the same commit.

## Consequences

- Three minor releases ship type-removal work; each is independently
  revertible.
- `spec/__init__.py:8-14` deprecation notice ("removed in v6.0") is
  updated per phase to reflect actual removal version.
- Once Phase 3 lands, `core.skills.base` shrinks by ~80 LOC and
  `parser.build_metadata()` (deprecated since v5.5.0) is finally gone.
- The S23 + S29 architect reports' #1 architectural debt is closed.

## Tracking

- [x] v7.1: Phase 1 (SkillDefinition removal) — shipped 2026-06-14 (commit 3f90c9b)
- [~] v7.2: Phase 2 (SkillConfig removal) — **WITHDRAWN** 2026-06-14 after architect review (spec/persistence split)
- [x] v7.3: Phase 3 (SkillMetadata removal) — shipped 2026-06-14

Each phase requires its own pre-implementation plan per ADR-003
(Plan Completion Criteria).
