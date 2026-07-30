# Cross-Session / Cross-Project Cluster — Review Merged

**Date**: 2026-07-30
**Reviewers**: grok + pi (parallel, independent)
**Brief**: `docs/decisions/_review-cross-session-cluster-brief.md`
**Raw outputs**: `/tmp/grok-review-prompt.txt`, `/tmp/pi-review-prompt.txt`

## Convergence — both independently flagged

### P0-1: Display-only `project_path` does not fix hard-group collision

**Grok (data layer)**:
- `cluster_queries` hard-groups by `task_id` only (`clustering.py:5-7`, `155-166`)
- Same normalized query → same `task_id` → forced merge **before** cosine runs
- Downstream: `assess_gold_status` mixes projects (`gold_detection.py:83`),
  Instinct lookup is CWD-local (`gold_detection.py:76`), skill promote inherits mixed counts
- **Do NOT re-hash `project_path` into `task_id`** (v2 trap) — scope aggregation instead

**Pi (product layer)**:
- Display annotation is "annotating confusion, not resolving it"
- User must manually de-confuse output by mentally splitting by project_path
- If user promotes cluster → bakes semantic garbage into skill library
- Need `project_distribution` field (`{"cmspark": 12, "webapp": 5}`)
- Warn explicitly on heterogeneous clusters

**Joint fix**:
- Algorithm-level: `(project_id, task_id)` composite hard-key for same-project gold/promote
- Cross-project merge as **separate opt-in display-only view** (`recall --cross-project`),
  not on promote path
- `Cluster.project_distribution: dict[str, int]` for UI warning

### P1: Sampling strategy = most-recent-N (both agreed)

- Apply **after** time filter (grok)
- Deterministic tie-break for reproducibility (grok)
- Not random (promote becomes non-reproducible)
- Documents "what's current practice" — recall's core use case (pi)

### P1: Populate `session_id` and `project_id` now (both agreed)

- Grok caught: fields **already on schema** (`models.py:43`, `62`), just unpopulated
- Historical data has `project_id="default"` + `session_id=null`
- Q5 reframed: "start filling", not "add field"
- Cost: zero migration, just start populating on write path

## Complementary findings — what each caught that the other missed

### Grok-only (data/structural layer)

| # | Finding | Severity |
|---|---------|----------|
| G-P0-2 | `recall_similar` reads `span.get("timestamp")` but real spans have `started_at`. Missing field → **keep span** (silent bug). Tests use `timestamp` so green. Prod `--days` is dead. | **P0** |
| G-P0-3 | Brief was stale: `recall` already uses `limit=5000 + --days 30` (`recall_cmd.py:44-55`). Real gate is `scan-candidates` at `limit=100` (`skill_commands.py:1059-1091`). W5.0 value should target scan-candidates. | **P0** |
| G-P0-4 | Existing spans have `project_id="default"`. B1 read-time tagging is insufficient — must stamp absolute `project_path` at write time. | **P0** |
| G-P1-1 | Math claim "cosine is project-count-independent" is **half-true**. Soft merge is, but hard-group semantics (span_count, gold gates, first-wins rep, cluster_id membership) change with aggregation domain. | P1 |
| G-P1-2 | mtime-poll issues: (1) full-file scan per project (not just mtime), (2) per-file tail ≠ global merge, (3) relative path resolution, (4) symlink double-count, (5) reader takes no shared lock → torn reads | P1 |
| G-P1-4 | `cluster_id` = sha1 of task_ids only (`clustering.py:209-211`). Window changes reshape clusters → promote ID churn (already true, B1 amplifies) | P1 |

### Pi-only (product/UX/cognitive layer)

| # | Finding | Severity |
|---|---------|----------|
| P-P0-2 | No UX spec for `recall --cross-project` output. Need mock for 1/3/8-project cases before implementation. | **P0** |
| P-P1-1 | A alone delivers near-zero user value ("see 17 vs 3 spans" is infrastructure, not feature). Bundle A into B1; don't ship A as standalone milestone. | P1 |
| P-P1-2 | YAML config is wrong primary UX. Need `vibe pool add/remove/list/status` CLI commands. YAML is persistence layer. | P1 |
| P-P2-2 | Privacy "local-only" not stated explicitly. Must write into brief + first-add CLI notice. | P2 |
| P-P2-3 | Cross-project skill promote story missing. Which project(s) get the skill? | P2 |

## Updated direction (post-review)

### W5.0 — Bug fix + instrumentation (1-2 days)

Originally: "lift recall's 100-span cap"
Now:
1. **Fix `timestamp` → `started_at` field resolution** in `recall_similar`
   (silent prod bug, independent of W5 value)
2. **Populate `session_id` (UUID per CLI session) and `project_id` (absolute
   project path) on span write** — schema already has fields, just fill them
3. **Parameterize `scan-candidates` window** (the real gate, not `recall`)
4. **Most-recent-N sampling** after time filter, deterministic tie-break

### W5.1 — Cross-project bridge with correct scoping (3-5 days)

Originally: "B1 read-time aggregation + display project_path"
Now:
1. `vibe pool add/remove/list/status` CLI commands (pi P-P1-2)
2. **`(project_id, task_id)` composite hard-key** for gold/promote path
3. `recall --cross-project` as **explicit opt-in display-only view**, NOT on
   promote path
4. `Cluster.project_distribution: dict[str, int]` field + heterogeneous warning
5. mtime + content cache with TTL (5-60s); shared read lock or accept rare drops
6. Privacy notice on first `vibe pool add`

### W5.2 — Deferred

- Project-aware sub-clustering (per-project then centroid merge)
- Cross-project skill promote story (which project gets the skill?)
- Retention / compaction policy for spans.jsonl

## Go/No-Go

| Item | Verdict |
|------|---------|
| W5.0 "A" (bug fix + instrumentation) | **Go** after P0-2 field fix + retarget to scan-candidates |
| B1 as originally proposed (display-only bridge) | **No-go** for gold/promote path |
| B1 revised (composite hard-key + display-only opt-in) | **Conditional Go** |
| Math direction (keep task_id pure query, scope aggregation) | **Sound** — v2 trap avoided |

## Lessons

- **Brief staleness**: I wrote the brief from memory, didn't verify against
  current code. Grok caught `recall` already has limit=5000 + --days 30, my
  "lift the 100-cap" value prop was wrong. Should have read the file first.
- **Complementary review style** ([[feedback-grok-pi-complementary-style]]):
  grok caught 4 data-layer issues pi missed; pi caught 4 UX issues grok missed.
  Both P0-1 (display ≠ fix) converged independently — strongest signal.
- **Field-existence vs field-population** (grok): assumed we needed schema
  migration for `session_id`. Schema already has it; we need to populate it.
  Always grep schema before claiming migration cost.
