# VibeSOP 评审后优化计划

> **Status**: Draft
> **Date**: 2026-04-25
> **Based on**: 深度评审分析 + v5-quality-sprint.md + skillos-productization.md + version_05.md ADR
> **Theme**: 止血 → 清债 → 加固 → 展望

---

## 优先级框架

```
优先级判定：
  P0 (立即) — 产品谎报：声称完成但实际不可用或未实现
  P1 (本月) — 体验断裂：已实现但用户感知不到，或链路不通
  P2 (下月) — 架构债：设计不一致、代码膨胀、封装泄漏
  P3 (远期) — 方向性：需要产品决策而非工程实现的根本性问题
```

---

## Phase 0: 版本号统一与现状对齐（P0，0.5 天）

**问题**：5 个文件声明了不同版本号（4.3.0 vs 4.4.0），文档声称的功能与实际版本不匹配。

### Task 0.1: 确定真实版本号

当前 `_version.py` 为 4.3.0，但 PROJECT_STATUS.md 声称 4.4.0 已发布。
决策：`_version.py` 是代码中唯一的真实版本。解决方案有两个：

**选项 A（推荐）**: 承认当前为 4.3.0，PROJECT_STATUS 中 4.4.0 的描述改为「开发中」。
**选项 B**: 升版到 4.4.0 并确保所有 4.4.0 声称的功能真正可验证。

### Task 0.2: 一致性修复

- [ ] `PROJECT_STATUS.md`: 修正版本号，标注实际状态
- [ ] `PHILOSOPHY.md`: 同步版本号
- [ ] `ROADMAP.md`: 标注 4.4.0 为「进行中」
- [ ] `README.md`: 同步版本号，更新功能状态描述

---

## Phase 1: 消除虚假完成态（P0，Week 1-2）

> 来自 `v5-quality-sprint.md` Phase 1，已有一份详尽计划。此处补充验收标准。

### 关键补充：评审视角下的新增 P0 项

#### Task 1.X: FakePass 测试审计（新增，1 天）

**问题**：PROJECT_STATUS 声称 1555+ tests / 99.9% pass rate，但覆盖率仅 74%。存在大量浅层测试（只 import 不 cover）或测试与实现脱节的可能。

**行动**：
- [ ] 运行 `pytest --cov=src/vibesop --cov-report=term-missing` 导出覆盖率缺口
- [ ] 识别覆盖率 <50% 的模块，判断是「不需要测试」还是「测试缺失」
- [ ] 修正 PROJECT_STATUS 中的测试统计为真实数字（区分 pass/cov）

#### Task 1.Y: 标签声明审计（新增，0.5 天）

**问题**：ROADMAP 中标记 ✅ 的 20+ 项，部分可能为「代码存在但不可用」。

**行动**：
- [ ] 逐项验证所有 ✅ 标记的功能，标准：「端到端可演示」
- [ ] 将「代码存在但缺乏集成验证」的项改为 ⚠️
- [ ] 输出一份审计表到 ROADMAP

---

## Phase 2: 质量债清理（P1，Week 2-4）

> 来自评审分析第 2.3 节。指标持续恶化，需集中清理。

### Task 2.1: Lint 清零（2 天）

**现状**: 114 lint errors（ROADMAP 数据）。

**行动**：
```bash
# 1. 先拿到精确数字
uv run ruff check --output-format=concise | wc -l

# 2. 自动修复安全的部分
uv run ruff check --fix

# 3. 手动修复剩余（通常 <30 个需要手动判断）
# 4. 在 pre-commit hook 中加硬阻断：lint error > 0 → 拒绝 commit
```

**验收**: `uv run ruff check` 输出 0。

### Task 2.2: 测试覆盖率达标（3 天）

**目标**: 74% → 80%。

**行动**：
```bash
# 1. 生成覆盖率报告，导出薄弱模块列表
uv run pytest --cov=src/vibesop --cov-report=term-missing \
  --cov-report=html -q 2>&1 | tee coverage_report.txt

# 2. 优先补充覆盖率 <40% 且代码量 >100 行的模块
# 3. 检查 tests/ 中有无 dead test（导入错误被静默跳过）
```

