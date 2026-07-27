# Dashboard v3 Addendum — Review Brief

**Date:** 2026-07-27
**Scope:** v2 final 之上的两个新增维度——Orchestration Map 视图 + Reflection 协作层
**v2 final:** `docs/decisions/2026-07-27-dashboard-redesign-v2-final.md`（已通过 grok+pi 评审）
**v3 addendum:** `docs/decisions/2026-07-27-dashboard-v3-orchestration-map-and-reflection.md`（~510 行）
**3 路并行调研:** Agent A (Explore 数据) + Agent B (Visual 可视化) + Agent C (Reflection 设计)
**Verification:** 设计文档级（[inspected]），未实施代码

---

## What v3 adds on top of v2

### 增量 1: Orchestration Map 视图

**问题**: v2 的 Live → Latest Task 是**线性决策路径**叙事（intent → decision → execution → outcome），但复杂 query 的实际工作流是**非线性 DAG**（orchestrator 拆分 → 并行 sub-agent → 综合 → 可能再拆）。

**方案**:
- Map **不是独立一级 tab**，是 Live → Latest Task 的第二种呈现模式（`[Decision Path] [Orchestration Map]` toggle）
- 复杂 query（命中 `multi_intent` / `decompose` mode）→ 自动默认 Map；简单 query → 默认 Path；状态记 URL hash `?view=map`
- 技术栈 **Cytoscape.js + cytoscape-elk**（vanilla TS，ELK Sugiyama layered RIGHT 布局）
- 9 种节点（user_intent / orchestrator / decompose / plan / step / sub_agent / llm / tool / output）+ 4 种边（parent-child / dependency / temporal / error）
- 大图性能：>50 节点时折叠 llm/tool 叶子成"5× llm calls"汇总节点；textureOnViewport；增量布局
- bundle 255KB gzip（独立 chunk，首屏不阻塞）

**节点形状/颜色**（Linear 视觉 DNA）:
- user_intent = 白边 pill + MessageSquare
- orchestrator = Violet-700 rect + Split
- step = Green-600 hexagon + Sparkles（含 skill_id）
- sub_agent = Amber-600 hexagon + Bot
- tool = Pink-600 diamond + Wrench
- output = Emerald-600 pill + Check

### 增量 2: 数据埋点 P0（5 个关键字段）

**实测发现**（Agent A 跑 1573 spans）:

| 字段 | 当前填充率 | 目标 | 补埋位置 |
|------|-----------|------|---------|
| `Span.task_id` | **0%** | 100% | `PlanExecutor` 执行 step 时显式传入 |
| `Span.role_id` | **0%** | 100% | 同上 |
| `Span.parent_span_id` | 5.8% | >80% | `SpanWrappedProvider` 从 contextvars 取 |
| `conv.metadata.orchestration_id` | 不存在 | 100% | `Orchestrator.orchestrate()` 完成后写回 |
| `mirror.metadata.parent_session` | 设计有实际空 | 100% | 修复 `conversation_import.py:611-648` 触发条件 |

→ 没补这 5 个字段，DAG 重建算法跑不起来。**Map 视图的前置依赖**。

### 增量 3: Reflection 协作层（横切注解）

**核心原则**: 人工反思是 instinct learner 的高质量种子，**不重建系统**。

**7 类反思分类法**:

| ID | 对象 | 判断 | 闭环 action |
|----|------|------|------|
| R1 routing_miss | route span | 路由错了 | instinct_patch → `~/.vibe/instincts/pending/` |
| R2 skill_misuse | skill span | skill 用错 | instinct_patch + project-knowledge |
| R3 trigger_vague | skill route | 触发词不准 | suggestion（不自动） |
| R4 cost_blow | task/span | 成本超标 | cost_alert + suggestion |
| R5 agent_choice | subagent span | agent 选错 | agent-prefs.json |
| R6 positive_pattern | task span | 值得复用 | instinct_patch（强化） |
| R7 context_note | 任意节点 | 仅注释 | 无（仅 dashboard 可见） |

**关键设计**: R1/R2/R6 与 v8.2 InsightAnalyzer 共享 `~/.vibe/instincts/pending/` 队列——人工反思和机器 insight **走同一个 accept 流程**。

**UX**:
- 节点 hover → `[+]` 角标 → inline 面板（非 modal）→ 7 类 radio + <500 字 + "Save & propose action" / "Save as note"
- 快捷键 `r` + `1-7` + `Cmd+Enter`
- 🔔 Insights 侧栏 **合并 machine 🤖 + human 👤** 同列显示
- 已注释节点显示角标 `N`（红 = open / 绿 = addressed）

**Storage**: `.vibe/reflections.jsonl`（append-only，cross-lock 复用）

**Schema**:
```python
@dataclass
class Reflection:
    id: str                          # uuid4 hex
    target_type: Literal["route_span", "skill_span", "task", "subagent", "decision_node"]
    target_id: str                   # span_id / task_id / step_id
    task_id: str                     # FK → WorkTask
    kind: Literal["routing_miss", "skill_misuse", "trigger_vague",
                  "cost_blow", "agent_choice", "positive_pattern", "context_note"]
    content: str                     # <500 chars
    severity: Literal["info", "warn", "critical"] = "info"
    created_at: datetime
    status: Literal["open", "addressed", "dismissed"] = "open"
    linked_action: dict | None = None
```

### 增量 4: 写闭环（复用 v2 § 6.2）

- 反思保存 → 触发 linked_action（如生成 instinct_patch JSON）
- Approve 按钮 → 内部 socket（localhost:8421）→ CLI process 执行 → `vibe instinct apply --dry-run`
- 内部 socket **不接受外部连接**，只接受 dashboard 前端

