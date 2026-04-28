> **Status**: ✅ Delivered (degradation, recommender, market install shipped in v5.1-v5.2)

# VibeSOP v4.4.x → v5.0 质量冲刺计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 VibeSOP 从"功能广但集成浅"的 v4.4.0 推进到工程质量扎实、编排深化的 v5.0-ready 状态

**Architecture:** 五阶段渐进优化——先固基（测试+代码质量），再提效（性能），然后重构（架构拆分），再深化（编排能力），最后可视化（可观测性）。每阶段独立可交付，不阻塞下游。

**Tech Stack:** Python 3.12+, Pydantic v2, Typer, Rich, Pytest, ruff, basedpyright

**与现有 Roadmap 的关系:** Phase 1-3 属于 v4.4.x 加固，Phase 4-5 与 ROADMAP.md v5.0.0 SkillRuntime 并行推进

---

## 背景与动机

### 当前状态

| 指标 | 值 | 目标 | 差距 |
|------|-----|------|------|
| 测试覆盖率 | 74% | >80% | -6% |
| 路由 P95 延迟 | 225ms | <100ms | -125ms |
| Lint 错误 | 1 | 0 | -1 |
| 代码行数 | ~49,000 | ~15,000 | +34,000 |
| CLI main.py | 1,084 行 | <400 行 | -684 |
| UnifiedRouter | 1,164 行 | <600 行 | -564 |

### 核心问题诊断

1. **编排流水线"有但浅"**: MultiIntentDetector 仅用启发式（LLM 确认被注释），TaskDecomposer 无 LLM 时退化严重
2. **CLI 和 Router 都是 God Object**: 渲染、确认、反馈全堆在 main.py；路由、编排、记忆全在 unified.py
3. **测试覆盖倒退**: 从 80% 降到 74%，新增 500+ 测试但覆盖浅
4. **缺少 Agent Execution Protocol**: 编排产出了 ExecutionPlan 但没有让 Agent 执行的标准化协议
5. **没有可观测性**: 所有分析数据在 JSONL 里，无仪表盘、无趋势跟踪

### 哲学一致性检查

本计划遵循 PHILOSOPHY.md 的核心原则：
- **渐进增强**: 分阶段交付，不阻塞、不推翻
- **数据驱动**: 每阶段有可量化成功指标
- **简单优于复杂**: 拆分 > 新增，删除 > 修补

---

## Phase 1: 质量基础加固（v4.4.1，预计 3 天）

### 目标
- 测试覆盖 74% → 80%
- CLI main.py 1,084 → <500 行
- 启用 LLM 多意图二次确认

---

### Task 1: 补充编排流水线端到端测试

**问题**: 编排流水线（detect → decompose → build_plan）没有端到端集成测试，覆盖率从 80% 跌到 74% 的主要原因是新编排代码覆盖率不足。

**Files:**
- Create: `tests/core/orchestration/test_orchestration_pipeline_e2e.py`
- Create: `tests/core/orchestration/conftest.py`

- [ ] **Step 1: 编写编排流水线集成测试**

```python
# tests/core/orchestration/conftest.py
from __future__ import annotations

import pytest
from pathlib import Path

from vibesop.core.routing import UnifiedRouter


@pytest.fixture
def router(tmp_path: Path) -> UnifiedRouter:
    """Create a router with a temp project root for isolated testing."""
    (tmp_path / ".vibe").mkdir(exist_ok=True)
    return UnifiedRouter(project_root=tmp_path)
```

```python
# tests/core/orchestration/test_orchestration_pipeline_e2e.py
"""End-to-end tests for the full orchestration pipeline:
MultiIntentDetector → TaskDecomposer → PlanBuilder → ExecutionPlan
"""
from __future__ import annotations

from vibesop.core.models import OrchestrationMode
from vibesop.core.matching import RoutingContext


class TestOrchestrationPipelineE2E:
    """Test the full orchestration pipeline end-to-end."""

    def test_single_intent_query_stays_single(self, router):
        """Simple queries should produce SINGLE mode result, not orchestrated."""
        result = router.orchestrate(
            "debug the database connection error",
            context=RoutingContext(),
        )
        assert result.mode == OrchestrationMode.SINGLE
        assert result.primary is not None

    def test_multi_intent_with_conjunction_triggers_orchestration(self, router):
        """Queries with conjunctions spanning multiple domains should be orchestrated."""
        result = router.orchestrate(
            "分析项目架构然后给出代码优化建议",
            context=RoutingContext(),
        )
        # This query spans architecture + optimization domains
        # Should be detected as multi-intent
        assert result.mode in (OrchestrationMode.SINGLE, OrchestrationMode.ORCHESTRATED)
        if result.mode == OrchestrationMode.ORCHESTRATED:
            assert result.execution_plan is not None
            assert len(result.execution_plan.steps) >= 2

    def test_multi_intent_without_conjunction_still_detected(self, router):
        """Queries spanning multiple intent domains WITHOUT conjunctions
        should still be detected by domain diversity analysis."""
        result = router.orchestrate(
            "帮我审查这段代码的安全性，看看有没有性能问题",
            context=RoutingContext(),
        )
        # Spans: code_review + security_audit + performance
        assert result.mode in (OrchestrationMode.SINGLE, OrchestrationMode.ORCHESTRATED)

    def test_orchestrator_produces_valid_execution_plan(self, router):
        """Orchestrated results must have valid, non-empty execution plans."""
        result = router.orchestrate(
            "先分析架构再写测试然后做代码审查",
            context=RoutingContext(),
        )
        if result.mode == OrchestrationMode.ORCHESTRATED:
            plan = result.execution_plan
            assert plan is not None
            assert len(plan.steps) >= 2
            assert len(plan.detected_intents) >= 2
            # Each step must have a valid skill_id
            for step in plan.steps:
                assert step.skill_id
                assert step.intent
                assert step.step_number > 0

    def test_orchestrated_plan_has_single_fallback(self, router):
        """Orchestrated results must include a single_fallback
        in case the user rejects the plan."""
        result = router.orchestrate(
            "review the code and deploy it",
            context=RoutingContext(),
        )
        if result.mode == OrchestrationMode.ORCHESTRATED:
            assert result.single_fallback is not None

    def test_orchestration_disabled_respects_config(self, tmp_path):
        """When enable_orchestration=False, all queries stay SINGLE mode."""
        from vibesop.core.config.manager import RoutingConfig

        config = RoutingConfig(enable_orchestration=False)
        router = __import__(
            "vibesop.core.routing", fromlist=["UnifiedRouter"]
        ).UnifiedRouter(project_root=tmp_path, config=config)
        result = router.orchestrate(
            "分析架构然后写测试",
            context=RoutingContext(),
        )
        assert result.mode == OrchestrationMode.SINGLE

    def test_no_false_positive_for_simple_queries(self, router):
        """Simple single-domain queries should NOT be over-decomposed."""
        simple_queries = [
            "帮我调试这个空指针错误",
            "review my pull request",
            "写一个单元测试",
            "部署到生产环境",
        ]
        for query in simple_queries:
            result = router.orchestrate(query, context=RoutingContext())
            # Simple queries should typically stay single
            # (not an assertion since routing can be imperfect, but log for tracking)
            assert result.mode in (OrchestrationMode.SINGLE, OrchestrationMode.ORCHESTRATED)
```

