# W1 Implementation Review Brief — task-memory-loop v3

**Date**: 2026-07-29
**Scope**: W1 Task A/B/C — embedding cache + cluster algorithm + gold detection
**Prior**: W0 shipped (commit `75b7a81`), passed 3 rounds of grok+pi review

## What shipped

| Module | File | Tests |
|---|---|---|
| Embedding cache | `src/vibesop/core/observability/embedding.py` | 13 |
| Cluster algorithm | `src/vibesop/core/observability/clustering.py` | 14 |
| Gold detection | `src/vibesop/core/observability/gold_detection.py` | 8 |
| Tiny API add | `src/vibesop/core/instinct/learner.py` (`get_instinct_for_query`) | covered by existing 282 tests |

Total: 35 new tests, no regression in 282 existing tests.

## Design decisions

### W1.A Embedding cache (`embedding.py`)

**Cache key**: `sha1(model_id + "\x1f" + normalize(query))[:16]`

- Reuses `task_id.normalize_query` so cache hits align with task_id equivalence
  (queries that normalize identically share one cache entry)
- `model_id` prefix enables cache invalidation on model upgrade

**Storage**: `.vibe/cache/embeddings.npz` with three arrays:
- `metadata`: 0-d `<U` numpy array wrapping `{"model_id": ..., "version": 1, "count": N}`
- `keys`: 1-d `<U16` array of cache keys
- `vectors`: 2-d `float32` array, shape `(N, 384)`

**Cross-process safety**:
- `fcntl.flock` on a **sidecar `.lock` file** (not the `.npz` itself — locking
  the data file requires opening it in modes that risk truncation)
- Re-read under lock to merge external additions (RMW pattern from
  ReflectionStore race fix [[project-dashboard-v3-phase-b-shipped]])
- Atomic write: `tmp.npz` → `replace`
- Race tolerance: lost updates are acceptable (embeddings are deterministic)

**Lazy model load**:
- `_compute()` lazily imports fastembed inside the function body; returns
  `None` if library missing (fastembed is `[semantic]` optional extra)
- Singleton via `get_embedding_cache()` module-level global

**Specific concern I want feedback on**: the lock pattern uses a sidecar
`.lock` file created lazily inside `_flush_locked`. If the lock file
cannot be created (read-only filesystem), we fall through to Windows
branch (no cross-process lock). Is this acceptable for MVP, or should
we surface the error?

### W1.B Cluster algorithm (`clustering.py`)

**Two signals combined**:
1. **Hard group**: spans sharing `task_id` → same cluster (never split)
2. **Soft merge**: distinct task_ids with `cosine(representative_query_embedding_i,
   representative_query_embedding_j) >= threshold` → Union-Find merge

**Default threshold**: 0.80 (per design addendum §8.1; benchmark showed
MiniLM near-miss p90=0.894, so 0.80 absorbs screenshot-adjacent queries)

**Transitivity**: Union-Find connected components (not just pairwise)
— if A~B and B~C but not A~C, they still form one cluster.

**Cluster ID**: `sha1("\x1f".join(sorted_member_task_ids))[:16]`
— deterministic, order-independent

**Representative query per task_id**: first query encountered. Since
all queries with same task_id normalize equivalently, this is safe.

**Specific concern**: I chose `>= threshold` (inclusive boundary) for
the merge condition. Test `test_threshold_at_boundary_includes` locks
this in. Alternative is strict `>`, which would split boundary pairs.
Both are defensible; inclusive seemed more aligned with "absorb
adjacent queries" intent. Confirm or push back.

### W1.C Gold detection (`gold_detection.py`)

**Primary signal**: any member task_id has an instinct with
`success_count >= 1` (configurable)

**Size gate**:
- `span_count >= 5` AND has success → `is_gold = True`
- `span_count < 5` AND has success → `is_candidate = True`
- No success signal → both False

**Gold rate**: `len(gold_task_ids) / len(member_task_ids)`
- Used by W4 skill promote trigger (`gold_rate >= 0.6`)

**Tiny API add to InstinctLearner**: `get_instinct_for_query(query) -> Instinct | None`
- Avoids breaking `_instincts` encapsulation from outside the class
- Bounded Earned Refactor: 1 method, no architectural change, serves Task C root cause

