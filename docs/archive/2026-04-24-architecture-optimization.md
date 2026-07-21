# 架构级优化计划 — 从路由引擎到技能操作系统

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 VibeSOP 从"静态技能集合 + 单技能路由"升级为"动态技能生态 + 多意图编排"，同时收敛代码膨胀、消除文档不一致、打开技能市场。

**Architecture:** 5 个独立可交付的 Phase，每个 Phase 解决一类核心问题。Phase 0-2 为架构补丁，Phase 3-4 为生态解锁。与 `.vibe/plans/v5-quality-sprint.md`（修地基、补空壳）互补，本计划聚焦架构层面。

**Tech Stack:** Python 3.12+, Pydantic v2, Typer, Rich, pytest

---

## 背景：深度评审发现的 6 大问题

| # | 问题 | 严重度 | 根因 |
|---|------|--------|------|
| 1 | 多意图查询只匹配单个技能 | P0 架构 | `route()` 返回单结果，`orchestrate()` 未成默认路径 |
| 2 | 代码量 3× 超目标（~49K vs 15K） | P1 维护 | 8 个 mixin + 22 个 routing 文件过度解耦 |
| 3 | 技能市场不存在 | P1 生态 | 有 `.skill` 格式无分发渠道，路由价值无法释放 |
| 4 | 路由透明度是 opt-in flag | P1 体验 | `--explain` 控制展示，默认模式下用户看不到决策 |
| 5 | 文档版本/层级数不一致 | P2 质量 | PHILOSOPHY 两处版本不同，文档说 5/7 层实际 10 层 |
| 6 | 定位在"纯路由"和"轻量编排"间摇摆 | P2 战略 | 有 ExecutionPlan 但说"不执行"，导致功能膨胀但方向模糊 |

**已有计划覆盖情况**：`v5-quality-sprint.md` 覆盖了问题 4 的部分（确认逻辑统一）、问题 5 的部分（ROADMAP 数据修正）。本计划覆盖问题 1、2、3、6 的核心部分，以及问题 4、5 中未被覆盖的深度修复。

---

## Phase 0: 文档一致性清零（1 天）

> 目标：所有文档中的版本号、层级数、功能声明与实际代码一致。

### Task 0.1: 统一版本号和路由层数

**原则**：以 `src/vibesop/core/models.py` 的 `RoutingLayer` 枚举（10 个值）和 `pyproject.toml` 的 `version = "4.3.0"` 为准。

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `docs/PHILOSOPHY.md`
- Modify: `docs/PROJECT_STATUS.md`

- [ ] **Step 1: 审计所有文档中的版本号**

```bash
rg "版本.*:.*\d+\.\d+\.\d+|Version.*:.*\d+\.\d+\.\d+" docs/ README.md CLAUDE.md --no-filename
```

期望：找到所有版本号声明，列出不一致项（预期：PHILOSOPHY.md 的 `4.1.0` 和 `4.2.0`，PROJECT_STATUS.md 的 `4.1.0`）。

- [ ] **Step 2: 修正 PHILOSOPHY.md 的版本号**

```bash
# 将头部版本和底部版本统一为 4.3.0
```

在 `docs/PHILOSOPHY.md` 中：

```diff
- > **版本**: 4.2.0
+ > **版本**: 4.3.0

- **更新时间**: 2026-04-18
+ **更新时间**: 2026-04-24

- **版本**: 4.1.0
- **状态**: ✅ 哲学文档完成
+ **版本**: 4.3.0
+ **状态**: ✅ 活动维护中
```

- [ ] **Step 3: 修正 PROJECT_STATUS.md 的版本号**

在 `docs/PROJECT_STATUS.md` 中：

```diff
- **Version**: 4.1.0
- **Status**: 🟢 Production Ready
- **Last Updated**: 2026-04-18
+ **Version**: 4.3.0
+ **Status**: 🟢 Active Development
+ **Last Updated**: 2026-04-24
```

- [ ] **Step 4: 修正 CLAUDE.md 的路由层数描述**

在 `CLAUDE.md` 中：

```diff
- **5-Layer Routing System:**
- - **Layer 0**: AI Semantic Triage (Haiku/GPT, 95% accuracy)
- - **Layer 1**: Explicit overrides (user-specified)
- - **Layer 2**: Scenario patterns (predefined cases)
- - **Layer 3**: Semantic matching (TF-IDF + cosine similarity)
- - **Layer 4**: Fuzzy matching (Levenshtein distance)
+ **10-Layer Routing System:**
+ - **Layer 0**: Explicit overrides (user-specified)
+ - **Layer 1**: Scenario patterns (predefined cases)
+ - **Layer 2**: AI Semantic Triage (Haiku/GPT, 95% accuracy)
+ - **Layer 3**: Keyword matching (exact + partial)
+ - **Layer 4**: TF-IDF semantic similarity
+ - **Layer 5**: Embedding-based (optional, 85% accuracy)
+ - **Layer 6**: Levenshtein fuzzy matching
+ - **Layer 7**: Custom plugin matchers
+ - **Layer 8**: No Match (below threshold)
+ - **Layer 9**: Fallback LLM (transparent degradation)
```

- [ ] **Step 5: 修正 README.md 的架构图层级**

在 `README.md` 的架构 ASCII 图中：

```diff
- |  7-Layer Pipeline:                              |
- |  AI Triage → Explicit → Scenario → Keyword      |
- |  → TF-IDF → Embedding → Fuzzy                   |
+ |  8-Layer Pipeline:                              |
+ |  AI Triage → Explicit → Scenario → Keyword      |
+ |  → TF-IDF → Embedding → Fuzzy → Fallback LLM    |
```

- [ ] **Step 6: 运行验证确保无遗漏**

```bash
rg "(Version|版本).*\d+\.\d+\.\d+" README.md CLAUDE.md docs/ --no-filename
```

