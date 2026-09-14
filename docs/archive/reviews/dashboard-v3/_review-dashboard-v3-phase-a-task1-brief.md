# Dashboard v3 Phase A Task 1 — Review Brief

**Date:** 2026-07-27
**Scope:** Task 1 (`bind_task_context` helper) 代码 + 测试评审
**Reviewer:** pi（按 [[feedback-pi-alone-review-sufficient]] 单评审足够）
**Commit:** `f7bc36d feat(observability): extend current_task_id to carry role_id + bind_task_context`
**Plan:** `docs/plans/2026-07-27-dashboard-v3-phase-a-data-instrumentation.md` Task 1
**Test results:** 5/5 new + 34/34 observability suite green, ruff/basedpyright 0 new errors

---

## What Task 1 changes

### Files modified

| Path | Change |
|------|--------|
| `src/vibesop/core/observability/models.py` | `TraceContext` 加 `current_role_id: str \| None = None`（紧跟 `current_task_id`） |
| `src/vibesop/core/observability/tracer.py` | `trace()` 写 `ctx.current_role_id = role_id`；`span()` / `start_span()` 继承 role_id；新增 `bind_task_context()` 模块级 context manager |
| `src/vibesop/core/observability/__init__.py` | export `bind_task_context` |
| `tests/core/observability/test_tracer_task_role_context.py` | 5 new tests |

### Core design choice

**grok P1-1 落实**：复用现有 `current_task_id` 路径，**没开新 ContextVar**。

`bind_task_context(task_id, role_id)` 直接 mutate 现有 `TraceContext` 对象，退出时 restore 旧值：

```python
@contextmanager
def bind_task_context(task_id, role_id=None):
    tracer = get_tracer()
    if not tracer._enabled:
        yield; return
    ctx = tracer._get_context()
    if ctx is None:
        yield; return
    old_task = ctx.current_task_id
    old_role = ctx.current_role_id
    ctx.current_task_id = task_id
    ctx.current_role_id = role_id
    try:
        yield
    finally:
        ctx.current_task_id = old_task
        ctx.current_role_id = old_role
```

### Test coverage（5 tests）

1. `test_propagates_task_and_role_to_child_span` — bind 块内 `tracer.span()` 拿到 task_id + role_id
2. `test_does_not_leak_after_exit` — 退出后 revert 到外层 trace 的值
3. `test_nested_bind_restores_outer_on_exit` — 嵌套 bind 内层退出后恢复外层 bind
4. `test_outside_trace_is_noop` — 无 active trace 时不报错
5. `test_role_only_bind_keeps_outer_task` — task_id=None 时保留外层 task_id

### Explicit cross-process limitation（pi H2 / grok Q6 落实）

docstring 明文写：
> Cross-process limitation: contextvars does NOT cross process boundaries. Sub-agent execution (Claude Code CLI etc.) runs as a separate OS process — bind has no effect there. Cross-process task attribution is established via the mirror hook writing metadata.parent_session, which the DAG rebuilder joins on.

---

## Key questions for pi

按 [[feedback-pi-alone-review-sufficient]] 聚焦 5 个结构性问题。

### Q1: `bind_task_context` mutable mutation 在 asyncio.gather 下是否安全？

**当前实现**：直接 mutate 现有 `TraceContext` 对象（L97-100 `ctx.current_task_id = task_id`），退出 restore。

**风险场景**：如果两个 asyncio.Task 共享同一个 `TraceContext` 对象（例如 task_b 从 task_a 的 context copy 来），bind 的 mutation 会互相干扰：

```python
async def step_1():
    with bind_task_context(task_id="step-1", role_id="reviewer"):
        await asyncio.sleep(0)  # yield to scheduler
        # 此时 task_2 可能 mutate 了 ctx.current_task_id
        with tracer.span("llm", "llm"):  # ← 这个 span 的 task_id 可能错乱
            pass

async def step_2():
    with bind_task_context(task_id="step-2", role_id="implementer"):
        await asyncio.sleep(0)
        with tracer.span("llm", "llm"):
            pass

# 同一 trace 下两个协程并行
with tracer.trace("plan"):
    asyncio.gather(step_1(), step_2())
```

**现有 `test_async_isolation.py` 不覆盖这个场景**——它测的是"每个 asyncio.Task 各自开 trace 时不互相干扰"（每次 `tracer.trace()` 都 `_set_context(new_ctx)` 创建独立对象）。bind_task_context 是在已有 trace 内 mutate，**不调 `_set_context()`**。

**问题**：
1. 真实 asyncio context copy 语义下，两个 task 是否共享同一个 `TraceContext` 对象？
2. 如果共享，bind 的 mutation 是否会让 task_1 / task_2 的 span task_id 错乱？
3. 是否应该：
   - (a) 文档化"bind 仅用于顺序场景，不用于并行 task 隔离"
   - (b) 改为 token-based（`ContextVar.set()` + `Var.reset(token)`）
   - (c) 加一个 `test_concurrent_binds_in_gather` 测试验证现有实现

