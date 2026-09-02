# VibeSOP

> **Version**: 8.1.3
> **同步说明**：README.md 为英文主线（面向英文社区），本文件为中文完整版。两份内容结构对齐；如有出入，以仓库实际代码为准，并请在修改时同步两份。
> 📖 [English docs](README.md)

---

# VibeSOP

> **AI 辅助开发的技能操作系统**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/Ruff-Enabled-black.svg)](https://github.com/astral-sh/ruff)
[![Coverage](https://img.shields.io/badge/Coverage-73%25-yellow.svg)]()
[![Version](https://img.shields.io/badge/Version-8.1.3-blue.svg)](https://github.com/nehcuh/vibesop-py)
[![Spec](https://img.shields.io/badge/Spec-v3.0-green.svg)](docs/skill-format-spec-v3.md)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

VibeSOP 是一个 **AI SkillOS**：把你的意图路由到正确的技能，编排多步任务，
并为你的 AI coding agent 管理完整的技能生命周期。

## 为什么选 VibeSOP？

**1. 安装一次，跨你的 AI coding agents 通用。**
一套技能定义，所有 agent 共享。Claude Code 和 Grok Build 获得完整的 hook
注入（hook 层已在 Claude Code 上端到端验证）；OpenCode、Cursor、Kimi CLI、
Pi 支持配置生成级别。

**2. 你的经验跨项目复利。**
task-memory 闭环把日常工作变成可复用资产：每个路由过的任务留下 trace →
trace 聚类成可复用模式 → 当你遇到相似问题时 `vibe recall` 直接调出过往
方案，即使是在另一个项目里。

## 快速开始

```bash
pipx install vibesop   # 或: uv tool install vibesop
vibe quickstart
```

路由演示无需 API key——quickstart 走本地轻量路由（关键词/场景匹配）。
LLM 增强路由见下文[配置 LLM API](#配置-llm-api)。

---

## 愿景

**不再记忆命令，只需表达意图。**
**不再猜测工具，智能匹配最佳。**
**不再学习平台，一次掌握所有。**

---

## 什么是 VibeSOP？

VibeSOP 是 **SkillOS（技能操作系统）**——管理技能的全生命周期：

### 技能全生命周期管理（SkillOS 定位）

- **发现与安装**：一键安装技能，自动安全审计，零配置

- **智能路由**：理解意图，从 18 个内置工作流技能 + 可安装技能包（superpowers、omx、gstack 等）中匹配最佳

- **任务编排**：复杂请求自动分解，生成串行/分组执行计划

- **生命周期管理**：启禁用、作用域隔离、质量评估、自动淘汰

- **跨平台适配**：一套技能定义，按平台生成各自配置

**VibeSOP 定位**: VibeSOP 是 SkillOS + 轻量引导执行层。它管理技能的**全生命周期**：发现 → 安装 → 路由 → 编排 → 评估 → 保留/淘汰。
简单任务由 VibeSOP 端到端完成（路由→注入→引导执行），复杂任务由 AI Agent（Claude Code, Cursor, OpenCode）接手。

📖 **阅读我们的哲学**: [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md)

🧭 **技能路由（人话 + 对照实验）**: [docs/skill-routing-explained.md](docs/skill-routing-explained.md)

🎯 **实际用例**: [docs/USE_CASES.md](docs/USE_CASES.md) (中文) | [docs/USE_CASES.en.md](docs/USE_CASES.en.md) (English) — 12 个具体场景

---

## 核心价值

### 发现 > 执行

找到正确的工具比执行更重要。AI 工具已经足够强大，真正的问题是：**找到正确的工具**。

### 编排 > 单技能

真实世界的请求往往是复合的。VibeSOP 能够分解复杂意图，编排多个技能协同工作。

### 生命周期 > 堆积

技能应该被管理，而不是无限堆积。启用/禁用、作用域隔离、质量评估、自动淘汰——让技能生态保持健康。

### 匹配 > 猜测

理解意图比记忆命令更重要。你记不住所有技能的命令，但你可以自然地表达你想做什么。

### 开放 > 封闭

开放生态比封闭系统更有价值。VibeSOP 不绑定任何平台，你可以使用任何 AI 工具。

---

## ⚡ 快速开始

### 5 分钟快速安装

```bash
# 1. 全局安装（Windows：把 %USERPROFILE%\.local\bin 加入用户 PATH）
pipx install vibesop   # 或：uv tool install vibesop

# 2. 交互式配置向导（平台配置、技能包安装）
vibe quickstart

# 3. 配置平台（Grok Build / Claude Code）
vibe build grok-build --output ~/.grok
# vibe build claude-code --output ~/.claude

# 4.（可选）配置 API Key——见下方「配置 LLM API」
export ANTHROPIC_API_KEY="sk-ant-..."

# 5. 重启 AI Agent，然后测试
vibe route "帮我调试代码"
```

✅ **完成！** VibeSOP 现在已全局可用：18 个内置工作流技能，可通过技能包扩展（`vibe install mattpocock`、`vibe install gstack` 等）。

---

### 🚀 一键安装技能（核心特性）

**从 8 个手动步骤 → 1 条命令！**

```bash
# 安装技能 - 自动配置，零学习曲线
vibe skills add tushare

# 系统自动完成：
# ✅ 检测技能类型
# ✅ 安全审计
# ✅ 智能配置路由规则
# ✅ 自动设置优先级
# ✅ 验证和同步

# 立即开始使用
vibe route "帮我获取茅台最近一年的股价"
# → AI 自动匹配到 tushare 技能（95% 置信度）
```

**对比旧流程**：
- ❌ 旧方式：30-60 分钟，8+ 手动步骤，40% 错误率
- ✅ 新方式：1-2 分钟，1 条命令，<5% 错误率

详见：[智能技能安装文档](docs/QUICKSTART_SKILL_INSTALLATION.md)

---

### 第一次使用

以下两个示例在全新安装、无 API key 下即可复现（关键词/场景层）：

```bash
# 单意图 - 路由到最佳技能
$ vibe route "帮我深入诊断并优化这个性能问题"

🔍 Routing Decision Report
Selected: builtin/deep-diagnosis-optimization (confidence: 82%)

# 会话生命周期意图
$ vibe route "wrap up the session"

🔍 Routing Decision Report
Selected: builtin/session-end (confidence: 95%)
```

> 💡 VibeSOP 路由到技能并把指令注入你的 AI Agent（Claude Code / OpenCode）的上下文，由 Agent 负责实际执行。运行 `vibe doctor` 查看哪些 Agent 可用。

```bash
# 多意图 - 自动编排
# （需要已配置 LLM 路由 + 已安装社区技能包，如 vibe install superpowers；
#  下面的技能名来自已安装的技能包）
$ vibe route "分析架构并生成测试"

🔍 Routing Summary
─────────────────────────────
Mode         Orchestrated
Steps        2
Strategy     sequential

Plan:
  1. riper-workflow — 架构分析
  2. superpowers/test — 测试生成

[✅ Confirm] [✏️ Edit] [🔀 Single skill] [📝 Skip]
```

**就这么简单！** VibeSOP 理解你的意图——无论是单一任务还是复杂多步骤请求。

---

### 配置 AI Agent 平台

安装完成后，需要部署配置到你的 AI Agent。VibeSOP 支持以下平台：

| 平台 | 命令 |
|------|------|
| **Claude Code** | `vibe build claude-code --output ~/.claude` |
| **Grok Build** | `vibe build grok-build --output ~/.grok` |
| **Kimi CLI** | `vibe build kimi-cli --output ~/.kimi-code` |
| **Pi Agent** | `vibe build pi --output .pi` |
| **OpenCode** | `vibe build opencode --output ~/.config/opencode` |
| **Cursor** | `vibe build cursor --output ~/.cursor` |

```bash
# 示例：为 Claude Code 配置
vibe build claude-code --output ~/.claude

# 输出示例：
# ✓ Build complete!
# Files created:
#   📄 ~/.claude/CLAUDE.md
#   📄 ~/.claude/rules/behaviors.md
#   📄 ~/.claude/hooks/vibesop-route.sh
#   📄 ~/.claude/skills/...
#
# Restart Claude Code to apply changes.
```

> **重要**: 部署完成后，**重启你的 AI Agent** 才能生效。

---

## 配置 LLM API

> 💡 **Agent 开发者可跳过本节**：如果你的 Agent 以 Python 库形式集成 VibeSOP（进程内），`AgentRouter.set_llm()` 可直接复用宿主 Agent 的 LLM，无需任何 API key——见 **[Agent 集成指南](docs/agent-integration.md)**。以下配置仅适用于 CLI 子进程路径（`vibe route`）。

CLI 路径下 VibeSOP 需要自己的 LLM 配置（子进程无法复用 Agent 的内部 LLM）：

**Linux / macOS:**
```bash
# Anthropic Claude（推荐）
export ANTHROPIC_API_KEY="sk-ant-..."

# 或 OpenAI
export OPENAI_API_KEY="sk-..."

# 或本地 Ollama（零成本，数据不出机器）
export VIBE_LLM_PROVIDER=ollama
export OLLAMA_BASE_URL=http://localhost:11434/v1
export OLLAMA_MODEL=qwen3:35b-a3b-mlx

# 持久化（添加到 ~/.bashrc 或 ~/.zshrc）
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.bashrc
```

**Windows:**
```cmd
# 临时设置（当前会话）
set ANTHROPIC_API_KEY=sk-ant-...
set OPENAI_API_KEY=sk-...

# 永久设置（系统环境变量）
setx ANTHROPIC_API_KEY "sk-ant-..."
setx OPENAI_API_KEY "sk-..."

# 或通过 PowerShell
$env:ANTHROPIC_API_KEY="sk-ant-..."
[System.Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY', 'sk-ant-...', 'User')
```

> **提示**: 在 PowerShell 中，环境变量设置仅对当前进程生效。使用 GUI 方式可永久设置：
> - Windows 设置 → 系统 → 关于 → 高级系统设置 → 环境变量
> - 添加用户变量 `ANTHROPIC_API_KEY` 或 `OPENAI_API_KEY`

---

## VibeSOP 解决什么问题

### 问题

AI 辅助开发工具正在爆发：
- Claude Code, Cursor, Continue.dev, Aider...
- 每个工具都有自己的命令和技能
- superpowers, mattpocock, omx 等技能包蓬勃发展
- **你不知道该用哪个**

### 解决方案

```bash
# Just say what you want (自然语言输入)
vibe route "帮我深入诊断并优化这个性能问题"
# → Routes to: builtin/deep-diagnosis-optimization (82% confidence)

vibe route "wrap up the session"
# → Routes to: builtin/session-end (95% confidence)
```

安装社区技能包（`vibe install superpowers`）后，其技能加入同一个路由池——
一套语法，全部来源。

VibeSOP:
1. **理解你的意图** (自然语言，支持中英文)
2. **找到正确的技能** (从 18 个内置技能 + 可安装技能包中选择)
3. **学习你的偏好** (越用越准确)
4. **跨 AI coding agents 通用** (Claude Code / Grok Build 走 hook 注入；
   OpenCode、Cursor、Kimi CLI、Pi 走配置生成)

---

## 核心功能

### 🚀 一键智能安装

**从 8 步手动配置 → 1 条命令，AI 自动完成所有配置**

```bash
# 安装任何技能，零配置
vibe skills add tushare
vibe skills add git-helper
vibe skills add code-reviewer

# 系统自动完成：
# ✅ 检测技能类型和元数据
# ✅ 运行安全审计
# ✅ 询问安装范围（项目/全局）
# ✅ AI 智能配置路由规则
# ✅ 自动计算优先级
# ✅ 验证和同步到平台
```

**对比传统方式**：

| 特性 | 传统方式 | VibeSOP |
|------|---------|---------|
| 安装步骤 | 8+ 手动步骤 | 1 条命令 |
| 时间成本 | 30-60 分钟 | 1-2 分钟 |
| 配置文件 | 3-4 个手动编辑 | 0 个（AI 生成） |
| 错误率 | 40% | <5% |
| 学习曲线 | 陡峭 | 平缓 |

**智能特性**：
- 🤖 **AI 配置引擎** - 分析技能描述，自动生成最优配置
- 🎯 **智能路由** - 提取关键词，自动生成正则表达式
- ⚡ **优先级计算** - 基于技能类别自动设定优先级
- 🔒 **安全审计** - 自动扫描，风险分级，交互式确认
- 💬 **友好向导** - 清晰的进度展示和错误提示

[完整文档](docs/QUICKSTART_SKILL_INSTALLATION.md) | [.skill 格式规范](docs/skill-format-spec.md)

---

### 🎯 路由准确率（~90% 内部估计）

基于 4 阶段路由级联，结合 AI 语义分析和场景知识（数据来源见
[性能指标](#性能指标)表）：

- **Stage 1**: Explicit override — exact skill ID match (e.g. `/review`), immediate dispatch
- **Stage 2**: Scenario + Semantic Index — predefined scenarios + skill semantic index
  (token-overlap + embedding), best-of-N selection
- **Stage 3**: AI Semantic Triage — LLM intent understanding（抽样验证 ~95%，
  适用于复杂/长查询）
- **Stage 4**: Matcher aggregation — keyword, TF-IDF, embedding, and fuzzy matchers run
  in parallel; highest-confidence candidate wins (not serial fallback)

Terminal states (not routing layers):
- **No Match**: all candidates below the minimum confidence threshold
- **Fallback LLM**: last-resort raw LLM routing

### 🛒 技能市场 (v5.2.0+)

发现、安装公共生态中的技能：

```bash
# 搜索 GitHub 公共技能生态（agent-skills 等 topic + curated awesome lists）
vibe market search "debug"

# 按分类查看热门技能（分类映射到 GitHub topic，按 stars 排序）
vibe market trending agent

# 从市场安装技能
vibe market install user/repo
```

搜索结果按信任级别排序：官方（内置可信包）→ 已策展（awesome list）→ 未验证来源，同级按 stars 降序。

```bash
# 安装到当前项目（仅 .vibe/skills/，全链路安全审计）
vibe market install user/repo --scope project

# 查看分类趋势
vibe market trending agent
```

**智能建议反馈环**（v8.0）：未命中查询会被本地匿名计数（仅存哈希），重复未命中时给出搜索建议；编排确认流与 Claude Code 工具钩子会学习你的重复工作流，`vibe skills suggestions` 统一收件，`vibe skills distill` 一键蒸馏为项目级技能（LLM 生成 + 全文审定 + 安全审计）。

### 📉 智能降级 (v5.2.0+)

4 级置信度降级，替代二元 fallback：

```
>= 0.6 → 自动选择    (AUTO)
>= 0.4 → 建议确认    (SUGGEST)
>= 0.2 → 降级警告    (DEGRADE)
< 0.2  → 原始 LLM   (FALLBACK)
```

所有阈值可配置。用户显式指定的技能不受降级影响。

### 🔍 主动发现 (v5.2.0+)

每次路由后自动推荐尚未使用但匹配当前工作流的技能，标记为 `[DISCOVER]`。让你持续发现生态中适合你的技能。

### 🔁 任务记忆与本能学习 (v8.0+)

VibeSOP 观测你的真实工作流，把重复模式沉淀为可复用资产：

```bash
# 语义检索过往任务轨迹（embedding 相似度，跨项目可信池可选）
vibe recall "上次怎么修的 Windows 路径 bug"

# 查看路由观测：span 追踪、回放与指标
vibe trace metrics
vibe trace replay <trace-id>

# 本能学习：从会话工具序列中挖掘技能候选
vibe analyze session
vibe instinct eval

# 技能蒸馏队列：重复任务 → 候选 → 人工 promote / dismiss
vibe skill scan-candidates
vibe skill promote <candidate-id>
```

- **Task-memory loop**：query → task_id 派生 → trace 聚类 → gold 判定 → `vibe recall` 语义召回
- **Instinct learning**：工具序列模式挖掘 + launchd 后台采集，成熟候选经 `vibe instinct eval` 晋升
- **Discovery 队列**：候选簇带评分/来源/行为标签（含 agent-echo 识别），promote 附 shadow verifier 徽章（PASS/WARN，永不阻断）
- **跨项目池**：`vibe pool` 管理可信项目，`vibe recall --cross-project` 复用其他项目沉淀的经验
- **Conversation mirror**：主会话与 sub-agent 内部过程（thinking/tool_calls/usage）全量镜像，供 dashboard 与回放

### 🧠 偏好学习

VibeSOP 会记住你的选择：

```bash
# 第一次
$ vibe route "帮我深入诊断并优化这个性能问题"
→ builtin/deep-diagnosis-optimization (82%)

# 你用了且有效
$ vibe feedback record "帮我深入诊断并优化这个性能问题" "builtin/deep-diagnosis-optimization" --correct

# 下一次
$ vibe route "帮我深入诊断并优化这个性能问题"
→ builtin/deep-diagnosis-optimization (89%) ← Boosted!
```

### 🔓 开放生态

不绑定任何平台——一套技能定义，按 agent 部署：

- ✅ Claude Code（hooks 自动注入）
- ✅ Grok Build（hooks 自动注入）
- ✅ Kimi CLI（config 自动注入）
- ✅ Pi Agent（extensions 自动注入）
- ✅ Cursor / OpenCode（配置生成）
- ✅ 任何能读 SKILL.md 的 agent（自行接线）

### 🛡️ 安全审计

每个外部技能都会经过安全扫描：

- ✅ Prompt injection detection
- ✅ Command injection detection
- ✅ Role hijacking detection
- ✅ Privilege escalation detection
- ✅ Path traversal protection

---

## 使用示例

> 标注社区技能 id 的示例（如 `mattpocock/tdd`）假设已安装对应技能包
> （`vibe install mattpocock`）。builtin 示例在全新安装上即可复现。

### 调试错误

```bash
$ vibe route "帮我深入诊断并优化这个性能问题"

✅ Matched: builtin/deep-diagnosis-optimization
   Rationale: Error detected → Use debugging workflow
```

### 代码审查

```bash
$ vibe route "review my changes before pushing"

✅ Matched: mattpocock/tdd
   Confidence: 93%
```

### 中文查询

```bash
$ vibe route "帮我重构这个函数"

✅ Matched: superpowers/refactor
   Confidence: 89%

$ vibe route "代码覆盖率太低怎么办"

✅ Matched: superpowers/tdd
   Confidence: 91%
```

### 头脑风暴

```bash
$ vibe route "I need ideas for a new feature"

✅ Matched: mattpocock/grill-with-docs
   Confidence: 87%
   Rationale: "ideas" + "new feature" → design thinking
```

---

## 谁应该使用 VibeSOP？

### 👨‍💻 开发者

你正在使用 AI 辅助开发工具，但：

- ❌ 记不住那么多命令
- ❌ 不知道哪个技能最适合当前场景
- ❌ 想要在不同工具间切换而不失去技能

**VibeSOP 为你解决这些问题！**

### 🏢 团队

你们正在采用 AI 辅助开发，但：

- ❌ 团队成员使用不同的技能
- ❌ 缺乏统一的技能管理
- ❌ 难以跟踪和分享最佳实践

**VibeSOP 提供统一的技能管理和路由！**

### 🌐 开源社区

你正在维护 AI 辅助开发工具，但：

- ❌ 技能格式不统一
- ❌ 难以集成外部技能
- ❌ 缺乏跨平台支持

**VibeSOP 提供标准的 SKILL.md 格式和跨平台支持！**

---

## CLI 命令参考

### 核心命令

```bash
# Route query to best skill
vibe route "<query>"

# Orchestrate complex multi-intent query
vibe orchestrate "<query>"

# Decompose query into sub-tasks (without routing)
vibe decompose "<query>"

# List all available skills
vibe skills available

# Show skill details
vibe skills info <skill-id>

# Install skill pack
vibe install <url-or-name>

# Check environment
vibe doctor
```

### 技能管理

```bash
# List installed skills
vibe skills list

# Show all skills including builtins
vibe skills available

# Show detailed skill information
vibe skills info <skill-id>

# Install from URL or name
vibe install mattpocock
vibe install https://github.com/user/skills

# Sync skills to platform
vibe skills sync claude-code
```

### 跨域工作流 (v7.0)

跨域工作流把多个技能编排成一条完整的开发流水线（如"诊断 → 实现 → 验证 → 审查"）。VibeSOP 内置的 `prompt-chain-validator` 工作流为本仓库验证过的"动态提示词链 + 容器端到端验证"模式：

```bash
# 列出所有跨域工作流
vibe workflows list-workflows

# 查看工作流详情
vibe workflows show prompt-chain-validator

# 一站式：诊断 → 生成分阶段提示词 → 容器验证
vibe prompt-chain run "为 VibeSOP 增加 Multi-Agent Squad 能力"

# 分步执行
vibe prompt-chain diagnose "Multi-Agent Squad" --files="src/core/*.py"
vibe prompt-chain generate "Multi-Agent Squad" --output ./prompts
vibe prompt-chain validate --container orbstack --json
```

`vibe prompt-chain generate` 输出 7 个 `.md` 提示词文件（Phase 0 扇出诊断 → Phase 1-5 分阶段实现 → Final 端到端验证），每个文件可独立喂给 Claude Code。`vibe prompt-chain validate` 在 Linux 容器（orbstack/docker/lima 自动检测，或 `--container local` 走宿主机）中跑完整验证流水线，输出 JSON 报告。

### 反馈收集

```bash
# Record correct routing
vibe feedback record "<query>" "<skill>" --correct

# Record incorrect routing
vibe feedback record "<query>" "<skill>" --wrong "<actual-skill>"

# View feedback report
vibe feedback report
```

### 任务记忆与观测 (v8.0+)

```bash
# 语义检索过往任务轨迹
vibe recall "<query>"
vibe recall "<query>" --cross-project   # 跨可信项目池召回

# 路由观测：指标与回放
vibe trace metrics
vibe trace replay <trace-id>

# 本能学习：工具序列挖掘与晋升
vibe analyze session
vibe instinct eval
vibe instinct status

# 技能蒸馏队列（候选 → 人工 promote/dismiss，附 shadow verifier 徽章）
vibe skill scan-candidates
vibe skill promote <candidate-id>
vibe skill dismiss <candidate-id>

# 跨项目可信池管理
vibe pool add / list / remove
```

### 会话智能路由

> **⚠️ 默认开启**：会话智能追踪默认**开启**（`routing.session_aware: true`），自动记录会话状态并支持多轮对话重路由。
>
> **为什么可以关闭？**
> - **性能**：部分用户希望零开销
> - **隐私**：不希望记录工具使用历史
> - **控制**：完全由用户决定是否启用
>
> 如需关闭：
> ```bash
> vibe config set routing.session_aware false
> ```

```bash
# Enable tracking (Claude Code)
vibe session enable-tracking

# Record tool usage (manual)
vibe session record-tool --tool "read" --skill "systematic-debugging"

# Check for re-routing suggestions
vibe session check-reroute "design new architecture" --skill "systematic-debugging"

# View session summary
vibe session summary
```

完整命令参考: [docs/user/CLI_REFERENCE.md](docs/user/CLI_REFERENCE.md)

---

## 配置

### 项目级配置

创建 `.vibe/config.toml`：

```yaml
# .vibe/config.toml
platform: claude-code

routing:
  min_confidence: 0.6
  enable_ai_triage: true
  enable_embedding: false
  max_candidates: 3
  confirmation_mode: ambiguous_only  # ambiguous_only（默认）| always | never
  keyword_match_max_chars: 5  # max chars for keyword routing (0=always LLM, 200=always keyword)

  # Degradation: confidence-gated layered fallback (v5.2.0)
  degradation_enabled: true
  degradation_auto_threshold: 0.6    # >= this = auto-select
  degradation_suggest_threshold: 0.4 # >= this but < auto = suggest
  degradation_degrade_threshold: 0.2 # >= this but < suggest = degrade
  degradation_fallback_always_ask: true  # ask user before raw LLM

security:
  threat_level: medium
  scan_external: true

skills:
  namespaces:
    - builtin
    - mattpocock
    - superpowers
    - omx
```

#### 用户确认模式

默认 `ambiguous_only`：置信度 ≥ `auto_select_threshold`（0.6）的路由自动放行（阈值默认与降级梯度 AUTO 档一致，但二者独立可调），只在置信度不足或多意图编排存在分歧时弹出确认：

```bash
$ vibe route "帮我 review 代码"
╭────────── 🔍 Routing Decision Report ──────────╮
│ Selected: mattpocock/tdd (confidence: 87%)      │
│ ...                                            │
╰────────────────────────────────────────────────╯
（≥ 0.6：自动选择，直接继续）

$ vibe route "这个查询有点含糊"
How would you like to proceed?
  ✅ Confirm selected skill
  🔀 Choose a different skill
  📝 Skip skill, use raw LLM
```

调整方式：

- **每次都确认**：`routing.confirmation_mode = "always"`（旧版默认值）
- **临时跳过**：`vibe route "query" --yes` 或 `-y`
- **完全关闭**：在 `~/.vibe/config.toml` 中设置 `routing.confirmation_mode = "never"`

> 💡 **为什么改默认**：`always` 与 PHILOSOPHY 第五信条「延续 > 启动 / 瓶颈在人不在系统」相抵触——每条路由都要人点一次头，系统本身就成了瓶颈。`ambiguous_only` 把人工关口保留给真正模糊的决策。

### 全局配置

创建 `~/.vibe/config.toml`：

```yaml
# ~/.vibe/config.toml
default_platform: claude-code
llm_provider: anthropic  # or openai

routing:
  enable_ai_triage: true
  use_cache: true

preferences:
  learning_enabled: true
```

---

## 集成

### Claude Code

```bash
vibe build claude-code --output ~/.claude
# Shell hooks auto-trigger routing on UserPromptSubmit
```

### Kimi CLI

```bash
vibe build kimi-cli --output ~/.kimi-code
# Config hooks auto-trigger routing via config.toml
```

### Pi Agent

```bash
vibe build pi --output .pi
# TypeScript extensions auto-trigger routing
```

### OpenCode

```bash
vibe build opencode --output ~/.config/opencode
# Manual: source ~/.config/opencode/vibesop-env.sh && opencode
```

### Grok Build

```bash
vibe build grok-build --output ~/.grok
# Shell hooks auto-trigger routing on UserPromptSubmit
# (also collects PostToolUse tool sequences)
```

### Workflow Engine (v6.2.0+)

VibeSOP 的动态工作流引擎支持 6 种编排模式，自动分类用户意图并选择最佳执行策略。

**6 种工作流模式：**

| 模式 | 用途 |
|-------------|--------------|
| `SEQUENTIAL` | 线性依赖链 |
| `PARALLEL` | 独立并发任务 |
| `FAN_OUT` | 一对多分发 |
| `ADVERSARIAL` | 独立验证 |
| `LOOP_UNTIL_DRY` | 迭代到无新发现 |
| `TOURNAMENT` | 最佳选择 |

```bash
# 强制指定工作流模式
vibe route --pattern fan_out "分析架构并优化性能"

# 启用对抗式验证
vibe route --verify "重构认证模块"
```

**平台支持：**

| Platform | Workflow | Native Parallel | Trigger |
|----------|----------|-----------------|---------|
| Claude Code | ✅ | ✅ Sub-agents | Auto (hooks) |
| Grok Build | ✅ | ⚠️ Serial only | Auto (hooks) |
| Kimi CLI | ✅ | ⚠️ Serial only | Auto (config) |
| Pi Agent | ✅ | ⚠️ Serial only | Auto (extensions) |
| OpenCode | ✅ | ⚠️ Serial only | Manual |

---

## 架构

VibeSOP (v5.5.0+) introduces a **3-pillar architecture** (enhanced with Dynamic Workflow Engine):

| Pillar | Purpose | Artifacts |
|--------|---------|-----------|
| **The Spec** | Canonical SKILL.md v3.0 format | `spec/models.py`, 29 fields, `SpecValidator` |
| **The Reference** | 3 integration patterns | File-based, Hook-based, SDK-based adapters |
| **The Conformance Suite** | Any platform can verify compliance | 85 tests, `vibe spec conformance --all` |

```
┌─────────────────────────────────────────────────┐
│               AI Agent (执行层)                  │
│    Claude Code / Cursor / OpenCode / etc.        │
└────────────────────┬────────────────────────────┘
                     │ 执行技能
┌────────────────────▼────────────────────────────┐
│              VibeSOP SkillOS                     │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │         CLI / Agent Runtime Layer         │   │
│  │   vibe route │ orchestrate │ skill mgmt   │   │
│  └────────────────────┬─────────────────────┘   │
│                       │                         │
│  ┌────────────────────▼─────────────────────┐   │
│  │          UnifiedRouter (路由层)           │   │
│  │   4-Stage Cascade:                        │   │
│  │   Explicit → Scenario+Index → AI Triage   │   │
│  │   → Matcher Aggregation → Fallback        │   │
│  └────────────────────┬─────────────────────┘   │
│                       │                         │
│  ┌────────────────────▼─────────────────────┐   │
│  │       TaskOrchestrator (编排层)           │   │
│  │   多意图检测 → 任务分解 → 执行计划生成    │   │
│  └────────────────────┬─────────────────────┘   │
│                       │                         │
│  ┌────────────────────▼─────────────────────┐   │
│  │      Skill Lifecycle Manager (管理层)      │   │
│  │   启禁用 │ 作用域 │ 质量评估 │ 保留淘汰   │   │
│  └────────────────────┬─────────────────────┘   │
│                       │                         │
│  ┌────────────────────▼─────────────────────┐   │
│  │        Integration Layer (适配层)          │   │
│  │   Claude Code │ OpenCode │ Kimi CLI       │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

详细架构文档: [docs/architecture/](docs/architecture/)

---

## 文档

**📚 完整文档索引**: [docs/INDEX.md](docs/INDEX.md)

### 核心文档

- [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md) - 核心哲学和使命
- [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) - 系统架构
- [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) - 项目背景
- [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) - 项目状态

### 用户指南

- **🆕 [docs/SKILLS_GUIDE.md](docs/SKILLS_GUIDE.md)** - 技能生态系统完整指南
  - 18 个内置技能 + 社区技能包详解（superpowers、omx、gstack）
  - 4 阶段路由级联
  - 优先级决策机制
  - 手动切换技能
- **🆕 [docs/agent-integration.md](docs/agent-integration.md)** - Agent 进程内集成指南
  - `AgentRouter.set_llm()` 复用宿主 Agent 的 LLM，无需 API key
  - 多轮对话 reroute / 置信度感知
- [docs/QUICKSTART_USERS.md](docs/QUICKSTART_USERS.md) - 用户快速入门
- [docs/QUICKSTART_DEVELOPERS.md](docs/QUICKSTART_DEVELOPERS.md) - 开发者快速入门
- [docs/user/CLI_REFERENCE.md](docs/user/CLI_REFERENCE.md) - CLI 命令参考
- [docs/EXTERNAL_SKILLS_GUIDE.md](docs/EXTERNAL_SKILLS_GUIDE.md) - 外部技能开发

### 技能包指南

- **[docs/OMX_GUIDE.md](docs/OMX_GUIDE.md)** - oh-my-codex (OMX) 完整指南
  - deep-interview, ralph, ralplan, team, ultrawork, autopilot, ultraqa
  - 使用场景和最佳实践

### 开发者文档

- [docs/dev/CONTRIBUTING.md](docs/dev/CONTRIBUTING.md) - 贡献指南
- [docs/ROADMAP.md](docs/ROADMAP.md) - 路线图
- [docs/CODE_OF_CONDUCT.md](docs/CODE_OF_CONDUCT.md) - 行为准则
- [docs/SECURITY.md](docs/SECURITY.md) - 安全政策

---

## 性能指标

### 路由准确率

| 指标 | 值 | 说明 |
|-----------|---------|----------|
| **总体准确率** | **~90%** | 基于内部测试集估算，非标准化基准 |
| **AI Triage 准确率** | **~95%** | 基于抽样验证估算 |
| **场景匹配准确率** | **~90%** | 基于关键词匹配估算 |
| **语义歧义准确率** | **~90%** | 基于 LLM 评估估算 |

### 响应时间

| 操作 | 时间 | 说明 |
|--------------|----------|----------|
| **简单路由** (缓存命中) | ~10-50ms | P50 估算值，受硬件影响 |
| **复杂路由** (多层) | ~200-300ms | 含 LLM Triage |
| **AI Triage** | ~200-300ms | 取决于 LLM 提供商和网络 |

> ⚠️ **性能声明说明**：以上数据为设计目标和内部估算值，非标准化基准测试结果。实际性能因硬件、网络、LLM 提供商和技能数量而异。标准化基准测试套件正在建设中。

---

## 对比

### 与其他工具对比

| Feature | VibeSOP | Cursor | Continue.dev | Aider |
|---------|---------|--------|--------------|-------|
| **Routing** | 4-stage cascade routing | Built-in commands | Extension-based | CLI flags |
| **Orchestration** | Multi-skill composition | No | No | No |
| **Lifecycle Mgmt** | Enable/disable, scope, evaluate | No | No | No |
| **Skills** | 18 内置 + 社区技能包 | Built-in features | Community extensions | Built-in workflows |
| **Learning** | Preference learning | Fixed | No | No |
| **Cross-Platform** | ✅ Per-agent config generation | ❌ Cursor only | ❌ Continue only | ❌ Aider only |
| **Open Ecosystem** | ✅ Any SKILL.md | ❌ Closed | ⚠️ Extension API | ❌ Closed |
| **Security Audit** | ✅ Before loading skills | N/A | ⚠️ User discretion | N/A |

### 为什么选择 VibeSOP？

1. **不绑定单一工具** — 从 Cursor 切换到 Claude Code？你的技能跟着你走
2. **发现你不知道存在的技能** — "我能做什么？" → `vibe skills available`
3. **越来越聪明** — 记住什么对你有效
4. **开放可扩展** — 用简单的 markdown 文件创建自己的技能

---

## 开发

```bash
# Type checking
uv run basedpyright

# Linting
uv run ruff check

# Formatting
uv run ruff format

# Testing (fast, parallel, ~30s)
make test-fast

# Full test suite with coverage (~4 min)
uv run pytest

# Test coverage
uv run pytest --cov=src/vibesop --cov-report=html
```

---

## 路线图

已完成里程碑（v4.0–v6.2 等）的完整清单见 [docs/ROADMAP.md](docs/ROADMAP.md)（历史版本记录）。

详见: [docs/ROADMAP.md](docs/ROADMAP.md) | [version_05.md ADR](docs/archive/version_05.md)

---

## 许可证

MIT License - see [LICENSE](LICENSE) file.

---

## 致谢

VibeSOP 站在巨人的肩膀上，整合了社区优秀的 AI 工程实践：

### 🔗 社区项目集成

VibeSOP 内置了对以下社区技能包的支持，并提供统一的智能路由：

- **[mattpocock/skills](https://github.com/mattpocock/skills)** by [@mattpocock](https://github.com/mattpocock)
  - 🎯 **定位**: 高质量工程技能 — TDD、诊断、架构改进、代码审查
  - 📦 **技能数**: 6+ 个技能 (tdd, diagnose, grill-with-docs, improve-codebase-architecture, handoff, grill-me)
  - 🎨 **特点**: `.claude-plugin/plugin.json` 注册表格式，专注技能设计范式
  - ⚡ **默认安装**: `vibe install` 自动安装

- **[superpowers](https://github.com/obra/superpowers)** by [@obra](https://github.com/obra)
  - 🎯 **定位**: 基础开发工作流 - TDD、重构、调试、优化
  - 📦 **技能数**: 7 个技能 (tdd, refactor, debug, optimize, architect, review, brainstorm)
  - 🎨 **特点**: 开发最佳实践，red-green-refactor 循环
  - 💡 **适用**: 日常开发任务，个人工作流优化

- **[oh-my-codex (OMX)](https://github.com/Yeachan-Heo/oh-my-codex)** by [@Yeachan-Heo](https://github.com/Yeachan-Heo)
  - 🎯 **定位**: 高级工程方法论 - 结构化思维和系统化执行
  - 📦 **技能数**: 7 个技能 (deep-interview, ralph, ralplan, team, ultrawork, autopilot, ultraqa)
  - 🎨 **特点**: 需求澄清、持久执行、共识规划、多代理并行
  - 📖 **文档**: [OMX_GUIDE.md](docs/OMX_GUIDE.md) (完整使用指南)

- **[gstack](https://github.com/anthropics/gstack)** by [@brandonrobertz](https://github.com/brandonrobertz)
  - 🎯 **定位**: 虚拟工程团队 - 工程技能和浏览器自动化
  - 📦 **技能数**: 19 个技能 (review, qa, ship, office-hours, browse, etc.)
  - 🎨 **特点**: 角色-based 技能 (产品、工程、设计、QA)
  - 💡 **适用**: 需显式安装 `vibe install gstack`（非默认）

### 🏗️ 核心技术基础

- **[Claude Code](https://github.com/anthropics/claude-code)** by Anthropic
  - 📋 **贡献**: SKILL.md 规范标准
  - 🔧 **集成**: VibeSOP 完全兼容 SKILL.md 规范
  - 📚 **文档**: [SKILL.md Specification](docs/EXTERNAL_SKILLS_GUIDE.md)

### 🎯 VibeSOP 独特价值

VibeSOP 不仅仅是这些技能包的集合，而是一个**统一的智能路由层**：

- 🧠 **智能路由** (~90% 内部估计) - 自动选择最合适的技能
- 🔄 **统一管理** - 一个工具管理所有技能包
- 🛡️ **安全审计** - 所有外部技能经过安全扫描
- 📚 **跨平台** - 在 Claude Code、Cursor、Continue.dev 等平台使用
- 🎓 **偏好学习** - 记住你的选择，越来越准确

### 📊 技能选择指南

**详细对比**: 请参考 [OMX_GUIDE.md](docs/OMX_GUIDE.md#与其他技能包的区别)

```
需求不明确？ → OMX deep-interview (深度澄清)
TDD 开发？ → mattpocock/tdd (red-green-refactor)
代码审查？ → mattpocock/grill-me (深度审视)
调试错误？ → mattpocock/diagnose (系统化诊断)
架构改进？ → mattpocock/improve-codebase-architecture (领域驱动重构)
```

---

> 📖 [English docs](README.md)
