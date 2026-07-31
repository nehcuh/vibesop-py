# W5.2 Cross-Project Promote — Review Merged

**Date**: 2026-07-30
**Reviewers**: grok + pi (parallel, independent)
**Brief**: `docs/decisions/_w5-2-cross-project-promote-brief.md`
**Raw outputs**: `/tmp/w5-2-grok-review.md`, `/tmp/w5-2-pi-review.md`

## Verdict: REQUEST CHANGES (both lanes)

The brief's high-level shape is right (single `--scope` flag, hard-error
guard, single-target per invocation, propagate `project_distribution`).
But both reviewers independently caught **5 convergence issues** that
block ship as written.

## Convergence — both independently flagged

### P0-1: User-home scope writes to a discovery path → re-opens W4 P0

**Grok (data layer)**:
- Brief kill criteria says `~/.vibe/skills/<id>/SKILL.md`.
- `~/.vibe/skills/` is on `ExternalSkillLoader.EXTERNAL_PATHS` (external_loader.py:65-69).
- W4 P0 deliberately moved drafts OUT of discovery into
  `.vibe/observability/skill_drafts/` to enforce 未审不注入
  (`materialize_candidate` docstring).
- Reusing "loader already discovers it" as a *writer* target reopens the bug.

**Pi (product layer)**:
- `SkillManager.discover_all()` auto-loads the unreviewed draft.
- `SkillSecurityAuditor` checks for malicious code, not human review.
- Directly contradicts non-goal §2/§9.
- Concrete fix: user-home drafts → `~/.vibe/observability/skill_drafts/<id>/`.

**Joint fix**: Drafts land under **draft roots** in BOTH scopes:

| scope | draft root |
|---|---|
| `project` | `<cwd>/.vibe/observability/skill_drafts/` (unchanged) |
| `user-home` | `~/.vibe/observability/skill_drafts/` |

Activation stays a separate `vibe skill add` step.

### P0-2: `originating_project_ids` is redundant + leaks absolute paths

**Both**: `project_distribution: dict[str, int]` already carries the set
of projects as its `keys()`. `originating_project_ids = sorted(keys())`
duplicates storage for zero audit gain.

**Privacy**: `project_id = str(Path.cwd().resolve())` — absolute filesystem
paths. Storing twice doubles the leak surface. **Drop the field.** If you
want a sorted list, make it a `@property`.

### P0-3: γ (representative query selection) is unimplementable as specified

**Both**: γ says "highest-freq project's representative query", but
`Cluster.queries` is ordered by sorted `(project_id, task_id)`
(clustering.py:306-331), NOT by span frequency. `queries[0]` is
lexicographically first path, not busiest project.

**Fix**: propagate `task_keys: list[tuple[str, str]]` (or a
`query→project_id` map) onto `ClusterCandidate`. Then selection becomes
`argmax over project_distribution → that project's rep query`.

### P0-4: β (per-project query filter for `--scope project`) is dead code

**Both**: Q2 says `--scope project` on cross-project cluster errors.
Q4(β) implements per-project query redaction for `--scope project`.
These are contradictory.

**Fix paths** (pick one):
- **(i)** Drop β entirely. Project scope = single-project clusters only
  (the W4 happy path). Cross-project must use user-home scope.
- **(ii)** Reopen `--scope project` as a real product option: promote a
  cross-project cluster filtered to cwd project's queries only. Requires
  the provenance data from P0-3.

**Recommendation**: **(i)** for W5.2 — smallest viable scope. (ii) is a
real product capability but adds the β pipeline ripple cost pi flagged.

### P0-5: Redaction surface is wider than queries + gold_task_ids

**Both**: brief's redaction policy misses several leak vectors:

1. **`cluster_id`**: sha1 of sorted `(project_id, task_id)` composite
   keys (clustering.py:56,91). Deterministic — reviewer who guesses a
   query can confirm membership. Appears in YAML frontmatter +
   `promoted_from_cluster` metric.
2. **`name:`**: = `queries[0]` (skill_promote.py:860). One project's
   verbatim phrasing.
3. **`core_steps`**: `label_step_frequency` runs on ALL cluster spans
   (skill_promote.py:793-811). Steps section can encode other projects'
   workflows.
4. **`metrics table`**: brief says "scrub gold_task_ids" but table also
   has `task_ids` count + `gold_rate` derived from cwd-local
   InstinctLearner — semantically muddy for foreign task_ids.

**Joint fix**: For cross-project promotes to user-home:
- Drop `cluster_id` and `name:` from frontmatter (or regenerate from
  representative query only).
- Recompute `core_steps` from representative project's spans only.
- Replace metrics table with `project_distribution` (aliases, not paths).

## Complementary findings — what each caught that the other missed

### Grok-only

