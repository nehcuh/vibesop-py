# Project Context

## Current project scope — 2026-10-22

VibeSOP 是多代理 AI 工程工作流系统：把请求路由到合适的技能或代理，按明确标准验证交付，并记录可观测的执行证据；围绕主线还提供技能选择、发布放行的治理，以及跨代理的经验/知识积累。SkillOS 是技能管理子系统；任务计划与验证交付、执行观测、经验检索、定时任务和实验研究共同构成当前仓库。

- 定位依据与边界：[docs/POSITIONING.md](docs/POSITIONING.md)。
- 源码与包元数据为 **8.6.0**（2026-10-22）。PyPI 与 GitHub Release 由 tag `v8.6.0` 的 Release workflow 发布。8.5.0 仍是上一公开版本，其只读 `vibe observe routing` 观测器保持不变，见[项目状态](docs/PROJECT_STATUS.md)。
- 工程主线继续验证选择和交付的可信性；未合并 evo 分支和未完成固定角色实验不算已发行能力。
- 旧 worktree 已归档，当前保留主目录与 `.experiment/worktree`。原始数据和未提交成果的恢复见[维护索引](docs/maintenance/README.md)。

## Historical session handoff

以下为当时的交接记录，日期相关的 Next Steps 不自动代表当前待办；涉及保留实验容器和证据的约束继续有效。

<!-- handoff:start -->
### 2026-10-22 S100 END · 8.6.0 已发布，Dependabot 收口

**Workspace**：main @ `34ad78a0`，与 origin 一致。tag `v8.6.0` = `c88caada`。PyPI 8.6.0。未入库：`.pi/`、`Makefile`、`.grok/hooks/`、pptx。

**完成**：正式发布 8.6.0（Release 39727715512，E2E 39727710603）。pillow 用 uv override 锁到 13.0.0，全量审计是 `pip-audit --no-deps --disable-pip`。哈希记在 `65fa9c8c`，该提交不移动标签。Dependabot 收成 `44722385`（CI/E2E 全绿）和 `34ad78a0`（openai 3.35.1、fastapi 0.146.0、pytest-mock 3.17.0）。Anthropic 维持 `<1.0.0` 并忽略 semver-major。NumPy 下限维持 `>=1.26.0`。收工时开放 PR 为 0。`34ad78a0` 的 E2E 39736146034 全绿。

**Next**：CI 39736145997 收工时 Windows Python 3.12 仍在跑。若红再修。不要 force-move `v8.6.0`，也不要把 Unreleased 的依赖提交当成新发布。

### 2026-10-16 S97 END · 对抗面板修复轮全闭环（12 commits pushed，CI 12/12 绿）

**Workspace**：VibeSOP main @ `031c7992`（全部推送，`9dcc3a53..031c7992` 共 12 commits；CI/E2E/CodeQL 三 run 全绿，CI 12/12 job 含双 3.13 lane）。工作树遗留 .pi/*、Makefile、memory/*、docs/*.pptx、.grok/hooks/（S95/S96/S97 会话层改动，memory/ 与 PROJECT_CONTEXT 由 session-end 提交）。产物链 `.omx/artifacts/pull-20261015/`（panel-report.md + 各批 fix diff + kimi/grok 双门禁 prompt/out）。

**完成**：S97 对抗面板总账 16 项（P1×7/P2×6/P3×3）经 dual-gate-review-fix 全部双门禁闭合（kimi 改动前闸 + grok 只读复审，批A→A-2→A-3、批B→B-2+NIT、批C、批C+D-2、批D、批E→E-2）。批E-2 修 cap 采样源（frontmatter→as-routed 池，1024/128）。push 后 CI 双 3.13 lane 红 → 根因升级为**产品缺陷**：glob 元字符 id 在 3.13 pathlib 下当跨分隔符通配符（`**` id 实测解析到无关技能 autonomous-experiment 并注入其内容；单 `*` 两版本均通配劫持）→ fixCI-glob-meta `031c7992`（`contains_glob_metachar` 守卫注入器 walk + 序列化 hint 两路径）双门禁闭合，CI 全绿。

**Next**：① 两个 NIT 另案——`_find_skill_md_path` docstring 措辞收紧（守卫拒绝范围比"glob lookups"字面更宽，实际无回归）+ `trace_cmd.py:114` trace_id→glob 既有行为；② kimi 提议的 skill_lint >1024 description warn 规则（新功能，防 cap 口径再漂移）；③ 轮初已知本地 artifact-links 基线失败未处置（`.omx` 悬挂引用，CI 不受影响）。

<!-- handoff:end -->