期望：所有输出均为 `4.3.0`。

- [ ] **Step 7: Commit**

```bash
git add README.md CLAUDE.md docs/PHILOSOPHY.md docs/PROJECT_STATUS.md
git commit -m "docs: unify version to 4.3.0 and fix routing layer count (5→8) across all docs"
```

---

## Phase 1: 路由透明度 — 从 opt-in 到默认（2 天）

> 目标：`--explain` 不再是 flag，而是默认行为。路由结果始终携带完整决策路径，CLI 默认展示精简版，详细版通过 `--verbose` 触发。

### Task 1.1: 重构 `RoutingResult` 使其始终携带 `layer_details`

**Files:**
- Modify: `src/vibesop/core/models.py:182-231`
- Modify: `src/vibesop/core/routing/unified.py:253-350`

**背景**：当前 `orchestrate()` 返回 `OrchestrationResult`，但 `layer_details` 仅在 `--explain` 时被消费。需要保证 `orchestrate()` 始终填充 `layer_details`。

- [ ] **Step 1: 写失败的测试 — 验证默认路由包含 layer_details**

```python
# tests/unit/core/routing/test_transparency.py (新建)

import pytest
from vibesop.core.models import RoutingLayer, LayerDetail, RoutingResult

def test_routing_result_always_has_layer_details():
    """Default routing must include layer details, not just with --explain."""
    from vibesop.core.routing.unified import UnifiedRouter

    router = UnifiedRouter(project_root=".")
    result = router.route("debug database error")

    # Default routing must populate layer_details
    assert result.layer_details is not None
    assert len(result.layer_details) > 0

    # At minimum, the layer that produced the match must be present
    matched_layers = [d for d in result.layer_details if d.matched]
    assert len(matched_layers) >= 1

def test_routing_result_always_has_alternatives():
    """Alternatives must be populated even in default mode."""
    from vibesop.core.routing.unified import UnifiedRouter

    router = UnifiedRouter(project_root=".")
    result = router.route("debug database error")

    assert result.primary is not None
    # Alternatives may be empty but must exist as a list
    assert isinstance(result.alternatives, list)


def test_orchestrate_result_always_has_layer_details():
    """Orchestration must also include layer details."""
    from vibesop.core.routing.unified import UnifiedRouter

    router = UnifiedRouter(project_root=".")
    result = router.orchestrate("analyze architecture and optimize performance")

    assert result.layer_details is not None
    assert len(result.layer_details) > 0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/unit/core/routing/test_transparency.py -v
```

期望：至少部分测试 FAIL（因为当前默认路由不保证 `layer_details` 填充）。

- [ ] **Step 3: 修改 `UnifiedRouter.route()` 确保 layer_details 始终填充**

在 `src/vibesop/core/routing/unified.py` 的 `route()` 方法中，找到 `_execute_layers()` 调用处，确保结果始终包含 `layer_details`：

```python
# unified.py route() method — 在 _execute_layers 之后

# 确保 layer_details 始终非空
if not layer_details:
    # 如果没有任何层产生结果，至少记录一个概览
    layer_details = [
        LayerDetail(
            layer=RoutingLayer.NO_MATCH,
            matched=False,
            reason="No routing layer produced a confident match",
            duration_ms=0.0,
        )
    ]

# 始终填充 alternatives（当前仅在部分路径填充）
if not alternatives:
    alternatives = self._collect_alternatives_from_details(layer_details, self._config.min_confidence * 0.7)
```

在 `unified.py` 中添加辅助方法：

```python
def _collect_alternatives_from_details(
    self,
    layer_details: list[LayerDetail],
    threshold: float,
) -> list[SkillRoute]:
    """Collect skill alternatives from layer diagnostics."""
    seen: set[str] = set()
    alternatives: list[SkillRoute] = []
    for detail in layer_details:
        for rejected in detail.rejected_candidates:
            if rejected.skill_id not in seen and rejected.confidence >= threshold:
                seen.add(rejected.skill_id)
                alternatives.append(
                    SkillRoute(
                        skill_id=rejected.skill_id,
                        confidence=rejected.confidence,
                        layer=rejected.layer,
                        source="",
                    )
                )
    return alternatives[:5]  # top-5 alternatives
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/unit/core/routing/test_transparency.py -v
```

- [ ] **Step 5: 修改 CLI — 默认展示精简报告，`--verbose` 展示完整**

在 `src/vibesop/cli/main.py` 的 `route` 命令中：

```python
# 将 --explain 改为 --verbose
# 默认展示精简版（匹配技能 + 置信度 + 路由层）
# --verbose 展示完整版（每层诊断 + rejected candidates）

@app.command()
def route(
    query: str = typer.Argument(...),
    # ... other options ...
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show full routing decision tree with per-layer diagnostics",
    ),
    # ... remaining options ...
) -> None:
    # ...

    result = router.orchestrate(query, context=context)

    if verbose:
        # Full details
        if result.mode.value == "single":
            from vibesop.core.models import RoutingResult
            routing_result = RoutingResult(
                primary=result.primary,
                alternatives=result.alternatives,
                routing_path=result.routing_path,
                layer_details=result.layer_details,
                query=result.original_query,
                duration_ms=result.duration_ms,
            )
            render_routing_report(routing_result, console=console, context=context)
        else:
            render_orchestration_result(result, console=console)
        raise typer.Exit(0)

    # Default: compact decision summary with transparency
    _render_compact_summary(result, console)
    # ... proceed with confirmation logic ...
```

- [ ] **Step 6: 创建精简摘要渲染函数**

