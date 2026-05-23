# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-05-23 16:50
**Session**: Fix GitHub URL clone bug + add --platform flag to install

**Completed**:
- Fixed `RepoAnalyzer.analyze()` passing GitHub web URLs (`/tree/...`, `/blob/...`) directly to `git clone` — invalid git remote
- Added `_parse_github_url()` to decompose URLs into (clone_url, subdirectory) pairs
- Added `--platform`/`-p` flag to `vibe install` (claude-code, kimi-cli, opencode, cursor)
- `PackInstaller.install_pack()` already supported `platforms=` param — CLI just needed to expose it
- Added `_validate_platform()` with early validation against `SkillStorage.PLATFORM_SKILLS_DIRS`
- 16 analyzer tests + 14 install tests all pass

**Key Learnings**:
- `git clone` silently fails on GitHub web UI URLs with `/tree/` or `/blob/` path segments
- `patch.object(analyzer, "git_clone") as mock_clone` pattern needed for asserting on instance method calls

**Files Modified**:
- `src/vibesop/installer/analyzer.py`
- `src/vibesop/cli/commands/install.py`
- `tests/installer/test_analyzer.py`
- `tests/cli/test_install_command.py`
- `pyproject.toml` (added pytest-asyncio dev dep)

**Next Steps**: Can now use `vibe install <url-with-subdir> --platform <target>`

---

### 2026-05-17 16:00
**Session**: Test coverage improvement — 172 new tests + config fix + adapter refactor + push

**Completed**:
- Fixed `config_manager._load_skill_config_file()` cross-format TOML loading bug (isinstance guard)
- Fixed Kimi CLI E2E tests for slim AGENTS.md format
- 172 new tests: instinct learner (36), skills loader (47 new file), external_loader (25), storage (9), matching strategies (55 new file)
- Adapter refactoring: slim AGENTS.md index, routing-protocol/session-lifecycle migrated to docs/
- Coverage: 72.61 → 73.75%, 2647 → 2766 passing tests
- Committed + pushed: `335c082`

**Key Learnings**:
- `SkillMetadata` requires `intent` as positional arg (not defaulted) — test instantiations need all 4 required fields
- `PromptSkill._prompt_template` is private (underscore prefix)
- `SkillLoader` coverage went from 0 tests to 47 tests — most impactful new file

**Files Modified**:
- `src/vibesop/core/skills/config_manager.py`
- `tests/core/skills/test_loader.py` (new)
- `tests/core/matching/test_strategies.py` (new)
- `tests/core/skills/test_external_loader.py`
- `tests/core/skills/test_skill_storage.py`
- `tests/core/test_instinct_learner.py`
- `tests/e2e/test_agent_runtime.py`
- Adapter files: `_shared.py`, `claude_code.py`, `kimi_cli.py`, `opencode.py`, templates

**Next Steps**: Phase 3 complete; next session could target integration/e2e tests or remaining low-coverage modules
<!-- handoff:end -->
