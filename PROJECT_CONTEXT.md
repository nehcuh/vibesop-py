# Project Context

## Session Handoff

<!-- handoff:start -->

### 2026-05-30 (S12) yaml-quoting-bugs
**Session**: Deep audit + fix YAML frontmatter generation bugs across VibeSOP
**Completed**:
- Traced root cause of `[OMX]` YAML parse errors: `[` interpreted as flow sequence in bare strings
- Fixed 7 files: _shared.py (3 locations), base.py, format_converter.py, _discovery.py (2), instinct_cmd.py, cross_cutting.py, pi/skills/SKILL.md.j2
- Added `_yaml_dquote()` and `_yaml_safe_value()` centralized helpers for YAML-safe description quoting
- Fixed depth-2 skill install path not discovered by is_pack_installed() — added source_path fallback
- All 118 tests pass; rebuilt pi config: 85 skills, 0 YAML errors
**Root cause pattern**: Three independent code paths (Jinja2, f-string, str.replace) all generated YAML without quoting free-text values
**Files**: _shared.py, base.py, format_converter.py, _discovery.py, instinct_cmd.py, cross_cutting.py, pi/skills/SKILL.md.j2
**Next**: None — all known YAML generation paths audited and fixed

### 2026-05-30 (S11) pi-agent-config-cleanup
**Session**: Fix pi agent skill conflicts — frontmatter + orphan cleanup + gstack removal + extension path bug
**Completed**:
- Batch-fixed 66 SKILL.md files missing YAML frontmatter (description is required)
- Fixed shared SKILL.md.j2 template generating files without frontmatter
- Removed gstack from registry/config/platform dirs
- Fixed vibesop-track.ts template hardcoding session-end path
**Files**: pi_coding_agent.py, SKILL.md.j2, registry.yaml, config.toml, vibesop-track.ts.j2
**Next**: Verify pi agent starts without errors

<!-- handoff:end -->
