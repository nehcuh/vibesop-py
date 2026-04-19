# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-04-19 10:47
**Session Summary**: 文档改进 - 会话追踪 opt-in 设计强调

**Completed**:
- 确认会话追踪默认为关闭状态（opt-in 设计）
- 检查文档发现配置表格有记录但缺乏醒目强调
- 改进 README.md：添加醒目的警告框，解释为什么默认关闭
- 改进用户文档：添加专门的"⚠️ Opt-In Design"章节
- 使用视觉元素（⚠️ 图标、引用块）吸引注意

**Files Modified**:
- `README.md`: 在会话智能路由部分添加 opt-in 警告框
- `docs/user/session-intelligent-routing.md`: 添加专门的 Opt-In Design 章节

**Key Improvements**:
- 用户现在能立即看到这是 opt-in 功能
- 清晰解释三个原因：性能、隐私、用户控制
- 避免用户误以为会话追踪是默认启用的

**Commit**: d5b04b9 - docs: emphasize opt-in nature of session tracking

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