- [ ] **Step 2: 运行测试验证失败（新测试）**

```bash
cd /Users/huchen/Projects/vibesop-py
uv run pytest tests/core/orchestration/test_orchestration_pipeline_e2e.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/core/orchestration/conftest.py tests/core/orchestration/test_orchestration_pipeline_e2e.py
git commit -m "test: add orchestration pipeline end-to-end integration tests"
```

---

### Task 2: 修复现有编排测试中的失败

**问题**: 新增编排代码后可能出现测试失败。

- [ ] **Step 1: 运行全量编排测试，定位失败**

```bash
cd /Users/huchen/Projects/vibesop-py
uv run pytest tests/core/orchestration/ -v --tb=short 2>&1 | grep -E "FAILED|PASSED|ERROR" | head -30
```

- [ ] **Step 2: 逐一修复失败测试**

对每个失败测试，按 `systematic-debugging` 流程定位根因：
1. 检查测试断言的语义是否正确（编排逻辑改了断言没跟上）
2. 检查 router fixture 是否正确初始化
3. 检查 mock/fixture 是否与新代码路径兼容

- [ ] **Step 3: 验证全量编排测试通过**

```bash
cd /Users/huchen/Projects/vibesop-py
uv run pytest tests/core/orchestration/ -v
# Expected: 全部 PASSED (69+ tests)
```

- [ ] **Step 4: Commit**

```bash
git add tests/core/orchestration/
git commit -m "fix: resolve orchestration test failures, all 69+ tests passing"
```

---

### Task 3: 拆分 CLI main.py——提取渲染模块

**问题**: `src/vibesop/cli/main.py` 1,084 行，包含命令定义 + 7 个渲染函数 + 确认流程 + 健康检查 + 反馈收集。渲染函数应提取到独立模块。

**Files:**
- Create: `src/vibesop/cli/render/__init__.py`
- Create: `src/vibesop/cli/render/single.py`
- Create: `src/vibesop/cli/render/orchestration.py`
- Create: `src/vibesop/cli/render/fallback.py`
- Modify: `src/vibesop/cli/main.py`

- [ ] **Step 1: 创建 `src/vibesop/cli/render/__init__.py`**

```python
# src/vibesop/cli/render/__init__.py
"""CLI rendering functions — extracted from main.py to reduce God Module size."""

from vibesop.cli.render.single import render_match_panel, render_no_match
from vibesop.cli.render.fallback import render_fallback_panel
from vibesop.cli.render.orchestration import render_compact_orchestration

__all__ = [
    "render_match_panel",
    "render_no_match",
    "render_fallback_panel",
    "render_compact_orchestration",
]
```

- [ ] **Step 2: 创建 `src/vibesop/cli/render/single.py`**

```python
# src/vibesop/cli/render/single.py
"""Single-skill routing result renderers."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel


def render_match_panel(result: Any, console: Console) -> None:
    """Render normal skill match panel with quality indicators."""
    primary = result.primary
    quality_str = ""
    grade = primary.metadata.get("grade")
    if grade:
        grade_colors = {"A": "green", "B": "green", "C": "yellow", "D": "yellow", "F": "red"}
        color = grade_colors.get(grade, "dim")
        quality_str = f"\n[dim]Quality:[/dim] [{color}]{grade}[/{color}]"
    habit_boost = primary.metadata.get("habit_boost")
    if habit_boost:
        quality_str += " [dim](habit)[/dim]"
        console.print("[dim]💡 Habit boost applied[/dim]")

    deprecated = primary.metadata.get("deprecated_warnings", [])
    if deprecated:
        console.print(
            f"\n[yellow]⚠️  Deprecated skills in ecosystem:[/yellow] {', '.join(deprecated)}"
        )

    console.print(
        Panel(
            f"[bold green]✅ Matched:[/bold green] {primary.skill_id}\n"
            f"[dim]Confidence:[/dim] {primary.confidence:.0%}\n"
            f"[dim]Layer:[/dim] {primary.layer.value}\n"
            f"[dim]Source:[/dim] {primary.source}{quality_str}\n"
            f"[dim]Duration:[/dim] {result.duration_ms:.1f}ms",
            title="[bold]Routing Result[/bold]",
            border_style="blue",
        )
    )
    if result.alternatives:
        console.print("\n[bold]💡 Alternatives:[/bold]")
        for alt in result.alternatives[:3]:
            desc = f" — {alt.description[:50]}" if alt.description else ""
            console.print(f"  • {alt.skill_id} ({alt.confidence:.0%}){desc}")


def render_no_match(result: Any, console: Console) -> None:
    """Render no-match panel."""
    console.print(
        Panel(
            f"[yellow]❓ No suitable match found[/yellow]\n\n"
            f"[dim]Query:[/dim] {result.original_query}\n"
            f"[dim]Routing path:[/dim] {' → '.join([layer.value for layer in result.routing_path])}\n\n"
            f"[dim]Try:[/dim]\n"
            f"  • Using more specific keywords\n"
            f"  • Lowering the threshold\n"
            f"  • Listing available skills",
            title="[bold]Routing Result[/bold]",
            border_style="yellow",
        )
    )
```

- [ ] **Step 3: 创建 `src/vibesop/cli/render/fallback.py`**

```python
# src/vibesop/cli/render/fallback.py
"""Fallback routing result renderer."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel


def render_fallback_panel(result: Any, console: Console) -> None:
    """Render fallback-llm routing result panel."""
    alt_text = ""
    if result.alternatives:
        alt_text = "\n[bold]💡 Nearest installed skills:[/bold]\n"
        for alt in result.alternatives[:3]:
            desc = f" — {alt.description[:50]}" if alt.description else ""
            alt_text += f"  • {alt.skill_id} ({alt.confidence:.0%}){desc}\n"
    console.print(
        Panel(
            f"[bold yellow]🤖 Fallback Mode[/bold yellow]\n\n"
            f"No installed skill confidently matched your query.\n"
            f"[dim]Query:[/dim] {result.original_query}\n"
            f"[dim]Routing path:[/dim] {' → '.join([layer.value for layer in result.routing_path])}\n"
            f"{alt_text}\n"
            f"[dim]VibeSOP is a routing engine, not an executor.[/dim]\n"
            f"[dim]Your AI Agent can still process this request using raw LLM.[/dim]\n\n"
            f"[dim]Try:[/dim]\n"
            f"  • Using more specific keywords\n"
            f"  • Browsing available skills: [bold]vibe skills list[/bold]\n"
            f"  • Installing a relevant skill pack",
            title="[bold]Routing Result[/bold]",
            border_style="yellow",
        )
    )
```

