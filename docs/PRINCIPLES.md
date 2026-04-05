# VibeSOP Principles

> **Version**: 3.0.0
> **Status**: Mandatory (必须遵守)
> **Last Updated**: 2026-04-05

> **任何开发工作开始前，必须阅读并理解本文档。**
> **所有设计决策、代码实现、功能添加都必须符合这些原则。**

---

## Vision（愿景）

### 一句话定义

**VibeSOP 是一套 AI 辅助开发的标准工作流（SOP）——个人用它积累知识、加速开发，团队用它统一规范、沉淀经验。**

### 我们不是什么

- **不是** AI 工具本身——VibeSOP 是工作流层，运行在 AI 工具之上
- **不是** 配置模板集——VibeSOP 是可执行的框架，有 routing、memory、learning
- **不是** 只服务于 Claude Code——Portable Core + Adapter 架构确保跨平台

### 核心痛点（我们解决什么）

1. **每次会话从零开始** → 结构化配置 + 分层加载
2. **重复犯同样的错误** → Memory + Instinct 系统
3. **每个人都要重新摸索** → Skill 生态 + 智能路由

---

## Core Principles（核心原则）

### 1. Production-First（生产优先）

**宣言**: *Not a tutorial. Not a toy config. A production workflow that actually ships.*

**要求**:
- ✅ 所有功能必须经过实战检验
- ✅ 拒绝"演示级"代码，坚持"生产级"质量
- ✅ 优先考虑稳定性而非新特性
- ✅ 每个功能都必须有测试覆盖

**检查清单**:
- [ ] 这个功能在生产环境测试过吗？
- [ ] 有全面的错误处理吗？
- [ ] 边界条件考虑了吗？
- [ ] 性能影响评估了吗？

**反模式**:
- ❌ "先做个简单的，以后再优化"
- ❌ "演示可以用就行"
- ❌ 没有测试就合并

---

### 2. Structure > Prompting（结构化优于提示）

**宣言**: *A well-organized config file beats clever one-off prompts every time.*

**要求**:
- ✅ 优先建立结构化的配置系统
- ✅ 避免依赖聪明的单次提示
- ✅ 建立可复用的规则和模板
- ✅ 让 AI 通过读取配置而非记忆来工作

**实践方式**:
- 将规则写入 `rules/behaviors.md`
- 将技能定义写入 `skills/*/SKILL.md`
- 将项目信息写入 `memory/`
- 使用 YAML/JSON 而非长文本提示

**反模式**:
- ❌ 写一个很长的提示期望 AI 记住
- ❌ 每次会话都重新解释需求
- ❌ 依赖 AI 的"理解"而非明确规则

---

### 3. Memory > Intelligence（记忆优于智能）

**宣言**: *An AI that remembers your past mistakes is more valuable than a smarter AI that starts fresh each session.*

**要求**:
- ✅ 系统化记录经验教训
- ✅ 建立可搜索的知识库
- ✅ 自动保存工作进度
- ✅ 让错误只犯一次

**三层记忆架构**:
```
memory/
├── session.md           # Hot: 每日进度，活跃任务
├── project-knowledge.md # Warm: 技术陷阱，模式
└── overview.md          # Cold: 目标，基础设施
```

**关键实践**:
- 使用 `session-end` 技能自动保存进度
- 在 `memory/project-knowledge.md` 记录技术陷阱
- 使用 `experience-evolution` 技能积累项目知识
- 建立 SSOT（单源真理）防止信息重复

---

### 4. Verification > Confidence（验证优于自信）

**宣言**: *The cost of running `npm test` is always less than the cost of shipping a broken build.*

**要求**:
- ✅ 要求显式验证才能声称完成
- ✅ 消除"应该可以了"的假设
- ✅ 建立强制检查点
- ✅ 让测试成为完成的定义

**强制规则**:
- 任何任务完成前必须运行验证命令
- 必须阅读验证输出，不能假设通过
- 使用 `verification-before-completion` 技能强制执行

**反模式**:
- ❌ "应该可以工作了"
- ❌ "我相信没问题"
- ❌ 没有验证就声称完成

---

### 5. Portable > Specific（可移植优于特定）

**宣言**: *`core/` keeps the semantics portable, while adapters keep platforms productive right now.*

**三层架构**:
```
┌─────────────────────────────────┐
│  Portable Core                   │  ← 平台无关的语义层
│  core/models, skills, policies    │
├─────────────────────────────────┤
│  Target Adapters                 │  ← 平台适配器
│  claude-code, opencode, cursor    │
├─────────────────────────────────┤
│  Project Overlay                 │  ← 项目定制
│  .vibe/overlay.yaml              │
└─────────────────────────────────┘
```