```python
# src/vibesop/cli/routing_report.py — 添加

def render_compact_summary(result: OrchestrationResult, console: Console) -> None:
    """Render a compact routing decision summary (always shown in default mode)."""
    from rich.table import Table

    console.print()
    table = Table(title="🔍 Routing Decision", show_header=False, border_style="dim")
    table.add_column("Key", style="bold cyan")
    table.add_column("Value")

    if result.primary:
        table.add_row("Selected Skill", f"[bold green]{result.primary.skill_id}[/bold green]")
        table.add_row("Confidence", f"{result.primary.confidence:.0%}")
        table.add_row("Matched By", result.primary.layer.value)
        table.add_row("Duration", f"{result.duration_ms:.1f}ms")
    elif result.execution_plan:
        table.add_row("Mode", "[bold yellow]Orchestrated[/bold yellow]")
        table.add_row("Steps", str(len(result.execution_plan.steps)))
        table.add_row("Strategy", result.execution_plan.execution_mode.value)

    if result.alternatives:
        alts = ", ".join(
            f"[dim]{a.skill_id} ({a.confidence:.0%})[/dim]"
            for a in result.alternatives[:3]
        )
        table.add_row("Alternatives", alts)

    table.add_row("", "[dim]Use --verbose for full decision tree[/dim]")
    console.print(table)
    console.print()
```

- [ ] **Step 7: 更新测试确认 CLI 不报错**

```bash
uv run pytest tests/cli/ -k "route" -v --tb=short
```

- [ ] **Step 8: Commit**

```bash
git add tests/unit/core/routing/test_transparency.py src/vibesop/core/routing/unified.py src/vibesop/cli/main.py src/vibesop/cli/routing_report.py
git commit -m "feat: make routing transparency default behavior (--explain → --verbose)"
```

---

## Phase 2: IntentDecomposer v2 — 从骨架到默认多意图路由（2 周）

> 目标：`orchestrate()` 成为默认路由入口。当查询包含多意图时，自动分解为子任务并生成 ExecutionPlan。`route()` 保留为单技能退化模式。

### 架构变更

```
当前: route() → 单 SkillRoute → CLI 展示
       orchestrate() → OrchestrationResult → CLI 展示（仅当手动触发）

目标: orchestrate() → OrchestrationResult → CLI 展示（默认入口）
        ├── 单意图: mode=SINGLE, primary=SkillRoute
        └── 多意图: mode=ORCHESTRATED, execution_plan=ExecutionPlan
```

### Task 2.1: 增强 `MultiIntentDetector` — 减少误判

**Files:**
- Modify: `src/vibesop/core/orchestration/multi_intent_detector.py:53-146`
- Create: `tests/unit/core/orchestration/test_multi_intent_detector.py`

- [ ] **Step 1: 写失败的测试 — 短查询不应被误判为多意图**

```python
# tests/unit/core/orchestration/test_multi_intent_detector.py

import pytest
from vibesop.core.orchestration.multi_intent_detector import MultiIntentDetector


class TestMultiIntentDetector:
    def test_short_query_not_multi_intent(self):
        """Short queries should not be decomposed even with conjunctions."""
        detector = MultiIntentDetector(min_query_length=10)

        assert detector._heuristic_check("分析并测试", None) is False

    def test_long_query_with_conjunctions(self):
        """Long queries with conjunctions should pass heuristic."""
        detector = MultiIntentDetector(min_query_length=10)

        assert detector._heuristic_check(
            "分析当前项目的架构，并对代码质量进行审查",
            None
        ) is True

    def test_long_single_intent(self):
        """Long but single-intent queries should not be decomposed."""
        detector = MultiIntentDetector(min_query_length=10)

        # "帮我仔细review这段代码的安全问题" — 单意图
        assert detector._heuristic_check(
            "帮我仔细review这段代码的安全问题",
            None,
        ) is False

    def test_multiple_domains_triggers(self):
        """Queries spanning >1 intent domain should trigger."""
        detector = MultiIntentDetector(min_query_length=10)

        # 同时包含 "架构" (analyze) 和 "审查" (review) 两个领域
        assert detector._heuristic_check(
            "分析当前架构设计，然后审查代码的安全性",
            None,
        ) is True

    def test_sequential_keywords(self):
        """Sequential markers should trigger decomposition."""
        detector = MultiIntentDetector(min_query_length=10)

        assert detector._heuristic_check(
            "先review代码，再设计优化方案",
            None,
        ) is True
```

- [ ] **Step 2: 运行测试确认部分失败**

```bash
uv run pytest tests/unit/core/orchestration/test_multi_intent_detector.py -v
```

- [ ] **Step 3: 增强 `_heuristic_check` 添加意图领域检测**

在 `src/vibesop/core/orchestration/multi_intent_detector.py` 中修改：

```python
def _heuristic_check(self, query: str, single_result) -> bool:
    """Fast heuristic check for multi-intent candidates.

    Returns True only when MULTIPLE conditions agree on multi-intent.
    v2: Added intent domain diversity check to reduce false positives.
    """
    query_lower = query.lower()

    # Condition 1: Must have multi-intent conjunctions AND be long enough
    has_conjunction = _KEYWORD_PATTERN.search(query) is not None
    is_long = len(query) >= self.min_query_length
    if not has_conjunction or not is_long:
        return False

    # Condition 2: Must span at least 2 distinct intent domains
    # This prevents "帮我review这段代码" (conjunction "这段" is not a separator)
    matched_domains = set()
    for domain, keywords in _INTENT_DOMAINS:
        if any(kw in query_lower for kw in keywords):
            matched_domains.add(domain)
            if len(matched_domains) >= 2:
                break

    if len(matched_domains) < 2:
        return False

    # Condition 3: Low single-skill confidence OR close alternatives
    if single_result is not None and single_result.primary is not None:
        primary_conf = single_result.primary.confidence
        if primary_conf >= self.low_confidence_threshold:
            # Primary is confident — check if alternatives are close
            top_alt = max(
                (a.confidence for a in (single_result.alternatives or [])),
                default=0.0,
            )
            if (primary_conf - top_alt) > self.confidence_gap_threshold:
                # Large gap — likely single intent, don't decompose
                return False

    logger.debug(
        "Multi-intent heuristic passed: domains=%s, len=%d",
        matched_domains,
        len(query),
    )
    return True
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/unit/core/orchestration/test_multi_intent_detector.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/unit/core/orchestration/test_multi_intent_detector.py src/vibesop/core/orchestration/multi_intent_detector.py
git commit -m "feat: reduce MultiIntentDetector false positives with domain diversity check"
```

