# VibeSOP 深度评审优化规划

> **Status**: Active
> **Date**: 2026-04-25
> **Based on**: 深度代码 + 文档审查（覆盖 16000+ 行源码、2007 测试、100+ 文档）
> **Related**: post-review-optimization-plan.md, v5-quality-sprint.md, version_05.md ADR
> **Theme**: 止血 → 清债 → 加固 → 产品化

---

## 评审结论摘要

```
项目定位：  Skill Operating System（路由 + 编排 + 生命周期管理）—— 精准
架构质量：  80 分。管线分层、回退路径、安全保障均设计良好
主要矛盾：  代码已实现 80%，用户只感知到 30%
核心债务：  类型安全、代码重复、枚举混乱、测试缺口、CLI 暴露不足
```

---

## 优先级框架

```
P0 (立即，本周)     — 测试失败、产品谎报、链路断裂
P1 (本月，Week 1-3) — 质量债、透明度、编排水线
P2 (下月，Week 3-5) — 架构一致性、代码瘦身
P3 (远期)          — 产品方向决策、SkillMarket 产品化
```

---

## Phase 0: 立即修复（P0，0.5 天）

> 阻塞性问题，不修则后续所有验证不可信。

### Task 0.1: 修复测试失败 🔴

**现状**：
```
FAILED tests/agent/runtime/test_slash_interception.py::TestIntentInterceptorSlashCommands::test_slash_command_with_context
TypeError: IntentInterceptor.should_intercept() got an unexpected keyword argument 'context'
1 failed, 158 passed
```

**根因**: `should_intercept()` 签名变更后测试未同步更新，调用了已移除的 `context=` 参数。

**行动**:
```bash
# 1. 确认当前 should_intercept() 签名
grep -n "def should_intercept" src/vibesop/agent/runtime/intent_interceptor.py

# 2. 修复测试调用
# tests/agent/runtime/test_slash_interception.py:83
# 移除 context= 参数，或补上缺失参数
```

**验收**: `uv run pytest tests/agent/runtime/ -q` 全部通过，36 个测试 0 失败。

### Task 0.2: 版本号一致性

> 来自 `post-review-optimization-plan.md` Phase 0，确认并执行。

**现状**: `_version.py` = 4.3.0，但 PROJECT_STATUS.md 声称 4.4.0 已发布。

**行动**:
- [ ] 确认决策：保持 `_version.py` 4.3.0，修正所有文档
- [ ] `PROJECT_STATUS.md` 4.4.0 → 标注为「开发中」
- [ ] `PHILOSOPHY.md`、`ROADMAP.md`、`README.md` 统一版本号
- [ ] `CHANGELOG.md` 最新条目标注 unreleased

**验收**: `grep -r "4\.[34]\.0" docs/ README.md --include="*.md" | grep -v CHANGELOG` 统一。

---

## Phase 1: 消除虚假完成态（P0，Week 1）

> 来自 `v5-quality-sprint.md` Phase 1，此处只列出**评审视角下新增或补充**的项。

### Task 1.1: 代码重复消除 🔴 新增

**发现**: 两处独立定义了相似的关键词/模式表。

| 位置 | 定义 | 行号 |
|------|------|------|
| `agent/runtime/intent_interceptor.py` | `MULTI_INTENT_PATTERNS`、`EXPLICIT_SKILL_PATTERNS` | 97-127 |
| `core/orchestration/task_decomposer.py` | `INTENT_PATTERNS`、`MULTI_INTENT_KEYWORDS` | 内部常量 |

**行动**:
```python
# 方案: 抽取到公共模块 src/vibesop/core/orchestration/patterns.py
# intent_interceptor.py 和 task_decomposer.py 都从此处 import
```

**验收**: 两个模块的 import 来源统一，关键词定义只有一份。

### Task 1.2: RoutingLayer 枚举修复 🔴 新增

**发现**: 三个不一致：

1. `RoutingLayer.layer_number`: `AI_TRIAGE=2` 但 `_LAYER_PRIORITY` 将其放在 `SCENARIO` 之后
2. `RoutingLayer.FALLBACK_LLM` 定义了但**从未被任意层使用**（代码中无 `RoutingLayer.FALLBACK_LLM` 赋值点）
3. `RoutingLayer.CUSTOM` 定义了但未在 `_LAYER_PRIORITY` 中注册

