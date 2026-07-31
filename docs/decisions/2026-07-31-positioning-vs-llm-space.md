# 2026-07-31 — 产品定位 sharpening：对照 LLM Space 后的优化方向

> **Status**: Strategy decision（定位/红线有效；**执行排序已由对抗终裁 supersede**）  
> **Execution order**: 见 [2026-07-31-product-evolution-adversarial.md](2026-07-31-product-evolution-adversarial.md)  
> **Trigger**: 对照 [deer-flow/llm-space](https://github.com/deer-flow/llm-space) 的 dashboard / loop / trace 产品化  
> **Predecessors**:
> - [PHILOSOPHY.md](../PHILOSOPHY.md) — SkillOS + L0–L3 分层
> - [2026-07-27-dashboard-first-principles.md](2026-07-27-dashboard-first-principles.md) — Dashboard = 显微镜 + 教练
> - [2026-07-27-dashboard-v3-orchestration-map-and-reflection.md](2026-07-27-dashboard-v3-orchestration-map-and-reflection.md)
> - [2026-07-22-observability-loop-closure.md](2026-07-22-observability-loop-closure.md)
> - [2026-07-29-task-memory-product-design.md](2026-07-29-task-memory-product-design.md)
> - [task-memory-loop-article.md](../task-memory-loop-article.md)

---

## 0. TL;DR

1. **LLM Space 没有「做完」我们的 dashboard / loop**——它把 **Agent harness 的 Build–Trace–Debug–Eval** 做成了桌面产品；我们做的是 **Skill 路由 OS 的发现→记忆→自治→反馈闭环**。
2. **定位 sharpening（一句话）**：  
   > **VibeSOP 不是 Agent 工作台，而是 AI 协作的技能操作系统：让你找到对的技能、记住有效的工作方式，并在人离开后继续跑该跑的循环。**
3. **核心叙事（保留并强化）**：  
   > *Mastra / LLM Space 让你看清楚 agent 在做什么；VibeSOP 让 agent 记住你做过什么，并让「该持续发生的事」在回路外发生。*
4. **可吸收的是 UX 与 artifact 纪律，不是产品身份**。  
5. **后续三条主轴（按杠杆排序）**：  
   **闭环优先 → 可回放的 Task Artifact → 自治 Loop 产品化**；Dashboard UI 是闭环的「人机接口」，不是独立赛道。

---

## 1. 对照结论：相邻，不重叠

### 1.1 对象与主路径

| 维度 | LLM Space | VibeSOP |
|------|-----------|---------|
| **用户** | Agent / prompt 建造者 | 用多 agent 干活的开发者 + 想统一 skill 生态的人 |
| **核心对象** | Thread（prompt / tools / model / run） | Skill · Route · Orchestration · Task · Loop · Instinct |
| **主路径** | 打开桌面 App → 写 Thread → Run → Trace → Eval | 意图输入 → `vibe route` / hook → 注入 skill → Agent 执行 → 观察/记忆/循环 |
| **「Dashboard」** | 产品本身 = harness 工作台 | 旁路 OS 控制面：健康、编排、反思、成本、loop |
| **「Loop」** | Agent step loop（model↔tool）；kaizen = 产品迭代 skill | `vibe loop` 定时自治；`LOOP_UNTIL_DRY` 语义收敛；FeedbackLoop / task-memory 闭环 |
| **成功标准** | 跑通并调试一个 agent 想法 | 找对技能 + 沉淀可复用模式 + 95% 枯燥活无人值守 |
| **执行边界** | 自带 Pi runtime，可执行 tool / 导出 LangGraph | L0–L2 在 OS；L3 文件/代码由外部 Agent |

### 1.2 一句话差异（对外可用）

| 产品类 | 代表 | 价值主张 |
|--------|------|----------|
| Agent 工作台 / harness IDE | LLM Space、部分 LangSmith Studio | **造 agent、看 step、调 prompt** |
| LLM Observability SaaS | Langfuse、Helicone、Mastra Trace | **看清一次 run 发生了什么** |
| **Skill Operating System** | **VibeSOP** | **选对技能、跨平台复用、记住有效路径、定时自治、反馈进技能池** |

### 1.3 我们绝不被带偏的红线

对照后明确 **non-goals**（即使 LLM Space 做得很漂亮）：

| ❌ 不做 | 原因 |
|--------|------|
| 桌面 Prompt / Thread 编辑器 | 与 SkillOS 主路径冲突；DeerFlow 系主场 |
| 替代 Claude Code / Cursor 当编码 IDE | L3 边界写进 PHILOSOPHY，不可侵蚀 |
| 以「模型 call 时间线」为唯一北极星 | 我们的北极星是 **路由准确 + 技能沉淀 + 自治覆盖率** |
| 复制他们的「Thread = 一切」数据模型 | 我们的一等公民是 **Task（意图聚类）+ Skill + LoopSpec** |

---

## 2. 产品定位 sharpening

### 2.1 已有定位（保留）

来自 PHILOSOPHY / GOALS / USE_CASES：

```
VibeSOP = SkillOS + Loop Engine
生命周期: 发现 → 安装 → 路由 → 编排 → [L1/L2 | L3 Agent] → 评估 → 保留/淘汰
         + L0 定时自治
```

### 2.2 对照后强化的「三层价值」

把对外叙事压成三层，避免功能清单散装：

```
┌─────────────────────────────────────────────────────────────┐
│  L-Remember   记住有效工作方式（task cluster / instinct / skill draft） │
│  L-Operate    无人值守循环（vibe loop + guard + 报告）                 │
│  L-Observe    看懂协作系统（dashboard L1→L2→L3：数据→洞察→行动）        │
└─────────────────────────────────────────────────────────────┘
         ▲ 全部建立在同一地基上
┌─────────────────────────────────────────────────────────────┐
│  Foundation: 路由 · 编排 · 跨平台适配 · 技能生命周期 · 本地 .vibe/   │
└─────────────────────────────────────────────────────────────┘
```

| 层 | 用户一句话 | 已有资产 | 缺口（对照后更清晰） |
|----|------------|----------|----------------------|
| **Foundation** | 「别让我记 50 个 skill 命令」 | 10 层路由、多平台、install/lifecycle | 冷启动体验、路由可解释性 UI |
| **L-Observe** | 「系统健康吗？这次编排怎么走的？」 | spans、analytics、DAG API、Reflection API | Phase C UI；run 回放感；token/cost 一等展示 |
| **L-Remember** | 「别让 agent 失忆」 | task-memory 设计 + 部分 MVP | 闭环到人审 skill 草稿的默认路径 |
| **L-Operate** | 「下班后 CI 有人看」 | `vibe loop` + launchd + Guard 模型 | metric trigger 真接线；dashboard 接 loop；模板化场景 |

### 2.3 与 Dashboard 第一性原理对齐

[first principles](2026-07-27-dashboard-first-principles.md) 已正确：

> Dashboard 是从原始事件提取意义、驱动决策的界面（L1→L2→L3）。

对照 LLM Space 后的补充：

- LLM Space 的产品级 Trace/Eval 证明：**「可回放的 run artifact」是信任基础设施**。  
- 我们的 L3（Insight → Action）不能停在「建议文案」——必须接 **Reflection / instinct / skill draft / loop create** 等可执行出口。  
- 因此 Dashboard 的北极星不是「更好看的表格」，而是 **闭环转化率**：  
  `看到问题 → 写 reflection 或接受建议 → 技能/instinct/loop 状态变化`。

### 2.4 与 Observability Loop Closure 对齐

[v8.2](2026-07-22-observability-loop-closure.md) 的用户原话仍然是正确北极星：

> 后台记录 agent 内部调用 → 定期检测路由准确性与 skill 可优化性 → 反馈改进。

LLM Space 停在「记录 + 人工评估」；我们要停在 **「记录 + 分析 + 写回」**。  
**写回**才是差异化，不是更漂亮的 trace 面板。

---

## 3. 可从 LLM Space 学习与吸收的（模式，非外壳）

按「吸收难度 × 与定位一致性」排序。

### 3.1 必吸收（高杠杆 · 与 SkillOS 一致）

| # | 模式 | LLM Space 做法 | VibeSOP 落点 | 成功标准 |
|---|------|----------------|--------------|----------|
| A1 | **Run / Task 为一等可回放 artifact** | Thread + Run History 可 replay、可对比 | 一次 `orchestration_id` / `task_id` = 可打开的「工作包」：route decision + DAG + spans + conversations + cost | Dashboard 能从 Library 一键打开完整任务回放 |
| A2 | **Step 级成本可见** | per-step token/cost chip | spans 已有 `cost_usd`；Dashboard Live/Map 节点与 summary 必须显示 | 任一任务详情页无需 CLI 即可看到总成本 + top 昂贵 step |
| A3 | **评估 rubric 心智 → 反思结构化** | 2–6 criteria、1–5 分、A/B delta | 已有 7 类 Reflection；补「轻量 rubric」可选字段（不强制打分） | Reflection 能驱动 instinct/suggestion 队列（已有设计，需 UI 接线） |
| A4 | **本地文件 = 真相** | `~/.llm-space` 文件树即产品 | `.vibe/` 已是真相；强化「可检查、可分享、可 git」叙事与导出 | `vibe export task <id>` 或等价一键打包 |

### 3.2 宜吸收（UX 纪律）

| # | 模式 | 落点 |
|---|------|------|
| B1 | **Decision Path vs Orchestration Map toggle** | 与 v3 设计一致；复杂 query 默认 Map——**坚持实现，不另起炉灶** |
| B2 | **时间线 + 树状混合** | 线性对话叙事 + DAG 结构并存（LLM Space 的 run-trace 是时间线，我们要 DAG 优先 + 时间线辅） |
| B3 | **空状态与首跑引导** | 冷启动：无 analytics 时引导开 analytics + 跑 3 次 route 的 checklist |
| B4 | **不可变历史快照** | evaluation snapshot 不因 rubric 编辑而改写历史——我们的 reflection / plan dump 同样要「历史不可变」 |

### 3.3 明确不吸收

| 模式 | 原因 |
|------|------|
| Thread 编辑器 + system prompt 版本管理 | 技能作者工具链，非 OS 职责 |
| 桌面 Electron/Electrobun 壳 | 我们是 CLI-first + 可选 Web；panel 已拆 [vibesop-py-panel](https://github.com/nehcuh/vibesop-py-panel) |
| 把任意 Thread 生成 LangGraph | 执行引擎赛道 |
| 仅靠手动 tool continuation 调试 | 我们的执行在外部 Agent，不复制 harness |

### 3.4 可选借鉴（中期）

| 模式 | 条件 |
|------|------|
| **A/B run 对比** | 同一 normalize(query) 两次路由/两次 skill 的 outcome 对比——服务路由改进，不是 prompt 调参 |
| **Variable / template 注入 available_skills** | 已有 skill injector；可做成「上下文预览」调试工具，非主路径 |
| **Kaizen-loop 纪律** | 产品迭代 skill 的证据门 / north-star / capability map——可用于 VibeSOP **自身**开发，不必做成用户产品 |

---

## 4. 后续优化方向（分阶段）

原则：**先接闭环，再补体验；先本地单用户杠杆，再生态。**  
每阶段有 **kill criteria**（测效用，不测功能清单长度）。

### Phase 0 — 定位与沟通（1 周内，低成本）

| 动作 | 产出 |
|------|------|
| 固定对外一句话 + 三层价值（§2.2） | README / PHILOSOPHY 补丁（可选 PR） |
| 明确竞品地图：LLM Space 在「观察/建造」侧，我们在「记忆/自治」侧 | 本文 + project-knowledge 摘要 |
| 统一术语表 | Task ≠ Thread；Loop ≠ agent-loop；Trace 分 routing-trace vs agent-span |

**Kill**：若团队仍把「做更好看的 dashboard」当唯一下一目标，说明叙事未落地。

---

### Phase 1 — 闭环优先（P0，2–3 周）

**目标**：让「观察 → 洞察 → 写回」在本地可跑通一条黄金路径。

| 工作包 | 内容 | 与既有文档关系 |
|--------|------|----------------|
| **1.1 Loop 真接线** | `METRIC` trigger 评价 + `SpanAggregator` 至少 1 个消费者（route auditor） | observability-loop-closure GAP-2/3 |
| **1.2 Analyzer → 写回** | 低置信路由 / 低使用 skill / reflection 聚合 → `instincts/pending` 或 `suggestions.jsonl` | GAP-4；dashboard v3 Reflection |
| **1.3 黄金 CLI** | `vibe loop create route-auditor ... && vibe loop tick` 产出可读报告 | v8.2 acceptance |

**Kill criteria**（至少满足 2/3）：

1. 连续 7 天日常使用后，**至少 1 条** suggestion/instinct 候选被用户接受或明确 dismiss  
2. route-auditor 能指出 **真实存在的** 路由问题（非空报告噪音）  
3. 无新 SaaS 依赖；数据仍全在 `.vibe/`

**不在 Phase 1**：重写前端视觉系统、Cytoscape 大动画、桌面壳。

---

### Phase 2 — 可回放 Task Artifact（P0/P1，2–4 周）

**目标**：吸收 LLM Space 的「run 是一等公民」，但用我们的对象模型。

| 工作包 | 内容 |
|--------|------|
| **2.1 Task 聚合视图** | `task_id` / `orchestration_id` 下 JOIN：analytics + plan + spans + conversations + reflections |
| **2.2 Dashboard Phase C（薄）** | Live：Decision Path / Orchestration Map toggle；任务详情页显示 cost + 状态；Reflection 写回 API 已有，补最小 UI |
| **2.3 Export** | `vibe task show <id>` / 导出 markdown 或 zip，便于分享复盘 |

**Kill criteria**：

1. 复杂编排任务打开 Map 后，用户能在 **30 秒内**指出失败 step / 昂贵 step  
2. 从 Map 或任务页 **一键** 创建 reflection，且出现在 inbox  
3. 数据填充率：`trace_id` / `task_id` 在真实 orchestrate 路径 ≥ 设计阈值（延续 v3 Phase A 验收）

**吸收自 LLM Space**：A1、A2、B1、B2。  
**不吸收**：Thread 编辑器。

---

### Phase 3 — L-Operate 产品化（P1，并行可开）

**目标**：`vibe loop` 从「能跑」变成「敢长期开」。

| 工作包 | 内容 |
|--------|------|
| **3.1 场景模板** | `ci-watcher` / `daily-pr-digest` / `route-auditor` / `deps-scan` 一键 create |
| **3.2 Dashboard Loop 页** | 状态机可视化（ACTIVE/FAILING/DEAD）、最近 run、失败原因 |
| **3.3 Guard UX** | max_failures、DEAD 后如何 `reset`、审批门文案；通知（Issue/Slack）可后置 |
| **3.4 与 Phase 1 合流** | 默认推荐「每周 route-auditor」进 onboarding |

**Kill criteria**：

1. 至少一个真实项目 **连续 14 天** 无人工干预的 loop 在跑  
2. DEAD 状态可被用户理解并恢复，无静默丢任务  
3. Loop 产出至少 1 次被用户用于真实决策（修 CI / 改 skill / 清技能）

---

### Phase 4 — L-Remember 加深（P1，与 Phase 2 咬合）

**目标**：task-memory v3 MVP 的效用验收，而不是功能扩张。

| 工作包 | 内容 |
|--------|------|
| **4.1** 完成 W0–W3 中未完成部分（以当前代码状态为准） | 见 task-memory-product-design |
| **4.2** Replay 可执行 hint（非只展示） | W3 设计 |
| **4.3** 人审 skill draft 路径默认可用 | 拒绝 auto-write |

**Kill criteria**：见 task-memory 文档——**测 recall/precision 与是否真省时间**，不测 cluster 数量。

---

### Phase 5 — 体验与生态（P2，有余力）

| 方向 | 说明 |
|------|------|
| Dashboard 视觉 / IA 完整 v2 | Live \| Library + 🔔 + cmd+k |
| A/B skill outcome 对比 | 服务路由改进 |
| 社区 skill share 与 dashboard 洞察联动 | 中期愿景 |
| panel 仓库与 core dashboard 的边界再确认 | 避免双前端分叉 |

---

## 5. 优先级矩阵（执行时用）

| 优先级 | 项 | 理由 |
|--------|----|------|
| **P0** | Phase 1 闭环接线 | 唯一不可替代的差异化；LLM Space 不会替我们做 |
| **P0** | Phase 2 Task 回放（含薄 Phase C） | 信任与调试；吸收竞品 UX 最有价值部分 |
| **P1** | Phase 3 Loop 产品化 | 哲学「延续 > 启动」的落地证明 |
| **P1** | Phase 4 Task memory 效用 | 叙事第二句「让 agent 记住」 |
| **P2** | 重 UI / 生态市场 | 在闭环证明之后再砸 |

```
        高差异化
            │
   闭环写回 ●──────── ● Task 回放
            │           │
   vibe loop●           ● Reflection UI
            │
   ─────────┼──────────────── 高体验
            │
            │           ● 桌面 Prompt IDE  ← 不做
            │
        低差异化
```

---

## 6. 风险与反模式

| 风险 | 表现 | 缓解 |
|------|------|------|
| **Dashboard 虚荣指标** | hit_rate 卡片好看但无人行动 | 以闭环转化率为验收 |
| **Trace 军备竞赛** | 为对齐 LLM Space 堆 step 细节 | 只服务「路由/编排/技能改进」所需粒度 |
| **Loop 僵尸** | 装了 launchd 但从不看输出 | Phase 3 模板 + DEAD 可见 + 报告入口 |
| **定位漂移** | 开始做 Agent builder | 红线 §1.3；PHILOSOPHY L3 边界 |
| **双前端** | core dashboard vs panel 分叉 | 单一数据契约（API）；UI 二选一为「推荐壳」 |

---

## 7. 建议的下一动作（具体、可开 session）

按「最小可证伪」顺序：

1. **Session A（1–2 天）**：盘点 Phase 1 缺口清单——`METRIC` / `SpanAggregator` 调用点 / InsightAnalyzer 现状 vs v8.2 文档，输出 issue 级 checklist。  
2. **Session B（并行）**：Dashboard Phase C **垂直切片**：单任务 Map + cost strip + reflection 按钮（用已有 API，不做完整 IA）。  
3. **Session C**：`route-auditor` loop 模板 + 一次真实 24h 跑通。  
4. **可选文档 PR**：README 定位段引用 §2.2 三层价值 + 与 LLM Space 类产品的边界一句。

---

## 8. 结语

LLM Space 的价值，是提醒我们：**可观测必须产品级，否则 OS 不可信**。  
它没有替我们完成的工作，才是护城河：

> **选对技能 · 记住有效路径 · 人离开后仍运转 · 洞察写回技能系统。**

后续所有优化，应用同一过滤器：

```
这是在加强「记忆 / 自治 / 闭环」？
  → 做。
还是在做「更好的 agent 工作台」？
  → 不做，或只借 UX 模式。
```

---

## 附录：术语对照（避免同名陷阱）

| 词 | LLM Space | VibeSOP |
|----|-----------|---------|
| Loop | Agent harness 内 model↔tool 迭代 | 定时自治任务；或语义 `LOOP_UNTIL_DRY` |
| Trace | 一次 run 的 model/tool 时间线 | routing decision tree **或** agent spans（需标明 source） |
| Thread | 可编辑实验文件 | （无对应；最近似 conversation + task） |
| Evaluation | 人工 rubric 评 run | Reflection + FeedbackLoop + skill 分级 |
| Skill | Thread 内可注入能力列表 | 全生命周期管理对象 + 路由目标 |
| Dashboard | 整个桌面产品 | OS 控制面 / 显微镜+教练 |