- [ ] **Step 4: 创建 `src/vibesop/cli/render/orchestration.py`**

```python
# src/vibesop/cli/render/orchestration.py
"""Orchestration result renderers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich import box
from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from vibesop.core.models import OrchestrationResult


def render_compact_orchestration(
    result: OrchestrationResult,
    console: Console | None = None,
) -> None:
    """Render a compact summary directly from OrchestrationResult."""
    if console is None:
        console = Console()

    table = Table(
        title="[bold cyan]🔍 Routing Summary[/bold cyan]",
        box=box.SIMPLE,
        show_header=False,
        padding=(0, 1),
    )
    table.add_column("Field", style="dim", justify="right")
    table.add_column("Value", style="bold")

    if result.mode.value == "single":
        if result.primary:
            if result.primary.layer.value == "fallback_llm":
                table.add_row("Selected", f"[yellow]{result.primary.skill_id}[/yellow]")
                table.add_row("Status", "[yellow]Fallback (no skill matched)[/yellow]")
            else:
                table.add_row("Selected", f"[green]{result.primary.skill_id}[/green]")
                table.add_row("Confidence", f"{result.primary.confidence:.0%}")
                table.add_row("Layer", result.primary.layer.value)
        else:
            table.add_row("Selected", "[yellow]No match[/yellow]")
        table.add_row("Duration", f"{result.duration_ms:.1f}ms")
        if result.alternatives:
            alt_lines = []
            for alt in result.alternatives[:3]:
                alt_lines.append(
                    f"  • {alt.skill_id} ({alt.confidence:.0%} via {alt.layer.value})"
                )
            table.add_row("Alternatives", "\n".join(alt_lines))
    else:
        plan = result.execution_plan
        if plan:
            table.add_row("Mode", "[cyan]Orchestrated[/cyan]")
            table.add_row("Steps", str(len(plan.steps)))
            table.add_row("Strategy", plan.execution_mode.value)
            step_lines = []
            for step in plan.steps:
                step_lines.append(
                    f"  {step.step_number}. {step.skill_id} — {step.intent}"
                )
            table.add_row("Plan", "\n".join(step_lines))
            if result.single_fallback:
                table.add_row(
                    "Fallback",
                    f"{result.single_fallback.skill_id} ({result.single_fallback.confidence:.0%})",
                )
        else:
            table.add_row("Mode", "[yellow]Orchestrated (no plan)[/yellow]")

    console.print(table)
    console.print()
```

- [ ] **Step 5: 修改 `src/vibesop/cli/main.py`——删除旧渲染函数，替换为导入**

删除以下函数（`_render_match_panel`、`_render_no_match`、`_render_fallback_panel`、`_render_compact_orchestration`），替换为从 `vibesop.cli.render` 导入：

在 main.py 顶部添加：
```python
from vibesop.cli.render import (
    render_match_panel,
    render_no_match,
    render_fallback_panel,
    render_compact_orchestration,
)
```

在 `_handle_single_result` 中替换调用：
```python
# 将 _render_match_panel(result, console) 改为:
render_match_panel(result, console)
# 将 _render_no_match(result, console) 改为:
render_no_match(result, console)
# 将 _render_fallback_panel(result, console) 改为:
render_fallback_panel(result, console)
# 将 _render_compact_orchestration(result, console) 改为:
render_compact_orchestration(result, console)
```

- [ ] **Step 6: 运行 CLI 测试验证导入无错误**

```bash
cd /Users/huchen/Projects/vibesop-py
uv run pytest tests/cli/ -v -k "route" --tb=short
```

- [ ] **Step 7: Commit**

```bash
git add src/vibesop/cli/render/ src/vibesop/cli/main.py
git commit -m "refactor: extract CLI render functions to cli/render/ module, reduce main.py by ~170 lines"
```

---

### Task 4: 启用 MultiIntentDetector LLM 确认阶段

**问题**: `src/vibesop/core/orchestration/multi_intent_detector.py:62` 的 LLM 确认被注释掉，只用启发式判断多意图。应在启发式通过后加轻量 LLM 二次确认（~10 tokens）。

**Files:**
- Modify: `src/vibesop/core/orchestration/multi_intent_detector.py`

- [ ] **Step 1: 启用 LLM 确认逻辑**

修改 `should_decompose` 方法，在启发式通过后调用 LLM 做 yes/no 确认：

```python
# src/vibesop/core/orchestration/multi_intent_detector.py
# 修改 should_decompose 方法

def should_decompose(
    self,
    query: str,
    single_result: RoutingResult,
    llm_client: Any | None = None,
) -> bool:
    """Determine if a query should be decomposed into multiple sub-tasks.

    Returns True only if heuristic passes AND (when available) LLM confirms.
    """
    # Phase 1: Heuristic filter (fast, zero cost)
    heuristic_pass = self._heuristic_check(query, single_result)
    if not heuristic_pass:
        logger.debug("Heuristic rejected multi-intent for query: %s", query[:50])
        return False

    # Phase 2: LLM confirmation (lightweight, ~10 tokens)
    if llm_client is not None:
        llm_confirms = self._llm_confirm_multi_intent(query, llm_client)
        if not llm_confirms:
            logger.debug("LLM rejected multi-intent for query: %s", query[:50])
            return False

    logger.debug("Multi-intent confirmed for query: %s", query[:50])
    return True

def _llm_confirm_multi_intent(self, query: str, llm_client: Any) -> bool:
    """Lightweight LLM yes/no check for multi-intent confirmation.

    Uses a minimal prompt (~10 tokens output) to confirm whether the
    query genuinely contains multiple independent intents.
    """
    prompt = (
        "Does this request contain MULTIPLE INDEPENDENT tasks that "
        "should be handled separately? Answer only YES or NO.\n\n"
        f"Request: {query}"
    )
    try:
        response = llm_client.call(prompt, max_tokens=5, temperature=0.0)
        content = getattr(response, "content", str(response)).strip().upper()
        return content.startswith("YES")
    except Exception as e:
        logger.warning("LLM multi-intent confirmation failed: %s, defaulting to heuristic", e)
        return True  # On failure, trust heuristic to avoid blocking
```

- [ ] **Step 2: 更新 `UnifiedRouter.orchestrate` 以传递 LLM 客户端**

在 `src/vibesop/core/routing/unified.py` 的 `orchestrate` 方法中：

```python
# 修改 orchestrator 调用，传递 LLM 客户端
detector = self._get_multi_intent_detector()
should_decompose = detector.should_decompose(
    query, single_result, llm_client=self._llm
)
```

- [ ] **Step 3: 编写 LLM 确认的测试**

在 `tests/core/orchestration/test_multi_intent_detector.py` 添加：

