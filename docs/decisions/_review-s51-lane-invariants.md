# S51 Lane C — Platform / Windows / Routing Invariants

- Reviewer: independent general-purpose agent
- Window: e286e67..f6a90fd
- Files actually read: `docs/decisions/_review-s51-gate45-46-brief.md`, `docs/dev/platform-invariants.md`, `CHANGELOG.md`, `core/registry.yaml`, `core/skills/{code-review,commit-message,systematic-debugging,test-generation}/SKILL.md`, `.github/workflows/{quickstart-e2e.yml,ci.yml}`, `scripts/demo/{dual-platform-demo.sh,probe-inject.sh}`, `pyproject.toml`, `src/vibesop/cli/main.py`, `src/vibesop/cli/commands/verify.py`, `src/vibesop/adapters/{grok_build.py,claude_code.py,_content.py}`, `src/vibesop/adapters/templates/shared/vibesop-route.sh.j2`, `src/vibesop/utils/{bundled.py,hook_commands.py}`, `src/vibesop/agent/runtime/{skill_injector.py,agent_runtime.py}`, `src/vibesop/core/routing/{candidate_manager.py,unified.py,project_config.py,scenario_layer.py}`, `src/vibesop/core/matching/strategies.py`, `src/vibesop/core/config/manager.py`, `src/vibesop/core/skills/external_loader.py`, `src/vibesop/constants.py`, `src/vibesop/installer/{installer.py,quickstart_runner.py}`, `src/vibesop/builder/renderer.py`, `tests/cli/{test_platform_registry_sync.py,test_verify_hook_commands.py,test_route_commands.py}`, `tests/core/routing/test_demo_skills.py`, `tests/installer/{test_quickstart.py,test_installer.py}`, `tests/agent/runtime/{test_demo_injection.py,test_skill_injector.py}`, `tests/utils/test_bundled.py`, `docs/SKILLS_GUIDE.md`, `docs/INDEX.md`, `memory/project-knowledge.md`
- Verdict: NEEDS_FIX
- Counts: 0 BLOCKER / 4 MAJOR / 5 MINOR

## Invariant scorecard

