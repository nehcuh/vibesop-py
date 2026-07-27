# Dashboard v3 Phase A Plan — Review Brief

**Date:** 2026-07-27
**Scope:** Phase A 实施计划评审（数据埋点 + DAG rebuilder + Reflection Store）
**Plan:** `docs/plans/2026-07-27-dashboard-v3-phase-a-data-instrumentation.md`（13 task，每个 5 步 TDD + commit）
**Design doc:** `docs/decisions/2026-07-27-dashboard-v3-orchestration-map-and-reflection.md` § 3
**Verification target:** 现有 4434 tests 全绿 + ~50 新 tests + ruff/basedpyright clean

---

## Context

v3 设计文档已落地，本 plan 是 Phase A（数据地基）的实施计划。Plan 顶部已记录 v3 § 3.1 的关键修正：**`PlanExecutor` 不是 runtime，是 prompt 生成器**——所以 task_id 注入路径完全改写。Plan 已经吸收了 Explore agent 的发现。

13 个原子 task（每个 5 步 TDD + 独立 commit）：

| # | Task | 关键文件 |
|---|------|---------|
| 1 | `bind_task_context` contextvars helper | tracer.py |
| 2 | Orchestrator 整体包 trace context | orchestrator.py |
| 3 | 7 phase 各开 workflow_node span | orchestrator.py |
| 4 | task_id/role_id 注入 plan_building phase | orchestrator.py |
| 5 | orchestration_id 写回 conversation metadata | orchestrator.py |
| 6 | `import_subagent` 接入 mirror_session_end hook | hooks/ |
| 7 | Reflection dataclass + JSON round-trip | reflection.py（new） |
| 8 | ReflectionStore append + cross-lock | reflection.py |
| 9 | ReflectionStore list_by_task / update_status | reflection.py |
| 10 | AgentPrefsStore（R5 agent-prefs.json writer） | agent_prefs.py（new） |
| 11 | DAG rebuilder: load plans + build span tree | dag_rebuilder.py（new） |
| 12 | DAG rebuilder: JOIN plan↔span + sub-agent attach | dag_rebuilder.py |
| 13 | E2E integration test（验证关卡） | test_dag_rebuilder_e2e.py |

## Plan 自承认的 4 个 risk + fallback

| # | Risk | Plan 提的 fallback |
|---|------|-------------------|
| R1 | Task 4: `PlanBuilder.build_plan()` 可能不在 orchestrator 层遍历 steps | Bind `task_id=plan_id`（不是 step_id）整个 plan_building phase；step-level tagging 推到 Phase B 在 `agent_runtime.arun()` 做 |
| R2 | Task 6: mirror_session_end.sh 可能是纯 shell 无 Python 入口 | 加 `vibe conversation mirror-session-end` CLI 子命令，shell hook 调它 |
| R3 | Task 11: `execution_plans.jsonl` 可能不存在（Orchestrator 只 in-memory + `_record_plan_sequence`） | 加 Task 11.5：写 ExecutionPlanStore |
| R4 | Task 13: E2E 可能发现 `discover_subagents` 需要 trace_id 过滤 | 加 optional `trace_id` 参数到 `discover_subagents`，default None 保持向后兼容 |

---

## Key questions for grok+pi

按 [[feedback-pi-alone-review-sufficient]] 的纪律，**聚焦 6 个结构性问题**——寻找"plan 实施时会爆炸的隐藏假设"，不是 nitpick。

### Q1: Task 4 fallback 的语义降级——`task_id=plan_id` 是否会让 Map 视图错位？

Plan 的 R1 fallback：如果 step-level binding 不可达，bind `task_id=plan_id`。

**问题**:
- v3 § 2 设计的 Map 视图节点层次是 `orchestrator → step (hexagon) → sub_agent (hexagon)`——step 节点是核心
- 如果所有 span 的 task_id 都归到 plan_id，那 DAG rebuilder（Task 12）的"JOIN plan↔span via task_id"会把所有 span 挂到 plan 节点下，**step 节点会变成空壳**（没有 span 子节点）
- 这是不是变相让 Phase A 的 task_id 填充率指标（0%→100%）"达标但无效"？
- 真正的修复是不是应该在 Task 4 强制要求 step-level binding（即使要重构 PlanBuilder）？

### Q2: Task 6 的 idempotency——重复触发会重复写入吗？

Plan 说"接到 mirror_session_end hook"，但没说幂等性。

**问题**:
- mirror_session_end 每次 session 结束都跑——如果用户开 5 次会话，每次都触发 import_subagent，会不会把同一个 sub-agent 写 5 次？
- `import_subagent` 当前用 `ConversationContext.save()` 或 `_append_dedup_turns(ctx, parsed)`——后者名字暗示有去重，但**判定 key 是什么**？conversation_id？tool_use_id？turn content hash？
- 如果重复写入，Phase B 的 dashboard 会显示同一个 sub-agent 多次，UX 灾难
- Plan 是否需要加 Task 6.5：测试"同一 sub-agent 被多次 import_subagent 后 reflections.jsonl / mirror 文件不重复"？

### Q3: Task 11 假设 `execution_plans.jsonl` 存在——这是不是 v3 设计的另一个根本盲点？

