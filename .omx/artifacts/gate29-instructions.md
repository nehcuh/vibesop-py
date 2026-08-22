# Gate 29 review — doc-debt cleanup: checker calibration + 173 version mismatches + 53 dead links

You are an independent senior reviewer. The attached diff (37 files) cleans up doc debt in VibeSOP (/Users/huchen/Projects/vibesop-py). Both checkers now report GREEN (0 version mismatches, 0 broken links) from a baseline of 173 + 53.

## Policy (fixed by the project owner — do not relitigate, DO verify faithful execution)

1. `(vX.Y.Z+)` = historical "since" marker → docs unchanged, checker's pattern 5 got a `(?!\+)` negative lookahead (its old comment claimed it avoided `5.5.0+` but `\b` actually matched).
2. Header `> **Version**:` declarations and "current: vX.Y.Z" references → must equal pyproject version (8.1.0); docs updated.
3. Bare `(vX.Y.Z)` "since" markers → normalized to `(vX.Y.Z+)` in docs (facts unchanged).
4. Generated files (AGENTS.md/CLAUDE.md carry config-format/generator version 1.0.0, not app version) → new GENERATED_FILES exemption; generator itself was NOT changed (agent verified `generate_agents_md(version=__version__)` already emits the real version; the checked-in files are stale snapshots).
5. `--fix` flag was parsed-but-dead → implemented minimally (declaration contexts + dual-word "current"+"version" lines only; never fences, never since-markers).
6. check_docs.py rewritten: fence stripping (CommonMark length rule), bare-text heuristic (link targets must contain `/` or `.`), docs/archive/ exemption (aligned with the version checker), real anchor validation against GitHub slugs, plus two checker bug fixes (missing re.MULTILINE in heading regex; fenced-block toggling with indentation/tilde/nesting).
7. docs/adr/004 added to HISTORICAL_FILES (001/002 already were); README.zh-CN.md exempted as a self-declared stale snapshot (deletion decision left to the user); .pi/ added to SKIP_DIRS (generated deploy output).

## Claims to verify adversarially

- Both checkers exit 0 now (`uv run python scripts/check_doc_versions.py`, `uv run python scripts/check_docs.py`) — run them.
- Checker calibration didn't just move the goalposts: the new fence-stripping and `+`-lookahead rules are correct (probe edge cases: nested fences, tildes, indented fences, `v1.2.3+` vs `v1.2.3`, `pkg@v1.0.0` in code spans).
- --fix implemented as claimed; check for over/under-reach (the agent admits one real over-reach it fixed: "Phase 1: Current Platforms (v4.3.0)" — verify the dual-word guard actually prevents that class).
- Doc edits: since-normalizations don't alter facts; dead-link retargets point at REAL targets (spot-check at least 10, including docs/version_05.md → docs/archive/version_05.md and SKILL_SPEC → skill-format-spec); removed links/entries are genuinely dead targets; no content deleted that should have been retargeted.
- Roadmap checklist replacement in README.md/README.en.md: 27 stale lines replaced with a pointer to docs/ROADMAP.md — verify nothing of unique value was lost.
- The --fix audit claim: 16 fence-internal example versions were restored — confirm no 8.1.0 landed inside a code fence anywhere in the diff.
- 173 baseline − exemptions − normalizations − fixes = 0 should reconcile; any file that went green by exemption alone that SHOULDN'T be exempt?

## Output

Verdict PASS / PASS_WITH_NITS / BLOCK + numbered findings with severity + file:line refs + one-line residual risk. Be adversarial; do not rubber-stamp.
