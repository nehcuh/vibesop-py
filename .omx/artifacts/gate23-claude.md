All verification complete — 651 tests green across the affected suites, ruff/format clean, basedpyright 0 errors (the one warning at skill_promote.py:1137 is pre-existing). Here is the gate 23 review.

---

# Gate 23 Review — discover resolver hardening + candidate first_seen_at

**Verdict: PASS_WITH_NITS**

## Findings

**1. NIT — dashboard label drift after semantics change** (`src/vibesop/dashboard/templates/index.html:719`)
Template renders `年龄: {age_days}d` while the CLI header was renamed "Age" → "First seen" (skill_commands.py:2379). The dashboard's `age_days` now silently means pattern-first-seen age, but the label still reads "年龄" (candidate age). The minimal-intrusion choice is defensible, but a one-word template tweak would close the CLI/dashboard wording gap. Residual risk: dashboard users misread the column as pool-entry age.

**2. NIT — `first_seen_at` name collision** (`discovery.py:419` vs `skill_promote.py:352`)
`DiscoveryObservationStore` already persists its own `first_seen_at` (queue-observation clock, drives cooling) in a separate JSONL; `ClusterCandidate.first_seen_at` (span timestamps) is a different provenance with the same name in the same module family. Confusion risk for maintainers only — no data path intersects (verified: different files, different stores).

**3. NIT — `--mute ""` entry point untested** (skill_commands.py:2552)
The empty guard protects both callers (dismiss :2589 and `--mute` :2552) since it sits inside the resolver, but `TestResolveCandidateHardening` only exercises dismiss. Trivial risk — the guard is upstream of both.

## Verified (adversarial checks that passed)

- **NIT-A entry-point coverage**: both callers convert `None` → `"not in Discovery queue"` + `Exit(1)`; the empty-string test additionally proves the pending row survives (no silent dismiss). Ambiguous listing is byte-identical to `_resolve_candidate_for_mutation` (:1780) — sorted, scope-annotated, `[:8]` + `+N more`. Same-cluster_id cross-scope dedup handled upstream by `_gather_scoped_candidates`' dict keying, so the listing can't double-name one id.
- **NIT-B merge correctness**: `_do_locked_upsert` :530-533 handles all four None/value combos — legacy backfill (existing None → new value wins), shorter window (existing earlier wins), *longer* window (new older value wins — I checked this direction explicitly), all-undated rescan (existing preserved, not wiped). `created_at`/`ttl` preservation and terminal-row no-op untouched.
- **No out-of-cluster spans**: `cluster_spans` (:1272) and `mc_spans` (:1325) are the same task-key-filtered lists already fed to `label_step_frequency`; tasks belong to exactly one cluster. Zero new full scans — one pass per already-built list.
- **Parse tolerance**: `_earliest_span_timestamp` (:1398) byte-matches `_miss_recurrence_counts` (:1450-1455) — same import, `Z`→`+00:00`, ValueError skip, naive→UTC. Round-trip/missing-key/naive tests lock the serialization invariants.
- **No hidden consumers shifted**: `evidence_score` (discovery.py:144) uses no age; admission/eviction/kill-switch code untouched in the diff; `is_route_miss_span`/`_is_miss` not in the diff.
- **Time-bomb fix is semantic, not cosmetic**: span ordering preserved (miss before other), same default session, distinct queries → distinct derived task_ids → `session_moved_on` branch fires; `other-1` at now−30min stays undecided for ~23.5h vs the original bomb at T0+30min+24h (the `len(outcomes) == 1` assertion was what flipped). I swept the remaining 20 `T0` uses in the file: all are either precedence-protected (`explicit_accept`/`strong_positive` classify before expiry) or already now-relative/intentionally expired — no other latent bombs.
- **Scope**: diff touches exactly the 7 declared files; no unrelated refactors. (The untracked `.omx/artifacts/` and `.vibe/tool_sequences.last` are runtime/review artifacts, not in the diff.)

Residual risk overall: low — the only behavior-affecting surface beyond the intended ones is finding 1's dashboard label, which is cosmetic.
