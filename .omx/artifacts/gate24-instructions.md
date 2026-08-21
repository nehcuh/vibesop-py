# Gate 24 review — M3 behavior-consistency gate (bigram-Jaccard)

You are an independent senior code reviewer. Review the attached diff (git diff of the working tree) for the VibeSOP project (Python CLI, `vibe`).

## Context

M3 of the M12 milestone (design: `.omx/artifacts/m12-product-design.md` lines 60-145): a behavior-consistency gate for skill discovery candidates. If the same missed-routing pattern recurs AND the agent handled each recurrence with a similar tool-call sequence, the candidate is a more trustworthy workflow. Tool spans (`span_kind="tool_call"`, name `tool:Grep` / `tool: grep_search`, carry `task_id`/`session_id`/`trace_id`/`parent_span_id`/`started_at`) are joined to a candidate cluster's route spans via `ClusterCandidate.task_ids` → per-trace ordered tool-name sequences → bigram sets → pairwise Jaccard → mean aggregation → three-state evidence:

- `consistent` — ≥2 valid sequences AND mean pairwise Jaccard ≥ threshold
- `divergent` — enough data but below threshold (**design doc named only consistent/unavailable; the implementer added divergent because "has data, below threshold" cannot honestly be labelled unavailable — assess this**)
- `unavailable` — <2 valid sequences (e.g. platform without hooks; single-tool traces have empty bigram sets and don't count)
- field absent (None) = 未采集 (pre-existing label path)

Threshold: design start 0.5, MUST be calibrated before fixing. Calibration ran self-supervised (within-cluster trace pairs = positive, cross-cluster = negative) on real cmspark data (159 tool spans, 10 traces, 25 candidates): **0 positive pairs, 1 negative pair (0.300)** → decision-band evidence insufficient → 0.5 kept as UNVALIDATED starting point, recorded in `.omx/artifacts/m3-behavior-calibration.md` with a recheck trigger (rerun once any candidate cluster has ≥2 sequences). Aggregation = mean (no calibration data to discriminate; min too veto-sensitive, median == mean at n=2) — rationale in comments. Cleaning decision: consecutive duplicate tool names folded (a real trace had 50 consecutive Reads; 99/157 consecutive-duplicate pairs would drown the bigram set); non-consecutive repeats kept.

Files: new `src/vibesop/core/observability/behavior_consistency.py` + `scripts/calibrate_behavior_threshold.py`; `skill_promote.py` (ClusterCandidate.behavior_evidence/behavior_score with validation + legacy-None compat; scan_candidates `behavior_threshold` kwarg; fill at gold :~1288 / miss :~1336 build points; `behavior_spans` captured BEFORE the W5.1 age-out filter so legacy tool spans without project_id aren't mis-filtered; rescan overwrites with latest value — opposite of first_seen_at's earliest-wins, by design); `skill_commands.py` (`--behavior-threshold` flag with [0,1] validation, `_render_behavior` divergent branch); `discovery.py` (divergent label). Dashboard passes row.behavior through unchanged. Tests: test_behavior_consistency.py (11), test_calibrate_behavior_threshold.py, TestBehaviorEvidence in test_scan_candidates.py, serialization cases, CLI 4-state render. 1333 passed across cli/core-observability/dashboard/scripts suites; touched files ruff-clean.

Real scan on cmspark (--limit 8000, 793 clusters): 20 pending rows got `unavailable`, 8 unscanned legacy rows keep None (未采集); consistent/divergent = 0 occurrences — honest given kimi hooks never loaded (only claude/grok emit tool spans).

## Invariants that must hold

- Privacy: tool names only, never tool_input/params (design 隐私边界).
- Admission/eviction/kill-switch logic untouched; behavior is evidence annotation, not a gate on admission (M3 is a card-level evidence label, NOT an admission filter — verify the diff didn't accidentally wire it into admission).
- Legacy candidates (no behavior keys) must round-trip; invalid behavior_evidence values rejected.
- `is_route_miss_span` / bridge `_is_miss` untouched.

## Review focus

1. The divergent third state — is the design-contract deviation justified and consistently applied (label, render, dashboard, tests)?
2. Join correctness: parent_span_id primary / trace_id fallback — can a tool span be mis-attributed across tasks or sessions? Orphan handling?
3. Consecutive-fold cleaning: does folding bias Jaccard in a systematic direction? Is single-tool-trace exclusion (empty bigrams) the right call vs counting as trivially consistent?
4. Mean aggregation with n=2 sequences — any degenerate behavior? Threshold knob validation.
5. The pre-age-out capture of behavior_spans — does it leak spans the W5.1 filter was meant to exclude into any OTHER consumer, or is it scoped only to behavior evaluation?
6. Calibration script discipline: does it refuse to conclude on thin samples? Is the self-supervised labeling sound (cluster labels from candidate pool task_ids)? Any leakage (pairs counted twice, self-pairs)?
7. Test quality: do the 11 unit cases + scan integration cases lock the three states and the join rules?

## Output

Verdict: PASS / PASS_WITH_NITS / BLOCK, then numbered findings with severity (BLOCK/MAJOR/NIT), file:line refs, one-line residual-risk note. Be adversarial; do not rubber-stamp.
