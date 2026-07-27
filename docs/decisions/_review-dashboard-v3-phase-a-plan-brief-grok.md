# Dashboard v3 Phase A Plan — grok Review

**Date:** 2026-07-27  
**Brief:** `docs/decisions/_review-dashboard-v3-phase-a-plan-brief.md`  
**Plan:** `docs/plans/2026-07-27-dashboard-v3-phase-a-data-instrumentation.md`  
**Design:** `docs/decisions/2026-07-27-dashboard-v3-orchestration-map-and-reflection.md` § 3 / § 6  
**Reviewer:** grok  
**Method:** brief § Key questions Q1–Q6 structural review; code + local data verification  
**Focus:** "测试通过但生产无效" 的隐藏假设

---

## Verdict

```text
VERDICT: CONDITIONAL
```

Plan 有可执行骨架（13 原子 task、TDD、R1–R4 自省），但有 **3 个结构性假设** 会让 Phase A 关卡「达标却喂不饱 Map」。**不宜 SHIP AS-IS**。

- **不是 SHIP**：Q1 / Q3 / Q6 会让「全绿」与「Map 有数据」脱钩。
- **不是 REJECT**：问题可在 plan 层修掉，不必推倒 13-task 结构；基础设施（`PlanTracker`、`import_subagent`、trace `task_id` 继承）已大半存在。

**一句话：** Phase A 应交付 **可 JOIN 的持久化契约**（plan↔trace、step 结构、`parent_session`），而不是 **进程内 fill rate 化妆**。当前 plan 在后一项上用力，在前一项上仍缺强制 task。

证据标记：

- `[inspected]` — 读代码 / 设计文档
- `[executed]` — 跑本地数据探测

---

## 总览

| # | 问题 | 结论 | 严重度 |
|---|------|------|--------|
| Q1 | `task_id=plan_id` fallback → Map 错位 | **确认**。会制造「fill rate 达标、step 空壳」 | **Blocker** |
| Q2 | Task 6 幂等 / 重复 import | **半否**。幂等已有；真问题是 join key 与「是否已接入」的误诊 | Medium |
| Q3 | `execution_plans.jsonl` 盲点 | **R3 低估且诊断偏了**：文件已在，缺的是 **plan↔trace 外键** | **Blocker** |
| Q4 | E2E mock vs 真 LLM | **确认风险**。Plan 未规定 → 极易假绿 | High |
| Q5 | Reflection 是否该进 Phase A | **可留 schema/store**；AgentPrefs 宜推迟 | Low–Med |
| Q6 | contextvars 跨进程 | **确认致命**。与 Q1 同一根因 | **Blocker** |

---

## Q1 — `task_id=plan_id`：达标但无效？

**Yes. 这是 vanity metric trap。**

### 事实

1. `Orchestrator` **只建 plan，不执行 step**。`PlanBuilder.build_plan()` 后直接 `OrchestrationResult`；CLI 写得很清楚：实际执行在外部 agent CLI。`[inspected]`
2. Task 4 绑在 **plan_building** 阶段 → 最多给分类/拆解时的 LLM span 打标，**打不到 step 执行 span**。
3. R1 fallback `task_id=plan_id` 与 Task 12 JOIN 契约冲突：

```text
step.spans = [s for s in spans if s.task_id == step.step_id]
```

`plan_id ≠ step_id` → **所有 step 节点 children 为空**，依赖边（来自 plan）还在，但「step → 运行时 span/sub-agent」挂不上。

4. 验收清单只要求「至少一个 span 的 `task_id` 非空」`[inspected]` —— 用 `plan_id` 即可刷绿，Map 仍废。

### 隐藏假设

> 「`task_id` 从 0%→非零 = Phase A 成功。」

真正需要的是：**JOIN 键能把 runtime 节点挂到 step 上**；否则 100% 也是错的 100%。

### 必修

