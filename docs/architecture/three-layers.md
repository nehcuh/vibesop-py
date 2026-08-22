# VibeSOP 三层架构

> **版本**: 8.1.0
> **更新时间**: 2026-06-05
> **状态**: ✅ 架构文档化完成 (4 阶段路由级联)

---

## 概述

VibeSOP 采用清晰的三层架构，每层有明确的职责和边界。这种设计确保：
- **模块独立性** - 层与层之间低耦合
- **可扩展性** - 易于添加新平台和新功能
- **可维护性** - 清晰的依赖关系
- **可测试性** - 每层可独立测试

> **定位**: VibeSOP 是 SkillOS（技能操作系统）。核心三层架构分别负责：
> 构建 → 适配 → 路由+编排+管理。自 (v4.3.0+) 起新增 Agent Runtime、
> CLI、集成、安全等横向支撑层。技能代码的最终执行由 AI Agent 完成。

---

## 架构图 (v8.0.0+)

```
┌──────────────────────────────────────────────────────────────────┐
│                         CLI Layer (cli/)                          │
│               vibe route │ orchestrate │ skills │ market          │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                    Agent Runtime Layer (agent/)                   │
│       AgentRouter │ IntentInterceptor │ StepContextInjector       │
│       PlanExecutor │ DecisionPresenter │ SlashCommandExecutor     │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                        Builder Layer (builder/)                   │
│     Manifest │ Renderer │ DynamicRenderer │ DocGenerators         │
│     DocModels │ DocTemplates │ Overlay │ templates/               │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                      Adapter Layer (adapters/)                    │
│         Claude Code │ OpenCode │ Kimi CLI │ (future)              │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                        Core Layer (core/)                         │
│                                                                    │
│  ┌─ Routing ────┐ ┌─ Orchestration ─┐ ┌─ Skills ────────┐        │
│  │ UnifiedRouter │ │ TaskDecomposer   │ │ SkillManager    │        │
│  │ 4-stage pipe │ │ PlanBuilder      │ │ SkillLoader     │        │
│  │ TriageService │ │ MultiIntentDet.  │ │ LifecycleManager│        │
│  └───────────────┘ └─────────────────┘ └─────────────────┘        │
│                                                                    │
│  ┌─ Matching ───┐ ┌─ Optimization ──┐ ┌─ Intelligence ──┐        │
│  │ KeywordMatcher│ │ PreferenceBoost │ │ InstinctLearner  │        │
│  │ TFIDFMatcher │ │ CandidateFilter │ │ MemoryManager    │        │
│  │ Levenshtein  │ │ SkillClusterIdx │ │ SessionAnalyzer  │        │
│  └──────────────┘ └─────────────────┘ └──────────────────┘        │
│                                                                    │
│  ┌─ Config ─────┐ ┌─ Feedback ──────┐ ┌─ Orchestration ─┐        │
│  │ ConfigManager│ │ FeedbackCollector│ │ DegradationMgr  │        │
│  └──────────────┘ └─────────────────┘ └──────────────────┘        │
└──────────────────────────────────────────────────────────────────┘

横向支撑层 (Cross-cutting):
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ Security │ │Installer │ │  Market  │ │Integrations│ │   LLM    │
│ (security)│ │(installer│ │ (market) │ │(integrations│ │  (llm)   │
│          │ │    /)    │ │          │ │   /)     │ │          │
│ Scanner  │ │Pack      │ │Crawler   │ │Health     │ │Anthropic │
│ Auditor  │ │Installer │ │Publisher │ │Monitor    │ │OpenAI    │
│ PathSafe │ │Txnal     │ │          │ │Recommender│ │Ollama    │
│ Rules    │ │InitSup   │ │          │ │Detector   │ │DeepSeek  │
└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

---

## 第零层：CLI + Agent Runtime 层 (cli/ + agent/)

自 (v4.3.0+) 起新增，位于 Core 层之上，提供面向用户和 AI Agent 的入口。

### CLI 层 (cli/)

**职责**: 面向用户的命令行入口。

**核心组件**:
```python
cli/
├── main.py              # vibe route / orchestrate / doctor / status
├── commands/            # 子命令模块
│   ├── skills_cmd.py    # vibe skills list/info/install/optimize
│   ├── market_cmd.py    # vibe market search/install/publish
│   └── ...
├── routing_report.py    # 路由透明度渲染
├── orchestration_report.py # 编排结果渲染
└── confirmation.py      # 用户确认交互
```

### Agent Runtime 层 (agent/)

**职责**: 为 AI Agent 提供 in-process Python API，无需外部 API key。

**核心组件**:
```python
agent/
├── runtime/
│   ├── plan_executor.py         # 多步骤编排执行
│   ├── intent_interceptor.py    # 意图拦截与 slash 命令
│   ├── context_injector.py      # SKILL.md 内容注入
│   └── decision_presenter.py    # 路由决策呈现
├── step_runner.py               # 步骤并行执行引擎
└── __init__.py                  # AgentRouter (复用 Agent 内部 LLM)
```

**关键特性**:
- ✅ 无需外部 API key（in-process 模式下复用 Agent LLM）
- ✅ 直接 Python API（无子进程开销）
- ✅ 与 Agent 会话状态深度集成
- ⚠️ CLI 子进程模式仍需单独配置 LLM

---

## 第一层：核心层 (core/)

### 职责

提供所有核心功能，完全独立于任何平台或适配器。

### 模块结构

#### 1. SkillOS 路由层 (routing/)

**职责**: 将用户请求路由到最合适的技能（SkillOS 智能路由层）

**核心组件**:
```python
core/routing/
├── unified.py           # UnifiedRouter - 4 阶段路由级联
├── triage_service.py    # TriageService - AI语义分流
├── cache.py            # CacheManager - 缓存管理
├── layers.py           # 路由层定义
├── matcher_pipeline.py # 匹配器pipeline
└── conflict.py         # ConflictResolver - 冲突解决
```

**关键特性**:
- 4 阶段路由级联 (Stage 1: 显式覆盖 → Stage 2: 场景+语义索引 → Stage 3: AI 分诊 → Stage 4: 匹配器聚合；终端: 无匹配 / Fallback LLM)
- 智能缓存 (70%+ 命中率)
- 冲突解决策略
- 性能优化 (预热、并行)

#### 2. 技能管理 (skills/)

**职责**: 技能的发现、加载、执行和验证

**核心组件**:
```python
core/skills/
├── manager.py          # SkillManager - 统一技能管理API
├── executor.py         # ExternalSkillExecutor - 外部技能执行
├── workflow.py         # WorkflowEngine - 工作流引擎
├── parser.py           # SkillParser - SKILL.md解析器
├── storage.py          # SkillStorage - 技能存储
└── loader.py           # SkillLoader - 技能加载器
```

**关键特性**:
- 支持内置技能和外部技能包
- 工作流解析和执行
- 安全审计和沙箱执行
- 变量替换和工具调用

#### 3. 匹配算法 (matching/)

**职责**: 实现各种技能匹配算法

**核心组件**:
```python
core/matching/
├── base.py             # IMatcher - 匹配器接口
├── tfidf.py            # TFIDFMatcher - TF-IDF相似度
├── similarity.py       # 余弦相似度计算
├── tokenizers.py       # 文本分词器
└── strategies.py       # 匹配策略
```

**关键特性**:
- 多种匹配算法 (TF-IDF、关键词、模糊)
- 可插拔的匹配器架构
- 性能优化 (缓存、批处理)

#### 4. 优化系统 (optimization/)

**职责**: 优化路由性能和准确率

**核心组件**:
```python
core/optimization/
├── preference.py       # PreferenceBooster - 偏好学习
├── prefilter.py        # CandidatePrefilter - 候选筛选
└── clustering.py       # SkillClusterIndex - 技能聚类
```

**关键特性**:
- 用户偏好学习 (InstinctLearner)
- 候选技能预筛选
- 技能聚类索引

#### 5. 记忆系统 (memory/, instinct/)

**职责**: 管理用户偏好和历史记录

**核心组件**:
```python
core/memory/
├── manager.py          # MemoryManager - 记忆管理
└── storage.py          # 记忆存储

