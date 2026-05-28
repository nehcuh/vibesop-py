# Project Context

## Session Handoff

<!-- handoff:start -->

### 2026-05-28 (S9) pi-skill-namespace-collisions
**Session**: Fix pi agent skill name collisions + gstack default install removal
**Completed**:
- Added `DEFAULT_AUTO_INSTALL_PACKS` (excludes gstack) in constants.py; `_auto_install()` and `_sync_platform_symlinks()` now use filtered lists
- Added `_is_valid_skill()` in pack_installer to skip SKILL.md files with empty descriptions
- Added `_namespace_skill_name()` in pi adapter to prefix `name:` field with pack namespace (e.g., `name: qa` → `name: gstack-qa`)
**Root cause**: Pi agent resolves name collisions by alphabetical directory order; VibeSOP's routing conflict resolution runs before pi loads skills
**Files**: constants.py, install.py, quickstart_runner.py, pack_installer.py, pi_coding_agent.py, test_pack_installer.py

### 2026-05-28 (S8) reinstall-pypi-publish
**Session**: Reinstall project with uv + publish v5.4.6 to PyPI
**Completed**:
- `uv sync` reinstall locally; `uv tool install --force --editable .` to override global vibesop
- Version bump 5.4.5 → 5.4.6 (v5.4.5 files already existed on PyPI)
- Built sdist + wheel with `uv build`, published via `uv publish` with token auth from `~/.pypirc`
**Files**: pyproject.toml (version bump)

<!-- handoff:end -->
