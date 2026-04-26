# VibeSOP v5.x → v6.0 评审驱动优化计划

> **Status**: Draft
> **Date**: 2026-04-27
> **Based on**: Kimi 深度评审（修正版）+ DeepSeek 交叉验证 + version_05.md ADR
> **Theme**: 体验闭环 → 技术债控制 → 性能达标 → 生态自举

---

## 评审核心诊断（经交叉验证后的共识）

| 洞察 | 优先级 | 严重性 | 性质 |
|------|--------|--------|------|
| 编排执行闭环缺失（计划生成→确认→...结束） | **P0** | 产品突破点 | 产品逻辑缺失 |
| 代码膨胀加速（53K/15K=3.5x 目标） | **P1** | 技术债累积 | 工程债 |
| Mixin 架构中等复杂度（认知跳转成本） | **P2** | 维持成本 | 架构债 |
| LLM 调用是 P95 路由瓶颈（~220ms/225ms） | **P2** | 性能不达标 | 性能债 |
| 推荐系统硬编码（静态字典无数据驱动） | **P3** | 体验天花板 | 功能深度 |

---

## Phase 0: 架构边界决策（v5 → v6 路线选择）

### 核心问题

PHILOSOPHY.md 明确定义：
> "VibeSOP decides **what skills and in what order**; AI Agent decides **how to execute**."

评审提出的 P0（让 VibeSOP 自动执行编排计划）实质上是在提议跨越这条边界。

### 两条路线

#### 路线 A: 激进跨越（v6.0）
让 VibeSOP 承担执行角色 → 自动加载技能、捕获输出、注入上下文。
- 优势：完整的"编排执行器"体验
- 风险：架构边界重新定义，工作量巨大，平台依赖更深

#### **路线 B: 深化指导（v5.2+）—— 推荐**
不跨越架构边界，但让 PlanExecutor 生成的指导大幅增强：
- **内嵌 SKILL.md 内容**：计划中直接包含每个步骤需要的完整技能文档，Agent 无需手动加载
- **上下文文件注入**：为每个步骤生成前置上下文文件，Agent 只需读取即可获知前置步骤结果
- **`--execute` 模式**：CLI 以流式方式逐步骤输出指导，Agent 逐步骤执行
- **Completion Signal**：标准化"步骤完成"的信号机制，Agent 发出信号后自动获取下一步指南

**决策**：选路线 B。跨越架构边界是 v6.0 级决策，需要新的 ADR。当前在 PHILOSOPHY 边界内做最大程度的体验优化。

---

## Phase 1: 编排体验闭环（P0，Week 1-2）

> 让 ExecutionPlan 不只是展示，而是**可以被 Agent 逐步跟随执行**的完整指南。

### Task 1.1: ExecutionManifest — 可执行计划协议（2 天）

**目标**：PlanExecutor 从"生成文字指南"升级为"生成可执行清单"。

**新数据模型** (`src/vibesop/core/models.py`)：

```python
@dataclass
class StepManifest:
    """一个编排步骤的完整执行清单"""
    step_number: int
    skill_id: str
    skill_name: str
    skill_path: Path        # SKILL.md 在磁盘上的路径
    skill_content: str      # 完整的 SKILL.md 内容（已内嵌，无需 Agent 加载）
    input_context: str      # 前置步骤的输出摘要（作为本步骤的输入上下文）
    output_slot: str        # 本步骤输出的存储槽（如 "architecture_analysis"）
    completion_marker: str  # Agent 完成后需输出的标记文本
    instruction: str        # 精简后的执行指令

@dataclass
class ExecutionManifest:
    """完整的编排执行清单"""
    plan_id: str
    original_query: str
    strategy: str           # sequential | parallel | mixed
    steps: list[StepManifest]
    context_file: Path      # .vibe/plans/{plan_id}/context.md（总上下文文件）
```

**改造 Place**：
- `src/vibesop/core/models.py`：新增 `StepManifest`、`ExecutionManifest`
- `src/vibesop/agent/runtime/plan_executor.py`：`build_guide()` → `build_manifest()`，返回 `ExecutionManifest`
- `src/vibesop/core/skills/loader.py`：新增 `read_skill_content(skill_id) -> str`

**验收标准**：
- `build_manifest(plan)` 返回的 `ExecutionManifest` 中每个 `StepManifest.skill_content` 包含完整 SKILL.md
- 上一个步骤的 `output_slot` 与下一个步骤的 `input_context` 有对应关系

### Task 1.2: StepContextInjector — 上下文注入器（1 天）

**目标**：让 Agent 不需要手动传递步骤间的结果。