**行动**:
- [ ] `_LAYER_PRIORITY` 排序与 `RoutingLayer.layer_number` 保持一致
- [ ] 如果 FALLBACK_LLM 用于 `--explain` 展示，确认其赋值逻辑存在；否则标注为预留或移除
- [ ] CUSTOM 加入 `_LAYER_PRIORITY`

**验收**: `RoutingLayer` 枚举值、`_LAYER_PRIORITY` 列表、实际 `_route()` 执行顺序三者一致。

### Task 1.3: 编排 CLI 命令补齐 🔴 新增

**发现**: `TaskDecomposer`、`MultiIntentDetector`、`PlanBuilder` 全部实现且测试通过，但**没有 CLI 命令**。

```bash
# 这些应存在的命令：
vibe orchestrate "分析架构并提出优化建议"    # → 一站式编排
vibe decompose "先测试再审查最后部署"        # → 仅分解
vibe plan "重构模块并添加文档"               # → 仅构建计划
```

**行动**:
- [ ] `cli/main.py` 添加 `orchestrate` 命令（调用 `router.orchestrate()`）
- [ ] `cli/main.py` 添加 `decompose` 命令（调用 `TaskDecomposer`）
- [ ] 支持 `--strategy=sequential|parallel|auto` 和 `--format=json`
- [ ] 更新 `docs/user/CLI_REFERENCE.md`

**验收**: `vibe orchestrate "分析并测试"` 返回完整编排结果。

---

## Phase 2: 质量债清理（P1，Week 1-3）

> 来自 `post-review-optimization-plan.md` Phase 2，此处合并。

### Task 2.1: Lint 清零（1 天）

**现状**: `uv run ruff check` 输出 All checks passed ✅。Lint 已清零，标记完成。

**行动**: 确保 pre-commit hook 已配置硬阻断。

**验收**: ✅ 已完成。

### Task 2.2: 测试覆盖率达标（3 天）

**现状**: 全量运行 2007 测试收集，覆盖率 74%（full run）。`--co` 显示 18.81% 是误报（collect only 模式不计实际执行）。

**按模块优先级**:

| 优先级 | 模块 | 理由 |
|--------|------|------|
| P0 | `core/orchestration/` | 编排是默认模式 |
| P0 | `agent/runtime/` | v4.3 核心交付 |
| P1 | `adapters/` | 平台适配器 |
| P1 | `installer/` | 一键安装核心卖点 |

**行动**:
```bash
# 1. 生成精确覆盖率数据
uv run pytest --cov=src/vibesop --cov-report=term-missing -q 2>&1 | grep "%"

# 2. 识别覆盖率 <50% 且代码量 >100 行的模块
# 3. 优先补核心模块
```

**验收**: `pytest --cov` 报告 ≥80%，无关键模块 <50%。

### Task 2.3: 性能 — P95 延迟达标（3 天）

**现状**: 路由 P95 ~225ms，目标 <100ms。

**新增发现**: `EmbeddingMatcher` 首次 warm-up 占 150ms+，依赖 `sentence-transformers` 可选安装。如未安装，matcher 静默跳过——但冷启动判断在 `_get_cached_candidates()` 中，不在 `route()` 显式路径上。

**行动**:
1. 确认 `_warm_up_matchers` 在 `UnifiedRouter.__init__` 中被调用且不阻塞
2. 将 `routing_config` 缓存为实例属性（当前每次 `route()` 重新解析 YAML）
3. 增加 AI Triage 结果缓存（相似 query 语义去重）
4. 对未安装 `sentence-transformers` 的环境确保 GracefulDegradation 显式日志

**验收**: `python -m timeit` 基准测试 P95 <100ms。

---

## Phase 3: 编排水线加固（P1，Week 2-4）

### Task 3.1: 封装泄漏修复（1 天）

> 来自 `post-review-optimization-plan.md` Task 3.1。

**问题**: `PlanBuilder.build_plan()` 调用 `self._router._route()`。

**修复**:
```python
# UnifiedRouter 新增公共方法
def route_single(self, query: str, context=None) -> RoutingResult:
    """Public single-skill entry point for composition."""
    return self._route(query, context=context)
```

### Task 3.2: confirmation_mode 双模式统一（2 天）

