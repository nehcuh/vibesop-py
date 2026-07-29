# W2 Implementation Review — Merged Findings

**Reviewers**: grok (full pass), pi (full pass)
**Date**: 2026-07-29
**Phase**: task-memory-loop v3 → W2 Recall CLI
**Verdict**: ✅ **PASS after P0 + P1 punch-list cleared**

## Reviewer verdicts

| Reviewer | Verdict | P0 | P1 | P2 |
|----------|---------|----|----|----|
| grok | CONDITIONAL PASS | 1 | 4 | 6 |
| pi | PASS (no blockers) | 0 | 1 (overlaps grok P1-4) | 5 |

Both agreed `_filter_recent` edge cases need tests (P1-4). Grok caught the JSON/ANSI leak that pi missed; pi caught less but agreed on the meta-points.

## Resolved in this round

### P0-1: JSON output emits Rich ANSI codes in TTY mode ✅
**Evidence (grok)**: `console.print(json.dumps(...))` wraps payload with `\x1b[1m{...}` when stdout is a TTY, breaking `vibe recall --json | jq`.
**Fix**: Replaced 3 `console.print(json.dumps(...))` calls with plain `print(json.dumps(...))` in recall_cmd.py (matches main.py:198/615/815 pattern for route JSON).
**Files**: `src/vibesop/cli/commands/recall_cmd.py` (3 sites)

### P1-1: JSON schema drift between brief and code ✅
**Evidence (grok)**: Brief specified `{"matches", "total"}`, code emitted `{query, threshold, days, matches}`.
**Decision**: Keep enriched schema `{query, threshold, days, total, matches}` — debugging context is useful, and `total` is now included. Brief was the source of truth mismatch, not the code. Schema documented in CLI `--help` examples + this doc.
**Files**: `src/vibesop/cli/commands/recall_cmd.py` (added `total: len(results)`)

### P1-2: Empty representative_query still scored ✅
**Evidence (grok)**: `_group_by_task_id` kept task_ids with `query=""`, embedding empty strings as noise.
**Fix**: Added `if not rep_query: continue` skip in `_group_by_task_id`.
**Test**: `test_task_id_with_empty_query_skipped` in `test_recall.py::TestEmptyQuerySkipped`.
**Files**: `src/vibesop/core/observability/recall.py`, `tests/core/observability/test_recall.py`

### P1-3: Gold column always blank in CLI ✅
**Evidence (grok)**: Recall never populates `is_gold` (defaults False — D5 decision), so the Gold column was always empty, confusing users.
**Fix**: Hide Gold column dynamically when no result has `is_gold=True`. Future W3 callers that fuse is_gold will trigger the column automatically.
**Files**: `src/vibesop/cli/commands/recall_cmd.py` (`_render_results`)

### P1-4: `_filter_recent` edge cases untested ✅
**Evidence (grok + pi)**: Missing/malformed/future timestamp branches had no unit tests.
**Fix**: Added `TestFilterRecentEdgeCases` class with 4 tests covering missing ts, malformed ts, future ts, empty ts string. All confirm "keep" behavior (don't drop data on formatting quirks).
**Files**: `tests/core/observability/test_recall.py`

## Deferred to debt / later phases

| ID | Issue | Phase |
|----|-------|-------|
| P2-1 / D1 | Hoist `_extract_query` to shared util | When 3rd caller appears (likely W3 or W4) |
| P2-2 / D3 | Document `datetime.min` fallback puts undated spans first | Minor docstring tweak, defer |
| P2-3 / D6 | Embedding cache GC for stale entries | W4+ ops debt |
| P2-4 | Table + detail block redundancy for k=3 | UX polish, defer |
| P2-5 | Real fastembed integration test | Out of scope for W2 (mocked only) |
| P2-6 | Add `span_ids` or fetch-by-`task_id` helper | Only if W3/W4 need it |

## Design decisions (D1-D6) — final dispositions

| Dec | Decision | Reviewer consensus | Final |
|-----|----------|-------------------|-------|
| D1 | Duplicate `_extract_query` in recall + clustering | Accept bounded context, hoist later | ✅ Keep |
| D2 | Representative query = first non-empty | Accept (deterministic, matches clustering) | ✅ Keep |
| D3 | `datetime.min` for missing ts | Accept w/ doc caveat (P2-2) | ✅ Keep, document later |
| D4 | sha1 + never-zero embedding in tests | Accept (correct flake fix) | ✅ Keep |
| D5 | Recall doesn't query InstinctLearner | Accept (retrieval primitive concern) | ✅ Keep, hide column (P1-3) |
| D6 | `days=30` window, no cache GC | Defer GC to ops debt (P2-3) | ✅ Keep, defer GC |

## Test verification

```bash
# W2 unit + acceptance smoke + CLI (post-fixes)
uv run pytest tests/core/observability/test_recall.py \
              tests/core/observability/test_recall_acceptance_smoke.py \
              tests/cli/test_recall_cli.py -v
# → 33 passed
```

Full W2-relevant suite (post-fixes):
```bash
uv run pytest tests/core/observability/ tests/cli/test_recall_cli.py tests/cli/test_route_cli_task_id.py -q
# → 232 passed
```

10 consecutive runs of W2 tests confirmed no flakes (sha1 + never-zero fix is stable).

## Commit plan

Single atomic commit covering:
- 2 new src files (recall.py, recall_cmd.py)
- 1 modified src file (cli/main.py: +2 lines for register call)
- 3 new test files (test_recall, test_recall_cli, test_recall_acceptance_smoke)
- 1 fixture (recall_gold_spans.jsonl)
- 1 review brief + 1 merged findings doc

Commit message: `feat(recall): W2 task-memory recall CLI + acceptance smoke`