**按模块优先级**:
| 优先级 | 模块 | 当前覆盖率（估计） | 理由 |
|--------|------|-------------------|------|
| P0 | `core/orchestration/` | 低 | 编排是默认模式，测试缺失意味着核心功能不可信 |
| P0 | `agent/runtime/` | 中 | Agent Runtime 是 v4.3 核心交付 |
| P1 | `adapters/` | 中 | 平台适配器，变更多 |
| P1 | `installer/` | 中 | 一键安装是核心卖点 |

**验收**: `pytest --cov` 报告 ≥80%（全量），无模块覆盖率 <50%。

### Task 2.3: 性能优化 — P95 延迟达标（3 天）

**现状**: P95 354ms，目标 <100ms。差距巨大。

**行动**：

```bash
# 1. Profiling
python -m cProfile -o route.prof -m vibesop.cli.main route "帮我调试数据库错误"
# 分析热点

# 2. 检查瓶颈点
```

**预估瓶颈及优化方向**:

| 瓶颈 | 预估耗时 | 优化 |
|------|---------|------|
| `EmbeddingMatcher` 模型加载 | ~150ms（首次） | 预热机制已有 (`_warm_up_matchers`)，验证是否生效 |
| LLM API 调用（AI Triage） | ~200ms | 缓存命中率提升，circuit breaker 策略优化 |
| `CandidatePrefilter` 全量遍历 | ~50ms | 索引优化 |
| 配置解析（每次 `route()` 都重新读 YAML） | ~30ms | 缓存配置对象 |

**优化顺序**:
1. 确认 `_warm_up_matchers` 在初始化时被调用，消除冷启动
2. 将配置对象缓存为实例属性（当前 route() 每次都 `self._config_manager.get_routing_config()`）
3. `CandidatePrefilter` 使用倒排索引替代线性遍历
4. 增加路由结果缓存（相似 query 直接命中，跳过全管线）

**验收**: 基准测试 P95 <150ms（作为中间目标，最终 <100ms）。

---

## Phase 3: 编排管线加固（P1，Week 3-5）

> 来自评审分析第 2.7 节 + skillos-productization.md Phase B。

### Task 3.1: 封装泄漏修复（1 天）

**问题**: `PlanBuilder.build_plan()` 调用 `self._router._route()`，这是私有方法的跨模块调用。

**修复**:
```python
# PlanBuilder 应通过正式的公共 API
# UnifiedRouter 暴露：
def route_single(self, query: str, context=None) -> RoutingResult:
    """Public single-skill routing (for internal composition use)."""
    return self._route(query, context=context)
```

### Task 3.2: TaskDecomposer 无 LLM 回退增强（2 天）

**问题**: 当 LLM 不可用时，回退到纯关键词规则分解。`_fallback_decomposition` 依赖硬编码的 INTENT_PATTERNS（32 个词），大量中文查询被误判为 "single task"。

**行动**:
- [ ] 扩充 `INTENT_PATTERNS` 关键词表，从 45+ 技能的 `trigger_when` 字段动态提取
- [ ] 增加「已有技能名称映射」：如 query 中明确提到某个技能（"用 ralph 实现..."），直接识别
- [ ] 回退分解结果标注 `source: rule_fallback` 以便追踪质量

### Task 3.3: 编排透明度（来自 skillos-productization Phase B，3 天）

**问题**: `orchestrate()` 的结果对 CLI 是可见的（有 Rich 渲染），但注入到 AI Agent 的 context 时仅传递 plan steps，不传递「为什么这样分解」的 reasoning。

**行动**:
- [ ] `SkillInjector` 的注入内容增加 `detected_intents` 和 `reasoning` 字段
- [ ] CLI 的 plan 展示增加「重新选择技能」的交互（当前仅确认/跳过）
- [ ] `confirmation_mode` 在 orchestrated 模式下同样生效（当前仅在单技能路由中生效）

### Task 3.4: 反馈闭环打通（2 天）

**问题**: 评审分析第 3.3 节 — AnalyticsStore 存储了执行记录，但数据是否流入 FeedbackCollector → PreferenceBooster 形成闭环？

**行动**:
- [ ] 端到端验证：`vibe route "xxx"` → 选择 skill → AnalyticsStore 记录 → 下次同类 query 置信度提升
- [ ] 编写集成测试验证闭环
- [ ] 如果链路断裂，修复之

---

## Phase 4: 设计一致性修复（P2，Week 4-5）

> 来自评审分析第 2.5 节。

### Task 4.1: SkillDefinition 类型安全化（0.5 天）

