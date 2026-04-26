# VibeSOP - Python 版本

> **AI 辅助开发的技能操作系统（SkillOS）**
>
> 发现、路由、编排、管理——技能的全生命周期

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/Ruff-Enabled-black.svg)](https://github.com/astral-sh/ruff)
[![Basedpyright](https://img.shields.io/badge/Basedpyright-Strict-blue.svg)](https://github.com/DetachHead/basedpyright)
[![Coverage](https://img.shields.io/badge/Coverage-65%25-green.svg)]()
[![Version](https://img.shields.io/badge/Version-4.0.0-green.svg)](https://github.com/nehcuh/vibesop-py)

---

## VibeSOP 是什么？

**VibeSOP 是 AI 开发工具的 SkillOS（技能操作系统）。**它管理技能的全生命周期——发现、路由、编排、评估、淘汰——让 AI 辅助开发变得简单。

### 核心问题

AI 编码工具（Claude Code、Cursor、Continue.dev、Aider）功能强大，但：

- **"代码评审用什么技能？"** → 需要记忆
- **"如何调试这个错误？"** → 搜索文档
- **"有重构技能吗？"** → 不知道有什么可用
- **"这个技能质量如何？"** → 无法评估
- **"安装了太多技能怎么办？"** → 无法管理

**当前方案**：记忆命令、搜索文档、手动管理。

### VibeSOP 的解决方案

```
不再记忆技能 → 表达意图，AI 自动匹配
不再猜测质量 → 使用数据驱动评估
不再堆积技能 → 全生命周期管理
```

VibeSOP：
1. **理解你的意图** — 支持中英文自然语言
2. **找到正确的技能** — 从 45+ 可用技能中匹配
3. **学习你的偏好** — 用得越多，路由越准
4. **兼容所有 AI 工具** — Claude Code、Cursor、Continue.dev、Aider 等

### VibeSOP 的定位

**VibeSOP 是 SkillOS（技能操作系统）**，管理技能的全生命周期：

| ✅ 是什么 | 说明 |
|---------|------|
| 技能操作系统 | 发现、路由、编排、评估、淘汰——全生命周期管理 |
| 智能路由器 | 理解意图，匹配最佳技能 |
| 任务编排器 | 复杂请求分解，多技能协同 |
| 生命周期管理器 | 启禁用、作用域隔离、质量评估 |

| ❌ 不是什么 | 说明 |
|---------|------|
| 技能执行器 | 执行技能代码的是 AI Agent，不是 VibeSOP |
| AI 编码工具 | VibeSOP 管理技能，AI Agent 执行技能 |
| 单平台工具 | 跨 Claude Code、Cursor、OpenCode 等工作 |

---

## 设计灵感与参考

VibeSOP 借鉴了多个优秀的项目和理念：

### 开源项目

| 项目 | 借鉴内容 |
|------|----------|
| **[gstack](https://github.com/anthropics/gstack)** | 19 个工程技能（代码评审、调试、QA、浏览器自动化） |
| **[superpowers](https://github.com/obra/superpowers)** | 7 个基础开发技能（TDD、头脑风暴、重构、架构设计） |
| **[oh-my-codex](https://github.com/mill173/omx)** | 面试技巧、slop 检测、验证工作流 |
| **[Claude Code](https://github.com/anthropics/claude-code)** | SKILL.md 规范、工具调用模式 |

### 学术与业界理念

- **信息检索**：TF-IDF、基于嵌入的语义搜索、模糊匹配
- **偏好学习**：隐式反馈循环、协同过滤
- **多臂老虎机**：技能选择中的探索与利用平衡
- **意图分类**：多阶段路由管道（7 层）

### VibeSOP 的差异化

```
┌─────────────────────────────────────────────────────┐
│                  用户意图                            │
│              "帮我调试这个 bug"                      │
└────────────────────┬────────────────────────────────┘
                     │
           ┌─────────▼──────────┐
           │     VibeSOP        │ ← 我们在这里
           │  智能路由引擎       │
           │  任务编排引擎       │
           │  生命周期管理器     │
           │                    │
           │  • 理解意图         │
           │  • 匹配技能         │
           │  • 学习偏好         │
           │  • 跨平台           │
           └─────────┬──────────┘
                     │
      ┌──────────────┼──────────────┐
      │              │              │
┌─────▼─────┐  ┌────▼─────┐  ┌────▼─────┐
│Claude Code│  │  Cursor  │  │ Continue │
│(执行技能) │  │(执行技能) │  │(执行技能) │
└─────┬─────┘  └────┬─────┘  └────┬─────┘
      │              │              │
      └──────────────┼──────────────┘
                     │
          ┌──────────▼──────────┐
          │   技能生态系统       │
          │                     │
          │ builtin │ gstack │  │
          │  (12)    │  (19)   │  │
          └─────────────────────┘
```

---

## 与同类工具对比

| 特性 | VibeSOP | Cursor | Continue.dev | Aider |
|------|---------|--------|--------------|-------|
| **智能路由** | 7 层管道 | 内置命令 | 扩展机制 | CLI 参数 |
| **技能数量** | 45+ 跨平台技能 | 内置功能 | 社区扩展 | 内置工作流 |
| **学习能力** | 偏好学习 | 固定 | 无 | 无 |
| **跨平台** | ✅ 兼容所有 AI 工具 | ❌ 仅 Cursor | ❌ 仅 Continue | ❌ 仅 Aider |
| **开放生态** | ✅ 任何 SKILL.md | ❌ 封闭 | ⚠️ 扩展 API | ❌ 封闭 |
| **安全审计** | ✅ 加载前扫描 | N/A | ⚠️ 用户自行判断 | N/A |

### 为什么选择 VibeSOP？

1. **不绑定单一工具** — 从 Cursor 切换到 Claude Code？你的技能随你迁移
2. **发现你不知道的技能** — "我能做什么？" → `vibe skills list`
3. **越用越聪明** — 记住什么对你有效
4. **开放可扩展** — 用简单的 markdown 文件创建自己的技能

---

## 安装

### 前置要求

- **Python 3.12+** — VibeSOP 使用现代 Python 特性
- **Git** — 用于克隆技能仓库
- **可选：API Key** — 用于 AI 驱动的路由（Anthropic/OpenAI）

### 快速安装

```bash
# 克隆仓库
git clone https://github.com/nehcuh/vibesop-py.git
cd vibesop-py

# 使用 uv 安装（推荐 - 比 pip 快 10-100 倍）
uv sync

# 或使用 pip
pip install -e .
```

### 验证安装

```bash
$ vibe --help
VibeSOP - AI-powered workflow SOP

$ vibe doctor
✅ Python 版本: 3.12
✅ 依赖已安装
✅ 配置文件找到
✅ LLM 提供商: Anthropic (API key 已找到)
```

### 可选：AI 驱动的路由

为获得最佳路由准确性，设置 LLM 提供商：

```bash
# Anthropic Claude（推荐）
export ANTHROPIC_API_KEY="sk-ant-..."

# 或 OpenAI
export OPENAI_API_KEY="sk-..."

# VibeSOP 将自动使用 AI 路由
```

**没有 API key** 时，VibeSOP 仍可使用关键词/TF-IDF 匹配（仅精度略低）。

---

## 快速开始

### 1. 路由你的第一个查询

```bash
$ vibe route "帮我调试这个错误"

📥 查询: 帮我调试这个错误
✅ 匹配: systematic-debugging
   置信度: 95%
   层级: scenario
   来源: builtin

💡 备选:
   • gstack/investigate (82%)
   • superpowers/debug (75%)
```

### 2. 列出可用技能

```bash
$ vibe skills list

📚 可用技能 (45 个总计)

builtin (12 个技能)
  • systematic-debugging - 修复前先找根因
  • verification-before-completion - 完成前必须验证
  • planning-with-files - 复杂任务使用持久化文件
  ...

gstack (19 个技能)
  • gstack/review - PR 合并前评审
  • gstack/qa - 系统化 QA 测试并修复 bug
  • gstack/browse - 快速无头浏览器用于 QA 测试
  ...

superpowers (7 个技能)
  • tdd - 测试驱动开发工作流
  • brainstorm - 结构化头脑风暴
  • refactor - 系统化代码重构
  ...
```

### 3. 查看技能详情

```bash
$ vibe skill-info systematic-debugging

╭──────────────────────────────────────────────╮
│ Systematic Debugging                          │
├──────────────────────────────────────────────┤
│ ID: systematic-debugging                      │
│ 类型: prompt                                  │
│ 命名空间: builtin                              │
│                                                │
│ 描述                                           │
│ 修复前先找根因。                               │
│ 防止在没有正确诊断的情况下跳到解决方案。       │
│                                                │
│ 触发场景                                      │
│ 使用时机:                                     │
│ - 出现错误消息                                │
│ - 测试失败                                    │
│ - "出问题了"                                  │
│ - 需要根因分析                                │
╰──────────────────────────────────────────────╯
```

### 4. 安装外部技能

```bash
# 安装 gstack 技能
vibe install https://github.com/anthropics/gstack

📦 发现技能包: gstack
   发现技能: 19 个
   安装目标: ~/.config/skills/gstack/
   继续? [Y/n]

✅ gstack 安装成功
   运行 'vibe skills list --namespace gstack' 查看技能
```

---

## 工作原理

### 7 层路由管道

VibeSOP 按顺序尝试多种匹配策略，从最快开始：

| 层级 | 策略 | 速度 | 准确率 | 使用场景 |
|-------|----------|-------|----------|----------|
| 0 | AI 分诊 | ~100ms | 95% | 复杂查询、语义理解 |
| 1 | 显式覆盖 | <1ms | 100% | 直接命令如 `/review` |
| 2 | 场景模式 | <1ms | 90% | 预定义场景（调试、测试、评审） |
| 3 | 关键词匹配 | <1ms | 70% | 直接关键词命中 |
| 4 | TF-IDF | ~5ms | 75% | 语义相似度 |
| 5 | 嵌入向量 | ~20ms | 85% | 深度语义匹配（可选） |
| 6 | 模糊匹配 | ~10ms | 60% | 容错拼写 |

**结果**：带缓存的 P95 延迟 < 50ms。

### 偏好学习

VibeSOP 记住什么对你有效：

```bash
# 第一次询问调试
$ vibe route "debug this"
→ 匹配: systematic-debugging (85%)

# 你使用它且有效
$ vibe record systematic-debugging "debug this" --helpful

# 下次排名更高
$ vibe route "debug this"
→ 匹配: systematic-debugging (92%) ← 提升了!
```

### 技能发现来源

技能从多个位置发现，按优先级排序：

```
优先级  来源                              路径
────────  ─────────────────────────────────  ──────────────────────────────
1         项目特定技能                      .vibe/skills/
2         共享项目技能                      skills/
3         Claude Code 原生技能              ~/.claude/skills/
4         外部技能包                        ~/.config/skills/{pack}/
5         VibeSOP 全局技能                  ~/.vibe/skills/
6         VibeSOP 内置技能                  (代码库内包含)
```

---

## 使用示例

### 调试错误

```bash
$ vibe route "部署后数据库连接失败"

✅ 匹配: systematic-debugging
   理由: 检测到错误 → 使用调试工作流

# 阅读技能
cat ~/.claude/skills/systematic-debugging/SKILL.md

# 按照系统化调试流程执行
1. 收集信息
2. 识别模式
3. 形成假设
4. 测试假设
5. 修复根因
```

### 代码评审

```bash
$ vibe route "推送前评审我的代码"

✅ 匹配: gstack/review
   置信度: 93%

# 或使用显式命令
$ vibe route "/review"
✅ 匹配: gstack/review (层级 1: 显式覆盖)
```

### 中文查询

```bash
$ vibe route "帮我重构这个函数"

✅ 匹配: superpowers/refactor
   置信度: 89%

$ vibe route "代码覆盖率太低怎么办"

✅ 匹配: superpowers/tdd
   置信度: 91%
```

### 头脑风暴

```bash
$ vibe route "我需要一个新功能的想法"

✅ 匹配: gstack/office-hours
   置信度: 87%
   理由: "想法" + "新功能" → 设计思维
```

---

## 配置

### 项目级配置

在项目中创建 `.vibe/config.yaml`：

```yaml
# .vibe/config.yaml
platform: claude-code

routing:
  min_confidence: 0.6
  enable_fuzzy: true
  semantic_threshold: 0.75

security:
  threat_level: medium
  scan_external: true

skills:
  namespaces:
    - builtin
    - gstack
    - superpowers
```

### 全局配置

创建 `~/.vibe/config.yaml`：

```yaml
# ~/.vibe/config.yaml
default_platform: claude-code
llm_provider: anthropic  # 或 openai

routing:
  ai_triage_enabled: true
  cache_enabled: true

preferences:
  learning_enabled: true
  instinct_enabled: true
```

---

## 集成

### 与 Claude Code

```bash
# 构建并部署到 Claude Code
vibe build claude-code --output ~/.claude

# Claude Code 现在将使用 VibeSOP 进行路由
```

### 与 Cursor

```bash
# 为 Cursor 构建
vibe build cursor --output ~/.cursor

# 在 Cursor 会话中可用技能
```

### 与 Continue.dev

```bash
# 为 Continue 构建
vibe build opencode --output ~/.continue

# 在 Continue.dev 配置中使用
```

---

## 安全性

每个外部技能在**加载前都会经过审计**：

- ✅ 提示词注入检测
- ✅ 命令注入检测
- ✅ 角色劫持检测
- ✅ 权限提升检测
- ✅ 路径遍历保护

```bash
$ vibe install https://github.com/suspicious/skills

⚠️  安全审计失败:
   • 在 skills/evil/SKILL.md 中检测到提示词注入
   • 不安全的路径遍历尝试

出于安全考虑，安装被阻止。
```

---

## 架构

```
┌─────────────────────────────────────────────────┐
│                    CLI 层                        │
│  vibe route │ vibe skills │ vibe install        │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│                 UnifiedRouter                    │
│  AI 分诊 → 显式 → 场景 → 关键词                 │
│                    ↓                            │
│  [优化: 预过滤 → 偏好 → 聚类]                   │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              技能管理                            │
│  发现 → 加载 → 审计 → 元数据                     │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│            集成层                                │
│  Superpowers │ GStack │ OMX │ 自定义包           │
└─────────────────────────────────────────────────┘
```

---

## 文档

- [架构概览](docs/architecture/README.md) - 系统设计与组件
- [路由系统](docs/architecture/routing-system.md) - 7 层管道详解
- [定位与理念](docs/POSITIONING.md) - 为什么存在 VibeSOP
- [贡献指南](CONTRIBUTING.md) - 如何贡献

---

## 理念

### 发现优于执行

知道使用哪个技能比能够执行它更重要。VibeSOP 专注于**路由**，而非执行。

### 匹配优于猜测

7 层匹配管道确保准确路由。不再有"你是想说...？"

### 记忆优于智能

记住什么有效比每次都重新推理更有价值。偏好学习随时间改进路由。

### 开放优于封闭

任何遵循 [SKILL.md](docs/SKILL_SPEC.md) 规范的技能都可以集成。无供应商锁定。

---

## 开发

```bash
# 类型检查
uv run basedpyright

# 代码检查
uv run ruff check

# 自动修复问题
uv run ruff check --fix

# 代码格式化
uv run ruff format

# 运行测试
uv run pytest

# 测试覆盖率
uv run pytest --cov=src/vibesop --cov-report=html
```

---

## 路线图

- [x] v4.0.0: 核心路由引擎（10 层管道）
- [x] v4.1.0: AI 分诊生产就绪
- [x] v4.2.0: 技能健康监控
- [x] v4.3.0: 上下文感知路由 + Agent Runtime
- [ ] v4.4.0: 高级路由优化（进行中）
- [ ] v5.0.0: 插件生态系统

---

## 许可证

MIT License - 参见 [LICENSE](LICENSE) 文件。

---

## 致谢

VibeSOP 站在巨人的肩膀上：

- **[gstack](https://github.com/anthropics/gstack)** - 工程技能和浏览器自动化
- **[superpowers](https://github.com/obra/superpowers)** - 基础开发工作流
- **[oh-my-codex](https://github.com/mill173/omx)** - 面试技巧和验证
- **[Claude Code](https://github.com/anthropics/claude-code)** - SKILL.md 规范

VibeSOP 是独立实现，具有：
- 清洁架构（相比 Ruby 版本减少 65% 代码）
- 统一路由管道
- 生产就绪的安全审计
- 偏好学习系统

---

**用 ❤️ 为 AI 原生开发工作流构建**

[GitHub](https://github.com/nehcuh/vibesop-py) • [Issues](https://github.com/nehcuh/vibesop-py/issues) • [Discussions](https://github.com/nehcuh/vibesop-py/discussions)
