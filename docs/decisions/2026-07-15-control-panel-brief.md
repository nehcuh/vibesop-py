# VibeSOP Control Panel — 设计 Brief v2（针对 vibesop-py）

> 日期：2026-07-15
> 项目：~/Projects/vibesop-py (v8.0.0.dev0，Python SkillOS)
> 评审目的：在已有 SkillOS 之上做控制面板的可行性、形态、技术栈
> 重要：v1 brief 把这当新项目做，错了 — 90% 已存在；本 v2 在已有事实上重写

---

## 1. VibeSOP 现状（事实清单）

### 1.1 已存在（不需要重做）

| 用户 brief 项 | VibeSOP 现状 |
|---|---|
| 集中式 Skill 管理 | ✅ `vibe skills` + lifecycle (DRAFT→ACTIVE→DEPRECATED→ARCHIVED) + scope (project/global) |
| Skill 路由 / 智能识别 | ✅ `vibe route` 4-stage cascade (Explicit→Scenario+Semantic→AI Triage→Matcher)，94% 准确率 |
| 任务分解 + 编排 | ✅ `vibe orchestrate` + `decompose` + Multi-Agent Squad（自动 ≥2 角色触发） |
| 跨 Agent 技能注入 | ✅ `SkillInjector` + 5 个 adapter：claude_code / cursor / opencode / kimi_cli / pi_coding_agent |
| Provider / LLM 配置 | ⚠️ 部分 — `set_llm()` in-process API、`SKILL_LLM_CONFIG_GUIDE.md` skill-level config；缺**全局可视化**与 **per-agent** |
| MCP 管理 | ❌ 未发现（grep 无 mcp keyword in src/，需确认） |
| Role 管理（Prompt + skill 范围） | ⚠️ 部分 — Squad 角色存在，但无「角色 = Prompt + skill 子集」的显式抽象 |
| CLI 管理 + 权限 | ⚠️ 部分 — adapter layer 存在，但无「权限模板」 |
| LSP 管理 | ❌ 无 |
| Tracing / 观测 | ✅ `vibe trace` + `vibe analyze sessions`；⚠️ 无 Langfuse 集成 |
| 危险操作分析 | ✅ `vibe analyze security`（基于 AST 安全评估），⚠️ 不是离线批跑 trace |
| 任务执行入口 | ✅ CLI 完整；⚠️ 无 GUI、无全局 Spotlight |
| VibeSOP 注入到 Agent | ✅ 5 adapter 实现 |
| 自主循环 | ✅ `vibe loop`（v7.0+） |
| Skill marketplace | ✅ `vibe market` |
| Instinct learning | ✅ `vibe instinct` |
| 多 Agent 协同 | ✅ Multi-Agent Squad（同 Agent 内多角色） — ❌ 但**不是「跨 CLI Agent 二进制」的异构编排** |

### 1.2 关键架构事实

- **语言/框架**：Python 3.12+ / pydantic 2 / typer / rich / httpx / anthropic SDK / openai SDK
- **测试规模**：2,972 tests，73% coverage
- **CLI 命令**：~40 个（route/orchestrate/skills/market/loop/trace/analyze/...）
- **适配 Agent**：claude_code.py / cursor.py / opencode.py / kimi_cli.py / pi_coding_agent.py + 通用 file_based/hook_based/sdk_based
- **SkillInjector** 支持的 PlatformType：需读源码确认（推测 claude_code/cursor/opencode）
- **数据存储**：JSONL + 文件原子写，无数据库（除 cache）
- **配置目录**：推测 `~/.vibe/` 或 `.vibe/` 项目级（需读源码确认）

---

## 2. 用户 brief 在 vibesop-py 语境下的「真问题」

不是「做一个新面板」，而是「给已有 SkillOS 加 GUI 控制层 + 补少数引擎缺口」。

### 2.1 真正的缺口（按重要性）

#### A. **GUI 控制层**（核心缺口）

现状全部是 CLI。用户想要的是：
- 一个常驻 GUI（桌面 app / web dashboard / TUI 强化版），聚合 ~40 个 CLI 命令的可视化界面
- Spotlight/Alfred 风格的全局任务入口（⌘⇧Space）
- 可视化 trace viewer、skill marketplace 浏览、agent 状态总览

#### B. **Per-Agent Provider 管理**（半缺口）

`set_llm()` 是 in-process；用户想要：
- 每个外部 Agent（Claude Code / Cursor / OpenCode / Kimi CLI / Pi）独立配置 provider（OpenAI/Anthropic/本地）
- GUI 编辑 → 写入对应 Agent 的 config 文件（`~/.claude/settings.json` / `~/.cursor/mcp.json` / `~/.config/opencode/...`）
- API key 走 OS keychain