```python
def test_llm_confirms_multi_intent(self):
    """When LLM confirms, multi-intent is detected."""
    from vibesop.core.orchestration.multi_intent_detector import MultiIntentDetector
    from vibesop.core.models import RoutingResult, SkillRoute, RoutingLayer

    detector = MultiIntentDetector()

    class MockLLM:
        def call(self, prompt, max_tokens=100, temperature=0.1):
            return type("Response", (), {"content": "YES"})()

    result = RoutingResult(
        primary=SkillRoute(skill_id="test", confidence=0.5, layer=RoutingLayer.KEYWORD),
        alternatives=[
            SkillRoute(skill_id="alt1", confidence=0.5, layer=RoutingLayer.KEYWORD),
        ],
    )
    assert detector.should_decompose(
        "分析架构然后写测试",
        result,
        llm_client=MockLLM(),
    )

def test_llm_rejects_false_multi_intent(self):
    """When LLM says NO, even heuristic-positive queries stay single."""
    from vibesop.core.orchestration.multi_intent_detector import MultiIntentDetector
    from vibesop.core.models import RoutingResult, SkillRoute, RoutingLayer

    detector = MultiIntentDetector()

    class MockLLM:
        def call(self, prompt, max_tokens=100, temperature=0.1):
            return type("Response", (), {"content": "NO"})()

    result = RoutingResult(
        primary=SkillRoute(skill_id="test", confidence=0.5, layer=RoutingLayer.KEYWORD),
        alternatives=[
            SkillRoute(skill_id="alt1", confidence=0.5, layer=RoutingLayer.KEYWORD),
        ],
    )
    assert not detector.should_decompose(
        "分析架构然后写测试",
        result,
        llm_client=MockLLM(),
    )

def test_llm_unavailable_falls_back_to_heuristic(self):
    """When LLM raises, trust heuristic to avoid blocking."""
    from vibesop.core.orchestration.multi_intent_detector import MultiIntentDetector
    from vibesop.core.models import RoutingResult, SkillRoute, RoutingLayer

    detector = MultiIntentDetector()

    class BrokenLLM:
        def call(self, prompt, max_tokens=100, temperature=0.1):
            raise RuntimeError("LLM unavailable")

    result = RoutingResult(
        primary=SkillRoute(skill_id="test", confidence=0.5, layer=RoutingLayer.KEYWORD),
        alternatives=[
            SkillRoute(skill_id="alt1", confidence=0.5, layer=RoutingLayer.KEYWORD),
        ],
    )
    assert detector.should_decompose(
        "分析架构然后写测试",
        result,
        llm_client=BrokenLLM(),
    )
```

- [ ] **Step 4: 运行测试**

```bash
cd /Users/huchen/Projects/vibesop-py
uv run pytest tests/core/orchestration/test_multi_intent_detector.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/core/orchestration/multi_intent_detector.py src/vibesop/core/routing/unified.py tests/core/orchestration/test_multi_intent_detector.py
git commit -m "feat: enable LLM confirmation phase in MultiIntentDetector, reduce false positives"
```

---

### Task 5: 删除 UnifiedRouter 向后兼容代理方法

**问题**: `src/vibesop/core/routing/unified.py:1112-1157` 有 6 个标注为 "backward-compatible proxy" 的代理方法，说明迁移不彻底。

- [ ] **Step 1: 搜索所有调用点**

```bash
cd /Users/huchen/Projects/vibesop-py
rg "_try_ai_triage\|_build_ai_triage_prompt\|_try_matcher_pipeline\|_apply_optimizations\|_prefilter_ai_triage_candidates\|_init_llm_client\|_parse_ai_triage_response" src/ tests/ --no-heading
```

- [ ] **Step 2: 将调用点迁移到直接的 service 调用，然后删除 6 个代理方法**

根据搜索结果，将调用改为直接使用 `self._triage_service` 和 `self._matcher_pipeline`，删除代理方法。

- [ ] **Step 3: 运行全量测试，确保无回归**

```bash
cd /Users/huchen/Projects/vibesop-py
uv run pytest -x --tb=short
```

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor: remove backward-compatible proxy methods from UnifiedRouter"
```

---

## Phase 2: 性能优化（v4.4.2，预计 3 天）

### 目标
- 路由 P95 延迟：225ms → <150ms（中期目标 <100ms）
- 纯关键字匹配延迟 <10ms

---

### Task 6: 路由热路径性能基准与 Profiling

**Files:**
- Create: `tests/benchmark/test_routing_hot_path.py`

- [ ] **Step 1: 编写性能基准测试**

```python
# tests/benchmark/test_routing_hot_path.py
"""Performance benchmarks for routing hot path."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from vibesop.core.routing import UnifiedRouter
from vibesop.core.matching import RoutingContext


class TestRoutingHotPath:
    """Benchmark routing performance for common scenarios."""

    @pytest.fixture(scope="class")
    def router(self, tmp_path_factory):
        tmp_path = tmp_path_factory.mktemp("bench")
        (tmp_path / ".vibe").mkdir(exist_ok=True)
        return UnifiedRouter(project_root=tmp_path)

    def _measure(self, router, query: str, iterations: int = 20) -> dict:
        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            router._route(query, context=RoutingContext())
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        times.sort()
        return {
            "p50": times[len(times) // 2],
            "p95": times[int(len(times) * 0.95)],
            "p99": times[int(len(times) * 0.99)],
            "min": times[0],
            "max": times[-1],
        }

    def test_simple_routing_p95_under_50ms(self, router):
        """Simple single-word queries should complete in <50ms P95."""
        stats = self._measure(router, "debug")
        assert stats["p50"] < 50, f"P50 {stats['p50']}ms exceeds 50ms"

    def test_medium_routing_p95_under_150ms(self, router):
        """Medium complexity queries should complete in <150ms P95."""
        stats = self._measure(router, "帮我调试数据库连接错误")
        assert stats["p95"] < 150, f"P95 {stats['p95']}ms exceeds 150ms"

    def test_complex_routing_tracks_latency(self, router):
        """Complex queries should complete and track latency."""
        stats = self._measure(router, "分析架构安全性然后优化代码性能")
        # This is an observation, not a hard assertion — complex queries
        # may have higher latency due to AI triage
        assert stats["max"] < 2000, f"Max {stats['max']}ms suspiciously high"

    def test_routing_is_consistent_across_runs(self, router):
        """Same query should produce consistent results."""
        result1 = router._route("debug error", context=RoutingContext())
        result2 = router._route("debug error", context=RoutingContext())
        if result1.primary and result2.primary:
            assert result1.primary.skill_id == result2.primary.skill_id
```

- [ ] **Step 2: 运行基准测试建立基线**

```bash
cd /Users/huchen/Projects/vibesop-py
uv run pytest tests/benchmark/test_routing_hot_path.py -v -s
```

- [ ] **Step 3: Commit**

```bash
git add tests/benchmark/test_routing_hot_path.py
git commit -m "bench: add routing hot path performance benchmarks"
```

---

### Task 7: 缓存命中率提升——添加常用查询预热

**Files:**
- Modify: `src/vibesop/core/routing/cache.py`

- [ ] **Step 1: 添加语义相似查询缓存**

在 `CacheManager` 中添加基于 TF-IDF 余弦相似度的近似缓存查找：

```python
# 在 CacheManager 中添加方法
def get_similar(self, query: str, similarity_threshold: float = 0.85) -> dict | None:
    """Find a cached result for a semantically similar query.
    
    Uses TF-IDF cosine similarity on cached query keys.
    Falls back to exact match if no similar query is found.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    
    if not self._cache:
        return None
    
    cached_queries = list(self._cache.keys())
    if not cached_queries:
        return None
    
    try:
        vectorizer = TfidfVectorizer().fit(cached_queries + [query])
        cached_vectors = vectorizer.transform(cached_queries)
        query_vector = vectorizer.transform([query])
        similarities = cosine_similarity(query_vector, cached_vectors)[0]
        best_idx = similarities.argmax()
        if similarities[best_idx] >= similarity_threshold:
            return self._cache[cached_queries[best_idx]]
    except Exception:
        pass
    
    return None
