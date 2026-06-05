# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-05-29 23:30
**Session Summary**: 修复 Claude Code UserPromptSubmit hook - python3 在 uv 项目中找不到 vibesop

**Completed**:
- 定位根因: `vibesop-route.sh` 用裸 `python3`，系统 Python 无 `vibesop`
- 模板修复: `vibesop-route.sh.j2` 添加 `uv run python` → `python3` 自动检测
- 实例修复: `~/.claude/hooks/vibesop-route.sh` 同步更新
- 知识记录: `memory/project-knowledge.md` 添加 uv/python3 陷阱条目

**Files Modified**:
- `src/vibesop/adapters/templates/shared/vibesop-route.sh.j2`
- `~/.claude/hooks/vibesop-route.sh`
- `memory/project-knowledge.md`
- `memory/session.md`

**Verified**: 39 tests pass; hook 手动执行返回正确 JSON

**Next Steps**: 无
<!-- handoff:end -->

### 2026-04-08
**Session Summary**: CLI command cleanup and comprehensive README documentation

**Completed**:
- Removed deprecated `route-cmd select` command (integrated as `vibe route --validate`)
- Added description for `inspect` command
- Updated `vibe build --output` help to clarify deployment
- Comprehensive README overhaul (+1026/-235 lines across EN/CN versions)
- Documented project positioning, comparisons with alternatives, installation guide

**Commits**:
- `b51e8d6`: fix: improve CLI command structure and remove deprecated commands
- `870fae8`: docs: comprehensive README overhaul with complete project documentation

**Test Status**: 1269 passed, 1 skipped, ~80% coverage

**Next Steps**:
1. Implement MemPalace integration (recorded as future optimization)
2. v4.1.0: AI Triage production readiness
3. v4.2.0: Skill health monitoring
4. Address remaining P2 items from code review
