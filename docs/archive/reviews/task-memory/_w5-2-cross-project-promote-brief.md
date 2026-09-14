# W5.2 — Cross-Project Skill Promote Story

**Status**: design brief (pre-review)
**Date**: 2026-07-30
**Author**: claude (first-cut, pre-grok+pi)
**Depends on**: W5.1 ship `891d0a8` (composite hard-key + `Cluster.is_cross_project`)
**Predecessor review**: `_review-cross-session-cluster-merged.md`

## 1. Problem

W5.1 shipped `Cluster.is_cross_project` + `project_distribution` so the data
layer knows when a cluster spans multiple projects. But the promote path is
cross-project-blind:

- `ClusterCandidate` dataclass (skill_promote.py:108-181) drops
  `project_distribution` when materializing the candidate — only `task_ids`,
  `queries`, `gold_task_ids`, `step_freq` survive (skill_promote.py:802-813).
- `vibe skill promote <cluster_id>` takes a single positional arg, no flags
  (skill_commands.py:1253-1298). Skill ID auto-derived; draft always written
  to `<cwd>/.vibe/observability/skill_drafts/<skill_id>/SKILL.md`.
- The clustering docstring (clustering.py:124-128) **promises** a guard
  ("UI consumers should warn before promoting a cross-project cluster...
  See `skill_promote` guard.") but **no such guard exists**.
- Drafted SKILL.md contains raw queries (up to 5 verbatim,
  skill_promote.py:876-879) and full `gold_task_ids` (skill_promote.py:932).
  Promoting a cross-project cluster into one project's skill file leaks
  queries from the other project(s).

## 2. Goals / non-goals

**Goals**:
1. Propagate `project_distribution` into `ClusterCandidate` so the CLI can
   warn without re-reading spans.
2. Make the cross-project state visible at every user-facing surface:
   `scan-candidates` output, `candidates` list, `promote` confirmation.
3. Decide target-project semantics: where does the skill land when the
   source cluster is heterogeneous?
4. Decide query-redaction policy: what survives into the drafted SKILL.md?
5. Preserve the W4 single-project flow unchanged when the cluster is
   single-project (backwards compat).

**Non-goals** (defer to W5.3+):
- Cross-project skill *installation* (draft → `.vibe/skills/`) — W5.2 only
  owns the promote step (candidate → draft). Installation remains manual.
- Cross-project skill *sharing* (publish a skill from project A so project
  B can install it without copying the file). Out of scope; needs a
  transport layer.
- Cross-project skill *rollback* / "move skill between projects". Out of
  scope; promote is currently one-shot.
- Retention / compaction of `cluster_candidates.jsonl`. Separate W5.2 track.

## 3. Design questions to resolve (5 from explore map)

### Q1 — Target scope: `--scope {project,user-home}` vs `--target-project <id>` vs both?

**Options**:

- **(A) `--scope {project,user-home}`**: reuses existing
  `ExternalSkillLoader.EXTERNAL_PATHS` (external_loader.py:65-69) which
  already includes `~/.vibe/skills/`. "user-home" means the skill is
  available to ALL projects on this machine. Single knob; minimal CLI
  surface change.
- **(B) `--target-project <alias>`**: writes into another project's
  `.vibe/skills/` (must be a pool member). Allows "I worked on this in
  project A but want the skill to live in project B".
- **(C) Both, mutually exclusive**: most flexible, biggest CLI surface.

**Tradeoffs**:
- (A) is the smallest viable change. Single new flag. The user-home scope
  is already half-built (loader discovers it, just no writer).
- (B) introduces cross-project writes — needs the pool registry, path
  resolution, write-through-locking on the *other* project's skill_drafts
  dir. Higher blast radius.
- (C) doubles the test matrix.

**Recommendation**: **(A)** for W5.2. Add `--target-project` only if a
concrete use case surfaces during review.

### Q2 — Cross-project guard behavior

**Options**:

- **(a) Hard-error**: `vibe skill promote <id>` exits non-zero when
  `is_cross_project`. Forces explicit `--allow-cross-project` override.
  Mirrors `recall --cross-project` opt-in pattern (recall_cmd.py:53).
- **(b) Warn + `--force`**: prints warning, requires confirmation flag,
  exits 0 on success.
- **(c) Auto-redirect**: silently redirect cross-project promotes to
  user-home scope (only valid if Q1=A). No flag needed.

**Tradeoffs**:
- (a) is the safest and matches the "user must opt in" precedent. Downside:
  one extra flag on the happy path for cross-project users.
- (b) is friendlier but `--force` is easy to muscle-memory past.
- (c) is magical — hides the cross-project decision from the user. The
  user might promote a cluster expecting it to land in cwd and be
  surprised when it lands in `~/.vibe/skills/`.

**Recommendation**: **(a)** with override `--scope user-home`
(Q1=A makes this natural: cross-project requires explicit scope choice).

### Q3 — `project_distribution` propagation

**Decision**: add to `ClusterCandidate` dataclass. Stored on disk in
`cluster_candidates.jsonl` so subsequent `candidates list` / `promote`
calls don't need to re-read spans.

**Schema change**:
```python
@dataclass
class ClusterCandidate:
    # ... existing fields ...
    project_distribution: dict[str, int] = field(default_factory=dict)

    @property
    def is_cross_project(self) -> bool:
        return len(self.project_distribution) > 1
```

**Migration**: existing `cluster_candidates.jsonl` records lack the field.
`ClusterCandidateStore.upsert` already does additive merge
(skill_promote.py — verify exact lines during impl); default-empty
factory handles backfill naturally. No migration script needed.

**Audit**: store `originating_project_ids: list[str]` (sorted) for
forensic value — if a skill later misbehaves, we know which projects
contributed. Cheap to add now, expensive to retrofit later.

### Q4 — Query redaction policy

**Options when promoting cross-project**:

- **(α) Keep all queries** (current behavior). Leaks queries from
  project B into project A's skill file. **Rejected**.
- **(β) Keep only queries from the target project**. Requires knowing
  which query came from which project at materialize time. Currently
  `candidate.queries` is a flat list (skill_promote.py:876). Would need
  `queries: list[dict[str, str]]` (query + project_id) or per-project
  query lists.
- **(γ) Keep only the representative query**. Single line, derived from
  the highest-frequency task. Loses example diversity but zero leakage.
- **(δ) Scrub `gold_task_ids` from metrics table, keep queries**. Half
  measure. task_ids are query-derived hashes, so they're a (weak)
  fingerprint but not raw text. Queries are still raw text → still leak.

**Recommendation**: **(β)** when target scope = a specific project
(Q1=A's `project` scope). **(γ)** when target scope = `user-home`
(shared across projects; can't privilege one project's queries). The
`gold_task_ids` metrics table gets replaced with a per-project breakdown
or scrubbed entirely on cross-project promotes.

### Q5 — Multi-target promotion (fork into N skills?)

**Question**: when a cluster spans projects A, B, C, does one `promote`
produce one skill (in one target) or N skills (one per project)?

**Recommendation**: **one skill in one target per `promote` invocation**.
User runs `promote <id> --scope project` N times if they want it in N
projects. Rationale:
- Each invocation is auditable and reversible.
- No collision story needed (single `_slugify`-derived skill_id per call).
- Mirrors the W4 mental model: one cluster → one skill.

Multi-target fork stays out of scope. If users want it, it's a thin
wrapper script later.

## 4. Proposed CLI surface

```bash
# Single-project cluster (backwards compat — no flag changes)
vibe skill promote <cluster_id>

# Cross-project cluster — must opt in explicitly
vibe skill promote <cluster_id> --scope user-home
vibe skill promote <cluster_id> --scope project  # error if cross-project

# Audit
vibe skill candidates --show-projects  # new flag, projects column
```

**Errors**:
- `promote <cross-project-id>` without `--scope`: exit 1, message names
  the projects involved and suggests `--scope user-home`.
- `promote <cross-project-id> --scope project`: exit 1, message explains
  why single-project scope can't hold cross-project data.

## 5. Data flow (proposed)

```
scan_candidates()
  └─ Cluster (has project_distribution, is_cross_project)
     └─ ClusterCandidate (NEW: project_distribution, originating_project_ids)
        └─ cluster_candidates.jsonl (persisted with new fields)

promote <id>
  ├─ load candidate
  ├─ if candidate.is_cross_project and scope != user-home: error
  ├─ redact queries per Q4 policy
  ├─ materialize_candidate() → ~/.vibe/skills/<id>/SKILL.md
  │                              or .vibe/observability/skill_drafts/<id>/
  └─ store.promote(id, skill_id)  # status flip
```

## 6. Implementation phases (sketch — not the final plan)

1. **Data layer**: add `project_distribution` + `originating_project_ids`
   to `ClusterCandidate`. Update `scan_candidates` to populate. Update
   `ClusterCandidateStore` JSONL read/write. (Additive — old records
   default to empty.)
2. **Guard + scope flag**: add `--scope` to `promote`. Implement
   cross-project error. Update `materialize_candidate` to honor scope.
3. **Redaction**: per-Q4 policy. Update `queries_block` and metrics table
   rendering in skill_promote.py.
4. **Display**: add Projects column to `candidates list` + `scan-candidates`
   output. Add `[CROSS-PROJECT]` tag.
5. **Tests**: ~15-20 new tests across the 4 layers.

Estimated effort: 2-3 days for a careful pass; single PR.

## 7. Open questions for reviewers

1. **Is `--scope user-home` the right name?** Alternatives: `--global`,
   `--shared`, `--user`. `user-home` is descriptive but verbose.
2. **Should cross-project single-project-scope promotes be a hard error,
   or should we offer an interactive prompt ("cluster spans A,B,C — pick
   a target")?** Interactive prompts break scripting; hard error is
   scriptable.
3. **`originating_project_ids` — should this be hashed (privacy) or
   plaintext (auditability)?** Hashed loses audit value if paths change;
   plaintext leaks absolute paths into the skill file.
4. **What happens to `gold_task_ids` in the metrics table when the
   cluster is cross-project?** Current table (skill_promote.py:932) lists
   them verbatim. Q4(δ) suggests scrubbing — confirm.
5. **Should `ClusterCandidateStore` gain a `cross_project_count` index
   for fast `candidates --filter cross-project` queries?** Cheap to add
   now; harder to retrofit.

## 8. Kill criteria

- All new tests green; full regression green (currently 1107).
- Real `vibe skill scan-candidates` shows Projects column when heterogeneous.
- `promote <cross-project-id>` without `--scope` errors with helpful message.
- `promote <cross-project-id> --scope user-home` writes to
  `~/.vibe/skills/<id>/SKILL.md` and the file contains NO raw queries
  from non-target projects (privacy assertion in test).
- Single-project cluster flow unchanged (regression: W4 tests pass unmodified).

## 9. Defer list (NOT in W5.2)

- Cross-project skill *installation* (draft → active skill). Manual copy
  + `vibe skill add` for now.
- Cross-project skill *publishing* (project A → project B without file copy).
- Cross-project skill *rollback* / move-between-projects.
- Retention / compaction of `cluster_candidates.jsonl` (separate W5.2 track).
- Per-project sub-clustering within a heterogeneous cluster (W5.2+).
