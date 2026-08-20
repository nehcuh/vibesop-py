Review complete. All areas examined, targeted tests executed, real-data claims independently reproduced.

# Gate 17 Review — M12 M2

## What I verified [executed]

- **Targeted suites**: 115 tests pass across `test_miss_recurrence_admission.py` (9), `test_discovery.py` (25), `test_skill_discover_cli.py` (15), plus clustering/scan-candidates/embedding-cache/gold-detection. No full-suite run by me (packet says it was in flight).
- **Ruff**: clean on all diff-authored lines. The one error (`PLW0603`, embedding.py:271) exists at HEAD (line 267 pre-diff) — pre-existing, not this milestone's.
- **Real-data claims reproduced exactly**: 175 spans → 6 miss spans (all `single_agent` mode) → 4 after low-info filter; the two cmspark queries share 1 day (2 pairs, 1 day → not admittable), others singletons. 0 admitted is the correct outcome, honestly reported.
- **`slash_command` safety**: confirmed via producer code (agent_runtime.py:466-481 returns before the `has_match` write at :597) and real data (zero `slash_command` spans carry `has_match=False`) — see finding 7.

## Findings by focus area

### 1. Admission gate — sound

Conjunction is correct (`pairs >= miss_min_pairs and days >= miss_min_days`, skill_promote.py:891) and the 9 synthetic tests pin exactly the gate15b trap cases: same-day multi-key burst (3 keys/1 day → blocked by day condition), same-key repeat spam (dedup → 1 pair), cross-day admission, threshold overrides. Exclusions verified: unknown (`has_match` missing), `not_intercepted`, hits, and low-info queries all stay out of the pool.

Gold-path non-interference verified: the supersession skip (skill_promote.py:913-919) sits only in the `gold_rate < unstable_gold_rate` branch; the stable branch is untouched. The subset check is sound given miss clustering (0.70) is guaranteed coarser than gold clustering (0.80) on the miss-key subset.

Edge observations (nits, not blockers):
- **UTC day boundary**: `ts.date()` on UTC — for a UTC+8 user the day flips at 08:00 local. An early-morning (07:00–09:00 local) iterative-rephrasing burst crosses the boundary and can satisfy the ≥2-day condition, cutting in the permissive direction the design works to block. Documented in the docstring ("Natural days are UTC dates"), so it's a declared choice, but worth revisiting for local dates.
- **Cap interplay**: miss candidates carry `gold_rate=0.0`, so at `MAX_PENDING` the admit-only-if-better check (`0.0 <= min`) rejects every miss upsert — the flagship M2 feature dies first under a full pool. Also `miss_admitted_count` increments before the store may silently reject the upsert, and the supersession skip + a cap rejection together can drop a pattern from *both* buckets (unstable skipped, miss rejected). Narrow, but the flag's meaning drifts under load.

### 2. Discovery CLI — works; one documented invariant is unwired

- **evidence_score**: sane ordering; small wrinkle that `len(candidate.task_ids)` counts duplicates for cross-project clusters (same query-derived task_id per project), so a one-query cluster in 3 projects maxes `task_term` and gets the XP bonus. Sort-key only.
- **Fingerprint vs cluster_id drift**: the query-set fingerprint is the right call (cluster_id churns on rescan). The documented failure mode — cluster growth changes the query set → dismiss "leaks" and the candidate re-nags — is real and acknowledged; note it also inflates `dismiss_count`, which drives the threshold suggestion.
- **`extra_dismissed`/`extra_mutes` are dead in production** (skill_commands.py:1865 is the only caller and passes neither). `build_queue`'s docstring claims "a fingerprint dismissed in either scope is treated as dismissed" — that invariant does not hold. It only bites when the dedup winner flips between scopes (heterogeneity change between dismiss-time and list-time), but the documented semantics and the code disagree. Either wire it or fix the docstring.
- **History honesty**: good — None-vs-0 distinction, rename caveat printed, precision mixes both dismiss mechanisms defensibly. Gap: `analytics_path` is cwd-only (skill_commands.py:~1990), so global-scope promotes are checked against one project's analytics — undercount not disclosed in output.
- **Concurrency deviation**: `DiscoveryObservationStore._save` is a whole-file read-modify-write with only a `threading.Lock` — no cross-process lock, unlike every sibling store (`ClusterCandidateStore`, `ReflectionStore`, `EmbeddingCache`). `DiscoverySignalStore._append` also drops the `cross_process_lock` fallback the siblings use on non-POSIX. This is the exact RMW race class recorded as CRITICAL in W5.1 (pool.yaml) and Phase B. Blast radius here is low (derived cooling state, lost updates self-heal; atomic rename prevents corruption), but it re-opens a closed bug class.

### 3. Calibration — defensible and honest, within its limits

