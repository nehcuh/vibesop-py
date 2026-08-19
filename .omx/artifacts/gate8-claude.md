All checks complete — 328 targeted tests pass, ruff and basedpyright clean. Compiling the verdict.

---

## Review Summary

**What I verified (all `[executed]` unless noted):**

**Slice A** — Enum check: all 6 trusted layers + 5 excluded layers match the real `RoutingLayer` enum (models.py:19-32). The prune's direct-write-instead-of-`_save()` claim is **correct**: `cross_process_lock` opens a fresh fd per call (file_lock.py:81) so flock is per-OFD non-reentrant — calling `_save()` inside the held lock would self-deadlock. RMW discipline (threading lock → file lock → clear-epoch guard → disk merge → backup → atomic write) mirrors `_save`. Human-confirmed instincts verified safe: accept write-back uses `source="routing_pending"` (instinct_cmd.py:187), auto-promote uses `source="auto-promote"` (:831) — both outside prune's filter. Preference removal verified safe: explicit paths still record (cli/feedback.py:56, cli/main.py:1731, accept/dismiss write-backs); no test or consumer depends on routing-driven preference writes (checked all `preferences.json` test references).

**Slice B** — Installer joins `project_path / ".vibe/skills" / id` (skill_installer.py:93); registry/marker paths match test assertions. `~/.vibe/skills` confirmed in `ExternalSkillLoader.EXTERNAL_PATHS` (external_loader.py:68), auditor allowlist (skill_auditor.py:124), and promote hints (skill_promote.py:1062). `SkillInstaller` has exactly one CLI caller. Migration edges probed: no-legacy noop, missing target (mkdir'd), name conflict (skip+warn, legacy kept), non-dirs untouched, OSError caught, legacy-symlinked-to-target (all conflicts skipped, safe), `~/.vibe/skills` as a file (FileExistsError → OSError caught). No data-loss path found.

**Slice C** — `NON_SKILL_YAML_FILENAMES` is a single source of truth shared by loader and indexer. All index reads route through the pruning `_load_single_index` (load_index, has_index, incremental add at skill_commands.py:1187); fresh builds consume loader discovery, so no re-pollution. `EmbeddingRecall` and `TriageService` each have exactly one production construction site, receiving the real `RoutingConfig` (single class, manager.py:130). Slice-then-filter threshold is equivalent to filter-then-slice; `[]`-vs-`None` semantics wired correctly, keyword fallback preserves backfill.

**Test runs:** 19 + 87 + 81 + 122 + 19 = 328 targeted tests pass across all changed files and their consumers (prefilter, triage cache/service, feedback loop, result mixin). Ruff clean; basedpyright 0 errors (1 pre-existing warning in untouched embedding code).

```
VERDICT: PASS_WITH_NITS
BLOCKS:
(none)
NITS:
- src/vibesop/core/instinct/learner.py:~440 (prune_auto_extracted clear-epoch guard) — guard clears _instincts + _embedding_cache but NOT _sequences, unlike _save()'s guard (learner.py:362-364), and syncs _clear_epoch_at_load. If the same learner instance later calls save(), a concurrent clear()'s purged sequences could resurrect (epoch already consumed). Unreachable via the CLI flow (prune exits immediately), but it diverges from the documented RMW discipline if the instance is ever reused.
- src/vibesop/cli/commands/instinct_cmd.py:684 — `console.print(f"  [dim]{v.id}[/dim] {v.pattern[:100]}")` interpolates unescaped user content into Rich markup; a pattern containing literal `[/x]` raises MarkupError — in --apply mode the deletion has already succeeded when the traceback hits. Matches the existing naive convention in the `pending` command (item.query[:120]), but prune deliberately prints megaprompts, the most bracket-likely content.
- tests/unit/core/routing/test_triage_recall.py — no exact-boundary test (similarity == min_similarity, `>=` inclusive); the boundary semantics are untested.
- src/vibesop/cli/commands/skill_commands.py:519-525 — install_result["warnings"] is never displayed; after migration moves a legacy copy to the unified path, a same-id non-force reinstall returns "already installed" (warning suppressed) and the CLI still prints "✓ Installed to" pointing at the legacy copy. Pre-existing gap, made slightly more reachable by the migration.
- src/vibesop/core/skills/loader.py:362 — filename exclusion applies at any rglob depth, so a legitimate YAML skill nested under a skills dir and literally named registry.yaml/auto-config.yaml is silently skipped; the indexer's substring prune (_is_non_skill_profile_id) could likewise false-positive on contrived ids like `project/registry.yaml-tools/main`. Both acceptable; worth one doc line.
- No end-to-end test that `vibe skill add --global` actually invokes _migrate_legacy_global_skills (migration and install root are unit-tested separately; the composition at skill_commands.py:510-512 is untested).
NOTES:
- The similarity floor only engages when len(eligible) > max_skills (triage_service.py:391 early return) — junk queries against small candidate sets still reach the LLM. Pre-existing behavior, not a regression; the fix's protection is partial by construction.
- Partial-clear case still backfills: when ≥1 candidate clears the floor but fewer than max_skills do, the window is padded with below-floor candidates (triage_service.py:418-420). Consistent with the docstring's intent (abstain only when NOTHING clears) but untested.
- The new try_ai_triage early-return also skips the stale last-good fallback for junk queries — deliberate and correct (a stale cache entry shouldn't route a query that healthy recall says is irrelevant).
- INDEX_VERSION "1.4.0" is descriptive only — nothing gates on version; self-heal is at read time, so phantoms remain on disk until the next index write (incremental add or rebuild both persist the prune).
- CJK low-info variants (e.g. "好的好的好的") pass the meaningful-token rule and survive the gate — accepted residual, identical boundary to routing_pending's own gate.
- Prune correctly reuses is_low_information_query from routing_pending (lazy import, no cycle — verified) and the CLI follows the repo's dry-run-default + --apply convention (matches vibe optimize --apply).
```