```

- [ ] **Step 2: 在 `TriageService` 中集成近似缓存**

在 `try_ai_triage` 中先尝试相似缓存，命中则跳过 LLM 调用。

- [ ] **Step 3: 运行基准测试验证改进**

```bash
cd /Users/huchen/Projects/vibesop-py
uv run pytest tests/benchmark/test_routing_hot_path.py -v -s
```

- [ ] **Step 4: Commit**

```bash
git commit -m "perf: add semantic similarity cache to reduce AI triage latency"
```

---

### Task 8: 消除重复场景缓存声明

**Files:**
- Modify: `src/vibesop/core/routing/unified.py`

- [ ] **Step 1: 删除重复的 `self._scenario_cache`**

在 `unified.py:234` 和 `unified.py:236` 有完全相同的两行 `self._scenario_cache: dict[str, Any] | None = None`。删除其中一行。

- [ ] **Step 2: Commit**

```bash
git commit -m "fix: remove duplicate scenario_cache initialization in UnifiedRouter"
```

---

## Phase 3: 架构重构（v4.5.0，预计 5 天）

### 目标
- UnifiedRouter: 1,164 行 → <600 行
- CLI main.py: <500 行
- 消除混合职责

---

### Task 9: 从 CLI main.py 提取确认流程和反馈收集

**Files:**
- Create: `src/vibesop/cli/interactive/__init__.py`
- Create: `src/vibesop/cli/interactive/confirmation.py`
- Create: `src/vibesop/cli/interactive/feedback.py`
- Create: `src/vibesop/cli/interactive/plan_editor.py`
- Modify: `src/vibesop/cli/main.py`

- [ ] **Step 1: 创建 `src/vibesop/cli/interactive/confirmation.py`**

将 `_needs_confirmation`、`_run_confirmation_flow` 提出：

```python
# src/vibesop/cli/interactive/confirmation.py
"""User confirmation flow for routing decisions."""

from __future__ import annotations

import sys
from typing import Any

import questionary
from rich.console import Console

from vibesop.cli.routing_report import render_routing_report
from vibesop.core.models import RoutingResult


def needs_confirmation(
    result: Any,
    router: Any,
    yes: bool = False,
    json_output: bool = False,
    validate: bool = False,
    is_orchestrated: bool = False,
) -> bool:
    """Determine if user confirmation is needed for a routing result."""
    if yes or json_output or validate:
        return False
    confirmation_mode = router._config.confirmation_mode
    if confirmation_mode == "never" or not sys.stdin.isatty():
        return False
    if is_orchestrated:
        if confirmation_mode == "ambiguous_only" and result.execution_plan:
            all_confident = all(
                getattr(step, "confidence", 0) >= router._config.auto_select_threshold
                for step in result.execution_plan.steps
            )
            return not all_confident
        return True
    return not (
        confirmation_mode == "ambiguous_only"
        and result.primary
        and result.primary.confidence >= router._config.auto_select_threshold
    )


def run_confirmation_flow(result: Any, console: Console) -> None:
    """Interactive confirmation: confirm / alternative / skip."""
    routing_result = RoutingResult(
        primary=result.primary,
        alternatives=result.alternatives,
        routing_path=result.routing_path,
        layer_details=result.layer_details,
        query=result.original_query,
        duration_ms=result.duration_ms,
    )
    render_routing_report(routing_result, console=console)

    choices = [
        questionary.Choice("✅ Confirm selected skill", value="confirm"),
        questionary.Choice("🔀 Choose a different skill", value="alternative"),
        questionary.Choice("📝 Skip skill, use raw LLM", value="skip"),
    ]
    choice = questionary.select("How would you like to proceed?", choices=choices).ask()

    if choice == "alternative" and result.alternatives:
        _choose_alternative(result, console)
    elif choice == "skip":
        result.primary = None


def _choose_alternative(result: Any, console: Console) -> None:
    """Let user choose from alternative skills."""
    alt_choices = [
        questionary.Choice(
            f"{alt.skill_id} ({alt.confidence:.0%} via {alt.layer.value})"
            f"{(' — ' + alt.description[:40]) if alt.description else ''}",
            value=alt.skill_id,
        )
        for alt in result.alternatives[:5]
    ]
    alt_choices.append(questionary.Choice("↩️  Back", value="back"))
    alt_id = questionary.select("Select a skill:", choices=alt_choices).ask()

    if alt_id and alt_id != "back":
        for alt in result.alternatives:
            if alt.skill_id == alt_id:
                result.primary = alt
                break
```

- [ ] **Step 2: 创建 `src/vibesop/cli/interactive/feedback.py`**

```python
# src/vibesop/cli/interactive/feedback.py
"""User feedback collection after orchestration."""

from __future__ import annotations

import contextlib
from typing import Any

import questionary
from rich.console import Console


def collect_feedback(result: Any, router: Any, console: Console) -> None:
    """Collect user satisfaction feedback after orchestration."""
    try:
        feedback = questionary.select(
            "Did this decomposition match your intent?",
            choices=[
                questionary.Choice("👍 Yes, perfect", value="yes"),
                questionary.Choice("🤔 Mostly, but could be improved", value="partial"),
                questionary.Choice("👎 No, wrong decomposition", value="no"),
                questionary.Choice("Skip", value="skip"),
            ],
        ).ask()

        if feedback == "skip":
            return

        satisfied = feedback == "yes"
        partial = feedback == "partial"

        from vibesop.core.analytics import AnalyticsStore
        store = AnalyticsStore()
        records = store.list_records(limit=1)
        if records:
            record = records[0]
            record.user_satisfied = satisfied
            record.user_modified = partial
            store.record(record)

        if satisfied and result.execution_plan:
            for step in result.execution_plan.steps:
                with contextlib.suppress(Exception):
                    router.record_selection(
                        step.skill_id, result.original_query, was_helpful=True
                    )

        if not satisfied:
            console.print(
                "[dim]Thanks for the feedback. We'll use this to improve routing.[/dim]"
            )
            record_deviation = questionary.confirm(
                "Would you like to record this as a routing deviation for analysis?",
                default=False,
            ).ask()
            if record_deviation:
                console.print(
                    '[dim]Use: vibe deviation record "<query>" "<skill>" <confidence> "<layer>"[/dim]'
                )
    except Exception:
        pass
