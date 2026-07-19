# Project Context

## Session Handoff

<!-- handoff:start -->

### 2026-07-18 (S31) fanout 诊断 + panel 分拆 + 质量收口
**Session**: 六路并行诊断 → control panel 分拆为独立仓库 → 全部已知问题收口 → CI 转绿。
**Completed**:
- Fanout 诊断（6 explore agents）：定位 main CI 双红因（.vibe 脚本 I001 + 注册表耦合测试）、release.yml 结构性损坏（workflow_call 缺失，发布从未跑通）、版本三方漂移、15 个堆积分支
- Panel 分拆：154 个 WIP 文件提交保护 → 创建 nehcuh/vibesop-py-panel（私有）并推为 main（36 提交全历史）→ worktree 转独立克隆（环境完整迁移）→ 主仓删 panel 规划文档（a1b3227）
- 仓库清理：origin 15 个陈旧分支删除（bundle 备份于 vibesop-py-branch-backup-20260718.bundle，确认无用可删），本地/远端只剩 main
- 质量收口 3 提交：c18d703（CI 门：ruff 排除 .vibe、测试 tmp project_root 隔离、bandit skips 收编 pyproject——原 [tool.bandit."skips"] 从未生效、pip-audit 全 extras、uv 0.11.19、删 mypy）、80b37e5（dependabot→uv、verify-* 脚本重写、删 sync-core.sh、benchmark 双目录合并）、2efdaf6（CHANGELOG 补 59 提交、INDEX 修死链+ADR-004、删陈旧 docs/PROJECT_CONTEXT.md）
**Verification**: CI run 29636446131 全 6 job 绿；本地 4067 passed / 覆盖率 74.65%；bandit/pip-audit（含 torch/transformers）0 问题
**Next**: ~~用户新提案（商店/未命中/蒸馏/Langfuse）~~ 已全部落地（P0–P4，2026-07-18，CI 绿）。**后续工作项目（用户确认 2026-07-18）：Zed adapter**（已入 ROADMAP Backlog）；Windows 副本兜底补测试。其余 backlog：文档深度治理（49 坏引用/187 版本漂移）、双 PromptChainGenerator 合并、`InstinctLearner._load_sequences` 加载怪癖、squad 逐角色步骤展开的确定性

### 2026-07-14 (S30) 技能架构梳理、迁移与清理
**Session**: 全面梳理项目技能存储架构，迁移自定义技能到 cross-cutting，清理重复和损坏条目。
**Completed**:
- 梳理 128→116 个技能目录，按命名空间分类（builtin/mattpocock/omx/superpowers/personal）
- 发现三层技能存储架构：~/.config/skills/ → ~/.claude/skills/ → .pi/skills/
- 删除 12 个与 builtin 重复的别名目录 + 6 项重复/损坏
- personal-kimi-gated-fix → cross-cutting/kimi-gated-fix.skill（git 跟踪）
- Fuck_My_Shit_Mountain（364K, 50 文件）→ cross-cutting/fuck-my-shit-mountain.skill
- 配置 cross-cutting namespace（priority 110）自动安装
**Verification**: 3 个 cross-cutting 技能就位，JSON 配置有效
**Next**: git commit + push；验证 vite route 能发现全部 cross-cutting 技能

<!-- handoff:end -->
