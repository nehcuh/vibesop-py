# Fix-plan review A — correctness

- Spec: `docs/decisions/_review-s51-gate45-46-merged.md`
- Plan: `docs/decisions/_fix-s51-m1-m7.md` (v1)
- HEAD: `f6a90fd` [executed]
- Verdict: **REJECT**
- BLOCKERS: B1–B7 (must revise the plan before implement)
- NITS: N1–N10 (optional; do not by themselves flip REJECT)

Independent evidence only. No production source was modified.

---

## BLOCKERS

### B1 — M3 leaves cwd `core/skills` first-wins in two live readers; plan does not pin SkillLoader order

- Plan: `_fix-s51-m1-m7.md:118-124` (caller list) and `:120` (“Insert `resolve_builtin_skills_dir(self.project_root)` once”).
- Source today:
  - `src/vibesop/core/skills/loader.py:103-114` always includes `self.project_root / "core" / "skills"` **before** `pkg_builtins`.
  - `loader.py:336-338` is explicit first-wins: “Preserve already-loaded skills so earlier search paths take precedence”.
  - `src/vibesop/agent/runtime/skill_injector.py:240-241` `candidate_dirs[0]` is still `self.project_root / "core" / "skills"` (plan only rewrites the namespaced `strip_bases` list at `:269-295`).
  - `src/vibesop/agent/runtime/agent_runtime.py:199-228` still first-tries `user_root / "core" / "skills" / bare_name / "SKILL.md"`, then wheel, then `__file__` repo, then sys.path. Not in the plan’s file list (`:24-36`).
- Fact vs suggestion: merged M3 (`_review-s51-gate45-46-merged.md:50-54`) is “one `resolve_builtin_skills_dir`” so **any** `cwd/core/skills` must not shadow the wheel. The plan routes five named callers and **drops sys.path**, but:
  1. Does not say *where* SkillLoader inserts the resolved dir. `insert(0)` would make builtins shadow `project_root/skills` and `.vibe/skills` (also first-wins). Leaving the old `core/skills` entry in place keeps the cmspark hole.
  2. Does not change `candidate_dirs` or `agent_runtime` hint resolution. After green injector `strip_bases`, a namespaced `builtin/code-review` can inject **wheel** text while the runtime “read this SKILL.md” hint still points at **foreign** `cwd/core/skills/code-review/SKILL.md` if that file exists.
- Revise: pin SkillLoader order as `[project/skills, .vibe/skills, resolve_builtin_skills_dir(project_root)]` — do not `insert(0)`, do not keep a raw `project_root/core/skills` beside it. Route `agent_runtime.py` builtin hints through the same helper. Either drop `candidate_dirs`’s `project_root/core/skills` or identity-gate it the same way.

### B2 — M3 green will fail existing injector tests the plan does not rewrite

- Plan: `_fix-s51-m1-m7.md:142-144` rewrites only `test_load_skill_builtin_dev_repo_preferred_over_bundle` and adds a foreign-sibling; `:144` renames the sys.path test.
- Source today [inspected]:
  - `tests/agent/runtime/test_skill_injector.py:306-322` `test_load_skill_strips_builtin_namespace` writes `tmp_path/core/skills/deep-diagnosis-optimization/SKILL.md` **without** `pyproject.toml name = "vibesop"` and asserts that foreign body is returned for `builtin/deep-diagnosis-optimization`.
  - After plan green (`strip_bases = [resolve_builtin_skills_dir(self.project_root)]` + identity required), that tmp_path is **not** an identified checkout → resolve returns the wheel (or `__file__` checkout), not `# Deep diagnosis builtin content`. Test goes red for a reason the plan does not name.
