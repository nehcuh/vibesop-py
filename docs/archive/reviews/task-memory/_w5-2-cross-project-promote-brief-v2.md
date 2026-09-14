# W5.2 — Cross-Project Skill Promote Story (v2, post-review)

**Status**: revised brief (incorporates grok+pi review)
**Date**: 2026-07-30
**Author**: claude
**Predecessor**: `_w5-2-cross-project-promote-brief.md` (v1, pre-review)
**Review**: `_review-w5-2-cross-project-promote-merged.md`
**Depends on**: W5.1 ship `891d0a8`

## What changed from v1

Per grok+pi review (REQUEST CHANGES) + user decisions on the two
architectural forks:

- **Intake**: SHIP `scan-candidates --cross-project` + pooled candidate
  store in W5.2 (not deferred to W5.3). [G-1 + P-1 closed]
- **Redaction**: PERMISSIVE — keep all queries + gold_task_ids, add
  prominent cross-project warning header to SKILL.md. γ and β are
  dropped (no representative-only mode).
- **Scope flag value**: `--scope {project,global}` (reuses existing
  `global` term from skill_commands.py:510, pi P-3).
- **Draft roots**: both scopes write under `observability/skill_drafts/`,
  NEVER into discovery paths (P0-1 fix).
- **Drop `originating_project_ids`** (P0-2 fix).
- **Propagate `project_distribution` only** onto `ClusterCandidate`
  (no `task_keys` needed without γ).
- **Widen redaction scope discussion** — permissive mode means most of
  P0-5 is moot, but `cluster_id` and `name` are still flagged with the
  warning header.

## 1. Problem (unchanged)

W5.1 made `Cluster.is_cross_project` available at the data layer. W5.2
makes every consumer of that field correct:

- Propagate `project_distribution` into the persisted candidate.
- Surface cross-project state at every CLI touch point
  (scan / list / promote / SKILL.md header).
- Make promote target scope explicit when cluster is heterogeneous.
- Add a pooled intake path so cross-project clusters actually appear
  in the candidate pool.

## 2. Goals / non-goals

**Goals**:
1. `scan-candidates --cross-project` reads pool members' spans,
   produces cross-project candidates that live in a global store.
2. `vibe skill candidates` shows both project-local and global candidates
   with `[CROSS-PROJECT]` tag + Projects column.
3. `ClusterCandidate.project_distribution` propagated; old records
   backfill via default factory.
4. `vibe skill promote` gains `--scope {project,global}` flag.
5. Cross-project cluster + no `--scope` → hard error (must opt in).
6. Drafted SKILL.md for cross-project clusters gets a prominent warning
   header naming the source projects. All queries/gold_task_ids kept
   (permissive policy).
7. Drafts NEVER written to a discovery path (`skills/`); always
   `skill_drafts/`.

**Non-goals** (defer to W5.3+):
- Cross-project skill *installation* (draft → active skill). Manual
  copy + `vibe skill add` for both scopes.
- Cross-project skill *sharing* (publish from project A so project B
  can install without file copy).
- Cross-project skill *rollback* / move-between-projects.
- Retention / compaction of `cluster_candidates.jsonl`.
- Per-project sub-clustering within a heterogeneous cluster.
- Per-project query filtering (the β path — explicitly dropped per
  permissive redaction choice).

## 3. Design decisions (locked)

### D1 — Pooled candidate store (NEW)

Two stores, both JSONL:

| store | path | writers | readers |
|---|---|---|---|
| project-local | `<project>/.vibe/observability/cluster_candidates.jsonl` | `scan-candidates` (default) | `candidates`, `promote` (from cwd) |
| global | `~/.vibe/observability/cluster_candidates.jsonl` | `scan-candidates --cross-project` | `candidates`, `promote` (from any cwd) |

`vibe skill candidates` reads BOTH stores, merges by `cluster_id`
(global wins on conflict since cross-project view is strictly more
general), tags each row with origin (`[PROJECT]` or `[CROSS-PROJECT]`).

### D2 — `--scope {project,global}` flag

- `--scope project` (default): draft → `<cwd>/.vibe/observability/skill_drafts/<id>/`
- `--scope global`: draft → `~/.vibe/observability/skill_drafts/<id>/`

Neither scope writes into a discovery path. Activation is a separate
`vibe skill add` step that copies draft → `<scope>/skills/<id>/` and
runs the security auditor. (Mirrors W4 flow.)

### D3 — Hard-error guard (unchanged from v1)

`vibe skill promote <cross-project-cluster-id>` without `--scope`:
exit 1, message names the source projects (via pool aliases when
available) and suggests both scope choices.

`--scope` provided → proceed (permissive: data is preserved with
warning header).

### D4 — `ClusterCandidate` schema change (slim)