- **禁止** 把 `task_id=plan_id` 当作 step-level 解；若只能 plan-level，必须改 JOIN 语义并 **改验收指标**。
- Task 4 绑定点改到 **执行边界**（`step_runner` / `agent_runtime` 按 step 调度处），不是 plan_building 装饰。
- 验收改为：`rebuild_dag` fixture 中 **step 节点有 children 或明确的 sub_agent 边**，而不是 fill rate。

---

## Q2 — Task 6 幂等？

**重复写入风险被高估；「没接入 hook」被低估成错误前提。**

### 事实

1. `import_subagent` 已有 turn 去重 + 稳定 `derive_subagent_conversation_id` + `test_import_subagent_idempotent_on_rerun`。`[inspected]`
2. `import-claude` 默认 **`--include-subagents=True`**。`[inspected]`
3. `vibesop-mirror-session-end.sh` 已调 `vibe conversation import-claude ...`，未关 subagents。`[inspected]`

因此 Task 6「接到 hook」很可能在 **解决一个已接通的路径**；生产若仍空，更可能是：

| 疑点 | 说明 |
|------|------|
| **Join key 错位** | `parent_session_id=path.stem`（完整 session id），而 conv id 是 `mirror-claude-{session[:20]}`。DAG 用 `parent_session == conversation_id` 会对不上。`[inspected]` |
| **发现路径** | `discover_subagents` 假定 `<jsonl-parent>/<stem>/subagents/`；布局不对则永远 0 条。 |
| **mirror 根目录** | 部署 hook 里 `_MIRROR_ROOT` 可能写死用户路径，会话不一定落在项目 `.vibe`。 |

### 必修

- 把 Task 6 改成 **诊断 + 修 join 契约**，不是再包一层 hook。
- 加契约测试：`parent_session` 必须能 resolve 到 parent conversation（建议直接写 **parent conversation_id**，或双写 session_id + conversation_id）。
- Task 6.5 幂等：**可选**（单元已有）；**join 契约测试不可选**。

---

## Q3 — ExecutionPlan 持久化：另一层盲点？

**R3 方向对、细节错；真实盲点更重。**

### R3 低估 / 误诊

| Plan 假设 | 现实 |
|-----------|------|
| 可能没有 `execution_plans.jsonl` | **已有** `PlanTracker` → `.vibe/execution_plans.jsonl` |
| 可能只有 `_record_plan_sequence` | `_record_plan_sequence` **只写 instinct skill 序列**，不是 plan 持久化 |
| 需要新建 ExecutionPlanStore | **不需要新 store**；缺的是写入契约与 trace 关联 |

本地探测：`[executed]`

- 135 行 plan，**129 含 dependencies**（依赖边数据够）
- **0 条含 `trace_id`**
- `ExecutionPlan` schema **无 `trace_id` 字段**；metadata 样例为空

谁写 plan？`[inspected]`

- CLI `_orchestration_post_process` / guided execution / `step_runner` → `PlanTracker.create_plan`
- **`Orchestrator.orchestrate()` 本身不写 PlanTracker**

### 隐藏假设

> `load_plans_for_trace(trace_id)` 在 Phase A 可实现。

**当前没有任何 plan↔trace 外键 → Task 11 的第 1 步在生产不可用。** 这与 v2 评审抓过的「实体未定义」同类：**JOIN 边未契约化**。

### 必修（原 optional R3 → **mandatory Task 11.5**）

1. 凡 `orchestrate()` 产出 plan，**统一** `PlanTracker.create_plan`（含非 CLI 路径）。
2. 在 active trace 下写入 `plan.metadata["trace_id"]`（或一等字段）。
3. `load_plans_for_trace` 按该键过滤；无键则明确 fallback（例如 `orchestration_id` / 时间窗）并写进测试。
4. 无此 task → Task 11–13 对生产是空转。

---

## Q4 — E2E：mock 还是真 LLM？

**Plan 未规定 = 假绿高概率。**

