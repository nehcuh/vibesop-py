# Gate 17b Confirmation Review — M12 M2 fix round

Repo: /Users/huchen/Projects/vibesop-py. The appended diff is the FULL current diff vs HEAD (supersedes gate17.diff). Gate17 verdicts: pi BLOCK (2 contract items + 8 nits), claude PASS_WITH_NITS (10 nits). All items addressed. Verify and check for new issues. DO NOT modify anything.

## pi BLOCK items — fixed

1. **Embedding-health annotation** (design: degradation must be explicit in scan output, not per-query warnings): `ScanSummary.embedding_degraded` — `scan_candidates` probes the cache once with a fixed text (cache-hit on rescans); degraded → WARNING log + the scan-candidates CLI prints a prominent degraded-mode warning ("soft-merge 未生效,簇仅按 task_id 硬分组"). Tests: probe both directions.
2. **M2 exit fallback formalized**: scan-candidates CLI now always renders `miss pool: N span(s) → M miss_recurrence candidate(s) admitted` (the silent-spin instrumentation); the design doc records the M2 exit criterion as **deferred** (0 real-data admissions, recalibrate + re-verify at ≥30 distinct real misses) — `.omx/artifacts/m12-product-design.md` milestone table.

## Nits fixed (both reviewers, deduplicated)

- miss knobs as CLI flags (`--miss-cosine-threshold/--miss-min-pairs/--miss-min-days`, validated, wired to scan_candidates kwargs); `threshold_suggestion` is now source-aware (miss candidates get miss-knob advice, told gold knobs don't apply).
- `miss_admitted_count` only increments on actual store upsert (new `miss_rejected_count` for cap rejections; full-pool miss-rejection behavior documented in the constants comment).
- `_discovery_rows` now really wires both scopes' dismissed/muted fingerprints into `build_queue` (cross-scope dismissal works in one dismissal).
- `DiscoverySignalStore._append` + `DiscoveryObservationStore.observe`: threading.Lock + fcntl.flock with cross_process_lock fallback (repo's double-lock convention).
- `count_skill_route_hits` gains a `since=` window (history passes reviewed_at; bad timestamps counted conservatively; output says "提升后 N 次命中").
- History output discloses the cwd-only analytics scope for global promotes; dismiss threshold suggestion uses a both-scope dismiss total.
- Low-info filter: length rule is now Latin-only (CJK short intents like 清理吧 survive; calibration-pair-driven).
- Calibration band comment corrected (0.47–0.71 plateau, not 0.60–0.71).
- evidence_score docstring corrected (miss+XP 1.04 can outrank non-XP gold 1.00 — intentional, noted).
- Two miss predicates cross-referenced in docstrings (bridge `_is_miss` excludes CLI/slash for outcome derivation; scan `is_route_miss_span` keeps CLI misses as legitimate discovery signal — deliberate difference stated).
- UTC natural-day: declared choice, documented in code (left as-is per both reviewers' "documented" acceptance).

## Verification

- Fix-round targeted suites: observability 448→456, cli 710; 17 new tests. Full pytest running at packet time (pre-fix round: 5733 passed / 0 failed).

## Verdict format

End with exactly one of: `VERDICT: PASS`, `VERDICT: PASS_WITH_NITS` (list nits), `VERDICT: BLOCK` (file:line + reasoning).
