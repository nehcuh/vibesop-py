# VibeSOP Principles

> **Version**: 4.0.0
> **Status**: Mandatory (必须遵守)
> **Last Updated**: 2026-04-06

> **任何开发工作开始前，必须阅读并理解本文档。**
> **所有设计决策、代码实现、功能添加都必须符合这些原则。**

---

## Vision（愿景）

### 一句话定义

**VibeSOP 是 AI 辅助开发的智能路由引擎 — 理解用户意图，发现最佳工作流，管理技能生态，让 AI 工具从"每次从零开始"变成"越用越聪明"。**

### 我们不是什么

- **不是** 技能执行引擎 — 执行是 AI Agent（Claude Code / OpenCode）的事
- **不是** 技能创造平台 — 技能以 SKILL.md 定义，VibeSOP 负责发现和路由
- **不是** AI 工具本身 — VibeSOP 运行在 AI 工具之上，是工作流层
- **不是** 配置模板集 — VibeSOP 是可执行的框架，有路由、记忆、学习

### 核心价值（我们解决什么）

1. **每次会话从零开始** → 智能路由 + 偏好学习，越用越准
2. **不知道有什么工具可用** → 技能发现 + 安装 + 健康检查
3. **工具散落各处无法统一** → 统一技能生态，任何 SKILL.md 都可接入

---

## Core Principles（核心原则）

### 1. Discovery > Execution（发现优于执行）

**宣言**: *Knowing what's available matters more than being able to execute it yourself.*

**要求**:
- ✅ VibeSOP 负责路由和发现，不负责技能执行
- ✅ 执行是 AI Agent 的职责，VibeSOP 只推荐最佳技能
- ✅ 所有外部技能包统一处理（superpowers/gstack/omx/自定义）
- ✅ 智能安装器自动分析项目结构

**反模式**:
- ❌ 在 VibeSOP 中实现技能执行逻辑
- ❌ 对某个外部技能包特殊对待

---

### 2. Matching > Guessing（匹配优于猜测）

**宣言**: *Multi-layer matching beats keyword guessing every time.*

**要求**:
- ✅ 多层匹配管道（keyword → TF-IDF → embedding → fuzzy）
- ✅ 冲突解决机制
- ✅ 偏好学习让路由越来越准
- ✅ 路由效果追踪，持续优化

**反模式**:
- ❌ 单层关键词匹配
- ❌ 每次都重新推理，不利用历史

---

### 3. Memory > Intelligence（记忆优于智能）

**宣言**: *An AI that remembers your past mistakes is more valuable than a smarter AI that starts fresh each session.*

**要求**:
- ✅ 系统化记录偏好和历史（instinct/memory/session_analyzer）
- ✅ 路由决策参考历史选择
- ✅ 自动发现重复模式，建议新技能
- ✅ 让错误只犯一次

**三层记忆架构**:
```
core/
├── instinct/         # 偏好学习：记录用户选择模式
├── memory/           # 会话记忆：项目级知识持久化
└── session_analyzer  # 模式发现：从重复行为中提取技能
```

---

### 4. Open > Closed（开放优于封闭）

**宣言**: *Any skill that follows the SKILL.md spec can join the ecosystem.*

**要求**:
- ✅ 任何符合 SKILL.md 规范的技能都可以接入
- ✅ 已知包直接安装，任意 URL 智能分析安装
- ✅ 外部技能经过安全审计后可用
- ✅ 技能包优先级：外部 > 内置 fallback

**反模式**:
- ❌ 只支持自家技能
- ❌ 对外部技能包设置不合理的接入门槛

---

### 5. Production-First（生产优先）

**宣言**: *Not a tutorial. Not a toy config. A production routing engine that actually ships.*

**要求**:
- ✅ 所有功能必须经过实战检验
- ✅ 拒绝"演示级"代码，坚持"生产级"质量
- ✅ 优先考虑稳定性而非新特性
- ✅ 每个功能都必须有测试覆盖

**反模式**:
- ❌ "先做个简单的，以后再优化"
- ❌ "演示可以用就行"
- ❌ 没有测试就合并

---

### 6. Verification > Confidence（验证优于自信）

**宣言**: *The cost of running `npm test` is always less than the cost of shipping a broken build.*

**要求**:
- ✅ 要求显式验证才能声称完成
- ✅ 消除"应该可以了"的假设
- ✅ 让测试成为完成的定义
- ✅ 技能安装前必须通过安全审计

**反模式**:
- ❌ "应该可以工作了"
- ❌ 没有验证就声称完成

---

### 7. Portable > Specific（可移植优于特定）

