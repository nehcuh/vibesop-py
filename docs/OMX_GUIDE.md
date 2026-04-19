# OMX 技能指南

> **版本**: 1.0.0
> **更新时间**: 2026-04-19
> **来源**: [oh-my-codex](https://github.com/mill173/omx) by @mill173

---

## 📖 目录

- [概述](#概述)
- [为什么使用 OMX](#为什么使用-omx)
- [技能列表](#技能列表)
- [使用场景](#使用场景)
- [启用方法](#启用方法)
- [与其他技能包的区别](#与其他技能包的区别)
- [实战示例](#实战示例)
- [常见问题](#常见问题)

---

## 概述

### 什么是 OMX？

**OMX** (oh-my-codex) 是由 [@mill173](https://github.com/mill173) 开发的高级工程方法论技能包，专注于：

- 🔍 **深度需求澄清** - 苏格拉底式提问，挖掘真实需求
- 🔄 **持久执行循环** - 确保任务完整完成，不中途放弃
- 🤝 **共识规划** - 团队协作的结构化决策流程
- 🚀 **并行执行** - 多代理协作处理复杂任务
- 🤖 **自主开发** - 从想法到验证代码的完整生命周期
- 🧪 **自主 QA** - 架构驱动的质量保证循环

### OMX 的设计哲学

OMX 强调**结构化思维**和**系统化执行**：

1. **明确性优先** - 在行动前先澄清需求
2. **完整性保证** - 持续执行直到真正完成
3. **共识驱动** - 重大决策需要结构化审议
4. **并行效率** - 独立任务应该并行处理
5. **自主循环** - QA 和开发应该是持续循环

---

## 为什么使用 OMX？

### 适用场景

✅ **推荐使用 OMX 的场景**：

- **需求不明确** - 需要深度澄清和挖掘
- **复杂任务** - 需要持久执行才能完成
- **团队协作** - 需要共识和结构化决策
- **真正并行** - 多个独立任务同时处理
- **完整开发** - 从想法到验证的端到端流程
- **质量循环** - 持续测试和改进

❌ **不推荐使用 OMX 的场景**：

- **简单任务** - 如小 bug 修复、简单查询
- **快速原型** - 需要快速迭代而非深度分析
- **单人小任务** - 不需要并行或共识

### OMX vs 其他技能包

| 特性 | OMX | GStack | Superpowers |
|------|-----|--------|-------------|
| **焦点** | 结构化方法论 | 工程实践 | 开发工作流 |
| **适用阶段** | 需求澄清 + 完整执行 | 代码实现 + QA | 特定任务 |
| **团队协作** | ✅ 强调共识和并行 | ⚠️ 部分支持 | ❌ 个人工作流 |
| **需求澄清** | ✅ 深度苏格拉底式 | ⚠️ 产品头脑风暴 | ❌ 无 |
| **执行模式** | 持久循环 + 并行 | 线性 + 浏览器 QA | 单次执行 |
| **QA 方式** | 架构驱动自主循环 | 浏览器自动化 | 手动测试 |

---

## 技能列表

### 1. 🤔 omx/deep-interview

**用途**: 苏格拉底式需求澄清，数学歧义评分

**触发模式**: `suggest` (自动建议)

**触发关键词**:
- 中文: 澄清、需求、理解、搞清楚、做什么、弄明白
- 英文: clarify, understand, requirements, figure out, what to build

**核心能力**:
- 通过苏格拉底式提问挖掘真实需求
- 使用数学方法量化需求歧义度
- 识别需求中的矛盾和不一致
- 引导用户明确真正的目标

**示例场景**:
```bash
# 用户需求不明确
vibe route "用户说要做一个社交功能，但具体不清楚"

→ 自动路由到: omx/deep-interview (95% 置信度)
→ 开始苏格拉底式需求澄清
```

**输出**:
- 需求歧义度评分 (0-100)
- 关键问题清单
- 明确的需求描述
- 潜在冲突警告

---

### 2. 🔄 omx/ralph

**用途**: 持久完成循环 + 强制 deslop + 架构验证

**触发模式**: `suggest` (自动建议)

**触发关键词**:
- 中文: 持久执行、长时间运行、完整实现、不要停
- 英文: persistent execution, long running, complete implementation

**核心能力**:
- **持久循环**: 持续执行直到任务真正完成
- **Deslop 清理**: 强制去除 AI 生成的冗余代码
- **架构验证**: 多层级质量检查
- **完整性保证**: 确保不遗漏任何细节

**Deslop 机制**:
```python
# 自动检测并清理：
❌ 冗余注释
❌ 过度抽象
❌ 无意义的变量重命名
❌ 冗长的类型标注
✅ 保留必要的逻辑和文档
```

**架构验证层级**:
1. **L1 基础检查**: 语法、类型、导入
2. **L2 逻辑检查**: 边界条件、错误处理
3. **L3 架构检查**: 设计模式、代码组织
4. **L4 最佳实践**: 性能、安全、可维护性

**示例场景**:
```bash
vibe route "完整实现用户认证系统，不要中途停止"

→ 自动路由到: omx/ralph (89% 置信度)
→ 持续执行直到完成，强制 deslop，多层验证
```

---

### 3. 🤝 omx/ralplan

**用途**: 共识规划 + RALPLAN-DR 结构化审议 + ADR 输出

**触发模式**: `suggest` (自动建议)

**触发关键词**:
- 中文: 结构化规划、共识、决策、架构决策记录、ADR
- 英文: structured plan, consensus, decision, ADR

**核心能力**:
- **RALPLAN-DR 流程**: 结构化的团队审议方法
- **共识达成**: 确保所有利益相关者同意
- **ADR 生成**: 自动生成架构决策记录
- **决策追溯**: 记录决策过程和理由

**RALPLAN-DR 流程**:
```
1. Propose (提案)    → 提出决策项
2. Analyze (分析)    → 分析选项和影响
3. Listen (倾听)     → 收集各方意见
4. Plan (规划)       → 制定实施方案
5. Agree (同意)      → 达成共识
6. Document (记录)   → 生成 ADR
7. Review (审查)     → 后续审查
```

**ADR 输出格式**:
```markdown
# ADR-001: 采用 PostgreSQL 作为主数据库

## Status
Accepted

## Context
我们需要一个支持复杂查询的关系型数据库...

## Decision
采用 PostgreSQL，因为...

## Consequences
- 正面影响: ACID 支持、JSON 类型
- 负面影响: 学习曲线、资源消耗
```

**示例场景**:
```bash
vibe route "团队需要决定使用哪个数据库"

→ 自动路由到: omx/ralplan (87% 置信度)
→ 启动 RALPLAN-DR 共识流程，生成 ADR
```

---

### 4. 👥 omx/team

**用途**: 多代理并行执行（Python asyncio + 文件协调）

**触发模式**: `manual` (手动调用 `/team`)

**触发关键词**:
- 中文: 并行、多代理、团队执行、同时处理
- 英文: parallel, multi-agent, team execution

**核心能力**:
- **Python asyncio**: 异步运行时
- **文件协调**: 基于文件的代理间通信
- **任务分发**: 智能任务分配
- **结果聚合**: 自动汇总结果

**工作原理**:
```python
async def team_execution():
    # 创建多个代理
    agents = [
        Agent("frontend"),
        Agent("backend"),
        Agent("database"),
    ]

    # 并行执行独立任务
    results = await asyncio.gather(
        agents[0].fix_ui_bug(),
        agents[1].optimize_api(),
        agents[2].add_index(),
    )

    # 聚合结果
    return aggregate(results)
```

**协调机制**:
```
.team/
├── tasks.json          # 任务队列
├── status.json         # 状态跟踪
├── results/            # 结果存储
│   ├── agent-1.json
│   ├── agent-2.json
│   └── agent-3.json
└── consensus.json      # 共识状态
```

**示例场景**:
```bash
# 在 Claude Code 中
/team "同时修复这 3 个独立的 bug"

→ 启动 3 个代理并行处理
→ 自动协调和汇总
```

---

### 5. ⚡ omx/ultrawork

**用途**: 层级感知并行执行引擎

**触发模式**: `manual` (手动调用 `/ultrawork`)

**核心能力**:
- **任务分层**: 按复杂度自动分层
- **依赖管理**: 处理任务间依赖
- **优先级调度**: 重要任务优先
- **资源优化**: 合理分配计算资源

**层级系统**:
```
Tier 1 (简单): 单文件修改、简单查询
Tier 2 (中等): 跨文件重构、小功能
Tier 3 (复杂): 架构变更、大功能
Tier 4 (核心): 基础设施、平台级
```

**示例场景**:
```bash
/ultrawork "优化整个项目的性能"

→ 分析任务层级
→ Tier 1: 修复慢查询 (并行 x10)
→ Tier 2: 添加缓存 (并行 x3)
→ Tier 3: 重构核心模块 (串行)
→ Tier 4: 数据库迁移 (串行，最后执行)
```

---

### 6. 🤖 omx/autopilot

**用途**: 全自主开发生命周期（想法 → 验证代码）

**触发模式**: `manual` (手动调用 `/autopilot`)

**核心能力**:
- **需求分析**: 自动理解和澄清
- **架构设计**: 生成技术方案
- **代码实现**: 编写高质量代码
- **测试验证**: 自动化测试
- **文档生成**: 完善的文档

**生命周期**:
```
1. 💡 Idea (想法)
   ↓
2. 📋 Requirements (需求)
   ↓
3. 🏗️ Architecture (架构)
   ↓
4. 💻 Implementation (实现)
   ↓
5. 🧪 Testing (测试)
   ↓
6. 📚 Documentation (文档)
   ↓
7. ✅ Verified Code (验证通过)
```

**示例场景**:
```bash
/autopilot "实现一个支持实时聊天的评论系统"

→ 自动完成整个生命周期
→ 输出可部署的代码
```

---

### 7. 🧪 omx/ultraqa

**用途**: 自主 QA 循环（架构诊断 → 修复）

**触发模式**: `manual` (手动调用 `/ultraqa`)

**核心能力**:
- **架构诊断**: 先诊断根本原因
- **循环测试**: 持续测试和修复
- **回归预防**: 确保不引入新问题
- **性能测试**: 包含性能验证

**QA 循环**:
```
1. 🔍 Diagnose (诊断)
   → 分析架构，找出根本原因

2. 🎯 Test (测试)
   → 编写测试用例

3. 🔧 Fix (修复)
   → 修复问题

4. ✅ Verify (验证)
   → 运行所有测试

5. 🔄 Repeat (循环)
   → 如果失败，回到步骤 1
```

**与 gstack/qa 的区别**:
| 特性 | omx/ultraqa | gstack/qa |
|------|-------------|-----------|
| **诊断方式** | 架构分析 | 浏览器测试 |
| **测试类型** | 单元 + 集成 | 端到端 UI |
| **修复策略** | 根因修复 | 快速修复 |
| **循环模式** | 持续循环 | 单次测试 |

**示例场景**:
```bash
/ultraqa "用户报告登录后偶尔会退出"

→ 架构诊断: session 过期逻辑错误
→ 编写测试: 重现问题
→ 修复: 调整过期策略
→ 验证: 通过所有测试
→ 循环: 直到问题完全解决
```

---

## 使用场景

### 场景 1: 需求不明确

**问题**: 用户说"做一个社交功能"，但不知道具体要做什么

**推荐技能**: `omx/deep-interview`

```bash
vibe route "用户说要做一个社交功能，但具体不清楚"

→ omx/deep-interview 开始苏格拉底式提问

Q: 你说的"社交功能"具体指什么？
A: 就是用户可以互相评论

Q: 评论需要实时更新吗？还是刷新后可见？
A: 需要实时更新

Q: 需要点赞、回复、嵌套评论吗？
A: 需要点赞和回复，不需要嵌套

...
→ 最终输出明确的需求文档
→ 歧义度评分: 从 85 降到 15
```

---

### 场景 2: 复杂功能完整实现

**问题**: 需要实现完整的用户认证系统，包括多种登录方式

**推荐技能**: `omx/ralph`

```bash
vibe route "完整实现用户认证系统，包括邮箱、手机、第三方登录，不要中途停止"

→ omx/ralph 启动持久执行循环

Phase 1: 数据库设计
✓ 用户表
✓ OAuth 表
✓ Session 表

Phase 2: 后端实现
✓ 邮箱密码登录
✓ 手机验证码登录
✓ Google OAuth
✓ GitHub OAuth

Phase 3: 前端实现
✓ 登录表单
✓ OAuth 按钮
✓ Session 管理

Phase 4: Deslop 清理
✓ 移除冗余注释
✓ 简化过度抽象
✓ 统一错误处理

Phase 5: 架构验证
✓ L1: 基础检查通过
✓ L2: 逻辑检查通过
✓ L3: 架构检查通过
✓ L4: 最佳实践检查通过

→ 完整实现，质量保证
```

---

### 场景 3: 团队架构决策

**问题**: 团队需要决定是否采用微服务架构

**推荐技能**: `omx/ralplan`

```bash
vibe route "团队需要决定是否采用微服务架构"

→ omx/ralplan 启动 RALPLAN-DR 共识流程

**Propose (提案)**:
是否从单体迁移到微服务？

**Analyze (分析)**:
选项 A: 保持单体
- 优点: 简单、部署快
- 缺点: 扩展性受限

选项 B: 采用微服务
- 优点: 独立扩展、技术栈灵活
- 缺点: 复杂度增加、运维成本

**Listen (倾听)**:
- 后端团队: 支持微服务，便于独立开发
- 运维团队: 担心管理复杂度
- 产品团队: 无所谓，只要稳定

**Plan (规划)**:
渐进式迁移，先拆分用户服务

**Agree (同意)**:
✅ 所有团队同意渐进式迁移方案

**Document (记录)**:
生成 ADR-001: 渐进式微服务化

**Review (审查)**:
3 个月后评估效果
```

---

### 场景 4: 并行处理独立任务

**问题**: 有 10 个独立的 bug 需要修复

**推荐技能**: `omx/team`

```bash
/team "并行修复这 10 个独立的 bug"

→ omx/team 启动多代理并行执行

Agent 1: 修复 bug #123 (UI 问题)
Agent 2: 修复 bug #124 (API 错误)
Agent 3: 修复 bug #125 (数据验证)
...
Agent 10: 修复 bug #132 (文档更新)

[并行执行中...]
✓ Agent 1 完成 (2min)
✓ Agent 2 完成 (3min)
✓ Agent 3 完成 (1min)
...
✓ Agent 10 完成 (5min)

[汇总结果]
✓ 10 个 bug 全部修复
✓ 通过所有测试
✓ 代码审查通过
✓ 文档已更新

总耗时: 5min (串行需要 30min)
```

---

### 场景 5: 从想法到部署

**问题**: 想要一个实时聊天功能

**推荐技能**: `omx/autopilot`

```bash
/autopilot "实现一个类似微信的实时聊天功能"

→ omx/autopilot 自动执行完整生命周期

**1. Idea Analysis** 💡
- 实时消息
- 群聊和私聊
- 消息历史
- 在线状态

**2. Requirements** 📋
- 功能需求文档
- 非功能需求
- 技术约束

**3. Architecture** 🏗️
- WebSocket 通信
- 消息队列
- 数据库设计
- 缓存策略

**4. Implementation** 💻
- 后端 API
- 前端组件
- WebSocket 处理
- 消息存储

**5. Testing** 🧪
- 单元测试
- 集成测试
- 性能测试
- 安全测试

**6. Documentation** 📚
- API 文档
- 部署指南
- 用户手册

**7. Verified Code** ✅
- 可部署的代码
- 通过所有测试
- 完整文档

→ 从想法到可部署代码，全自动化
```

---

### 场景 6: 持续 QA 循环

**问题**: 用户报告登录后偶尔退出，找不到原因

**推荐技能**: `omx/ultraqa`

```bash
/ultraqa "用户报告登录后偶尔会退出，问题不稳定"

→ omx/ultraqa 启动自主 QA 循环

**Cycle 1: Diagnose** 🔍
分析架构:
- Session 存储在 Redis
- 过期时间 24 小时
- 中间有 CDN 缓存

诊断结果: CDN 缓存可能导致 session 验证失败

**Cycle 1: Test** 🎯
编写测试: 模拟 CDN 缓存场景
✓ 复现问题

**Cycle 1: Fix** 🔧
修复: 调整 CDN 缓存策略，session 相关请求不缓存

**Cycle 1: Verify** ✅
运行测试: ✅ 通过
回归测试: ✅ 通过

**Cycle 2: Diagnose** 🔍
再次检查: 还有其他可能吗？
发现: OAuth token 刷新时机可能有问题

**Cycle 2: Test** 🎯
编写测试: 模拟 token 刷新
✓ 复现第二个问题

**Cycle 2: Fix** 🔧
修复: 优化 token 刷新逻辑

**Cycle 2: Verify** ✅
运行测试: ✅ 通过
回归测试: ✅ 通过
性能测试: ✅ 通过

**最终结果**:
✓ 两个根因全部修复
✓ 所有测试通过
✓ 性能无影响
✓ 文档已更新

→ 问题彻底解决，不再复发
```

---

## 启用方法

### 方法 1: 自动同步

```bash
# 同步所有内置技能（包括 OMX）到 Claude Code
vibe skills sync claude-code

# 查看已同步的技能
vibe skills list
```

### 方法 2: 构建部署

```bash
# 构建并直接部署到 Claude Code
vibe build claude-code --output ~/.claude

# 重启 Claude Code
```

### 方法 3: 验证安装

```bash
# 检查 OMX 技能是否可用
vibe skills info omx/deep-interview
vibe skills info omx/ralph
vibe skills info omx/ralplan
vibe skills info omx/team
vibe skills info omx/ultrawork
vibe skills info omx/autopilot
vibe skills info omx/ultraqa

# 测试路由
vibe route "帮我澄清这个需求"
→ 应该匹配到 omx/deep-interview
```

---

## 与其他技能包的区别

### 选择指南

```
需求不明确？
├─ 是 → 使用 omx/deep-interview (深度澄清)
└─ 否 → 继续判断

需要完整实现（不中途停止）？
├─ 是 → 使用 omx/ralph (持久执行)
└─ 否 → 继续判断

团队共识决策？
├─ 是 → 使用 omx/ralplan (共识规划)
└─ 否 → 继续判断

真正的并行任务？
├─ 是 → 使用 omx/team (多代理并行)
└─ 否 → 继续判断

从想法到代码？
├─ 是 → 使用 omx/autopilot (全自主)
└─ 否 → 继续判断

需要 QA 循环？
├─ 是 → 使用 omx/ultraqa (架构驱动)
└─ 否 → 使用其他技能包
```

### 具体对比

| 场景 | OMX | GStack | Superpowers |
|------|-----|--------|-------------|
| **需求澄清** | deep-interview (苏格拉底式) | office-hours (产品头脑风暴) | brainstorm (设计细化) |
| **完整实现** | ralph (持久 + deslop) | ❌ 无 | ❌ 无 |
| **架构决策** | ralplan (共识 + ADR) | plan-eng-review (技术审查) | architect (架构设计) |
| **并行执行** | team (多代理) | ❌ 无 | ❌ 无 |
| **QA 测试** | ultraqa (架构驱动) | qa (浏览器自动化) | ❌ 无 |
| **代码审查** | ❌ 无 | review (PR 前审查) | review (全面质量检查) |
| **调试** | ❌ 无 | investigate (根因分析) | debug (高级调试) |

---

## 实战示例

### 完整项目流程

```bash
# 1. 需求澄清
/deep-interview "做一个电商平台"

→ 输出: 详细需求文档
→ 歧义度: 95 → 12

# 2. 架构决策
/ralplan "选择技术栈"

→ 输出: ADR-001 技术栈决策
→ 团队共识: ✅

# 3. 并行开发
/team "实现用户、商品、订单模块"

→ 3 个代理并行开发
→ 耗时: 2 小时（串行需要 6 小时）

# 4. 完整实现核心功能
/ralph "实现支付系统，不要停"

→ 持续执行直到完成
→ Deslop 清理
→ 多层验证

# 5. QA 循环
/ultraqa "测试整个系统"

→ 架构诊断 + 测试 + 修复
→ 循环直到质量达标

# 6. 部署验证
vibe route "准备部署"

→ gstack/ship 处理发布流程
```

---

## 常见问题

### Q1: OMX 和 GStack 可以同时使用吗？

**A**: 可以！它们互补：

```bash
# 需求澄清 - OMX
/deep-interview "用户想要什么"

# 产品头脑风暴 - GStack
/office-hours "探索更多可能性"

# 架构决策 - OMX
/ralplan "技术选型"

# 代码实现 - GStack
/plan-eng-review "设计 API"

# 并行开发 - OMX
/team "实现前后端"

# QA 测试 - GStack
/qa "浏览器测试"

# 发布 - GStack
/ship "准备发布"
```

---

### Q2: 什么时候必须手动调用？

**A**: 以下 OMX 技能必须手动调用：

- `/team` - 多代理并行（需要明确任务分配）
- `/ultrawork` - 层级感知并行（需要复杂任务分析）
- `/autopilot` - 全自主开发（需要明确想法）
- `/ultraqa` - 自主 QA（需要明确问题）

其他技能可以自动触发：

- `deep-interview` - 需求澄清场景
- `ralph` - 持久执行场景
- `ralplan` - 共识规划场景

---

### Q3: OMX 的安全吗？

**A**: OMX 技能已通过 VibeSOP 安全审计：

- ✅ 无 prompt injection 风险
- ✅ 无 command injection 风险
- ✅ 无 privilege escalation 风险
- ✅ 代码审查通过
- ✅ 标记为 `trusted_builtin`

---

### Q4: OMX 适合个人开发者吗？

**A**: 部分适合：

✅ **适合个人**:
- `deep-interview` - 澄清自己的想法
- `ralph` - 完整实现功能
- `autopilot` - 快速原型开发
- `ultraqa` - 提高 QA 质量

❌ **更适合团队**:
- `ralplan` - 共识决策
- `team` - 多人协作
- `ultrawork` - 复杂任务调度

---

### Q5: OMX 的性能如何？

**A**: 性能数据：

| 技能 | 响应时间 | 资源占用 |
|------|----------|----------|
| deep-interview | ~1-2 min | 低 |
| ralph | 持续 (5-30 min) | 中 |
| ralplan | ~3-5 min | 低 |
| team | ~2-10 min | 高 (多代理) |
| ultrawork | ~5-15 min | 中-高 |
| autopilot | ~10-30 min | 高 |
| ultraqa | ~5-20 min | 中-高 |

---

## 进阶使用

### 自定义配置

```yaml
# .vibe/config.yaml
skills:
  omx:
    deep_interview:
      max_questions: 10      # 最多提问数
      ambiguity_threshold: 30 # 歧义度阈值

    ralph:
      deslop_level: aggressive # deslop 强度
      verification_layers: 4    # 验证层级

    ralplan:
      consensus_threshold: 0.8 # 共识阈值
      auto_adr: true           # 自动生成 ADR

    team:
      max_agents: 5            # 最大代理数
      timeout_per_task: 10     # 任务超时(分钟)
```

### 集成到工作流

```bash
# 项目初始化脚本
#!/bin/bash
echo "🔍 澄清需求..."
/deep-interview "$1"

echo "🤝 架构决策..."
/ralplan "技术栈选型"

echo "👥 并行开发..."
/team "实现核心模块"

echo "🧪 QA 测试..."
/ultraqa "完整测试"

echo "🚀 准备部署..."
/ship
```

---

## 相关资源

### 官方资源

- **OMX 源仓库**: [https://github.com/mill173/omx](https://github.com/mill173/omx)
- **OMX 文档**: [https://github.com/mill173/omx#readme](https://github.com/mill173/omx#readme)
- **作者**: [@mill173](https://github.com/mill173)

### VibeSOP 资源

- **VibeSOP 文档**: [docs/INDEX.md](INDEX.md)
- **CLI 参考**: [user/CLI_REFERENCE.md](user/CLI_REFERENCE.md)
- **外部技能指南**: [EXTERNAL_SKILLS_GUIDE.md](EXTERNAL_SKILLS_GUIDE.md)

### 社区

- **GitHub Issues**: [报告问题](https://github.com/nehcuh/vibesop-py/issues)
- **GitHub Discussions**: [讨论和问答](https://github.com/nehcuh/vibesop-py/discussions)

---

## 更新日志

### v1.0.0 (2026-04-19)

- ✅ 初始版本
- ✅ 包含 7 个 OMX 技能的完整文档
- ✅ 使用场景和实战示例
- ✅ 与其他技能包的对比

---

**文档维护**: VibeSOP 团队
**最后更新**: 2026-04-19
**反馈**: 请在 GitHub 提交 Issue 或 PR
