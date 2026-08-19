# Gate 8 — Dual Review: Tier2 Routing Signal Integrity

You are reviewing an UNCOMMITTED changeset in the repo `/Users/huchen/Projects/vibesop-py`.
The full diff of modified files is at `.omx/artifacts/gate8.diff`; the full text of the two new test files is at `.omx/artifacts/gate8-newfiles.txt`. You may also read any file in the repo for context, and run `git diff` / `git status` yourself. Do NOT modify any files. Do NOT run package installs. You may run read-only commands (`grep`, `sed -n`, `uv run pytest <specific test file>` if you must, but prefer reading).

## Context

This is milestone M7-Tier2 of an ongoing routing-quality overhaul (M1–M7 Tier1 already merged to main). Three independent workstreams landed in this changeset:

### Slice A — auto_extract source filtering + preference feedback gating
Problem: `_record_routing_decision` in `src/vibesop/core/routing/unified.py` minted an "auto_extracted" instinct for ANY routing match with confidence >= 0.7 (even weak last-resort layers like levenshtein fuzzy fallback), storing multi-hundred-char megaprompts as permanent patterns; and recorded `record_selection(..., was_helpful=True)` to the preference learner merely for being routed (unconditional positive feedback loop).
Changes: `_AUTO_EXTRACT_TRUSTED_LAYERS` gate in unified.py; `is_auto_extract_worthy()` + `AUTO_EXTRACT_MAX_PATTERN_CHARS = 300` + `prune_auto_extracted(dry_run=True)` in `src/vibesop/core/instinct/learner.py`; new CLI `vibe instinct prune --auto-extracted [--apply]` in `src/vibesop/cli/commands/instinct_cmd.py`; removed the routing-driven positive preference record.

### Slice B — global skill install path unification
Problem: `vibe skill add --global` installed to `~/.vibe/.vibe/skills/<id>` (doubled path: `project_path=~/.vibe` joined with installer's `.vibe/skills`), which NO loader searches — global installs were invisible. Loader searches `~/.vibe/skills/`.
Changes: `_install_root(scope)` returns `Path.home()` for global (so installer lands in `~/.vibe/skills/<id>`); `_migrate_legacy_global_skills()` moves legacy `~/.vibe/.vibe/skills/` installs into `~/.vibe/skills/` (shutil.move, conflict-safe, non-directories left alone); stale comments/docs fixed. Installer itself untouched.

### Slice C — index pollution fix + embedding recall floor
Problem 1: `.vibe/skills/auto-config.yaml` (SkillConfigManager state file) and `registry.yaml` were discovered/indexed as skills (e.g. phantom id `project/auto-config.yaml/auto-config` in `.vibe/skill-index.json`). A 2026-07-21 guard (yaml must have id/name) partially covered it, but stale on-disk indexes persisted.
Changes: `NON_SKILL_YAML_FILENAMES` exclusion in `src/vibesop/core/skills/loader.py`; `SkillIndexer.INDEX_VERSION = "1.4.0"` + load-time pruning of non-skill profile ids in `src/vibesop/core/skills/indexer.py` (self-heal without rebuild).
Problem 2: `EmbeddingRecall.recall()` returned top-N by cosine with no floor — junk queries got N semantically-distant "best" candidates pushed to the LLM triage window.
Changes: `min_similarity` param + `DEFAULT_MIN_SIMILARITY = 0.25` in `src/vibesop/core/routing/triage_recall.py`; explicit `[]`-vs-`None` semantics in `triage_service.py` (`None` = recall unavailable → keyword fallback; `[]` = healthy recall, nothing relevant → abstain without LLM call, no arbitrary backfill); new config `RoutingConfig.ai_triage_recall_min_similarity` (0..1, default 0.25) in `src/vibesop/core/config/manager.py`, plumbed through `TriageService._recall_min_similarity()`.

## Your task

Adversarially review this changeset. For EACH of the three slices, hunt for:
1. **Correctness bugs**: logic errors, off-by-one, wrong layer enum values (verify against the actual `RoutingLayer` enum in the repo!), broken migration edge cases (Slice B: what if `~/.vibe/skills` doesn't exist? symlinked? what if legacy dir IS `~/.vibe/skills` via some alias?), threshold/filter bypasses.
2. **Integration breaks**: callers of changed functions whose semantics shifted (empty list vs None, removed record_selection — does anything DEPEND on routing-driven preference counts? check preference_boost consumers, decay logic, stats), config plumbing reaching all instantiation sites of EmbeddingRecall/TriageService (grep for every constructor call — are there sites that don't pass the new config?), SkillLoader behavior change breaking pack loading or external paths.
3. **Test gaps**: tests that assert the new behavior but would also pass if the fix were absent; missing edge cases (conflict during migration, unicode patterns in prune, index with BOTH stale phantom and real entries, min_similarity boundary 0.25 exactly).
4. **Consistency**: does pruning-by-filename in indexer agree with loader's exclusion set? Does the CLI prune dry-run/apply flag handling follow the repo's other destructive-command conventions? Comments/docs claiming old behavior.

Verdict format (exactly):
```
VERDICT: PASS | PASS_WITH_NITS | BLOCK
BLOCKS:
- [severity P0/P1] file:line — issue — why it matters
NITS:
- file:line — issue
NOTES:
- anything the team should know (positive or risk)
```
BLOCK only for issues that would cause wrong behavior, data loss, or test-suite/CI failure if merged as-is. Nit = worth fixing soon but not merge-blocking. Be specific: cite file:line and show the offending code. Do not pad; if it's clean, say PASS with short notes.