#### C. **集中式 MCP 管理**（完全缺口）

- 维护一份 MCP 主配置 → 一键 sync 到各 Agent 的 MCP 配置文件
- 不做「统一 MCP server 池」（那个是 SDK 维护地狱）

#### D. **Role 显式抽象**（半缺口）

- 把 Squad 内部角色提升为一等公民：`Role = { name, system_prompt, allowed_skills[], allowed_mcps[], default_agent }`
- GUI 可视化编辑

#### E. **Langfuse 集成**（半缺口）

- 现有 `vibe trace` 输出 JSONL；增加 Langfuse export（不自部署，接用户云）
- 离线危险分析（每日扫描 trace，便宜模型分类）

#### F. **跨 Agent 异构编排**（v1 brief 的 1.2.9，需重新评估）

- VibeSOP 现有 Squad 是「同进程内多角色」
- v1 brief 想要「Claude Code + Kimi Code + Pi 跨二进制协同」 — 这是新功能
- **关键问题**：5 个 adapter 已存在，但是否已有「spawn 子进程 + 解析输出 + 上下文传递」的 runtime？

#### G. **LSP 管理**（完全缺口，但价值存疑）

- 三方评审一致认为这是伪需求

### 2.2 v1 brief 中的「已经做了」项

- Skill 集中管理 ✅
- VibeSOP 路由 + 注入 ✅
- 任务编排 ✅
- Skill 范围/scoping ✅
- Tracing（基础）✅
- Skill 危险分析（基础）✅
- Multi-agent（基础）✅

---

## 3. 评审要点（请重点回答）

### 3.1 产品形态（最关键）

VibeSOP 是 Python CLI SkillOS。控制面板应该是什么？

候选：
- **A. Web dashboard**：FastAPI + React，浏览器访问 `localhost:14500`
- **B. Tauri 桌面 app**：Rust 壳 + React UI，调 `vibe` CLI
- **C. Textual TUI**：纯 Python 终端 UI（与现有 typer/rich 一脉相承）
- **D. Electron 桌面 app**：与 Tauri 类似但更重
- **E. 增强 CLI**：不做 GUI，用 rich 的 Live + questionary 做半图形化 CLI

请推荐 + 理由 + 与现有 Python SkillOS 的集成成本。

### 3.2 与现有 Python 架构的关系

- 控制面板是 vibesop-py 的子模块（同 monorepo）？独立仓库？
- 进程模型：spawn `vibe` CLI 子进程，还是直接 import `vibesop.agent.AgentRouter` 同进程？
- Python 是 GIL 限制下的常驻 daemon 可行性？

### 3.3 缺口优先级

A-G 七个缺口，请排 P0/P1/P2。**MVP 应包含哪些？**

### 3.4 跨 Agent 异构编排的可行性

5 个 adapter 已存在，但 v1 brief 的「Claude Code + Kimi Code + Pi 跨二进制协同」是否实际可行？
- spawn CLI + stdin/stdout JSON-lines（仅 Claude Code 有此能力）
- pty + 解析 TUI（Kimi/Pi 可能只支持 TUI）
- 文件接力（A 跑完输出文件 → B 读入）
- 哪种最现实？是否该砍掉？

### 3.5 Langfuse vs 现有 trace

`vibe trace` 已存在。是否真有必要引入 Langfuse？
- 自部署：~1.5GB 内存常驻
- 云版：隐私问题
- 替代：JSONL + 自己写 dashboard + OpenTelemetry export

### 3.6 与 v1 评审的差异

请说明：v1 评审中哪些结论因为「VibeSOP 已有 X」而**改变**了？
- v1 说「砍 orchestrator」— 但 VibeSOP 已有 Squad，是否还砍？
- v1 说「独立产品」— 但 VibeSOP 是已有项目，独立产品还成立吗？
- v1 说「Tauri」— 在 Python 生态还合适吗？

---

## 4. 期望反馈格式（同 v1）

1. 总体判断（feasibility + value）
2. 致命问题 / 阻断风险
3. 必须砍掉的功能 + MVP（在 VibeSOP 事实上重排）
4. 产品形态推荐
5. UI 草图建议
6. 技术栈（与现有 Python SkillOS 的关系）
7. 可执行路线图（3 阶段）

请直接对比 v1 评审的结论，明确指出哪些 changed / still hold。