core/instinct/
└── learner.py          # InstinctLearner - 本能学习
```

**关键特性**:
- 长期记忆存储
- 短期会话记忆
- 偏好模式学习

#### 6. 算法库 (algorithms/)

**职责**: 实现高级AI辅助算法

**核心组件**:
```python
core/algorithms/
├── interview/          # 深度访谈算法
└── ralph/              # RALPH持续完成循环
```

**关键特性**:
- Socratic需求澄清
- 持续完成循环
- 多维度评分

#### 7. 支持模块

**配置管理** (config/):
```python
core/config/
├── manager.py          # ConfigManager - 配置管理
└── optimization_config.py # 优化配置
```

**LLM集成** (llm/):
```python
core/llm/
├── anthropic.py        # Anthropic Claude集成
├── openai.py           # OpenAI GPT集成
└── factory.py          # LLM工厂
```

**安全** (security/):
```python
core/security/
├── skill_auditor.py    # 技能安全审计
├── scanner.py          # 威胁扫描
└── path_safety.py      # 路径安全
```

**会话管理** (sessions/):
```python
core/sessions/
├── manager.py          # SessionManager - 会话管理
└── tracker.py          # 工具使用追踪
```

### 依赖规则

**✅ 允许**:
- core/ 内部模块可以相互依赖
- 可以使用标准库和第三方库

**❌ 禁止**:
- 不能依赖 adapters/
- 不能依赖 builder/
- 不能依赖任何平台特定代码

---

## 第二层：适配器层 (adapters/)

### 职责

将核心层功能适配到不同的AI开发平台。

### 模块结构

```python
adapters/
├── base.py             # PlatformAdapter - 适配器基类
├── models.py           # Manifest, RenderResult - 数据模型
├── protocol.py         # 适配器协议
├── claude_code.py      # Claude Code适配器
└── opencode.py         # OpenCode适配器
```

### Claude Code 适配器

**职责**: 生成 Claude Code 平台的配置文件

**生成内容**:
```
~/.claude/
├── CLAUDE.md           # 主入口
├── rules/              # 总是加载的规则
│   ├── behaviors.md
│   ├── routing.md
│   └── skill-triggers.md
├── docs/               # 按需加载的文档
│   ├── safety.md
│   ├── skills.md
│   └── task-routing.md
└── skills/             # 技能定义
    └── [skill-id]/
        └── SKILL.md
