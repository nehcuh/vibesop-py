# Gate 29 Verdict: **PASS_WITH_NITS**

Execution is faithful to the fixed policy; both checkers verified GREEN by running them; baseline reconciliation is exact. Findings below are real but none block. Evidence tags: `[executed]` = ran code, `[inspected]` = read source.

## Claims verified

| Claim | Result |
|---|---|
| Both checkers exit 0 | ✅ `[executed]` — `PASS: 18 checked files` / `No broken references` |
| Baseline 173 + 53 | ✅ `[executed]` — replayed old rules over HEAD corpus via a harness validated against the working tree (reproduces 0/0). Both endpoints exact. |
| Pattern-5 `(?!\+)` lookahead correct | ✅ `[executed]` — `(v5.5.0+)` skipped, `(v5.5.0)` matched; old comment was indeed wrong (old pattern matched `5.5.0+`) |
| Fence stripping (nested/tilde/info-string/unclosed) | ✅ `[executed]` — probes behave per CommonMark; QUICKSTART_DEVELOPERS 4-backtick fix (docs/QUICKSTART_DEVELOPERS.md:104) is both correct rendering and required by the new scanner |
| Retargets point at real targets | ✅ `[executed]` — all 12 verified (`skill-format-spec.md`, `SECURITY.md`, `docs/PHILOSOPHY.md`, `archive/version_05.md`, `archive/DISCUSSION_SUMMARY.md`, `archive/SKILL_UNDERSTANDING_SUMMARY.md`, `QUICKSTART_SKILL_INSTALLATION.md`, `CONTRIBUTING.md`, `docs/api/`, `CLI_REFERENCE.md` ×3, `../ROADMAP.md`) |
| Anchor validation real, not goalpost-moving | ✅ `[executed]` — all 4 fragment links that the *old* checker falsely broke now validate against GitHub slugs (incl. em-dash `v800--autonomous-loop-system`) |
| Removed targets genuinely dead | ✅ `[executed]` — `superpowers/plans/`, 3× `dev/*`, `KIMI_REVIEW*` (nowhere in repo), `docs/adapters/`, `adapter-protocol`, `semantic/config.md`+`performance.md`, `docs/claude-code/` all absent at referenced paths |
| Dual-word guard blocks the admitted over-reach class | ✅ `[executed]` — `"Phase 1: Current Platforms (v4.3.0)"` untouched; `"current version is v6.2.0"` → `v8.1.0` (v-prefix preserved) |
| Generator unchanged & already emits real version | ✅ `[inspected]` — `src/vibesop/adapters/_generation.py:29,96` default `version: str = __version__`; diff touches no adapter code |
| No 8.1.0 inside code fences | ✅ `[executed]` — 35 fence-internal example versions intact (1.0.0 frontmatter, git tags), zero 8.1.0 |
| `.vibe/config.toml` de-linking | ✅ good judgment — the file exists but is untracked runtime state; a retarget would break the checker on fresh clones |

## Findings

1. **MINOR — v5.5.0 milestone lost from the pointer target.** docs/ROADMAP.md's completion table (line 614 area) jumps v5.3.0 → v6.0.0; v5.5.0 appears nowhere in the file `[executed]`. The deleted README checklist was the only milestone-record home; facts survive only in CHANGELOG.md:1240 (exempt file). README.en.md's new text promises "the full list of completed milestones (v4.0–v6.2 and beyond)" — it overpromises. *Residual risk: reader following the pointer misses the Spec v3.0 / Conformance milestone. Fix: one table row.*

2. **MINOR — `--fix` produces passing garbage on dev-suffixed headers.** `> **Version**: 8.2.0.dev0` → `8.1.0.dev0` `[executed]` — which then *passes* the checker (pattern captures 8.1.0). This is exactly the header form the repo had; only manual cleanup saved it this run (scripts/check_doc_versions.py:175-184). Also: `> **文档版本**：v8.0.0` is flagged by the checker but never fixed by `--fix` — flag/fix surface mismatch on Chinese docs. *Residual risk: future `--fix` runs silently corrupt dev-version headers.*

3. **MINOR — `--fix` pattern-4 rewrites foreign versions in prose.** `"Python version: 3.12.0 required"` → `"Python version: 8.1.0 required"` `[executed]`. None exist today (green proves it), but `--fix` is now a live, documented flag and its "declaration" scope is syntactic, not contextual. *Residual risk: one future sentence about a tool version gets nuked.*

4. **MINOR — zh/en README factual divergence preserved and normalized.** README.md:679 now says 3-pillar introduced "(v8.0.0+)" while README.en.md:683 and docs/architecture/ARCHITECTURE.md:6 say v6.2.0+. Pre-existing error, faithfully kept per policy 3 — but the diff touched this exact line. *Residual risk: contradiction is now greppable-permanent.*

5. **NIT — calibration gaps, none currently triggered** `[executed/inspected]`: pattern 5 still flags sentence-final since-markers (`since v4.2.1.`) and prose `pkg@v1.0.0` outside fences; check_docs.py false-positives on link titles (`[x](y "t")`) and duplicate-heading anchors (`#h-1`) — both absent today; 4+-space indented fences treated as fences (benign for stripping).

6. **NIT — three different dodges for one semantic class**: parentheticals → `+`, headings de-v'd (`### v1.0.0`→`### 1.0.0`, ARCHITECTURE.md v5.x), prose precision-loss (`removed in v4.1.0`→`v4.1`), one `4.4.x`. All fact-preserving; stylistically inconsistent.

7. **NIT — exemption-set hygiene**: HISTORICAL_FILES carries dead entries (`docs/version_05.md`, `docs/DISCUSSION_SUMMARY.md` — both now only in `docs/archive/`); adr/003 & adr/005 unexempted while 001/002/004 are (harmless today — verified no X.Y.Z strings in either `[executed]`, but latent tripwire); GENERATED_FILES comment claims CLAUDE.md carries "1.0.0" — it carries no version at all `[executed]`.

8. **NIT — INDEX.md disposition inconsistency**: "Technical Planning" entries dropped although their targets exist in `docs/archive/` (CLI_OPTIMIZATION_PLAN.md, PRODUCTION_READINESS_REVIEW.md, roadmap-index.md) while other archive files were retargeted *into* the index. Plus README.en.md:849-851 stacks two ROADMAP pointers; docs/ROADMAP.md:299 link text still reads "docs/version_05.md" over an archive/ target.

## Reconciliation

173 → 0 and 53 → 0 both measured exactly `[executed]`. Dispositions: ~⅔ doc edits (verified real targets), README.zh-CN (13) + adr/004 (9) + `.pi` (10 generated files) exempted with verified justification (banner `[executed]`; generator-version claim `[inspected]`), archive/ link-exemption covers 11 of the 53 (all point-in-time snapshots). No file went green by exemption that didn't deserve it; no content deleted that had a live retarget available (KIMI_REVIEW exists nowhere; adapters/ dir never existed).

No files were written during this review (all probes were in-process; the two filesystem attempts were denied and abandoned).