| # | Finding | Severity |
|---|---|---|
| G-1 | **Intake gap**: `scan_candidates` reads only local spans. Cross-project clusters will rarely appear in the candidate pool → guard is effectively dead code. Either add `scan-candidates --cross-project` (union pool spans) or explicitly defer intake to W5.3. | P0 |
| G-2 | `from_dict` `cls(**payload)` will throw if old code reads new keys or new required fields lack defaults. Both new fields MUST be optional with defaults. | P1 |
| G-3 | Prefer `--scope user` / `shared` over `user-home` — "home" describes a path, not a product concept. | Nit |

### Pi-only

| # | Finding | Severity |
|---|---|---|
| P-1 | **Candidate store is per-cwd** (`Path.cwd()/.vibe/observability`). Cross-project candidate lives in ONE project's store. "cd into each project to fork" dies on first cd — `store.get(cluster_id)` returns None. Either pooled candidate view in W5.2 or scope promote to "scanning project only". | P0 |
| P-2 | Q2 precedent citation is loose: `recall --cross-project` is a capability opt-in, not a hard-error guard. Closer precedent: sticky-state "cannot promote dismissed" at skill_commands.py:1280. | Nit |
| P-3 | `scope` with value `"global"` ALREADY exists at skill_commands.py:510 for install wizard. Reuse `"global"` instead of inventing `user-home`. | Nit |
| P-4 | Data-model cost of β is bigger than brief admits: per-project redaction requires `project_id` alongside each query through the whole pipeline (clustering → JSONL → render). Round-trip tests ripple. | P1 |
| P-5 | Privacy kill-test "no raw queries from non-target projects" would PASS while `cluster_id`/`name`/steps still leak. Tighten kill criterion to assert no foreign-project-derived identifiers at all. | P1 |

## Joint recommendations for revised brief

1. **Scope flag value**: use `--scope {project,global}` (pi P-3 — `global` already exists in the module).
2. **Draft roots**: both scopes write under `*_drafts/`, NOT into discovery paths (P0-1).
3. **Drop `originating_project_ids`** entirely (P0-2). `project_distribution.keys()` suffices.
4. **Drop β** (P0-4.i) — project scope is single-project only.
5. **Propagate `task_keys`** (or query→project map) onto `ClusterCandidate` (P0-3).
6. **Redaction scope**: queries + gold_task_ids + cluster_id + name + core_steps + metrics table (P0-5).
7. **Intake**: explicitly decide — either ship `scan-candidates --cross-project` in W5.2, or non-goal it to W5.3 (G-1). Don't leave implicit.
8. **Candidate store model**: explicitly decide — either pooled candidate view in W5.2, or scope promote to "scanning project only" + document the limitation (P-1).
9. **Tighten kill criteria**: assert no foreign-project-derived identifiers (raw queries, paths, composite-key hashes, verbatim names) — not just "no raw queries" (P-5).
10. **Migration**: both new fields MUST be Optional with defaults (G-2).

## Scorecard

| Q | Original rec | Joint verdict | Revision |
|---|---|---|---|
| Q1 scope flag | `--scope {project,user-home}` | AGREE shape, NUDGE value + target path | `--scope {project,global}`; draft roots only |
| Q2 hard-error guard | exit 1 + `--scope user-home` | AGREE | Cite sticky-state precedent (P-2); resolve Q4 contradiction |
| Q3 propagation | + `project_distribution` + `originating_project_ids` | DROP originating_project_ids | `project_distribution` only; Optional + default factory |
| Q4 redaction | β + γ + scrub gold_task_ids | DROP β; γ needs `task_keys`; widen redaction | γ for global only; redact cluster_id/name/steps/metrics |
| Q5 single-target | one promote = one target | AGREE | Document fork is non-goal given per-cwd store (P-1) |

## Ship-ready checklist (revised brief must address)

- [ ] P0-1: draft roots (not discovery paths) for both scopes
- [ ] P0-2: drop `originating_project_ids`
- [ ] P0-3: propagate `task_keys` (or equivalent) onto candidate
- [ ] P0-4: drop β OR explicitly reopen `--scope project` for cross-project (recommend drop)
- [ ] P0-5: redaction covers cluster_id + name + steps + metrics, not just queries
- [ ] G-1: explicit intake decision (ship `scan-candidates --cross-project` OR defer to W5.3)
- [ ] P-1: explicit candidate-store decision (pooled view OR "scanning project only" non-goal)
- [ ] P-5: tightened kill criteria (no foreign-project-derived identifiers)
- [ ] G-2: both new candidate fields Optional with defaults
- [ ] P-3: use `global` not `user-home`

## Next step

Revise the brief incorporating all 10 checklist items, then optional
self-adversarial pass before EnterPlanMode for implementation.

Per [[feedback-dynamic-workflow-external-review-first]]: external review
BEFORE self-adversarial. Per [[feedback-no-premature-production-ready]]:
review closure ≠ production-ready; need real end-to-end smoke after impl.