- Fact vs suggestion: the plan treats identity as a two-test delta. It is not. Any injector/loader test that plants `project_root/core/skills` on a scratch dir without the identity marker is now testing the **forbidden** shadow. List and rewrite those tests in the plan (at least `:306-322`; keep `:210-219` `test_load_skill_from_core_skills` only if `candidate_dirs` is still allowed to serve bare ids from foreign `core/skills` — that is the B1 hole).
- The red bundled test at plan `:129-134` is also a weak pin: `assert resolved == bundled_path(...) or not (tmp_path/"core"/"skills") == resolved` passes for **any** non-foreign path (including a leftover `__file__` repo checkout). That does not prove “foreign must not shadow the wheel”.

### B3 — M5/M6 Claude host-smoke uses the wrong envelope for the generated script; Windows Git-Bash quoting is unspecified

- Plan: `_fix-s51-m1-m7.md:190-195` (probe Claude via `$VIBE_BIN route --hook --platform claude-code` + `userPrompt`/`sessionId`); `:227-228` (e2e `bash -c` settings.json command with “a `userPrompt` stdin JSON (or whatever the script expects)”); `:195` (“Escape JSON via `python -c` json.dumps if `$QUERY` can contain quotes”).
- Source today [inspected]:
  - `scripts/demo/probe-inject.sh:22-24` still interpolates `$QUERY` into JSON and sends Claude-shaped `prompt`/`session_id` plus `platform`.
  - `src/vibesop/adapters/templates/shared/vibesop-route.sh.j2:15-18` jq extracts **only** `.prompt // .user_prompt // .query // .message // .text` — **not** `userPrompt`. `:30` then `QUERY="$INPUT"` (the whole JSON blob) when jq misses.
  - Same template `:123-134` does **not** call `vibe route --hook`. It calls `AgentRuntime.handle_query_for_hook(..., platform='{{ platform|pyquote }}')` with the platform **baked into the generated script**.
  - Merged M5 (`_review-s51-gate45-46-merged.md:71-72`) and Lane C: probe Claude via the **generated** `settings.json` command + `bash -c` from a non-repo cwd; Grok camelCase **without** `platform`.
- Fact vs suggestion:
  1. M5 as written still runs the **Grok CLI entry** twice (`vibe route --hook`), just with a flag on one lane. That does not close “Claude’s generated command is never `bash -c`’d”. M6 is supposed to, but its stdin is wrong: `userPrompt` will not be parsed by the shell hook; on Windows Git-Bash, `jq` is typically absent, so even a correct `prompt` field falls through to raw JSON as the query.
  2. “or whatever the script expects” is a we’ll-see. Pin Claude host smoke stdin as snake_case `{"prompt": "...", "session_id": "..."}` (what `vibesop-route.sh.j2` actually reads). Pin Grok probe stdin as camelCase `userPrompt`/`sessionId` **without** `platform`, piped to the deployed command (`vibe route --hook` or, after M5 JSON change, `vibe route --hook --platform grok-build`).
  3. Do **not** interpolate `$QUERY` into a `python -c "...'$QUERY'..."` string on Windows Git-Bash. Pass the query as `sys.argv` (or a here-doc file). The default probe query has no quotes so today’s script happens to work; the plan’s `python -c` sketch is how this goes red on the first apostrophe.

### B4 — M6 `vibe verify … must exit 0` is unpinned against `project_claude_md` + cwd

- Plan: `_fix-s51-m1-m7.md:226` (“`vibe verify claude-code -v` and `vibe verify grok-build -v` under scratch HOME (must exit 0)”).
- Source today [inspected]: `src/vibesop/cli/commands/verify.py:244-248` `project_claude_md` is `Path.cwd() / "CLAUDE.md"`, not HOME. Claude adapter writes `CLAUDE.md` into `~/.claude` (`src/vibesop/installer/installer.py:148,255`), not into cwd. Quickstart e2e already runs `--force` with `working-directory: ${{ runner.temp }}` (`.github/workflows/quickstart-e2e.yml:62-81`).
- Fact vs suggestion: if the new verify step inherits `working-directory: runner.temp`, `project_claude_md` is missing → verify exits 1 → “must exit 0” is false. If it runs from `GITHUB_WORKSPACE`, `project_claude_md` passes via **this clone’s** `CLAUDE.md` — a false-pass that is not the scratch user project. Pin cwd + HOME for verify (and whether `project_claude_md` is in scope for this smoke), or write a project `CLAUDE.md` into the scratch tree first. Do not claim exit 0 until that is named.