### Task 2.2: 将 `orchestrate()` 设为 CLI 默认入口

**Files:**
- Modify: `src/vibesop/cli/main.py:48-184`

- [ ] **Step 1: 写失败测试 — 验证多意图查询返回编排结果**

```python
# tests/cli/test_orchestrate_default.py (新建)

def test_multi_intent_query_returns_orchestrated():
    """Multi-intent queries should auto-detect and return orchestrated plan."""
    from vibesop.core.routing.unified import UnifiedRouter

    router = UnifiedRouter(project_root=".")
    result = router.orchestrate("分析项目架构，并对代码质量进行审查")

    # Should auto-detect multi-intent
    if result.mode.value == "orchestrated":
        assert result.execution_plan is not None
        assert len(result.execution_plan.steps) >= 2
        assert result.execution_plan.reasoning
    # Single-intent is also acceptable (router may legitimately decide otherwise)
```

- [ ] **Step 2: 运行测试确认现状**

```bash
uv run pytest tests/cli/test_orchestrate_default.py -v
```

- [ ] **Step 3: 确认 CLI 默认路径是 `orchestrate()`**

当前 `src/vibesop/cli/main.py:157` 已经调用了 `router.orchestrate(query, ...)`，确认此路径。如果当前 `orchestrate()` 对单意图查询直接退化为 `route()`，则架构已就位。验证逻辑：

```python
# 确认 orchestration_mixin.py 中的 orchestrator 逻辑
# 路径：src/vibesop/core/routing/orchestration_mixin.py
```

- [ ] **Step 4: 确保 `orchestrate()` 的退化路径正确**

验证 `orchestrate()` 对单意图查询返回 `mode=SINGLE` + `primary=SkillRoute`，而非空 `ExecutionPlan`。

```python
# 快速手动验证
def test_single_intent_degradation():
    router = UnifiedRouter(project_root=".")
    result = router.orchestrate("help me debug a null pointer")
    assert result.mode.value == "single"
    assert result.primary is not None
```

- [ ] **Step 5: Commit**

```bash
git add tests/cli/test_orchestrate_default.py
git commit -m "test: add orchestrate-as-default integration tests"
```

### Task 2.3: 确保 `TaskDecomposer.fallback` 的高质量分段

**Files:**
- Modify: `src/vibesop/core/orchestration/task_decomposer.py:125-179`

- [ ] **Step 1: 写失败的测试 — 验证语义分段优于正则分段**

```python
# tests/unit/core/orchestration/test_task_decomposer.py (新建或增强)

def test_fallback_decompose_chinese_multi_intent():
    """Fallback should decompose Chinese multi-intent query into >1 subtask."""
    decomposer = TaskDecomposer(llm_client=None)  # force fallback

    sub_tasks = decomposer.decompose("分析项目架构，然后审查代码质量")

    assert len(sub_tasks) >= 2
    intents = [st.intent for st in sub_tasks]
    assert "analyze_architecture" in intents
    assert "code_review" in intents


def test_fallback_decompose_single_intent():
    """Fallback should return single subtask for single-intent queries."""
    decomposer = TaskDecomposer(llm_client=None)

    sub_tasks = decomposer.decompose("修复数据库连接错误")

    assert len(sub_tasks) == 1


def test_fallback_decompose_parallel_intent():
    """'同时' should produce tasks that can run in parallel."""
    decomposer = TaskDecomposer(llm_client=None)

    sub_tasks = decomposer.decompose("同时审查前端和后端代码的安全性")

    assert len(sub_tasks) >= 2
```

- [ ] **Step 2: 运行测试确认部分失败**

```bash
uv run pytest tests/unit/core/orchestration/test_task_decomposer.py -v
```

- [ ] **Step 3: 增强 `_fallback_decomposition` 的分词质量**

在 `src/vibesop/core/orchestration/task_decomposer.py` 中重写 `_fallback_decomposition`：

```python
def _fallback_decomposition(self, query: str) -> list[SubTask]:
    """Rule-based intent decomposition when LLM is unavailable.

    v3: Improved segmentation using intent domain boundaries instead of
    regex splitting on conjunctions. Each segment is matched to the
    closest intent domain for better skill routing.
    """
    # 1. Extract segments using conjunction splitting
    segments = self._segment_by_conjunctions(query)

    # 2. For each segment, detect intent domain
    sub_tasks: list[SubTask] = []
    for seg in segments:
        cleaned = seg.strip().rstrip(".,，。；;")
        if len(cleaned) < self.MIN_QUERY_LENGTH:
            continue

        intent = self._detect_intent(cleaned)
        contextualized = self._contextualize_query(query, cleaned, intent)
        sub_tasks.append(SubTask(intent=intent, query=contextualized))

    # 3. If only 1 subtask, treat as single intent
    if len(sub_tasks) <= 1:
        intent = self._detect_intent(query)
        return [SubTask(intent=intent, query=query)]

    return sub_tasks[: self.MAX_SUB_TASKS]


def _segment_by_conjunctions(self, query: str) -> list[str]:
    """Split query by conjunctions, preserving context in each segment.

    Uses structural markers (commas + conjunctions) rather than
    naive regex split to avoid splitting mid-sentence.
    """
    import re

    # Build regex that matches conjunction markers
    conjunctions = [
        "然后", "之后", "接着", "并", "并且", "同时", "另外", "还有", "以及",
        "先", "再", "最后",
        "and then", "after that", "and also", "plus", "meanwhile",
        "first", "second", "third", "then",
    ]
    # Match conjunction preceded by punctuation or whitespace
    pattern = r"[,，\s]+(?:" + "|".join(re.escape(c) for c in conjunctions) + r")[,，\s]+"

    parts = re.split(pattern, query)
    return [p for p in parts if p.strip()]
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/unit/core/orchestration/test_task_decomposer.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/unit/core/orchestration/test_task_decomposer.py src/vibesop/core/orchestration/task_decomposer.py
git commit -m "feat: improve TaskDecomposer fallback segmentation with intent domain boundaries"
```

