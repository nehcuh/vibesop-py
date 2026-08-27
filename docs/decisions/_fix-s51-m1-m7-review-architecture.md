# Fix Plan Review — S51 M1–M7 (architecture / devil's advocate)

- Reviewer: independent general-purpose agent (plan confirm, not implement)
- Plan: `docs/decisions/_fix-s51-m1-m7.md` (v1)
- Spec: `docs/decisions/_review-s51-gate45-46-merged.md`
- HEAD: `f6a90fd`
- Files actually read: plan + merged review + lane-architecture; `src/vibesop/utils/bundled.py`; `src/vibesop/utils/hook_commands.py`; `src/vibesop/agent/runtime/skill_injector.py`; `src/vibesop/agent/runtime/agent_runtime.py`; `src/vibesop/core/skills/loader.py`; `src/vibesop/core/routing/candidate_manager.py`; `src/vibesop/adapters/_content.py`; `src/vibesop/adapters/grok_build.py`; `src/vibesop/adapters/claude_code.py`; `src/vibesop/adapters/pi_coding_agent.py`; `src/vibesop/adapters/templates/shared/vibesop-route.sh.j2`; `src/vibesop/cli/main.py`; `src/vibesop/cli/confirmation.py`; `src/vibesop/cli/commands/verify.py`; `src/vibesop/core/models.py`; `src/vibesop/core/orchestration/plan_builder.py`; `src/vibesop/core/orchestration/workflow_engine.py`; `src/vibesop/core/instinct/learner.py`; `src/vibesop/core/instinct/tool_sequences.py`; `src/vibesop/core/routing/orchestrator.py`; `src/vibesop/core/routing/unified.py`; `src/vibesop/core/matching/strategies.py`; `src/vibesop/builder/renderer.py`; `src/vibesop/installer/installer.py`; `src/vibesop/installer/quickstart_runner.py`; `pyproject.toml`; `core/skills/{code-review,test-generation,commit-message,systematic-debugging}/SKILL.md`; `docs/SKILLS_GUIDE.md`; `CHANGELOG.md`; `scripts/demo/probe-inject.sh`; `.github/workflows/{quickstart-e2e.yml,ci.yml}`; `tests/core/routing/test_demo_skills.py`; `tests/cli/test_plan_sequence_recording.py`; `tests/cli/test_route_commands.py`; `tests/utils/test_bundled.py`
- Architectural Status: **WATCH**
- Verdict: **REJECT**
- Counts: 0 BLOCKER / 3 MAJOR / 5 MINOR

Direction of the locked table is right. The spec as written will TDD-green a local-true 8.1.2 that leaves the original M3 policy split, an unbounded M4 routing-policy hole, and an M6 host-smoke that is still not the 8.1.0 failure class. Do not start implementation until the must-lock punch-list is in the plan.

Routing note: this turn matched `fuck-my-shit-mountain` (no SKILL.md on disk). Followed the user's explicit architecture-review brief (same exception as S51 lane review).

## Strongest counterargument against shipping this plan

The merged MAJOR was **one builtin-resolution policy**. This plan adds `resolve_builtin_skills_dir` and then (1) identifies a checkout with a raw substring `name = "vibesop"` that is both too weak and too strong, (2) re-admits checkout-wins as rung 3 via `__file__` without an exist-gate, (3) writes a test that passes in this editable repo without ever proving the wheel beat a foreign `core/skills`, and (4) leaves `to_hook_response`'s hint ladder and the injector's `candidate_dirs[0] = project_root/core/skills` on the old order. That is the cmspark ghost-skill class with a new helper name. Compounded by M4's "smallest levenshtein change if the pin fails" — an implementer-discretion hole large enough to mutate last-resort routing to make a test green — and M6's `bash -c "$cmd"` smoke that can pass while jq is missing, cwd is the clone, and the script's `INPUT=$(cat)` is fed `userPrompt` JSON the jq filter does not read. Local-true, MAJOR still open.