```python
@dataclass
class ClusterCandidate:
    # ... existing fields ...
    project_distribution: dict[str, int] = field(default_factory=dict)
    # NO originating_project_ids (dropped per P0-2)

    @property
    def is_cross_project(self) -> bool:
        return len(self.project_distribution) > 1

    @property
    def source_project_aliases(self) -> list[str]:
        """Project IDs as aliases when in pool, else basename."""
        # Implemented at render time, not stored.
```

Both fields Optional with defaults — old records backfill naturally.
`from_dict` must tolerate missing field on read (G-2 fix).

### D5 — SKILL.md output for cross-project (permissive + warning)

```markdown
---
name: <slug-from-representative-query>
cluster_id: <hash>
project_distribution:
  cmspark: 12
  vibesop: 3
scope_recommended: global
---

> ⚠ **Cross-project cluster — handle with care.**
>
> This skill was synthesized from queries across multiple projects:
> `cmspark` (12 spans), `vibesop` (3 spans). Example queries and step
> sequences below may encode one project's workflow that doesn't apply
> to the other. Review carefully before activating.
>
> Activate via: `vibe skill add <path> --scope global`

## Examples
- <query 1>    # may be from either project
- <query 2>
...

## Steps
...   # computed from all cluster spans — may be inconsistent

## Metrics
gold_rate: 0.78
gold_task_ids: [...]   # may include hashes from both projects
```

Permissive policy keeps all data; warning header is the safeguard.

### D6 — `scan-candidates --cross-project` (NEW)

```bash
vibe skill scan-candidates --cross-project [--days 30] [--limit 5000]
```

