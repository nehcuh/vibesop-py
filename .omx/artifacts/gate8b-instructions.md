# Gate 8b — Re-review: nit convergence round

You reviewed this changeset at gate8 (verdicts: PASS_WITH_NITS, 0 BLOCK from both). The team has now converged the nits. Re-review the FINAL changeset in `/Users/huchen/Projects/vibesop-py`: full diff at `.omx/artifacts/gate8b.diff`, new test files at `.omx/artifacts/gate8b-newfiles.txt`. Your gate8 verdicts are at `.omx/artifacts/gate8-claude.md` and `.omx/artifacts/gate8-pi.md` — read them first. Do NOT modify files. Read-only commands only.

## What changed since gate8 (nit convergence)

Slice A (learner.py / instinct_cmd.py / unified.py):
1. **Reviewer conflict on prune-vs-accept was adjudicated by reproduction: pi was RIGHT.** `_learn_locked` id-merge ignores new source/tags, so an accepted auto_extracted instinct kept its auto markings and was prunable. Fix is two-layer: (a) `_apply_accept_writeback` now re-tags merged instincts to `source="routing_pending"`, tags `["routing","pending_accept"]`, context `"routing_pending_accept"` (instinct_cmd.py:174-200); (b) prune skips any candidate with `success_count > 0` (explicit positive feedback) — `failure_count` deliberately does NOT protect. Docstring rewritten to the true contract.
2. Prune clear-epoch guard now also clears `_sequences`, mirroring `_save()`.
3. Prune output escapes pattern text via `rich_escape` (repo convention).
4. Prune now ALSO drops auto_extracted instincts whose mint-time `context` is an untrusted layer, sharing the constant: `_AUTO_EXTRACT_TRUSTED_LAYERS` renamed public `AUTO_EXTRACT_TRUSTED_LAYERS` in unified.py, lazy-imported by learner.py (`_is_untrusted_layer_context`). Unknown/missing context → quality-gate-only (documented lenient fallback).

Slice B (skill_commands.py / tests):
5. Installer warnings now printed (`⚠` yellow) before the success line in `vibe skill add`.
6. New command-level composition test: `vibe skill add --global` with a seeded legacy `~/.vibe/.vibe/skills/` dir actually migrates it (CliRunner + patched home).

Slice C (triage_recall.py / triage_service.py / manager.py / loader.py / indexer.py / tests):
7. Floor short-circuit behavior KEPT (protective for small candidate sets / CJK); docs/comments/config-description corrected to the true contract (floor only applies when eligible count exceeds `ai_triage_max_skills`).
8. Recall floor re-synced from config at every `prefilter_ai_triage_candidates` call (per-call), only for service-constructed recalls (`_owns_embedding_recall`); injected recalls never overridden. `EmbeddingRecall._min_similarity` → public `min_similarity`.
9. Indexer prune tightened from substring to whole `/`-separated segment match (`project/registry.yaml-tools/main` kept; `project/auto-config.yaml/auto-config` dropped); loader comment notes any-depth exclusion.
10. New tests: inclusive `>=` boundary at the floor; partial-clear backfill; config-swap-after-construction.

Deliberately NOT changed (please confirm or challenge): CLI prune keeps dry-run-default + `--apply` (reviewers cited conflicting repo conventions — `vibe optimize --apply` matches it); CJK low-info variants residual accepted.

## Your task

Verify the nit fixes actually fix what your gate8 verdict flagged, and hunt for regressions introduced BY the fixes:
- The accept re-tag in `_apply_accept_writeback`: does it run inside the right locks? Does the extra `save()` risk a deadlock or an epoch issue? Does re-tagging break any consumer filtering on `auto_extracted` / `auto_routing` (grep for all readers of these markers)?
- `success_count > 0` protection: can `success_count` be incremented by anything OTHER than explicit human/feedback action? If auto paths can bump it, the protection is leaky.
- Prune layer gate: is the lazy import of `AUTO_EXTRACT_TRUSTED_LAYERS` cycle-safe from EVERY prune entry point? Does the unknown-context lenient fallback create a bypass?
- Per-call floor re-sync: any case where `min_similarity` mutation races a concurrent `recall()` call (threading)?
- Segment-match prune: does it handle ids without `/`? Case sensitivity vs loader?
- Composition test fidelity: does it mock away so much that it wouldn't catch a real regression in the add flow?

Verdict format (exactly):
```
VERDICT: PASS | PASS_WITH_NITS | BLOCK
BLOCKS:
- [severity] file:line — issue — why
NITS:
- file:line — issue
NOTES:
- ...
```
Also answer explicitly: was your gate8 verdict's key concern (the one you cared most about) resolved correctly?
