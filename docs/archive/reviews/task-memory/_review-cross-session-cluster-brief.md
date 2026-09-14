# Review Brief — Cross-Session / Cross-Project Cluster (W5 design exploration)

**Date**: 2026-07-30
**Status**: Design exploration, pre-implementation
**Reviewer**: grok + pi

## Context

VibeSOP task-memory-loop v3 (W0-W4) shipped 2026-07-29. The loop is:
`spans.jsonl` → `task_id` (sha1 of normalized query) → `cluster_queries` (cosine +
union-find) → `assess_gold_status` (InstinctLearner success rate) → `vibe recall`
CLI / `vibe skill scan-candidates` / auto-replay prompt.

**v2 history**: original design had a math contradiction — `task_id` was hashed
with `project_path` (cross-project → different ids) while selling "cross-project
cluster" as a feature (needs cross-project → same id). Grok+pi independently
caught this; it was the most severe v2 design flaw.

**W0 resolution**: task_id is now pure query derivation
(`sha1(normalize(query))[:16]`), no `project_path` in hash. Math precondition
for cross-project satisfied.

**Current gap**: even though task_id is now cross-project stable,
`SpanWriter` reads/writes per-project `.vibe/observability/spans.jsonl`, and
`recall` defaults to `query_recent(limit=100)`. No code path actually aggregates
across sessions or projects.

## Current code reality (verified)

- `src/vibesop/core/observability/task_id.py` — pure query hash, frozen
  normalize rules, comment explicitly notes "project_path NOT in hash"
- `src/vibesop/core/observability/span_writer.py:62` — writes to relative
  `.vibe/observability/spans.jsonl`; only read API is `query_recent(limit=100)`
- `src/vibesop/core/observability/clustering.py:126` — `cluster_queries(spans:
  list[dict])` is a pure function; doesn't care where spans come from
- `src/vibesop/cli/commands/recall_cmd.py:54-55` — `SpanWriter.query_recent`
  is the only span source
- `src/vibesop/core/config/manager.py` — no `cross_project` field exists
- `spans.jsonl` files do NOT separate sessions — they accumulate across all
  sessions in the project's lifetime

## Two orthogonal dimensions

### A. Same-project cross-session

`spans.jsonl` already accumulates across sessions; the only gate is
`query_recent(limit=100)`.

**Proposed change**:
- Add `--all-time` / `--since=7d` flag to `recall` + `skill scan-candidates`
- Generalize `query_recent` → `query_spans(limit=None, since=None)`
- Add `--max-spans-per-task=N` sampling before clustering (O(n²) cosine)

**Cost**: ~50 LOC + 2 tests.

### B. Cross-project opt-in bridge

**B1 (recommended): read-time aggregation**
- New config: `~/.config/vibesop/cross_project_pool.yaml` lists N project paths
- New API: `SpanWriter.query_cross_project(limit)` mtime-polls each project's
  spans.jsonl, merges by timestamp, returns slice
- `recall --cross-project` triggers it; default off
- Cluster dict carries `project_path` as display field

**B2 (deferred): write-time mirror**
- SpanWriter.write_span also mirrors to global `~/.vibe/observability/spans.jsonl`
- Strong consistency but daemon/hook complexity

**Cost**: B1 ~100 LOC + schema + tests. B2 ~200 LOC + consistency story.

## Key math note (avoiding v2 trap)

Cross-project aggregation does NOT change the cluster algorithm (cosine is
pairwise; 1 project or N, same math). The real risk is **semantic collision**:

```
project A: "调试登录 bug" → task_id X → real intent OAuth
project B: "调试登录 bug" → task_id X → real intent session
```

W0 decided task_id excludes project_path, so these collide. Cluster gets
polluted.

**Mitigation**: cluster data carries `project_path` as display field; UI shows
provenance. Do NOT add project_path back into task_id hash (would re-introduce
v2 contradiction).

## Recommendation

- **W5.0 (1 day)**: ship A first, validate "user solved 'screenshot permission'
  17 times in cmspark" scenario forms a meaningful cluster
- **W5.1 (3-5 days)**: if W5.0 validates, ship B1 bridge pool
- **Defer**: B2 unless B1 read-time perf is a bottleneck

## 5 questions for review

**Q1**: Is "ship A first, validate, then B1" the right sequencing? Or should
we go straight to B1 (cross-project was the original v2 intent)?

**Q2**: Semantic collision (same query string, different real intent across
projects). Carrying `project_path` as display-only field — sufficient, or does
the cluster algorithm itself need a project-aware component (e.g. per-project
sub-clustering then merge)?

**Q3**: B1 read-time aggregation mtime-polls N files on every `recall`. At what
N does this become a perf problem? Should we cache the merged view with a TTL?

**Q4**: A's `--max-spans-per-task=N` sampling — random sample, most-recent-N,
or stratified by time bucket? Affects which clusters surface.

**Q5**: Is "spans accumulate forever, no session boundary" a hidden liability?
Should we add a `session_id` field to spans now (cheap) so future features can
slice on it, even if W5.0 doesn't use it?

## Key files (for reviewer reference)

- `src/vibesop/core/observability/task_id.py` — task_id contract
- `src/vibesop/core/observability/span_writer.py` — span storage + query_recent
- `src/vibesop/core/observability/clustering.py:126` — cluster_queries
- `src/vibesop/cli/commands/recall_cmd.py` — recall CLI
- `src/vibesop/core/observability/skill_promote.py` — W4 scan-candidates
- `memory/project-task-id-bug-and-cross-project.md` — v2 history
- `memory/feedback-feature-mutual-exclusion-check.md` — v2 math contradiction lesson
