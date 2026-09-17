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
### 2026-09-17 S86 END · Hook 无匹配横幅静默

**Workspace**：VibeSOP main，ahead origin/main 1（S85 chore）+ 本 commit。`.pi/` 与 `.grok/hooks/` 仍是 S85 工作树脏项，未纳入。

**完成**：`to_hook_response` miss 不再写用户可见 `systemMessage`。Claude/Kimi 指纹进 `additionalContext`；`grok-build` 返回 `{}`。Grok routing rule 把静默当成功 miss。已 `uv tool install --reinstall --force --no-cache .` + `vibe build grok-build --output ~/.grok`。现场：grok miss `{}`，claude miss 无 🤖，session-end 命中仍 `VibeSOP routed:`。

**关键决定**：不对 `~/.claude` 全量 build（184 extra skills，避免 orphan 清理）；Claude hook 走 tool 环境 Python，重装即可。Grok UserPromptSubmit 会丢掉 allow-hook stdout，所以不能靠 additionalContext 当指纹。

**Next**：重启 Grok（Claude 同理）后在 llm-safety 确认闲聊不再弹横幅。

### 2026-09-15 S85 END · VibeSOP 8.5.0 配置分发

**Workspace**：VibeSOP main `dfed8ab4`，工作树当时 clean。

**完成**：8.5.0 配置构建到 CMspark `.vibe/dist/` 五平台；CMspark `.claude`/`.grok` 及全局 Claude/Grok/Kimi/Pi/OpenCode 已刷新。五个平台 `vibe verify` 通过。

**关键决定**：刷新前暂存 `skills/` 以免 orphan symlink 清理；Pi 全局构建会改写调用目录 `AGENTS.md`。

**Next**：重启相关 Agent；CMspark `.grok/rules/` 与 hooks 是否入库另审。
<!-- handoff:end -->
