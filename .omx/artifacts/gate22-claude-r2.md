# Gate 22 Round 2 Review — promote/dismiss prefix resolution + fixture rebase

All claims re-verified against the working tree: `tests/cli` = **733 passed** [executed] (round-1's 728 + exactly the 5 new round-2 tests — count math is consistent), replay smoke = 10 passed [executed], all 3 touched files ruff-clean [executed].

## Round-1 findings: all adequately fixed

**MAJOR-1 (empty-string) — FIXED.** Guard at `skill_commands.py:1753-1754` returns None before any `startswith` can fire; `test_empty_string_resolves_to_not_in_pool` (test_skill_promote_cli.py:1170) locks exit-1 + "not in pool" + row stays `pending`. [executed]

**MAJOR-2 (dual-store coverage) — FIXED, and the tests are genuinely discriminating.** `TestPrefixResolutionDualStore` uses `side_effect` routing to two real stores (mirroring the pattern my round-1 review asked for):
- (a) prefix→fallback: hint printed, fallback flipped, primary untouched (`project_store.get(full_id) is None`) [executed]
- (b) same id in both stores: the 8-char input is NOT the full id, so this goes through the **prefix loop** — the dedup-by-cluster_id primary-wins branch (`row.cluster_id not in matches`, skill_commands.py:1770) is exercised for real, not trivially. Project flipped, global `pending`, no redirect hint. [executed]
- (c) cross-store collision: ambiguous exit 1, scope-annotated, neither store mutated. [executed]

**NIT-3 — FIXED.** 6-char prefix ≠ 8-char suffix makes `endswith(full_id[:8])` discriminating (a leaked prefix would produce `custom/topic-a-abc123`, failing the assert), plus the `Promoted '<full_id>'` echo lock and the `prefix != full_id[:8]` sanity check.

**NIT-4 — FIXED.** Scope annotation `(project|global)` asserted in test (c); `+N more` past 8 at skill_commands.py:1778-1779.

**NIT-5 — FIXED.** `test_prefix_hitting_dismissed_row_stays_sticky` — prefix resolves over `list_all()` which I confirmed includes terminal states (skill_promote.py:635-640), so the sticky refusal fires via prefix input.

**Rebind/privacy re-audit (round-1 verified-correct items, still hold):** every downstream consumer uses the rebound full id — skill_id (1905), `materialize_candidate` (1921), `store.promote` (1929), reload `get` (1932), `store.dismiss` (2144), all messages. `_activate_promoted_draft` receives the *requested* `scope`; the global privacy confirmation (2074-2080, default-N, `--force`-proof) is keyed on `scope` only and cannot be bypassed by resolution. No prefix leakage found.

## NEW: fixture rebase in `test_replay_acceptance_smoke.py` — sound

Verified beyond the test passing:
- **Root cause real**: `_DEFAULT_DAYS_WINDOW = 30` (recall.py:38); fixture max is 2026-07-27, T-cmspark-3 at 07-22 crossed the cutoff on 2026-08-21 — the aging-out story checks out.
- **No aware/naive trap**: all fixture timestamps are `+00:00`-suffixed; `now(UTC) - max()` is aware/aware arithmetic; the `.isoformat()` output stays in the `+00:00` family, which recall's `_parse_timestamp` (recall.py:264, handles both `Z` and offset) parses fine.
- **No flake window**: single shift computed once per load; rebased fixture sits at 1–13 days old (12-day internal spread) against a 30-day cutoff — deterministic margin, relative gaps preserved, distinct-trace/span counts unchanged. I confirmed all 5 cmspark traces land in-window after rebase. [executed]
- **Sole consumer**: grep shows this fixture is used only by this test file (+ a doc reference); no other test reads the on-disk timestamps directly. The hardcoded `last_seen="2026-07-25..."` in `test_emit_replay_span_carries_provenance` constructs its own `RecallResult` and never passes through the window filter — unaffected.

## Findings

1. **NIT (pre-existing, deferred follow-up — restate of round-1 claude NIT-5)** — `_resolve_discovery_candidate` (skill_commands.py:2284-2296) still has the same empty-string hole (`cid.startswith("")` matches all pending rows) and its ambiguous path still doesn't list matches. Read-mostly path, explicitly out of this diff's scope; backport the guard + annotated listing in a follow-up.
2. **NIT** — the `+N more` overflow branch (skill_commands.py:1778-1779) is untested (would need 9 colliding rows). Trivial string formatting; not worth the test.

## Verdict: **PASS**

Both round-1 MAJORs are explicitly confirmed fixed with discriminating tests [executed]; the newly-added fixture rebase is correct, deterministic, and scoped to its sole consumer. Residual risk: the pre-existing TOCTOU between unlocked resolution and the locked store transition remains (not widened by this diff), plus the deferred empty-string hole in the discovery resolver (finding 1).
