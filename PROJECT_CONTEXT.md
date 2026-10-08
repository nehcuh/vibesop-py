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
### 2026-10-08 S95 END · 拉取评审 COMMENT + 14 修复落盘待提交

**Workspace**：VibeSOP main（本地 ahead 2，均为 S90 记忆提交，未 push）。工作树有 14 个修复文件未 commit；`.omx/` 产物、`.grok/workflows/`、`examples/datasets/` 不入库。

**完成**：origin/main 10 提交（`86b69f43→58692f70`）E2E 全绿后补跑五路对抗评审，终裁 **COMMENT**（15 候选 → 14 确认 / 1 驳回，0H/2M/12L），报告 `.omx/artifacts/adversarial-review-86b69f43-58692f70.md`。用户点名「标准流程进行优化」后 14 条确认全修：C1 hook 配置错误信封用户可见（全平台 exit 0）+ 裸 CLI exit 2；L1 视频级联对齐真实顺序 explicit→scenario+semantic→AI triage→matcher；12 LOW（TTS 读音、ffmpeg 退出码、asyncio.to_thread、tempfile.mkdtemp 重构、钉测试等）。验证 [executed]：定向 241 + 波及 2042 passed / 4 skipped、ruff 全仓干净、basedpyright 0 err、hermetic exit 0。

**关键决定**：修复未 commit——项目惯例（S80/S55）等用户点名再提交。grok 真 miss 仍静默（NIT-3 契约保留），仅 errors 发信封。

**Next**：用户点名「提交」→ 分组 git add（排除上述目录）→ conventional commit → push → 盯 **job 级** CI。`render.py` 高亮行号绑采集输出，下次渲染视频前需人工复核。

### 2026-10-07 S95 · 双门禁修复轮 A/B + CI 修红 + JEV 复测

**Workspace**：VibeSOP main @ `58692f70`（已推送，CI/E2E/CodeQL 全绿）。`.pi/settings.json`、`.pi/extensions/*.ts`、skills.md、vibe-help.md、Makefile、`.grok/hooks/`、17页 pptx 仍是树内脏项，未纳入。

**完成**：批A `bff4699e`（RoutingConfig 强制 bypass>=keyword validator；5 处 keyword_match_max_chars 5→15 + bypass 文档；unified.py docstring/指针；scripts/video lint 清零）；批B `96d2a75a`（cost-log 与 match path 共享 _bounded_confidence）。双门禁各经一轮 REQUEST CHANGES 后双 APPROVE（claude post-commit 闸抓到 _layers.py 契约被切出提交的 P0）。CI 既有红修复：`24395b27`（ruff format 3 文件 + virtualenv 21.14.5）+ `58692f70`（urllib3 2.8.0）。

**JEV 复测**：维持 S94「不接入」。构造集 jev-1.13.0 **57/61** vs 生产路由 triage-on **52/61**（p50 1270ms vs 15ms，仅 3/61 真调 LLM）；conf=0.99 过注入、noul 不一致（16/37）复现；真实会话集 `/tmp/jev-real-eval/` 已失不可重验。原始 `/tmp/jev-reval-20261007/`。

**Next**：B5 `[:200]` 截断产品决策；eval triage-on 覆盖缺口单开一批（`eval_routing.py:193` 硬编码 triage off）；vibe-route.ts 手写逻辑下沉模板（被未提交 .pi/extensions 阻塞）；grok CLI 需 `grok update` ≥1.0.13 才能恢复第二道闸。

### 2026-09-24 S94 END · JEV 不替换技能路由

**Workspace**：VibeSOP main。本会话未改 `src/`。`.pi/` 与 `.grok/hooks/` 仍是既有脏项，未纳入。

**完成**：官方 `jev-1.13.0` choice 对过构造评测和本项目 Grok 真实会话。构造集 58/59 对关键词路由 53/59；真实会话 17/27 对 23/27。延迟中位数约 1.15s，与 deepseek triage 的 988ms 同级。送入的是截断后的 description/intent，约 1800 token。

**关键决定**：不把 JEV 接进路由。判断用 choice；不要用 noul 当注入闸门。密钥和 `/tmp/jev-*-eval/` 原始记录不入库。

**Next**：若再比较，对照现有 AI triage，并单独计真实会话里不该注入的句子。
<!-- handoff:end -->
