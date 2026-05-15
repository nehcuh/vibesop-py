# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-05-15 15:30
**Session**: Fix `vibe skills list` + PyPI release v5.4.5

**Completed**:
- Diagnosed `SkillStorage.list_skills()` bug: non-recursive + manifest-dependent, missing pack skills
- Fix: resolve platform symlinks backwards to discover pack-installed skills
- `vibe skills list`: 13 → 209 skills
- All 46 related tests pass
- Version bump: 5.4.4 → 5.4.5, pushed tag v5.4.5 for PyPI release via GitHub Actions OIDC

**Key Learnings**:
- Two divergent skill discovery mechanisms in same codebase: `SkillStorage.list_skills()` (manifest-based, non-recursive) vs `SkillLoader` (recursive rglob)
- Pack skills have varying directory structures: gstack flat, omx/superpowers nested under `skills/`

**Files Modified**:
- `src/vibesop/core/skills/storage.py`

**Next Steps**: Monitor CI for v5.4.5 PyPI publish

---

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
<!-- handoff:end -->
