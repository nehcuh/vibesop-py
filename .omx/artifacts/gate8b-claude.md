All checks complete — 248 targeted tests pass `[executed]`, ruff clean, basedpyright 0 errors (remaining warnings pre-existing). Compiling the verdict.

---

## Gate 8b Re-review Summary

**What I verified (all `[executed]` unless noted):**

**Nit-fix verification** — Every item from my gate8 verdict and pi's is resolved, each with a genuine regression pin:
- Prune clear-epoch guard now clears `_sequences` too (learner.py:497-502), exactly mirroring `_save()` (learner.py:382-392). My gate8 nit #1. ✔
- `rich_escape(v.pattern[:100])` on prune output (instinct_cmd.py); `test_markup_in_pattern_does_not_crash` exercises both dry-run and `--apply` after deletion. My nit #2. ✔
- `test_threshold_boundary_is_inclusive` computes the true cosine floor rather than hardcoding 0.25 — stronger than I asked. My nit #3. ✔
- Warnings printed before the success line (skill_commands.py:525-527); `test_installer_warnings_are_printed` pins it. My nit #4. ✔
- Indexer prune is now whole-segment match (`skill_id.split("/")`, exact `in` frozenset); loader comment documents any-depth exclusion. My nit #5. ✔
- `TestGlobalAddComposition` runs the real command with real `SkillInstaller` + real migration + real filesystem under a patched home. My nit #6. ✔
- Pi's prune-vs-accept reproduction: fixed two-layer (re-tag at accept + `success_count > 0` guard), with both layers independently pinned.

**Regression hunt (task's specific questions) — all clear:**
- **Accept re-tag locks**: `learn()` acquires and fully releases both locks inside its `_save()`; the re-tag mutates in-memory; `learner.save()` re-acquires sequentially — no nested flock, no deadlock (flock is per-OFD, fresh fd per acquisition). Epoch handling inherited from `_save`'s guard. Grep confirms **no consumer** filters on `auto_extracted`/`auto_routing` outside the prune filter itself — re-tagging breaks nothing.
- **`success_count` protection not leaky**: every writer enumerated. Incrementers of `success_count`: accept writeback (explicit), `vibe feedback` (explicit), replay-confirm (requires TTY + `typer.confirm` Y at main.py:2015). Dismiss/decay are failure-only; `extract_from_experiment` (source=`experiment`) and replay rows (source=`replay_confirm`) fall outside prune's source/tag filter; `record_instinct_matched` touches only `times_matched`.
- **Layer-gate import cycle**: definitively safe from every entry point. learner.py's module-level imports are stdlib + `utils.atomic_writer` only; unified↔learner references are both call-time, and a call-time import resolves via `sys.modules` regardless of load order.
- **Unknown-context fallback**: fails toward under-pruning (no data loss); current mints always store `match.layer.value`, so the leniency only reaches genuinely legacy rows. Documented and tested.
- **`min_similarity` mutation race**: plain float attribute read/write, atomic under the GIL; `prefilter_ai_triage_candidates` is single-threaded through recall. Worst case an in-flight recall uses the pre-swap floor for one call — benign for a mid-flight config change.
- **Segment prune**: ids without `/` → single exact segment check; case-sensitive exact match identical to the loader's `file_path.name in NON_SKILL_YAML_FILENAMES` — the two layers cannot diverge.
- **Composition test fidelity**: mocks only detection/audit/auto-config/verify (patch target valid — `add()` imports the auditor function-level at skill_commands.py:472, resolving through the patched module; installer's already-installed path returns `success=True` + warning at skill_installer.py:95-98). Both gate8 wiring regressions (missing migration call; doubled install path) would be caught.

**Deliberately NOT changed — I confirm both:** dry-run-default + `--apply` matches the verified `vibe optimize --apply` precedent (optimize_cmd.py:31); CJK residual shares routing_pending's exact gate boundary, so tightening it here would fork the shared gate.

```
VERDICT: PASS
BLOCKS:
(none)
NITS:
- instinct_cmd.py:195-199 — accept-on-merged-auto now double-persists (learn() saves, then the re-tag branch saves again: two full writes + lock cycles). Correct and simple; a single locked write would be marginally cheaper. Cosmetic.
- instinct_cmd.py:214-237 — accept/dismiss asymmetry: dismiss does not re-tag merged auto rows, so a dismissed auto row that passes both gates keeps auto markers until confidence decay. Deliberate (failure_count deliberately doesn't protect, pinned by test_negative_outcome_does_not_protect) — noting it's intended, not an oversight.
- learner.py:199 — prune's lazy import of unified pulls the full router stack (ConfigManager, matching, optimization) into a data-hygiene CLI command; first prune call pays that import cost. Acceptable given the gate is shared by design; a constants-only module would be a marginal cleanup.
NOTES:
- Key-concern answer below.
- 248 targeted tests pass across all seven touched files; ruff clean; basedpyright 0 errors (warnings pre-existing in untouched LLM-call region).
- The floor-sync placement before the `len(eligible) <= max_skills` early return is intentional (test-observable config swap even when recall won't run) — harmless one-float write, and it makes the config-swap semantics deterministic.
- try_ai_triage's empty-window early return also improves a pre-existing case: an all-management-only candidate set now skips the LLM call entirely instead of sending an empty prompt.
```

**Was my gate8 verdict's key concern resolved correctly?** Yes — and better than my bar. My gate8 treatment of the prune-vs-accept interaction was the weakest part of my review: I flagged it as a docstring overclaim and judged the harm "limited" on the theory that pruned patterns are unmatchable junk anyway. Pi was right to push: the row is human-confirmed *data*, and deletion of confirmed data is a different harm class than deleting junk. The gate8b fix resolves it structurally rather than cosmetically — where I would have accepted a docstring correction or a `pending_accept` tag exclusion, the team shipped a two-layer fix (accept-time re-tag for post-fix rows, `success_count > 0` guard for pre-fix legacy rows), and I verified the second layer is airtight (no auto path can increment `success_count`). The docstring now states the true contract, and `test_accepted_megaprompt_survives_prune` plus `test_positive_outcome_marks_human_confirmation` pin each layer independently. Correctly resolved.
