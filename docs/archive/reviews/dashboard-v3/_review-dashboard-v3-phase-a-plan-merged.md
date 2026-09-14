# Phase A Plan — grok+pi Merged Verdict

**Date:** 2026-07-27
**评审来源**: grok + pi（双评审完全一致；kimi 不可用，按 [[feedback-review-standard-grok-pi]] 走 grok+pi）
**评审对象**: `docs/plans/2026-07-27-dashboard-v3-phase-a-data-instrumentation.md`（13 task）
**Verdict**: **CONDITIONAL** — 4 个 P0 必修 + 3 个 P1 强烈建议 + 1 Nit

---

## 共识（grok+pi 强信号）

两份评审各自独立得出**几乎完全相同**的结论——这是高质量评审的标志。3 个 Blocker 级问题双方都点名：

| Blocker | grok | pi |
|---------|------|-----|
| Task 4 `task_id=plan_id` fallback 是 vanity metric | "fill rate 达标、step 空壳" | "tests pass, production broken" |
| ExecutionPlan 持久化盲点（Orchestrator 不调 PlanTracker） | "缺 plan↔trace 外键" | "Map dependency edges literally cannot be rendered" |
| contextvars 跨进程限制未文档化 | "全 plan 最大的隐藏假设" | "tracer.py 已注释了不传播" |

**一句话定论**（grok）：Phase A 应交付**可 JOIN 的持久化契约**（plan↔trace、step 结构、`parent_session`），而不是**进程内 fill rate 化妆**。

---

## P0 必修（4 项，落地前必须改进 plan）

### P0-1: 移除 Task 4 的 `task_id=plan_id` fallback（S1 / F1）

**问题**: Task 4 R1 fallback 说"如果 step-level binding 不可达，bind `task_id=plan_id`"。但 `plan_id ≠ step_id`，DAG rebuilder Task 12 的 JOIN 是 `step.spans = [s for s in spans if s.task_id == step.step_id]`——所有 span 都会挂到 plan 节点下，**所有 step 节点变空壳**。

**grok 证据** `[inspected]`: Orchestrator 只建 plan 不执行 step；PlanBuilder.build_plan() 后直接 OrchestrationResult；R1 fallback 与 Task 12 JOIN 契约直接冲突。

**pi 证据** `[inspected]`: ExecutionStep 已有 `step_id` / `assigned_role` / `dependencies` / `parallel_group` 全字段（`models.py:321-397`，Explore agent 确认）；orchestrator 在 plan_building phase 遍历 `plan.steps`。

**修复**:
- **删除** R1 fallback
- Task 4 强制 step-level binding；如果 `PlanBuilder.build_plan()` 不暴露 step iteration，**重构它**（Task 4.3）
- 验收指标改为：`rebuild_dag` fixture 中 step 节点有 children 或明确的 sub_agent 边，**而不是 task_id fill rate**

### P0-2: Task 11.5 mandatory — Orchestrator 接 PlanTracker + 写 trace_id（S3 / F3）

**问题**: v3 § 3.3 DAG 算法第 1 步 `load_plans_for_trace(trace_id)` 假设 `execution_plans.jsonl` 存在且 plan↔trace 可 JOIN。实际：

- **PlanTracker 已完整实现**（`plan_tracker.py`）—— 写 full `ExecutionPlan.to_dict()` 到 `.vibe/execution_plans.jsonl`
- **但 `Orchestrator.orchestrate()` 从不调用它**
- `_record_plan_sequence`（`orchestrator.py:335`）只写 instinct skill 序列到 `instinct_learner.record_sequence()`，是 telemetry，不是 plan 持久化
- **ExecutionPlan schema 没有 `trace_id` 字段**；PlanTracker 写的 plan 全部 trace_id=null

**grok 本地探测** `[executed]`: 135 行 plan，**129 含 dependencies**（依赖边数据够），**0 条含 trace_id**。

**修复**: Task 11.5 从 optional 提升为 **mandatory**（建议放 Task 11 之前作为前置）：
1. `Orchestrator.orchestrate()` 在 completion phase 调 `PlanTracker.create_plan(plan)`
2. 在 active trace 下写 `plan.metadata["trace_id"]`（或一等字段，需 schema migration）
3. `load_plans_for_trace(trace_id)` 按该键过滤
4. 无此 task → Task 11-13 对生产是空转

**这是 v2 评审抓过的"实体未定义"同类问题**：JOIN 边未契约化。

### P0-3: Task 6 改写 — 加 `--include-subagents` flag + parent_session join 契约测试（S2 / F2）

