# Project Context

## Session Handoff

<!-- handoff:start -->

### 2026-05-30 (S11) pi-agent-config-cleanup
**Session**: Fix pi agent skill conflicts — frontmatter + orphan cleanup + gstack removal + extension path bug
**Completed**:
- Batch-fixed 66 SKILL.md files missing YAML frontmatter (description is required)
- Fixed PiCodingAgentAdapter missing clean_orphan_skills() call
- Fixed shared SKILL.md.j2 template generating files without frontmatter (synced to uv tool install path)
- Removed gstack from core/registry.yaml, .vibe/config.toml, and all platform skill dirs
- Fixed vibesop-track.ts template hardcoding session-end path without builtin- prefix
- Recorded 5 instincts for reusable patterns
**Files**: pi_coding_agent.py, SKILL.md.j2, registry.yaml, config.toml, vibesop-track.ts.j2, vibesop-track.ts
**Next**: Verify pi agent starts without errors; consider adding namespace-aware skill path resolution in extensions

### 2026-05-29 (S10) 4-phase-transformation-audit-optimization
**Session**: Phase 4 audit review optimization — 3 tasks completed
**Completed**:
- Dead code removal: SkillDefinition dataclass removed from base.py; CHANGELOG v5.5.0 entry; README gstack→mattpocock sync
- SKILL.md template unification: `templates/shared/SKILL.md.j2` + `render_skill_md()` in `_shared.py`; 2 old adapter templates deleted
- Pi adapter → SdkBasedAdapter: ~30 lines duplicated code removed; Pi now correctly inherits from SdkBasedAdapter
- Shell hook optimization: `vibesop-route.sh.j2` 53→22 lines; all logic in Python AgentRuntime
**Test**: 2963 passed, 3 skipped, 0 failures
**Files**: _shared.py, claude_code.py, pi_coding_agent.py, vibesop-route.sh.j2, base.py, spec/__init__.py, CHANGELOG.md, README.md, pyproject.toml, ARCHITECTURE.md, spec_cmd.py, test files, SKILL.md.j2 (new), tests/conformance/ (new)
**Next**: git commit pending changes; v5.5.0 ready for release

### 2026-05-28 (S9) pi-skill-namespace-collisions
**Session**: Fix pi agent skill name collisions + gstack default install removal
**Completed**:
- Added `DEFAULT_AUTO_INSTALL_PACKS` (excludes gstack) in constants.py; `_auto_install()` and `_sync_platform_symlinks()` now use filtered lists
- Added `_is_valid_skill()` in pack_installer to skip SKILL.md files with empty descriptions
- Added `_namespace_skill_name()` in pi adapter to prefix `name:` field with pack namespace (e.g., `name: qa` → `name: gstack-qa`)
**Root cause**: Pi agent resolves name collisions by alphabetical directory order; VibeSOP's routing conflict resolution runs before pi loads skills
**Files**: constants.py, install.py, quickstart_runner.py, pack_installer.py, pi_coding_agent.py, test_pack_installer.py

<!-- handoff:end -->
