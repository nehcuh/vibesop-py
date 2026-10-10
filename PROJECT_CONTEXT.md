# Project Context

## Current project scope — 2026-09-15

VibeSOP 是多代理 AI 工程工作流系统：把请求路由到合适的技能或代理，按明确标准验证交付，并记录可观测的执行证据；围绕主线还提供技能选择、发布放行的治理，以及跨代理的经验/知识积累。SkillOS 是技能管理子系统；任务计划与验证交付、执行观测、经验检索、定时任务和实验研究共同构成当前仓库。

- 定位依据与边界：[docs/POSITIONING.md](docs/POSITIONING.md)。
- 源码、包元数据、PyPI 与 GitHub Release 均为 **8.5.0**（2026-09-15 发布）。8.5.0 新增只读的 `vibe observe routing` 在线路由证据观测器（`vibesop.observe.routing` v1）与 eval provenance fail-closed，见[项目状态](docs/PROJECT_STATUS.md)。
- 工程主线继续验证选择和交付的可信性；未合并 evo 分支和未完成固定角色实验不算已发行能力。
- 旧 worktree 已归档，当前保留主目录与 `.experiment/worktree`。原始数据和未提交成果的恢复见[维护索引](docs/maintenance/README.md)。

## Historical session handoff

以下为当时的交接记录，日期相关的 Next Steps 不自动代表当前待办；涉及保留实验容器和证据的约束继续有效。

<!-- handoff:start -->
### 2026-10-10 S96 END · 二轮评审修复全推送 + 本地部署验证 + doctor 修红

**Workspace**：VibeSOP main @ `f5f98d88`（全部推送，CI/E2E/CodeQL 全绿）。工作树 tracked 干净；`.omx/` 产物不入库。意外副作用：本机全局 npm 装了 `oh-my-codex@0.21.8`（沙盒 PATH 串扰所致，已披露，可 `npm uninstall -g oh-my-codex`）。

**完成**：拉取 `41b7699b..251043f7`（3 提交：--with-cli OMX 伴装 / occupied-target 保护 / 依赖+CI 更新）→ 七路评审（内部五路 swarm + claude + grok）9 确认（0H/1M/8L），grok 唯一 HIGH 经实证驳回。用户点名后 F1–F8 全修：`9d886c7d`（`_which_trusted` 堵 Windows CWD 劫持 / ANSI 剥离 / `installed_off_path` / Volta .exe 直跑）+ `b4f9d412`（occupied 文案 + upgrade 契约测试）+ `497d3bb6`（attest v4.2.2 注释 + pre-commit ruff 0.16.4）;kimi 门禁两轮收敛 APPROVE（N1 阻塞项被 autouse fixture 证据驳回，吸收其硬化建议）。本地部署验证：`vibe build claude-code --output ~/.claude` 174→182 skills;fake-node 沙盒实证 npm.cmd 零执行；敌意 cwd 载荷零执行。DeepSeek route 三层实证（直连 ROUTE_LLM_OK / keyword 命中 / AI_TRIAGE 1235.9ms 选中 experience-evolution）。doctor 修红 `f5f98d88`:`PROVIDER_MODEL_ALIASES` 别名感知（项目 SOP 要求显式写 `deepseek-v4-flash`，厂商重定向到 `deepseek-flash`)。

**Next**：用户在别处评审 4 个提交（`9d886c7d`/`b4f9d412`/`497d3bb6`/`f5f98d88`)，意见回来走 fix-from-review。遗留同 S95(B5 截断决策、eval triage-on 覆盖缺口、vibe-route.ts 下沉）。证据：`.omx/artifacts/pull-20261010b-*.md`、`panel-20261010b/`、`e2e-evidence-20261010-deploy.md`。

### 2026-10-08 S95 END · 拉取评审 COMMENT + 14 修复落盘待提交

**Workspace**：VibeSOP main（本地 ahead 2，均为 S90 记忆提交，未 push）。工作树有 14 个修复文件未 commit；`.omx/` 产物、`.grok/workflows/`、`examples/datasets/` 不入库。

**完成**：origin/main 10 提交（`86b69f43→58692f70`）E2E 全绿后补跑五路对抗评审，终裁 **COMMENT**（15 候选 → 14 确认 / 1 驳回，0H/2M/12L），报告 `.omx/artifacts/adversarial-review-86b69f43-58692f70.md`。用户点名「标准流程进行优化」后 14 条确认全修：C1 hook 配置错误信封用户可见（全平台 exit 0）+ 裸 CLI exit 2；L1 视频级联对齐真实顺序 explicit→scenario+semantic→AI triage→matcher；12 LOW（TTS 读音、ffmpeg 退出码、asyncio.to_thread、tempfile.mkdtemp 重构、钉测试等）。验证 [executed]：定向 241 + 波及 2042 passed / 4 skipped、ruff 全仓干净、basedpyright 0 err、hermetic exit 0。

**关键决定**：修复未 commit——项目惯例（S80/S55）等用户点名再提交。grok 真 miss 仍静默（NIT-3 契约保留），仅 errors 发信封。

**Next**：用户点名「提交」→ 分组 git add（排除上述目录）→ conventional commit → push → 盯 **job 级** CI。`render.py` 高亮行号绑采集输出，下次渲染视频前需人工复核。
<!-- handoff:end -->
