# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-07-28 S38 [vibesop-py] Dashboard v3 Phase A 收尾 (Tasks 10-13) + Phase B 全 ship

**Session Summary**:
- Task 10 / P0-2：`Orchestrator.orchestrate()` 接 `PlanTracker.create_plan()`，写 `plan.metadata["trace_id"]` — DAG rebuilder plan↔span JOIN 契约
- Task 11/12：`rebuild_dag()` — 多 plan 聚合 + step tree build + sub-agent attach；plan-scoped step ids（`step:{plan_id}:{step_id}`）避免跨 plan 节点重复；iterations 从 `reorchestration_history` 推导（非 `len(plans)`）
- Task 13：fixture-based E2E (4 tests, zero LLM) + orchestrate→rebuild_dag integration smoke (3 tests)；验收关卡从 fill rate 改为 rebuild_dag 真实数据 smoke
- Phase B（HTTP API layer）：4 endpoints（GET /api/orchestration/dag, POST/GET/PATCH /api/reflections）+ 28 tests + Pydantic schemas + `_trace_exists`（JSON parse + exact-field match，非 substring，防 T-1 vs T-1x 误判）
- Phase B Polish（grok+pi closeout）：P0 fix — `ReflectionStore._locked_update_status` list_all() 在 flock 外导致 RMW lost-update race（Phase A 遗留，Phase B 写路径让其 user-visible）

**Key Decisions**:
- 跨进程 RMW 必须把 read 放进锁内：append-only 走锁 + update 走锁 不够 — update 是 RMW，read 在锁外则穿插的 appender 会被 rewrite 静默吃掉（AtomicWriter tmp+rename 让 bug 无 crash 痕迹）
- plan-scoped step ids 防跨 plan 节点重复：多 plan 共享 step_id 在 dict-as-index 模型下会互相覆盖；scope 为 `step:{plan_id}:{step_id}` 后去重自然解决
- substring match 是 trace_id 误判源：用 JSON parse + `record.get("trace_id") == trace_id` 精确匹配，不用 `trace_id in line`
- Pydantic + dataclass 双层校验：API 边界 Pydantic 给干净 422，核心层 dataclass `__post_init__` 是 backstop（防 hand-edited JSON）；Literal 从 core re-import 防 drift

**Next Steps**:
- Phase C（UI 前端 — Orchestration Map Cytoscape.js + Reflection Inbox）可基于 rebuild_dag API + 4 reflection endpoints 直接开干
- Phase B+1（deferred）：AtomicWriter sibling lock file 修 rename+inode race；trace_id 内存 index + mtime cache 优化 `_trace_exists` perf
- 24h 实机观察：跑实际 orchestrate 验证 trace_id 落盘到 execution_plans.jsonl

### 2026-07-27 S37 [vibesop-py] Dashboard v3 Phase A — Tasks 1-9 (data instrumentation)

**Session Summary**:
- Task 1-5 (前序 session)：trace context 包裹 + workflow_node phase spans + per-step task_id binding (P0-1) + orchestration_id/trace_id 写 conversation metadata
- Task 6 / P0-3：mirror hook `--include-subagents`；`import_subagent` 双写 `parent_session`（raw, legacy）+ `parent_conversation_id`（resolved, 新 JOIN key）
- Task 7：`Reflection` dataclass — 7 kinds × 3 statuses × 5 target_types；dataclass + Literal + `__post_init__`（不引 Pydantic）；JSON round-trip 13/13
- Task 8：`ReflectionStore` append + `list_all` — JSONL append-only，cross-process lock（POSIX fcntl inline / Windows cross_process_lock）；4-thread × 25-write 无 interleaving
- Task 9：`list_by_task` / `list_open` / `update_status` — atomic rewrite via AtomicWriter（tmp+rename），同一把 cross-process lock 防 lost-update race；2-thread × 10-update 无 lost mutation

**Key Decisions**:
- PEP 567 contextvars 不跨进程 — sub-agent 跑独立 OS process，跨进程 JOIN 必须落盘
- JSONL store 双锁 pattern：in-process threading.Lock + cross-process fcntl/cross_process_lock；append + update 共用同一把 cross-process lock
- update_status unknown id → KeyError（fail loud）；理由：stale id post-rebuild 是 dashboard bug，silent no-op 会掩盖
<!-- handoff:end -->