### B5 — M7 layout test as specified does not exercise `Path(".pi")`

- Plan: `_fix-s51-m1-m7.md:272` `test_pi_checks_pass_on_rendered_layout(tmp_path)` — “mkdir `.pi/extensions`, write dummy ts files, `AGENTS.md`, `.pi/skills`, `.pi/prompts`” with **no** `monkeypatch.chdir(tmp_path)`.
- Source today [inspected]: `src/vibesop/cli/commands/verify.py:91` `"config_dir": Path(".pi")` is a **cwd-relative** path stored at import. `_check_platform:227` uses it as-is. `exists()` is resolved against **process cwd**, not `tmp_path`.
- Fact vs suggestion: without `chdir(tmp_path)`, the test either inspects the real repo `.pi/` (false-pass if a local `vibe build --platform pi` exists) or reports Missing against the pytest cwd. The completeness test at plan `:260-261` *does* chdir — the layout test must too. Also pin `AGENTS.md` at `Path.cwd() / "AGENTS.md"` (`plan:241-242` is correct vs `verify.py:241-245` pattern) and dummy files at `Path(".pi") / "extensions" / "vibesop-route.ts"` etc., matching the adapter (`src/vibesop/adapters/pi_coding_agent.py:44,85-93`).

### B6 — M2c CHANGELOG instruction searches a phrase that does not exist

- Plan: `_fix-s51-m1-m7.md:16,100` replace Unreleased “instinct loop does not starve” / “instinct loop un-starved”.
- Source today [executed]: `CHANGELOG.md:37-41` Unreleased Fixed is Chinese: “现在确认跳过点补记 application-only 遥测（success=False）”. Grep of `CHANGELOG.md` has **no** “instinct loop”, “un-starved”, or “does not starve”.
- Fact vs suggestion: merged M2 (`_review-s51-gate45-46-merged.md:48`) requires the changelog to stop claiming the instinct loop is un-starved until promotion polarity is honest. The live claim to retract is `:37-41`, not an English slogan. If implementers grep the plan’s string they will no-op and ship the anti-signal sentence. Name `CHANGELOG.md:37-41` and replace it with the plan’s honest three-part statement (auto-proceed writes nothing; only explicit confirm writes `success=True`; aha/`--hook` are out of this loop).

### B7 — M4 “same task” matcher fix is only specified for one of the two executed steals

- Plan: `_fix-s51-m1-m7.md:150-170` strip `code-review` tag `"review my changes"` and `test-generation` trigger `"write tests"`; pin `PACK_OWNED_QUERIES` at **any** layer; “If after tag/trigger strip `write tests` still hits `builtin/commit-message` via levenshtein, **do not weaken the test**. Next-step … levenshtein must not select `builtin/commit-message`”.
- Source today [inspected]:
  - `core/skills/code-review/SKILL.md:5-6` still tags `review my changes`.
  - `core/skills/test-generation/SKILL.md:10` still triggers `"write tests"`.
  - `tests/core/routing/test_demo_skills.py:54-56,192-204` only archives `write tests`, and only forbids `layer == "keyword"`.
  - Merged M4 (`_review-s51-gate45-46-merged.md:61-67`) [executed]: **both** `write tests` → `builtin/commit-message` levenshtein 0.5 **and** `review my changes` → `builtin/code-review` levenshtein 1.0 with a pack fixture present.