- Task 4 断言「任意 llm span 有 task_id」—— mock 在 `bind_task_context` 里造一个 span 即可过，**测不到 JOIN**。
- Task 13 写 `orchestrator.orchestrate("complex query")`，未声明 stub 边界；现有 orchestration e2e 也偏「真 router 碰运气」。`[inspected]`
- 真 LLM：CI 慢 / 花钱 / 不稳定；假 LLM：容易绕开埋点路径。

### 必修

拆成两层，写进 plan：

1. **CI 确定性 E2E（Task 13）**  
   手写 `execution_plans.jsonl` + `spans.jsonl` + subagent conv → `rebuild_dag`  
   断言：step 数、dependency 边、phase 节点、sub_agent 挂载  
   **零 LLM**
2. **人工 smoke（13.4）**  
   可选真 `vibe orchestrate`；不进默认 CI

Orchestrator 单测：stub `should_decompose` / decomposer / `build_plan`，**只测 span 形状与 metadata 写回**。

---

## Q5 — Reflection 是否该在 Phase A？

**Store 可以留；AgentPrefs 应推迟。Brief 略偏。**

- v3 §6 Phase A 已列 **A6 `reflections.jsonl` writer、A7 agent-prefs**；Phase D 是 **UI**，不是 store 首发。`[inspected]`
- Task 7–9 与 A6 一致，可保留（薄 schema + append store）。
- **Task 10 AgentPrefs** 更贴近 Phase E（R5 闭环）；Phase A 无消费者，schema 易废。

### 建议（非 blocker）

- 保留 7–9；**10 挪到 Phase E**。
- 工期目标仍写「数据地基」，避免 13 task 里 4 个是反思子系统。

---

## Q6 — contextvars：测试过 ≠ 生产有效

**这是全 plan 最大的隐藏假设，与 Q1 同源。**

### 事实

1. `TraceContext.current_task_id` **已在** `tracer.trace(task_id=...)` 继承路径里；子 span 已会吃 task_id。`[inspected]`  
   Task 1 若另开 `_task_ctx_var` 却只改 `start_span`、不贯通 `span()`，会再埋一条不一致路径。
2. **生产主路径是跨进程**：plan 生成在 VibeSOP；执行在 Claude Code / 其它 agent CLI。contextvars **不过进程**。
3. Sub-agent 是独立进程；VibeSOP 侧只能靠 **mirror + parent_session**，不能靠 bind。
4. 本地 spans：`task_id` **0%**，`parent_span_id` **~5.9%**（与 brief 一致）。`[executed]`  
   即使用 contextvars 修好 **进程内** classifier span，Map 要的 **step 执行拓扑** 仍来自 plan 结构 + conversation mirror，不是 agent 进程内的 llm span。

### 隐藏假设

> 「在 Orchestrator 里 `bind_task_context` → 生产 span 的 task_id 变 100% → Map 可画。」

进程内测试会绿；**外部 agent 会话的执行图仍然空。**

### 生产路径对照

| 路径 | contextvars 有效？ | 正确做法 |
|------|-------------------|----------|
| Orchestrator 内 LLM（classify / decompose） | 是 | plan_building 期 bind 可接受 |
| `agent_runtime` / `step_runner` 进程内 | 是 | **按 step** bind |
| 外部 Claude Code 会话 | 否 | 永不靠 contextvars；靠 plan + mirror |
| Sub-agent 进程 | 否 | 只靠 `parent_session` join |

### 必修：重写 Phase A 数据模型叙事

| 数据 | 来源 | 是否需要 contextvars |
|------|------|----------------------|
| plan / step / dependencies | `execution_plans.jsonl` | 否 |
| orchestrator phase 边界 | Task 2–3 `workflow_node` | 进程内即可 |
| step → VibeSOP 内 LLM | bind at step_runner / runtime | 是（仅 in-process） |
| step → 外部 agent / sub-agent | conversation + `parent_session` | **否**；靠 Task 6 join |
| plan ↔ trace | `metadata.trace_id` | 否（写 plan 时抄 trace） |

