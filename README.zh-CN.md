# VibeSOP

> **Version**: 8.1.0
> **同步说明**：README.md 本身即为中文主线（README.en.md 为英文版）。本文件保留为中文镜像副本，内容与 [README.md](README.md) 全量一致；更新时请以 README.md 为事实源修改并同步本文件。

---
# VibeSOP

> **AI 辅助开发的技能操作系统**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/Ruff-Enabled-black.svg)](https://github.com/astral-sh/ruff)
[![Coverage](https://img.shields.io/badge/Coverage-73%25-yellow.svg)]()
[![Version](https://img.shields.io/badge/Version-8.1.0-blue.svg)](https://github.com/nehcuh/vibesop-py)
[![Spec](https://img.shields.io/badge/Spec-v3.0-green.svg)](docs/skill-format-spec-v3.md)
[![Conformance](https://img.shields.io/badge/Conformance-85%20tests-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

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

- **智能路由**：理解意图，从 50+ 技能中匹配最佳

- **任务编排**：复杂请求自动分解，生成串行/分组执行计划

- **生命周期管理**：启禁用、作用域隔离、质量评估、自动淘汰

- **跨平台适配**：一套技能定义，所有 AI Agent 通用

**VibeSOP 定位**: VibeSOP 是 SkillOS + 轻量引导执行层。它管理技能的**全生命周期**：发现 → 安装 → 路由 → 编排 → 评估 → 保留/淘汰。
简单任务由 VibeSOP 端到端完成（路由→注入→引导执行），复杂任务由 AI Agent（Claude Code, Cursor, OpenCode）接手。

📖 **阅读我们的哲学**: [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md) | [中文版](docs/PHILOSOPHY.md)

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

理解意图比记忆命令更重要。你记不住 50+ 个技能的命令，但你可以自然地表达你想做什么。

### 开放 > 封闭

开放生态比封闭系统更有价值。VibeSOP 不绑定任何平台，你可以使用任何 AI 工具。

---

## ⚡ 快速开始

### 🚀 一键安装技能（核心特性）

**从 8 个手动步骤 → 1 条命令，98% 时间节省！**

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

### 安装 VibeSOP

```bash
# Clone the repository
git clone https://github.com/nehcuh/vibesop-py.git
cd vibesop-py

# Install with uv (recommended - 10-100x faster than pip)
uv sync
```

### 第一次使用

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
   • mattpocock/diagnose (82%)
   • superpowers/debug (75%)
```

> 💡 VibeSOP 路由到技能并把指令注入你的 AI Agent（Claude Code / OpenCode）的上下文，由 Agent 负责实际执行。运行 `vibe doctor` 查看哪些 Agent 可用。

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

> **⚠️ Important: VibeSOP requires its own LLM configuration**
>
> VibeSOP runs as a CLI subprocess and **cannot reuse the host Agent's internal LLM** (e.g., OpenCode or Claude Code's session model). You must configure a separate LLM API key or local Ollama service for VibeSOP. Without LLM, VibeSOP uses keyword/TF-IDF matching only, and long queries may fail to match any skill.
>
> ```bash
> # Anthropic Claude (recommended)
> export ANTHROPIC_API_KEY="sk-ant-..."
> # or OpenAI
> export OPENAI_API_KEY="sk-..."
> # or local Ollama (zero cost, no data leaving your machine)
> export VIBE_LLM_PROVIDER=ollama
> export OLLAMA_BASE_URL=http://localhost:11434/v1
> export OLLAMA_MODEL=qwen3:35b-a3b-mlx
> ```

---

## 为什么选择 VibeSOP？

### 问题

AI 辅助开发工具正在爆发：
- Claude Code, Cursor, Continue.dev, Aider...
- 每个工具都有自己的命令和技能
- superpowers, mattpocock, omx 等技能包蓬勃发展
- **你不知道该用哪个**

### 解决方案

```bash
# Just say what you want (自然语言输入)
vibe route "debug this database error"
# → Routes to: systematic-debugging (95% confidence)

vibe route "帮我扫描安全漏洞"
# → Routes to: mattpocock/diagnose (88% confidence)

vibe route "review my PR"
# → Routes to: mattpocock/tdd (92% confidence)
```

VibeSOP:
1. **理解你的意图** (自然语言，支持中英文)
2. **找到正确的技能** (从 50+ 技能中选择)
3. **学习你的偏好** (越用越准确)
4. **跨平台通用** (Claude Code, Cursor, Continue.dev 等)

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

### 🎯 95% 路由准确率

基于 4 阶段路由级联，结合 AI 语义分析和场景知识：

- **Stage 1**: Explicit override — exact skill ID match (e.g. `/review`), immediate dispatch
- **Stage 2**: Scenario + Semantic Index — predefined scenarios + skill semantic index
  (token-overlap + embedding), best-of-N selection
- **Stage 3**: AI Semantic Triage — LLM intent understanding (95% accuracy, complex /
  long queries)
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

### 🧠 偏好学习

VibeSOP 会记住你的选择：

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

### 🔓 开放生态

不绑定任何平台，支持所有 AI 工具：

- ✅ Claude Code
- ✅ Cursor
- ✅ Continue.dev
- ✅ Aider
- ✅ Any tool that supports SKILL.md

### 🛡️ 安全审计

每个外部技能都会经过安全扫描：

- ✅ Prompt injection detection
- ✅ Command injection detection
- ✅ Role hijacking detection
- ✅ Privilege escalation detection
- ✅ Path traversal protection

---

## 使用示例

### 调试错误

```bash
$ vibe route "database connection failed after deployment"

✅ Matched: systematic-debugging
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
    - mattpocock
    - superpowers
    - omx
```

#### 用户确认模式

默认情况下，VibeSOP 会在选择技能前展示路由决策报告并要求你确认：

```bash
$ vibe route "帮我 review 代码"
╭────────── 🔍 Routing Decision Report ──────────╮
│ Selected: mattpocock/tdd (confidence: 87%)      │
│ ...                                            │
╰────────────────────────────────────────────────╯
How would you like to proceed?
  ✅ Confirm selected skill
  🔀 Choose a different skill
  📝 Skip skill, use raw LLM
```

你可以通过以下方式关闭确认：

- **临时跳过**：`vibe route "query" --yes` 或 `-y`
- **全局关闭**：在 `~/.vibe/config.toml` 中设置 `routing.confirmation_mode = "never"`
- **仅低置信度时确认**：设置 `routing.confirmation_mode: ambiguous_only`

> ⚠️ **注意**：确认模式默认开启 (`always`)，旨在让你了解 VibeSOP 的决策过程。关闭后将恢复为自动选择。

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
  - 50+ 个技能详解
  - 4 阶段路由级联
  - 优先级决策机制
  - 手动切换技能
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
| **Skills** | 50+ cross-platform skills | Built-in features | Community extensions | Built-in workflows |
| **Learning** | Preference learning | Fixed | No | No |
| **Cross-Platform** | ✅ Works with any AI tool | ❌ Cursor only | ❌ Continue only | ❌ Aider only |
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

- 🧠 **智能路由** (94% 准确率) - 自动选择最合适的技能
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

> 📖 [English version](README.en.md)
