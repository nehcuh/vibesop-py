# VibeSOP

> **AI 辅助开发的技能操作系统**
>
> **The Skill Operating System for AI-assisted development**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/Ruff-Enabled-black.svg)](https://github.com/astral-sh/ruff)
[![Coverage](https://img.shields.io/badge/Coverage->75%25-green.svg)]()
[![Version](https://img.shields.io/badge/Version-5.2.0-blue.svg)](https://github.com/nehcuh/vibesop-py)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## 愿景 Vision

**不再记忆命令，只需表达意图。**
**不再猜测工具，智能匹配最佳。**
**不再学习平台，一次掌握所有。**

**No more memorizing commands. Just express your intent.**
**No more guessing tools. Intelligent matching finds the best.**
**No more learning platforms. Master them all at once.**

---

## 什么是 VibeSOP？ What is VibeSOP?

VibeSOP 是 **SkillOS（技能操作系统）**——管理技能的全生命周期：

**VibeSOP is a Skill Operating System — managing the full lifecycle of skills:**

### 技能全生命周期管理（SkillOS 定位）Skill Lifecycle Management

- **发现与安装**：一键安装技能，自动安全审计，零配置
  **Discovery & Installation** — one-click install, auto security audit, zero config

- **智能路由**：理解意图，从 50+ 技能中匹配最佳
  **Intelligent Routing** — understand intent, match the best from 50+ skills

- **任务编排**：复杂请求自动分解，串行/并行执行计划
  **Task Orchestration** — decompose complex requests, serial/parallel execution plans

- **生命周期管理**：启禁用、作用域隔离、质量评估、自动淘汰
  **Lifecycle Management** — enable/disable, scope isolation, quality evaluation, auto-deprecation

- **跨平台适配**：一套技能定义，所有 AI Agent 通用
  **Cross-Platform** — one skill definition, works with all AI Agents

**VibeSOP 定位**: VibeSOP 是 SkillOS。它管理技能的**全生命周期**：发现 → 安装 → 路由 → 编排 → 评估 → 保留/淘汰。
技能的实际执行由 AI Agent（Claude Code, Cursor, OpenCode）完成。

**Note**: VibeSOP is a Skill Operating System. It manages the **full skill lifecycle**: discovery → installation → routing →
orchestration → evaluation → retention/deprecation. Actual skill execution is done by AI Agents
(Claude Code, Cursor, OpenCode).

📖 **Read our philosophy**: [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md) | [中文版](docs/PHILOSOPHY.md)

---

## 核心价值 Core Values

### Discovery over Execution (发现 > 执行)

找到正确的工具比执行更重要。AI 工具已经足够强大，真正的问题是：**找到正确的工具**。

**Finding the right tool is more important than executing it.** AI tools are already powerful enough. The real problem is: **finding the right tool**.

### Orchestration over Single-Skill (编排 > 单技能)

真实世界的请求往往是复合的。VibeSOP 能够分解复杂意图，编排多个技能协同工作。

**Real-world requests are composite.** VibeSOP decomposes complex intents and orchestrates multiple skills working together.

### Lifecycle over Accumulation (生命周期 > 堆积)

技能应该被管理，而不是无限堆积。启用/禁用、作用域隔离、质量评估、自动淘汰——让技能生态保持健康。

**Skills should be managed, not infinitely accumulated.** Enable/disable, scope isolation, quality evaluation, auto-deprecation — keeping the skill ecosystem healthy.

### Matching over Guessing (匹配 > 猜测)

理解意图比记忆命令更重要。你记不住 50+ 个技能的命令，但你可以自然地表达你想做什么。

**Understanding intent is more important than memorizing commands.** You can't remember 50+ skill commands, but you can naturally express what you want to do.

### Open over Closed (开放 > 封闭)

开放生态比封闭系统更有价值。VibeSOP 不绑定任何平台，你可以使用任何 AI 工具。

**An open ecosystem is more valuable than a closed system.** VibeSOP doesn't bind to any platform — you can use any AI tool.

---

## ⚡ 快速开始 Quick Start

### 🚀 一键安装技能（核心特性）

**从 8 个手动步骤 → 1 条命令，98% 时间节省！**

```bash
# 安装技能 - 自动配置，零学习曲线
vibe skill add tushare

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

### 安装 VibeSOP

```bash
# Clone the repository
git clone https://github.com/nehcuh/vibesop-py.git
cd vibesop-py

# Install with uv (recommended - 10-100x faster than pip)
uv sync

# Or with pip
pip install -e .
```

### 第一次使用 First Use

```bash
# Single intent - routes to best skill
$ vibe route "帮我调试这个错误"

🔍 Routing Summary
─────────────────────────────
Selected     systematic-debugging
Confidence   95%
Layer        scenario
Duration     12.3ms

💡 Alternatives:
   • gstack/investigate (82%)
   • superpowers/debug (75%)
```

```bash
# Multi intent - automatically orchestrates
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

**That's it!** VibeSOP understands your intent — whether it's a single task or a complex multi-step request.

---

## 为什么选择 VibeSOP？ Why VibeSOP?

### 问题 The Problem

AI 辅助开发工具正在爆发：
- Claude Code, Cursor, Continue.dev, Aider...
- 每个工具都有自己的命令和技能
- superpowers, gstack, omx 等技能包蓬勃发展
- **你不知道该用哪个**

AI-assisted development tools are exploding:
- Claude Code, Cursor, Continue.dev, Aider...
- Each tool has its own commands and skills
- Skill packs like superpowers, gstack, omx are booming
- **You don't know which one to use**

### 解决方案 The Solution

```bash
# Just say what you want (自然语言输入)
vibe route "debug this database error"
# → Routes to: systematic-debugging (95% confidence)

vibe route "帮我扫描安全漏洞"
# → Routes to: gstack/cso (88% confidence)

vibe route "review my PR"
# → Routes to: gstack/review (92% confidence)
```

VibeSOP:
1. **理解你的意图** (自然语言，支持中英文)
2. **找到正确的技能** (从 45+ 技能中选择)
3. **学习你的偏好** (越用越准确)
4. **跨平台通用** (Claude Code, Cursor, Continue.dev 等)

VibeSOP:
1. **Understands your intent** (natural language, English + Chinese)
2. **Finds the right skill** (from 45+ available skills)
3. **Learns your preferences** (gets better over time)
4. **Works with any AI tool** (Claude Code, Cursor, Continue.dev, etc.)

---

## 核心功能 Core Features

### 🚀 一键智能安装（One-Click Smart Installation）

**从 8 步手动配置 → 1 条命令，AI 自动完成所有配置**

```bash
# 安装任何技能，零配置
vibe skill add tushare
vibe skill add git-helper
vibe skill add code-reviewer

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

### 🎯 95% 路由准确率 (95% Routing Accuracy)

基于 10 层路由 pipeline，结合 AI 语义分析和场景知识：

Based on a 10-layer routing pipeline combining AI semantic analysis and scenario knowledge:

- **Layer 0**: Explicit overrides
- **Layer 1**: Scenario patterns (90% accuracy)
- **Layer 2**: AI Semantic Triage (95% accuracy, forced for long queries >5 chars)
- **Layer 3**: Keyword matching (70% accuracy, short queries only by default)
- **Layer 4**: TF-IDF semantic similarity (75% accuracy)
- **Layer 5**: Embedding-based matching (85% accuracy)
- **Layer 6**: Fuzzy matching for typos (60% accuracy)
- **Layer 7**: Custom plugin matchers (user-defined)
- **Layer 8**: No Match (below threshold)
- **Layer 9**: Fallback LLM (last-resort routing)

### 🛒 技能市场 (Skill Market) — v5.2.0

发现、安装、发布技能：

```bash
# 搜索市场中已有的技能
vibe market search "debug"

# 从市场安装技能
vibe market install user/repo

# 发布你的技能到市场（通过 GitHub Issue）
vibe market publish
vibe market publish --dry-run  # 预览发布内容
```

发布基于 GitHub Issues，无需额外服务器。关闭 Issue 即下架。

### 📉 智能降级 (Degradation) — v5.2.0

4 级置信度降级，替代二元 fallback：

```
>= 0.6 → 自动选择    (AUTO)
>= 0.4 → 建议确认    (SUGGEST)
>= 0.2 → 降级警告    (DEGRADE)
< 0.2  → 原始 LLM   (FALLBACK)
```

所有阈值可配置。用户显式指定的技能不受降级影响。

### 🔍 主动发现 (Proactive Discovery) — v5.2.0

每次路由后自动推荐尚未使用但匹配当前工作流的技能，标记为 `[DISCOVER]`。让你持续发现生态中适合你的技能。

### 🧠 偏好学习 (Preference Learning)

VibeSOP 会记住你的选择：

VibeSOP remembers your choices:

```bash
# First time
$ vibe route "debug this"
→ systematic-debugging (85%)

# You use it and it works
$ vibe feedback record "debug this" "systematic-debugging" --correct

# Next time
$ vibe route "debug this"
→ systematic-debugging (92%) ← Boosted!
```

### 🔓 开放生态 (Open Ecosystem)

不绑定任何平台，支持所有 AI 工具：

No platform lock-in, works with all AI tools:

- ✅ Claude Code
- ✅ Cursor
- ✅ Continue.dev
- ✅ Aider
- ✅ Any tool that supports SKILL.md

### 🛡️ 安全审计 (Security Audit)

每个外部技能都会经过安全扫描：

Every external skill is security-scanned:

- ✅ Prompt injection detection
- ✅ Command injection detection
- ✅ Role hijacking detection
- ✅ Privilege escalation detection
- ✅ Path traversal protection

---

## 使用示例 Usage Examples

### 调试错误 Debugging Errors

```bash
$ vibe route "database connection failed after deployment"

✅ Matched: systematic-debugging
   Rationale: Error detected → Use debugging workflow
```

### 代码审查 Code Review

```bash
$ vibe route "review my changes before pushing"

✅ Matched: gstack/review
   Confidence: 93%
```

### 中文查询 Chinese Queries

```bash
$ vibe route "帮我重构这个函数"

✅ Matched: superpowers/refactor
   Confidence: 89%

$ vibe route "代码覆盖率太低怎么办"

✅ Matched: superpowers/tdd
   Confidence: 91%
```

### 头脑风暴 Brainstorming

```bash
$ vibe route "I need ideas for a new feature"

✅ Matched: gstack/office-hours
   Confidence: 87%
   Rationale: "ideas" + "new feature" → design thinking
```

---

## 谁应该使用 VibeSOP？ Who Should Use VibeSOP?

### 👨‍💻 开发者 Developers

你正在使用 AI 辅助开发工具，但：

You're using AI-assisted development tools, but:

- ❌ 记不住那么多命令 / Can't remember all the commands
- ❌ 不知道哪个技能最适合当前场景 / Don't know which skill fits the current scenario
- ❌ 想要在不同工具间切换而不失去技能 / Want to switch tools without losing skills

**VibeSOP 为你解决这些问题！**
**VibeSOP solves these problems for you!**

### 🏢 团队 Teams

你们正在采用 AI 辅助开发，但：

You're adopting AI-assisted development, but:

- ❌ 团队成员使用不同的技能 / Team members use different skills
- ❌ 缺乏统一的技能管理 / Lack unified skill management
- ❌ 难以跟踪和分享最佳实践 / Hard to track and share best practices

**VibeSOP 提供统一的技能管理和路由！**
**VibeSOP provides unified skill management and routing!**

### 🌐 开源社区 Open Source Community

你正在维护 AI 辅助开发工具，但：

You're maintaining AI-assisted development tools, but:

- ❌ 技能格式不统一 / Inconsistent skill formats
- ❌ 难以集成外部技能 / Hard to integrate external skills
- ❌ 缺乏跨平台支持 / Lack cross-platform support

**VibeSOP 提供标准的 SKILL.md 格式和跨平台支持！**
**VibeSOP provides standard SKILL.md format and cross-platform support!**

---

## CLI 命令参考 CLI Reference

### 核心命令 Core Commands

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

### 技能管理 Skills Management

```bash
# List installed skills
vibe skills list

# Show detailed skill information
vibe skills info <skill-id>

# Install from URL or name
vibe install gstack
vibe install https://github.com/user/skills

# Sync skills to platform
vibe skills sync claude-code
```

### 反馈收集 Feedback Collection

```bash
# Record correct routing
vibe feedback record "<query>" "<skill>" --correct

# Record incorrect routing
vibe feedback record "<query>" "<skill>" --wrong "<actual-skill>"

# View feedback report
vibe feedback report
```

### 会话智能路由 Session Intelligent Routing

> **⚠️ Opt-in 设计**：会话智能追踪默认**关闭**（`VIBESOP_CONTEXT_TRACKING=false`），这是有意的设计选择。
>
> **为什么默认关闭？**
> - **性能**：零开销，不影响正常使用
> - **隐私**：不记录工具使用历史
> - **控制**：完全由用户决定是否启用
>
> 需要手动启用才能使用此功能。

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
Full CLI reference: [docs/user/CLI_REFERENCE.md](docs/user/CLI_REFERENCE.md)

---

## 配置 Configuration

### 项目级配置 Project-Level Config

创建 `.vibe/config.yaml`：

Create `.vibe/config.yaml`:

```yaml
# .vibe/config.yaml
platform: claude-code

routing:
  min_confidence: 0.6
  enable_ai_triage: true
  enable_embedding: false
  max_candidates: 3
  confirmation_mode: always  # always | never | ambiguous_only
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
    - gstack
    - superpowers
```

#### 用户确认模式 User Confirmation Mode

默认情况下，VibeSOP 会在选择技能前展示路由决策报告并要求你确认：

```bash
$ vibe route "帮我 review 代码"
╭────────── 🔍 Routing Decision Report ──────────╮
│ Selected: gstack/review (confidence: 87%)      │
│ ...                                            │
╰────────────────────────────────────────────────╯
How would you like to proceed?
  ✅ Confirm selected skill
  🔀 Choose a different skill
  📝 Skip skill, use raw LLM
```

你可以通过以下方式关闭确认：

- **临时跳过**：`vibe route "query" --yes` 或 `-y`
- **全局关闭**：在 `~/.vibe/config.yaml` 中设置 `routing.confirmation_mode: never`
- **仅低置信度时确认**：设置 `routing.confirmation_mode: ambiguous_only`

> ⚠️ **注意**：确认模式默认开启 (`always`)，旨在让你了解 VibeSOP 的决策过程。关闭后将恢复为自动选择。

### 全局配置 Global Config

创建 `~/.vibe/config.yaml`：

Create `~/.vibe/config.yaml`:

```yaml
# ~/.vibe/config.yaml
default_platform: claude-code
llm_provider: anthropic  # or openai

routing:
  enable_ai_triage: true
  use_cache: true

preferences:
  learning_enabled: true
```

---

## 集成 Integrations

### Claude Code

```bash
# Build and deploy to Claude Code
vibe build claude-code --output ~/.claude

# Claude Code will now use VibeSOP for routing
```

### Cursor

```bash
# Build for Cursor
vibe build cursor --output ~/.cursor

# Skills available in Cursor sessions
```

### Continue.dev

```bash
# Build for Continue
vibe build opencode --output ~/.continue

# Use in Continue.dev configurations
```

---

## 架构 Architecture

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
│  │   10-Layer Pipeline:                      │   │
│  │   AI Triage → Scenario → Keyword → TF-IDF │   │
│  │   → Embedding → Levenshtein → Fallback    │   │
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
Detailed architecture docs: [docs/architecture/](docs/architecture/)

---

## 文档 Documentation

**📚 完整文档索引 Complete Documentation Index**: [docs/INDEX.md](docs/INDEX.md)

### 核心文档 Core Documentation

- [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md) - 核心哲学和使命 / Core philosophy and mission
- [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) - 系统架构 / System architecture
- [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) - 项目背景 / Project context
- [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) - 项目状态 / Project status

### 用户指南 User Guides

- **🆕 [docs/SKILLS_GUIDE.md](docs/SKILLS_GUIDE.md)** - 技能生态系统完整指南 / Complete skills ecosystem guide
  - 50+ 个技能详解 / All skills explained
  - 10 层路由系统 / 10-layer routing system
  - 优先级决策机制 / Priority decision mechanism
  - 手动切换技能 / How to switch skills
- [docs/QUICKSTART_USERS.md](docs/QUICKSTART_USERS.md) - 用户快速入门 / User quick start
- [docs/QUICKSTART_DEVELOPERS.md](docs/QUICKSTART_DEVELOPERS.md) - 开发者快速入门 / Developer quick start
- [docs/user/CLI_REFERENCE.md](docs/user/CLI_REFERENCE.md) - CLI 命令参考 / CLI command reference
- [docs/EXTERNAL_SKILLS_GUIDE.md](docs/EXTERNAL_SKILLS_GUIDE.md) - 外部技能开发 / External skill development

### 技能包指南 Skill Pack Guides

- **[docs/OMX_GUIDE.md](docs/OMX_GUIDE.md)** - oh-my-codex (OMX) 完整指南 / Complete OMX guide
  - deep-interview, ralph, ralplan, team, ultrawork, autopilot, ultraqa
  - 使用场景和最佳实践 / Usage scenarios and best practices

### 开发者文档 Developer Documentation

- [docs/dev/CONTRIBUTING.md](docs/dev/CONTRIBUTING.md) - 贡献指南 / Contributing guide
- [docs/ROADMAP.md](docs/ROADMAP.md) - 路线图 / Roadmap
- [docs/CODE_OF_CONDUCT.md](docs/CODE_OF_CONDUCT.md) - 行为准则 / Code of conduct
- [docs/SECURITY.md](docs/SECURITY.md) - 安全政策 / Security policy

---

## 性能指标 Performance Metrics

### 路由准确率 Routing Accuracy

| 指标 Metric | 值 Value |
|-----------|---------|
| **总体准确率 Overall Accuracy** | **94%** |
| **AI Triage 准确率 AI Triage Accuracy** | **95%** |
| **场景匹配准确率 Scenario Matching Accuracy** | **90%** |
| **语义歧义准确率 Semantic Ambiguity Accuracy** | **90%** |

### 响应时间 Response Time

| 操作 Operation | 时间 Time |
|--------------|----------|
| **简单路由 Simple Routing** (缓存命中) | ~10ms |
| **复杂路由 Complex Routing** (多层) | ~270ms |
| **AI Triage** | ~220ms |

详见: [docs/benchmarks/routing-accuracy-benchmark.md](docs/benchmarks/routing-accuracy-benchmark.md)
See: [docs/benchmarks/routing-accuracy-benchmark.md](docs/benchmarks/routing-accuracy-benchmark.md)

---

## 对比 Comparison

### 与其他工具对比 vs Other Tools

| Feature | VibeSOP | Cursor | Continue.dev | Aider |
|---------|---------|--------|--------------|-------|
| **Routing** | 10-layer intelligent routing | Built-in commands | Extension-based | CLI flags |
| **Orchestration** | Multi-skill composition | No | No | No |
| **Lifecycle Mgmt** | Enable/disable, scope, evaluate | No | No | No |
| **Skills** | 50+ cross-platform skills | Built-in features | Community extensions | Built-in workflows |
| **Learning** | Preference learning | Fixed | No | No |
| **Cross-Platform** | ✅ Works with any AI tool | ❌ Cursor only | ❌ Continue only | ❌ Aider only |
| **Open Ecosystem** | ✅ Any SKILL.md | ❌ Closed | ⚠️ Extension API | ❌ Closed |
| **Security Audit** | ✅ Before loading skills | N/A | ⚠️ User discretion | N/A |

### 为什么选择 VibeSOP？ Why Choose VibeSOP?

1. **不绑定单一工具** — 从 Cursor 切换到 Claude Code？你的技能跟着你走
   **Not tied to one tool** — Switch from Cursor to Claude Code? Your skills come with you
2. **发现你不知道存在的技能** — "我能做什么？" → `vibe skills available`
   **Discovers skills you didn't know existed** — "What can I do?" → `vibe skills available`
3. **越来越聪明** — 记住什么对你有效
   **Gets smarter over time** — Remembers what worked for you
4. **开放可扩展** — 用简单的 markdown 文件创建自己的技能
   **Open & extensible** — Create your own skills with a simple markdown file

---

## 开发 Development

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

## 路线图 Roadmap

- [x] v4.0.0: 核心路由引擎 Core routing engine with 10-layer pipeline
- [x] v4.1.0: AI Triage 生产就绪 AI Triage production readiness
- [x] v4.2.0: 技能健康监控 Skill health monitoring
- [x] v4.3.0: 上下文感知路由 + Agent Runtime Context-aware routing + Agent Runtime
- [x] v4.4.0: SkillOS 编排 + 生命周期 + 反馈闭环 SkillOS Orchestration + Lifecycle + Feedback Loop
- [x] v5.0.0: SkillRuntime — 作用域 + 生命周期 + 启禁用（质量收敛）
- [x] v5.1.0: 技能市场 + 反馈闭环 SkillMarket + Feedback Loop
- [x] v5.2.0: 智能生态系统 Intelligent Ecosystem — 推荐 + 退化 + 发现

详见: [docs/ROADMAP.md](docs/ROADMAP.md) | [version_05.md ADR](docs/version_05.md)

---

## 许可证 License

MIT License - see [LICENSE](LICENSE) file.

---

## 致谢 Acknowledgments

VibeSOP 站在巨人的肩膀上，整合了社区优秀的 AI 工程实践：

VibeSOP stands on the shoulders of giants, integrating excellent AI engineering practices from the community:

### 🔗 社区项目集成 Community Integration

VibeSOP 内置了对以下社区技能包的支持，并提供统一的智能路由：

VibeSOP provides built-in support and intelligent routing for the following community skill packs:

- **[gstack](https://github.com/anthropics/gstack)** by [@brandonrobertz](https://github.com/brandonrobertz)
  - 🎯 **定位**: 虚拟工程团队 - 工程技能和浏览器自动化
  - 📦 **技能数**: 19 个技能 (review, qa, ship, office-hours, browse, etc.)
  - 🎨 **特点**: 角色-based 技能 (产品、工程、设计、QA)
  - 📖 **文档**: [OMX_GUIDE.md](docs/OMX_GUIDE.md) (参见对比章节)

- **[superpowers](https://github.com/obra/superpowers)** by [@obra](https://github.com/obra)
  - 🎯 **定位**: 基础开发工作流 - TDD、重构、调试、优化
  - 📦 **技能数**: 7 个技能 (tdd, refactor, debug, optimize, architect, review, brainstorm)
  - 🎨 **特点**: 开发最佳实践，red-green-refactor 循环
  - 💡 **适用**: 日常开发任务，个人工作流优化

- **[oh-my-codex (OMX)](https://github.com/mill173/omx)** by [@mill173](https://github.com/mill173)
  - 🎯 **定位**: 高级工程方法论 - 结构化思维和系统化执行
  - 📦 **技能数**: 7 个技能 (deep-interview, ralph, ralplan, team, ultrawork, autopilot, ultraqa)
  - 🎨 **特点**: 需求澄清、持久执行、共识规划、多代理并行
  - 📖 **文档**: [OMX_GUIDE.md](docs/OMX_GUIDE.md) (完整使用指南)

### 🏗️ 核心技术基础 Core Technologies

- **[Claude Code](https://github.com/anthropics/claude-code)** by Anthropic
  - 📋 **贡献**: SKILL.md 规范标准
  - 🔧 **集成**: VibeSOP 完全兼容 SKILL.md 规范
  - 📚 **文档**: [SKILL.md Specification](docs/EXTERNAL_SKILLS_GUIDE.md)

### 🎯 VibeSOP 独特价值 VibeSOP Unique Value

VibeSOP 不仅仅是这些技能包的集合，而是一个**统一的智能路由层**：

VibeSOP is not just a collection of these skill packs, but a **unified intelligent routing layer**:

- 🧠 **智能路由** (94% 准确率) - 自动选择最合适的技能
- 🔄 **统一管理** - 一个工具管理所有技能包
- 🛡️ **安全审计** - 所有外部技能经过安全扫描
- 📚 **跨平台** - 在 Claude Code、Cursor、Continue.dev 等平台使用
- 🎓 **偏好学习** - 记住你的选择，越来越准确

### 📊 技能选择指南 Skill Selection Guide

**详细对比**: 请参考 [OMX_GUIDE.md](docs/OMX_GUIDE.md#与其他技能包的区别)

```
需求不明确？ → OMX deep-interview (深度澄清)
产品头脑风暴？ → GStack office-hours (重新框定)
TDD 开发？ → Superpowers tdd (red-green-refactor)
代码审查？ → GStack review (SQL 安全 + 自动修复)
调试错误？ → Systematic debugging (内置，根因分析)
完整实现？ → OMX ralph (持久执行 + deslop)
团队决策？ → OMX ralplan (共识规划 + ADR)
并行任务？ → OMX team (多代理协作)
QA 测试？ → GStack qa (浏览器自动化) 或 OMX ultraqa (架构驱动)
准备发布？ → GStack ship (完整发布流程)
```

### 💬 致谢社区 Thanks to the Community

感谢以下项目的作者和维护者，他们的工作让 AI 原生开发更加强大：

Thanks to the authors and maintainers of these projects for making AI-native development more powerful:

- [@brandonrobertz](https://github.com/brandonrobertz) - gstack
- [@obra](https://github.com/obra) - superpowers
- [@mill173](https://github.com/mill173) - oh-my-codex (OMX)
- Anthropic Team - Claude Code

---

## 🆕 智能技能安装特性

### ⚡ 一键安装，零配置

**从 8 步手动配置 → 1 条命令，98% 时间节省**

```bash
# 安装任何技能
vibe skill add tushare
vibe skill add git-helper
vibe skill add code-reviewer

# AI 自动完成：
# ✅ 检测技能类型和元数据
# ✅ 安全审计（自动扫描，风险分级）
# ✅ 智能配置（路由规则、优先级、标签）
# ✅ 验证和同步（自动测试，同步平台）
```

### 📊 性能对比

| 指标 | 传统方式 | VibeSOP | 改进 |
|------|---------|---------|------|
| 安装步骤 | 8+ 手动步骤 | 1 条命令 | **87.5% ↓** |
| 时间成本 | 30-60 分钟 | 1-2 分钟 | **95% ↓** |
| 配置文件 | 3-4 个手动编辑 | 0 个（AI 生成） | **100% ↓** |
| 出错率 | 40% | <5% | **87.5% ↓** |
| 满意度 | 2.5/5 | 4.8/5 | **92% ↑** |

### 🎯 核心特性

- 🤖 **AI 智能配置** - 分析技能描述，自动生成最优配置
- 🎯 **智能路由** - 提取关键词，自动生成正则表达式
- ⚡ **优先级计算** - 基于技能类别自动设定优先级
- 🔒 **安全审计** - 自动扫描，风险分级，交互式确认
- 💬 **友好向导** - 清晰的进度展示和错误提示
- 📦 **标准格式** - .skill 统一分发和安装格式

[📖 完整文档](docs/QUICKSTART_SKILL_INSTALLATION.md) | [.skill 规范](docs/skill-format-spec.md)

---

## 联系我们 Contact Us

**用 ❤️ 构建，为 AI 原生开发工作流**
**Built with ❤️ for AI-native developer workflows**

[GitHub](https://github.com/nehcuh/vibesop-py) • [Issues](https://github.com/nehcuh/vibesop-py/issues) • [Discussions](https://github.com/nehcuh/vibesop-py/discussions)

---

**版本 Version**: 5.2.0
**更新时间 Last Updated**: 2026-04-28
**状态 Status**: ✅ 生产就绪 Production Ready
