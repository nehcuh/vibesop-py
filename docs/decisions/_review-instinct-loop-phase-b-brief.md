# Phase B Milestone — Review Brief

**Date:** 2026-07-23
**Scope:** Instinct learner cross-process file lock + .bak rotation + decay_frequent/hash_for API
**Plan v2:** `/Users/huchen/.claude/plans/starry-herding-stream.md` §3, §4
**Phase A merged:** commit `fdafbcb` (approved by kimi+pi SHIP TO PHASE B)
**Phase B diff:** 675 lines (`git diff HEAD -- src/vibesop/core/instinct/learner.py src/vibesop/core/skills/miss_counter.py tests/core/test_instinct_learner.py tests/core/skills/test_miss_counter.py tests/core/loop/test_executor.py`)
**Verification:** 4484 passed / 13 skipped (full suite), ruff clean, basedpyright 0 errors

## What Phase B changes

### `src/vibesop/core/instinct/learner.py`

1. **Cross-process file lock** (`_cross_process_lock` context manager): `fcntl.flock` on a sibling `.lock` file. POSIX only; Windows no-op (matches `core/observability/span_writer.py` precedent). OSError during acquisition falls through to "yield anyway" (degraded mode preferred over total failure).

2. **`.bak` rotation** (`_backup_locked`): before each overwrite, `data_path` is copied to `data_path.bak`. Single-step recovery point. No-op when data file doesn't exist yet.

3. **Clear-epoch guard** (`_read_clear_epoch`, `_bump_clear_epoch_locked`): generation counter at `.vibe/clear_epoch`. `clear()` increments it after file deletion; `_save()` checks it before merge and drops stale in-memory state if disk's epoch is newer. Solves the CRITICAL regression where a concurrent in-memory learner would resurrect purged data via merge.

4. **Merge step** (`_merge_disk_into_memory_locked`, `_merge_disk_sequences_into_memory_locked`): on every save, re-read disk and pull in disk-only IDs. In-memory wins for shared IDs. **Known limitation (documented)**: shared-ID concurrent counter updates (e.g., A's `record_outcome(True)` racing B's `record_outcome(False)`) silently lose one side — delta-merge deferred.

5. **Rewrote `_save()`**: takes both `self._lock` (in-process RLock) and cross-process flock. Checks epoch → merges disk → backs up `.bak` → writes data + sequences.

6. **Rewrote `clear()`**: holds both locks, unlinks `instincts.jsonl`, `.bak`, `sequences.jsonl`, `.bak`, bumps epoch. Skips `_save()` (no merge — privacy purge must not preserve anything).

7. **Fixed `record_sequence`**: now holds both locks + runs sequence merge. Was lock-free at the cross-process level — HIGH bug found by adversarial review.

8. **Fixed pre-existing `_load()` bug**: was short-circuiting on missing `instincts.jsonl` and skipping `_load_sequences()`, silently dropping all sequences on next startup if no instincts existed.

### `src/vibesop/core/skills/miss_counter.py`

- `decay_frequent(min_count=3) -> list[MissedHashCluster]`: halves counts for clusters at/above min_count, returns pre-decay list (so caller can correlate). Replaces `clear()` for the feedback loop (kimi/pi plan v2 MUST-FIX D).
- `hash_for(normalized_query) -> str`: public wrapper around `_hash` for `feedback-collect` to match instinct patterns against `frequent()` hashes.

### Tests

