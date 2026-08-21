# Gate 22 review — promote/dismiss cluster-id prefix resolution

You are an independent senior code reviewer. Review the attached diff (git diff of the working tree) for the VibeSOP project (Python CLI, `vibe`).

## Context

`vibe skill candidates` displays 8-char truncated cluster IDs, but `vibe skill promote <id>` / `vibe skill dismiss <id>` (W4 commands in `src/vibesop/cli/commands/skill_commands.py`) resolved the argument via `ClusterCandidateStore.get()` which is an EXACT match on the full 16-char id. A real user copy-pasted the displayed 8-char id and got "✗ Cluster 'bd1bc217' not in pool" even though the candidate existed.

The fix adds `_resolve_candidate_for_mutation(cluster_id, scope)` in skill_commands.py and rewires promote_cmd + dismiss_cmd to use it. Semantics: exact match in requested-scope store first (W5.2: --scope is authoritative) → exact in fallback store (keeps the "found in {scope} store" hint) → unique prefix across the union of both stores (dedup by cluster_id, requested scope wins) → ambiguous prefix prints up to 8 full ids and exits 1 → otherwise None (existing "not in pool" path). On success the local `cluster_id` is rebound to `candidate.cluster_id` so all downstream mutations/skill_id derivation use the full id.

Note `_resolve_discovery_candidate` (M12 discover commands) was NOT reused because it only sees pending rows and doesn't return the store object; the new helper resolves over `list_all()` of both stores so terminal-state rows stay reachable (idempotent re-promote, updating a dismissed row's reason). This rationale is in the docstring.

Tests: `TestPrefixResolution` in tests/cli/test_skill_promote_cli.py (5 cases). `uv run pytest tests/cli` = 728 passed. Touched files are ruff-clean (repo has 24 pre-existing lint errors in untouched files — out of scope).

## Review focus

1. Correctness of the resolution order and scope-authority preservation (W5.2 invariant: the requested scope's store must win exact matches; fallback must not silently flip the wrong store's status).
2. Ambiguity handling: can two rows with the same cluster_id in project+global stores confuse the dedup? Can a prefix colliding across scopes mis-route the mutation?
3. After rebind `cluster_id = candidate.cluster_id`, is there ANY remaining downstream use of the user-supplied prefix that would corrupt state (skill_id suffix, store.promote/dismiss calls, logging, draft paths)?
4. Error-message UX: ambiguous listing, not-in-pool path unchanged.
5. Test quality: do the 5 new cases actually lock the semantics (state flipped, full id used, no side effects on ambiguous/unknown)?
6. Any regression risk to existing promote/dismiss behavior (status stickiness, dismissed/promoted terminal guards, --scope global privacy confirmation in promote --activate path — confirm the fix didn't bypass it).

## Output

Verdict: PASS / PASS_WITH_NITS / BLOCK, then numbered findings with severity (BLOCK/MAJOR/NIT), file:line refs, and a one-line residual-risk note. Be adversarial; do not rubber-stamp.

---

# Round 2 (re-review) — claude gave soft BLOCK, all findings converged

Both reviewers' findings were fixed. Verify the fixes, focusing on your two MAJORs:

1. MAJOR-1 (empty-string guard): `_resolve_candidate_for_mutation` now returns None on empty input at the top; test `test_empty_string_resolves_to_not_in_pool` locks it.
2. MAJOR-2 (dual-store coverage): new `TestPrefixResolutionDualStore` with side_effect returning two distinct stores — (a) prefix→fallback+hint+only fallback mutated, (b) same id in both stores → requested scope flips, (c) cross-store prefix collision → exit 1, neither store mutated.
3. NIT-3: prefix test now uses a 6-char prefix (≠ display length) and asserts the echoed `Promoted '<full_id>'` line.
4. NIT-4: ambiguous listing annotates each id with `(project|global)` and prints `+N more` past 8.
5. NIT-5: new test locks prefix→dismissed-row sticky refusal.

ALSO NEW IN THIS DIFF (not in round 1): tests/core/observability/test_replay_acceptance_smoke.py `_load_fixture()` now rebases hardcoded 2026-07 fixture timestamps relative to now (newest ≈ 1 day old). Root cause: recall's wall-clock 30-day look-back window (recall.py `_DEFAULT_DAYS_WINDOW=30`) aged the fixture out today — T-cmspark-3 (2026-07-22T09:00Z) crossed the cutoff mid-session, distinct traces 3→2, is_gold flipped, `test_cmspark_gold_match_triggers_replay` failed. Unrelated to the prefix fix; pre-existing time bomb. Review this rebase approach too (relative gaps preserved; span/trace counts unchanged).

Output: Verdict PASS / PASS_WITH_NITS / BLOCK + numbered findings with severity. If your round-1 MAJORs are adequately fixed, say so explicitly.
