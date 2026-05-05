# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-05-05 18:50
**Session**: 公众号文章修订 + 路由代码提交推送

**Completed**:
- Revised `docs/vibe-coding-article.md`: added "Core Problems + Survival Principles" overview chapter (5 problems mapped to 5 principles via table)
- Article structure now: answers first → story second → methodology third
- Git commit + push: `2380ec2` — routing candidate dedup, management-only skill exclusion, triage prompt v3

**Files Modified**:
- `docs/vibe-coding-article.md`
- `src/vibesop/core/routing/candidate_manager.py`
- `src/vibesop/core/routing/triage_service.py`
- `src/vibesop/llm/triage_prompts.py`
- `tests/core/routing/test_candidate_dedup_and_management.py`

**Next Steps**: None — user left

---

### 2026-05-03 15:35
**Session**: Claude Code template sync — Agent Override Protocol

**Completed**:
- Synced Agent Override Protocol (4-step) + Disagreement Protocol (7-step) to Claude Code templates
- Updated `CLAUDE.md.j2` with mandatory override rules, failure mode, deviation recording guardrails
- Updated `CLAUDE.md.project.j2` with simplified override protocol for project-level context
- Verified with `pytest -k "claude"`: 29 passed
- Committed and pushed: `ffc9bcd`

**Key Learnings**:
- Cross-platform template consistency requires explicit checks after updating one platform
- "我要离开了" = "heading out" is a session-end trigger (was missed)

**Files Modified**: 2 files
- `src/vibesop/adapters/templates/claude-code/CLAUDE.md.j2`
- `src/vibesop/adapters/templates/claude-code/CLAUDE.md.project.j2`

**Next Steps**: None — template sync complete
<!-- handoff:end -->