---

## Findings

### F1 — Severity: MAJOR — M3 identity is the wrong test, the test does not prove the contract, callers are incomplete

- File: plan M3; `src/vibesop/utils/bundled.py:23`; `src/vibesop/agent/runtime/skill_injector.py:240-295`; `src/vibesop/agent/runtime/agent_runtime.py:193-229`; `src/vibesop/core/skills/loader.py:109-114`; `src/vibesop/installer/installer.py:229-234`; `src/vibesop/adapters/templates/shared/vibesop-route.sh.j2:43`; `pyproject.toml:2`; `tests/utils/test_bundled.py:63-74`
- Fact vs suggestion: **Fact** about current ladders and the plan's API/tests. Suggestion is the lock required before TDD.
- Description: `name = "vibesop" in pyproject.toml` is not an identity policy. Combined with "identified checkout → wheel → `__file__` checkout" and no exist-gate, the plan does not close "foreign `cwd/core/skills` must not shadow the wheel."

**Too weak.** The plan's identity is a substring, not a TOML `[project].name`. False positives: any other table or comment that contains the exact bytes `name = "vibesop"`; a workspace/tool table; a vendored snippet. The hook script already uses an even weaker grep (`name[[:space:]]*=[[:space:]]*"vibesop"` at `vibesop-route.sh.j2:43`) that also matches `name = "vibesop-tools"`. Copying that heuristic into Python is consistency with a known-loose matcher, not a fix. cmspark inversion class is "cwd looks like a skills tree"; a foreign pyproject that happens to mention the string is enough to re-open it.

**Too strong.** False negatives: `name='vibesop'` (PEP 621 single quotes), `name="vibesop"` (no spaces), `name = "VibeSOP"` (PyPI-normalized). This repo currently has `name = "vibesop"` (`pyproject.toml:2`) so the canonical checkout matches; a hatch/format drive-by or a fork that keeps `core/skills` but retitles the project falls through to the wheel (stale-in-checkout), which is the inverse of the bug being fixed.

**Dropping sys.path does not break standard editable installs.** [inspected] `src/vibesop/` has no `builtin_skills/` directory — hatch `force-include` is wheel-only (`pyproject.toml:106-109`). Hatchling editable: `import vibesop` loads `src/vibesop/__init__.py`; `bundled_path("builtin_skills")` is a missing path; `__file__`.parent.parent.parent / `core/skills` is the repo and is the live source. `bundled_path` via `vibesop.__file__` already covers wheel/uv-tool/pipx. The injector's sys.path scan (`skill_injector.py:287-295`) was redundant with `bundled_path` for any importable `vibesop`, and could pick a *different* `sys.path` entry's `vibesop/builtin_skills` than the imported package. Drop it. Do not drop the exist-gate.

**The third rung re-opens checkout-wins.** Order "identified `project_root` → wheel → `__file__`-derived identified checkout" is the right *idea* for editable+foreign-cwd (live checkout skills, because the wheel copy does not exist). It is only safe if `resolve_builtin_skills_dir` exist-gates each rung and returns the first *existing* dir. The plan's signature returns `Path` with no exists() contract. If implementers `return bundled_path("builtin_skills")` whenever `project_root` is not identified, every editable pytest / `uv run vibe` from a scratch cwd sees an empty builtins dir.

**The specified red test does not prove wheel-over-foreign.** `test_foreign_core_skills_does_not_shadow_wheel` asserts

```text
resolved == bundled_path("builtin_skills")
or not (tmp_path / "core" / "skills") == resolved
```

In this checkout, identity on `tmp_path` fails, `src/vibesop/builtin_skills` does not exist, rung 3 returns *this repo's* `core/skills`. The `or` clause is then true. The test is green without a wheel, which is exactly today's `test_repo_checkout_skills_still_discovered` lie (`tests/utils/test_bundled.py:63-74`: "exactly one builtin source exists"). Lane B F1 named that comment false for `uv tool` + cwd-in-clone. The plan reproduces it.