- Fact vs suggestion: the any-layer pin is the right close (not weakened). The “next-step” only names commit-message. If `review my changes` still lands on `builtin/code-review` after the tag strip (remaining tags include `review changes`, `look over diff`; trigger `look over my changes`), the new pin fails with **no planned matcher change**. Extend the same-task escape hatch to **every** `PACK_OWNED_QUERIES` row, and lock one matcher strategy (exclude the four demo ids from levenshtein **or** raise last-resort threshold for `builtin/*` demos — pick one in the plan, do not “smallest change we’ll discover”). Do not touch `VERIFIED_DEMO_QUERIES` expected ids.

---

## NITS

### N1 — Several “red” tests are already green on HEAD

- Plan M1 `:55-62` `test_parse_rejects_unquoted_space_and_backtick`: unquoted space already yields `len(tokens) != 2` → `None` (`hook_commands.py:77-78`); backtick already fails `_PATH_ALLOWED` (`:86-87`). Only `:44-53` (`First Last` + `vibesop-mirror-prompt.sh` rewrite) is red. [inspected]
- Plan M2 `:89` case (b) “one step 0.2 → prompt still fires”: on HEAD `ExecutionStep` has **no** `confidence` field (`models.py:317-398`); Pydantic v2 extra defaults to ignore, so `ExecutionStep(..., confidence=c)` **succeeds and drops the kwarg**; `getattr(step, "confidence", 0)` is 0 (`confirmation.py:95-99`); orchestrated TTY always prompts. Case (b) already passes. Case (a) is the actual red.
- Plan M5 `:205-214` omitted-flag and camelCase-default tests already match today’s `hook_platform == "grok-build"` JSON override (`cli/main.py:656-664`). Only `:200-203` (explicit `--platform grok-build` must beat JSON `claude-code`) is red. Keep the two green tests as locks, but do not call them red.

### N2 — M2 `from_dict` is in the plan; the existing round-trip test will not catch an omission

- Plan `:96-97` correctly includes `to_dict`/`from_dict` (`data.get("confidence", 0.0)`). `ExecutionPlan.from_dict` already delegates (`models.py:555`).
- Fact: `tests/core/test_execution_plan_from_dict.py:38-72` `_build_full_step` does not set `confidence`. If green adds the Field with default `0.0` but forgets `from_dict`, round-trip of a 0.0 default still passes. Extend `_build_full_step` with a non-zero `confidence` (and the PlanBuilder test in existing `tests/core/orchestration/test_plan_builder.py:101-123`). Hidden-breakage item from the brief is **addressed in the plan text**, not locked by tests as written.

### N3 — PlanBuilder only writes confidence on the primary sub-task loop

- Plan `:98` `PlanBuilder ExecutionStep(..., confidence=confidence)` — the local variable exists at `plan_builder.py:302,340,356,384`.
- Other constructors at `plan_builder.py:623,745,775,848` and `workflow_engine.py:607` omit it → default `0.0` after the Field is added. `_needs_confirmation` uses `all(...)` (`confirmation.py:95-99`), so FAN_OUT / ADVERSARIAL / TOURNAMENT / squad plans would still always prompt. Spec did not require those patterns. Sequential 3-skill plans (the M2 recording tests) are enough **if** the loop site is the one wired. Pin that the unit test uses `build_plan` sequential steps, not `_apply_fan_out`.

### N4 — M5 `--platform` default `None` is the right sentinel; do not substitute `""`

- Plan `:18,178-185` and source `cli/main.py:494-498` (today default `"grok-build"`, then `:660` treats that default as unset). [inspected]
- Typer `str | None = typer.Option(None, "--platform")` is already the local pattern (`deviation_cmd.py:136` etc.). Omitted flag → `None` (falsy) → JSON then `grok-build`; explicit `--platform grok-build` is a truthy string and **must not** fall through. Do not use `default=""` (Click can make omitted and empty indistinguishable in help/parsing edge cases). The three CliRunner tests as written are the right lock for this.

