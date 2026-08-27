# S51 Lane A — Correctness / Security

- Reviewer: independent general-purpose agent
- Window: e286e67..f6a90fd
- Files actually read: docs/decisions/_review-s51-gate45-46-brief.md; CHANGELOG.md; pyproject.toml; src/vibesop/security/scanner.py; src/vibesop/security/runtime_scan.py; src/vibesop/utils/hook_commands.py; src/vibesop/utils/bundled.py; src/vibesop/cli/commands/verify.py; src/vibesop/cli/confirmation.py; src/vibesop/cli/main.py; src/vibesop/cli/commands/sequence_cmd.py; src/vibesop/agent/runtime/skill_injector.py; src/vibesop/agent/runtime/plan_executor.py; src/vibesop/agent/runtime/agent_runtime.py; src/vibesop/adapters/claude_code.py; src/vibesop/adapters/grok_build.py; src/vibesop/adapters/_content.py; src/vibesop/core/config/manager.py; src/vibesop/core/routing/candidate_manager.py; src/vibesop/core/routing/project_config.py; src/vibesop/core/models.py; src/vibesop/core/orchestration/plan_builder.py; src/vibesop/core/skills/loader.py; src/vibesop/core/matching/strategies.py; src/vibesop/installer/quickstart_runner.py; src/vibesop/installer/init_support.py; scripts/demo/probe-inject.sh; scripts/demo/dual-platform-demo.sh; core/registry.yaml; core/skills/{code-review,commit-message,systematic-debugging,test-generation}/SKILL.md; tests/cli/test_verify_hook_commands.py; tests/cli/test_plan_sequence_recording.py; tests/cli/test_route_commands.py; tests/security/test_scanner.py; tests/utils/test_bundled.py; tests/adapters/test_claude_code.py; tests/agent/runtime/test_skill_injector.py; tests/agent/runtime/test_plan_executor.py; tests/agent/runtime/test_demo_injection.py; tests/core/routing/test_demo_skills.py; tests/core/test_config_manager.py; .github/workflows/quickstart-e2e.yml
- Verdict: NEEDS_FIX
- P0: 0  P1: 2  P2: 4

## Summary

The `\n{5,}` removal plus empty-vs-unsafe split does not deliver injection payload as a data notice: empty/whitespace still fails closed into `empty_content_notice`, and phrase rules still fire through newline padding (`tests/security/test_scanner.py`). Wheel force-include of `core/registry.yaml` + `core/skills` is the right packaging shape; hatchling never read the deleted `MANIFEST.in`. Two this-window contracts are false in production: `_PATH_ALLOWED` rejects spaces so the new strict rewrite cannot upgrade Git-`bash.exe` wrappers for spaced Windows homes, and `ExecutionStep` has no `confidence` field so the advertised `ambiguous_only` orchestration auto-proceed / learning-signal path is test-only.

## Findings

### F1 — Severity: MAJOR
- File: src/vibesop/utils/hook_commands.py:34
- Fact vs suggestion: fact
- Description: `parse_hook_script_command` cannot return a path containing a space, so the M1 legacy rewrite leaves Git-`bash.exe` (and `bash` prefix) wrappers untouched for the exact Windows username class this window tests elsewhere (`First Last`).
- Evidence: `_PATH_ALLOWED` is `ascii_letters + digits + "._/+-:"` — no space. After `unwrap_token`, a legal quoted path `C:/Users/First Last/.claude/hooks/vibesop-route.sh` fails the allowlist and returns `None` ("do not rewrite"). [executed] on win32:

  ```
  CMD '"C:/Program Files/Git/bin/bash.exe" "C:/Users/First Last/.claude/hooks/vibesop-route.sh"'
  TOK ['"C:/Program Files/Git/bin/bash.exe"', '"C:/Users/First Last/.claude/hooks/vibesop-route.sh"']
  PARSE None

  CMD '"C:/Program Files/Git/bin/bash.exe" "C:/Users/HuChen/.claude/hooks/vibesop-route.sh"'
  PARSE C:/Users/HuChen/.claude/hooks/vibesop-route.sh
  ```

  `shlex.split(..., posix=False)` + `unwrap_token` already grouped the spaced path; the reject is the allowlist, not quote retention. Route hooks are refreshed via `bash_hook_command` (src/vibesop/adapters/claude_code.py:553), so a rebuild still writes a canonical route entry. Preserved non-route entries (conversation-mirror `vibesop-mirror-prompt.sh`, the form the rewrite tests actually use) stay on the broken wrapper. `vibe verify` flags `bash.exe` / `bash ` (src/vibesop/cli/commands/verify.py:147-172) but `vibe build` does not repair them. Rewrite tests only use `C:/Users/h/` and `C:/Users/HuChen/` (tests/adapters/test_claude_code.py:70-94).
- Suggestion: After unwrap, allow space (and only space) inside an already-absolute quoted token; add a rewrite test for `"C:/Program Files/Git/bin/bash.exe" "C:/Users/First Last/.claude/hooks/vibesop-mirror-prompt.sh"` → `"C:/Users/First Last/.claude/hooks/vibesop-mirror-prompt.sh"` on win32. Keep rejecting backtick/`$`/`%`/`^`.
- Status: open