**Callers list is not "one policy."** Plan routes loader, injector *strip_bases*, CandidateManager, Grok count, `find_skill_content`. It does not route:

1. `AgentRuntime.to_hook_response` hint (`agent_runtime.py:193-229`) — still `user_root/core/skills` first, then bundled, `__file__` repo, sys.path. The banner can inject wheel SKILL.md while `NEXT STEP: read` points at the foreign file. Original lane-B F1 listed this; the merged punch-list dropped it; the plan followed the merge. The ghost-skill class lives in the path the agent actually Reads.
2. Injector `candidate_dirs[0] = self.project_root / "core" / "skills"` (`skill_injector.py:240-241`). Strategy 0 (namespace strip) only runs when `"/" in skill_id`. Bare ids (`code-review`) skip Strategy 0 and hit the foreign tree first. Injector docstring (`:210-214`) says routing can return the bare `name:` field.
3. `bundled_core_file` (`bundled.py:23-29`) still prefers any `project_root/core/<name>` with no identity — registry/policies, not skills, but it is the other half of "bundled.py is the policy."
4. `VibeSOPInstaller._get_project_root` (`installer.py:229-234`) still returns the first of cwd / cwd/src / `__file__` ancestor that has `core/skills`, no identity. It is the `project_root` fed to `ConfigRenderer` / `find_skill_content`. Identity inside `resolve_*` can still save it *if* identity is real; with a substring it does not.

- Suggestion (must-lock):
  1. `is_vibesop_checkout(root)`: `tomllib` load; `canonicalize_name(project.name) == "vibesop"`; `(root / "core" / "skills").is_dir()`. No substring. Align the hook grep later (out of this MAJOR if documented); do not copy it.
  2. `resolve_builtin_skills_dir`: first *existing* of identified `project_root/core/skills` → `bundled_path("builtin_skills")` → identified `__file__`-derived repo `core/skills`. Return a missing wheel path only when nothing exists (callers already skip missing).
  3. Callers: every reader in lane-B F1, including `to_hook_response` hint and injector `candidate_dirs` builtin slot. `bundled_core_file` either uses the same identity or is explicitly declined-with-record as registry-only.
  4. Tests: fake a wheel dir with distinctive content (`# WHEEL`) *and* patch `__file__` so rung 3 is not this clone; foreign `core/skills/code-review/SKILL.md` (`# FOREIGN`) must not be returned. Identified-checkout test stays. Rename sys.path test as the plan says.
- Status: open — blocks implementation

### F2 — Severity: MINOR — M2 omit is the right polarity; CHANGELOG retract is enough; two leftovers

- File: plan M2a–c; `src/vibesop/cli/main.py:326-348,1429-1440`; `src/vibesop/cli/confirmation.py:93-99`; `src/vibesop/core/instinct/learner.py:118-123,791-853`; `src/vibesop/core/routing/orchestrator.py:486-520`; `src/vibesop/core/models.py:317-429`; `src/vibesop/core/orchestration/plan_builder.py:403-418,622-641,745-760,775-795,848`; `CHANGELOG.md:37-41`
- Fact vs suggestion: **Fact** that omit stops anti-signal on the skip path and that unattended still writes `success=False`. Suggestion is documentation + constructor completeness, not a third-class schema.
- Description: Adding `ExecutionStep.confidence` so `_needs_confirmation` stops using `getattr(..., 0)` is the correct model fix (M2a). Auto-proceed **omit** (M2b) is the right polarity for a promoter that requires `total_count >= 5 and success_rate >= 0.8` (`learner.py:122-123`): `success=False` is anti-signal; `success=True` without a human violates the privacy rule (`cli/main.py:329-332`). Retracting "instinct loop un-starved" (M2c) is necessary and **sufficient** for the product claim. Appearance of jsonl rows was never promotion.