### N5 — M1 green “keep original tokens” is necessary and correct; single quotes are unspecified

- Plan `:12,65`; source `hook_commands.py:34,74-87`. [inspected] Unwrap already grouped the spaced path; reject is the allowlist. Interpreter is not allowlisted — `"C:/Program Files/Git/bin/bash.exe"` already works (`test_claude_code.py:61-68`).
- `unwrap_token` only strips **double** quotes (`hook_commands.py:37-41`). A single-quoted spaced script stays quoted, `'` ∉ `_PATH_ALLOWED` → `None`. Spec said “already-absolute quoted token”. Pin double-quote only (matches rewrite output `f'"{norm}"'` on win32, `claude_code.py:78`) or also accept single quotes. `tests/cli/test_verify_hook_commands.py:75-79` already covers single-quoted paths for **verify**, not rewrite.

### N6 — Identity substring `name = "vibesop"` is looser than the hook’s regex

- Plan `:116`. Live hook `vibesop-route.sh.j2:43` uses `grep -E 'name[[:space:]]*=[[:space:]]*"vibesop"'`. Reuse that (or `tomllib` `[project].name == "vibesop"`) so a comment / dependency line cannot identify a foreign tree. `pyproject.toml:2` is `name = "vibesop"` today.

### N7 — M5 Grok JSON `--platform grok-build` is extra hardening, not required for the default path

- Plan `:188`. After default `None`, omitted flag + no JSON platform already `or "grok-build"` (`plan:181-185`). Deploying the explicit flag is what Lane C F6 asked (`_review-s51-lane-invariants.md:83-84`) so a future Grok envelope `platform` field cannot hijack the host. Keep it; add a unit assertion on `_render_hook_json()` (there is **no** current test of that command string — grep of `tests/` only hits `test_route_commands.py:382`). n10 PATH prefix stays out of scope (`plan:22,289`) — do not let the new substring assert (`plan:230`) replace a PATH-prefix claim.

### N8 — M2 skip-path comment drift

- Plan `:99` omits `_record_plan_sequence` on auto-proceed. `_record_plan_sequence` docstring (`cli/main.py:329-332`) and `_is_unattended_run` (`:354-357`) still describe auto-proceed as application-only telemetry and point at a **non-existent** `_confirm_orchestrated_result`. Update those comments in the same patch so the next reviewer does not think omit-vs-False was accidental.

### N9 — SKILLS_GUIDE already calls two demos P1; the P0 blurb is the namespace, not the four files

- Plan `:168`. `docs/SKILLS_GUIDE.md:72-80` says Builtin is “必须启用 / P0” then already lists `systematic-debugging` / `commit-message` as “P1 建议”. Edit the **namespace** blurb (slash/session-end stay P0; four aha demos are P1 keyless). Do not “fix” the examples by deleting them.

### N10 — Verification slice is missing the tests this plan actually needs to stay green

- Plan `:276-282` omits `tests/core/test_execution_plan_from_dict.py`, `tests/core/orchestration/test_plan_builder.py`, `tests/agent/runtime/test_skill_injector.py`’s remaining builtin tests, and any grok `_render_hook_json` test. `tests/cli/test_verify_hook_commands.py` is listed but unchanged by M1–M7. After B2’s test rewrites, the verification command must include those files or the “broader affected slice if green” will be the first time they fail.

---

## Red-test / MAJOR close table (HEAD `f6a90fd`)

