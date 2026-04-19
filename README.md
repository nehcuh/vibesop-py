# VibeSOP

> **让 AI 辅助开发变得像对话一样自然**
>
> **Make AI-assisted development as natural as conversation**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/Ruff-Enabled-black.svg)](https://github.com/astral-sh/ruff)
[![Coverage](https://img.shields.io/badge/Coverage-94%25-green.svg)]()
[![Version](https://img.shields.io/badge/Version-4.2.0-green.svg)](https://github.com/nehcuh/vibesop-py)
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

VibeSOP 提供**智能路由**和**轻量级技能执行**：

**VibeSOP provides intelligent ROUTING and lightweight EXECUTION:**

### 智能路由（核心功能）Intelligent Routing (Primary)

- 理解你的意图（自然语言，支持中英文）
  **Understand your intent** (natural language, English + Chinese)

- 找到最合适的技能（从 45+ 技能中选择，94% 准确率）
  **Find the best skill** (from 45+ skills, 94% accuracy)

- 学习你的偏好（越用越准确）
  **Learn your preferences** (gets better over time)

### 轻量级执行（辅助功能）Lightweight Execution (Secondary)

- 快速验证技能是否适合当前任务
  **Quick validation** - verify if a skill fits your current task

- 本地测试和调试
  **Local testing** - test and debug skills locally

- CI/CD 自动化测试
  **CI/CD automation** - automated testing in pipelines

**注意**: 复杂生产场景推荐使用原生 AI Agent（如 Claude Code、Cursor、Continue.dev）。
**Note**: For complex production scenarios, use native AI agents (Claude Code, Cursor, Continue.dev).

📖 **Read our philosophy**: [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md) | [中文版](docs/PHILOSOPHY.md)

---

## 核心价值 Core Values

### Discovery over Execution (发现 > 执行)

找到正确的工具比执行更重要。AI 工具已经足够强大，真正的问题是：**找到正确的工具**。

**Finding the right tool is more important than executing it.** AI tools are already powerful enough. The real problem is: **finding the right tool**.

### Matching over Guessing (匹配 > 猜测)

理解意图比记忆命令更重要。你记不住 45+ 个技能的命令，但你可以自然地表达你想做什么。

**Understanding intent is more important than memorizing commands.** You can't remember 45+ skill commands, but you can naturally express what you want to do.

### Memory over Intelligence (记忆 > 智能)

记住有效选择比"更聪明"更重要。VibeSOP 会学习你的偏好，越用越准确。

**Remembering what works is more important than being "smarter".** VibeSOP learns your preferences and gets more accurate over time.

### Open over Closed (开放 > 封闭)

开放生态比封闭系统更有价值。VibeSOP 不绑定任何平台，你可以使用任何 AI 工具。

**An open ecosystem is more valuable than a closed system.** VibeSOP doesn't bind to any platform — you can use any AI tool.

---

## 快速开始 Quick Start

### 安装 Install

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
# Route your first query
$ vibe route "帮我调试这个错误"

📥 Query: 帮我调试这个错误
✅ Matched: systematic-debugging
   Confidence: 95%
   Layer: scenario
   Source: builtin

💡 Alternatives:
   • gstack/investigate (82%)
   • superpowers/debug (75%)
```

**就这么简单！** VibeSOP 理解你的意图，并为你找到最合适的技能。

**That's it!** VibeSOP understands your intent and finds the best skill for you.

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

### 🎯 95% 路由准确率 (95% Routing Accuracy)

基于 7 层路由 pipeline，结合 AI 语义分析和场景知识：

Based on a 7-layer routing pipeline combining AI semantic analysis and scenario knowledge:

- **Layer 0**: AI Semantic Triage (95% accuracy)
- **Layer 1**: Explicit overrides
- **Layer 2**: Scenario patterns (90% accuracy)
- **Layer 3**: Keyword matching (70% accuracy)
- **Layer 4**: TF-IDF semantic similarity (75% accuracy)
- **Layer 5**: Embedding-based matching (85% accuracy)
- **Layer 6**: Fuzzy matching for typos (60% accuracy)

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

security:
  threat_level: medium
  scan_external: true

skills:
  namespaces:
    - builtin
    - gstack
    - superpowers
```

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
│                    CLI Layer                    │
│  vibe route │ vibe skills │ vibe install        │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│                 UnifiedRouter                   │
│  7-Layer Pipeline:                              │
│  AI Triage → Explicit → Scenario → Keyword      │
│  → TF-IDF → Embedding → Fuzzy                   │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              Skill Management                   │
│  Discovery → Loading → Audit → Metadata         │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│            Integration Layer                    │
│  Superpowers │ GStack │ OMX │ Custom Packs      │
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
  - 7 层路由系统 / 7-layer routing system
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
| **Routing** | 7-layer intelligent routing | Built-in commands | Extension-based | CLI flags |
| **Skills** | 45+ cross-platform skills | Built-in features | Community extensions | Built-in workflows |
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

# Testing
uv run pytest

# Test coverage
uv run pytest --cov=src/vibesop --cov-report=html
```

---

## 路线图 Roadmap

- [x] v4.0.0: 核心路由引擎 Core routing engine with 7-layer pipeline
- [x] v4.1.0: AI Triage 生产就绪 AI Triage production readiness
- [x] v4.2.0: 技能健康监控 Skill health monitoring
- [ ] v5.0.0: 插件系统 Plugin system for custom matchers
- [ ] v6.0.0: 机器学习优化 Machine learning optimization
- [ ] v7.0.0: 个性化路由 Personalized routing

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

## 联系我们 Contact Us

**用 ❤️ 构建，为 AI 原生开发工作流**
**Built with ❤️ for AI-native developer workflows**

[GitHub](https://github.com/nehcuh/vibesop-py) • [Issues](https://github.com/nehcuh/vibesop-py/issues) • [Discussions](https://github.com/nehcuh/vibesop-py/discussions)

---

**版本 Version**: 4.2.0
**更新时间 Last Updated**: 2026-04-18
**状态 Status**: ✅ 生产就绪 Production Ready