```

- [ ] **Step 3: 创建 `src/vibesop/cli/interactive/plan_editor.py`**

将 `_edit_execution_plan` 从 main.py 提出。

- [ ] **Step 4: 更新 main.py 导入**

```python
from vibesop.cli.interactive.confirmation import needs_confirmation, run_confirmation_flow
from vibesop.cli.interactive.feedback import collect_feedback
from vibesop.cli.interactive.plan_editor import edit_execution_plan
```

删除原函数定义，替换所有调用点。

- [ ] **Step 5: 运行 CLI 测试**

```bash
cd /Users/huchen/Projects/vibesop-py
uv run pytest tests/cli/ -v --tb=short
```

- [ ] **Step 6: Commit**

```bash
git commit -m "refactor: extract confirmation, feedback, and plan editor from CLI main.py"
```

---

### Task 10: 拆分 UnifiedRouter——提取 CandidateManager

**Files:**
- Create: `src/vibesop/core/routing/candidate_manager.py`
- Modify: `src/vibesop/core/routing/unified.py`
- Modify: `src/vibesop/core/routing/__init__.py`

- [ ] **Step 1: 创建 `src/vibesop/core/routing/candidate_manager.py`**

将以下职责从 UnifiedRouter 提取出来：
- `_get_candidates`
- `_get_cached_candidates`
- `reload_candidates`
- `_extract_name_keywords`
- `_get_skill_source`
- `_warm_up_matchers`
- 候选过滤（enabled/scope/lifecycle）

```python
# src/vibesop/core/routing/candidate_manager.py
"""Candidate management — skill discovery, filtering, and caching."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from vibesop.core.skills.lifecycle import SkillLifecycle, SkillLifecycleManager


class CandidateManager:
    """Manages skill candidate discovery, filtering, and caching.

    Handles:
    - Skill discovery from multiple search paths
    - Filtering by enablement, scope, and lifecycle state
    - Candidate caching with invalidation
    - Automatic keyword extraction from skill names
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._skill_loader: Any = None
        self._candidates_cache: list[dict[str, Any]] | None = None
        self._cache_lock = threading.Lock()

    def get_candidates(self) -> list[dict[str, Any]]:
        """Discover and return all skill candidates."""
        # ... (移植原有 _get_candidates 逻辑)
        pass

    def get_cached_candidates(self) -> list[dict[str, Any]]:
        """Return cached candidates, loading if necessary."""
        if self._candidates_cache is not None:
            return self._candidates_cache
        with self._cache_lock:
            if self._candidates_cache is None:
                self._candidates_cache = self.get_candidates()
            return self._candidates_cache

    def reload(self) -> int:
        """Invalidate cache and reload."""
        self._candidates_cache = None
        return len(self.get_cached_candidates())

    def filter_routable(
        self, candidates: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Filter candidates by enablement, scope, and lifecycle state.

        Returns:
            (filtered_candidates, deprecated_warnings)
        """
        filtered: list[dict[str, Any]] = []
        deprecated_warnings: list[str] = []

        for c in candidates:
            if not c.get("enabled", True):
                continue
            lifecycle_str = c.get("lifecycle", "active")
            try:
                lifecycle = SkillLifecycle(lifecycle_str)
            except ValueError:
                lifecycle = SkillLifecycle.ACTIVE
            if not SkillLifecycleManager.is_routable(lifecycle):
                continue
            if lifecycle == SkillLifecycle.DEPRECATED:
                deprecated_warnings.append(str(c.get("id", "")))
            scope = c.get("scope", "project")
            if scope == "project":
                source_file = c.get("source_file")
                if source_file:
                    try:
                        Path(source_file).resolve().relative_to(
                            self.project_root.resolve()
                        )
                    except ValueError:
                        continue
            filtered.append(c)

        return filtered, deprecated_warnings
```

- [ ] **Step 2: 修改 UnifiedRouter——委托给 CandidateManager**

在 `__init__` 中创建 `self._candidate_manager = CandidateManager(self.project_root)`

将候选管理方法改为委托：
```python
def _get_candidates(self, _query: str = "") -> list[dict[str, Any]]:
    return self._candidate_manager.get_candidates()

def _get_cached_candidates(self) -> list[dict[str, Any]]:
    return self._candidate_manager.get_cached_candidates()

def reload_candidates(self) -> int:
    return self._candidate_manager.reload()
```

- [ ] **Step 3: 运行全量测试**

```bash
cd /Users/huchen/Projects/vibesop-py
uv run pytest -x --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add src/vibesop/core/routing/candidate_manager.py src/vibesop/core/routing/unified.py
git commit -m "refactor: extract CandidateManager from UnifiedRouter, -200 lines"
```

---

## Phase 4: 编排深化（v5.0.0，预计 2 周）

---

### Task 11: 定义 Agent Execution Protocol

**问题**: 编排产出了 `ExecutionPlan`，但没有让 AI Agent 接收执行的标准化协议。

**Files:**
- Create: `src/vibesop/agent/execution_protocol.py`
- Create: `tests/agent/test_execution_protocol.py`

- [ ] **Step 1: 定义 ExecutionProtocol 数据模型**

```python
# src/vibesop/agent/execution_protocol.py
"""Agent Execution Protocol — standard interface for AI Agents to execute plans.

Defines the contract between VibeSOP (plan producer) and AI Agents
(plan consumers). Agents implement this protocol to receive and report
multi-step execution plans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from vibesop.core.models import ExecutionPlan, ExecutionStep


class StepResultStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    """Result of executing a single step in a plan."""
    step_id: str
    skill_id: str
    status: StepResultStatus
    output: str = ""
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class PlanExecutionResult:
    """Result of executing a full plan."""
    plan_id: str
    results: list[StepResult] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.status == StepResultStatus.SUCCESS)

    @property
    def all_succeeded(self) -> bool:
        return all(r.status == StepResultStatus.SUCCESS for r in self.results)