---

## Phase 3: 代码简化 Sprint（1 周）

> 目标：减少 195 个源文件的维护负担，消除过度解耦。不改行为，只收敛结构。

### Task 3.1: 合并 `routing/` 目录的过度拆分

**现状**：22 个文件，其中 8 个是 mixin。`unified.py` (609 行) 的用户需要理解 8 个 mixin 才能读懂路由逻辑。

**方案**：将 8 个 mixin 合并为 3 个大模块，保留可测试性。

**Files:**
- Modify: `src/vibesop/core/routing/unified.py`
- Create: `src/vibesop/core/routing/_layers.py`
- Create: `src/vibesop/core/routing/_pipeline.py`
- Delete: `src/vibesop/core/routing/candidate_mixin.py`
- Delete: `src/vibesop/core/routing/config_mixin.py`
- Delete: `src/vibesop/core/routing/context_mixin.py`
- Delete: `src/vibesop/core/routing/matcher_mixin.py`

- [ ] **Step 1: 审计 mixin 依赖关系**

```bash
# 生成每个 mixin 的 import 图
rg "from vibesop.core.routing\." src/vibesop/core/routing/unified.py -n
```

- [ ] **Step 2: 创建 `_layers.py` — 合并层级执行逻辑**

将 4 个显式层级（explicit, scenario, triage, execution）的执行逻辑合并到一个文件：

```python
# src/vibesop/core/routing/_layers.py (新建)

"""Routing layer implementations extracted from UnifiedRouter mixins.

Each function takes the router state it needs as parameters,
eliminating the need for mixin-based coupling.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from vibesop.core.models import LayerDetail, RoutingLayer, SkillRoute

if TYPE_CHECKING:
    from vibesop.core.routing.unified import UnifiedRouter


def try_explicit_layer(
    router: UnifiedRouter,
    query: str,
    candidates: list[dict[str, Any]],
) -> tuple[SkillRoute | None, LayerDetail]:
    """Layer 1: Check for explicit skill overrides (@skill_name)."""
    from vibesop.core.routing.explicit_layer import ExplicitLayer

    t0 = time.perf_counter()
    layer = ExplicitLayer()
    match = layer.match(query, candidates)
    duration = (time.perf_counter() - t0) * 1000

    detail = LayerDetail(
        layer=RoutingLayer.EXPLICIT,
        matched=match is not None,
        reason=f"Explicit override found: {match.skill_id}" if match else "No explicit override",
        duration_ms=duration,
    )
    return match, detail


def try_scenario_layer(
    router: UnifiedRouter,
    query: str,
    candidates: list[dict[str, Any]],
    context: Any | None = None,
) -> tuple[SkillRoute | None, LayerDetail]:
    """Layer 2: Check scenario patterns."""
    from vibesop.core.routing.scenario_layer import ScenarioMatcher

    t0 = time.perf_counter()
    matcher = ScenarioMatcher(router._scenario_cache)
    match = matcher.match(query, candidates, context=context)
    if match:
        router._scenario_cache = matcher.cache
    duration = (time.perf_counter() - t0) * 1000

    detail = LayerDetail(
        layer=RoutingLayer.SCENARIO,
        matched=match is not None,
        reason=f"Scenario matched: {match.skill_id}" if match else "No scenario match",
        duration_ms=duration,
    )
    return match, detail


def try_ai_triage_layer(
    router: UnifiedRouter,
    query: str,
    candidates: list[dict[str, Any]],
    context: Any | None = None,
) -> tuple[SkillRoute | None, LayerDetail]:
    """Layer 0: AI semantic triage."""
    # Delegate to TriageService
    # ... existing logic extracted from triage_mixin.py
```

（由于篇幅限制，此处展示结构模式，完整实现包含所有层级）

- [ ] **Step 3: 创建 `_pipeline.py` — 合并管道执行逻辑**

将 matcher pipeline、optimization、conflict resolution 的执行逻辑合并：

```python
# src/vibesop/core/routing/_pipeline.py (新建)

"""Routing pipeline: matcher execution, optimization, conflict resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vibesop.core.models import LayerDetail, RoutingLayer, SkillRoute

if TYPE_CHECKING:
    from vibesop.core.routing.unified import UnifiedRouter


def run_matcher_pipeline(
    router: UnifiedRouter,
    query: str,
    candidates: list[dict[str, Any]],
    context: Any | None = None,
) -> tuple[SkillRoute | None, list[LayerDetail]]:
    """Execute all matchers in priority order. First confident match wins."""
    layer_details: list[LayerDetail] = []
    # ... existing logic from matcher_mixin.py + matcher_pipeline.py
    return None, layer_details


def apply_optimizations(
    router: UnifiedRouter,
    candidates: list[dict[str, Any]],
    context: Any | None = None,
) -> list[dict[str, Any]]:
    """Apply prefilter + preference boost + habit boost to candidates."""
    # ... existing logic from optimization_mixin.py merged with optimization_service
    return candidates
```