```

**核心功能**:
- 从 Manifest 生成配置
- 技能路由配置
- 安全策略配置
- 触发规则配置

### OpenCode 适配器

**职责**: 生成 OpenCode 平台的配置文件

**核心功能**:
- 类似 Claude Code 适配器
- 平台特定的格式转换

### 依赖规则

**✅ 允许**:
- 可以依赖 core/
- 可以使用标准库和第三方库

**❌ 禁止**:
- 不能依赖其他适配器 (adapters/ 之间互不依赖)
- 不能依赖 builder/

### 扩展新平台

添加新平台适配器的步骤:

1. 创建 `adapters/[platform].py`
2. 继承 `PlatformAdapter`
3. 实现 `render_config()` 方法
4. 添加平台特定的模板
5. 更新 `adapters/__init__.py`

---

## 第三层：构建层 (builder/)

### 职责

配置文件的渲染、模板引擎、文档生成。

### 模块结构

```python
builder/
├── manifest.py         # Manifest - 配置清单
├── renderer.py         # Renderer - 渲染器
├── dynamic_renderer.py # DynamicRenderer - 动态渲染
├── doc_generators.py   # 文档生成器
├── doc_templates.py    # 文档模板
├── doc_models.py       # 文档模型
├── overlay.py          # Overlay - 配置覆盖
└── templates/          # Jinja2模板
```

### 核心功能

#### 1. 配置渲染

**Renderer**: 渲染配置文件
```python
renderer = Renderer()
result = renderer.render_config(manifest, output_dir)
```

**DynamicRenderer**: 动态内容渲染
- 规则文件
- 技能文档
- 路由配置

#### 2. 文档生成

**自动生成的文档**:
- 技能目录 (docs/skills.md)
- 路由文档 (docs/task-routing.md)
- 安全指南 (docs/safety.md)
- 行为规则 (rules/behaviors.md)

#### 3. 模板系统

**模板位置**:
```
builder/templates/
├── claude-code/
│   ├── CLAUDE.md.j2
│   ├── rules/
│   │   ├── behaviors.md.j2
│   │   └── routing.md.j2
│   └── docs/
│       ├── skills.md.j2
│       └── task-routing.md.j2
```

### 依赖规则

**✅ 允许**:
- 可以依赖 core/
- 可以依赖 adapters/
- 可以使用标准库和第三方库 (Jinja2)

**❌ 禁止**:
- 不能被 core/ 或 adapters/ 依赖

---

## 层间交互

### 典型流程：技能路由和执行

```
1. 用户请求
   ↓
