# Gate 23 review — discover resolver hardening + candidate first_seen_at

You are an independent senior code reviewer. Review the attached diff (git diff of the working tree) for the VibeSOP project (Python CLI, `vibe`).

## Context

Three changes, all follow-ups from gate 22 (commit 7ef8706, which added `_resolve_candidate_for_mutation` for promote/dismiss):

**1. NIT-A — `_resolve_discovery_candidate` hardening** (`src/vibesop/cli/commands/skill_commands.py` ~2284). Backports two guards to the M12 discovery resolver: (a) empty-string input returns None (previously `startswith("")` matched every pending row — `vibe skill discover dismiss ""` could silently hit a single-row pool); (b) the ambiguous path now lists full ids with `(project|global)` scope annotations + `+N more` past 8, mirroring the mutation resolver's wording. Deliberately NOT deduped into a shared helper: mutation resolver needs the store object + terminal rows via list_all(); discovery resolver sees pending-only (scope, candidate) pairs. Docstring records the rationale.

**2. NIT-B — `ClusterCandidate.first_seen_at`** (`skill_promote.py`, `discovery.py`, `skill_commands.py`). The discover table's "Age" column showed candidate creation age (always 0d) — useless. The decision-relevant quantity is pattern-first-seen age (the ≥2-days recurrence evidence from the M2 exit). Changes: `ClusterCandidate` gains optional `first_seen_at` (legacy rows without the key → None → display falls back to created_at); scan populates it from the earliest span timestamp in the cluster via `_earliest_span_timestamp` (same parse-tolerance as the miss-recurrence counter: skip bad/missing ts, naive→UTC, all-undated→None), reusing existing per-cluster span iterables (gold path `cluster_spans` :1288, miss path `mc_spans` :1336) — no new full scans; `_do_locked_upsert` refresh branch merges earliest-wins so a shorter rescan window never pushes first-seen forward; `build_queue()` age_days uses `first_seen_at or created_at`; discover column header "Age" → "First seen". Dashboard `_discoveries.py` consumes the same age_days (semantics change automatically; template wording untouched by minimal-intrusion choice).

**3. Unplanned but required — another time-bomb test** (`tests/core/observability/test_tool_call_bridge.py` ~278). `test_session_continued_is_weak_positive` used fixed `T0 = 2026-08-20 10:00 UTC`; once wall clock passed 2026-08-21 10:30 UTC, a span crossed SESSION_COMPLETE_HOURS=24 and the outcome flipped to session_expired_without_reask. Fixed to the now-relative style already used by neighboring tests (which carry a comment about exactly this trap). Same class of bomb as the replay fixture fixed in 7ef8706.

## Invariants that must hold

- Scan admission/eviction/kill-switch logic untouched; only field fill added.
- `gold_detection.is_route_miss_span` and bridge `_is_miss` untouched.
- first_seen_at must never move BACKWARD on rescan (earliest-wins), and legacy pool rows must keep working (None → created_at fallback).
- Serialization round-trip preserves the field; naive ISO parses as UTC per repo convention.

## Review focus

1. NIT-A: does the empty guard cover all entry points (dismiss + any other discover subcommand using the resolver)? Is the ambiguous listing identical in spirit to the mutation version (wording, scope annotation source)?
2. NIT-B: is earliest-wins merge correct under locked upsert (no lost update vs created_at/ttl preservation)? Any path where first_seen_at could be populated from a span OUTSIDE the cluster? Does the naive→UTC handling match repo conventions? Display fallback correct?
3. Time-bomb fix: is the now-relative rewrite semantically identical to the original intent (session_continued weak-positive), not just made-green?
4. Test quality: do the new tests actually lock the invariants above (TestFirstSeenAt ×3, TestFirstSeenAtField ×3, TestFirstSeenColumn ×2, TestResolveCandidateHardening ×3)?
5. Anything in the diff that widens scope beyond these three items.

## Output

Verdict: PASS / PASS_WITH_NITS / BLOCK, then numbered findings with severity (BLOCK/MAJOR/NIT), file:line refs, one-line residual-risk note. Be adversarial; do not rubber-stamp.