**新模块** (`src/vibesop/agent/runtime/context_injector.py`)：

```python
class StepContextInjector:
    """管理编排执行中的上下文传递"""

    def prepare_step_context(self, manifest: ExecutionManifest, current_step: int) -> str:
        """为第 current_step 步准备完整的上下文 prompt"""
        # 1. 查找所有依赖于本步骤输入的前置步骤
        # 2. 读取前置步骤的输出文件
        # 3. 组装：前置结果 + 本步骤 SKILL.md 内容 + 本步骤指令

    def save_step_output(self, plan_id: str, step_number: int, content: str):
        """Agent 提交步骤输出后，保存到磁盘供后续步骤读取"""
        # 写入 .vibe/plans/{plan_id}/step_{step_number}_output.md

    def build_sequence_file(self, manifest: ExecutionManifest) -> Path:
        """生成本地执行序列文件，Agent 只需逐步骤读取"""
        # 写入 .vibe/plans/{plan_id}/execution_sequence.md
        # 包含所有步骤的完整上下文，已解决所有依赖
```

**验收标准**：
- `build_sequence_file()` 生成的文件包含所有步骤的完整 SKILL.md 内容和数据依赖说明
- Agent 只需顺序读取该文件即可执行全部步骤

### Task 1.3: CLI `--execute` 模式（1 天）

**目标**：用户确认编排计划后，自动进入流式执行模式。

**改造文件**：`src/vibesop/cli/main.py`

```
vibe route "分析架构并生成测试"
  ↓ 展示编排计划
  ↓ 用户选择 [Execute] [Confirm]
  ↓ --execute 模式：

  正在执行第 1/3 步: 架构分析 (riper-workflow)
  ├─ SKILL.md 已加载
  ├─ 指令: 分析 src/vibesop 目录的架构...
  └─ 完成后请标记: [StepCompleted:1]

  [等待 Agent 输出...]

  ✅ 第 1/3 步完成
  
  正在执行第 2/3 步: 代码评审 (superpowers/review)
  ├─ SKILL.md 已加载
  ├─ 输入上下文: 第1步的架构分析结果
  ├─ 指令: 基于架构分析结果评审代码质量...
  └─ 完成后请标记: [StepCompleted:2]

  ...
```

**实现**：
- `--execute` flag on `vibe route`
- `_handle_orchestrated_result()` 检测 `--execute` 时进入 `_execute_plan_interactive()`
- 每个步骤：
  1. 创建 `ProgressDisplay`（Rich Live）
  2. 输出包含 `input_context` + `skill_content` + `instruction` 的完整 prompt
  3. 等待用户/Agent 输入（实际上是让 Agent 在确认进入下一步后继续）
  4. 保存步骤输出到 `.vibe/plans/{plan_id}/`

**注意**：真正自动化的执行引擎（无需人类介入的 step-by-step）需要跨架构边界。`--execute` 模式提供的是**引导式手动执行**（Agent 无需加载技能文件或查找上下文），这是体验闭环而非架构跨越。

**验收标准**：
- `vibe route "query" --execute` 确认计划后进入分步执行模式
- 每个步骤的 prompt 包含该步骤的 SKILL.md 内容和前置步骤的上下文

### Task 1.4: Completion Signal 标准化（0.5 天）

**目标**：定义 Agent 信号约定，让 step completion 可被自动检测。

**标准**：
```
[StepCompleted:{step_number}] {summary}
```
或（避免与代码注释混淆）：
```
<!-- StepCompleted:1 --> 完成架构分析，识别出9个核心模块...
```

**改造**：
- `PlanExecutor._build_prompt()` 在每步指令末尾添加：
  ```
  完成后必须输出: <!-- StepCompleted:{step_number} --> 并附上结果摘要
  ```
- `StepContextInjector` 解析 Agent 输出的 completion marker，提取摘要作为上下文

**验收标准**：
- 每个步骤指令末尾包含标准化的 completion marker 指令

---

## Phase 2: 代码瘦身（P1，Week 2-4）

> 目标：53,052 → ~38,000 行（-15K，务实目标；评审建议的 35K 需更长时间）

### Task 2.1: skills_cmd.py 拆分（2 天）

**当前**：1,667 行，是最大单体 CLI 文件。

**拆分为**：
| 新文件 | 内容 | 估计行数 |
|--------|------|---------|
| `skills_rate_cmd.py` | rate/ratings 命令 | ~300 |
| `skills_recommended_cmd.py` | recommended 命令 | ~250 |
| `skills_suggest_cmd.py` | suggestions/suggest 命令 | ~250 |
| `skills_cmd.py`（精简） | scope/enable/disable/list/status 等生命周期命令 | ~867 |

