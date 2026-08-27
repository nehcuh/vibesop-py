# S51 Merged Review — `e286e67..f6a90fd` (gate45 + gate46)

> Date: 2026-08-27
> Window: 22 commits, 63 files, +3237/−1736; HEAD `f6a90fd`
> Lanes: A correctness/security · B architecture · C platform/Windows/routing invariants
> Rule: independent evidence only. Missing lane would be unavailable-review, not approval.

## Final recommendation: **REQUEST CHANGES**

| Lane | Verdict | Status | BLOCKER | MAJOR | MINOR |
|------|---------|--------|---------|-------|-------|
| A correctness | NEEDS_FIX | — | 0 | 2 | 4 |
| B architecture | NEEDS_FIX | WATCH | 0 | 3 | 5 |
| C invariants | NEEDS_FIX | 6 HOLD / 6 BROKEN | 0 | 4 | 5 |

Synthesis (brief + OMX gate): architect is **WATCH** (not BLOCK); every lane returned evidence; **any MAJOR → REQUEST CHANGES**. No APPROVE path.

Do not cut 8.1.2 from this window until the MAJOR punch-list is dispositioned (fix or explicit decline with record).

## What the three lanes independently agreed is closed

Do not re-work these as remaining defects:

- Wheel force-include of `core/skills` + `registry.yaml` + policies; hatchling never consumed the deleted `MANIFEST.in`. Fresh wheel has 18 `builtin_skills` + `builtin_data/core/registry.yaml` (C executed `uv build`; A agrees packaging shape is right).
- `\n{5,}` removal + empty-vs-unsafe split does not deliver phrase-injection as a data notice (A, with `tests/security/test_scanner.py`).
- M2: `vibe verify` Git-Bash scan is scoped to vibesop hook commands; user PowerShell is not flagged (A/C).
- Claude `bash_hook_command` emits quoted POSIX path, not Git-`bash.exe` wrapper (C HOLD).
- Grok `routing.md` builtin count is dynamic **18**, not stale 50+/14 (C executed). Docs INDEX / SKILLS_GUIDE say 18.
- CI Lint is `ruff check .` + `ruff format --check .` (C).
- Documented 8.1.2 leftovers C1 (whitelist canary) / C2 (substring preserve-matcher): **unchanged, not worse**. Stay on the leftover list.

## MAJOR punch-list (must-fix or decline-with-record)

Empirical pattern held: **the three lanes' MAJORs barely overlap**. Complementary pairs are noted, not collapsed.

### M1 — Spaced Windows home is not rewritten (Lane A)

