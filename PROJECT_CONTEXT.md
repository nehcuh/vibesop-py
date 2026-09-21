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
### 2026-09-21 S91 END · 内部介绍 7 页 PPT

**Workspace**：VibeSOP main。本会话未改 `src/`。`.pi/` 与 `.grok/hooks/` 仍是 S85 遗留脏项，未纳入。

**完成**：内部介绍叙事压成 7 页 `docs/VibeSOP-内部介绍.pptx`（误区 → 对照数字 → 五件事/四层分工 → 查看器差异 → 三亮点 → 三句话）。口径：R8 盲评未结算；委员会 0/72 主因阶段额度；记忆只承诺可检索。

**关键决定**：不把 `docs/VibeSOP-CMspark-部门分享-17页.pptx` 当本会话产物入库。macOS 无 soffice 时用 PowerPoint 导 PDF，必须按 presentation **name** 选取，不能信 `active presentation`。

**Next**：上场第 3 页口头补阶段额度与 R8 未结算。R8 盲评仍待独立盲评人。

### 2026-09-17 S86 END · Hook 无匹配横幅静默

**Workspace**：VibeSOP main。`.pi/` 与 `.grok/hooks/` 仍是 S85 工作树脏项，未纳入。

**完成**：`to_hook_response` miss 不再写用户可见 `systemMessage`。Claude/Kimi 指纹进 `additionalContext`；`grok-build` 返回 `{}`。Grok routing rule 把静默当成功 miss。已 `uv tool install --reinstall --force --no-cache .` + `vibe build grok-build --output ~/.grok`。

**关键决定**：不对 `~/.claude` 全量 build（184 extra skills）。Grok UserPromptSubmit 会丢掉 allow-hook stdout。

**Next**：重启 Grok（Claude 同理）后在 llm-safety 确认闲聊不再弹横幅。
<!-- handoff:end -->