Plan 正文必须写死：

> contextvars 只覆盖 in-process；cross-process 只靠 plan 持久化 + mirror metadata；**禁止**把 fill rate 当跨进程成功标准。

Map MVP 应允许：**step 节点可以没有 llm children**，仍用 plan 的 skill/deps + sub_agent 边构成可用 DAG。

---

## 对 4 个自承认 risk 的再评级

| Risk | Plan 态度 | 评审再评级 |
|------|-----------|------------|
| R1 task_id fallback | 可接受降级 | **不可接受**（与 Map JOIN 矛盾）→ 改绑定点 + 改指标 |
| R2 mirror 无 Python 入口 | 加 CLI | **部分假问题**：shell 已调 `import-claude`；真问题是 join key |
| R3 plan 未持久化 | optional 11.5 | **mandatory**；且文件已在，缺 **trace 关联 + 全路径写入** |
| R4 discover 要 trace_id | optional 参数 | 次要；主缺口是 `plan.trace_id` 与 `parent_session` 契约 |

---

## 必修项清单（满足后可 SHIP）

在开 Task 1 前改 plan：

1. **重写 Phase A 成功标准**
   - `rebuild_dag`：steps + dependency 边 + phase 节点 + sub_agent 挂载（fixture）
   - 降级 / 删除「task_id fill rate 0→100%」为主门禁

2. **Mandatory Task 11.5 — Plan↔Trace 契约**
   - 统一 `PlanTracker.create_plan`
   - 写 `trace_id`
   - `load_plans_for_trace` 可测

3. **重写 Task 4**
   - 绑定执行边界；禁止 `plan_id` 冒充 `step_id`
   - 文档化 in-process vs cross-process

4. **重写 Task 6**
   - 验证现有 import 路径；修 `parent_session` ↔ parent conv join
   - 契约测试必做

5. **Task 13 = fixture E2E，零 LLM**
   - 真跑只作 manual smoke

6. **（建议）Task 10 → Phase E**；Task 1 复用 / 扩展 `current_task_id`（+ role），避免双 ContextVar

---

## 可保留、可直接做的部分

- Task 2–3：`orchestrate()` 包 trace + phase `workflow_node` — 正确且本地可验证
- Task 5：`orchestration_id` 写回 conversation — 需要，注意 conversation_id 线程参数
- Task 7–9：Reflection 薄存储 — 与 v3 A6 一致
- Task 11–12 算法骨架 — 在 **11.5 + JOIN 契约** 之后有意义
- 不重复造 ExecutionPlanStore；扩展 `PlanTracker` 即可

---

## 关注重点回执（brief § Verdict sought）

| brief 关注点 | 结论 |
|--------------|------|
| 1. 「测试通过但生产无效」隐藏假设（Q1 / Q4 / Q6） | **均成立**；Q6 最重，Q1 是其指标化表现，Q4 会掩盖二者 |
| 2. Phase A scope 是否合理（Q5） | **大体合理**；Reflection store 可留，AgentPrefs 宜推迟 |
| 3. 自承认 4 risk 是否被低估 | **R1/R3 严重低估**；R2 误诊；R4 次要 |
| 4. 是否漏关键 task | **漏 Task 11.5（mandatory）**；Task 6 应改成 join 契约而非 re-hook；可选 6.5 非关键 |

---

## 建议的 plan 修订顺序（若采纳）

1. 在 plan 顶部加 **「数据边界（in-process vs cross-process）」** 表（见 Q6）。
2. 插入 **Task 11.5**（或提升为 Task 0 前置）Plan↔Trace 契约。
3. 改写 Task 4 / 6 / 13 正文与验收 checklist。
4. Task 10 标为 out-of-scope → Phase E。
5. 再进 Task 1 实施。

---

*Review complete — CONDITIONAL until must-fix items land in the plan text.*