class ExecutionProtocol:
    """Protocol for AI Agents to consume and report on execution plans.

    VibeSOP produces ExecutionPlan → Agent receives via this protocol
    Agent executes steps → Agent reports results via this protocol
    """

    @staticmethod
    def plan_to_agent_instructions(plan: ExecutionPlan) -> str:
        """Convert an ExecutionPlan into natural language instructions for the agent.

        The output is a Markdown-formatted string the AI Agent can directly
        use as a prompt for step-by-step execution.
        """
        lines = [
            f"# Execution Plan: {plan.original_query}",
            "",
            f"**Strategy**: {plan.execution_mode.value}",
            f"**Steps**: {len(plan.steps)}",
            f"**Reasoning**: {plan.reasoning}",
            "",
            "---",
            "",
        ]
        for step in plan.steps:
            deps = f" (depends on: {', '.join(step.dependencies)})" if step.dependencies else ""
            lines.append(
                f"## Step {step.step_number}: {step.intent}{deps}"
            )
            lines.append(f"- **Skill**: `{step.skill_id}`")
            lines.append(f"- **Task**: {step.input_query}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def plan_to_json(plan: ExecutionPlan) -> dict[str, Any]:
        """Serialize an ExecutionPlan to JSON for programmatic consumption."""
        return plan.to_dict()

    @staticmethod
    def validate_results(plan: ExecutionPlan, results: PlanExecutionResult) -> bool:
        """Validate that execution results cover all plan steps."""
        plan_step_ids = {step.step_id for step in plan.steps}
        result_step_ids = {r.step_id for r in results.results}
        return plan_step_ids == result_step_ids
```

- [ ] **Step 2: 编写测试**

```python
# tests/agent/test_execution_protocol.py
"""Tests for Agent Execution Protocol."""

from vibesop.agent.execution_protocol import (
    ExecutionProtocol,
    PlanExecutionResult,
    StepResult,
    StepResultStatus,
)
from vibesop.core.models import (
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
    StepStatus,
)


class TestExecutionProtocol:
    def test_plan_to_instructions_includes_all_steps(self):
        plan = ExecutionPlan(
            plan_id="test-001",
            original_query="分析架构然后写测试",
            steps=[
                ExecutionStep(
                    step_id="s1", step_number=1,
                    skill_id="superpowers-architect",
                    intent="架构分析",
                    input_query="分析项目架构",
                    output_as="step_1_result",
                    status=StepStatus.PENDING,
                ),
                ExecutionStep(
                    step_id="s2", step_number=2,
                    skill_id="superpowers-tdd",
                    intent="测试生成",
                    input_query="生成单元测试",
                    output_as="step_2_result",
                    status=StepStatus.PENDING,
                ),
            ],
            detected_intents=["架构分析", "测试生成"],
            execution_mode=ExecutionMode.SEQUENTIAL,
        )
        instructions = ExecutionProtocol.plan_to_agent_instructions(plan)
        assert "superpowers-architect" in instructions
        assert "superpowers-tdd" in instructions
        assert "SEQUENTIAL" in instructions.upper() or "sequential" in instructions

    def test_plan_to_json_serializable(self):
        import json
        plan = ExecutionPlan(
            plan_id="test-002",
            original_query="review code",
            steps=[ExecutionStep(
                step_id="s1", step_number=1,
                skill_id="gstack-review",
                intent="代码审查",
                input_query="review the code",
                output_as="step_1_result",
                status=StepStatus.PENDING,
            )],
            detected_intents=["代码审查"],
            execution_mode=ExecutionMode.SEQUENTIAL,
        )
        data = ExecutionProtocol.plan_to_json(plan)
        json_str = json.dumps(data)
        assert "test-002" in json_str
        assert "gstack-review" in json_str

    def test_validate_results_matches_all_steps(self):
        plan = ExecutionPlan(
            plan_id="test-003",
            original_query="test",
            steps=[
                ExecutionStep(
                    step_id="s1", step_number=1,
                    skill_id="skill-a", intent="task a",
                    input_query="do a", output_as="a",
                    status=StepStatus.PENDING,
                ),
                ExecutionStep(
                    step_id="s2", step_number=2,
                    skill_id="skill-b", intent="task b",
                    input_query="do b", output_as="b",
                    status=StepStatus.PENDING,
                ),
            ],
            detected_intents=["a", "b"],
            execution_mode=ExecutionMode.PARALLEL,
        )
        results = PlanExecutionResult(
            plan_id="test-003",
            results=[
                StepResult(step_id="s1", skill_id="skill-a", status=StepResultStatus.SUCCESS),
                StepResult(step_id="s2", skill_id="skill-b", status=StepResultStatus.SUCCESS),
            ],
        )
        assert ExecutionProtocol.validate_results(plan, results)

    def test_validate_results_detects_missing_steps(self):
        plan = ExecutionPlan(
            plan_id="test-004",
            original_query="test",
            steps=[
                ExecutionStep(
                    step_id="s1", step_number=1,
                    skill_id="skill-a", intent="task a",
                    input_query="do a", output_as="a",
                    status=StepStatus.PENDING,
                ),
            ],
            detected_intents=["a"],
            execution_mode=ExecutionMode.SEQUENTIAL,
        )
        results = PlanExecutionResult(plan_id="test-004", results=[])
        assert not ExecutionProtocol.validate_results(plan, results)
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/huchen/Projects/vibesop-py
uv run pytest tests/agent/test_execution_protocol.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/vibesop/agent/execution_protocol.py tests/agent/test_execution_protocol.py
git commit -m "feat: add Agent Execution Protocol for standardized plan consumption"
```

---

### Task 12: 改进 TaskDecomposer 规则回退——处理嵌套意图

**Files:**
- Modify: `src/vibesop/core/orchestration/task_decomposer.py`
- Modify: `tests/core/orchestration/test_task_decomposer_fallback.py`

- [ ] **Step 1: 增强 `_split_by_intent_boundaries`——处理无连接词的复合查询**

当前 `_fallback_decomposition` 依赖连接词切割。增加一个语义边界检测：当检测到多个意图域且无连接词时，尝试通过意图域关键词的分布自然分割。

```python
# 在 TaskDecomposer 中添加
def _detect_implicit_intent_boundaries(self, query: str) -> list[str]:
    """Detect intent boundaries in queries without explicit conjunctions.

    When a query spans multiple intent domains without clear separators
    (e.g., "代码安全性和性能优化"), use keyword density to find natural
    split points.
    """
    query_lower = query.lower()
    # Find all intent keyword positions with their intent labels
    positions: list[tuple[int, str]] = []
    for intent, keywords in self.INTENT_PATTERNS.items():
        for kw in keywords:
            idx = query_lower.find(kw)
            if idx >= 0:
                positions.append((idx, intent))

    if len(set(intent for _, intent in positions)) < 2:
        return [query]

    # Sort by position, find transition between different intents
    positions.sort(key=lambda x: x[0])
    segments = []
    current_start = 0
    current_intent = positions[0][1] if positions else None

    for i, (pos, intent) in enumerate(positions):
        if intent != current_intent and pos - current_start > self.MIN_QUERY_LENGTH:
            segment = query[current_start:pos].strip()
            if len(segment) >= self.MIN_QUERY_LENGTH:
                segments.append(segment)
            current_start = pos
            current_intent = intent

    if current_start < len(query):
        segment = query[current_start:].strip()
        if len(segment) >= self.MIN_QUERY_LENGTH:
            segments.append(segment)

    return segments if len(segments) >= 2 else [query]
```

- [ ] **Step 2: 在 `_fallback_decomposition` 中集成**

在现有 `_segment_by_conjunctions` 之后、合并之前调用 `_detect_implicit_intent_boundaries`，当连接词切割无效时尝试隐式边界检测。

- [ ] **Step 3: 添加测试用例**

```python
# 在 test_task_decomposer_fallback.py 中添加
def test_implicit_intent_boundaries_without_conjunctions(self):
    """Queries spanning multiple domains without conjunctions should still split."""
    decomposer = TaskDecomposer()
    tasks = decomposer._fallback_decomposition(
        "帮我审查代码安全性并优化性能瓶颈"
    )
    # Should detect at least: code_review + optimization
    intents = {t.intent for t in tasks}
    assert len(intents) >= 2 or len(tasks) >= 2

def test_single_domain_query_not_over_split(self):
    """Single-domain queries should not be incorrectly split."""
    decomposer = TaskDecomposer()
    tasks = decomposer._fallback_decomposition("调试数据库连接池泄漏")
    # Should produce at most 1 task (or all same intent)
    assert len(tasks) <= 1
```

- [ ] **Step 4: 运行测试**

```bash
cd /Users/huchen/Projects/vibesop-py
uv run pytest tests/core/orchestration/test_task_decomposer_fallback.py -v
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: improve TaskDecomposer fallback with implicit intent boundary detection"
```

---

## Phase 5: 可观测性（v5.0.x，预计 5 天）

---

### Task 13: 创建路由分析仪表盘命令

**Files:**
- Create: `src/vibesop/cli/commands/dashboard_cmd.py`
- Modify: `src/vibesop/cli/main.py`

- [ ] **Step 1: 编写 `vibe dashboard` 命令**

```python
# src/vibesop/cli/commands/dashboard_cmd.py
"""VibeSOP Dashboard — interactive analytics and routing insights."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

app = typer.Typer(name="dashboard", help="Analytics and routing insights")

console = Console()


@app.command()
def overview() -> None:
    """Show routing analytics overview."""
    from vibesop.core.analytics import AnalyticsStore

    store = AnalyticsStore()
    records = store.list_records(limit=100)

    if not records:
        console.print("[yellow]No routing data yet. Run some queries first.[/yellow]")
        return

    total = len(records)
    orchestrated = sum(1 for r in records if r.mode == "orchestrated")
    satisfied = sum(1 for r in records if r.user_satisfied is True)
    dissatisfied = sum(1 for r in records if r.user_satisfied is False)

    skill_counts: dict[str, int] = {}
    for r in records:
        if r.primary_skill:
            skill_counts[r.primary_skill] = skill_counts.get(r.primary_skill, 0) + 1

    top_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    table = Table(title="[bold cyan]📊 Routing Analytics[/bold cyan]")
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="bold")

    table.add_row("Total queries", str(total))
    table.add_row("Orchestrated", f"{orchestrated} ({orchestrated / max(total, 1) * 100:.0f}%)")
    table.add_row("Satisfied", f"{satisfied} ({satisfied / max(total, 1) * 100:.0f}%)")
    table.add_row("Dissatisfied", f"{dissatisfied} ({dissatisfied / max(total, 1) * 100:.0f}%)")

    console.print(table)

    if top_skills:
        console.print("\n[bold]Top Skills Used:[/bold]")
        for skill_id, count in top_skills:
            console.print(f"  • [cyan]{skill_id}[/cyan] — {count}x")


@app.command()
def layers() -> None:
    """Show routing layer distribution."""
    from vibesop.core.analytics import AnalyticsStore

    store = AnalyticsStore()
    records = store.list_records(limit=200)

    layer_counts: dict[str, int] = {}
    for r in records:
        for layer in r.routing_layers:
            layer_counts[layer] = layer_counts.get(layer, 0) + 1

    if not layer_counts:
        console.print("[yellow]No layer data available.[/yellow]")
        return

    table = Table(title="[bold cyan]📊 Layer Distribution[/bold cyan]")
    table.add_column("Layer", style="cyan")
    table.add_column("Hits", style="bold")
    table.add_column("Share", style="dim")

    total_hits = sum(layer_counts.values())
    for layer, count in sorted(layer_counts.items(), key=lambda x: x[1], reverse=True):
        pct = count / max(total_hits, 1) * 100
        bar = "█" * int(pct / 5)
        table.add_row(layer, str(count), f"{bar} {pct:.0f}%")

    console.print(table)
```

- [ ] **Step 2: 在 main.py 注册 dashboard 命令**

```python
from vibesop.cli.commands.dashboard_cmd import app as dashboard_app
app.add_typer(dashboard_app, name="dashboard")
```

- [ ] **Step 3: 编写测试**

```python
# tests/cli/test_dashboard.py
def test_dashboard_overview_no_data(tmp_path, capsys):
    """Dashboard should handle empty analytics gracefully."""
    # ... test that `vibe dashboard overview` shows "No routing data yet"
    pass

def test_dashboard_overview_with_data(tmp_path, capsys):
    """Dashboard should show stats when analytics exist."""
    # ... seed analytics data, verify table output
    pass
```

- [ ] **Step 4: 运行测试**

```bash
cd /Users/huchen/Projects/vibesop-py
uv run pytest tests/cli/test_dashboard.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/cli/commands/dashboard_cmd.py tests/cli/test_dashboard.py src/vibesop/cli/main.py
git commit -m "feat: add 'vibe dashboard' command for routing analytics and insights"
```

---

## 成功指标总结

| 阶段 | 版本 | 核心交付 | 量化目标 |
|------|------|---------|---------|
| Phase 1 | v4.4.1 | 测试加固 + CLI 拆分 + LLM 确认 | 覆盖率 74→80%, main.py <500 行 |
| Phase 2 | v4.4.2 | 性能优化 | P95 <150ms, 缓存命中率 >50% |
| Phase 3 | v4.5.0 | 架构重构 | UnifiedRouter <600 行, Lint 0 |
| Phase 4 | v5.0.0 | 编排深化 | Agent Protocol + 隐式意图检测 |
| Phase 5 | v5.0.x | 可观测性 | `vibe dashboard` 命令可用 |

## 验证策略

每个 Phase 完成后运行：

```bash
# 全量测试 + 覆盖率
uv run pytest --cov=src/vibesop --cov-report=term --cov-report=html -q

# Lint
uv run ruff check .

# Type check
uv run basedpyright

# 确认关键指标
grep "TOTAL" htmlcov/index.html  # 覆盖率
```

---

## 执行选择

**1. Subagent-Driven (推荐)** — 每个 Task 派发独立子 Agent，Task 间 Review

**2. Inline Execution** — 当前会话内按顺序执行，批量提交

> 建议 Phase 1-2 使用 Inline（改动小、风险低），Phase 3-5 使用 Subagent-Driven（改动大、需要并行）。
