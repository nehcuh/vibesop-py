All checks complete. Here's my review.

## Review summary

**F1 (gold_detection.py:82-90)** — Truncation is the right policy. Statically verified against `zip_longest`: there is no correct pairing for a mismatched cluster, and `zip_longest` would pair real task_ids with `None` queries (guaranteed instinct-lookup miss) or invent semantics. Truncation math: numerator ≤ min(len) while denominator stays `len(task_ids)`, so `gold_rate` can only be **under-estimated, never inflated** — the safe direction for a promotion gate that drafts user-facing skills. The "truncated misses failures" scenario has no inflation vector: dropped task_ids (queries shorter) count in the denominator but can never be gold; dropped queries (task_ids shorter) can only hide successes, not hide failures.

**WARNING spam** — non-issue: `cluster_queries` builds `task_ids` and `queries` from the same `member_keys` list in one pass (clustering.py:328-331), so production output cannot diverge. The warning fires only for hand-built/future-producer clusters, once per scan per cluster, bounded. [inspected]

**F2 (skill_promote.py:803-810)** — `continue` is correct. Nothing downstream counts on the candidate: the store is untouched, summary counters untouched — identical to the existing neutral-zone skip. Quarantine machinery for an invariant that can't break in production would be over-engineering. The `python -O` claim is real: I executed a minimal repro confirming `assert` vanishes under `-O` [executed], and grepped `core/observability/` — **zero asserts remain** in the whole module, so no other stripped guard protects this path (none needed now).

**Tests** — 18/18 pass [executed]. Both genuinely fail under HEAD code by deterministic Python semantics (`zip(strict=True)` on 3-vs-2 → ValueError; `assert []` → AssertionError) — I could not execute the old-code run (sandbox blocked temp-dir setup), so that's [inspected] but certain. The F2 test is non-vacuous: `_spans` sets `project_id: "test"` so the age-out filter doesn't short-circuit, and the error-log assertion proves execution reached the guard.

**Eval yaml** — `reject:` IS supported and scores: eval_routing.py:55 and the mirror driver (eval_driver.py:45, faithful copy including the `or []` hardening) both do `primary not in reject` for empty-expect entries. No vacuous entries (all 7 have expect or reject non-empty). One real caveat: **positive #1 appears verbatim in the SKILL.md description and in the skill-index `query_patterns`** (SKILL.md:4, index:70), and #3 shares its distinctive phrase (起草/建站规格书) — so the 7/7 is partially self-fulfilling for the positives. The 4 negatives (junk + adjacent) are clean and genuinely discriminate, so the set does measure false-positive rejection.

**skill-index.json** — diff adds exactly one skill entry + version bump to 1.4.0; grep for api_key/token/secret/password//Users//sk-/Bearer/email patterns: no matches.

Also audited sibling `zip(..., strict=True)` sites across src/ for F1-class batch-killers: all remaining ones are internal-lockstep pairs or fixed-dimension dot products where failing loud is correct — no siblings needed the same fix.

```
VERDICT: PASS_WITH_NITS
BLOCKS:
(none)
NITS:
- tests/benchmark/routing_eval_oneshot.yaml:2 / .vibe/skills/oneshot-web-spec/SKILL.md:4 — eval positive #1 ("帮我写一个贪吃蛇单页游戏的任务书") is embedded verbatim in the skill description and skill-index query_patterns; #3 is near-verbatim — the 7/7 positives are partially self-fulfilling rather than evidence of paraphrase generalization; paraphrased positives would strengthen the measurement
- tests/core/observability/test_scan_candidates.py:350 — no coverage executes under `python -O`; the fix is definitionally immune (an `if` is never stripped) and I verified the stripping semantics, but a `-O` smoke of the guard test would lock the property against regression back to an assert
NOTES:
- F1 truncation can only under-estimate gold_rate (numerator ≤ pairs, denominator = len(task_ids)) — biases against promotion, the safe direction; no inflation vector exists in either mismatch geometry
- Production task_ids/queries divergence is impossible: cluster_queries derives both from the same member_keys pass (clustering.py:328-331); the WARNING is hand-built-cluster-only, bounded 1/cluster/scan — no spam guard needed
- F2 downstream safety: skipped cluster is simply absent from the store, same as neutral-zone skip; no counters or consumers assume its existence; zero asserts remain in core/observability (grep-verified)
- reject entries measure only "primary != oneshot-web-spec" — junk hits should not be read as "junk queries handled", only as this skill's precision; that matches the stated eval intent
- eval_routing.py hardcodes routing_eval.yaml (no --file flag); the oneshot set requires the mirror driver or concatenation, as the yaml header documents
- Old-code test failure verified statically (deterministic ValueError/AssertionError semantics); new-code pass verified [executed] 18/18
- .vibe/skill-index.json: 1 new entry + v1.4.0 bump only; secret/PII/path scan clean
```