**注意**：`skills_cmd.py` 中的 `rate`/`ratings`/`recommended`/`suggestions` 命令已在本次对话中新增，功能独立，适合拆分。

**验收标准**：
- 原 `skills_cmd.py` 中不存在 `rate`/`ratings`/`recommended`/`suggest`/`suggestions` 的 Typer 命令注册
- 新文件中的命令通过 `subcommands/__init__.py` 注册，CLI `vibe skills rate` 等命令正常

### Task 2.2: workflow.py 合并到 sessions.py（1 天）

**当前**：`workflow.py`（1,136 行）和 `sessions/context.py`（699 行）有功能重叠。

**分析**：
- `workflow.py` 的 `WorkflowEngine`（654 行）是测试/验证用的工作流执行引擎，但核心路由并未使用
- `workflow.py` 的 `parse_workflow_from_markdown()`（196 行）解析 SKILL.md 中的工作流定义
- `sessions/context.py` 管理会话上下文

**方案**：
- `WorkflowEngine` → 移到 `tests/support/workflow_engine.py`（仅测试用）
- `parse_workflow_from_markdown()` → 移到 `core/skills/parser.py`
- `Workflow`/`WorkflowStep`/`ExecutionContext`/`WorkflowResult` → 移到 `core/models.py`

**验收标准**：
- `core/skills/workflow.py` 不存在
- 所有原有功能通过新位置可访问
- 现有测试通过

### Task 2.3: 实验性模块清理（0.5 天）

**待评估模块**：

| 模块 | 路径 | 状态 | 行动 |
|------|------|------|------|
| ralph/deslop | `core/algorithms/ralph/deslop.py` (2.7KB) | 仅算法内部导入，无外部消费者 | 检查 `AlgorithmRegistry` 是否注册，未注册则归档到 `docs/archive/` |
| interview/ambiguity | `core/algorithms/interview/ambiguity.py` (2.8KB) | 仅算法内部导入，无外部消费者 | 同上 |

**操作**：
1. 搜索 `AlgorithmRegistry.register()` 调用中是否包含这两个模块
2. 如未注册：从 `core/algorithms/__init__.py` 移除导出，归档文件
3. 如已注册：保留

**验收标准**：
- 未使用的实验性模块不再从 `core/algorithms/__init__.py` 导出

### Task 2.4: memory/ → sessions/ 统一（1 天）

**当前**：`core/memory/`（4 个文件，~555 行）和 `core/sessions/`（5+ 个文件）有功能重叠。

| 模块 | 文件 | 行数 | 外部消费者 |
|------|------|------|-----------|
| memory | `manager.py` (317), `base.py` (126), `storage.py` (94) | 537 | 仅 `unified.py`（2 处） |
| sessions | `context.py` (699), `tracker.py` (280), 其他 | ~1,200 | `agent/__init__.py`, `unified.py`, `cli/session_cmd.py` |

**方案**：
- `MemoryManager` 的功能合并到 `SessionContext`（会话数据存储是更自然的归属）
- `memory/` 目录删除，`unified.py` 中的 2 处导入改为 `from vibesop.core.sessions import ...`
- `memory/` 中的 `StorageBackend` 抽象保留在 `sessions/storage.py`

**验收标准**：
- `core/memory/` 目录不存在
- `unified.py` 不再导入 `vibesop.core.memory`
- 原有功能通过 `core/sessions/` 可访问

### Task 2.5: Mixin → 独立服务（2 天）

**目标**：将 3 个 Mixin 转变为独立服务类，让 `UnifiedRouter` 成为协调器。

**当前**：
```python
class UnifiedRouter(RouterStatsMixin, RouterExecutionMixin, RouterOrchestrationMixin):
```

**改造为**：
```python
class UnifiedRouter:
    def __init__(self, ...):
        self._stats_service = RoutingStatisticsService(self)
        self._execution_engine = RoutingExecutionEngine(self)
        self._orchestration_engine = OrchestrationEngine(self)

    def _route(self, query, candidates, context):
        return self._execution_engine.execute_layers(query, candidates, context)

    def orchestrate(self, query, ...):
        # 委托给 orchestration_engine
```

**新文件**：
- `core/routing/stats_service.py`（从 `stats_mixin.py` 重构）
- `core/routing/execution_engine.py`（从 `execution_mixin.py` 重构）
- `core/routing/orchestration_engine.py`（从 `orchestration_mixin.py` 重构）

**优势**：
- 显式依赖：不再有隐式 Mixin 方法调用
- 可独立测试：每个服务类可 mock 后单独测试
- 认知复杂度：开发者只需关注主类 + 3 个明确的服务委托

