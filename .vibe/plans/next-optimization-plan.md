# VibeSOP 下一步优化计划

> **Date**: 2026-04-26
> **From**: 全量深度评审
> **Status**: Draft

---

## 当前基线

| 指标 | 当前 | 目标 | 差距 |
|------|------|------|------|
| Lint 错误 | 7（无法自动修复） | 0 | 轻微 |
| 测试数量 | 2,077 | 2,100+ | 少量补充 |
| 测试覆盖率 | 74% | 80% | -6% |
| 源代码行数 | 51,017 | ~40,000 | -11K |
| P95 路由延迟 | 225ms | <100ms | 2.25× |
| 并行执行 | 串行 only | DAG | 功能缺失 |

---

## 阶段总览

```
阶段 1（本周）: 止血 —— 代码质量归零
    修 7 个 lint → 补覆盖率缺口 → 校验 Router 热路径

阶段 2（下周）: 减负 —— 代码体积精简 20%
    识别死代码 → 砍实验性功能 → 合并冗余 Mixin

阶段 3（2 周后）: 加速 —— 路由性能优化
    缓存优化 → 懒加载 → 并行预热

阶段 4（3 周后）: 执行桥 —— 补齐编排空白
    步骤执行器 → 状态持久化 → 错误恢复
```

---

## 阶段 1: 代码质量归零（预计 2-3 天）

### 1.1 修复剩余 7 个 lint 错误

**TC002 × 5: Rich Console 导入不是类型检查块**

影响文件: `cli/confirmation.py`, `cli/feedback.py`, `cli/plan_editor.py`, `cli/render/fallback.py`, `cli/render/single.py`

```python
# 现在（运行时导入）
from rich.console import Console

# 改为（延迟导入，函数内使用）
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from rich.console import Console
```

这 5 个文件中 `Console` 只在函数体内使用字面量创建 `Console()` — 实际上**运行时需要的**，不应该放到 `TYPE_CHECKING` 块。正确做法是**抑制 TC002 规则**（因为这些是运行时导入，不是仅类型注解使用的导入）。

**方案**: 在 `pyproject.toml` 中为这 5 个文件添加 `per-file-ignores`:

```toml
[tool.ruff.lint.per-file-ignores]
"src/vibesop/cli/confirmation.py" = ["TC002"]
"src/vibesop/cli/feedback.py" = ["TC002"]
"src/vibesop/cli/plan_editor.py" = ["TC002"]
"src/vibesop/cli/render/fallback.py" = ["TC002"]
"src/vibesop/cli/render/single.py" = ["TC002"]
```

**ARG001**: `console: Console` 参数未使用 → 删除参数或使用它
**SIM102**: 嵌套 if → 合并为 `if a and b`

### 1.2 补齐测试覆盖率到 80%

**策略**: 不用盲目加测试。先定位覆盖盲区。

```bash
# 生成覆盖率报告，定位 < 50% 的模块
uv run pytest --cov=src/vibesop --cov-report=html
# 打开 htmlcov/index.html，找红色模块 > 重点补
```

**优先补测区域**（根据代码规模和覆盖猜测）:
1. `agent/runtime/` — Agent Runtime 层（最新添加，覆盖可能低）
2. `orchestration/callbacks.py` — 流程编排回调
3. `routing/triage_service.py` — AI Triage 服务的边界情况
4. `routing/cache.py` — 缓存命中/未命中/过期

**性价比策略**: 补 200-300 行测试即可将覆盖率从 74% 拉到 80%（高覆盖文件权重高，低覆盖文件权重低）。

### 1.3 验证 Router 热路径测试

```bash
# 路由热路径性能基准
uv run pytest tests/benchmark/test_routing_hot_path.py -v
```

---

## 阶段 2: 代码体积精简（预计 1 周）

### 2.1 识别可移除的模块

使用 `coverage.py` 或 dead code 检测找出从未被导入的模块：

```bash
# 用 vulture 检测死代码
uv run vulture src/vibesop/ --min-confidence 80
```

**重点审查区域**:
- `experiments/` — A/B 测试框架（无实际使用记录）
- `analytics/` — 部分 pipeline（仅有 JSONL 存储，缺少读取路径）
- `hooks/` — 钩子系统（当前仅框架，无实际 hook 实现）
- `market/crawler.py` — GitHub Topic 爬取（MVP 级别，成熟度低）

### 2.2 合并冗余 Mixin

当前 UnifiedRouter 有 8 个 Mixin，但实际上是**组合优于继承**的反模式：

| Mixin | 职责 | 建议 |
|------|------|------|
| RouterStatsMixin | 统计计数 | → 委托给 StatsCollector 对象 |
| RouterExecutionMixin | 执行分析 | → 委托给 AnalyticsStore |
| RouterOrchestrationMixin | 编排入口 | → 移到 OrchestrationService |
| 其余 5 个 | 初始化 + 辅助 | → 合并或委托 |

**目标**: 从 8 个 Mixin 减少到 3-4 个，每个 Mixin 职责更清晰。

### 2.3 代码行数目标

| 源头 | 删除量 |
|------|--------|
| 实验性功能砍除 | ~3,000 |
| 死代码清理 | ~2,000 |
| Mixin 合并 | ~2,000 |
| 冗余抽象 | ~3,000 |
| **合计** | **~10,000** |