**开发流程**:
1. 在 `core/` 定义可移植语义
2. 在 `adapters/` 添加适配器文档
3. 在 `rules/`/`docs/` 同步 Claude Code 文件
4. 最后扩展 `builder/` 生成器

**反模式**:
- ❌ 硬编码平台特定逻辑
- ❌ 在 `core/` 中添加平台相关代码
- ❌ 不使用配置就添加新功能

---

### 6. Security by Default（安全默认）

**宣言**: *External code must be audited before execution.*

**要求**:
- ✅ 所有外部内容扫描威胁
- ✅ 路径遍历攻击防护
- ✅ SKILL-INJECT 防护机制
- ✅ 白名单目录机制

**安全策略**:
- 外部技能必须通过安全审计
- 只允许预定义的安全目录
- 检测注入攻击模式
- 原子文件操作防止损坏

---

### 7. Progressive Disclosure（渐进式披露）

**宣言**: *Show the right information at the right time.*

**要求**:
- ✅ 根据用户熟练度调整信息密度
- ✅ 新手看到详细说明，专家看到极简提示
- ✅ 按需加载文档和规则

**熟练度级别**:
```python
class DisclosureLevel(Enum):
    NOVICE = "novice"      # 新手：显示详细说明
    INTERMEDIATE = "inter" # 中级：显示摘要
    EXPERT = "expert"      # 专家：显示极简提示
```

---

## Architecture Principles（架构原则）

### 三层运行时架构

| Layer | What | Loaded | Location |
|-------|------|--------|----------|
| **0: Rules** | Core behavior rules | Always | `rules/` |
| **1: Docs** | Reference guides | On demand | `docs/` |
| **2: Memory** | Your project state | Session start | `memory/` |

### SSOT - 单源真理（Single Source of Truth）

**宣言**: *Every piece of information has ONE canonical location.*

| 信息类型 | 权威位置 |
|---------|---------|
| 行为规则 | `rules/behaviors.md` |
| 技能定义 | `skills/*/SKILL.md` + registry |
| 能力层级 | `core/models/tiers.yaml` |
| 项目状态 | `memory/session.md` |
| 安全策略 | `core/security/policy.yaml` |

---

## Decision Framework（决策框架）

### 当面临技术决策时，问自己：

1. **这符合项目愿景吗？**
   - 是否让工作流更结构化？
   - 是否提升生产效率？
   - 是否保持跨平台可移植性？

2. **这遵循核心原则吗？**
   - 是生产优先吗？
   - 是结构化优于提示吗？
   - 是记忆优于智能吗？
   - 是验证优于自信吗？
   - 是可移植优于特定吗？
   - 是安全默认吗？
   - 是渐进式披露吗？

3. **这会增加技术债务吗？**
   - 是否引入不必要的复杂性？
   - 是否破坏现有架构？
   - 是否难以测试和维护？

4. **这对用户友好吗？**
   - 是否易于理解和使用？
   - 错误信息是否清晰？
   - 是否有完善的文档？

---

## Development Checklist（开发检查清单）

### 开始开发前

- [ ] 阅读并理解本文档
- [ ] 确认功能符合项目愿景
- [ ] 检查是否已有类似功能
- [ ] 评估对现有功能的影响

### 设计阶段

- [ ] 设计符合三层架构
- [ ] 确定 SSOT 位置
- [ ] 考虑多平台支持
- [ ] 评估性能影响

### 实现阶段

- [ ] 编写测试先（TDD）
- [ ] 实现功能
- [ ] 添加错误处理
- [ ] 更新文档

### 完成前

- [ ] 所有测试通过
- [ ] 代码审查完成
- [ ] 文档更新完成
- [ ] 性能测试通过
- [ ] 向后兼容性验证

---

## Anti-Patterns（反模式）

### 绝对禁止

1. **破坏向后兼容性**（除非是主版本升级）
2. **添加未经测试的功能**
3. **在 core/ 中添加平台特定代码**
4. **重复信息**（违反 SSOT）
5. **添加"演示级"功能**

### 强烈反对

1. **增加不必要的依赖**
2. **忽视性能**
3. **硬编码敏感信息**
4. **跳过安全审计**

---

## Related Documents（相关文档）

- [Architecture Overview](../docs/dev/architecture.md)
- [Contributing Guide](../CONTRIBUTING.md)
- [Security Policy](../core/security/policy.yaml)

---

## Changelog（修订历史）

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 3.0.0 | 2026-04-05 | Python 版本，新增 Security by Default 和 Progressive Disclosure | @huchen |
| 2.0.0 | 2026-03-29 | 明确项目愿景定位，新增双场景价值、整合过滤器 | @huchen |
| 1.0.0 | 2026-03-12 | 初始版本 | @huchen |

---

**记住：这些原则不是建议，是要求。**

**任何偏离这些原则的开发都必须通过整合过滤器检验。**