| Invariant | Status (HOLD|BROKEN|UNVERIFIED) | Evidence |
|-----------|--------------------------------|----------|
| 1. Single platform set (set-equality, never `len >= 2`) | BROKEN | [executed] `SUPPORTED_PLATFORMS`={claude-code,kimi-cli,opencode,cursor,pi,grok-build}; installer/quickstart/renderer omit `cursor`; verify includes it. Tests still use `<=` / `>=` subsets (`tests/cli/test_platform_registry_sync.py`) and leftover `len(...) >= 2` in files this window edited. |
| 2. Installed means VibeSOP marker, not host config.toml/settings.json | HOLD | [inspected] `VibeSOPInstaller._VIBESOP_MARKERS` + `_is_configured` (`installer.py:239-263`). Unknown/`platform is None` still falls through to host-native filenames; `install()`/`verify()` always pass platform. |
| 3. Hooks that spawn `vibe` must find it (JSON/Node have no bash PATH prefix) | BROKEN | [executed] Grok JSON still `"command": "vibe route --hook"` with no PATH patch (`grok_build.py:213`). Windows e2e never spawns that command as Grok would; `vibe_on_path` is `shutil.which` at CLI time (`verify.py:421-424`). |
| 4. `vibe verify` check_ids must have handlers | BROKEN | [executed] pi: 6/7 check_ids have no `_check_platform` branch (`agents_md`, `extensions_dir`, `skills_dir`, `route_extension`, `track_extension`, `prompts_dir`) → silent `pass=False`. No test asserts handler completeness. Window touched `verify.py` and did not add one. |
| 5. Claude Code Windows `command` is quoted POSIX path, not bash wrapper | HOLD | [inspected] `bash_hook_command` (`claude_code.py:24-41`); rewrite gated by `parse_hook_script_command` + `_legacy_rewrite_signal`. `tests/cli/test_verify_hook_commands.py` covers PowerShell false-positive, win32 1-token, drive-letter on non-win32. Host smoke (`bash -c <settings.json command>` from a non-repo cwd) is still not in e2e. |
| 6. Route-hook Python is uv-tool interpreter, never Store `python3` | HOLD (template) / UNVERIFIED (host) | [inspected] `vibesop-route.sh.j2:54-116` searches `uv tool dir` / `%APPDATA%\uv\tools\...\Scripts/python.exe`, skips `WindowsApps`. Dual-platform probe never executes this script. |
| 7. EXTERNAL_PATHS ClassVar frozen at import | HOLD in R7 tests / BROKEN in new injection test | [inspected] `test_demo_skills.py` patches the ClassVar + non-empty pool guard. `tests/agent/runtime/test_demo_injection.py` only `chdir`s — does not patch `EXTERNAL_PATHS`. |
| 8. Builtin count 50+ vs 14 vs 18 | HOLD | [executed] `GrokBuildAdapter._count_builtin_skills()` = 18; `core/skills` has 18 dirs; fresh wheel contains 18 `builtin_skills/*`. `docs/INDEX.md` / `docs/SKILLS_GUIDE.md` say 18. Count includes 6 `slash-*` dirs (not a 14 leftover). |
| 9. Demo tags do not steal keyword routing (`write tests`, `review my changes`) | BROKEN | [executed] see F3. Claim 8 is false on the phrases the brief names. |
| 10. `vibe route --hook --platform` actually parameterized | HOLD with nits | [executed] JSON `platform` and `--platform` both reach `handle_query_for_hook`. Help says "flag wins"; code lets JSON win whenever the flag is still the default `grok-build`. No test invokes the CLI flag. Probe never passes `--platform`. |
| 11. Wheel-install builtins not empty-route | HOLD | [executed] `uv build` 8.1.1 wheel contains 18 skill dirs + `vibesop/builtin_data/core/registry.yaml` + policies. `bundled_core_file` wired in `ConfigManager.load_registry` and `load_merged_scenario_config`. Sdist still ships `core/skills` after MANIFEST.in deletion (git-tracked). |
| 12. Git-Bash scan scoped to vibesop commands (M2) | HOLD | [inspected] `classify_vibesop_hook_command` + `_vibesop_command_unsafe_reason`; tests pin user PowerShell + non-win32 drive tokens. Allowlist is `.sh` basenames only (Grok JSON is a different check). |
| 13. CI Lint isomorphism (`ruff check .` + `ruff format --check .`) | HOLD | [inspected] `.github/workflows/ci.yml:37-41`. Quickstart E2E does **not** run those commands (different workflow). |
| 14. Quickstart E2E Windows lane is a real dual-platform host smoke | BROKEN | [inspected] `windows-latest` exists but `defaults.run.shell: bash`; UV 0.8.17 vs CI 0.11.19; hook assert is file grep; probe is `vibe route --hook` twice with Claude-shaped JSON. See F1/F2. |

Did not re-open documented 8.1.2 C1/C2 (whitelist canary missing; preserve-matcher substring). This window did not make those worse.

## Findings

