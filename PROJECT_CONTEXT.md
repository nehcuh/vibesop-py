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
### 2026-10-16 S97 END · 对抗面板修复轮全闭环（12 commits pushed，CI 12/12 绿）

**Workspace**：VibeSOP main @ `031c7992`（全部推送，`9dcc3a53..031c7992` 共 12 commits；CI/E2E/CodeQL 三 run 全绿，CI 12/12 job 含双 3.13 lane）。工作树遗留 .pi/*、Makefile、memory/*、docs/*.pptx、.grok/hooks/（S95/S96/S97 会话层改动，memory/ 与 PROJECT_CONTEXT 由 session-end 提交）。产物链 `.omx/artifacts/pull-20261015/`（panel-report.md + 各批 fix diff + kimi/grok 双门禁 prompt/out）。

**完成**：S97 对抗面板总账 16 项（P1×7/P2×6/P3×3）经 dual-gate-review-fix 全部双门禁闭合（kimi 改动前闸 + grok 只读复审，批A→A-2→A-3、批B→B-2+NIT、批C、批C+D-2、批D、批E→E-2）。批E-2 修 cap 采样源（frontmatter→as-routed 池，1024/128）。push 后 CI 双 3.13 lane 红 → 根因升级为**产品缺陷**：glob 元字符 id 在 3.13 pathlib 下当跨分隔符通配符（`**` id 实测解析到无关技能 autonomous-experiment 并注入其内容；单 `*` 两版本均通配劫持）→ fixCI-glob-meta `031c7992`（`contains_glob_metachar` 守卫注入器 walk + 序列化 hint 两路径）双门禁闭合，CI 全绿。

**Next**：① 两个 NIT 另案——`_find_skill_md_path` docstring 措辞收紧（守卫拒绝范围比"glob lookups"字面更宽，实际无回归）+ `trace_cmd.py:114` trace_id→glob 既有行为；② kimi 提议的 skill_lint >1024 description warn 规则（新功能，防 cap 口径再漂移）；③ 轮初已知本地 artifact-links 基线失败未处置（`.omx` 悬挂引用，CI 不受影响）。

### 2026-10-12 S97 · 三平台配置部署闭环（claude-code / grok-build / kimi-cli）

**Workspace**：VibeSOP main @ `9dcc3a53`，仓库 tracked 无本会话改动（工作树里 .pi/*、Makefile、.grok/hooks/、pptx 均为 S95/S96 遗留，归属待定）。改动全在用户全局目录：`~/.claude`、`~/.grok`、`~/.kimi-code`。三目录 tar 备份在 `/tmp/vibesop-deploy-backup-20261012/`（重启即失，需要尽快转移）。

**完成**：应用户要求把当前项目配置部署到三平台。预检发现 `~/.claude/settings.json` 路由钩子注册丢失（疑被 mirror 安装覆盖，本会话开头因此无自动路由注入）→ `uv run vibe build <target> --output <dir>` 三平台重部署（kimi 必须 `--output ~/.kimi-code`，deploy 默认表过时）→ `vibe verify` 三平台全绿，grok/claude route hook 端到端 exit 0（gate33 exit-2 不复现）。回归一处：重渲染把 `enabledPlugins`/`extraKnownMarketplaces`（warp 插件）静默洗掉，已从备份手工合并恢复；100 个中心技能符号链接无损伤。

**Next**：① 两个产品缺陷待用户定夺立 issue 或直接修——`_render_settings_json` 键级合并缺失（claude_code.py）+ SecurityScanner 短语误伤 QA 类技能（omx/ultraqa L44 运行时拒注入）；② 重启三个 agent 使新 hooks 生效；③ 如需保留备份，把 /tmp 的三个 tar 挪到持久位置。

<!-- handoff:end -->