```python
# models.py: SkillDefinition.lifecycle 从 str 改为 SkillLifecycle
from vibesop.core.skills.lifecycle import SkillLifecycle

class SkillDefinition(BaseModel):
    lifecycle: SkillLifecycle = Field(default=SkillLifecycle.ACTIVE, ...)
```

### Task 4.2: Metadata 类型统一（0.5 天）

**问题**: `SkillDefinition.metadata` 是 `dict[str, str | int | float | bool]`，但 `SkillRoute.metadata` 是 `dict[str, Any]`。不一致导致跨模块传递时需要手动转换。

**修复**: 统一为 `dict[str, Any]`，在需要严格验证的场景下用子模型。

### Task 4.3: UnifiedRouter 公共 API 梳理（1 天）

**问题**: UnifiedRouter 的公共 API 和内部方法界限模糊（`_get_cached_candidates`、`_build_result`、`_apply_optimizations` 等被外部调用）。

**行动**:
- [ ] 梳理所有外部对 UnifiedRouter 的调用点
- [ ] 将需要外部访问的方法升级为公共 API（加文档和类型标注）
- [ ] 将纯内部方法加上 `_` 前缀并在 `__all__` 中排除

---

## Phase 5: 架构瘦身（P3，远期）

> 来自评审分析第 2.2 节。49K 行 vs 15K 目标。

### 方向性建议（不做本轮计划）

1. **Mixin 继承 → 组合**: 当前 `UnifiedRouter(RouterStatsMixin, RouterExecutionMixin, RouterOrchestrationMixin)` 三层继承。考虑改为组合模式，每个子系统独立实例化。
2. **CLI 命令扁平化**: 当前 `cli/commands/` 下有 30+ 个命令文件，许多命令（`badges_cmd`、`deviation_cmd`、`tools_cmd`、`market_cmd`）使用频率低。考虑按使用频率分层：核心命令保持在 CLI，低频命令通过 plugin 机制按需加载。
3. **废弃代码清理**: `core/checkpoint/`、`core/experiment.py`、`core/badges.py` 等模块，确认是否仍在活跃使用。无调用方的代码直接移除。

---

## Phase 6: 产品方向决策（P3，需要讨论）

> 来自评审分析第 3.3 节。这些不是工程问题，需要产品决策。

### 待决策问题

| # | 问题 | 选项 |
|---|------|------|
| 1 | VibeSOP 是「薄路由层」还是「厚 OS」？ | A: 保持路由定位，编排/生命周期/市场作为独立可选模块；B: 继续加厚，成为完整 SkillOS |
| 2 | 编排能力何时有意义？ | 当前编排给 AI Agent 一个 plan，Agent 可能忽略它。需要验证 or 简化 |
| 3 | 是否坚持「只路由不执行」？ | 反馈闭环需要执行层数据，边界需要重新审视 |
| 4 | 内置能力 vs 社区生态的边界？ | 当 VibeSOP 自身越来越"厚"，和它路由的 skill 之间的区别是什么？ |

---

## 执行时间线

```
Week 1          Week 2          Week 3          Week 4          Week 5
├───────────────┼───────────────┼───────────────┼───────────────┤
│ Phase 0       │               │               │               │
│ 版本统一      │               │               │               │
├───────────────┤               │               │               │
│ Phase 1       │               │               │               │
│ 消除虚假完成态│               │               │               │
├───────────────┼───────────────┤               │               │
│               │ Phase 2       │               │               │
│               │ 质量债清理    │               │               │
├───────────────┼───────────────┼───────────────┤               │
│               │               │ Phase 3       │               │
│               │               │ 编排管线加固  │               │
├───────────────┼───────────────┼───────────────┼───────────────┤
│               │               │               │ Phase 4       │
│               │               │               │ 设计一致性    │
└───────────────┴───────────────┴───────────────┴───────────────┘

Phase 5 & 6: 远期，不纳入本轮 sprint
```

---

## 成功标准

- [ ] `uv run ruff check` 输出 0
- [ ] `pytest --cov` 报告 ≥80%
- [ ] 路由 P95 <150ms
- [ ] 版本号在所有文件中统一
- [ ] ROADMAP 中所有 ✅ 标记的功能可端到端演示
- [ ] `vibe route` 单技能 + 编排模式均经过 confirmation_mode 全链路验证
- [ ] 编排回退路径（无 LLM）可处理 80%+ 常见多意图查询