### 增量 5: 修订后的路线图

| Phase | 内容 | 工期 |
|-------|------|------|
| A | 数据埋点（5 字段 + DAG rebuilder + Reflection writer） | 2-3 天 |
| B | Dashboard P0（Live + 决策路径）[v2 § 7] | 3-4 天 |
| C | Dashboard P1（Library + Map + cmd+k） | 4-5 天 |
| D | 反思层 P0（与 C 并行） | 2-3 天 |
| E | 反思闭环 + Insights 合并（依赖 v8.2 P2） | 1-2 周 |

---

## Key questions for grok+pi

按 [[feedback-pi-alone-review-sufficient]] 的纪律，**聚焦 6 个结构性问题**——不是 dump-everything。寻找 v2 时 grok+pi 抓到的"实体未定义 / Persona 漂移"那种根本盲点。

### Q1: Orchestration Map 作为 Live 子模式 vs 独立视图

- 决策对吗？还是应该作为一级 tab？
- 自动判断（`multi_intent` mode → Map）的启发式可靠吗？如果 query 命中 decompose 但 step 只有一个，会被判成复杂但其实是简单 query——UX 后果？
- 如果用户在 Live 看 5 个最近任务，每个都点 Map 模式切换，URL hash 状态如何在 task 之间隔离？

### Q2: Reflection 7 类分类法的边界

- **R3 trigger_vague vs R1 routing_miss**：用户说"这个 trigger 太宽"和"路由错了"的边界在哪？两者都会进 instinct_patch 吗？会不会重复？
- **R7 context_note**：作为"逃生口"会不会被滥用变成垃圾桶？是否应该限制每月 R7 上限，或者强制打 severity？
- **R6 positive_pattern**：用户会主动标"这个值得复用"吗？还是会因为"懒得标"而沉默？
- **跨类型转换**：用户标了 R3 但实际是 R1，要不要允许 type 变更？

### Q3: 反思与 InsightAnalyzer 共享队列的污染风险

- 人工反思质量参差（用户随手写的）和机器 insight（基于统计阈值）混在同一个 pending 队列——会不会让 instinct learner 收到低质量训练数据？
- 是否应该用 `origin: human | machine` 标签隔离，accept 时分别对待？
- 如果用户标了 100 个 R1 routing_miss（基于个例），auto-promote 阈值（基于频次）会不会被这些个例污染？

### Q4: 数据埋点 5 个字段的实施风险

- 老 spans/conversations 数据怎么办？需要 backfill 还是从新数据开始？
- `parent_span_id` 从 contextvars 取，但 contextvars 在异步 / 跨进程时不传播——sub-agent 是新进程吗？
- 7 个 phase 各开 workflow_node span 会增加多少 span 量？（估算：每个 orchestrate +7 spans，如果日均 50 个 orchestrate = +350 spans/day）

### Q5: Map 视图在 Library / Insights 中的延伸

- v3 说 "Library skill cell 角标显示反思数"——但 Library 还没设计 reflection 聚合视图。是否需要？
- 🔔 Insights 侧栏合并 machine + human——但 sidebar 容量有限（屏幕高度），如果同时有 50 个 open 反思和 50 个 open insight，怎么排序 / 分页 / 过滤？
- cmd+k 全文搜反思内容——会不会因敏感内容（路径 / token）泄露到搜索索引？

### Q6: 整体实施顺序的依赖

- Phase A（数据埋点）和 Phase B（Dashboard P0）的窗口期：埋点了但 UI 还没消费。这段时间老数据还是没填充——会不会让 Live 视图（v2 P0）显示不完整？
- Phase D（反思层 P0）和 Phase E（反思闭环）拆开是否合理？如果 D 上线后用户积极反思但 E 没跟上，会积累一堆 status=open 的孤立反思——UX 后果？
- v8.2 P2 InsightAnalyzer ship 时间不确定，Phase E 依赖它——如果 P2 延后 1 个月，Phase D 反思会不会先变成纯注释（R7 化）？

---

## Verdict sought

- **SHIP AS-IS**: v3 设计合理，可以进 Phase A 实施
- **CONDITIONAL**: 列出必修项（如调整分类法、补 schema 字段、改 IA）
- **REJECT**: 设计根本问题（如 Map 不该作为子模式、Reflection 不该与 InsightAnalyzer 共享队列）

**关注重点**:
1. 是否有 v2 grok+pi 抓到过的"实体未定义"级别的盲点（v3 新增的 Reflection / Map 是否也有类似问题）
2. Persona（独立开发者本人）在 v3 新增的两个维度上是否仍然锚定
3. 实施风险（特别是数据埋点的 backfill / 异步 contextvars）
4. Phase A-E 的依赖图是否有死锁

---

## v3 资产

- `docs/decisions/2026-07-27-dashboard-v3-orchestration-map-and-reflection.md` — v3 addendum（~510 行）
- `docs/decisions/2026-07-27-dashboard-redesign-v2-final.md` — v2 final（前置依赖）
- `docs/decisions/2026-07-27-dashboard-redesign-v1.md` — v1（5 路对抗综合）
- `docs/decisions/2026-07-27-dashboard-first-principles.md` — v0 草案
- `~/.claude/projects/-Users-huchen-Projects-vibesop-py/memory/project-dashboard-redesign-v3-addendum.md` — memory 记录
- `~/.claude/projects/-Users-huchen-Projects-vibesop-py/memory/project-dashboard-redesign-v2-shipped.md` — v2 memory