### F1 — Severity: MAJOR
- File: `scripts/demo/probe-inject.sh:20-24`, `src/vibesop/cli/main.py:494-664`, `.github/workflows/quickstart-e2e.yml:134-141`
- Fact vs suggestion: fact
- Description: The "parameterized `--hook --platform`" dual-platform probe is still the Grok CLI entrypoint twice. It does not exercise Claude Code's deployed hook (`vibesop-route.sh` → uv-tool Python, Git-Bash `-c`, Store-python skip). Both lanes send a Claude-shaped stdin envelope (`prompt`/`session_id`) plus a synthetic `platform` field the real Grok host does not send. The deployed Grok hook is still `vibe route --hook` with no `--platform`. No test in `tests/cli/test_route_commands.py` (or elsewhere) invokes `route --hook --platform`.
- Evidence: [inspected] `probe()` always runs `$VIBE_BIN route --hook` (no `--platform` flag) and `2>/dev/null`. [executed] CLI: JSON `platform=claude-code` with default flag → `claude-code`; `--platform claude-code` beats JSON grok; `--platform grok-build` (same string as the default) **loses** to JSON `platform=claude-code` — help text "flag wins" is false. `userPrompt`-only payloads do extract (good). E2E last step is this script from `runner.temp`.
- Suggestion: Probe Claude via the generated `settings.json` command + `bash -c` from a non-repo cwd (invariant 5/6 host smoke). Probe Grok with a camelCase envelope **without** a `platform` field, matching the deployed `vibe route --hook`. Add a CLI test that `--platform` is distinguishable from the default (do not treat `== "grok-build"` as "flag omitted"). Pin `userPrompt` in `TestRouteHookMode` (today's "camelcase grok" test still uses `prompt` + `sessionId`).
- Status: open

### F2 — Severity: MAJOR
- File: `.github/workflows/quickstart-e2e.yml:21-39,113-141` vs `.github/workflows/ci.yml:14,37-41`
- Fact vs suggestion: fact
- Description: The Windows lane is Git-Bash-on-a-Windows-runner, not the failure class that shipped 8.1.0 (stock user PATH, Grok JSON spawn, Claude Git-Bash `-c`, Store `python3`). It does not use CI Lint commands. It does not run `vibe verify`. Hook "registration" is file existence + grep for the substring `vibe route --hook`. Grok lane assertions omit "Injection preview" / "# Commit Message" (asymmetric with Claude). `UV_VERSION` is `0.8.17` here vs `0.11.19` in CI — different uv-tool layout/PATH behavior is in scope for invariant 3/6.
- Evidence: [inspected] `matrix.os` includes `windows-latest` but `defaults.run.shell: bash`. Install step is `uv tool install ./dist/vibesop-*.whl` **before** HOME/USERPROFILE redirect (binary lives on the runner user PATH, not a stock Windows user PATH). Assert hook step never opens `settings.json` or feeds stdin to the JSON command. `dual-platform-demo.sh` is tmux + `claude`/`grok` binaries — not CI, not Windows.
- Suggestion: Align uv with CI. After quickstart, run `vibe verify claude-code -v` and `vibe verify grok-build -v` under the scratch HOME. Execute the Claude `settings.json` command with `bash -c` from `runner.temp`. Pipe a Grok-shaped camelCase envelope into `vibe route --hook` with no `platform` field. Keep file-existence as a necessary but not sufficient check.
- Status: open

### F3 — Severity: MAJOR
- File: `core/skills/code-review/SKILL.md:4-6`, `core/skills/test-generation/SKILL.md:8-10`, `tests/core/routing/test_demo_skills.py:46-56,192-204`
- Fact vs suggestion: fact
- Description: Product claim 8 ("demo `triggers` stay in explicit layer; `tags` do not steal `write tests` / `review my changes`") is false. Tags **are** the keyword-layer `keywords` field (`candidate_manager.py:145-161`). `code-review` still tags `"review my changes"`. `"write tests"` was moved to `test-generation` **triggers**, but the new `commit-message` demo skill now wins that query via levenshtein. The "mis-hit archive" test only forbids `builtin/*` **and** `layer == "keyword"`, so a levenshtein steal of a pack-owned phrase stays green.
- Evidence: [executed] isolated HOME, `HF_HUB_OFFLINE=1`, `LightweightRouter`:
  - `write tests` → `builtin/commit-message` layer=`levenshtein` conf=0.5 (with **and** without a `superpowers/test-driven-development` fixture that tags `"write tests"`)
  - `review my changes` → `builtin/code-review` layer=`levenshtein` conf=1.0 (with a `superpowers/review` fixture that tags the same phrase)
  - verified demo query `look over my changes before I push` → `builtin/code-review` keyword ~0.62 (this one matches the GIF floor)
  Under hook auto-select (no confirmation), 0.5 levenshtein still injects the wrong skill. This is a this-window regression class: the four demo skills did not exist at `e286e67`.
- Suggestion: Remove `"review my changes"` from `code-review` tags (keep it out of the keyword layer; put a longer phrase on `triggers` if needed). Drop `"write tests"` from builtin triggers **and** add a pack-owner pin: `write tests` must not land on `builtin/*` at any layer when the TDD pack is in the pool. Tighten `test_pack_owned_queries_not_stolen_by_builtin` to `assert got == owner` (or at least `not got.startswith("builtin/")`), not the keyword-only carve-out.
- Status: open

### F4 — Severity: MAJOR
- File: `src/vibesop/cli/commands/verify.py:89-100` vs `233-424`
- Fact vs suggestion: fact
- Description: Invariant 4 is still broken on a `SUPPORTED_PLATFORMS` member. `PLATFORM_CONFIGS["pi"]` declares seven checks; `_check_platform` has no `elif` for six of them. Unhandled ids keep the initializer `pass=False` with empty `detail` — `vibe verify pi` is a silent all-FAIL even on a correct install. This window rewrote the Git-Bash scan in the same function and did not add a "every check_id has a branch" test (the exact miss that let `agents_md` / `extensions_dir` ship).
- Evidence: [executed] handler extraction vs `PLATFORM_CONFIGS`:
  - pi missing: `agents_md`, `extensions_dir`, `prompts_dir`, `route_extension`, `skills_dir`, `track_extension`
  - claude-code / kimi-cli / opencode / cursor / grok-build: complete
  `tests/cli/test_platform_registry_sync.py` never asserts handler coverage. Pre-existing vs this window: not introduced here; **not closed**; verify.py was in the highest-risk set.
- Suggestion: Either implement the six pi branches or delete the orphan check_ids. Add `assert set(PLATFORM_CONFIGS[p]["checks"]) <= handled_ids` for every platform. Do not treat `len(checks) > 0` as coverage.
- Status: open

### F5 — Severity: MINOR
- File: `src/vibesop/constants.py:31-38`, `src/vibesop/installer/installer.py:12-33`, `tests/installer/test_quickstart.py:26`, `tests/installer/test_installer.py:22`, `tests/cli/test_platform_registry_sync.py:20-39`
- Fact vs suggestion: fact
- Description: Platform identity is still copied into 5 registries that disagree, and the anti-`len >= 2` lesson is not fully applied. `cursor` is in `SUPPORTED_PLATFORMS` and `verify.PLATFORM_CONFIGS` but missing from installer / quickstart / renderer — so `vibe quickstart --platform cursor` is "Unknown platform" while `vibe verify cursor` is valid. The sync tests allow subset, which cannot catch installer dropping grok-build **if** another two names remain (they currently also pin grok-build by name — that part holds).
- Evidence: [executed] set dump listed in the scorecard. [inspected] this window **added** a `set(...) >= {5 names}` in `test_quickstart.py` but **left** `assert len(runner._supported_platforms) >= 2` on the previous line. `test_installer.py:22` is still cardinality-only plus three `any(name==...)` checks.
- Suggestion: One named exemption (cursor is verify-only / not installer-managed) encoded as set equality against `SUPPORTED_PLATFORMS - EXEMPT`. Delete every `len >= 2` on platform lists.
- Status: open

### F6 — Severity: MINOR
- File: `src/vibesop/adapters/grok_build.py:203-213`, `src/vibesop/cli/main.py:494-498,656-664`
- Fact vs suggestion: fact
- Description: Invariant 3 is unchanged for Grok: JSON hooks still call bare `vibe` with no PATH prefix (the bash template's `$HOME/.local/bin` prepend is not promoted). `--platform` help claims "flag wins"; implementation treats the default value as "not passed" so a surprising `platform` key in a host envelope would silently switch injection format. Production Grok envelopes [assumed] omit `platform`, so the default `grok-build` holds in the field — but that is luck, not a pin in the deployed command.
- Evidence: [executed] `_render_hook_json()` command string is exactly `vibe route --hook`. [executed] `--platform grok-build` + JSON `platform=claude-code` → `claude-code`.
- Suggestion: Deploy `vibe route --hook --platform grok-build` (real flag, not default-detection). Document that Grok users need `%USERPROFILE%\.local\bin` on the **user** PATH; keep `vibe verify grok-build` `vibe_on_path` as a necessary check. Do not claim Windows e2e closed this.
- Status: open

### F7 — Severity: MINOR
- File: `src/vibesop/agent/runtime/skill_injector.py:152-155` vs `181-204`
- Fact vs suggestion: fact
- Description: This window added `PlatformType.GROK_BUILD` and mapped **single-skill** injection to the Claude `additionalContext` envelope. `inject_execution_plan` was not updated: grok falls through to generic `InjectionMethod.TEXT`. Hook orchestration currently builds `additionalContext` inside `to_hook_response` (so the live `--hook` multi-intent path may still look Claude-shaped), but any caller of `inject_execution_plan(plan, GROK_BUILD)` gets a different contract than `inject_single_skill`. Dual-platform "same envelope" is not true for that API.
- Evidence: [inspected] `if platform == PlatformType.CLAUDE_CODE` only in `inject_execution_plan`; grok is the `else`.
- Suggestion: Treat grok like claude in `inject_execution_plan` (or share one helper). Add a parametrize over `{claude-code, grok-build}` on the plan payload shape.
- Status: open

### F8 — Severity: MINOR
- File: `tests/agent/runtime/test_demo_injection.py:26-28`
- Fact vs suggestion: fact
- Description: The real-pipeline hook test that underwrites the dual-platform probe does not patch `ExternalSkillLoader.EXTERNAL_PATHS`. That ClassVar is the documented 2026-08-27 pitfall: HOME/`Path.home` patches do not isolate pack discovery. CI runners with empty homes stay green; a pack-loaded Windows developer machine can change the pool under the same test.
- Evidence: [inspected] autouse fixture only `monkeypatch.chdir(tmp_path)`. Contrast `tests/core/routing/test_demo_skills.py:59-69` which patches the ClassVar and asserts `superpowers/` / `omx/` are actually in the pool.
- Suggestion: Reuse `_isolate_home` (or the same ClassVar patch) in `TestRealHookPipeline`.
- Status: open

### F9 — Severity: MINOR
- File: `scripts/demo/probe-inject.sh:1,20-24`; `src/vibesop/adapters/grok_build.py:139-149`; `src/vibesop/core/routing/candidate_manager.py:238-255`
- Fact vs suggestion: fact (first two) / suggestion (comment drift)
- Description: (a) Probe fail-open: `vibe route --hook` **always exits 0** (`main.py:677-678`); stderr is discarded (`2>/dev/null`), so a missing `vibe` vs an empty `{}` envelope is indistinguishable except for the later marker check — and that check cannot see why. (b) `dual-platform-demo.sh` is bash/tmux-only; not a Windows artifact. (c) Grok builtin count is computed, but the docstring says "same resolution ladder as the candidate manager (repo first, wheel second)" while `_build_search_paths` inserts wheel then repo via `insert(0)`, which **reverses** to repo-first when both exist. Not a 14 leftover; comment is wrong.
- Evidence: [inspected] probe + grok count loop vs candidate_manager insert loop. [executed] count=18 on this checkout.
- Suggestion: Drop `2>/dev/null`; print a short stderr tail on PROBE FAILED. Align count/search order comments with one ladder (and decide wheel-vs-checkout precedence under `uv tool` + cwd-in-clone — Lane B territory if both exist).
- Status: open

## What this window did close (do not credit as remaining work)

- Wheel builtins + registry/policies force-include: [executed] fresh `uv build` 8.1.1 wheel has 18 skills and `builtin_data/core/registry.yaml`. Stale `dist/vibesop-8.1.0-*.whl` in-tree still has **14 skills and no registry** — anyone installing that leftover wheel will empty-route; e2e rebuilds, humans may not.
- M2 verify scope: user PowerShell no longer fails the Claude Git-Bash scan [inspected tests].
- Claude rewrite conservatism via `hook_commands.parse_hook_script_command` [inspected].
- Grok `routing.md` count is dynamic 18, not a stale 50+/14 [executed].
- CI Lint job is `ruff check .` + `ruff format --check .` [inspected].
- Shell hook Store-python / `Scripts/python.exe` lookup remains in the template [inspected] — not shown to run on Windows e2e.

## Verdict

NEEDS_FIX — 0 BLOCKER, 4 MAJOR (F1–F4), 5 MINOR (F5–F9).

The window's platform story is "CI + Quickstart E2E green ⇒ dual-platform / Windows / keyword-steal / empty-route closed." Wheel packaging and M2 scan scope hold under execution. Dual-platform, Windows host-hook smoke, demo tag/trigger layering, and verify check_id completeness do not.
