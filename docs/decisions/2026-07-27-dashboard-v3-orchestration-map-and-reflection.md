# 2026-07-27 — Dashboard v3 Addendum: Orchestration Map + Reflection Layer

> **Status**: Addendum to v2 final（吸收用户洞察 + 3 路并行 sub-agent 调研）
> **Predecessors**:
> - [v2 final](2026-07-27-dashboard-redesign-v2-final.md)
> - [v0 first principles](2026-07-27-dashboard-first-principles.md)
> - [v1 5-way adversarial synthesis](2026-07-27-dashboard-redesign-v1.md)
> **Author**: Claude

---

## 0. TL;DR

用户指出 v2 遗漏了关键一层：**复杂 query 的 orchestration DAG 视图**（拆分 → 并行 sub-agent → 综合 → 可能迭代）+ **网页侧反思协作层**。3 个并行 sub-agent（数据探索 / 可视化研究 / 反思设计）调研后整合：

1. **Orchestration Map 视图**: 不是独立一级 tab，而是 **Live → Latest Task 的第二种呈现模式**（与"决策路径图"并列 toggle）。技术栈 **Cytoscape.js + ELK layered 布局**。
2. **数据埋点 P0**: 实测发现 `task_id` / `role_id` 填充率 0%，`parent_span_id` 仅 5.8%。补 **5 个关键字段**才能落地 Map。
3. **反思协作层**: 横切注解层（与 v2 § 5 Insights 侧栏合并），7 类反思，**与 v8.2 InsightAnalyzer 共享 `instincts/pending/` + `suggestions.jsonl`**——人工反思是 instinct learner 的种子，不重建系统。

修订后的 IA: `Live | Library` + 🔔（insights + reflections 合并收件箱）+ ⚙ + cmd+k。Map 是 Live 的子模式。

---

## 1. 用户洞察 → v3 增量

### 1.1 v2 的盲点

v2 的 Live → Latest Task 视图是**线性决策路径**（intent → decision → execution → outcome）。但当 query 是复杂多意图时（如"分析架构并生成测试"），实际工作流是**非线性 DAG**：

```
User query (complex)
    ↓
Orchestrator 拆分
    ↓
┌───────────┬───────────┬───────────┐
↓           ↓           ↓           
Sub-agent A Sub-agent B Sub-agent C  (并行)
↓           ↓           ↓
Results    Results    Results
└───────────┴───────────┴───────────┘
    ↓
Orchestrator 综合
    ↓
(可能再拆分新任务，迭代多轮)
    ↓
Final output
```

v2 的线性叙事**无法表达并行 / 依赖 / 迭代**。同时用户提到"网页侧可以进行的反思"——这是把 dashboard 从"观察镜"升级为"协作改进工坊"的新维度，v2 完全没考虑。

### 1.2 3 路并行 sub-agent 调研结论

| Agent | 视角 | 核心产出 |
|-------|------|---------|
| **A (Explore)** | 数据结构真相 | 静态 DAG（plan→step dependencies）数据完整；运行时 DAG（step→span→sub-agent）关键关联字段 **0-5.8% 填充率**；`trace_cmd.py:321-394` 已有树渲染可复用 |
| **B (Visual)** | 可视化方案 | **Cytoscape.js + cytoscape-elk** 是 vanilla TS 生态最优解；ELK Sugiyama layered (RIGHT) 布局；255KB gzip 独立 chunk；HTML overlay 节点解决 Linear 视觉 |
| **C (Reflection)** | 反思层设计 | 7 类反思分类法；**与 InsightAnalyzer 共享 pending 队列**；R1/R2/R6 → instincts/pending/，R3/R4 → suggestions.jsonl，R5 → agent-prefs.json |

---

## 2. Orchestration Map 视图设计

### 2.1 定位：Live 的第二种呈现模式

**不是独立一级 tab**（避免 IA 膨胀）。Live → Latest Task 视图加 mode toggle：

```
┌─ Latest Task ──────────────────────────────────────────────────┐
│  [Decision Path] [Orchestration Map]   ← toggle              │
└────────────────────────────────────────────────────────────────┘
```

