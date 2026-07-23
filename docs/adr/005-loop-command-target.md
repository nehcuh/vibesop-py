# ADR-005: LoopSpec.command_args as a Flat Fourth Target

> **Date**: 2026-07-23
> **Status**: Proposed — Phase A shipped (`fdafbcb`), Phase D shipped (`3be214d`)
> **Context**: instinct-loop phases A–E

## Context

`LoopSpec` (Phase 1) defined three target types for a scheduled loop:

- `skill_id` — invoke `/slash-route use <skill>` and let routing handle it.
- `query` — invoke `vibe route "<query>"` for raw semantic matching.
- `workflow_id` — invoke a saved workflow.

For the **instinct learning loop** (Phases D–E) we needed to schedule
**internal CLI subcommands** that are not any of the above:

| Preset | Subcommand | Purpose |
|--------|-----------|---------|
| `instinct-assemble` | `vibe sequence assemble` | Fold captured tool calls into sequence-pattern candidates |
| `instinct-promote` | `vibe instinct auto-promote` | Convert high-confidence candidates to persistent instincts |
| `instinct-feedback` | `vibe instinct feedback-collect` | Decay / boost instincts from miss-counter signal |

None of these has a `skill_id`, a routeable `query`, or a workflow id.
The 3-way `skill_id / query / workflow_id` model could not express them.

## Decision

Add **`command_args: list[str]`** as a flat fourth field on `LoopSpec`,
alongside the existing three. Enforce a **4-way xor** validator
(`_exactly_one_target`) so a spec must set exactly one target type.

```python
class LoopSpec(BaseModel):
    skill_id: str = ""
    query: str = ""
    workflow_id: str = ""
    command_args: list[str] = Field(default_factory=list)
    # ...
```

### Why a flat field, not a discriminated union

Considered three alternatives:

1. **Discriminated union** — `target: Annotated[Union[SkillTarget, QueryTarget, CommandTarget], Field(discriminator="kind")]`. Pros: type-safe, self-documenting. Cons: breaks every existing `spec.skill_id` access (15 sites: ~11 in `executor.py`, ~4 in `loop_cmd.py`); migration would touch every test fixture that constructs a `LoopSpec`; `save_spec`/`load_spec` JSON format would break backward-compat for existing `~/.vibe/loops/*/spec.json`.

2. **Nested sub-model** — `target: TargetSpec`. Same migration cost as (1) without the type-safety win.

3. **Flat field (chosen)** — keep `skill_id / query / workflow_id` as today, add `command_args` next to them. Pros: **zero migration cost** (existing 3-field specs still validate); executor's existing `if skill_id: ... elif query: ...` ladder just gains one more `elif command_args:` branch; the 4-way xor enforces mutual exclusion at the schema layer.

The flat-field choice trades a small bit of expressiveness (you can't
statically prove which target type is set from the type alone) for a
meaningful reduction in blast radius. Every existing `LoopSpec` caller
keeps working unchanged, and the persistence format stays
backward-compatible with loops already on disk.

### Why `list[str]`, not a single `command: str`

- `list[str]` is **argv form** — `subprocess.run(argv)` runs it directly
  with no shell interpretation, eliminating the entire shell-injection
  family of risks. A `command: str` would have forced us to choose a
  parser (shlex? shell=True?) and document its limits.
- The CLI layer accepts `--command "instinct auto-promote --min-confidence 0.85"`
  as a string for ergonomics, then `shlex.split`s it into argv at the
  CLI boundary. A `ValueError` from shlex is caught and surfaced as a
  friendly CLI error.
- The plist generator emits `ProgramArguments` as a literal `<array>` of
  `<string>` — no shell escaping, no `&amp;` entity munging, paths with
  spaces survive intact.

### Executor branch

```python
def execute_loop_tick(spec: LoopSpec, ...) -> TickResult:
    if spec.skill_id:
        return _run_skill_target(...)
    elif spec.query:
        return _run_query_target(...)
    elif spec.workflow_id:
        return _run_workflow_target(...)
    elif spec.command_args:
        return _run_command_target(spec.command_args, ...)
    # unreachable: _exactly_one_target raises at validation time
```

`_run_command_target` reuses the same `state.record_run` /
`_classify_failure` plumbing as the other branches, so DEAD-transition
semantics are uniform across all target types.

## Consequences

- ✅ No migration cost for existing 3-target specs.
- ✅ Shell-injection-safe by construction (argv list, no shell).
- ✅ Uniform DEAD-transition / failure-classification across all targets.
- ⚠️ 4-way xor must be enforced explicitly — `_exactly_one_target` runs in
  a Pydantic `@model_validator(mode="after")`, so it fires at construction
  time. Only `model_construct()` could bypass it (intentional, not a hole).
  `LoopStore.save_spec` calls `model_dump_json` (no re-validation), but the
  spec it receives has already been validated at construction — the only
  way to slip an invalid spec into the store is to load it back from a
  tampered JSON on disk, which `load_spec` does re-validate.
- ⚠️ `_target_str` (used for table rendering) must remember to include
  `command_args` — easy to forget when adding a new branch.

## Alternatives considered and rejected

- **Add an `instinct_target` enum** (`assemble` / `promote` / `feedback`) —
  rejected as too narrow; future vibe subcommands would each require an
  enum update.
- **Use `workflow_id` for everything and treat each subcommand as a
  workflow** — rejected: workflows have their own lifecycle (paused,
  resumable, multi-step) that doesn't match a fire-and-forget CLI call.
