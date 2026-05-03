# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-05-03 11:15
**Session**: Routing inconsistency fix — OpenCode config sync + markdown intent stripping

**Completed**:
- Fixed `~/.config/opencode/AGENTS.md`: verbatim query instruction (`<original_user_query>`), orchestration plan compliance, removed stale `riper-workflow`
- Removed stale `riper-workflow` from `~/.config/opencode/config.yaml` (kept `builtin/riper-workflow`)
- Synced orchestration plan section to Claude Code template (`CLAUDE.md.j2`)
- Added `_clean_intent()` in `task_decomposer.py` to strip markdown artifacts (`**Input`, `**Translation/Understanding`)
- Added 5 regression tests for markdown stripping
- P1-B sweep: 349 tests passed, zero regressions
- Explained root causes to user: temperature variance + Agent query rewriting + riper over-matching + stale OpenCode config

**Key Learnings**:
- OpenCode config was stale compared to Claude Code templates (Fix B not applied)
- Stale `riper-workflow` entry without `builtin/` prefix created duplicate/conflicting matches
- LLM markdown artifacts leak into intent labels via regex fallback when JSON parsing fails
- `_clean_intent()` pattern: strip `\*+\s*` from intent strings before downstream consumption

**Files Modified**: 3 files
- `src/vibesop/adapters/templates/claude-code/CLAUDE.md.j2` — orchestration plan instruction
- `src/vibesop/core/orchestration/task_decomposer.py` — `_clean_intent()` + markdown stripping
- `tests/core/orchestration/test_task_decomposer.py` — 5 regression tests

**Next Steps**: None — fixes complete

---

### 2026-04-29 15:30
**Session**: 移除冗余 builtin 技能 (systematic-debugging / verification-before-completion / using-git-worktrees)

**Completed**:
- 移除 3 个从 superpowers 移植来的内置技能（SKILL.md + 已安装副本）
- 路由更新：`systematic-debugging` → `gstack/investigate`，`verification-before-completion` → `gstack/investigate`，`using-git-worktrees` → `superpowers/using-git-worktrees`
- 更新 cold_start、recommender、format_converter、triage_prompts、task-routing 等所有引用
- 保留 `riper-workflow` 作为内置技能
- 测试：92 passed，1 预存失败（无关）

**Key Decisions**:
- 这 3 个技能原本是 superpowers 包的技能，早期移植进了 VibeSOP builtin
- 当前 superpowers 安装只包含 7 个精选技能（`superpowers-*` 前缀），不含这 3 个
- `gstack/investigate` 可替代 `systematic-debugging`，`verification-before-completion` 无直接替代

**Files Modified**: 10 files (-347/+26)
- core/registry.yaml, core/policies/task-routing.yaml
- src/vibesop/core/optimization/cold_start.py, src/vibesop/core/skills/recommender.py, src/vibesop/core/skills/format_converter.py, src/vibesop/llm/triage_prompts.py
- tests/core/test_cold_start.py

**Next Steps**: None — cleanup complete
<!-- handoff:end -->