**问题**: Task 6 说"接到 mirror_session_end hook"——**但 hook 已经接入**，只是缺一个 flag。

**pi 证据** `[inspected]`: hook 模板 `vibesop-mirror-session-end.sh.j2` 调：
```bash
vibe conversation import-claude --source "$_JSONL" --conversation-id "$_CONV_ID" --storage-dir "$_STORAGE_DIR"
```
**没传 `--include-subagents`**。CLI 支持（`conversation_cmd.py:135-137`），但 hook 从不传。Sub-agent import 在自动化 mirror 路径**生产环境 0%**。

**grok 证据** `[inspected]`: `import_subagent` 已有 turn 去重 + 稳定 `derive_subagent_conversation_id` + `test_import_subagent_idempotent_on_rerun`——**幂等性已有**。Task 6.5 幂等测试**可选**。但还有另一个问题：**join key 错位**——`parent_session_id=path.stem`（完整 session id），而 conv id 是 `mirror-claude-{session[:20]}`，DAG 用 `parent_session == conversation_id` 会对不上。

**修复**: Task 6 改写为（不是再加一层 hook）：
1. 加 `--include-subagents` flag 到 hook 模板 `vibesop-mirror-session-end.sh.j2`
2. 加**契约测试**：`parent_session` 必须 resolve 到 parent conversation（建议直接写 parent conversation_id，或双写 session_id + conversation_id）
3. Task 6.5 幂等测试**可选**（单元已有）；**join 契约测试不可选**

### P0-4: Task 13 改写 — fixture-based E2E，零 LLM（H1 / F4）

**问题**: Task 13 E2E 写 `orchestrator.orchestrate("complex query")`——内部依赖 ClassifierAgent / MultiIntentDetector / TaskDecomposer，全是 LLM 调用。Plan 没规定 mock 边界 → 极易假绿。

**pi 证据** `[inspected]`: 现有 `test_orchestrate.py` 用短 / disabled query 避开 LLM；orchestrator 测试套件**没有 mock-LLM 模式**。

**修复**: Task 13 拆成两层：
1. **CI 确定性 E2E（Task 13 主体）** — 零 LLM
   - 手写 fixture: `execution_plans.jsonl` + `spans.jsonl` + sub-agent mirror conv
   - 调 `rebuild_dag(trace_id)` → 断言 step 数 / dependency 边 / phase 节点 / sub_agent 挂载
2. **人工 smoke（Task 13.4）** — 可选真 `vibe orchestrate`，**不进默认 CI**

Orchestrator 单测：stub `should_decompose` / decomposer / `build_plan`，**只测 span 形状与 metadata 写回**。

---

## P1 强烈建议（3 项）

### P1-1: Task 1 复用现有 `current_task_id` ContextVar（grok）

**问题**: grok `[inspected]` 发现 `TraceContext.current_task_id` **已在** `tracer.trace(task_id=...)` 继承路径里；子 span 已会吃 task_id。Task 1 若另开 `_task_ctx_var` 却只改 `start_span`、不贯通 `span()`，会**再埋一条不一致路径**。

**修复**: Task 1 改为"**复用 / 扩展** `current_task_id`（+ role），避免双 ContextVar"。先 grep 确认现有实现，再决定是 extend 还是新建。

### P1-2: Task 10 AgentPrefs 推到 Phase E（grok + pi 共识）

**问题**: Task 10 `AgentPrefsStore` 服务 R5（agent_choice）反思闭环。Phase A 无消费者，schema 易废。v3 §6 把 R5 闭环放 Phase E。

**修复**:
- **保留** Task 7-9（ReflectionStore）——与 v3 §6 A6 一致
- **挪走** Task 10（AgentPrefs）→ Phase E
- 工期目标仍写"数据地基"，避免 13 task 里 4 个是反思子系统

### P1-3: Plan 顶部加 "in-process vs cross-process" 数据边界表（grok）

**问题**: Phase A 最大的隐藏假设是"contextvars 解决 task_id 传播"。实际生产主路径是**跨进程**（plan 在 VibeSOP；执行在 Claude Code / 其它 agent CLI），contextvars 不过进程。

**修复**: Plan 正文必须写死数据边界表：

| 数据 | 来源 | contextvars 有效？ | 正确做法 |
|------|------|-------------------|----------|
| plan / step / dependencies | `execution_plans.jsonl` | 否 | PlanTracker 持久化（P0-2） |
| orchestrator phase 边界 | Task 2-3 workflow_node | 进程内即可 | tracer.span |
| step → VibeSOP 内 LLM | bind at step_runner / runtime | **是** | bind_task_context |
| step → 外部 agent / sub-agent | conversation + parent_session | **否** | Task 6 hook + 契约（P0-3） |
| plan ↔ trace | `metadata.trace_id` | 否 | 写 plan 时抄 trace（P0-2） |