### F2 — Severity: MAJOR
- File: src/vibesop/cli/confirmation.py:94
- Fact vs suggestion: fact
- Description: The `ambiguous_only` orchestration auto-proceed / application-only learning path this window added cannot fire on real plans, because `ExecutionStep` has no `confidence` field; the new test only passes by stuffing confidence onto a `SimpleNamespace`.
- Evidence: `_needs_confirmation` uses `getattr(step, "confidence", 0) >= auto_select_threshold` (confirmation.py:95-98). `ExecutionStep` (src/vibesop/core/models.py:317-398) has no `confidence`. `PlanBuilder` computes a local `confidence` and writes it only into `reasoning_parts`, not onto the step (src/vibesop/core/orchestration/plan_builder.py:387, 402-418). For production steps `getattr(..., 0)` is always `0`, `all_confident` is always false, and orchestration still always prompts on TTY — the pre-change `always` behavior. CHANGELOG Unreleased claims the skip-point now records application-only telemetry so the instinct loop does not starve; that skip-point is `if not _is_unattended_run(...): _record_plan_sequence(..., success=False)` in src/vibesop/cli/main.py:1439-1440, reached only when `_needs_confirmation` is false. tests/cli/test_plan_sequence_recording.py:126-127 builds `SimpleNamespace(skill_id=s, confidence=0.9)` and asserts recording (lines 147-152). That object is not an `ExecutionStep`.
- Suggestion: Add `confidence: float = 0.0` to `ExecutionStep`, pass the builder's `confidence` into the constructor, and change the recording test to use a real `ExecutionPlan`/`ExecutionStep`. Until then, do not claim the learning-signal hole is closed.
- Status: open

### F3 — Severity: MINOR
- File: src/vibesop/agent/runtime/skill_injector.py:115
- Fact vs suggestion: fact
- Description: The empty-content gate is an unanchored substring match on `CONTENT_NOT_FOUND_MARKER`, so a tampered SKILL.md that embeds `*Skill content not found` skips the runtime security scan and ships a `[VibeSOP]` data notice instead of `[VibeSOP SECURITY]`.
- Evidence: `if not skill_content.strip() or CONTENT_NOT_FOUND_MARKER in skill_content:` runs before `_is_content_safe` (skill_injector.py:115-144). The original body is replaced, not injected — this is a banner/classification skip, not an additionalContext payload bypass. Phrase injection padded with newlines is still flagged (tests/security/test_scanner.py:391-403). `PlanExecutor.build_manifest` only checks `not skill_content.strip()` (plan_executor.py:130), so the two paths diverge on a marker-bearing unsafe file. tests/agent/runtime/test_skill_injector.py:81-104 never combines the marker with an injection phrase.
- Suggestion: Treat as empty only when the loaded text equals the producer placeholder (`f"# Skill: {skill_id}\n\n{CONTENT_NOT_FOUND_MARKER} at expected locations.*"`) or `not strip()`; never `in`. Add a test: marker + `Ignore all previous instructions` → SECURITY notice, phrase absent from payload.
- Status: open

### F4 — Severity: MINOR
- File: src/vibesop/utils/hook_commands.py:77
- Fact vs suggestion: fact
- Description: A 1-token Windows backslash vibesop command is not rewritten (token count ≠ 2) even though verify will fail it.
- Evidence: [executed] `C:\Users\h\.claude\hooks\vibesop-route.sh` → `PARSE None`, `CLASS True`. Conservative by the stated `<bash> <script>` contract. Route rebuild still replaces the route entry; leftover 1-token backslash forms only survive if they are preserved non-route commands. Verify's `unsafe_windows_hook_command_reason` catches `\\` (verify.py:144-145).
- Suggestion: Optional: if `len(tokens)==1` and the token is a win_abs `.sh` on win32 with a vibesop basename, treat as a rewrite candidate. Not required if F1's space allowlist is the only ship gate.
- Status: open

### F5 — Severity: MINOR
- File: scripts/demo/probe-inject.sh:22
- Fact vs suggestion: fact
- Description: The probe interpolates `$QUERY` into JSON with `printf '%s'`, so a query containing `"` or newlines breaks the envelope (or injects extra JSON fields).
- Evidence: `printf '{"prompt": "%s", "session_id": "probe-%s", "platform": "%s"}' "$QUERY" ...`. Default query is safe. `VIBE_BIN` is unquoted on purpose for `uv run ... vibe`. This is an operator-facing demo, not a hook the host runs on untrusted input. `dual-platform-demo.sh` likewise feeds `$QUERY` to `tmux send-keys`.
- Suggestion: `jq -n --arg q "$QUERY" --arg p "$platform" '{prompt:$q,session_id:("probe-"+$p),platform:$p}'`.
- Status: open

### F6 — Severity: MINOR
- File: tests/utils/test_bundled.py:34
- Fact vs suggestion: fact
- Description: The wheel-fallback unit tests assert path construction, not that hatch actually packed `registry.yaml` / `builtin_skills`.
- Evidence: `test_falls_back_to_wheel_bundle_when_repo_missing` checks `result == bundled_path("builtin_data", "core", "registry.yaml")` and `"builtin_data" in result.parts` — not `result.exists()`. `src/vibesop/` in this checkout has no `builtin_data/` or `builtin_skills/` (force-include is wheel-only). Real coverage is `.github/workflows/quickstart-e2e.yml` (`uv build` + `uv tool install ./dist/vibesop-*.whl`). Deleting `MANIFEST.in` is a no-op for hatchling; it never consumed that file.
- Suggestion: In the e2e job (or a packaging unit test), `unzip -l dist/*.whl` and assert `vibesop/builtin_data/core/registry.yaml` and `vibesop/builtin_skills/commit-message/SKILL.md`.
- Status: open