**新增发现**: `confirmation_mode` 仅在单技能路由中生效，编排模式走的是独立的确认逻辑（在 `_render_compact_orchestration` 中）。两个确认逻辑不一致：

| 模式 | confirmation_mode | 行为 |
|------|------------------|------|
| 单技能 | always/never/ambiguous_only | 展示候选 → 用户选择 → 确认 |
| 编排 | 无配置控制 | 始终展示 plan → 确认/编辑/跳过 |

**行动**:
- [ ] 统一编排模式使用 `routing.confirmation_mode` 配置
- [ ] `confirmation_mode: never` → 编排自动执行不弹确认
- [ ] `confirmation_mode: ambiguous_only` → 仅在置信度 < `auto_select_threshold` 时弹确认

### Task 3.3: 编排透明度注入（2 天）

**问题**: `orchestrate()` 的 reasoning 信息（为什么这样分解、为什么选这些技能）在 AI Agent 集成时不传递。

**行动**:
- [ ] `SkillInjector` 注入内容增加 `detected_intents: list`、`reasoning: str`
- [ ] `ExecutionPlan` 增加 `decomposition_rationale` 字段
- [ ] `PlanExecutor` 生成指南时包含推理上下文

### Task 3.4: TaskDecomposer 规则回退增强（1 天）

**问题**: `_fallback_decomposition` 依赖硬编码 32 个关键词，大量中文查询误判为 single task。

**行动**:
- [ ] 从 45+ 技能的 `trigger_when` 字段动态提取关键词表
- [ ] 增加技能名直接映射（query 中出现 `ralph` → 识别为 ralph 技能调用）
- [ ] 回退结果标注 `source: rule_fallback` 便于质量追踪

### Task 3.5: 反馈闭环打通（2 天）

**发现**: `AnalyticsStore` 存储执行记录 → `FeedbackCollector` 收集满意度 → 但链路是否流入 `PreferenceBooster` 形成闭环未经验证。

**行动**:
- [ ] 端到端验证：`vibe route "review my code"` → 选择 skill → 记录 analytics → 下次同类 query 置信度提升
- [ ] 如果链路断裂，修复 `AnalyticsStore → PreferenceBooster` 的数据流
- [ ] 编写集成测试：`test_feedback_loop_closed.py`

---

## Phase 4: 架构一致性修复（P2，Week 3-5）

### Task 4.1: Mixin → Protocol 类型安全（2 天）🆕 新增

**发现**: `UnifiedRouter` 通过 `RouterStatsMixin`、`RouterExecutionMixin`、`RouterOrchestrationMixin` 三层继承，大量 `# type: ignore[attr-defined]`。

**方案**: 引入 `Protocol` 定义公共接口契约。

```python
# src/vibesop/core/routing/_protocols.py (新建)
from typing import Protocol

class RoutingCore(Protocol):
    def _route(self, query: str, context=None) -> RoutingResult: ...
    def _get_candidates(self) -> list[dict]: ...
    def _build_result(self, ...) -> RoutingResult: ...

class OrchestrationCapable(Protocol):
    def orchestrate(self, query: str, context=None, callbacks=None) -> OrchestrationResult: ...
    def _get_orchestration(self) -> OrchestrationService: ...
```

**行动**:
- [ ] 新建 `_protocols.py`，定义 `RoutingCore`、`OrchestrationCapable`、`StatsProvider` 协议
- [ ] `_layers.py`、`_pipeline.py` 的函数签名使用 Protocol 而非 `Any`
- [ ] 逐步移除 `# type: ignore[attr-defined]`

### Task 4.2: SkillDefinition 类型安全化（0.5 天）

> 来自 `post-review-optimization-plan.md` Task 4.1。

```python
# models.py
class SkillDefinition(BaseModel):
    lifecycle: SkillLifecycle = Field(default=SkillLifecycle.ACTIVE)
```

### Task 4.3: Metadata 类型统一（0.5 天）

> 来自 `post-review-optimization-plan.md` Task 4.2。

`SkillDefinition.metadata: dict[str, str|int|float|bool]` vs `SkillRoute.metadata: dict[str, Any]` → 统一为 `dict[str, Any]`。

### Task 4.4: UnifiedRouter 公共 API 梳理（1 天）

> 来自 `post-review-optimization-plan.md` Task 4.3。