Does omit starve anything else? Yes, by design: `get_sequence_candidates`, dashboard `sequence_candidates`, volume stats. The default TTY `ambiguous_only` path will write **zero** plan-sequence rows. That is honest starvation, not a remaining MAJOR, provided CHANGELOG says so. aha/`--hook` already never call `record_sequence` (`quickstart_runner.py` / hook returns before CLI context). `<3` steps already no-op. tool-sequence capture (`tool_sequences.py`) is a different loop — do not imply it is fed by this patch.

Leftovers (do not reopen M2 as MAJOR):

1. Unattended (`--yes` / `--json` / non-TTY / `never`) still records `success=False` in `Orchestrator._record_plan_sequence` (`orchestrator.py:505-520`) via `_sequence_unattended`. The plan only omits the confirmation skip point. High-volume `--yes` still poisons the promoter. Document as remaining anti-signal or omit there too (one line, same task).
2. PlanBuilder's routed `ExecutionStep(...)` at `:403` is the only constructor the plan names. Squad / synthesise / verify / judge / workflow-engine appends (`plan_builder.py:622,745,775,848`; `workflow_engine.py:607`) stay at default `0.0`. Fail-closed for `ambiguous_only` (will prompt). Fine. Pass `confidence=` on the routed constructor; leave synthetic steps at 0 unless you have a real value.
3. Replacing `test_ambiguous_only_auto_proceed_records_application_only` is required — that test currently *demands* the anti-signal (`test_plan_sequence_recording.py:113-152`).

- Suggestion: keep M2a/b/c. CHANGELOG Unreleased must replace `:37-41` with the plan's sentence. One extra sentence: unattended still application-only / still in the failure numerator unless also omitted. Do not invent a third class this patch.
- Status: open as nit; not a reason to REJECT alone

### F3 — Severity: MAJOR — M4 "smallest levenshtein change if pin fails" is an unbounded routing-policy hole

- File: plan M4 last paragraph; `tests/core/routing/test_demo_skills.py:46-56,192-204`; `core/skills/test-generation/SKILL.md:8-11`; `core/skills/code-review/SKILL.md:5-6`; `src/vibesop/core/routing/unified.py:824-875`; `src/vibesop/core/matching/strategies.py:708-782`
- Fact vs suggestion: **Fact** that the contingency licenses any matcher change that makes one pin hold. Suggestion is to delete the contingency from the locked table.
- Description: Option 2 (keep four demos always-on, strip steal phrases, pin pack-owner at **any** layer) is a coherent product call; `--demos` default-off would kill gate46. Frontmatter edits are scoped:

  - drop tag `"review my changes"` (keep trigger `"look over my changes"`)
  - drop trigger `"write tests"` (keep `"write unit tests"`)
  - add superpowers/review fixture; `PACK_OWNED_QUERIES` both phrases; `assert not str(got).startswith("builtin/")`

  That pin is the contract. The next sentence is the hole: "If after tag/trigger strip `write tests` still hits `builtin/commit-message` via levenshtein, **do not weaken the test**. … Implement the smallest change that makes the pin hold without breaking `VERIFIED_DEMO_QUERIES`." Allowed examples include raising last-resort threshold for builtin demos **or** excluding demo ids from levenshtein.

  Lane C already measured `write tests` → `builtin/commit-message` levenshtein 0.5 with a TDD fixture in the pool. Token matcher (`strategies.py:750-782`) scores query tokens against name/tags/id pieces; `commit-message` shares no "write"/"tests" tokens, but `test-generation` still has description "Write focused unit tests" and tags `unit test` / `写用例` — after trigger strip, keyword/explicit should miss, and last-resort may still land on a builtin. "Smallest change" lets the implementer:

  - raise `MatcherConfig.min_confidence` globally (silences real typos)
  - special-case `query == "write tests"`
  - exclude *all* `builtin/*` from levenshtein (breaks keyless typo hits for slash/session-end)
  - mutate `_run_matcher_pipeline_levenshtein_last` (gate7 already burned us on matcher-list races)
  - edit commit-message tags until the pin is green and a different pack phrase now steals

  A pin that must not be weakened plus a blank check to change the matcher is how a local-true dual-state test ships a routing-policy regression the mis-hit archive will not catch (it only forbade `layer == "keyword"`; the plan correctly tightens that — then hands the implementer the layer it just started caring about).