The artifact is disciplined: distributions + band not a bare point, blade pairs recorded, 0.82 explicitly rejected with the 17/20 split evidence, single-annotator/small-n/paraphrase-shift limitations all stated, recalibration trigger (≥30 distinct misses) defined. 0.70 sits inside the recommended 0.60–0.71 interval at the upper edge with a stated cost asymmetry argument (Union-Find chaining makes a single false edge glue two clusters). Two notes:
- The `LABELED_PAIRS` cluster class is built from ~6 workflow families contributing multiple correlated pairs each (5 progress-check, 4 merge-to-main, 3 dual-review, 3 push) — effective n is meaningfully below 48. §7 lists small-sample but not intra-family correlation. Dogfood-specific, as the artifact admits.
- The constant's comment (skill_promote.py:117-118) says "minimum-error band at 0.60–0.71" — the artifact's min-error band is 0.47–0.71; 0.60–0.71 is the *recommended* interval. Trivial conflation.
- The degenerate pair ("可以"×"继续", 0.792) is included in the scan despite being pre-filtered in production — biases the low-threshold false-merge counts upward, i.e., conservative for the 0.70 recommendation. Fine.

### 4. Envelope unwrap — correct, no legitimate query harmed

Whole-string-only matching is the right scope: embedded envelopes preserved (tested), a query merely *containing* `<user_query>` can't match the anchored pattern. Ordering with the low-info filter is correct (unwrap happens first, so `<user_query>继续</user_query>` → filtered). task_id is span-field derived and untouched; wrapped/unwrapped variants of the same query now soft-merge, which heals rather than harms. One contrived edge: concatenated envelopes (`<user_query>a</user_query><user_query>b</user_query>`) extract as `a</user_query><user_query>b` because `(.*?)` with DOTALL spans the first closer — harmless noise, not worth fixing.

### 5. Low-info filter — conservative direction, aggressive for CJK

`len(q) <= 4` drops genuinely informative terse CJK imperatives ("合并", "部署", "跑测试", "提交代码") whose recurrence across days would otherwise qualify. This matches the artifact's own §6 recommendation, and the error direction is invisible-miss (the `miss_pool_size` metric would reveal systematic shrinkage). Acceptable as shipped; a CJK-aware rule (≤2 chars + list) would recover signal.

### 6. Scope & reporting

- **The M2 exit criterion is not met**: design says “真实数据准入的候选 ≥1 条出现在 `vibe skill discover`”. Real data admits 0, so the “最小可 demo 闭环” cannot be demonstrated end-to-end yet. The packet reports this honestly and the recalibration plan exists, but the milestone should be recorded as *exit criterion deferred pending data accumulation* (≥30 distinct misses), not closed.
- `miss_pool_size`/`miss_admitted_count` exist in `ScanSummary` but the scan CLI output doesn't print them — the "silent-spin detection" fields are invisible to the operator running the command. Given the design's own framing (“防止第三种静默空转”), surface them.
- The miss knobs are not exposed as CLI flags, and the skill_promote.py comment's claim that "the scan-candidates CLI flags wire onto those kwargs" is false. Consequence: `threshold_suggestion`'s remediation text (`--min-cluster-size` / `--min-gold-rate`) is a no-op for miss-recurrence candidates — the very source the suggestion targets — leaving the dismiss-driven tightening loop a dead end.
- `--history` is M5 scope pulled into M2 (read-only, harmless, but beyond the milestone line as drawn).
- Two miss predicates now coexist in the package: `tool_call_bridge._is_miss` (excludes CLI + `slash_command`) vs `is_route_miss_span` (excludes neither). Currently harmless — slash spans never carry `has_match`, and CLI misses are arguably legitimate discovery signal — but nothing in either docstring acknowledges the other, so they can drift silently. A cross-reference stating why the rules deliberately differ would close this.

## Verdict

The shipped code is correct where it claims to be, the tests pin the right invariants, the calibration is honest about its weaknesses, and the 0-admitted real-data outcome is truthfully reported rather than gamed. All findings are fixable in follow-up without touching the core gate.

Nits (in priority order):
1. Wire or de-document `extra_dismissed`/`extra_mutes` (build_queue docstring vs skill_commands.py:1865).
2. Add cross-process locking to `DiscoveryObservationStore._save` (and the `cross_process_lock` fallback in `DiscoverySignalStore._append`) per repo convention.
3. Surface `miss_pool_size`/`miss_admitted_count` in scan-candidates output; expose miss knobs as flags and fix `threshold_suggestion`'s ineffective advice + the "CLI flags wire onto those kwargs" comment.
4. Record M2 exit criterion as deferred (0 real-data admissions; re-run at ≥30 distinct misses).
5. UTC-vs-local natural-day boundary for the ≥2-day condition.
6. Cross-reference the two miss predicates; document why `is_route_miss_span` omits the bridge's CLI/slash exclusions.
7. Fix "minimum-error band 0.60–0.71" comment (that's the recommended interval; the band is 0.47–0.71).
8. Cap behavior: miss candidates permanently rejectable at `MAX_PENDING`; `miss_admitted_count` overcounts store-rejected rows.
9. `evidence_score` counts duplicate task_ids for cross-project clusters; `--history` analytics path cwd-only for global promotes (undisclosed).
10. Low-info filter len≤4 aggressive for CJK; calibration intra-family correlation shrinks effective n below 48; `--history` is M5 scope pulled forward.

VERDICT: PASS_WITH_NITS
