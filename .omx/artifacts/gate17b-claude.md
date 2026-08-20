All verification complete. Here is the Gate 17b review.

---

# Gate 17b Review — M12 M2 fix round

## pi BLOCK items — both verified fixed

**BLOCK-1 (embedding-health annotation)** `[executed]`
- `ScanSummary.embedding_degraded` (skill_promote.py:812) set by a pre-clustering probe (skill_promote.py:895-904): one fixed-string `embed` through `cache or get_embedding_cache()`, exception-safe.
- Verified the "cache-hit on rescans" claim structurally: `EmbeddingCache.embed` never caches `None` (embedding.py:86-87), so a degraded probe re-probes and recovers when the backend returns; healthy probes hit the npz cache in later processes. Probe tests cover both directions.
- CLI renders the bold-yellow degraded warning (skill_commands.py:1423-1427); absence tested (`test_no_degraded_warning_when_embedding_ok`).

**BLOCK-2 (M2 exit fallback)** `[executed/inspected]`
- The miss-pool line renders unconditionally (skill_commands.py:1430-1433); rendering tested both with and without degradation.
- Design doc records the exit as deferred with the ≥30-distinct-key recalibration trigger (m12-product-design.md:165-170).

## Nit fixes — all verified on disk `[inspected]`

Miss knobs as validated CLI flags wired to `scan_candidates` kwargs; `miss_admitted_count` counted post-upsert with `miss_rejected_count` for cap refusals (upsert's `gold_rate <= current_min` check at skill_promote.py:369 confirms a 0.0-rate miss always loses — the detection is real); cross-scope dismissed/mute union in `_discovery_rows`; threading.Lock + fcntl with `cross_process_lock` fallback in both `_append` and `observe` (fcntl spy-tested); `since=` window in `count_skill_route_hits` — producer contract verified: `ExecutionRecord.to_dict` writes both `primary_skill` and tz-aware ISO `timestamp` (analytics.py:42-55), and `reviewed_at` is always tz-aware so the comparison can't raise; cwd-only scope disclosure + both-scope dismiss totals; Latin-only length rule (清理吧 survives); band comment matches the calibration artifact (plateau 0.47–0.71 at line 57; 0.70 = upper edge per §5); evidence_score >1.0 note present; both miss predicates cross-reference each other; UTC natural-day declared in `_miss_recurrence_counts`.

Also checked: the miss-path `include_legacy=True` comment "age-out already applied above" is accurate (identical filter at skill_promote.py:885); composite `(project_id, task_id)` keys are consistent between clustering and all scan-side membership filters.

## Verification runs `[executed]`

- `tests/core/observability/` + `tests/cli/test_skill_discover_cli.py`: **479 passed** (6.2s)
- `tests/cli/` full: **710 passed** — matches the packet's claim
- `tests/core/test_session_analyzer.py` + `tests/agent/runtime/test_slash_interception.py` (the only other test files referencing changed modules): 39 passed
- `ruff check` on all changed files: clean; `basedpyright`: 0 errors, 8 warnings (7 pre-existing + 1 new `_extract_query` private-usage at skill_promote.py:866, same tolerated pattern as the pre-existing `_filter_recent` import)
- Full suite: could not independently complete — without `HF_HUB_OFFLINE=1` (env-prefixed commands not allowlisted here) embedding tests crawl through HF hub timeouts (~8%/8min, the known 2026-07-31 issue). Targeted coverage above spans every test file touching the changed modules; packet's full-run claim accepted as stated.

## New issues found (nits)

1. **Gold↔miss same-cluster_id overwrite ordering** (skill_promote.py:1031 vs 1065). If a gold-stable cluster and an admitted miss cluster share the same composite key set → same `cluster_id`, the gold loop upserts first, then the miss upsert's refresh path overwrites the row: `source` gold→miss_recurrence, `gold_rate` >0→0.0, `gold_task_ids`→[], `span_count`→miss-spans-only, and both `promoted_count` and `miss_admitted_count` increment for one row. Reachable when the same queries have instinct successes (gold_rate comes from instinct data, independent of route `has_match`) *and* cross-day route misses — plausible over time. Row stays pending/reviewable, so display-fidelity + count double-report only. Suggest upserting miss candidates before the gold loop, or skipping the miss upsert when a pending row for that id already exists.
2. **`miss_rejected_count` not rendered in scan output** — the field added for the full-pool silent-swallow case surfaces only via `logger.warning` + the generic `capped` line. One-line fix: append `(N refused: pool at cap)` to the miss-pool line when >0.
3. (minor) `_render_discovery_history` re-reads the full `analytics.jsonl` once per promoted row (skill_commands.py:2123) — O(promoted × filesize); fine at current scale.
4. (micro) `scripts/calibrate_discovery_threshold.py` matches `name.startswith("route")` (no colon) vs `is_route_miss_span`'s `"route:"` — diagnostic-script-only drift.

Considered and accepted: AtomicWriter rename+inode race on the observations RMW is the repo's known deferred limitation (dashboard Phase B+1), consistent with the convention both gate17 reviewers signed off on; cross-project pair undercounting in `_miss_recurrence_counts` (task_id without project qualifier) is conservative-direction only.

**VERDICT: PASS_WITH_NITS** (nits 1–4 above; none block M2 exit-deferral bookkeeping or the M3/M4 dependencies)