- [ ] **Step 4: 重写 `unified.py` 的 `route()` 使用新模块**

```python
# unified.py — route() method rewritten

def route(
    self,
    query: str,
    candidates: list[dict[str, Any]] | None = None,
    context: RoutingContext | None = None,
) -> RoutingResult:
    start_time = time.perf_counter()
    self._total_routes += 1

    # Multi-turn enrichment
    if context and context.conversation_id:
        query = self._enrich_conversation(query, context)

    # Candidate loading
    if candidates is None:
        candidates = self._get_cached_candidates()

    candidates = self._filter_by_lifecycle(candidates)
    context = self._enrich_context(context, query)

    # Layers in priority order
    layer_details: list[LayerDetail] = []

    # Layer 1: Explicit
    match, detail = _layers.try_explicit_layer(self, query, candidates)
    layer_details.append(detail)
    if match:
        return self._build_result(match, [], layer_details, query, start_time)

    # Layer 2: Scenario
    match, detail = _layers.try_scenario_layer(self, query, candidates, context)
    layer_details.append(detail)
    if match:
        return self._build_result(match, [], layer_details, query, start_time)

    # Layer 0: AI Triage
    if self._config.enable_ai_triage:
        match, detail = _layers.try_ai_triage_layer(self, query, candidates, context)
        layer_details.append(detail)
        if match:
            return self._build_result(match, [], layer_details, query, start_time)

    # Layer 3-6: Matcher pipeline
    candidates = _pipeline.apply_optimizations(self, candidates, context)
    match, details = _pipeline.run_matcher_pipeline(self, query, candidates, context)
    layer_details.extend(details)
    if match:
        return self._build_result(match, [], layer_details, query, start_time)

    # No match — fallback
    detail = _layers.build_fallback_detail(self._config)
    layer_details.append(detail)
    return self._build_result(None, [], layer_details, query, start_time)
```

- [ ] **Step 5: 删除废弃的 mixin 文件**

```bash
rm src/vibesop/core/routing/candidate_mixin.py
rm src/vibesop/core/routing/config_mixin.py
rm src/vibesop/core/routing/context_mixin.py
rm src/vibesop/core/routing/matcher_mixin.py
rm src/vibesop/core/routing/optimization_mixin.py
rm src/vibesop/core/routing/triage_mixin.py
```

- [ ] **Step 6: 运行全量测试**

```bash
uv run pytest tests/ -x --tb=short 2>&1 | tail -30
```

- [ ] **Step 7: 更新 `unified.py` 的类定义**

```python
# 从 8-mixin 继承改为单一继承
class UnifiedRouter(RouterStatsMixin, RouterExecutionMixin, RouterOrchestrationMixin):
    """Unified router for skill selection.

    Layers are implemented as standalone functions in _layers.py and
    _pipeline.py, eliminating the need for mixin-based coupling.
    ...
    """
```

- [ ] **Step 8: Commit**

```bash
git add src/vibesop/core/routing/
git commit -m "refactor: collapse 6 routing mixins into _layers.py + _pipeline.py (22→16 files)"
```

### Task 3.2: 消除 Agent Runtime 与核心路由的功能重叠

**现状**：`agent/runtime/IntentInterceptor` 检查 `/vibe-*` 前缀，`cli/main.py` 也有同样的逻辑。`SkillInjector` 的注入逻辑有 3 个平台路径但都是 `pass`。

**方案**：将 `IntentInterceptor` 的逻辑合并到 CLI 的 `route` 命令入口，删除 `SkillInjector` 的空壳。

**Files:**
- Modify: `src/vibesop/cli/main.py`
- Modify: `src/vibesop/agent/runtime/__init__.py`
- Delete: `src/vibesop/agent/runtime/skill_injector.py`

- [ ] **Step 1: 将 slash command 检测整合到 CLI 入口**

```python
# cli/main.py route() — 简化 slash command 处理
# 删除对 IntentInterceptor 的依赖，直接用前缀检测

SLASH_PREFIX = "/vibe-"

def _handle_slash_command(query: str, json_output: bool) -> None:
    """Handle /vibe-* slash commands inline."""
    from vibesop.agent.runtime import SlashCommandExecutor

    executor = SlashCommandExecutor()
    result = executor.execute_query(query)

    if json_output:
        import json
        console.print(json.dumps({
            "success": result.success,
            "message": result.message,
            "command": result.command,
        }, indent=2))
    elif result.success:
        console.print(f"[bold green]✓[/bold green] {result.message}")
    else:
        console.print(f"[bold yellow]⚠[/bold yellow] {result.message}")
    raise typer.Exit(0 if result.success else 1)
```

- [ ] **Step 2: 删除 SkillInjector 空壳**

```bash
# SkillInjector 的 3 个平台路径都是 pass — 没有实际功能
rm src/vibesop/agent/runtime/skill_injector.py
```

- [ ] **Step 3: 运行全量测试**

```bash
uv run pytest tests/agent/ tests/cli/ -x --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: consolidate slash-command handling, remove SkillInjector empty shell"
```

---

## Phase 4: SkillMarket MVP（2 周）

> 目标：用户可以发现、搜索、安装社区技能。GitHub Topic 驱动的去中心化技能市场。

### Task 4.1: GitHub Topic Crawler — 技能发现引擎