**明文禁止**: 把 fill rate 当跨进程成功标准。Map MVP 应允许 step 节点没有 llm children，仍用 plan 的 skill/deps + sub_agent 边构成可用 DAG。

---

## Nit（1 项）

### Nit-1: Task 5 conversation_id 线程参数（grok）

Task 5 写 `orchestration_id` 到 conversation metadata——需要 `conversation_id` 参数。Plan 没说怎么线程化。如果 `orchestrate()` 当前没有 `conversation_id` 参数，需要加上（向后兼容 default=None）。

---

## 修订后的 task 顺序（13 task 不变，但内容大改）

| # | Task | 改动 |
|---|------|------|
| 1 | bind_task_context helper | **P1-1**: 复用现有 current_task_id，不开新 ContextVar |
| 2 | Orchestrator 包 trace context | 不变 |
| 3 | 7 phase workflow_node span | 不变 |
| 4 | step-level task_id binding | **P0-1**: 删除 plan_id fallback，强制 step-level，必要时重构 PlanBuilder |
| 5 | orchestration_id 写回 | **Nit-1**: 加 conversation_id 参数 |
| 6 | mirror hook 接入 sub-agent | **P0-3**: 加 --include-subagents flag + parent_session 契约测试 |
| 7 | Reflection dataclass | 不变 |
| 8 | ReflectionStore append | 不变 |
| 9 | ReflectionStore query/update | 不变 |
| ~~10~~ | ~~AgentPrefsStore~~ | **P1-2**: 推到 Phase E |
| **10 (新)** | **Plan↔Trace 契约** | **P0-2**: Orchestrator 调 PlanTracker.create_plan() + 写 trace_id（mandatory） |
| 11 | DAG rebuilder load plans | 不变（但依赖新 Task 10） |
| 12 | DAG rebuilder JOIN + sub-agent | 不变 |
| 13 | E2E integration test | **P0-4**: fixture-based，零 LLM |

**总数**: 仍是 13 task（删 1 + 加 1）。

---

## 修订后的验证 checklist（替代原 §"Verification checklist"）

- [ ] All 13 task commits landed
- [ ] `uv run pytest` 现有 4434+ tests 全绿 + ~50 新 tests 全绿
- [ ] `uv run ruff check` / `basedpyright` clean
- [ ] **真实数据探测**（替代 fill rate 指标）:
  - [ ] `vibe orchestrate "complex multi-intent query"` 后，`.vibe/execution_plans.jsonl` 新增一条 plan 含 `trace_id` 非空
  - [ ] `.vibe/observability/spans.jsonl` 中**至少一个 llm span 的 task_id 等于某个 step.step_id**（不是 plan_id）
  - [ ] 触发带 sub-agent 的真实 session，`mirror-*.json.metadata.parent_session` 能 resolve 到 parent conversation_id
  - [ ] **`rebuild_dag(trace_id)`** 返回 DAG：>= 1 user_intent + >= 1 orchestrator + >= 2 step + dependency 边 + sub_agent 挂载（**这是主门禁**）

---

## 关注重点回执（brief § Verdict sought）

| brief 关注点 | 评审结论 |
|--------------|---------|
| 1. "测试通过但生产无效"隐藏假设 | **全部成立**：Q1/Q4/Q6 都属于此类 |
| 2. Phase A scope 是否合理 | **大体合理**：Reflection Store 可留，AgentPrefs 推迟 |
| 3. 自承认 4 risk 是否被低估 | **R1/R3 严重低估**；R2 误诊（hook 已接，缺 flag）；R4 次要 |
| 4. 是否漏关键 task | **漏 Task 11.5（mandatory）**；Task 6 改成 join 契约而非 re-hook |

---

## 关联

- [[feedback-dynamic-workflow-external-review-first]]: 又一次外部评审抓到结构性盲点（plan 自对抗的 4 risk 全部被低估）
- [[feedback-review-standard-grok-pi]]: grok+pi 双评审完全一致，证明流程正确
- [[feedback-no-premature-production-ready]]: 修订 plan 不等于 Phase A 通过；真实数据探测是验收关卡
- [[project-dashboard-redesign-v2-shipped]]: P0-2（PlanTracker 接入）与 v2 的"Work Task 实体未定义"是同类盲点