| ID | Will the stated red test fail on HEAD for the stated reason? | Will plan green close the merged MAJOR? |
|----|--------------------------------------------------------------|----------------------------------------|
| M1 | **Yes** for `test_rewrites_git_bash_wrapper_spaced_home` (`_PATH_ALLOWED` has no space, `hook_commands.py:34,86-87`; rewrite tests only use `HuChen`/`h`, `test_claude_code.py:70-94`). The reject-unquoted/backtick test is already green. | **Yes**, if original tokens gate the space union. Spec’s `First Last` + `vibesop-mirror-prompt.sh` path is exactly the planned assertion. |
| M2 | **Yes** for case (a): real `ExecutionStep` drops `confidence`, skip never fires, sequences currently **are** recorded (`cli/main.py:1439-1440`, test `:113-152` uses SimpleNamespace). | **Partial → No until B6.** Adding the Field + PlanBuilder write + omit `_record_plan_sequence` closes polarity. CHANGELOG as specified will not retract the live anti-signal sentence. Synthetic-step `confidence=0.0` (N3) does not reopen sequential 3-skill skip. |
| M3 | **Weak.** `test_foreign_core_skills_does_not_shadow_wheel` as written can pass without choosing the wheel (B2). Injector foreign-content test is the real red, and it is not in the plan. | **No** until B1–B2. Five named callers are the right set plus `agent_runtime.py`. SkillLoader first-wins is live and unpinned. |
| M4 | **Yes** once the any-layer pin is added (`test_demo_skills.py:202-204` currently allows levenshtein steal). Frontmatter strip alone does not make today’s keyword-only test fail. | **Not guaranteed.** Option 2 + any-layer pin is the spec pick (not `--demos`, not weakened). Matcher surgery is only specified for `write tests` (B7). |
| M5 | **Yes** for `test_explicit_platform_flag_beats_json_platform` (`cli/main.py:660` treats default `grok-build` as unset). The other two tests are already green (N1). | **Partial.** Flag-wins + default `None` closes Lane B F6 / C F1. Probe still does not `bash -c` the generated Claude command (B3). Grok JSON `--platform grok-build` is the right deploy pin (N7). |
| M6 | N/A (workflow, not pytest). `UV_VERSION: "0.8.17"` vs CI `0.11.19` (`quickstart-e2e.yml:21`, `ci.yml:14`) is a real delta. | **No as specified.** UV align is right. `vibe verify` exit 0 is unpinned (B4). Claude `bash -c` envelope is wrong (B3). Plan correctly does **not** claim stock user PATH (locked `:19`). |
| M7 | **Yes.** Pi declares 7 ids (`verify.py:89-101`); `_check_platform` has no `agents_md` / `extensions_dir` / `skills_dir` / `route_extension` / `track_extension` / `prompts_dir` branches; leftover `detail=""` (`:231`). Completeness test on empty detail fails today. | **Yes** for “silent all-FAIL → missing-file FAIL”, **if** B5 chdir is added. Implementing the six handlers (not deleting ids) matches the spec. `config_dir` relative `.pi` is pre-existing and correct **when cwd is the project**. |

---

## Weakened / unfixed MAJORs

- **M1** — not weakened.
- **M2** — omit-not-False is the spec’s allowed polarity; **changelog retract is unexecutable as written (B6)**. aha/`--hook` out of plan-sequence learning is documented-only (correct; no code path in scope).
- **M3** — **not closed** (B1–B2). “Drop sys.path” is in spec; leaving `candidate_dirs` + `agent_runtime` is a sixth/seventh reader.
- **M4** — option 2 locked (good; `--demos` would kill gate46). Any-layer pin is not weakened. Matcher close is a we’ll-see for the second executed steal (B7).
- **M5** — flag-wins closed; “Grok CLI twice / Claude command never bash -c’d” moved to M6 and then underspecified (B3).
- **M6** — UV pin is real; host-smoke and verify-exit-0 are not executable as written (B3–B4). Windows runner stays `shell: bash` with an honest comment (matches locked `:19`).
- **M7** — handlers-not-delete is the spec pick. Layout test as specified does not test pi (B5).

n1–n11 and C1/C2 remain deferred as declared (`plan:6,22,286-291`). That is in-scope honesty, not a MAJOR skip.

---

Revise v1 for B1–B7, then re-submit. Do not start TDD execute on this text.