**Specific concern**: I'm attaching `gold_task_ids` and `gold_rate` to
Cluster via dynamic attribute assignment
(`cluster.gold_task_ids = ...`), not via dataclass fields. The base
`Cluster` dataclass doesn't declare them. This keeps the base type lean
but means type checkers won't see them. Should I add them as proper
dataclass fields with default values, or leave as dynamic attributes?

## What I did NOT do

- **Secondary gold signal** (design §3 W1 Task C "辅信号"):
  `status==completed AND has_match==true AND duration<=p50(cluster)`
  — this needs span enrichment that isn't yet wired (status/duration
  not currently on all route spans). Defer to W2 alongside recall.
- **Real model invocation in tests**: all tests mock `_compute()` to
  return deterministic fake vectors. Real fastembed invocation tested
  in W0 benchmark script, not in unit tests (keeps test suite fast,
  doesn't require `[semantic]` extra in CI).
- **Centroid persistence**: `Cluster.centroid` is computed during
  `cluster_queries()` but not persisted anywhere. W2 recall will
  re-derive on demand. Is this acceptable, or should we cache?

## Acceptance criteria from design §3 W1

| Criterion | Status |
|---|---|
| Recall: ≥10 gold queries in one connected component | Untestable until W2 (no `vibe recall` yet); unit tests verify merge behaviour at the algorithm level |
| Precision: ≤1 irrelevant query in gold cluster | Same as above — algorithm-level verified, integration pending W2 |
| Stability: seed/threshold ±0.02 doesn't collapse | `test_threshold_just_below_boundary_excludes` and `test_threshold_at_boundary_includes` lock boundary behaviour |
| Multi-cluster: ≥2 real clusters verified | Pending W2 integration test with real spans.jsonl data |
| Manual edge case sampling: 5 boundary pairs | Pending — will do during W2 acceptance |

The kill-switch criteria really need W2 to evaluate (they're about
recall behaviour, not algorithm correctness). W1 only delivers the
algorithm primitives. Confirm this scoping is correct.

## Files changed

**New**:
- `src/vibesop/core/observability/embedding.py` (250 lines)
- `src/vibesop/core/observability/clustering.py` (200 lines)
- `src/vibesop/core/observability/gold_detection.py` (90 lines)
- `tests/core/observability/test_embedding_cache.py` (180 lines)
- `tests/core/observability/test_clustering.py` (200 lines)
- `tests/core/observability/test_gold_detection.py` (130 lines)

**Modified**:
- `src/vibesop/core/instinct/learner.py` (+12 lines: `get_instinct_for_query` method)

## Review focus

1. **Lock pattern correctness** (`embedding.py:_flush_locked`):
   - Sidecar `.lock` file — acceptable?
   - Re-read under lock — correct merge logic?
   - Race tolerance assumption (deterministic embeddings) — sound?

2. **Threshold inclusivity** (`clustering.py`): `>= threshold` vs `> threshold`

3. **Dynamic attribute attachment** (`gold_detection.py`): proper dataclass field vs dynamic attr?

4. **Lazy import pattern** (`embedding.py:_compute`): fastembed imported inside function body, returns None on ImportError. Acceptable for optional dep?

5. **Centroid non-persistence** — should we cache, or re-derive in W2?

6. **Test coverage gaps**:
   - No test for `_merge_external_locked` (cross-process concurrent writes)
   - No test for `embed_batch` with mixed hit/miss pattern
   - No test for malformed cache file (corrupted `.npz`)

7. **Scoping**: W1 only delivers algorithm primitives. Kill-switch criteria (recall precision, multi-cluster validation) deferred to W2 integration. Is this acceptable, or should W1 include a smoke test against real spans.jsonl?

## How to run

```bash
# Tests only
uv run pytest tests/core/observability/test_embedding_cache.py \
              tests/core/observability/test_clustering.py \
              tests/core/observability/test_gold_detection.py -v

# With semantic extra (real fastembed)
uv sync --extra dev --extra semantic
uv run python scripts/benchmark_embeddings.py
```