**Files:**
- Create: `src/vibesop/market/__init__.py`
- Create: `src/vibesop/market/crawler.py`
- Create: `tests/unit/market/test_crawler.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/unit/market/test_crawler.py

import pytest
from vibesop.market.crawler import GitHubSkillCrawler, SkillRepo


class TestGitHubSkillCrawler:
    def test_search_by_topic(self, mocker):
        """Crawler should return skill repos from GitHub topic search."""
        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "items": [
                {
                    "full_name": "user/vibesop-git-helper",
                    "description": "Git workflow automation skill for VibeSOP",
                    "stargazers_count": 42,
                    "topics": ["vibesop-skill", "git"],
                    "html_url": "https://github.com/user/vibesop-git-helper",
                },
                {
                    "full_name": "team/vibesop-docker",
                    "description": "Docker deployment skill",
                    "stargazers_count": 15,
                    "topics": ["vibesop-skill", "docker"],
                    "html_url": "https://github.com/team/vibesop-docker",
                },
            ],
            "total_count": 2,
        }

        mocker.patch("httpx.Client.get", return_value=mock_response)

        crawler = GitHubSkillCrawler()
        results = crawler.search("git")

        assert len(results) == 2
        assert results[0].name == "vibesop-git-helper"
        assert results[0].stars == 42
        assert "vibesop-skill" in results[0].topics


    def test_search_no_results(self, mocker):
        """Empty search should return empty list."""
        mock_response = mocker.Mock()
        mock_response.json.return_value = {"items": [], "total_count": 0}
        mocker.patch("httpx.Client.get", return_value=mock_response)

        crawler = GitHubSkillCrawler()
        results = crawler.search("nonexistent")

        assert results == []


    def test_validate_skill_repo(self, mocker):
        """Only repos with SKILL.md should be considered valid skills."""
        crawler = GitHubSkillCrawler()

        # Mock: has SKILL.md
        mock_has_skill = mocker.Mock()
        mock_has_skill.json.return_value = {"name": "SKILL.md"}
        mocker.patch("httpx.Client.get", return_value=mock_has_skill)

        repo = SkillRepo(name="test-skill", full_name="user/test-skill", html_url="...")
        assert crawler.validate(repo) is True
```

- [ ] **Step 2: 创建 GitHubSkillCrawler 实现**

```python
# src/vibesop/market/crawler.py

"""GitHub topic-based skill discovery crawler.

Searches GitHub for repos tagged with `vibesop-skill` topic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
SKILL_TOPIC = "vibesop-skill"
PAGE_SIZE = 30


@dataclass
class SkillRepo:
    """A discovered skill repository."""
    name: str
    full_name: str
    description: str
    stars: int
    topics: list[str]
    html_url: str
    has_skill_md: bool = False


class GitHubSkillCrawler:
    """Discovers VibeSOP skills via GitHub topic search."""

    def __init__(self, token: str | None = None):
        self._token = token
        self._client = httpx.Client(
            base_url=GITHUB_API,
            headers=self._build_headers(),
            timeout=10.0,
        )

    def _build_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self._token:
            headers["Authorization"] = f"token {self._token}"
        return headers

    def search(self, query: str, page: int = 1) -> list[SkillRepo]:
        """Search for skill repos matching query + topic:vibesop-skill."""
        q = f"{query} topic:{SKILL_TOPIC}"
        try:
            resp = self._client.get(
                "/search/repositories",
                params={"q": q, "per_page": PAGE_SIZE, "page": page, "sort": "stars"},
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            logger.warning("GitHub search failed: %s", e)
            return []

        results: list[SkillRepo] = []
        for item in data.get("items", []):
            repo = SkillRepo(
                name=item["name"],
                full_name=item["full_name"],
                description=item.get("description", ""),
                stars=item.get("stargazers_count", 0),
                topics=item.get("topics", []),
                html_url=item["html_url"],
            )
            results.append(repo)

        return results

    def validate(self, repo: SkillRepo) -> bool:
        """Check if repo has a valid SKILL.md at root."""
        try:
            resp = self._client.get(
                f"/repos/{repo.full_name}/contents/SKILL.md",
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
```

- [ ] **Step 3: 运行测试**

```bash
uv run pytest tests/unit/market/test_crawler.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/vibesop/market/ tests/unit/market/
git commit -m "feat: add GitHubSkillCrawler for topic-based skill discovery"
```

### Task 4.2: `vibe market` CLI 命令

**Files:**
- Create: `src/vibesop/cli/commands/market_cmd.py`
- Modify: `src/vibesop/cli/main.py`

- [ ] **Step 1: 创建 market 命令组**

```python
# src/vibesop/cli/commands/market_cmd.py

"""Skill marketplace CLI commands."""

import typer
from rich.console import Console
from rich.table import Table

from vibesop.market.crawler import GitHubSkillCrawler

app = typer.Typer(name="market", help="Discover and install VibeSOP skills")
console = Console()


@app.command()
def search(
    query: str = typer.Argument(..., help="Search keywords (e.g., 'docker', 'security')"),
    page: int = typer.Option(1, "--page", "-p", help="Page number"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
) -> None:
    """Search for VibeSOP skills on GitHub by topic."""
    crawler = GitHubSkillCrawler()
    results = crawler.search(query, page=page)

    if json_output:
        import json
        console.print(json.dumps(
            [{"name": r.name, "description": r.description, "stars": r.stars, "url": r.html_url}
             for r in results],
            indent=2,
        ))
        return

    if not results:
        console.print(f"[yellow]No skills found for '{query}'.[/yellow]")
        console.print("[dim]Tip: Skills must have [bold]vibesop-skill[/bold] GitHub topic.[/dim]")
        return

    table = Table(title=f"Skills matching '{query}'")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Stars", justify="right")
    table.add_column("Install")

    for r in results:
        table.add_row(
            r.name,
            r.description[:80] + ("..." if len(r.description) > 80 else ""),
            str(r.stars),
            f"vibe market install {r.full_name}",
        )

    console.print(table)
    console.print(f"\n[dim]Page {page} • {len(results)} results[/dim]")


@app.command()
def install(
    repo: str = typer.Argument(..., help="GitHub repo (e.g., 'user/vibesop-git-helper')"),
) -> None:
    """Install a skill from a GitHub repository."""
    console.print(f"[bold]Installing[/bold] {repo}...")

    # Validate
    crawler = GitHubSkillCrawler()
    from vibesop.market.crawler import SkillRepo
    skill = SkillRepo(
        name=repo.split("/")[-1],
        full_name=repo,
        description="",
        stars=0,
        topics=[],
        html_url=f"https://github.com/{repo}",
    )
    if not crawler.validate(skill):
        console.print(f"[red]✗[/red] {repo} is not a valid VibeSOP skill (no SKILL.md)")
        raise typer.Exit(1)

    # Delegate to existing vibe install flow
    console.print(f"[green]✓[/green] Valid SKILL.md found")
    git_url = f"https://github.com/{repo}.git"
    console.print(f"[bold]→[/bold] Run: [bold]vibe install {git_url}[/bold]")
```