Plan R3 承认"可能不存在"。

**问题**:
- v3 § 3.3 DAG 算法第 1 步是 `load_plans_for_trace(trace_id)`——前提是 plans 已持久化
- Agent A 的 Explore 报告只确认 `spans.jsonl` + conversations/mirror 存在，**没确认 ExecutionPlan 持久化**
- Orchestrator.orchestrate() L322 `_record_plan_sequence` 实际写什么？是完整 ExecutionPlan JSON，还是只是 plan_id 引用？
- 如果只是引用，DAG rebuilder 拿不到 step.dependencies / step.parallel_group，**Map 视图的依赖边根本画不出来**
- 这是不是说明 v3 设计漏了一层"ExecutionPlan 持久化契约"（类似 v2 grok+pi 抓到的"Work Task 实体未定义"）？

### Q4: Task 13 E2E 的 LLM 成本——mock 还是真的跑？

Plan 测试用 `orchestrator.orchestrate("complex query")` 触发完整流程。

**问题**:
- Orchestrator 内部依赖 `ClassifierAgent.classify()` / `MultiIntentDetector` / `TaskDecomposer`，这些都是 LLM 调用
- E2E 如果用真 LLM，每次 CI 跑都花钱（estimate: $0.05-0.20 per run）+ 慢（10-30s）
- 如果 mock LLM，那"task_id 注入"是否真的被测试到了？mock 可能直接返回固定 plan，绕过了 task_id 注入路径
- 现有测试是怎么做的？（看 `tests/agent/runtime/test_plan_executor.py` 或 `test_orchestrator.py` 是否有 mock 模式可借鉴）
- Plan 应该明确：E2E 用 mock-LLM-with-recorded-responses（fixture）还是 stub-classifier（不调 LLM）

### Q5: Reflection Store 是否应该在 Phase A？还是推迟到 Phase D？

Plan 把 ReflectionStore 放在 Phase A（Task 7-9）。v3 § 6 路线图原本是 Phase D 才做反思层 P0。

**问题**:
- Phase A 的 scope 是"数据埋点 + DAG rebuilder"——ReflectionStore 逻辑上不属于这个 scope
- 把 ReflectionStore 提前到 Phase A 的理由是什么？是为了 Phase B 的 dashboard 能展示反思角标？但 Phase B 的 v2 § 7 P0 也没要求反思展示
- 提前的代价：Phase A 工期 2-3 天 → 3-4 天；如果 Phase B/C 设计变了，ReflectionStore schema 可能要重做
- 是不是应该把 Task 7-9 + Task 10 推到 Phase D（与 Library 并行），Phase A 聚焦 5 字段埋点 + DAG？

### Q6: `bind_task_context` 的 contextvars 在异步 / 多进程边界的行为

Plan Task 1 用 `contextvars.ContextVar` 实现。

**问题**:
- v3 § 3 期望 task_id 在"Orchestrator 内 LLM 调用 + sub-agent 执行"都填充
- sub-agent 执行是不是在新进程？（agent_runtime 启动 Claude Code CLI？）如果是新进程，contextvars **不传播**
- SpanWrappedProvider 在子进程里跑时，task_id 怎么传过去？
- 现有 `tests/core/observability/test_async_isolation.py` 测的是 asyncio.Task 隔离（同进程），没测跨进程
- Plan Task 1.1 测试只覆盖"同进程 with 块内传播"——但实际生产场景跨进程，**测试通过 ≠ 生产有效**
- 是不是需要明确：contextvars 只解决 in-process；cross-process 通过 mirror hook 在 import 时 backfill（Task 6 的实际作用）？

---

## Verdict sought

- **SHIP AS-IS**: Plan 合理，可以进 Task 1 实施
- **CONDITIONAL**: 列出必修项（如：Task 4 强制 step-level、Task 6 加幂等测试、Task 11.5 补 ExecutionPlanStore、Reflection 推迟到 Phase D）
- **REJECT**: Plan 有根本执行风险（如：ExecutionPlan 没持久化让 DAG rebuilder 根本跑不起来；task_id fallback 让 Phase A 指标"达标但无效"）

**关注重点**:
1. 是否有"测试通过但生产无效"的隐藏假设（Q1 / Q4 / Q6 都是这种类型）
2. Phase A 的 scope 是否合理（Q5）
3. Plan 自承认的 4 个 risk 是否被低估（特别是 R3 ExecutionPlan 持久化）
4. 是否漏了关键 task（如 Task 11.5 / Task 6.5）

---

## Plan 资产

- `docs/plans/2026-07-27-dashboard-v3-phase-a-data-instrumentation.md` — Phase A plan（13 task）
- `docs/decisions/2026-07-27-dashboard-v3-orchestration-map-and-reflection.md` — v3 设计文档（§ 3 数据埋点）
- `docs/decisions/2026-07-27-dashboard-redesign-v2-final.md` — v2 final（前置）
- `~/.claude/projects/-Users-huchen-Projects-vibesop-py/memory/project-dashboard-redesign-v3-addendum.md` — v3 memory
- `~/.claude/projects/-Users-huchen-Projects-vibesop-py/memory/feedback-review-standard-grok-pi.md` — 评审标准