- File: `src/vibesop/utils/hook_commands.py:34`
- Fact: `_PATH_ALLOWED` has no space. After unwrap, `"C:/Users/First Last/.claude/hooks/vibesop-mirror-prompt.sh"` → parse `None` → leave the Git-`bash.exe` wrapper. [executed] on win32. Route entries still get a fresh `bash_hook_command`; preserved non-route vibesop scripts do not. Tests only use `C:/Users/h/` and `C:/Users/HuChen/`.
- Fix: allow space only inside an already-absolute quoted token; add rewrite test for `First Last` + `vibesop-mirror-prompt.sh`. Keep rejecting `` `$%^ ``.

### M2 — `ambiguous_only` orchestration skip is test-only (Lane A) + writes anti-signal (Lane B)

Two facts, one product claim ("learning signal hole closed"):

- A: `ExecutionStep` has no `confidence`. `_needs_confirmation` does `getattr(step, "confidence", 0)`. Production `all_confident` is always false → still always prompt on TTY. The new recording test stuffs confidence onto a `SimpleNamespace`, not an `ExecutionStep`.
- B: even if that skip fired, it records `success=False` into `SequencePattern.is_candidate` (`total_count >= 5` and `success_rate >= 0.8`). Auto-proceeds drive the rate toward 0. The aha/hook path never calls `record_sequence` at all.
- Fix: add `confidence` to `ExecutionStep` and pass PlanBuilder's value; do not put auto-proceed in the failure numerator (omit, or a third class). Changelog must not claim the instinct loop is un-starved until promotion polarity is honest. Document aha/hook as out of plan-sequence learning.

### M3 — No single builtin-resolution policy (Lane B)

- Files: `bundled.py`, `skill_injector.py`, `loader.py`, `candidate_manager.py`, `grok_build.py`, `_content.py`
- Fact: five readers disagree on order. Any `cwd/core/skills` shadows the installed wheel for injection/SkillLoader (no identity check). Grok count uses `__file__`, not `project_root`. Adapter `find_skill_content` was **not** migrated — wheel `vibe build` can still write Jinja stubs while the hook injector loads bundled SKILL.md. CandidateManager `insert(0)` comment ("exactly one of the two exists") is false for `uv tool` + cwd-in-clone.
- Fix: one `resolve_builtin_skills_dir` with a vibesop-checkout identity test: identified checkout → wheel `builtin_skills` → stop. Route loader, injector, Grok count, and `find_skill_content` through it. Test: foreign `cwd/core/skills/code-review` must not shadow the wheel.

### M4 — Four demo skills are always-on catalog, not a demo flag (Lane B) + they steal pack phrases (Lane C)

Complementary:

- B: `trusted_builtin`, force-included in every wheel, SKILLS_GUIDE still "必须启用 / P0". Dual-state tests **require** demo queries to beat installed packs. Routing winners changed in a "patch" window.
- C [executed]: isolated HOME `LightweightRouter`:
  - `write tests` → `builtin/commit-message` levenshtein 0.5 (even with a superpowers TDD fixture that tags the phrase)
  - `review my changes` → `builtin/code-review` levenshtein 1.0 (with a `superpowers/review` fixture)
  - The mis-hit archive only forbids `layer == "keyword"`, so levenshtein steal stays green.
- Fix (pick one, record it):
  1. Gate the four behind `--demos` / `builtin.demos` default-off for existing configs, **or**
  2. Keep them on, treat 8.1.2 as a minor product release, strip `"review my changes"` from tags, drop `"write tests"` from builtin triggers, and pin `write tests` must not land on `builtin/*` at any layer when the TDD pack is present.

### M5 — Dual-platform probe is still Grok CLI twice (Lane C) + `--platform` "flag wins" is false (Lane B F6 / Lane C F1)

- Fact: `probe-inject.sh` never passes `--hook --platform`. Both lanes send Claude-shaped `prompt`/`session_id` plus a synthetic `platform` field the deployed Grok hook (`vibe route --hook`, no flag) does not send. Claude's generated `settings.json` command is never `bash -c`'d. Help says flag wins; code treats default `"grok-build"` as unset, so `--platform grok-build` loses to JSON `platform: claude-code`.
- Fix: probe Claude via generated command + `bash -c` from a non-repo cwd; probe Grok with camelCase envelope **without** `platform`; default `--platform` to `None`; add a CLI test that explicit flag is distinguishable from omitted.

### M6 — Windows E2E is not the 8.1.0 failure class (Lane C)

- File: `.github/workflows/quickstart-e2e.yml`
- Fact: `windows-latest` + `defaults.run.shell: bash`. `uv tool install` happens before HOME redirect. Hook assert is file grep for `vibe route --hook`. No `vibe verify`. UV 0.8.17 vs CI 0.11.19. Does not spawn Grok JSON as the host would, does not run Claude hook from a stock user PATH.
- Fix: align UV with CI; `vibe verify` both platforms under scratch HOME; execute Claude `settings.json` command with `bash -c` from `runner.temp`; Grok camelCase envelope, no `platform` field.

### M7 — `vibe verify pi` silent all-FAIL (Lane C)

- File: `src/vibesop/cli/commands/verify.py`
- Fact: pi declares 7 check_ids; `_check_platform` has no branch for 6 of them → initializer `pass=False`. This window rewrote the Git-Bash scan in the same function and did not add handler-completeness. Pre-existing, **not closed**, in the highest-risk set.
- Fix: implement the six branches or delete orphan ids. Assert `set(PLATFORM_CONFIGS[p]["checks"]) <= handled_ids` for every platform.

## MINOR (do not block 8.1.2 if MAJORs are handled)

Deduplicated. Full text stays in the lane files.

| ID | Lanes | One-liner |
|----|-------|-----------|
| n1 | A F3 | Empty-content gate is unanchored `CONTENT_NOT_FOUND_MARKER in skill_content` → classification skip |
| n2 | A F4 | 1-token Windows backslash vibesop command not rewritten (verify will fail it) |
| n3 | A F5 / C F9 | `probe-inject.sh` interpolates `$QUERY` into JSON; stderr discarded; hook always exits 0 |
| n4 | A F6 | `test_bundled.py` asserts path construction, not that hatch packed the files |
| n5 | B F4 | classify vs parse are two policies sharing only the basename set — keep split, pin a shared corpus |
| n6 | B F5 | force-include is wheel-only; no sdist counterpart; no from-sdist CI job |
| n7 | B F7 / C F7 | `inject_execution_plan` does not map GROK_BUILD to additionalContext |
| n8 | B F8 / C F9 | aha queries hardcoded; Grok count docstring disagrees with CandidateManager insert order |
| n9 | C F5 | `cursor` in SUPPORTED_PLATFORMS + verify, missing from installer/quickstart/renderer; leftover `len >= 2` |
| n10 | C F6 | Grok JSON still bare `vibe route --hook` with no PATH prefix (invariant 3 unchanged) |
| n11 | C F8 | `test_demo_injection.py` does not patch `EXTERNAL_PATHS` ClassVar |

## Watchlist (architect; non-blocking if MAJORs dispositioned)

- C1/C2 leftovers: rewrite is *more* conservative, C2 not worse.
- `uv tool install` + cwd in an older/newer clone: treat as a version-pin ritual until M3 identity check exists.
- Adapter `SKILL.md.j2` stubs vs runtime injector: two SKILL.md producers; wheel `vibe build` should copy bundled SKILL.md or refuse stubs for `builtin/*`.
- `ambiguous_only` vs PHILOSOPHY: the default itself is coherent; the defect is M2 polarity/dead path, not the default.
- Demo triggers vs tags: keyword-layer steal is tested; explicit/levenshtein steal is the C executed hole (M4).

## Invariant scorecard (Lane C, not re-judged)

BROKEN: single platform set; Grok JSON `vibe` on PATH; `vibe verify` pi handlers; EXTERNAL_PATHS in new injection test; demo tag/trigger steal; Windows E2E as dual-platform host smoke.

HOLD: VibeSOP install markers; Claude quoted POSIX command; shell uv-tool Python lookup (template); builtin count 18; wheel force-include; M2 Git-Bash scan; CI Lint isomorphism.

## Lane artifacts

- Brief: `docs/decisions/_review-s51-gate45-46-brief.md`
- A: `docs/decisions/_review-s51-lane-correctness.md`
- B: `docs/decisions/_review-s51-lane-architecture.md`
- C: `docs/decisions/_review-s51-lane-invariants.md`

## Next (needs user call)

1. Fix M1–M7 in this window, or
2. Decline specific MAJORs with a written record (S50 style) and ship a narrower 8.1.2, or
3. Split: hook/packaging patch now; demo-skill catalog + E2E host-smoke as a follow-up minor.

Orchestrator did not modify production source during review (invariant: 复审运行期间不改被审文件).
