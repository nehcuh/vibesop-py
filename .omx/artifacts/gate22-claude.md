Review complete. All claims verified: 728 tests pass [executed], both touched files ruff-clean [executed], old duplicated lookup fully absorbed into the helper [inspected], `--activate` privacy chain intact [inspected]. Here is the Gate 22 review.

---

# Gate 22 Review — promote/dismiss prefix resolution

## Verdict: BLOCK
(soft block — design and implementation are correct; two targeted must-fix items, ~30 min combined, no rework needed. Do not merge as-is.)

## Findings

**1. MAJOR (bug, degenerate input) — empty-string argument mutates state.** `src/vibesop/cli/commands/skill_commands.py:1761`
`row.cluster_id.startswith("")` is true for every row, so `_resolve_candidate_for_mutation("")` matches the entire union of both stores. With exactly one row in that union, `vibe skill promote ""` — or the realistic footgun `vibe skill promote "$CID"` with `CID` unset — resolves to that row and flips it to `promoted`: a terminal-sticky status with no un-promote command, plus a draft write. Old code returned "not in pool" for this input. This violates the project's own "human decision wins" invariant (skill_promote.py:333). Likelihood is low (multi-row pools hit the ambiguity guard), but fresh installs have single-row pools and the union spans both stores. Fix is one line at the top of the helper: `if not cluster_id: return None`. [inspected — traced the full path; `Typer` accepts `""` for a required `Argument`]

**2. MAJOR (test coverage) — the dual-store prefix logic, the riskiest part of the diff, has zero coverage.** `tests/cli/test_skill_promote_cli.py:44`
`tmp_store` patches `_get_candidate_store` with a single `return_value`, so primary and fallback resolve to the **same store object** in all 5 new cases. Consequently nothing tests: (a) a prefix resolving into the *fallback* store with the redirect hint; (b) the dedup-by-cluster_id primary-wins rule when the same id exists in both stores — the `row.cluster_id not in matches` branch at skill_commands.py:1762 can only fire trivially (same object twice); (c) ambiguity across two different stores. The brief's claim that the 5 cases "lock the semantics" is true for single-store semantics only — and review-focus #2 (cross-scope collision) is answered "correct by inspection, unproven by test." The repo already has the right pattern: `test_dismiss_cross_project_candidate_via_global_fallback` (test_skill_promote_cli.py:608-633) uses a `side_effect` returning distinct stores per scope. Reuse it for 3 cases: prefix→fallback+hint, same-id-both-stores→requested scope flipped, cross-store ambiguity→exit 1 + neither store mutated. [inspected]

**3. NIT — tautological assertion overstated by its comment.** `tests/cli/test_skill_promote_cli.py:1146-1148`
`source_skill_id.endswith(full_id[:8])` cannot discriminate full-id from prefix derivation: skill_id is `custom/{slug}-{cluster_id[:8]}` (skill_commands.py:1892) and the test's input prefix *is* `full_id[:8]`, so both derivations are byte-identical. The status-flip assertion is the real load-bearing check (a prefix passed to `store.promote` would exact-match nothing and no-op — skill_promote.py:791). Fix by using a 5-6 char prefix in this test: it simultaneously makes the skill_id assertion discriminating and covers non-display-length prefixes. [inspected]

**4. NIT — ambiguous listing truncates silently.** `skill_commands.py:1765` — `sorted(matches)[:8]` shows 8 ids with no "+N more"; with a 20-row collision the user can't see all candidates. Print an ellipsis count.

**5. NIT — UX inconsistency with the sibling resolver.** `_resolve_discovery_candidate` (skill_commands.py:2283) prints "ambiguous" *without* the match listing; the new helper lists ids for copy-paste. The new behavior is strictly better — backport it to the discovery resolver in a follow-up.

## Verified correct (per review focus)

- **Resolution order & scope authority**: exact→primary, exact→fallback, prefix over union with primary-first insertion — W5.2 invariant preserved in both paths; fallback never silently wins (the dim hint fires whenever `resolved_scope != scope`). Cross-scope prefix collision → ambiguous exit 1, no mutation. [inspected]
- **Full-id rebind is complete and load-bearing**: every downstream consumer audited — skill_id (1892), `store.promote` (1916), reload `get` (1919), `store.dismiss` (2131), all messages — none touch the prefix afterward; and since `promote`/`dismiss` exact-match internally, a missing rebind would silently no-op. [inspected]
- **`--activate` privacy chain untouched**: global-scope interactive confirmation (2049-2067) runs after resolution, unconditional even with `--force`; resolution cannot bypass it. Terminal guards (1864, 2124) unchanged and now reachable by prefix via `list_all()` — the docstring's idempotency claim holds. [inspected]
- **Premise real**: candidates table renders `cluster_id[:8]` (1696). 728 tests pass, ruff clean on both files. [executed]

**Residual risk**: after fixes 1-2, the only unproven path is a TOCTOU between resolution and the locked store transition (pre-existing, tolerated — `store.promote` returning None is ignored at 1916 as before this diff).