- `tests/core/test_instinct_learner.py` — added `TestInstinctLearnerCrossProcessLock` (7 tests):
  - `.bak` rotation (after second save, not first)
  - `_save` no-op `.bak` when file missing
  - Cross-process merge preserves disk-only IDs
  - Lock file is sibling (`.jsonl.lock`)
  - Concurrent saves from two instances don't lose data
  - **Clear-epoch guard prevents resurrection** (regression test for FLAW #1)
  - **`record_sequence` uses cross-process lock** (regression test for FLAW #3)

- `tests/core/skills/test_miss_counter.py` — 4 new tests: `decay_frequent` halves + idempotent, `hash_for` matches `_hash` + deterministic across instances

- `tests/core/loop/test_executor.py` — 1 deferred Phase A test: `test_command_target_unicode_args_pass_through_unchanged`

## Adversarial review (Phase B.5)

Agent (opus) verdict: **FIX BEFORE EXECUTE** with 3 confirmed flaws:

| # | Severity | Description | Resolution |
|---|----------|-------------|------------|
| 1 | CRITICAL | `clear()` defeated by concurrent in-memory learner (merge resurrects purged data) | **Fixed**: clear-epoch generation counter |
| 2 | HIGH | Shared-ID concurrent counter updates silently lost (in-memory wins semantic) | **Documented** as known limitation; delta-merge deferred unless you flag P0 |
| 3 | HIGH | `record_sequence` bypassed cross-process lock | **Fixed**: now holds lock + runs sequence merge |
| 4 | LOW | `clear()` doesn't unlink `.lock` file | Accepted — `.lock` has no user data, cosmetic only |
| note | (pre-existing Phase A) | `_load()` skipped `_load_sequences()` when instincts.jsonl absent | **Fixed** as side-effect of FLAW #3 regression test surfacing it |

## Key questions for kimi+pi

1. **Clear-epoch approach (FLAW #1 fix)**: Is a generation counter at `.vibe/clear_epoch` the right shape? Alternatives considered: tombstone marker, mtime comparison, drop-merge-entirely. We picked epoch because it's monotonic, atomic via `write_text`, and survives across process restarts.

2. **FLAW #2 (shared-ID counter loss) deferral**: We documented the limitation in `_merge_disk_into_memory_locked` docstring. Trigger requires two writers mutating the SAME instinct's counters within the same load-save window — unlikely given the daily 04:37 feedback-collect schedule vs daytime interactive use. Is "document + defer delta-merge" acceptable, or do you require delta-merge in Phase B?

3. **Cross-process lock degradation**: If `fcntl.flock` raises `OSError`, we yield anyway (degraded). Is this acceptable, or should we abort the operation?

4. **`record_sequence` clear-epoch check**: We mirror `_save`'s epoch check inside `record_sequence`. Should this be factored into a shared helper, or is the duplication acceptable for v1?

5. **`.bak` rotation policy**: One `.bak` per file (overwritten each save). No rotation history. Is single-step recovery sufficient, or do you want N-generation rotation?

6. **Test coverage**: We test epoch guard + record_sequence lock via in-process simulation (two `InstinctLearner` instances, no fork). Should we add a true multi-process test (subprocess) for stronger guarantee?

## Phase B assets

- `src/vibesop/core/instinct/learner.py` — flock + .bak + epoch + merge + record_sequence lock + _load fix
- `src/vibesop/core/skills/miss_counter.py` — decay_frequent + hash_for
- `tests/core/test_instinct_learner.py` — 7 new tests in `TestInstinctLearnerCrossProcessLock`
- `tests/core/skills/test_miss_counter.py` — 4 new tests
- `tests/core/loop/test_executor.py` — 1 new test (Phase A deferred unicode)
- `.gitignore` — added `.vibe/*.lock`, `.vibe/sequences.jsonl*`
- `docs/decisions/_review-instinct-loop-phase-b-brief.md` — this brief

## Verdict sought

Per the workflow protocol (plan v2 §"执行顺序"):
- **SHIP TO PHASE C**: Phase B is correct enough to proceed to launchd plist generation.
- **CONDITIONAL**: list specific must-fix items, we address and re-review.
- **REJECT**: Phase B has fundamental design issues requiring re-plan.

Please focus on:
- Concurrency correctness (clear-epoch, record_sequence lock, shared-ID counter loss)
- Privacy/F-08 soundness (clear() actually purges everything)
- Test coverage realism (in-process simulation vs multi-process)
- Any blockers for adding launchd on top of this in Phase C
