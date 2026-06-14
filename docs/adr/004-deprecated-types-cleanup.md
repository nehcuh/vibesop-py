# ADR-004: Deprecated Skill Metadata Types Cleanup

> **Date**: 2026-06-14
> **Status**: Proposed (tracking v7.1-v7.3 migration)
> **Context**: VibeSOP currently maintains **four parallel skill metadata
> models** — `vibesop.spec.SkillSpec` (the v5.5.0 canonical source of
> truth) plus three deprecated predecessors that are still on hot
> production paths:
> - `core.skills.base.SkillMetadata`
> - `core.skills.config_manager.SkillConfig`
> - `core.models.SkillDefinition` (Pydantic v2 variant)
>
> The deprecation comments all promise "removed in v6.0"; current
> version is v7.0.12. Two major-version windows have passed without
> the cleanup landing. The S23 + S29 architect reports both flagged
> this as the #1 architectural debt.

## Decision

Adopt a **3-release phased migration** (v7.1 / v7.2 / v7.3) that
removes one deprecated type per release, with each release independently
revertible if a missed call site surfaces. The order is chosen by call
site count (smallest blast radius first).

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

### Phase 2 — v7.2: Remove `core.skills.config_manager.SkillConfig`

**Blast radius**: 5 import sites
(`feedback_loop.py:17`, `retention.py:166`, `evaluator.py:176`,
`routing/candidate_manager.py:260`, 5 CLI command modules).

**Why second**: Larger blast radius but confined to the skills
subsystem. Tests already cover the wrapping `SkillConfigManager`.

**Migration approach**: Replace each `SkillConfig` instance with
`SkillSpec`, since `SkillSpec` already has the same fields plus extras.
`SkillConfigManager` becomes a thin compatibility shim that returns
`SkillSpec` objects.

**Acceptance gate**: `grep -rn "SkillConfig\b" src/` returns 0 hits.

### Phase 3 — v7.3: Remove `core.skills.base.SkillMetadata`

**Blast radius**: largest — `parser.build_metadata()` is called from
`loader.py:330, 370, 408` (3 hot-path sites) plus 6 import sites.

**Why last**: SkillMetadata is the dataclass form that parser/loader
use directly; replacing it touches the most production code.

**Migration approach**:
1. v7.3.0: Change `parse_skill_md()` return type to `SkillSpec`.
2. v7.3.0: Update `loader.py` 3 sites to consume `SkillSpec`.
3. v7.3.1: Remove `SkillMetadata` class + `build_metadata()`.
4. v7.3.2: Remove the runtime `DeprecationWarning` (no longer needed).

**Acceptance gate**: `grep -rn "SkillMetadata\b" src/` returns 0 hits;
no `DeprecationWarning` for SkillMetadata appears in test output.

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

- [x] v7.1: Phase 1 (SkillDefinition removal) — shipped 2026-06-14
- [ ] v7.2: Phase 2 (SkillConfig removal) — issue TBD
- [ ] v7.3: Phase 3 (SkillMetadata removal) — issue TBD

Each phase requires its own pre-implementation plan per ADR-003
(Plan Completion Criteria).