- **Decision Path**（v2 默认）: 线性叙事，适合简单 query（单一 skill 路径）
- **Orchestration Map**（v3 新增）: DAG 脑图，适合复杂 query（多 sub-task 拆分）

自动判断：query 命中 orchestrator mode（multi_intent / decompose）→ 默认 Map；否则默认 Path。用户可手动 toggle，状态记 URL hash `?view=map`。

### 2.2 节点设计（Agent B 推荐）

| Type | Color | Shape | Icon (Lucide) | 数据来源 |
|------|-------|-------|---------------|---------|
| **user_intent** | white border | pill | MessageSquare | conversation 第一个 user turn |
| **orchestrator** | Violet-700 (#6d28d9) | rect | Split | orchestrate phase spans |
| **decompose** | Violet-500 | rect | ListTree | `task_decomposer.py` 输出 |
| **plan** | Blue-600 (#2563eb) | rect | Map | `ExecutionPlan` |
| **step** | Green-600 (#16a34a) | hexagon | Sparkles | `ExecutionStep` with `skill_id` |
| **sub_agent** | Amber-600 (#d97706) | hexagon | Bot | sub-agent mirror conv |
| **llm** | Gray-500 (#6e7681) | rect | Cpu | `span_kind=llm` |
| **tool** | Pink-600 (#db2777) | diamond | Wrench | `span_kind=tool_call` |
| **output** | Emerald-600 (#10b981) | pill | Check | final result |

### 2.3 边设计

| Type | Style | 含义 |
|------|-------|------|
| **parent-child** | 实线 Violet 1.5px ▶ | DAG 结构（plan→step, step→span） |
| **dependency** | 虚线 Gray 1px ▶ | step.dependencies（前置关系） |
| **temporal** | 细蓝线 0.5px ▶ | 按 started_at 排序（toggle 默认关） |
| **error** | 红虚线 ✕ | status=error 或 fallback 触发 |

### 2.4 布局算法

**ELK layered (Sugiyama 变体), 方向 RIGHT (左→右)**:

- 用户输入在左，最终输出在右，中间是 orchestration 拓扑
- `elk.layered.spacing.nodeNodeBetweenLayers: 60`，避免边交叉
- `elk.layered.crossingMinimization.strategy: LAYER_SWEEP`
- 比 dagre 更稳定（dagre 在长链/宽树时易抖动）

**多轮迭代呈现**: 主图按 `trace_id` 分组，每个 trace 一个独立 ELK 子图，**纵向堆叠** + 灰色分隔条标注 timestamp + duration。

### 2.5 大图性能（100+ 节点）

| 策略 | 触发 | 实现 |
|------|------|------|
| 折叠 llm/tool 叶子 | >50 节点 | 同 parent 下的多个 llm/tool 合并成 "5× llm calls" 节点 |
| `textureOnViewport` | 始终 | 平移/缩放用纹理缓存，60fps |
| 增量布局 | 节点 add 时 | `cy.batch()` + 增量 layout |
| 延迟加载 detail | 点击时 | `fetch('/api/spans/{id}')` |

实测 Cytoscape.js 在 300 节点 / 600 边时仍 60fps。

### 2.6 视觉草图

```
┌──────────────────────────────────────────────────────────────────────┐
│ Latest Task · Claude Code · debug-task · 4m 12s · $0.23              │
│ [Decision Path] [Orchestration Map ●]   ← toggle active             │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ╭──────────╮                                                       │
│   │ 👤 "fix  │                                                       │
│   │ the bug" │──────╮                                                │
│   ╰──────────╯       │                                                │
│                      ▼                                                │
│              ╭──────────────╮                                         │
│              │ 🪓 Orchestr. │                                         │
│              │  multi_intent│                                         │
│              ╰──────┬───────╯                                         │
│                     │                                                 │
│       ┌─────────────┼─────────────┐                                  │
│       ▼             ▼             ▼                                  │
│   ╭────────╮   ╭────────╮   ╭────────╮                              │
│   │✨step1 │   │✨step2 │   │✨step3 │   (并行)                       │
│   │omx-tdd │   │code-rev│   │explore │                               │
│   │0.87 ✓  │   │0.52 ⚠ │   │0.91 ✓  │                               │
│   ╰────┬───╯   ╰────┬───╯   ╰────┬───╯                              │
│        │            │            │                                   │
│        ▼            ▼            ▼                                   │
│   ╭────────╮   ╭────────╮   ╭────────╮                              │
│   │🤖 Claude│   │🤖 Claude│   │🤖Explore│   (sub-agent)              │
│   │ main    │   │ main    │   │ sub-agt │                            │
│   ╰────┬───╯   ╰────────╯   ╰────┬───╯                              │
│        │       (skipped)          │                                   │
│        ▼                          ▼                                   │
│   ╭─────────╮                ╭─────────╮                              │
│   │🔧Edit   │                │🔧Grep   │                              │
│   │auth.py  │                │"login"  │                              │
│   ╰────┬────╯                ╰─────────╯                              │
│        │                                                              │
│        ▼                                                              │
│   ╭─────────────╮                                                    │
│   │✅ Output    │                                                    │
│   │ "Fixed..."  │                                                    │
│   ╰─────────────╯                                                    │
│                                                                      │
│   ── Reflections (3 open) ──────                                     │
│   👤 "step 2 should have been skipped" — huchen, 2m ago             │
│   🤖 InsightAnalyzer: code-review trigger overlap — 1h ago          │
│                                                                      │
│   [+] Add reflection on any node                                     │
└──────────────────────────────────────────────────────────────────────┘
```

**关键交互**:
- 点击节点 → 右侧 detail panel 展开看 prompt/response/cost/tokens
- `[+]` 按钮挂在每个节点 hover 时右上角（Lucide `MessageSquarePlus`）
- 已注释节点显示角标 `N`（红色 = 有 open 反思 / 绿色 = 全部 addressed）
- 缩放 / 平移 / box-select
- `cmd+k` 全局搜索 → 高亮匹配节点 + 居中

---

## 3. 数据埋点 P0（5 个关键字段补全）

### 3.1 实测数据缺口（Agent A 发现 + Phase A plan Explore 修正）

> **Implementation correction (2026-07-27 Phase A plan 探索阶段)**: 初版方案假设 `PlanExecutor` 是 runtime，实际它是 prompt/manifest 生成器（`build_guide` / `build_manifest` 写 `context.md`），真正执行 step 的是外部 agent CLI（Claude Code 等）。所以 task_id / role_id 不能"在 PlanExecutor 传"，要改路径。
>
> 同时确认 `ExecutionStep` 已有 `step_id` / `assigned_role` / `agent_squad_id` / `dependencies` / `parallel_group` 全部字段（`src/vibesop/core/models.py:321-397`），DAG 重建**不需要新加字段**，只需要在执行时把值传到 Span。

| 字段 | 当前填充率 | 目标 | 补埋位置（修正后） |
|------|-----------|------|---------|
| `Span.task_id` | **0%** | 100% | `Orchestrator.orchestrate()` 进入 plan_execution phase 时，在 trace context 注入 `task_id=step.step_id`（ExecutionStep 已有字段）；下游 SpanWrappedProvider 从 contextvars 读 |
| `Span.role_id` | **0%** | 100% | 同上（`role_id=step.assigned_role`） |
| `Span.parent_span_id` | 5.8% | >80% | **关键入口包 `with tracer.trace(...)`**: 当前只有 `agent_runtime.py:409` + `cli/main.py:724` 共 2 处开 trace context；需在 `Orchestrator.orchestrate()` / `PlanExecutor.build_guide()` / `agent_runtime.arun()` 包裹。SpanWrappedProvider 已正确从 contextvars 取（`tracer.py:225`），上游不开 context 是根因 |
| `conversations/cli-*.json.metadata.orchestration_id` | 不存在 | 100% | `Orchestrator.orchestrate()` 在 `on_plan_ready` 回调时写回 conversation metadata |
| `mirror-*.json.metadata.parent_session` | 设计有实际空 | 100% | `conversation_import.import_subagent` (`conversation_import.py:611-668`) 只被 `conversation_cmd.py:249` CLI 调用；要把 `discover_subagents` + `import_subagent` 接到 `vibesop-mirror-session-end.sh` 对应的 Python hook 路径 |

### 3.2 orchestration phase spans（新增）

在 `Orchestrator.orchestrate()` 的 7 个 phase 各开一个 workflow_node span：

```python
# src/vibesop/core/routing/orchestrator.py 修订
with tracer.span(f"orchestrate:{phase_name}", kind="workflow_node") as phase_span:
    phase_span.set_metadata({"phase": phase_name, "query": query})
    # ... existing phase logic
```

7 个 phase: `routing / detection / decomposition / plan_building / execution / completion / re_orchestration`

### 3.3 DAG 重建算法（Agent A 草案）

```python
def rebuild_dag(trace_id: str) -> DAG:
    # 1. Load execution_plans.jsonl → plan dictionary by plan_id
    plans = load_plans_for_trace(trace_id)
    
    # 2. Load spans.jsonl → group by trace_id, build tree by parent_span_id
    spans = load_spans_for_trace(trace_id)
    span_tree = build_tree(spans, key="parent_span_id")  # 复用 trace_cmd.py:321-394
    
    # 3. JOIN plan ↔ span via task_id (P0 埋点完成后)
    for plan in plans:
        for step in plan.steps:
            step.spans = [s for s in spans if s.task_id == step.step_id]
    
    # 4. Load conversations → attach sub-agent mirrors via parent_session
    convs = load_conversations()
    for conv in convs:
        if conv.metadata.is_subagent:
            parent = find_conv(convs, conv.metadata.parent_session)
            parent.sub_agents.append(conv)
    
    # 5. Output DAG
    return DAG(
        nodes=build_nodes(plans, spans, convs),
        edges=build_edges(plan_dependencies, span_parents, sub_agent_links),
    )
```

### 3.4 新 API

```
GET /api/orchestration/dag?trace_id=<id>
  → { nodes: [...], edges: [...], phases: [...], iterations: N }

GET /api/orchestration/plans?days=7
  → 列出最近 plans（Library 视图用）
```

---

## 4. 反思协作层设计

### 4.1 核心原则（Agent C）

> **反思是 instinct learner 的人工种子，不是又一孤岛。**

人工反思（Reflection）和机器发现（InsightAnalyzer）**共享同一个 `instincts/pending/` 队列和 `suggestions.jsonl`**。用户在 dashboard 标记的反思和 analyzer 自动产出的 insight **走同一个 accept 流程**——一个用户、一个改进队列。

### 4.2 反思分类法（7 类）

| ID | 对象 | 判断 | 例句 | 闭环 action |
|----|------|------|------|------------|
| **R1 routing_miss** | route span | 路由错了 | "不该走 omx-tdd，应该 code-review" | instinct_patch → pending |
| **R2 skill_misuse** | skill span | skill 用错 | "omx-tdd 在此场景过度工程化" | instinct_patch + project-knowledge |
| **R3 trigger_vague** | skill route | 触发词不准 | "confidence 0.52 还匹配，触发词太宽" | suggestion（不自动） |
| **R4 cost_blow** | task/span | 成本超标 | "$0.23 比同类 +27%" | cost_alert + suggestion |
| **R5 agent_choice** | subagent span | agent 选错 | "Explore 多余，本可一步 grep" | agent-prefs.json |
| **R6 positive_pattern** | task span | 值得复用 | "决策路径很顺，存成 instinct" | instinct_patch（强化） |
| **R7 context_note** | 任意节点 | 仅注释 | "这个 query 来自 spike 分支" | 无（仅 dashboard 可见） |

### 4.3 数据 Schema

```python
# src/vibesop/observability/reflection.py
@dataclass
class Reflection:
    id: str                          # uuid4 hex
    target_type: Literal["route_span", "skill_span", "task", "subagent", "decision_node"]
    target_id: str                   # span_id / task_id / step_id
    task_id: str                     # 外键 → WorkTask
    kind: Literal[
        "routing_miss", "skill_misuse", "trigger_vague",
        "cost_blow", "agent_choice", "positive_pattern", "context_note",
    ]
    content: str                     # <500 字
    severity: Literal["info", "warn", "critical"] = "info"
    created_at: datetime
    status: Literal["open", "addressed", "dismissed"] = "open"
    linked_action: dict | None = None
    # {
    #   "type": "instinct_patch" | "suggestion" | "cost_alert" | "agent_pref" | "none",
    #   "target_path": "~/.vibe/instincts/pending/abc123.json",
    #   "applied_at": datetime | None,
    # }
```

**存储**: `.vibe/reflections.jsonl`（append-only，复用 cross-lock）

### 4.4 UX 流程

参考 **Linear inline comments** > GitHub PR review > Notion callouts。

```
节点 hover 时右上角:
                          ╭─────────╮
                          │➕ [1]   │  ← Lucide MessageSquarePlus + 角标
                          ╰─────────╯
                              
点击 [+] → inline 面板（不弹 modal）:
╭────────────────────────────────────────────────┐
│ ✍ Reflect on this decision                     │
│                                                │
│  Type:                                         │
│   ( ) R1 Wrong route    ( ) R2 Skill misuse   │
│   (•) R3 Trigger vague  ( ) R4 Cost blow      │
│   ( ) R5 Agent choice   ( ) R6 Save pattern   │
│   ( ) R7 Just a note                           │
│                                                │
│  Note: [________________________________]     │
│        [____________________________/500]      │
│                                                │
│  [Save & propose action]  [Save as note]  Cancel│
╰────────────────────────────────────────────────╯
                ↓ Save & propose
╭────────────────────────────────────────────────┐
│ ✓ Reflection saved                             │
│ → Proposed: tighten omx-tdd triggers           │
│   Status: open in Insights bell (🔔)           │
│   [Approve now (dry-run)]   [Review later]     │
╰────────────────────────────────────────────────╯
```

**快捷键**: 选中节点按 `r` 开反思面板；`1-7` 选类型；`Cmd+Enter` 保存。

### 4.5 跨视图可见性

| 视图 | 反思呈现 | 数据流 |
|------|---------|--------|
| **Live (Decision Path)** | 节点角标 `[+] N` / `[!] open` | join reflections × tasks by task_id |
| **Live (Orchestration Map)** | DAG 节点上的徽章（Cytoscape overlay） | 同上 |
| **Library 矩阵** | skill cell 角标 "3 reflect" | aggregate by target_id contains skill_id |
| **Library Instinct Timeline** | reflection 作为 instinct 的来源 | instinct patch 落地后回链 reflection.id |
| **🔔 Insights 侧栏** | **机器 🤖 + 人工 👤 合并显示** | merge suggestions.jsonl + reflections.jsonl (status=open) |
| **cmd+k** | 全文搜反思内容 | index reflections.jsonl.content |

### 4.6 与 v8.2 InsightAnalyzer 的边界

| 维度 | InsightAnalyzer (机器) | Reflection (人工) | 边界 |
|------|----------------------|------------------|------|
| 触发源 | launchd cron / loop tick | 用户 dashboard 点击 | 时间维度正交 |
| 输出格式 | `Insight` dataclass | `Reflection` dataclass | 不同 schema |
| **最终落点** | `instincts/pending/` + `suggestions.jsonl` | **完全相同** | **共享队列** |
| 判断能力 | 统计阈值 | 语义判断 | 互补：机器抓分布、人抓个例 |
| 闭环 | `vibe instinct accept <id>` | 同上 | **共用 accept 流程** |

### 4.7 激励机制（克制）

独立开发者审美拒绝游戏化。三层轻量激励:

1. **即时反馈**: 反思保存后立刻显示"→ Proposed: tighten omx-tdd triggers"
2. **闭环计数**: Insights 侧栏顶部 "X open / Y addressed this month"——仅统计，不奖励
3. **月度回看**: `vibe reflection monthly` CLI 输出 markdown "本月你提了 12 条反思，5 条已变成 instinct，hit_rate +8%"

明确不做: badge / streak / 等级 / 排行榜。

---

## 5. 修订后的信息架构（v3 FINAL）

```
┌──────────────────────────────────────────────────────────────────────┐
│ ●VibeSOP  Live  Library          🔔5   ⌘K   ◐ theme   ⚙ proj▾      │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  └─ Insights + Reflections 合并收件箱
                                     机器 🤖 + 人工 👤 同列显示

#live              #library
   ├─ ?view=path      ├─ skills-agents
   └─ ?view=map       ├─ instincts
                      └─ loops
```

**关键修订**:
- Live 加 `?view=map` query param 切换 Map / Path
- 🔔 铃铛现在合并显示 machine insight + human reflection（前缀 🤖 / 👤 区分）
- cmd+k 全文搜索包含 reflections

**保持 v2**:
- 两个一级视图（Live | Library）—— pi 的洞察：3 个里有 1 个假的（Account）
- Account 仍是齿轮下拉（不是一级 tab）
- Insights 仍是横切注解层

---

## 6. 修订后的 MVP 路线图

### Phase A — 后端数据埋点（v8.2 P1.5 增量，2-3 天）

**前置**: v2 § 4 的 `tasks.jsonl` + `aggregates.json`

**新增**:
- [ ] A1: `Span.task_id` / `Span.role_id` 在 `PlanExecutor` 显式传入
- [ ] A2: `SpanWrappedProvider` 修复 `parent_span_id` 从 contextvars 继承（提升到 >80%）
- [ ] A3: `Orchestrator.orchestrate()` 7 phase 各开 `workflow_node` span
- [ ] A4: `conversations/cli-*.json.metadata.orchestration_id` 写回
- [ ] A5: `conversation_import.py:611-648` sub-agent metadata 写入触发条件修复
- [ ] A6: `reflections.jsonl` writer（cross-lock 复用）
- [ ] A7: `agent-prefs.json` writer
- [ ] A8: DAG 重建算法（`src/vibesop/observability/dag_rebuilder.py`）

### Phase B — Dashboard P0（Live + 决策路径 + 视觉骨架，3-4 天）

[v2 § 7 P0 不变]

### Phase C — Dashboard P1（Library + Map + cmd+k，4-5 天）

**新增（v3 增量）**:
- [ ] C1: Vite + vanilla TS 工程化
- [ ] C2: `cytoscape@^3.30` + `cytoscape-elk@^2.3` + `cytoscape-popper@^2.0` + `tippy.js@^6` + `elkjs@^0.9` 依赖
- [ ] C3: 新 API `/api/orchestration/dag?trace_id=<id>`
- [ ] C4: Live 视图 `[Decision Path] [Orchestration Map]` toggle
- [ ] C5: DAG 渲染（节点/边/布局）+ HTML overlay 节点（Linear 风格）
- [ ] C6: 节点点击 → detail panel
- [ ] C7: 大图性能（折叠 + textureOnViewport）
- [ ] C8: cmd+k 命令面板

### Phase D — 反思协作层（与 Library 并行，2-3 天）

- [ ] D1: `Reflection` dataclass + writer
- [ ] D2: API `POST /api/reflections` + `GET /api/reflections?task_id=` + `PATCH /api/reflections/{id}`
- [ ] D3: Live 节点上的反思徽章 + inline 反思面板
- [ ] D4: 7 类型 radio + 快捷键 `r` + `1-7`
- [ ] D5: R7 (context_note) 先打通（仅 jsonl，无 linked_action）

### Phase E — 反思闭环（依赖 v8.2 P2，1-2 周）

- [ ] E1: R1/R2/R6 instinct_patch 生成器（与 v8.2 Path B 同格式）
- [ ] E2: R3/R4 suggestion writer
- [ ] E3: R5 agent_pref writer
- [ ] E4: 🔔 Insights 侧栏合并 machine + human（🤖 / 👤 前缀）
- [ ] E5: Approve 按钮 → 内部 socket → `vibe instinct apply --dry-run`（复用 v2 § 6.2）
- [ ] E6: `vibe reflection monthly` CLI
- [ ] E7: `vibe reflection export --redact` 脱敏导出

---

## 7. 完整 Live → Map 视图 ASCII 草图（含反思）

```
┌──────────────────────────────────────────────────────────────────────┐
│ ●VibeSOP  Live● Library           🔔5   ⌘K   ◐ light   ⚙ proj▾      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│ ← Yesterday 14:23 · Claude Code · debug-task · 4m 12s · $0.23 →    │
│                                                                      │
│ ┌─ Latest Task ────────────────────────────────────────────────┐   │
│ │                                                              │   │
│ │  [Decision Path] [Orchestration Map ●]                      │   │
│ │                                                              │   │
│ │  ┌─ Filters ──────────────────────────────────────────┐    │   │
│ │  │ ☑ All node types  ☐ Errors only  ☐ Cost > $0.10   │    │   │
│ │  └────────────────────────────────────────────────────┘    │   │
│ │                                                              │   │
│ │              ╭──────────╮                                    │   │
│ │              │ 👤 "fix  │                                    │   │
│ │              │ the bug" │                                    │   │
│ │              ╰─────┬────╯                                    │   │
│ │                    ▼                                         │   │
│ │            ╭──────────────╮                                  │   │
│ │            │ 🪓 Orchestr. │                                  │   │
│ │            │ multi_intent │                                  │   │
│ │            ╰──────┬───────╯                                  │   │
│ │                   │                                          │   │
│ │      ┌────────────┼────────────┐                             │   │
│ │      ▼            ▼            ▼                             │   │
│ │  ╭────────╮  ╭────────╮   ╭────────╮                         │   │
│ │  │✨step1 │  │✨step2 │   │✨step3 │                         │   │
│ │  │omx-tdd │  │code-rev│   │explore │  ← step2 有角标        │   │
│ │  │0.87 ✓  │  │0.52 ⚠ │   │0.91 ✓  │                         │   │
│ │  │        │  │  [!1]  │   │  [+]   │     [!1] = 1 open       │   │
│ │  ╰────┬───╯  ╰────┬───╯   ╰────┬───╯     [+]  = 可加         │   │
│ │       │           │            │                              │   │
│ │       ▼           ▼            ▼                              │   │
│ │  ╭────────╮  ╭────────╮   ╭────────╮                         │   │
│ │  │🤖Claude│  │🤖Claude│   │🤖Explore│                         │   │
│ │  │ main   │  │ main   │   │ sub-agt │                         │   │
│ │  ╰────┬───╯  ╰────────╯   ╰────┬───╯                          │   │
│ │       │      (skipped)         │                               │   │
│ │       ▼                        ▼                               │   │
│ │  ╭─────────╮              ╭─────────╮                          │   │
│ │  │🔧Edit   │              │🔧Grep   │                          │   │
│ │  │auth.py  │              │"login"  │                          │   │
│ │  ╰────┬────╯              ╰─────────╯                          │   │
│ │       │                                                         │   │
│ │       ▼                                                         │   │
│ │  ╭─────────────╮                                               │   │
│ │  │✅ Output    │                                               │   │
│ │  │ "Fixed..."  │                                               │   │
│ │  ╰─────────────╯                                               │   │
│ │                                                                │   │
│ │  ── Reflections (2 open) ───────────────────────────────       │   │
│ │  👤 "step2 trigger vague" — huchen, 2m ago                     │   │
│ │     → Proposed: tighten code-review triggers                   │   │
│ │     [Approve dry-run]  [Review later]                          │   │
│ │                                                                │   │
│ │  🤖 InsightAnalyzer: code-review overlap with review-related   │   │
│ │     — 1h ago, evidence: 12 low-confidence hits last week       │   │
│ │     [Approve dry-run]  [Review later]                          │   │
│ │                                                                │   │
│ │  [+] Add reflection on any node (or press 'r' when focused)   │   │
│ └────────────────────────────────────────────────────────────────┘   │
│                                                                      │
│ ── Earlier Today ────────────────────────────────────────────       │
│ 11:08 · Kimi · write-tests · 2m 30s · $0.11                          │
│ 09:45 · Claude · refactor · 8m 50s · $0.67                           │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 8. 修订后的实施清单

### Phase A（后端数据层）

- [ ] A1-A8（见 § 6 Phase A）

### Phase B（Dashboard P0，[v2 § 7 不变]）

- [ ] 见 v2 § 7 P0

### Phase C（Dashboard P1 + Map + cmd+k）

**Library 矩阵**（[v2 § 7 不变]）:
- [ ] Library 视图: Skills × Agents 矩阵
- [ ] 30s 轮询 + ETag

**Map 视图新增（v3）**:
- [ ] C1: Vite + vanilla TS 工程化（多文件开发）
- [ ] C2: cytoscape + cytoscape-elk + popper + tippy + elkjs + lucide 依赖
- [ ] C3: `/api/orchestration/dag?trace_id=<id>` API
- [ ] C4: Live 视图 view toggle
- [ ] C5: DAG 渲染（节点/边/ELK 布局）
- [ ] C6: 节点点击 detail panel
- [ ] C7: 大图性能（折叠 + textureOnViewport）
- [ ] C8: cmd+k 命令面板

### Phase D（反思层 P0，与 C 并行）

- [ ] D1: Reflection dataclass + writer
- [ ] D2: reflections API（POST/GET/PATCH）
- [ ] D3: Live 节点反思徽章 + inline 面板
- [ ] D4: 7 类型 radio + 快捷键
- [ ] D5: R7 context_note 打通

### Phase E（反思闭环 + Insights 合并，依赖 v8.2 P2）

- [ ] E1-E7（见 § 6 Phase E）

---

## 9. 关键设计决策回顾

| 决策 | 理由 |
|------|------|
| Map 不作为一级 tab，是 Live 子模式 | 避免 IA 膨胀；Map 数据来自 WorkTask（同 Live Latest Task） |
| 反思与 InsightAnalyzer 共享 pending 队列 | 不重建系统；一个用户一个改进队列 |
| 7 类反思，6 类触发 action，1 类纯注释 | 让用户自由记录而不强迫"有用"（R7 逃生口） |
| ELK Sugiyama RIGHT 布局 | 适合 query→output 横向流；工业级稳定 |
| Cytoscape.js 而非 React Flow | vanilla TS 约束；不绑框架 |
| 反思默认本地存（不发送） | Persona 是独立开发者；隐私优先 |
| Approve 走内部 socket + dry-run | 安全边界 + UX 闭环 |
| Map 模式自动判断（multi_intent → map） | 减少用户手动 toggle 负担 |

---

## 10. 设计哲学的延伸（v3）

> **v0**: 显微镜 + 教练
> **v1**: 显微镜 + 镜子
> **v2**: 显微镜 + 镜子（围绕 Work Task）
> **v3**: **显微镜 + 镜子 + 协作改进工坊**

第三个支柱（**协作改进工坊**）的内涵：
- 不只是"看"工作和成本
- 不只是"看见"决策路径
- 而是**直接在数据上反思 → 触发改进 → 下次自动变好**
- 人工反思是 instinct learner 的高质量种子

这把 dashboard 从"被动观察工具"升级为"主动协作伙伴"——同时不越界（不直接写文件，所有动作走 CLI + dry-run + accept 流程）。

**实体先于界面，契约先于分期**（grok）—— v3 把 Reflection 也作为一等公民实体（与 WorkTask 并列），不是 dashboard 的 UI 装饰。

---

*v3 addendum complete. 在 v2 之上新增 Orchestration Map + Reflection Layer 两个核心维度，吸纳 3 路并行 sub-agent 调研。*
