# W2 Implementation Review Brief

**Reviewer**: grok + pi
**Date**: 2026-07-29
**Phase**: task-memory-loop v3 → W2 Recall CLI
**Prior**: W1 shipped at commit 95d619d (EmbeddingCache + cluster_queries + assess_gold_status, 40 tests, grok-only review pass)

## Scope (7 files, ~700 LOC)

| File | Purpose | LOC |
|------|---------|-----|
| `src/vibesop/core/observability/recall.py` | Recall retrieval logic + `RecallResult` dataclass | ~265 |
| `src/vibesop/cli/commands/recall_cmd.py` | `vibe recall` CLI (text + JSON output) | ~210 |
| `src/vibesop/cli/main.py` | Wire `recall_cmd.register(app)` (2-line diff) | +2 |
| `tests/core/observability/test_recall.py` | Recall unit tests (13 tests) | ~200 |
| `tests/cli/test_recall_cli.py` | CLI smoke tests via CliRunner (5 tests) | ~190 |
| `tests/core/observability/test_recall_acceptance_smoke.py` | Fixture-based cluster + recall smoke (10 tests) | ~240 |
| `tests/fixtures/recall_gold_spans.jsonl` | 20 spans: 12 cmspark + 5 lid_sleep + 3 distractors | 20 lines |

## Contract to verify

### 1. `recall_similar(query, spans, cache=None, top_k=3, threshold=0.70, days=30) -> list[RecallResult]`

**Spec** (from v3 design §3 W2):
- Returns top-k similar past `task_id`s by cosine on representative query embedding
- Default absolute threshold `0.70` filters weak matches ("默认未达阈值视为无召回，防错召回污染信任")
- `days=30` look-back window excludes older spans
- Empty spans → empty list
- Embedding library missing (`embed()` returns `None`) → empty list with debug log (no crash)

### 2. `RecallResult` dataclass

Fields: `task_id`, `similarity`, `representative_query`, `span_count`, `step_sequence`, `last_seen`, `is_gold`

- `step_sequence` = span names in temporal order (oldest first)
- `last_seen` = ISO timestamp of most recent span
- `is_gold` defaults to `False` — recall itself doesn't query `InstinctLearner`; populated downstream by W3+ callers

### 3. CLI `vibe recall`

```
vibe recall "<query>" [--top-k N] [--threshold F] [--days N] [--json] [--span-file PATH] [--limit N]
```

- Text output: Rich Table with sim/task_id/query/spans/last_seen/gold columns
- JSON output: `{"matches": [...], "total": N}` for programmatic use
- `--span-file` allows tests to bypass CWD-singleton state (pytest runs under repo root would otherwise pick up dev spans)

### 4. Acceptance smoke (kill-switch replacement)

Original W2 design called for "follow rate ≥ 30%" kill-switch, which requires real users + product telemetry. **Replaced** with fixture-based smoke (same pattern as Dashboard v3 Phase A Task 13) that proves the algorithmic preconditions hold:

- 12 cmspark screenshot-permission queries (EN+ZH) cluster into ≥10 task_ids
- 5 lid_sleep overheating queries cluster into ≥5 task_ids
- ≥2 non-trivial clusters form
- Distractors (rust/postgres/react) don't merge with gold
- Recall finds correct cluster for screenshot/overheating queries

## Design decisions to scrutinize

### D1. `_extract_query` duplicated in recall.py and clustering.py

Both modules have a private `_extract_query(span) -> str | None` that handles `input_data` as dict or JSON string. Recall's docstring says "kept local to avoid cross-module coupling". Worth a second opinion — is this appropriate bounded-context separation, or should it be hoisted to a shared util?

### D2. Representative query = first non-empty query (not most recent)

`_group_by_task_id` picks the first non-empty raw query from the group as `representative_query`. Alternative would be most-recent (recency bias) or mode (most common phrasing). First-seen was chosen for determinism + simplicity. Is this the right call?

### D3. `step_sequence` uses timestamp sort with `datetime.min` fallback

```python
def _ts_key(s: dict) -> datetime:
    ts = _parse_timestamp(s.get("timestamp", ""))
    return ts or datetime.min.replace(tzinfo=UTC)
```

Spans without timestamps sort to the front (oldest position). For spans WITH mixed timestamp/no-timestamp, this puts no-timestamp spans first. Acceptable or surprising?

### D4. Flaky test fix: `hash()` → `hashlib.sha1` + never-zero scalar

`tests/cli/test_recall_cli.py` originally used `hash(query) & 0xFFFF % 10` for fake embeddings, which flaked 30% in full-suite runs (Python's `hash()` is process-randomized via `PYTHONHASHSEED`, and `% 10` had 10% chance of producing a zero vector → cosine undefined). Fixed by using `hashlib.sha1` and `v[0] = (h % 9) + 1` (range 1-9, never zero). Verified with 10 consecutive successful runs.

Note: `tests/core/observability/test_recall.py` still uses `hash(query)` but produces unit vectors via `_unit_vec(angle)` — vector is never zero regardless of seed, and assertions are on same-string cosine=1.0 which is deterministic. So this is OK.

### D5. Recall does NOT consult `InstinctLearner` for `is_gold`

W1's `assess_gold_status` populates `is_gold` on clusters. Recall deliberately leaves `is_gold=False` on all results — callers that care about gold can run `assess_gold_status` on the spans first and cross-reference by `task_id`. Rationale: recall is a retrieval primitive; gold-status is a separate concern. Push-back welcome if you think recall should fuse them.

### D6. Default `days=30` vs cache longevity

Spans older than 30 days are excluded from recall. Embeddings in the cache may persist longer (no automatic GC). This means cache can grow unbounded if old task_ids are never recalled. Worth flagging as debt or addressing now?

## Review focus questions

1. **Correctness**: Does `_filter_recent` correctly handle the edge cases (no timestamp, malformed timestamp, future timestamp)?
2. **Determinism**: Is the cluster_id derivation in clustering.py still stable given recall's new caller patterns? (recall doesn't add clusters, just consumes them — should be fine, but worth confirming)
3. **Concurrency**: Recall reads spans while `SpanWriter` may be appending. Is the JSONL read safe under concurrent appends? (Spans file is append-only; json.loads on partial line would fail — we currently skip unparseable lines in SpanWriter.query_recent, I believe)
4. **CLI UX**: Is the text table readable for the typical case (3 results)? Any fields that should be truncated or hidden by default?
5. **Test coverage gaps**: The acceptance smoke uses mocked keyword embeddings (`_keyword_embedding`) rather than real fastembed. Are there code paths only exercised by real embeddings that we're missing?
6. **API stability**: Is `RecallResult`'s field set right for W3 (replay mode) and W4 (skill promote) consumers? Anything obviously missing that we'd regret not adding now?

## How to run

```bash
# Unit tests
uv run pytest tests/core/observability/test_recall.py tests/cli/test_recall_cli.py -v

# Acceptance smoke
uv run pytest tests/core/observability/test_recall_acceptance_smoke.py -v

# CLI smoke (manual)
uv run vibe recall "screenshot permission popup" --span-file tests/fixtures/recall_gold_spans.jsonl --json
```

## Out of scope for W2

- W3: `vibe route --replay` one-key replay on gold cluster hit
- W4: `cluster_size ≥ 3 AND gold_rate ≥ 60%` triggers skill promote
- Real fastembed integration test (deferred to manual benchmark)
- Cache GC for stale embeddings (D6 above)