**验收标准**：
- `stats_mixin.py`、`execution_mixin.py`、`orchestration_mixin.py` 不存在
- `UnifiedRouter` 不再使用 Mixin 继承
- 所有现有路由功能通过委托模式保持不变

---

## Phase 3: 路由性能 P95 <100ms（P2，Week 3-4）

> 当前 P95 225ms，瓶颈是 AI Triage LLM 调用（~220ms）。

### Task 3.1: 短查询绕过 AI Triage（0.5 天）

**策略**：查询长度 < 10 词时，跳过 AI Triage（Layer 2），直接走 Keyword/TF-IDF。

**理由**：短查询通常是明确的技能名或领域关键词（如 "debug memory leak"、"run tests"），不需要 LLM 语义理解。LLM 的价值在于复杂的自然语言查询（"我改了一个数据库迁移文件，想确保不会破坏现有数据，应该用什么技能？"）。

**实现** (`src/vibesop/core/routing/_layers.py`)：
```python
def try_ai_triage_layer(query: str, candidates, ...):
    if len(query.split()) < 10:
        return None  # 绕过 LLM，走传统匹配
    # ... 现有 LLM 逻辑
```

**验收标准**：
- "run tests"（2 词）→ Layer 3+ 匹配
- "帮我分析现有项目的架构并生成测试覆盖计划"（12 词，复杂意图）→ Layer 2 AI Triage

### Task 3.2: AI Triage 缓存预热（0.5 天）

**策略**：在 `vibe doctor` 或 `vibe start` 时，预先计算 Top 50 高频查询的 AI Triage 结果。

**实现**：
- `CacheManager` 新增 `precompute_top_queries(queries)` 方法
- 从 `AnalyticsStore` 获取最近 1000 个查询，按频率排序取 Top 50
- 对每个查询调用 `TriageService.try_ai_triage()` 并写入缓存

**CLI**：
```bash
vibe warm-cache           # 手动预热
vibe warm-cache --refresh # 强制刷新
```

**验收标准**：
- 预热后，Top 50 查询的 AI Triage 层返回时间 < 5ms（缓存命中）

### Task 3.3: EmbeddingMatcher 完全延迟加载（0.5 天）

**当前**：`EmbeddingMatcher` 在 `__init__` 中被 eager 创建（如果 `enable_embedding=True`）。
**改造为**：仅在首次需要时才加载（在 `_warm_up_matchers()` 中懒初始化）。

**实现**：
- `UnifiedRouter.__init__`：仅存储 `enable_embedding` 标志，不构造
- `_warm_up_matchers()`：在 warming 时根据标志构造
- 节省初始化时间：~100-200ms（SentenceTransformer 模型加载）

**验收标准**：
- `enable_embedding=True` 时首次路由仍需 warm up，但 __init__ 时间显著缩短

### Task 3.4: 路由时序监控（0.5 天）

**新功能**：为路由增加实时 P95 追踪。

**新增**：`RoutingPerfMonitor` (`core/routing/perf_monitor.py`)
- 追踪最近 100 次路由的 duration_ms
- 实时计算 P50、P95、P99
- 在 `vibe route-stats` 中展示性能百分位

**验收标准**：
- `vibe route-stats` 显示最近 100 次路由的 P95 延迟
- 达到目标时触发提示（P95 < 100ms → "性能达标 ✅"）

---

## Phase 4: SkillMarket 数据驱动（P3，Week 4-5）

### Task 4.1: 推荐系统数据驱动化（1 天）

**当前**：`SkillRecommender` 使用硬编码 `STACK_RECOMMENDATIONS` 字典。

**改造为**：基于 `AnalyticsStore` 的实际使用数据。

```python
class SkillRecommender:
    def _build_recommendations_from_analytics(self):
        """从 AnalyticsStore 构建推荐数据"""
        # 1. 按技术栈分组所有使用记录
        # 2. 统计每个技术栈中技能的使用频率
        # 3. 生成动态推荐（替换硬编码字典）

    def recommend_for_project(self, project_path):
        # 1. 检测项目技术栈（保持）
        # 2. 从 AnalyticsStore 获取该技术栈的高频使用技能（新增）
        # 3. 结合质量评分（SkillRatingStore）排序（新增）
        # 4. 检测缺失技能（保持）
```

**保留硬编码作为冷启动兜底**：当 AnalyticsStore 为空时 fallback 到 `STACK_RECOMMENDATIONS`。

**验收标准**：
- 使用数据分析驱动的推荐，而非仅静态字典
- 冷启动场景（无数据）时 fallback 到硬编码

