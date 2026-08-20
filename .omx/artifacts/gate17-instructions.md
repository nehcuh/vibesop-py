# Gate 17 Review — M12 M2: miss-cluster admission + Discovery CLI + calibration

You are reviewing milestone M2 of the M12 design (repo: /Users/huchen/Projects/vibesop-py). Design: `.omx/artifacts/m12-product-design.md` (v3). The full diff is appended. Read any file; DO NOT modify anything.

## What was implemented (three parallel paths + orchestrator integration)

**M2a — miss-cluster admission gate** (`skill_promote.py`, `gold_detection.py`):
- `is_route_miss_span` predicate: route span AND `has_match is False` AND `mode != "not_intercepted"`; missing has_match = unknown, never miss (conservative); metadata dict-or-JSON-string.
- `scan_candidates` clusters miss-only spans separately at `MISS_COSINE_THRESHOLD` and admits clusters where: distinct (task_id, natural-day) pairs ≥ 3 **AND** ≥ 2 distinct days (conjunction — gate15b's false-implication trap). Admitted candidates: `source="miss_recurrence"`, gold_rate 0.0 (honest), enter the human-visible stable queue. Gold path untouched. Same-day/cross-day synthetic injection tests (9 cases).
- Real-data dry-run: miss pool 6 spans → after low-info filter 4 → clusters: cmspark pair (2 pairs, 1 day, NOT admitted), 2 singletons → 0 admitted (honest, expected for the tiny pool).

**M2b — unified Discovery CLI** (new `core/observability/discovery.py` + `vibe skill discover` in `skill_commands.py`):
- Queue cards: pattern summary + evidence strength (query evidence, behavior evidence field if present, [XP]) + source metrics + capture age; evidence_score = 0.45·min(spans/10,1) + 0.25·min(distinct_tasks/3,1) + 0.30·source_weight + 0.10·[XP].
- dismiss: sticky negative list (`.vibe/observability/discovery_dismissals.jsonl`, fingerprint = sha1 of sorted normalized query set; dismiss count ≥5 → suggests raising admission threshold, never auto-changes). --mute (14-day temporary, distinct from dismiss). 14-day no-new-members cooldown (observation store). --history: promoted/dismissed record + precision metric + post-promote route-hit≥5 closed-loop via analytics.jsonl primary_skill (honest "no data source" when absent). Empty-queue guidance. 40 new tests.

**M2c — cosine threshold calibration** (`scripts/calibrate_discovery_threshold.py` + `.omx/artifacts/m12-threshold-calibration.md`):
- 48 hand-labelled pairs (20 merge / 28 no-merge) from real miss pool + weak hits + eval expect=[] queries. Distributions overlap 0.41–0.79, minimum-error band 0.60–0.71 → **recommended 0.70** (upper edge: merge errors cost more than splits under Union-Find chaining). Explicitly REJECTED the 0.82 starting point (splits 17/20 same-intent pairs). Edge pairs documented. Real-miss-only pairs <10 → declared "prior band + recalibration plan at ≥30 distinct misses", no fake significance.

**Orchestrator integration** (after the three paths):
- `MISS_COSINE_THRESHOLD` 0.82 → **0.70** with calibration citation.
- Low-information pre-pool filter (`_is_low_information_query`): degenerate continuations ("继续"/"可以"/"ok") cosine-match EVERYTHING at 0.72–0.82 (calibration finding) — filtered before pooling; test added.
- `<user_query>` envelope unwrap in `_extract_query` (clustering.py): legacy spans' shared wrapper tokens inflated cosine so much that ALL wrapped queries merged into one garbage cluster (measured: "继续" merged with cmspark queries at 0.70) — unwrap whole-string envelopes; test added.
- M2 prerequisite: fastembed default model name → namespaced `sentence-transformers/…` (bare name raised, silently killing ALL embeddings — gate16 finding); supported-list smoke test added (no download needed).

## Verification claims

- Targeted suites green (observability 443+, cli 701, admission 9, discovery 25+15); full pytest running at packet time (baseline 5681).
- ruff clean on touched files.

## Review focus

1. The admission gate: conjunction correctness, task_id/day counting edge cases (no-timestamp spans, UTC day boundaries), gold-path non-interference, dry-run semantics.
2. Discovery CLI: evidence_score sanity, dismiss fingerprint stability vs cluster_id drift, mute/dismiss/cooldown interactions, history metric honesty.
3. Calibration methodology: is the 48-pair set defensible? Is 0.70 within the evidence? Anything about the labeled pairs that smells like overfitting to this dogfood project?
4. The envelope unwrap: any legitimate query harmed? Interaction with task_id (unchanged, span-field derived)?
5. The low-info filter: len≤4 + list — too aggressive / too weak? CJK edge cases?
6. Scope: anything beyond M2? Honest reporting of the 0-admitted real-data outcome?

## Verdict format

End with exactly one of: `VERDICT: PASS`, `VERDICT: PASS_WITH_NITS` (list nits), `VERDICT: BLOCK` (file:line + reasoning).