Mirrors `recall --cross-project` pattern:
1. Load pool members from `~/.vibe/pool.yaml`.
2. For each member, read its `spans.jsonl` via `SpanWriter.query_recent`.
3. Union all spans (preserving each span's `project_id`).
4. Run existing pipeline: `cluster_queries` → `assess_gold_status` → candidate filter.
5. Persist passing candidates to the GLOBAL store at
   `~/.vibe/observability/cluster_candidates.jsonl`.

Locking: the global candidate store uses the same cross-process lock
pattern as pool.yaml (cross_process_lock + atomic_writer).

## 4. CLI surface (final)

```bash
# Existing W4 happy path — single-project cluster, default scope
vibe skill scan-candidates                       # writes to project store
vibe skill candidates                            # shows project store
vibe skill promote <id>                          # writes to project skill_drafts

# NEW in W5.2 — cross-project intake + scope flag
vibe skill scan-candidates --cross-project       # writes to global store
vibe skill candidates                            # merges both stores, tags origin
vibe skill candidates --cross-project-only       # filter
vibe skill promote <id> --scope global           # writes to global skill_drafts
vibe skill promote <id>                          # ERRORS if cluster is cross-project
```

Error semantics:
- `promote <cross-project-id>` no `--scope` → exit 1 + suggest scope.
- `promote <single-project-id> --scope global` → allowed (user opts for global).
- `promote <cross-project-id> --scope project` → allowed (permissive; warning header still added).
- Pool empty + `--cross-project` → exit 1 + hint to `vibe pool add`.

## 5. Implementation phases

1. **Data layer** (1 day):
   - Add `project_distribution` to `ClusterCandidate` (Optional + default factory).
   - Update `scan_candidates` to propagate from `Cluster` to candidate.
   - Update `ClusterCandidateStore.from_dict` to tolerate missing field.
   - Tests: 4-5 new (backfill, is_cross_project property, render with/without).

2. **Global candidate store** (1 day):
   - Add `~/.vibe/observability/cluster_candidates.jsonl` store.
   - `ClusterCandidateStore` accepts a `scope: Literal["project","global"]` kwarg.
   - Locked writes via `cross_process_lock` + `atomic_writer`.
   - Tests: 4-5 new (concurrent writes, merge behavior on read).

3. **scan-candidates --cross-project** (0.5 day):
   - Reuse pool-loading logic from `recall_cmd._run_cross_project`.
   - Union spans, run existing pipeline, write to global store.
   - Tests: 3-4 new (pool aggregation, empty pool error, span attribution).

4. **Promote --scope + guard** (0.5 day):
   - Add `--scope {project,global}` Typer option.
   - Hard-error on cross-project + no scope.
   - `materialize_candidate` honors scope (writes to correct drafts dir).
   - Tests: 5-6 new (guard fires, scope routing, single-project unchanged).

5. **SKILL.md warning header** (0.5 day):
   - Extend `_render_skill_md` with conditional warning block + `project_distribution` in frontmatter.
   - Permissive: keep all queries + gold_task_ids.
   - Tests: 3 new (header present for cross-project, absent for single-project, frontmatter shape).

6. **candidates list display** (0.5 day):
   - Merge project + global stores; tag origin; add Projects column.
   - `--cross-project-only` filter flag.
   - Tests: 3-4 new (merge, tag, filter).

**Total**: 4-5 days for a careful pass.

## 6. Kill criteria (tightened per P-5)

- All new tests green; full regression green (currently 1107).
- Real `vibe skill scan-candidates --cross-project` against vibesop + cmspark pool produces a cross-project candidate in the global store.
- `vibe skill candidates` shows the cross-project candidate with `[CROSS-PROJECT]` tag and Projects column (aliases, not paths).
- `promote <cross-project-id>` without `--scope` errors with helpful message naming source projects.
- `promote <cross-project-id> --scope global` writes to `~/.vibe/observability/skill_drafts/<id>/SKILL.md` (NOT `~/.vibe/skills/`).
- SKILL.md for cross-project promote contains warning header + `project_distribution` frontmatter.
- **Privacy assertion**: SKILL.md does NOT contain absolute filesystem paths from any project (only aliases or hashes). This is the tightened kill criterion from P-5 — paths must not leak even in permissive mode.
- Single-project cluster flow unchanged (W4 tests pass unmodified).

## 7. Open questions for implementation plan

1. **Conflict resolution (resolved)**: same `cluster_id` in both stores.
   Rule: dedup by `cluster_id`; if both exist, prefer the record with
   larger `len(project_distribution)` (more heterogeneous view wins).
   Test: assert dedup contract.
2. **`scan-candidates --cross-project` idempotence (resolved)**: upsert
   keyed by `cluster_id`, not append. Subsequent runs refresh
   `project_distribution` + `last_seen_at`. Old entries whose cluster
   no longer forms (insufficient spans after age-out) get marked
   `stale=true` rather than deleted (deletion is retention's job).
3. **Pool member missing spans.jsonl**: skip silently with debug log
   (matches `recall --cross-project` behavior).
4. **Warning header i18n**: hardcode English for W5.2; defer i18n.
5. **Security auditor on `vibe skill add --scope global`**: existing
   auditor runs unchanged. It checks for malicious code patterns, not
   cross-project content. The warning header is the human-review
   safeguard; permissive policy means we accept the auditor won't catch
   leaked workflow knowledge. Documented in `vibe skill promote --help`.

## 7a. Self-adversarial notes (post-review pass)

Findings from self-adversarial pass after grok+pi review:

- **A1 (resolved in Q1 above)**: dedup contract was underspecified —
  fixed via "prefer more-heterogeneous record" rule.
- **A2 (open — product decision)**: `promote <cross-id> --scope project`
  writes foreign queries into cwd's draft. Permissive policy permits
  this, but the warning is the only safeguard. Options:
  - (i) Allow with warning header (current v2 design).
  - (ii) Require explicit `--i-understand-cross-project` flag for this
    specific combination.
  - (iii) Hard-error (force `--scope global` for cross-project).
  Current v2 picks (i). User chose permissive → (i) is consistent.
  Document loudly in promote --help.
- **A3 (resolved in Q2 above)**: scan idempotence via upsert.
- **A4 (open — gap)**: `vibe skill add --scope global` flow when draft
  is cross-project — security auditor doesn't see warning header content.
  Accepted under permissive policy; documented in Q5 above.
- **A5 (noted)**: γ drop means `core_steps` also unredacted. Warning
  header text already covers this ("step sequences below may encode one
  project's workflow"). No brief change needed.
- **A6 (added to risk register)**: global store concentrates raw
  queries from all pool members in one file. Higher blast radius than
  per-project stores. Filesystem permissions are the safeguard (0600).

## 8. Defer list (NOT in W5.2)

- Cross-project skill installation (draft → active skill). Manual.
- Cross-project skill publishing (project A → project B without file copy).
- Cross-project skill rollback / move-between-projects.
- Retention / compaction of `cluster_candidates.jsonl`.
- Per-project sub-clustering within a heterogeneous cluster.
- Per-project query redaction (β path) — explicitly dropped per permissive choice.
- Representative-only query mode (γ path) — explicitly dropped per permissive choice.

## 9. Risk register (post-review)

| Risk | Mitigation |
|---|---|
| User promotes cross-project cluster to project scope, doesn't read warning header | Header is bold + at top; promote command also prints warning to stdout |
| Global candidate store grows unbounded | Acceptable for W5.2 (defer to retention track); monitor |
| Pool member paths change (move/rename) → stale entries in `project_distribution` | Path is resolved canonical; if pool member removed, distribution shows orphan path with `[unknown]` tag |
| Concurrent `scan-candidates --cross-project` from two shells | Locked writes (cross_process_lock + atomic_writer) |
| Permissive policy leaks query content across projects | Warning header + user opt-in via `--scope`. Documented in `vibe skill promote --help`. |
| Global candidate store concentrates raw queries from all pool members in one file (A6) | Filesystem permissions 0600 on `~/.vibe/observability/cluster_candidates.jsonl`; same trust boundary as `~/.vibe/pool.yaml` (already stores absolute paths) |
