# VibeSOP 技能生态系统完整指南

> **版本**: 1.0.0
> **更新时间**: 2026-04-19
> **适用版本**: VibeSOP 4.2.0+

---

## 📖 目录

- [概述](#概述)
- [技能分类](#技能分类)
- [10 层路由系统](#10-层路由系统)
- [所有技能列表](#所有技能列表)
- [优先级决策机制](#优先级决策机制)
- [冲突解决策略](#冲突解决策略)
- [手动切换技能](#手动切换技能)
- [场景化选择指南](#场景化选择指南)
- [实战示例](#实战示例)
- [最佳实践](#最佳实践)

---

## 概述

### 什么是技能？

**技能（Skills）** 是封装了特定工作流程或专业知识的可执行单元。每个技能都是一个 `SKILL.md` 文件，定义了：

- **触发条件** - 何时使用这个技能
- **执行步骤** - 具体要做什么
- **所需工具** - 需要哪些 AI 工具
- **适用场景** - 什么时候最有效

### VibeSOP 技能生态

```
VibeSOP 技能生态
│
├─ 📦 Builtin (17 个)    - 内置核心技能
├─ 📦 Superpowers (7 个) - 基础开发工作流
├─ 📦 GStack (19 个)     - 虚拟工程团队
├─ 📦 OMX (7 个)         - 高级工程方法论
└─ 📦 Project (自定义)   - 项目特定技能

总计: 50+ 个技能，持续增长中
```

### 核心价值

**VibeSOP 不是技能的集合，而是智能路由层**：

| 特性 | 说明 |
|------|------|
| 🧠 **智能路由** | 94% 准确率自动选择最合适的技能 |
| 🔄 **统一管理** | 一个工具管理所有技能包 |
| 🛡️ **安全审计** | 所有外部技能经过安全扫描 |
| 📚 **跨平台** | Claude Code、Cursor、Continue.dev 等 |
| 🎓 **偏好学习** | 记住你的选择，越来越准确 |

---

## 技能分类

### 按 Namespace 分类

#### 1. Builtin (内置技能)

**特点**:
- ✅ 核心工作流，必须启用
- ✅ 优先级最高（P0）
- ✅ 完全信任，无安全风险
- ✅ VibeSOP 维护

**示例**:
- `systematic-debugging` - 系统化调试（P0 强制）
- `verification-before-completion` - 完成前验证（P0 强制）
- `session-end` - 会话结束处理（P0 强制）

#### 2. Superpowers (基础工作流)

**来源**: [github.com/obra/superpowers](https://github.com/obra/superpowers)

**特点**:
- 🎯 日常开发任务
- 🎯 TDD、重构、优化
- 🎯 个人工作流优化

**示例**:
- `superpowers/tdd` - 测试驱动开发
- `superpowers/refactor` - 代码重构
- `superpowers/optimize` - 性能优化

#### 3. GStack (虚拟工程团队)

**来源**: [github.com/anthropics/gstack](https://github.com/anthropics/gstack)

**特点**:
- 👥 角色-based 技能
- 👥 产品、工程、设计、QA
- 👥 浏览器自动化

**示例**:
- `gstack/office-hours` - 产品头脑风暴
- `gstack/review` - PR 前代码审查
- `gstack/qa` - 浏览器 QA 测试

#### 4. OMX (高级方法论)

**来源**: [github.com/mill173/omx](https://github.com/mill173/omx)

**特点**:
- 🏗️ 结构化思维
- 🏗️ 系统化执行
- 🏗️ 团队协作

**示例**:
- `omx/deep-interview` - 需求澄清
- `omx/ralph` - 持久执行循环
- `omx/team` - 多代理并行

#### 5. Project (项目自定义)

**特点**:
- 🎨 项目特定技能
- 🎨 本地维护
- 🎨 最高优先级（覆盖其他）

**示例**:
- `project/domain-audit` - 业务逻辑审计
- `project/api-style-check` - API 风格检查

---

### 按触发模式分类

| 触发模式 | 说明 | 示例 |
|----------|------|------|
| **mandatory** | 强制触发，无法关闭 | `systematic-debugging`, `verification-before-completion` |
| **suggest** | 自动建议，可选择 | `planning-with-files`, `gstack/review` |
| **manual** | 仅手动调用 | `omx/team`, `gstack/browse` |

---

### 按优先级分类

| 优先级 | 说明 | 技能数量 |
|--------|------|----------|
| **P0** | 强制触发，最高优先级 | 3 个（mandatory） |
| **P1** | 核心技能，自动建议 | 30+ 个 |
| **P2** | 辅助技能，手动或建议 | 10+ 个 |

---

## 10 层路由系统

### 架构概览

```
用户查询
  ↓
┌─────────────────────────────────────────┐
│ Layer 0: AI Semantic Triage (95%)      │ ← 最智能
├─────────────────────────────────────────┤
│ Layer 1: Explicit Overrides            │ ← 用户明确指定
├─────────────────────────────────────────┤
│ Layer 2: Scenario Patterns (90%)       │ ← 场景匹配
├─────────────────────────────────────────┤
│ Layer 3: Keyword Matching (70%)        │ ← 关键词
├─────────────────────────────────────────┤
│ Layer 4: TF-IDF Similarity (75%)       │ ← 语义相似
├─────────────────────────────────────────┤
│ Layer 5: Embedding Matching (85%)      │ ← 向量匹配
├─────────────────────────────────────────┤
│ Layer 6: Fuzzy Matching (60%)          │ ← 模糊匹配
└─────────────────────────────────────────┘
  ↓
推荐技能 + 置信度 + 备选方案
```

### 各层详解

#### Layer 0: AI Semantic Triage (95% 准确率)

**原理**: 使用 LLM（Claude Haiku/GPT）理解语义意图

**示例**:
```bash
Query: "我的测试失败了，而且数据库连接也有问题"

Layer 0 分析:
- 语义理解: "测试失败" + "数据库问题"
- 识别为: 调试场景
- 推荐技能: systematic-debugging
- 置信度: 95%
```

**配置**:
```yaml
# .vibe/config.yaml
routing:
  enable_ai_triage: true
  llm_provider: anthropic  # or openai
```

#### Layer 1: Explicit Overrides

**原理**: 用户明确指定技能

**示例**:
```bash
# 用户明确指定
vibe route "用 gstack/review 审查这个代码"

→ 跳过所有层，直接使用 gstack/review
```

**关键词**:
- "用 <skill>"
- "使用 <skill>"
- "use <skill>"
- "try <skill>"

#### Layer 2: Scenario Patterns (90% 准确率)

**原理**: 预定义场景映射到技能

**场景映射**:
```yaml
debugging:
  - systematic-debugging (primary)
  - gstack/investigate (alternative)
  - superpowers/debug (alternative)

code_review:
  - gstack/review (primary)
  - superpowers/review (alternative)

planning:
  - planning-with-files (primary)
  - gstack/plan-eng-review (alternative)
```

**示例**:
```bash
Query: "帮我调试这个错误"

→ 匹配场景: debugging
→ 推荐技能: systematic-debugging
→ 置信度: 90%
```

#### Layer 3: Keyword Matching (70% 准确率)

**原理**: 关键词直接映射

**关键词库**:
```yaml
debug: [debug, 错误, bug, 失败, 报错]
review: [review, 审查, pr, merge]
test: [test, 测试, tdd]
plan: [plan, 规划, 设计, 架构]
```

**示例**:
```bash
Query: "这个有 bug"

→ 匹配关键词: bug
→ 映射到场景: debugging
→ 推荐技能: systematic-debugging
```

#### Layer 4: TF-IDF Similarity (75% 准确率)

**原理**: TF-IDF 向量化 + 余弦相似度

**示例**:
```bash
Query: "优化数据库查询性能"

→ TF-IDF 向量化
→ 与所有技能描述计算相似度
→ 最高相似: superpowers/optimize (0.75)
```

#### Layer 5: Embedding Matching (85% 准确率)

**原理**: 词嵌入向量匹配

**示例**:
```bash
Query: "代码质量下降，需要重构"

→ 词嵌入向量化
→ 与技能意图向量匹配
→ 最高相似: superpowers/refactor (0.85)
```

#### Layer 6: Fuzzy Matching (60% 准确率)

**原理**: Levenshtein 距离模糊匹配

**示例**:
```bash
Query: "debub"  # 拼写错误

→ 模糊匹配到: "debug"
→ 推荐技能: systematic-debugging
```

---

## 所有技能列表

### Builtin Skills (17 个)

#### P0 Mandatory Skills (强制触发)

| 技能 ID | 用途 | 触发条件 |
|---------|------|----------|
| `systematic-debugging` | 系统化调试，先找根因再修复 | 检测到错误/失败 |
| `verification-before-completion` | 完成前必须验证 | 会话结束前 |
| `session-end` | 会话结束处理 | 检测到退出信号 |

#### P1 Core Skills (自动建议)

| 技能 ID | 用途 | 触发条件 |
|---------|------|----------|
| `planning-with-files` | 用文件作为工作记忆处理复杂任务 | 复杂任务（>5 文件） |
| `experience-evolution` | 捕获可重用的经验和模式 | 重复工作模式 |
| `instinct-learning` | 自动提取会话模式 | 会话结束时 |
| `riper-workflow` | 5 阶段开发工作流 | 复杂项目开发 |
| `using-git-worktrees` | Git worktree 并行隔离 | 需要并行分支 |
| `autonomous-experiment` | 自主实验循环 | 优化和迭代任务 |
| `skill-craft` | 自动检测模式生成技能 | 检测到重复模式 |

---

### Superpowers Skills (7 个)

| 技能 ID | 用途 | 触发模式 | 适用场景 |
|---------|------|----------|----------|
| `superpowers/tdd` | 测试驱动开发（red-green-refactor） | suggest | 编写新功能 |
| `superpowers/brainstorm` | 结构化头脑风暴 | manual | 需要创意 |
| `superpowers/refactor` | 系统化代码重构 | suggest | 代码质量下降 |
| `superpowers/debug` | 高级调试工作流 | suggest | 复杂 bug |
| `superpowers/architect` | 系统架构设计 | manual | 架构设计 |
| `superpowers/review` | 代码审查（全面质量检查） | suggest | PR 审查 |
| `superpowers/optimize` | 性能优化和性能分析 | manual | 性能问题 |

**详细文档**: [Superpowers GitHub](https://github.com/obra/superpowers)

---

### GStack Skills (19 个)

#### 产品与规划

| 技能 ID | 用途 | 触发模式 |
|---------|------|----------|
| `gstack/office-hours` | 产品头脑风暴，重新框定问题 | suggest |
| `gstack/plan-ceo-review` | CEO/创始人角度审查 | suggest |
| `gstack/plan-eng-review` | 工程架构审查 | suggest |
| `gstack/plan-design-review` | 设计/UX 审查 | manual |
| `gstack/design-consultation` | 构建设计系统 | manual |

#### 代码质量

| 技能 ID | 用途 | 触发模式 |
|---------|------|----------|
| `gstack/review` | PR 前审查（SQL 安全 + 自动修复） | suggest |
| `gstack/codex` | 跨模型第二意见 | manual |
| `gstack/investigate` | 系统化根因调试（自动 freeze 作用域） | suggest |

#### QA 与测试

| 技能 ID | 用途 | 触发模式 |
|---------|------|----------|
| `gstack/qa` | 浏览器 QA（测试 + 修复 + 原子提交） | suggest |
| `gstack/qa-only` | 仅 QA 报告（不修复） | manual |
| `gstack/browse` | 无头浏览器自动化 | manual |
| `gstack/setup-browser-cookies` | 导入浏览器 cookies | manual |

#### 发布与运维

| 技能 ID | 用途 | 触发模式 |
|---------|------|----------|
| `gstack/ship` | 发布工作流（测试 + 审查 + 推送 + PR） | suggest |
| `gstack/document-release` | 发布后自动更新文档 | suggest |
| `gstack/retro` | 周级工程回顾 | manual |

#### 安全与保护

| 技能 ID | 用途 | 触发模式 |
|---------|------|----------|
| `gstack/careful` | 破坏性命令警告 | suggest |
| `gstack/freeze` | 限制编辑范围 | manual |
| `gstack/guard` | 最大安全模式（careful + freeze） | manual |
| `gstack/unfreeze` | 移除编辑范围限制 | manual |

**详细文档**: [GStack GitHub](https://github.com/anthropics/gstack)

---

### OMX Skills (7 个)

| 技能 ID | 用途 | 触发模式 | 适用场景 |
|---------|------|----------|----------|
| `omx/deep-interview` | 苏格拉底式需求澄清 | suggest | 需求不明确 |
| `omx/ralph` | 持久执行循环 + deslop + 架构验证 | suggest | 需要完整实现 |
| `omx/ralplan` | 共识规划 + RALPLAN-DR + ADR | suggest | 团队决策 |
| `omx/team` | 多代理并行执行 | manual | 真正的并行任务 |
| `omx/ultrawork` | 层级感知并行执行 | manual | 复杂任务调度 |
| `omx/autopilot` | 全自主开发生命周期 | manual | 从想法到代码 |
| `omx/ultraqa` | 自主 QA 循环（架构驱动） | manual | 持续 QA |

**详细文档**: [OMX_GUIDE.md](OMX_GUIDE.md)

---

### Project Skills (自定义)

**创建方法**:

```bash
# 创建项目技能目录
mkdir -p .vibe/skills/my-audit

# 创建 SKILL.md
cat > .vibe/skills/my-audit/SKILL.md << 'EOF'
# My Custom Audit

id: project/my-audit
name: My Custom Audit
description: Audit specific to my project
intent:
  - user says "audit my code"
  - check for specific patterns

## Steps

1. Check pattern A
2. Check pattern B
3. Generate report
EOF

# 注册技能
vibe skills register .vibe/skills/my-audit
```

**优先级**: Project skills > External skills > Builtin

---

## 优先级决策机制

### 决策流程

```
用户查询
  ↓
Layer 0-6: 路由分析
  ↓
┌─────────────────────────────────┐
│ 1. 检查 Project Skills          │ ← 最高优先级
│    - 项目自定义技能              │
│    - 覆盖所有其他技能            │
├─────────────────────────────────┤
│ 2. 检查 Explicit Override       │ ← 用户明确指定
│    - "用 gstack/review"         │
│    - 强制使用指定技能            │
├─────────────────────────────────┤
│ 3. 检查 Mandatory Skills        │ ← P0 强制
│    - systematic-debugging       │
│    - verification-before-completion
├─────────────────────────────────┤
│ 4. 场景匹配 + 冲突解决          │ ← 核心决策
│    - 场景 → 主技能               │
│    - 冲突策略 → 备选方案         │
├─────────────────────────────────┤
│ 5. 置信度评分                   │ ← 质量控制
│    - ≥ 0.6: 自动使用            │
│    - < 0.6: 显示备选方案         │
└─────────────────────────────────┘
  ↓
推荐技能 + 备选方案
```

### 场景优先级表

| 场景 | 主技能 | 备选方案 1 | 备选方案 2 | 触发条件 |
|------|--------|-----------|-----------|----------|
| **调试** | systematic-debugging | gstack/investigate | superpowers/debug | 错误/失败 |
| **需求澄清** | omx/deep-interview | gstack/office-hours | superpowers/brainstorm | 需求不明确 |
| **代码审查** | gstack/review | superpowers/review | gstack/codex | PR/合并 |
| **产品思考** | gstack/office-hours | superpowers/brainstorm | - | 新功能/想法 |
| **规划** | planning-with-files | gstack/plan-eng-review | gstack/plan-ceo-review | 规划/设计 |
| **重构** | superpowers/refactor | gstack/review | - | 代码质量 |
| **持久执行** | omx/ralph | riper-workflow | - | 完整实现 |
| **共识规划** | omx/ralplan | planning-with-files | gstack/plan-eng-review | 团队决策 |
| **并行执行** | omx/team | omx/ultrawork | using-git-worktrees | 并行任务 |
| **QA 循环** | omx/ultraqa | gstack/qa | gstack/qa-only | 测试循环 |

### 冲突解决策略

**配置文件**: `core/registry.yaml`

```yaml
conflict_resolution:
  enabled: true
  source: .vibe/skill-routing.yaml

  strategies:
    # 调试场景：builtin 优先
    - scenario: debugging
      primary: systematic-debugging
      primary_source: builtin
      alternatives:
        - skill: gstack/investigate
          trigger: "需要自动 freeze 作用域"
        - skill: superpowers/debug
          trigger: "需要高级调试工作流"
      override_keywords:
        - "用 gstack"
        - "用 superpowers"

    # 需求澄清场景：OMX 优先
    - scenario: requirements_clarification
      primary: omx/deep-interview
      primary_source: omx
      alternatives:
        - skill: gstack/office-hours
          trigger: "产品头脑风暴"
        - skill: superpowers/brainstorm
          trigger: "设计细化"
```

**自定义冲突解决**:

```yaml
# .vibe/skill-routing.yaml
conflict_resolution:
  strategies:
    # 覆盖默认策略
    - scenario: code_review
      primary: superpowers/review  # 改为 superpowers 优先
      alternatives:
        - skill: gstack/review
```

---

## 手动切换技能

### 方法 1: 使用 Override 关键词

**在查询中明确指定**:

```bash
# 方式 1: "用 <skill>"
vibe route "用 gstack/review 审查这个代码"

# 方式 2: "使用 <skill>"
vibe route "使用 superpowers/refactor 重构这个函数"

# 方式 3: "use <skill>"
vibe route "use omx/deep-interview 帮我澄清需求"
```

### 方法 2: 在 Claude Code 中直接调用

**斜杠命令**:

```bash
# 直接调用技能（跳过路由）
/gstack/review
/superpowers/tdd
/omx/team
```

### 方法 3: 配置默认技能

**项目级配置**:

```yaml
# .vibe/config.yaml
skills:
  defaults:
    # 为特定场景设置默认技能
    code_review: superpowers/review  # 覆盖 gstack/review
    debugging: systematic-debugging
    planning: omx/ralplan  # 覆盖 planning-with-files
```

**用户级配置**:

```yaml
# ~/.vibe/config.yaml
skills:
  defaults:
    qa: omx/ultraqa  # 默认使用 omx 而非 gstack
    test: superpowers/tdd
```

### 方法 4: 禁用特定技能

```yaml
# .vibe/config.yaml
skills:
  disabled:
    - gstack/codex  # 禁用 Codex 技能
    - superpowers/brainstorm  # 禁用头脑风暴
```

### 方法 5: 调整技能触发模式

```yaml
# .vibe/config.yaml
skills:
  trigger_modes:
    # 改为手动触发
    gstack/qa: manual
    omx/team: suggest  # 改为自动建议
```

---

## 场景化选择指南

### 决策树

```
遇到问题？
├─ 是错误/失败？
│  ├─ 简单错误 → systematic-debugging (内置)
│  ├─ 需要隔离作用域 → gstack/investigate
│  └─ 复杂调试 → superpowers/debug
│
├─ 需求不明确？
│  ├─ 苏格拉底式澄清 → omx/deep-interview ⭐
│  ├─ 产品头脑风暴 → gstack/office-hours
│  └─ 设计细化 → superpowers/brainstorm
│
├─ 代码审查？
│  ├─ PR 前快速审查 → gstack/review ⭐
│  ├─ 全面质量检查 → superpowers/review
│  └─ 跨模型第二意见 → gstack/codex
│
├─ 编写新功能？
│  ├─ TDD 方式 → superpowers/tdd ⭐
│  ├─ 需要澄清 → omx/deep-interview
│  └─ 完整实现 → omx/ralph
│
├─ 性能问题？
│  ├─ 性能优化 → superpowers/optimize
│  └─ 需要实验 → autonomous-experiment
│
├─ 需要规划？
│  ├─ 复杂任务 → planning-with-files
│  ├─ 团队共识 → omx/ralplan ⭐
│  ├─ 工程审查 → gstack/plan-eng-review
│  └─ 产品视角 → gstack/plan-ceo-review
│
├─ 需要并行？
│  ├─ 多代理协作 → omx/team ⭐
│  ├─ 层级任务 → omx/ultrawork
│  └─ Git worktree → using-git-worktrees
│
├─ 需要测试？
│  ├─ 浏览器测试 → gstack/qa ⭐
│  ├─ 仅报告 → gstack/qa-only
│  └─ QA 循环 → omx/ultraqa
│
└─ 准备发布？
   ├─ 发布流程 → gstack/ship ⭐
   └─ 更新文档 → gstack/document-release

⭐ = 推荐的首选技能
```

### 快速参考表

| 我想... | 推荐技能 | 备选方案 | 命令示例 |
|---------|----------|----------|----------|
| **调试错误** | systematic-debugging | gstack/investigate | `vibe route "调试这个错误"` |
| **澄清需求** | omx/deep-interview | gstack/office-hours | `vibe route "需求不明确"` |
| **TDD 开发** | superpowers/tdd | - | `/tdd` |
| **审查 PR** | gstack/review | superpowers/review | `vibe route "review my PR"` |
| **重构代码** | superpowers/refactor | gstack/review | `vibe route "重构这个函数"` |
| **优化性能** | superpowers/optimize | autonomous-experiment | `vibe route "优化性能"` |
| **浏览器测试** | gstack/qa | gstack/qa-only | `/qa` |
| **并行任务** | omx/team | omx/ultrawork | `/team` |
| **完整实现** | omx/ralph | - | `vibe route "完整实现"` |
| **团队决策** | omx/ralplan | gstack/plan-eng-review | `vibe route "团队决策"` |
| **发布代码** | gstack/ship | - | `/ship` |

---

## 实战示例

### 示例 1: 调试错误

**场景**: 测试失败，不知道原因

**自动路由**:
```bash
vibe route "我的测试失败了"

→ Layer 2: 匹配场景 "debugging"
→ 推荐技能: systematic-debugging (95% 置信度)
→ 备选方案: gstack/investigate (82%), superpowers/debug (75%)
```

**手动切换**:
```bash
# 如果 systematic-debugging 不够用，明确切换
vibe route "用 gstack/investigate 调试这个"

→ Layer 1: 检测到 override
→ 强制使用: gstack/investigate
```

### 示例 2: 需求澄清

**场景**: 用户说"做一个社交功能"，但不知道具体要什么

**自动路由**:
```bash
vibe route "用户说要做一个社交功能，但具体不清楚"

→ Layer 0: AI Triage 理解语义
→ Layer 2: 匹配场景 "requirements_clarification"
→ 推荐技能: omx/deep-interview (95% 置信度)
→ 备选方案: gstack/office-hours (80%), superpowers/brainstorm (75%)
```

**在 Claude Code 中**:
```bash
# 直接调用（跳过路由）
/deep-interview

→ 直接使用 omx/deep-interview
→ 开始苏格拉底式提问
```

### 示例 3: 代码审查

**场景**: 准备提交 PR，需要审查

**自动路由**:
```bash
vibe route "准备提交 PR，帮我审查一下"

→ Layer 2: 匹配场景 "code_review"
→ 推荐技能: gstack/review (93% 置信度)
→ 备选方案: superpowers/review (78%)
```

**切换到其他审查技能**:
```bash
# 方式 1: 使用 override
vibe route "用 superpowers/review 审查这个"

# 方式 2: 在 Claude Code 中直接调用
/review  # 如果配置了 gstack 为默认

# 方式 3: 明确指定完整路径
/superpowers/review
```

### 示例 4: 并行任务

**场景**: 有 10 个独立的 bug 需要修复

**自动路由**:
```bash
vibe route "并行修复这 10 个独立的 bug"

→ Layer 2: 匹配场景 "parallel_execution"
→ 推荐技能: omx/team (87% 置信度)
→ 备选方案: omx/ultrawork (75%), using-git-worktrees (70%)
```

**手动调用** (team 是 manual 模式):
```bash
# 在 Claude Code 中
/team "并行修复这 10 个独立的 bug"

→ 启动多代理并行执行
→ 自动协调和汇总
```

### 示例 5: 完整开发流程

**场景**: 从想法到部署的完整流程

```bash
# 1. 需求澄清
/deep-interview "用户想要一个实时聊天功能"

# 2. 产品思考
/office-hours "探索更多可能性"

# 3. 架构规划
/plan-eng-review "设计技术方案"

# 4. TDD 开发
/tdd "实现核心功能"

# 5. 代码审查
/review "审查实现"

# 6. 浏览器测试
/qa "端到端测试"

# 7. 发布
/ship "准备发布"
```

---

## 最佳实践

### 1. 信任自动路由

**建议**: 先让 VibeSOP 自动路由，再考虑手动切换

**原因**:
- ✅ 94% 准确率
- ✅ 基于语义理解，不仅仅是关键词
- ✅ 会学习你的偏好

**示例**:
```bash
# ✅ 好的做法
vibe route "帮我调试这个问题"
→ 自动推荐 systematic-debugging

# ❌ 不好的做法
vibe route "用 systematic-debugging 帮我调试"
→ 限制了路由系统的能力
```

### 2. 使用备选方案

**当自动推荐不合适时**:

```bash
vibe route "帮我调试这个问题"

✅ Matched: systematic-debugging (95%)
💡 Alternatives:
   • gstack/investigate (82%) - 如果需要 freeze 作用域
   • superpowers/debug (75%) - 如果需要高级调试

# 如果 systematic-debugging 不够用
→ 选择 gstack/investigate（如果有作用域问题）
→ 选择 superpowers/debug（如果需要高级工作流）
```

### 3. 明确指定意图

**提供上下文，提高准确率**:

```bash
# ❌ 模糊的查询
vibe route "help me"

# ✅ 明确的查询
vibe route "我刚写了新功能，需要帮忙 review"
→ 明确推荐 gstack/review
```

### 4. 利用偏好学习

**记录反馈，让路由更准确**:

```bash
# 路由正确
vibe feedback record "review PR" "gstack/review" --correct

# 路由错误
vibe feedback record "review PR" "gstack/review" \
    --wrong "superpowers/review" --confidence 0.7
```

### 5. 组合使用技能

**不要依赖单个技能**:

```bash
# ✅ 好的组合
/deep-interview "澄清需求"
/office-hours "产品头脑风暴"
/plan-eng-review "架构设计"
/tdd "实现功能"
/review "代码审查"
/qa "浏览器测试"
/ship "准备发布"

# ❌ 不好的做法
/autopilot "做一个功能"
→ 虽然可行，但失去了细粒度控制
```

### 6. 配置项目默认值

**为项目设置合理的默认值**:

```yaml
# .vibe/config.yaml
skills:
  defaults:
    # 根据项目特点调整
    code_review: superpowers/review  # 如果更注重质量
    qa: omx/ultraqa  # 如果需要架构驱动测试
    planning: omx/ralplan  # 如果是团队项目
```

### 7. 定期查看技能列表

**了解可用技能**:

```bash
# 查看所有可用技能
vibe skills available

# 查看特定技能的详情
vibe skills info omx/deep-interview

# 列出某个 namespace 的技能
vibe skills list --namespace gstack
```

---

## 进阶配置

### 自定义技能路由

**创建项目级路由规则**:

```yaml
# .vibe/skill-routing.yaml
scenario_keywords:
  # 添加项目特定关键词
  audit:
    - "审计"
    - "检查"
    - "audit"

conflict_resolution:
  strategies:
    # 覆盖默认策略
    - scenario: audit
      primary: project/domain-audit
      alternatives:
        - skill: gstack/review
```

### 技能别名

**创建易记的别名**:

```yaml
# .vibe/config.yaml
skills:
  aliases:
    # 短别名
    review: gstack/review
    tdd: superpowers/tdd
    qa: gstack/qa
    ship: gstack/ship
```

### 技能链

**定义技能执行顺序**:

```yaml
# .vibe/skill-chains.yaml
chains:
  full-development:
    - omx/deep-interview
    - gstack/office-hours
    - gstack/plan-eng-review
    - superpowers/tdd
    - gstack/review
    - gstack/qa
    - gstack/ship
```

---

## 故障排查

### 问题 1: 路由不准确

**症状**: 推荐的技能不符合需求

**解决方案**:
1. 检查查询是否明确
2. 查看备选方案
3. 使用 override 明确指定
4. 记录反馈帮助学习

```bash
# 提供明确的查询
vibe route "我需要审查 PR，检查 SQL 安全性"

# 查看备选方案
vibe route "review code" --show-alternatives

# 明确指定
vibe route "用 gstack/review 审查这个"

# 记录反馈
vibe feedback record "review PR" "gstack/review" --correct
```

### 问题 2: 技能未找到

**症状**: "Skill not found"

**解决方案**:
1. 检查技能是否已安装
2. 检查技能 ID 是否正确
3. 查看技能列表

```bash
# 检查技能是否存在
vibe skills available | grep review

# 查看技能详情
vibe skills info gstack/review

# 安装缺失的技能包
vibe install gstack
```

### 问题 3: 无法手动调用技能

**症状**: 斜杠命令不工作

**解决方案**:
1. 检查技能是否已同步
2. 检查触发模式
3. 使用完整路径

```bash
# 同步技能到平台
vibe skills sync claude-code

# 使用完整路径
/gstack/review
/superpowers/tdd
/omx/deep-interview
```

---

## 相关资源

### 官方文档

- **[OMX 指南](OMX_GUIDE.md)** - OMX 技能完整指南
- **[外部技能指南](EXTERNAL_SKILLS_GUIDE.md)** - 创建自定义技能
- **[CLI 参考](user/CLI_REFERENCE.md)** - 命令行完整参考
- **[架构文档](architecture/ARCHITECTURE.md)** - 系统架构详解

### 社区资源

- **Superpowers**: [github.com/obra/superpowers](https://github.com/obra/superpowers)
- **GStack**: [github.com/anthropics/gstack](https://github.com/anthropics/gstack)
- **OMX**: [github.com/mill173/omx](https://github.com/mill173/omx)

### 配置参考

- **[core/registry.yaml](../core/registry.yaml)** - 技能注册表
- **[.vibe/config.yaml](.vibe/config.yaml)** - 项目配置

---

## 更新日志

### v1.0.0 (2026-04-19)

- ✅ 初始版本
- ✅ 完整的 10 层路由系统说明
- ✅ 所有 50+ 技能的列表和说明
- ✅ 优先级决策机制详解
- ✅ 冲突解决策略说明
- ✅ 手动切换技能的 5 种方法
- ✅ 场景化选择指南
- ✅ 实战示例和最佳实践

---

**文档维护**: VibeSOP 团队
**最后更新**: 2026-04-19
**反馈**: 请在 GitHub 提交 Issue 或 PR