目标: 51,017 → ~41,000 行（-20%）

---

## 阶段 3: 路由性能优化（预计 3-5 天）

### 3.1 病因分析

当前 P95 225ms 的瓶颈在:
- AI Triage（~220ms）: LLM API 调用是最耗时环节
- Embedding（~180ms）: Sentence Transformer 模型推理
- Scenario 加载（~30ms）: 首次场景注册表加载

### 3.2 优化策略

**A. 缓存优化（预计收益 -80ms）**
```python
# 当前: 每次 route() 都检查缓存
# 改进: 预构建查询 → 技能映射的确定性缓存
# 相同查询 → 直接返回缓存结果（跨越多层 pipeline）
```

**B. 懒加载 Embedding 模型（预计收益 -100ms 首次）**
```python
# 当前: __init__ 中预热所有 matchers
# 改进: 只在需要时才加载 EmbeddingMatcher
# 大多数查询在 L3(KEYWORD) 就已命中，不需要 L5(EMBEDDING)
```

**C. AI Triage 预热（预计收益 -50ms）**
```python
# 当前: 每次 AI Triage 都重新构建 prompt
# 改进: 预构建候选技能描述的向量索引，Triage 时只做检索
```

### 3.3 性能基准

```bash
# 建立基准（优化前）
uv run pytest tests/benchmark/ -v --benchmark-only

# 目标: P95 < 100ms
```

---

## 阶段 4: 执行桥（预计 1-2 周）

这是整个优化计划中**产品价值最大**的部分。

### 4.1 问题重述

当前流程:
```
VibeSOP → 生成 ExecutionPlan → 返回给 AI Agent
AI Agent → 自己理解计划 → 手动执行每个步骤 → 手动管理状态
```

这导致编排计划的**实际执行率很低**：Agent 收到了计划，但因复杂度或上下文限制而忽略它。

### 4.2 设计：最小化步骤执行器（StepRunner）

不追求"自动执行所有步骤"，而是提供一个**Agent 可直接调用的 Python API**：

```python
from vibesop.agent import StepRunner

runner = StepRunner(execution_plan, agent_llm)

# Agent 逐步骤执行
for step in runner.pending_steps():
    context = runner.get_step_context(step)  # 前面步骤的结果
    result = agent.execute_with_skill(step.skill_id, step.input_query, context)
    runner.mark_completed(step, result)

# 或者 Agent 直接委托给 runner（runner 使用注入的 LLM 执行）
final_result = runner.execute_all()  # 自动按 DAG 执行
```

### 4.3 实现步骤

1. **StepRunner** 类（核心）— 管理步骤状态、依赖检查、上下文传递
2. **StepContext** 数据模型 — 前面步骤输出的结构化传递
3. **ExecutionPlanStore** — 持久化执行状态（`.vibe/plans/`）
4. **DAG 调度器** — 并行步骤的真正并发执行（`asyncio.gather`）

### 4.4 验收标准

- `StepRunner` 能按 DAG 执行 3 个串行步骤
- 步骤间结果能正确传递
- 失败步骤能触发错误恢复（skip/retry/abort）
- DAG 调度器支持 2-3 个并行步骤

---

## 优先级矩阵

```
                    影响力
                  低        高
            ┌──────────┬──────────┐
        低  │          │ 阶段 1   │
成          │          │ 止血     │
本          ├──────────┼──────────┤
        高  │ 阶段 2   │ 阶段 3   │
            │ 减负     │ 加速     │
            │          │ 阶段 4   │
            │          │ 执行桥   │
            └──────────┴──────────┘
```

**执行顺序**: 阶段 1 → 阶段 4 → 阶段 3 → 阶段 2

原因: 阶段 1（止血）是最低成本的基础；阶段 4（执行桥）是产品价值最大的；之后再做阶段 3（速度）和阶段 2（体积）。

---

## 不在本期计划内的

以下项目已明确评估并排除：

| 项目 | 排除原因 |
|------|---------|
| DAG 并行（完整版） | 阶段 4 先做最小版，完整版放 v5.2 |
| 技能市场升级（评分/评论） | 没有人用市场时做市场是过早优化 |
| Web UI | 当前用户是 CLI/Agent，Web 不是现阶段价值 |
| 100+ 技能 | 当前 50+ 已覆盖核心场景，增长不是瓶颈 |
| 代码从 51K 减到 15K | 20% 是务实目标，70% 需要一起规划 v6 |

---

## 度量 & 回顾

每阶段完成后记录：

| 指标 | 初始值 | 阶段1后 | 阶段2后 | 阶段3后 | 阶段4后 |
|------|--------|---------|---------|---------|---------|
| Lint 错误 | 16 | 0 | 0 | 0 | 0 |
| 测试覆盖率 | 74% | 80%+ | 80%+ | 80%+ | 80%+ |
| 源文件行数 | 51,017 | 51,017 | ~41,000 | ~41,000 | ~43,000 |
| P95 延迟 | 225ms | 225ms | ~200ms | <100ms | <100ms |
| 并行执行 | ❌ | ❌ | ❌ | ❌ | ✅ 基本 |