**宣言**: *`core/` keeps the semantics portable, while adapters keep platforms productive right now.*

**三层架构**:
```
┌─────────────────────────────────┐
│  CLI Layer                       │  vibe route/install/skills
├─────────────────────────────────┤
│  Routing Engine (core)           │  平台无关的路由逻辑
├─────────────────────────────────┤
│  Skill Management                │  技能发现/安装/审计
├─────────────────────────────────┤
│  Adapter Layer                   │  claude-code / opencode
└─────────────────────────────────┘
```

**反模式**:
- ❌ 在 core/ 中添加平台特定代码
- ❌ 绑定某个 AI 工具的专有 API

---

### 8. Security by Default（安全默认）

**宣言**: *External code must be audited before execution.*

**要求**:
- ✅ 所有外部技能加载前扫描威胁
- ✅ 路径遍历攻击防护
- ✅ 白名单目录机制
- ✅ 智能安装器执行安全审计

---

## Architecture Principles（架构原则）

### 模块边界

| 模块 | 职责 | 边界 |
|---|---|---|
| `core/routing/` | 路由决策 | 只做匹配和推荐，不执行 |
| `core/matching/` | 匹配算法 | 纯计算，无副作用 |
| `core/optimization/` | 偏好学习 | 基于历史数据优化路由 |
| `core/algorithms/` | 可复用算法 | 纯数学/检测，任何技能可用 |
| `core/skills/` | 技能管理 | 发现、加载、注册，不执行 |
| `core/instinct/` | 偏好数据 | 路由的输入信号 |
| `core/memory/` | 会话记忆 | 路由的上下文感知 |
| `installer/` | 技能安装 | 检测、安装、版本管理 |
| `security/` | 安全审计 | 外部技能加载前扫描 |
| `adapters/` | 平台适配 | 配置渲染到目标平台 |

### SSOT - 单源真理（Single Source of Truth）

| 信息类型 | 权威位置 |
|---------|---------|
| 路由决策 | `core/routing/unified.py` |
| 技能定义 | `skills/*/SKILL.md` + `core/registry.yaml` |
| 偏好数据 | `core/instinct/` + `.vibe/preferences.json` |
| 项目状态 | `core/state/` + `.vibe/state/` |
| 安全策略 | `security/` |

---

## 与参考项目的关系

| 项目 | 它做什么 | VibeSOP 做什么 |
|---|---|---|
| superpowers | 7 个通用技能 | 发现、安装、路由这些技能 |
| gstack | 19 个工程团队技能 | 同上 |
| oh-my-codex | 7 种方法论 | 同上（含内置 fallback + 算法库支持） |
| karpathy/autoresearch | 自主研究方法论 | 提供可复用算法作为参考 |

**VibeSOP 不是技能的创造者，是技能的发现者、路由者和管理者。**

---

## Decision Framework（决策框架）

### 当面临技术决策时，问自己：

1. **这符合路由引擎定位吗？**
   - 是否增强了路由/发现/管理能力？
   - 是否避免了越界到技能执行？

2. **这遵循核心原则吗？**
   - 发现 > 执行？匹配 > 猜测？记忆 > 智能？
   - 开放 > 封闭？生产优先？可移植 > 特定？

3. **这会增加技术债务吗？**
   - 是否引入不必要的复杂性？
   - 是否破坏现有模块边界？

4. **这对用户友好吗？**
   - 是否让技能安装更简单？
   - 路由结果是否更准确？

---

## Anti-Patterns（反模式）

### 绝对禁止

1. **在 VibeSOP 中实现技能执行逻辑**（除非是纯可复用算法）
2. **对某个外部技能包特殊对待**（所有包统一处理）
3. **破坏向后兼容性**（除非是主版本升级）
4. **添加未经测试的功能**
5. **在 core/ 中添加平台特定代码**

### 强烈反对

1. **增加不必要的依赖**
2. **忽视路由性能**
3. **跳过安全审计**
4. **不记录路由决策的依据**

---

## Changelog（修订历史）

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 4.0.0 | 2026-04-06 | 重新定位为智能路由引擎，移除执行逻辑，新增算法库 | @huchen |
| 3.0.0 | 2026-04-05 | Python 版本，新增 Security by Default 和 Progressive Disclosure | @huchen |
| 2.0.0 | 2026-03-29 | 明确项目愿景定位，新增双场景价值、整合过滤器 | @huchen |
| 1.0.0 | 2026-03-12 | 初始版本 | @huchen |

---

**记住：这些原则不是建议，是要求。**

**任何偏离这些原则的开发都必须通过决策框架检验。**