2. [Adapter] Claude Code 接收请求
   ↓
3. [Core] UnifiedRouter.route()
   ├→ TriageService (AI分流)
   ├→ Matching (TF-IDF, 关键词)
   ├→ Optimization (偏好学习)
   └→ Skills (SkillManager)
   ↓
4. [Core] SkillManager.get_skill_definition()
   ├→ SkillLoader (加载技能)
   ├→ SkillParser (解析工作流)
   └→ SkillAuditor (安全审计)
   ↓
5. [Adapter] 返回工作流定义给 AI Agent
   ↓
6. [Core] AI Agent 执行工作流
   └→ WorkflowEngine.execute()
   ↓
7. [Builder] 生成文档和配置
   └→ Renderer.render_config()
```

### 数据流

```
Manifest (Builder)
    ↓
Adapter.render_config()
    ↓
Core (Skills, Routing)
    ↓
Platform Config Files
```

---

## 架构原则

### 1. 单向依赖

```
Builder → Adapters → Core
```

- Core 不依赖任何其他层
- Adapters 只依赖 Core
- Builder 可以依赖 Adapters 和 Core

### 2. 接口隔离

每层通过清晰的接口交互:
- Core 通过 `IMatcher` 接口扩展匹配器
- Adapters 通过 `PlatformAdapter` 基类扩展
- Builder 通过 Manifest 数据模型传递配置

### 3. 可测试性

- 每层可独立测试
- 使用依赖注入模拟依赖
- 清晰的测试边界

### 4. 可扩展性

- 添加新平台: 创建新 Adapter
- 添加新匹配算法: 实现 IMatcher
- 添加新技能类型: 扩展 SkillManager

---

## 架构验证

### 依赖检查

```bash
# 检查是否有违反架构的依赖
python -m pytest tests/architecture/test_dependencies.py -v
```

### 模块边界

```bash
# 验证模块边界
python -m pytest tests/architecture/test_boundaries.py -v
```

### 架构指标

| 指标 | 目标 | 当前 |
|------|------|------|
| 层间依赖 | 单向 | ✅ 达标 |
| 模块耦合 | 低 | ✅ 达标 |
| 接口清晰度 | 高 | ✅ 达标 |
| 可测试性 | >80% | ✅ 达标 |

---

## 未来演进

### Phase 3: 性能优化

- 优化路由准确率 (85% → 90%+)
- 减少延迟 (<100ms)
- 提高缓存命中率 (70% → 80%+)

### Phase 4: 平台扩展

- 添加 Cursor 适配器
- 添加 Windsurf 适配器
- 添加 generic 适配器

### Phase 5: 高级特性

- 技能市场集成
- 分布式技能执行
- 实时协作支持

---

**更新时间**: 2026-07-21
**版本**: 8.1.0
**状态**: ✅ 架构文档化完成