**行动**:
- [ ] 梳理所有外部对 `UnifiedRouter` 属性的直接访问
- [ ] 需要外部访问的方法升级为公共 API
- [ ] 纯内部方法加 `_` 前缀并在 `__all__` 中排除

---

## Phase 5: 架构瘦身（P3，远期）

> 来自 `post-review-optimization-plan.md` Phase 5。

### Task 5.1: 废弃代码清理

**评审确认以下模块的活跃状态**:

```bash
# 检查是否有调用方
grep -r "from vibesop.core.checkpoint" src/
grep -r "from vibesop.core.experiment" src/
grep -r "from vibesop.core.badges" src/
```

无调用方 → 直接移除。有调用方但功能边际 → 标记 deprecated。

### Task 5.2: CLI 命令分层

30+ 命令文件，按使用频率分层：
- **Always Load**: `route`, `doctor`, `version`, `skill`
- **Lazy Load**: `badges`, `deviation`, `market`, `experiment`, `tools`, `matcher`

---

## Phase 6: 产品方向决策（P3，需讨论）

> 来自 `post-review-optimization-plan.md` Phase 6 + 评审新增。

### 待决策

| # | 问题 | 选项 | 评审视角建议 |
|---|------|------|------------|
| 1 | VibeSOP 是「薄路由层」还是「厚 OS」？ | A: 保持路由定位；B: 继续加厚 | 推荐 B。当前代码体量已经「厚」了，架构上应承认这个事实并做好模块化，而非假装还薄 |
| 2 | 编排能力 AI Agent 是否真的会使用？ | 需要验证 | Agent 拿到 `ExecutionPlan` 后实际上是自己再分析一遍还是真的按计划执行？需埋点统计 |
| 3 | 「只路由不执行」边界 | 反馈闭环需要执行数据 | 不改变定位的前提下，在 `AnalyticsStore` 收集执行结果标记即可，不需自己执行 |
| 4 | SkillMarket 产品化时机 | v5.1 vs 更晚 | 当前 `market search` 可做但仅有骨架。需社区规模支撑。建议 v5.1 只做评分系统，市场等到有 50+ 外部技能再开放 |

---

## 执行时间线

```
Week 1              Week 2              Week 3              Week 4              Week 5
├───────────────────┼───────────────────┼───────────────────┼───────────────────┤
│ Phase 0           │                   │                   │                   │
│ 修复测试+版本    │                   │                   │                   │
├───────────────────┤                   │                   │                   │
│ Phase 1           │                   │                   │                   │
│ 去重+枚举+CLI    │                   │                   │                   │
├───────────────────┼───────────────────┤                   │                   │
│                   │ Phase 2           │                   │                   │
│                   │ 质量债清理        │                   │                   │
│                   │ Lint ✅ + Cov + Perf│                │                   │
├───────────────────┼───────────────────┼───────────────────┤                   │
│                   │                   │ Phase 3           │                   │
│                   │                   │ 编排水线加固      │                   │
│                   │                   │ 封装+确认+透明度  │                   │
├───────────────────┼───────────────────┼───────────────────┼───────────────────┤
│                   │                   │                   │ Phase 4           │
│                   │                   │                   │ 架构一致性         │
│                   │                   │                   │ Protocol+API     │
└───────────────────┴───────────────────┴───────────────────┴───────────────────┘

Phase 5 & 6: 远期，不纳入本轮
```

---

## 成功标准

- [ ] `uv run pytest tests/agent/runtime/ -q` 36/36 通过
- [ ] `uv run ruff check` 输出 0 ✅ 已达
- [ ] `pytest --cov` ≥80%
- [ ] 路由 P95 <100ms
- [ ] 所有文件版本号统一
- [ ] `vibe orchestrate "分析并测试"` CLI 端到端可用
- [ ] `confirmation_mode` 在单技能 + 编排双模式下行为一致
- [ ] `FeedbackCollector → PreferenceBooster` 数据流闭环经验证
- [ ] 编排回退路径（无 LLM）处理 80%+ 多意图查询
- [ ] `RoutingLayer` 枚举与 `_LAYER_PRIORITY` 准确一致
- [ ] `IntentInterceptor` 与 `TaskDecomposer` 无重复关键词定义

---

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-04-25 | 初始版本，合并深度评审发现 + post-review-optimization-plan.md |
