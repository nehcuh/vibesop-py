# Project Context

## Session Handoff

<!-- handoff:start -->
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

---

### 2026-04-29 01:00
**Session**: VibeSOP v5.3.1 Release

**Completed**:
- Documentation cleanup: archived 8 outdated/intermediate files to `docs/archive/`
- Fixed 2 broken documentation links in `docs/dev/CONTRIBUTING.md`
- Bumped version 5.3.0 → 5.3.1
- Successfully published to PyPI: https://pypi.org/project/vibesop/5.3.1/

**Key Learnings**:
- `uv publish` doesn't read `~/.pypirc` — use `twine upload dist/*` instead
- uv's .venv lacks pip module — install twine via `uv pip install --python .venv/bin/python twine`

**Commits**:
- 13dc34b: docs: fix broken links and archive outdated documentation
- 6d91c93: chore: bump version to 5.3.1

**Next Steps**: None — release complete
<!-- handoff:end -->