- Suggestion (must-lock): delete the contingency paragraph. Task is frontmatter + pin + SKILLS_GUIDE P0→P1 for the four aha demos (`docs/SKILLS_GUIDE.md:69-75` still "必须启用 / 优先级最高（P0）" for all Builtin). If the pin is red after the strip, **stop and write a one-page design**; the only pre-approved intervention is "exclude the four demo ids from the levenshtein last-resort pass, not from keyword/explicit." No threshold change, no global builtin exclusion, no query special-case. `VERIFIED_DEMO_QUERIES` remain keyword/explicit hits (`look over my changes before I push`, `write unit tests for this module`).
- Status: open — blocks implementation

### F4 — Severity: MAJOR — M5/M6 `bash -c "$cmd"` feeds stdin to `cat`, not to a parsed prompt, on windows-latest

- File: plan M5/M6; `src/vibesop/adapters/claude_code.py:24-41`; `src/vibesop/adapters/templates/shared/vibesop-route.sh.j2:1-31,123-134`; `src/vibesop/cli/main.py:494-664`; `scripts/demo/probe-inject.sh:20-25`; `.github/workflows/quickstart-e2e.yml:21,37-39,60-81,113-141`; `.github/workflows/ci.yml:14`
- Fact vs suggestion: **Fact** about command shape, script stdin, jq fields, E2E cwd/HOME. Suggestion is the invocation lock.
- Description: M5's CLI sentinel (`--platform` default `None`, explicit flag > JSON > grok-build) is the right fix for lane-B F6. Grok JSON becoming `vibe route --hook --platform grok-build` makes "flag wins" true for the deployed hook. Probe-inject using `--platform claude-code` vs omitted-flag camelCase is two real platform strings. That part can ship.

  The leftover of merged M5 ("Claude's generated `settings.json` command is never `bash -c`'d") is parked on M6. M6 as written will go green without being the 8.1.0 class.

  **Will `bash -c "$cmd"` feed stdin to the script on windows-latest?** Yes, in the narrow sense. `bash_hook_command` on win32 is a quoted POSIX path (`claude_code.py:38-41`), e.g. `"D:/a/_temp/scratch-home/.claude/hooks/vibesop-route.sh"`. Claude Code runs that string via Git Bash `-c` (S48). `bash -c '"/path/to/vibesop-route.sh"'` uses the quoted path as the command word and **inherits stdin**. The script's first action is `INPUT=$(cat)` (`vibesop-route.sh.j2:10`). So the pipe reaches `cat`.

  That is not the same as "the hook parsed the envelope and routed the query":

  1. jq field list is `.prompt // .user_prompt // .query // .message // .text` — **not `userPrompt`**. Plan M6 says "a `userPrompt` stdin JSON (or whatever the script expects)." Implementers following M5's Grok envelope will send `userPrompt`. With jq present, QUERY is empty, then `[ -z "$QUERY" ] && QUERY="$INPUT"` feeds **raw JSON** to `handle_query_for_hook` as argv (`:123-134`). The demo phrase may still keyword-hit as a substring of the JSON. Local-true.
  2. windows-latest Git Bash does not ship jq. The jq branch is skipped; QUERY is raw JSON always. The smoke never exercises the parse path Claude Code uses on a machine that has jq (or the Claude host's own JSON).
  3. The Python `-c` driver takes QUERY as **argv**, not stdin. After `cat`, stdin is consumed. `bash -c` did its job; asserting `[ACTIVE SKILL]` on a JSON blob is not asserting host-shaped parsing.
  4. `vibe verify … must exit 0` under scratch HOME without locking **cwd**:
     - cwd = `GITHUB_WORKSPACE`: `project_claude_md` is this repo's `CLAUDE.md` — vacuous pass. Local-true.
     - cwd = `runner.temp`: `--force` installs to `Path.home()` (`quickstart_runner.py:89`), so `runner.temp/CLAUDE.md` is missing — verify fails, implementer "fixes" by dropping verify or running it in the clone.
     - cwd = `$HOME` (scratch): `project_claude_md` is the file quickstart actually wrote. That is the only honest cwd. Plan does not say this.
  5. UV 0.8.17 → 0.11.19 matches `ci.yml:14`. `defaults.run.shell: bash` stays. Comment "Git-Bash-on-windows-runner, not stock user PATH" is honest and required. `uv tool install` still happens *before* HOME redirect (`quickstart-e2e.yml:55-66`); vibe-on-PATH is the runner tool layout, not a user PATH. Plan already declines that claim — keep it, and do not let `vibe verify grok-build`'s `vibe_on_path` be marketed as S45 PATH closure.

  M5 probe-inject dropping `2>/dev/null` and stopping JSON `platform` stuffing is correct. Do not pretend probe-inject is the settings.json command; M6 is.

- Suggestion (must-lock):
  1. Claude host smoke: extract `command` from scratch `settings.json`; `printf '%s\n' "$json" | bash -c "$cmd"` with cwd=`$RUNNER_TEMP` (not the clone). JSON **must** use `prompt` + `session_id` (what the script jq reads), or add `userPrompt` to the jq filter in the same task.
  2. Assert the output contains `[ACTIVE SKILL: builtin/commit-message]` **and** that the routed query is not the raw JSON (skill body / marker without `{` `userPrompt` leak is enough).
  3. Install `jq` on both E2E OS images **or** explicitly assert the no-jq fallback (raw JSON as query) so the job cannot launder a parse miss.
  4. `vibe verify claude-code` / `grok-build` cwd = `$HOME` (scratch), env HOME+USERPROFILE already set. Must exit 0 from that cwd.
  5. Grok JSON assert `--platform grok-build`, camelCase envelope, no `platform` field. Keep the PATH disclaimer.
- Status: open — blocks implementation

### F5 — Severity: MINOR — M7 implement-handlers is right; the golden test is a dummy layout, not the adapter

- File: plan M7; `src/vibesop/cli/commands/verify.py:89-100,224-231`; `src/vibesop/adapters/pi_coding_agent.py:49-146,154-172`; `src/vibesop/builder/renderer.py:66-109,137-156`; `src/vibesop/installer/installer.py:73-74`
- Fact vs suggestion: **Fact** that production Pi install goes through `ConfigRenderer.render` → `adapter.render_config` (full), which mkdir's `extensions/`, `skills/`, `prompts/` and writes the two `.ts` plus `AGENTS.md` at project root. `render_config_only` on the adapter itself skips `skills/` (`pi_coding_agent.py:168-171`) but ConfigRenderer does not call that method (`renderer.py:109,156`).
- Description: Implementing the six branches beats deleting ids (silent all-FAIL is the defect). Completeness (`every check_id → non-empty detail`) is the right meta-test. `exists()` / `is_dir()` on empty dirs will PASS: `render_config` mkdir's those dirs before writing. That is slightly weak and acceptable **if** the pass-layout test is adapter output.

  The plan's `test_pi_checks_pass_on_rendered_layout` hand-mkdirs `.pi/extensions`, dummy ts, `AGENTS.md`, `.pi/skills`, `.pi/prompts`. That blesses any handler that looks at those paths, including ones that would FAIL a real `vibe build --platform pi` if the adapter renamed `vibesop-route.ts` or wrote extensions under `~/.pi/agent/` (docstring at `pi_coding_agent.py:41-43` notes the global dir; deploy is project `.pi/`; verify `config_dir` is `Path(".pi")` cwd-relative — matching project deploy, not `~/.pi/agent`).

  Empty-dir `skills_dir` is **not** a mismatch with current `render_config`. It **would** be a mismatch if someone later called `PiCodingAgentAdapter.render_config_only` (no skills dir). Do not treat dummy mkdir as "rendered layout."

- Suggestion: keep implement-not-delete. Completeness test as specified. Replace the dummy golden test with `ConfigRenderer(project_root=tmp_path).render(QuickBuilder.default(platform="pi"), tmp_path / ".pi")` (or `PiCodingAgentAdapter(tmp_path).render_config`) then `_check_platform("pi")` from that cwd. Assert the two `.ts` files exist as the adapter named them. `is_dir()` empty is OK.
- Status: open as nit

---

## What is actually sound (do not re-open)

- **M1** — space only inside an already-quoted absolute script token; reject unquoted space and `` `$%^` ``. Unwrap already grouped `"C:/Users/First Last/..."`. Interpreter path is not on `_PATH_ALLOWED` (`hook_commands.py:34`); Program Files already works. Red tests as specified are the right corpus.
- **M2a** — `confidence` on `ExecutionStep` with PlanBuilder writing the value it already computes (`plan_builder.py:340`). Fail-closed default 0.0.
- **M2b polarity** — omit, not `success=True`, not a third class this patch.
- **M4 product call** — keep four demos always-on; SKILLS_GUIDE P1 for aha demos; any-layer pack-owner pin. (The contingency is the defect, not Option 2.)
- **M5 CLI** — `None` default; explicit flag > JSON platform > grok-build; three red tests; fix `test_hook_mode_camelcase_grok_payload` to `userPrompt` (`test_route_commands.py:404-411` still uses `prompt`).
- **M7 intent** — implement the six pi branches; completeness over delete.
- Out of scope list (n1–n11, C1/C2, n10 PATH prefix as CHANGELOG known issue) is still the right boundary.

---

## Must-lock punch-list (REJECT → APPROVE-WITH-NITS)

Fold these into the plan. Do not TDD around them.

1. **M3 identity** = tomllib `[project].name` canonicalize == `"vibesop"` AND `core/skills/` is a dir. Exist-gate every rung. Tests isolate wheel vs `__file__` checkout with distinctive content. Callers include `to_hook_response` hint and injector builtin `candidate_dirs` slot.
2. **M4** — delete "smallest levenshtein change." Pre-approved fallback if the pin is red: exclude the four demo ids from levenshtein last-resort only. Otherwise stop.
3. **M6** — `prompt` envelope into `bash -c "$cmd"`; cwd for verify = scratch `$HOME`; jq installed or fallback pinned; assert skill marker is not a raw-JSON false hit. PATH disclaimer stays.

Nits that may fold during TDD (do not need a v2 round-trip if the three locks land): M2 unattended anti-signal sentence; M7 adapter-rendered golden test; `bundled_core_file` identity or explicit decline; installer `_get_project_root` identity (same helper).

---

## Watchlist (non-blocking if must-locks land)

- Two SKILL.md producers (adapter Jinja stub vs injector bundled file): `find_skill_content` through `resolve_*` closes the wheel-stub half; still watch stub-vs-copy if `render_skill_md` is used for `builtin/*` when resolve misses.
- n10 Grok JSON still bare `vibe` on PATH after adding `--platform grok-build`. Command shape change does not close S45 PATH. CHANGELOG known issue as planned.
- C1/C2 leftovers unchanged.
- Hook script identity grep remains looser than Python tomllib until a follow-up. Document; do not silently copy it.
- `ambiguous_only` vs PHILOSOPHY: default is coherent; M2 polarity is the defect, and omit is the honest patch.

Architectural Status: **WATCH**. Verdict: **REJECT**. 0 BLOCKER / 3 MAJOR (F1 M3, F3 M4, F4 M5/M6) / 5 MINOR.
)