### Q2: 缺少 bind + `start_span`（手动 API）组合测试——"测试通过但生产无效"风险

**当前 5 个测试都用 `tracer.span()`（context manager API）**。

**但 SpanWrappedProvider 用的是 `start_span` / `finish_span`（手动 API）**——见 `src/vibesop/llm/span_wrapped.py:128-175`（同步）和 `:177-223`（异步）。

**风险**：如果 `start_span` 没正确继承 bind 设置的 task_id / role_id，**SpanWrappedProvider 在 bind 块里跑也不会被 tag**——orchestrator 内部 LLM 调用（classifier / decomposer）的 span 仍然 task_id=None。

**但是！** Task 1.4 实现里 `start_span()` L211-212 已经加了 `actual_role_id = role_id or (ctx.current_role_id if ctx else None)`——逻辑上应该工作。但**没测试覆盖**。

**问题**：
1. 是否应该加 `test_bind_task_context_inherit_via_start_span` 验证手动 API 路径？
2. 如果不测，怎么保证 SpanWrappedProvider 在 bind 块里跑时真的拿到 task_id？

### Q3: `test_outside_trace_is_noop` 测试覆盖偏移

**测试名**：`test_outside_trace_is_noop`
**实际断言**：`standalone["task_id"] is None` + `standalone["role_id"] is None`

**问题**：
- span 在无 trace 时本来就没 task_id（不论 bind 是否 no-op，因为 `ctx.current_task_id` 默认 None）
- 测试**没真正验证 bind 的 no-op 行为**——比如 "bind 不应该创建新 ctx" 或 "bind 后 `_get_context()` 仍返回 None"
- 如果将来 bind 实现改成"无 trace 时也创建临时 ctx"，这个测试还会过——但语义错了

**问题**：是否应该改为更精确的断言？比如：
```python
def test_outside_trace_does_not_create_context():
    with bind_task_context(task_id="x", role_id="y"):
        pass
    # Verify _get_context() still returns None — bind didn't create a ctx
    assert get_tracer()._get_context() is None
```

### Q4: `bind_task_context` protected access（`_enabled` / `_get_context`）

**basedpyright 报 2 个 warning**：
```
tracer.py:82:19 - warning: "_enabled" is protected and used outside of the class in which it is declared
tracer.py:86:18 - warning: "_get_context" is protected and used outside of the class in which it is declared
```

**当前设计**：`bind_task_context` 是模块级函数，访问 `ObservabilityTracer` 的 protected 成员。

**替代方案**：
- (a) 把 `bind_task_context` 作为 `ObservabilityTracer` 的方法（用户调用变成 `tracer.bind_task_context(...)`）
- (b) 暴露 public API：`is_enabled()` + `get_current_context()`
- (c) 接受 warning（同模块内 protected access 是 python convention 允许的）

**问题**：哪个方案最合理？为什么？

### Q5: `bind_task_context` 是否应该 `yield ctx`？

**当前**：`yield None`（用户在 with 块内拿不到 ctx 引用）。

**问题**：
- 如果 orchestrator 想验证 bind 是否生效（比如 debug log "current task is now X"），需要别的途径（再调 `_get_context()`）
- Linear / TDD 风格里，context manager 通常 `yield` 有用的对象（如 `with open(...) as f:`）

**替代**：
```python
@contextmanager
def bind_task_context(task_id, role_id=None):
    ...
    try:
        yield ctx  # ← 让用户能读 current_task_id / current_role_id
    finally:
        ...
```

**问题**：是否应该改？为什么？或者 docstring 是否应该明确说明"yield None by design"？

---

## Verdict sought

- **SHIP AS-IS**: Task 1 合理，可以进 Task 2
- **CONDITIONAL**: 列出必修项（如：加 start_span 测试、加并行 bind 测试、文档化顺序场景限制）
- **REJECT**: 设计根本问题（如：mutable mutation 在 asyncio 下确实有 bug，必须改 token-based）

**关注重点**：
1. 是否有"测试通过但生产无效"的隐藏假设（Q1 / Q2 都是这种类型）
2. mutable mutation vs token-based 的设计权衡是否合理
3. 测试覆盖是否到位（特别是 SpanWrappedProvider 走的 start_span 路径）
4. API 设计（protected access + yield 语义）是否符合项目惯例

---

## Task 1 资产

- `src/vibesop/core/observability/tracer.py` — `bind_task_context` 函数（L60-105）
- `src/vibesop/core/observability/models.py` — `TraceContext.current_role_id`（L153）
- `tests/core/observability/test_tracer_task_role_context.py` — 5 tests
- `git show f7bc36d` — 完整 diff
- `docs/plans/2026-07-27-dashboard-v3-phase-a-data-instrumentation.md` — Task 1 §