### Task 4.2: Market Search 质量排序（0.5 天）

**当前**：`vibe market search` 按 GitHub Stars 排序。

**改造为**：综合评分 = GitHub Stars (30%) + 本地评分 (40%) + 使用频率 (30%)。

**实现** (`market_cmd.py`):
```python
def _enrich_with_local_quality(results, analytics, ratings):
    for result in results:
        skill_id = result.skill_id_from_repo()
        result.quality_score = (
            _normalize_stars(result.stars) * 0.3 +
            ratings.get_avg_rating(skill_id) * 0.4 +
            analytics.get_usage_frequency(skill_id) * 0.3
        )
```

**验收标准**：
- `vibe market search` 结果按综合评分排序，而非仅 GitHub Stars

### Task 4.3: 项目结构检测增强（0.5 天）

**当前**：`ProjectAnalyzer` 检测 `pyproject.toml`、`package.json` 等。

**增强**：检测更多技术标记并提供精准推荐。
```python
PROJECT_SIGNALS = {
    "Dockerfile": ["docker", "deployment", "containerization"],
    "docker-compose.yml": ["docker", "orchestration"],
    ".github/workflows/": ["ci_cd", "github_actions"],
    "migrations/": ["database", "schema_migration"],
    "kubernetes/": ["k8s", "deployment"],
    "Makefile": ["automation", "build"],
    "requirements*.txt": ["python", "dependency_management"],
    "Cargo.toml": ["rust", "systems_programming"],
}
```

**验收标准**：
- 在包含 `Dockerfile` 的项目中，`vibe skills recommended` 推荐 Docker 相关技能

---

## Phase 5: 文档清洁（P3，Week 5）

### Task 5.1: 文档去重（1 天）

**问题**：README、PHILOSOPHY、PROJECT_STATUS 中有大量重叠的架构描述。

**操作**：
- README → 用户导向（安装、使用、快速开始）
- PHILOSOPHY → 设计哲学（唯一 source of truth）
- PROJECT_STATUS → 删除（内容已在 ROADMAP 中）
- 历史文档 `docs/archive/` → 移到 `docs/history/` 并加 ARCHIVED: 前缀

### Task 5.2: 计划文档归档（0.5 天）

- `.vibe/plans/` 中 11 个计划文件 → 归档 6 个月前的文件
- 活跃的保留：`v5-quality-sprint.md`、`v6-review-driven-optimization.md`

---

## 各 Phase 代码量影响预估

| Phase | 删除行数 | 新增行数 | 净变化 |
|-------|---------|---------|--------|
| **Phase 1**（编排闭环） | ~0 | +1,200 | +1,200 |
| **Phase 2**（瘦身） | ~6,000 | +500 | -5,500 |
| **Phase 3**（性能） | ~100 | +400 | +300 |
| **Phase 4**（市场） | ~200 | +600 | +400 |
| **Phase 5**（文档） | ~800 | +200 | -600 |
| **合计** | **~7,100** | **+2,900** | **-4,200** |

目标：53,052 → ~48,850（-8%，务实目标；评审建议的 35K 需要更长时间的重构）

---

## 执行顺序

```
Week 1-2: Phase 1（编排闭环）
Week 2-3: Phase 2 Task 2.1 + 2.3（快速瘦身）
Week 3-4: Phase 2 Task 2.2 + 2.4（重构瘦身）+ Phase 3（性能）
Week 4-5: Phase 2 Task 2.5（Mixin 重构）+ Phase 4（市场）
Week 5:   Phase 5（文档）
```

---

## 关键风险

1. **Phase 1 体验闭环 ≠ 架构跨越**：`--execute` 模式仍是引导式手动执行，真正的自动化执行需要 v6.0 ADR
2. **Phase 2 重构可能引入回归**：需要完善的集成测试覆盖（当前编排层测试不足）
3. **Phase 3 短查询绕过 AI Triage**：阈值（10 词）需要根据实际数据调整，可能误伤复杂短查询

---

## ADR 决策记录（已确认 2026-04-27）

1. **Phase 1 执行模式** → 路线 B（深化指导）。不跨越 PHILOSOPHY.md 架构边界。PlanExecutor 增强为可执行清单，但 Agent 自己执行。自动执行引擎留到 v6.0。
2. **代码瘦身目标** → 务实目标：-4,200 行（53,052 → ~48,850）。不删除 WorkflowEngine 或实验模块（需再评估后决定）。
3. **Mixin 重构** → 执行。3 个 Mixin → 3 个独立服务类。接受 +200 行 boilerplate 换取可测试性和认知清晰度。