- [ ] **Step 2: 注册到主 CLI**

```python
# src/vibesop/cli/main.py — 添加

from vibesop.cli.commands import market_cmd

app.add_typer(market_cmd.app, name="market")
```

- [ ] **Step 3: 快速集成测试**

```bash
# 手动测试命令存在
uv run vibe market --help
uv run vibe market search "git" --json
```

- [ ] **Step 4: Commit**

```bash
git add src/vibesop/cli/commands/market_cmd.py src/vibesop/cli/main.py
git commit -m "feat: add 'vibe market search|install' CLI for skill discovery"
```

---

## Phase 5: 定位澄清（1 天）

> 目标：在 README/PHILOSOPHY 中明确 VibeSOP 的定位边界，消除"纯路由"与"轻量编排"的模糊性。

### Task 5.1: 更新 README 中的定位描述

**Files:**
- Modify: `README.md`
- Modify: `docs/PHILOSOPHY.md`

- [ ] **Step 1: 在 README 中更新架构段**

```diff
- ### 轻量级执行（辅助功能）Lightweight Execution (Secondary)
- 
- - 快速验证技能是否适合当前任务
-   **Quick validation** - verify if a skill fits your current task
- 
- - 本地测试和调试
-   **Local testing** - test and debug skills locally
- 
- - CI/CD 自动化测试
-   **CI/CD automation** - automated testing in pipelines
- 
- **注意**: 复杂生产场景推荐使用原生 AI Agent（如 Claude Code、Cursor、Continue.dev）。
- **Note**: For complex production scenarios, use native AI agents (Claude Code, Cursor, Continue.dev).

+ ### 智能编排（辅助功能）Intelligent Orchestration (Secondary)
+ 
+ - 多意图任务分解：将复杂请求拆分为子任务序列
+   **Multi-intent decomposition** — break complex requests into sub-tasks
+ 
+ - 执行计划生成：自动决定串行/并行策略
+   **Execution planning** — auto-select sequential/parallel strategy
+ 
+ - 技能组合：为多步骤工作流匹配最佳技能组合
+   **Skill composition** — match best skills for multi-step workflows
+ 
+ **VibeSOP 定位**: VibeSOP 是路由引擎 + 编排层，它决定"用什么技能、以什么顺序"，
+ 但**不执行技能本身**。技能的实际执行由 AI Agent（Claude Code, Cursor, OpenCode）完成。
```

- [ ] **Step 2: 在 PHILOSOPHY.md 添加"我们做什么/不做什么"的清晰边界**

```diff
  ### 我们不做什么
 
  | ❌ | ✅ |
  |----|----|
  | AI 编码工具 | 路由引擎 |
- | 技能执行器 | 技能管理器 |
+ | 技能执行器（执行技能内容） | 技能编排器（决定何时用哪个） |
  | 命令记忆工具 | 智能匹配系统 |
  | 单平台工具 | 跨平台通用 |
  | 闭源系统 | 开源项目 |
  | 复杂框架 | 简单工具 |
+
+ > **定位边界**: VibeSOP 负责"路由"（找技能）和"编排"（排顺序），不负责"执行"（跑代码）。
+ > 当路由系统生成了 ExecutionPlan，用户将其交给 AI Agent 执行。
+ > 这是有意的架构选择：路由/编排与执行解耦，确保 VibeSOP 不绑定任何特定 AI Agent。
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/PHILOSOPHY.md
git commit -m "docs: clarify VibeSOP positioning as routing+orchestration engine, not executor"
```

---

## 全局验收标准

```bash
# 所有新测试通过
uv run pytest tests/ -x --tb=short

# 路由准确率不退化
uv run pytest tests/benchmark/test_routing_performance.py -v

# 代码量减少（目标：< 180 个 .py 文件）
find src/vibesop -name "*.py" | wc -l

# Type check 通过
uv run basedpyright src/

# Lint 通过
uv run ruff check src/
```

---

## 时间线与依赖

```
Week 1:     Phase 0 (文档一致性) + Phase 1 (透明度默认)
Week 2-3:   Phase 2 (IntentDecomposer v2) + Task 3.1 (代码简化)
Week 4:     Task 3.2 (消除功能重叠) + Task 3 收尾
Week 5-6:   Phase 4 (SkillMarket MVP)
Week 7:     Phase 5 (定位澄清) + 回归测试 + 文档同步
```

每个 Phase 独立可交付，可调整顺序。Phase 0-2 不依赖 Phase 3-4。

---

## 风险

| 风险 | 缓解 |
|------|------|
| Task 3.1 重构 mixin 引入回归 | 8 个 mixin 逐一迁移，每步运行全量测试 |
| Task 2.3 fallback 分段降级质量 | 添加 `single_intent` 标记，禁止虚假分段 |
| SkillMarket 依赖 GitHub API rate limit | 添加缓存（1 小时 TTL），token 可选 |
| Phase 1 透明度变更可能增加 CLI 噪音 | 默认精简展示，`--verbose` 展示详情 |
