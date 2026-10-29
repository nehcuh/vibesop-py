# Project Context

## Current project scope — 2026-10-28

VibeSOP 是多代理 AI 工程工作流系统：把请求路由到合适的技能或代理，按明确标准验证交付，并记录可观测的执行证据；围绕主线还提供技能选择、发布放行的治理，以及跨代理的经验/知识积累。SkillOS 是技能管理子系统；任务计划与验证交付、执行观测、经验检索、定时任务和实验研究共同构成当前仓库。

- 定位依据与边界：[docs/POSITIONING.md](docs/POSITIONING.md)。
- 源码与包元数据为 **8.7.1**（2026-10-28）。PyPI 与 GitHub Release 由 tag `v8.7.1` 的 Release workflow 发布。8.7.0 是上一公开版本，见[项目状态](docs/PROJECT_STATUS.md)。
- 工程主线继续验证选择和交付的可信性；未合并 evo 分支和未完成固定角色实验不算已发行能力。
- 旧 worktree 已归档，当前保留主目录与 `.experiment/worktree`。原始数据和未提交成果的恢复见[维护索引](docs/maintenance/README.md)。

## Historical session handoff

以下为当时的交接记录，日期相关的 Next Steps 不自动代表当前待办；涉及保留实验容器和证据的约束继续有效。

<!-- handoff:start -->
### 2026-10-28 · fallback-llm 死锁修复 + 8.7.1 发版

**Workspace**：codex 路由阻断报告（/tmp/cmspark-pr794-routing-block-20261028/report.md）暴露 8.7.0 回归——未匹配子任务的 `fallback-llm` 哨兵被所有交付入口渲染成「恢复技能、重建计划」阻断，外部 agent 正确核实该技能不存在后死锁。修复 `c7d62d05`：步骤级 FALLBACK_LLM = 本步骤由 agent 直接执行（与顶层 fallback 层同构），唯验证步骤带哨兵仍以 `fallback verifier` 阻断；全量 8257 passed/32 skipped/1 failed（`.omx/` 机器本底）。kimi 对抗复审 **APPROVE**（P0 五面全净；吸收 P1-2/P2-1/P2-3/P2-4；P1-1 hook JSON 仍携带原始 `skill_id: "fallback-llm"` 字段为已知残留，入 CHANGELOG；P1-3 全 fallback 计划 hook 路径仍降级单发、编排/CLI 路径保持可执行，维持现状待用户批准）。发版 `0051ab30`：8.7.1 patch；`check_doc_versions --fix` 会重写历史块中 v 前缀版本号，历史事实一律用无 v 写法规避；Release run 首跑两 Windows job 撞已知 `test_cli_concurrent_write_baseline_does_not_clobber` WinError 5 flake（同提交 main CI 14/14 全绿）rerun 过。验收：Release run 绿，PyPI latest 8.7.1（wheel+sdist），GitHub Release 8.7.1 含双 publish attestation，wheel 实检 METADATA 8.7.1、25 个 builtin SKILL.md、修复代码在包内。

**未入库**：`.pi/`、`.grok/hooks/`、pptx（交接约束，勿一并暂存）。

### 2026-10-27 · 交接审计三轮闭环 + 8.7.0 发版

**Workspace**：交接审计 6 提交（`7b8a584b` 扫描器配对级位置豁免 / `5fef8ff8` SKILL.md `metadata:` 路由提示+缓存 schema v7 / `f1fda4e1` 编排显式 sequential+未解析步骤可见 / `fb5c2136` worktree-convergence+release-version 内置技能+warm_up 锚可达守卫+基线刷新 / `b70aa259` auto-config 写安全 / `d24c3d5a` 审计台账）。三轮对抗全绿：自组五路 + kimi 五路（2P1+7P2 全处置）+ kimi 终审（P2-1 被 probe 驳回、P2-2 文档更正，增量复核 CONFIRMED）。全量 8234 passed/32 skipped/1 failed——失败为 `.omx/` 未跟踪遗留产物触发 artifact-links dangling，机器本底（HEAD 干净 worktree 同测试过），见审计台账 §6.1。

**发版**：8.7.0（新功能升 MINOR）已发布落地。CHANGELOG 8.7.0 段；`check_doc_versions --fix` + INDEX/PROJECT_CONTEXT 发布行更正——**8.6.1 从未发布**（PyPI 实际最新曾为 8.6.0，S102 纪要中「8.6.1 已发布」系中断残留失实行，本次已修正）。落地时序：首跑 Release run 被全锁 pip-audit 拦（setuptools 83.0.0 GHSA-xmj3-9gf7-h52w）→ `15308489` 升 84.2.1 后重指 tag（未发布过，安全）重跑；一次 `Test Windows (3.13)` 撞 `test_cli_concurrent_write_baseline_does_not_clobber` rename 竞态 flake（同提交 main CI 14 job 全绿）rerun 过。验收：Release run 绿，PyPI latest 8.7.0（wheel+sdist），GitHub Release 8.7.0 含双 publish attestation，wheel 实检 25 个 builtin SKILL.md（含 worktree-convergence / release-version）。

**未入库**：`.pi/`、`.grok/hooks/`、pptx（交接约束，勿一并暂存）。

<!-- handoff:end -->

