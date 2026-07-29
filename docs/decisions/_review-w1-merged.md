# W1 Implementation Review — Merged Findings

**Date**: 2026-07-29
**Reviewers**: grok (complete), pi (unavailable — CLI hung on skills loader)
**Verdict**: Ship after P0/P1 punch-list (all resolved below)

## Pi availability note

Pi CLI repeatedly failed in this session:
- `pi -nt -p < file.md` → intercepted by `vibe route` hook, args parsed as route query
- `pi -nt -p "<long prompt>"` → process ran 5+ min, 0 bytes output, killed
- `pi --no-session --no-tools --print "<short prompt>"` → emitted file-read tool calls
  but no final review text within timeout

Cause appears to be a broken skill in `~/.claude/skills/datayes-industry-onepage/`
(ruamel.yaml scanner error in `agents/openai.yaml` line 4). Pi tries to load
skills on startup, hits the error, and either crashes or hangs.

Per memory `feedback-pi-alone-review-sufficient.md`: when one reviewer is
unavailable, the other alone is sufficient. Grok's review was thorough
(covers all 7 review-focus questions + 5 additional findings). Moving
forward with grok-only verdict for W1.

Action item: file separate issue for the broken pi skill YAML (out of W1 scope).

## Grok findings + resolution

### P0 (must-fix before merge)

#### P0-1: Dynamic attrs on Cluster → proper dataclass fields

**Issue**: `is_candidate`, `gold_task_ids`, `gold_rate` attached dynamically
with `# type: ignore[attr-defined]`. Inconsistent with `is_gold` being a
declared field.

**Fix**: Promoted all four to dataclass fields with defaults.
File: `src/vibesop/core/observability/clustering.py`

```python
is_gold: bool = False
is_candidate: bool = False
gold_task_ids: list[str] = field(default_factory=list)
gold_rate: float = 0.0
```

Removed all `type: ignore` from `gold_detection.py`. Tests still pass (22/22).

#### P0-2: Inline fcntl → cross_process_lock helper

**Issue**: Project already has `vibesop.utils.file_lock.cross_process_lock`
(built after deep-diagnosis-2026-07-24 P0-3 for exactly this pattern).
Embedding cache was inventing a third lock dialect.

**Fix**: Swapped inline `fcntl.flock` for `cross_process_lock` context
manager. Defined OSError policy explicitly:
- Lock fails (RO FS, permission) → log warning + skip flush
- Entry stays in-memory; next embed() retries flush
- Acceptable because embeddings are deterministic (lost update = re-compute)

File: `src/vibesop/core/observability/embedding.py:_flush_locked`

### P1 (should-fix)

#### P1-1: zip(..., strict=True) in gold_detection

**Issue**: `cluster.task_ids` and `cluster.queries` should always be
parallel, but `strict=False` silently allows skew if someone mutates
Cluster by hand later.

**Fix**: Changed to `strict=True` so length skew fails loud.

#### P1-2: Test gap — embed_batch mixed hit/miss

**Issue**: Existing `test_batch_uses_cache` only verified call_count
globally; didn't lock in that hit and miss can coexist correctly.

**Fix**: Added `test_embed_batch_mixed_hit_and_miss` — warms cache for
one query, then batch-embeds [cached, fresh], asserts only fresh triggers
compute. Verifies result order matches input order.

#### P1-3: Test gap — corrupted cache file

**Issue**: `_load` catches KeyError/ValueError/OSError but no test
locked the contract.

**Fix**: Added `test_corrupted_cache_file_starts_cold` — writes garbage
bytes to cache path, constructs EmbeddingCache, asserts empty cache +
working subsequent embed().

#### P1-4: Test gap — _merge_external_locked

**Issue**: Cross-process merge logic untested.

**Fix**: Added `test_merge_external_picks_up_keys_added_by_another_process`:
- Process B writes one entry
- Process A loads (sees 1 entry)
- Process C writes another entry to same file
- Process A calls `_merge_external_locked()` directly
- Asserts A's in-memory cache now has 2 entries

#### P1-5: Test gap — empty query

**Issue**: `normalize_query("")` returns `""` → `_make_key` returns `None`
→ `embed` returns `None`. Behaviour reasonable but not locked.

**Fix**: Added `test_empty_query_returns_none` — asserts empty/whitespace/newline
queries all return None without invoking `_compute`.

#### P1-6: Test gap — OSError policy on flush

**Issue**: New OSError-skip policy (P0-2) needed coverage.

**Fix**: Added `test_readonly_filesystem_skips_flush_gracefully` —
monkeypatches `cross_process_lock` to raise OSError, asserts embed()
still returns vector + in-memory cache populated.

### P2 (nice-to-have, deferred)

- **Normalization split** between `task_id.normalize_query` and
  `InstinctLearner.generate_id`: latent W2 risk if span query and
  instinct pattern differ by punctuation. Documented in code; will
  address in W2 if recall misses gold signal.
- **Real fastembed in unit CI**: correctly skipped (kept in W0
  benchmark script). Confirmed.
- **`_compute_batch` is sequential**: fine for MVP, comment invites
  override for real FastEmbed batching when W2 hits >8 queries/recall.
- **Flush holds thread lock across disk I/O**: acceptable at current
  scale; revisit if recall becomes hot-path concurrent.
- **Centroid non-persistence**: confirmed acceptable — re-derive in W2.

### Additional grok findings (no action needed — confirmed sound)

- Cache key `sha1(model_id + \x1f + normalize(query))[:16]` ✓
- model_id whole-cache invalidation ✓
- Atomic `tmp.npz` + `replace` ✓
- Union-Find soft merge + hard task_id group ✓
- Deterministic `cluster_id` from sorted member tids ✓
- Size gate 5 for gold vs candidate ✓
- `get_instinct_for_query` as Bounded Earned Refactor ✓
- Lazy import + None-on-ImportError for optional fastembed ✓
- Inclusive `>=` threshold (matches "absorb adjacent" intent) ✓
- Scoping: W1 = algorithm primitives only; kill-switch owned by W2 ✓

## Decision matrix (direct answers, all 7 review-focus questions)

| # | Question | Answer |
|---|---|---|
| 1 | Sidecar lock + soft degrade? | Sidecar via `cross_process_lock`; OSError → log + skip flush (entry stays in memory) |
| 2 | `>=` vs `>` threshold? | Keep `>=` (inclusive boundary matches absorb intent) |
| 3 | Dynamic attrs vs fields? | Proper dataclass fields (P0-1) |
| 4 | Lazy fastembed import? | Yes (confirmed) |
| 5 | Cache centroid? | No — re-derive in W2 |
| 6 | Test gaps? | Added 5 gap tests (mixed batch, corrupt npz, merge sim, empty query, RO FS) |
| 7 | Kill-switch in W1? | No — W1 primitives only; kill-switch owned by W2 |

## Final test count

- 40 W1 tests pass (was 35; +5 gap tests)
- 282 instinct/observability/feedback tests pass (no regression)
- 0 type-check errors (all `type: ignore` removed)
