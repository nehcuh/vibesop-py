# 2026-07-31 — 产品进化方向（对抗验证终裁）

> **Status**: **Binding** — 取代 [2026-07-31-positioning-vs-llm-space.md](2026-07-31-positioning-vs-llm-space.md) 中的 **Phase 1→4 执行排序**；定位红线与 non-goals **仍然有效**。  
> **Pi review**: CONDITIONAL → GO（[`_review-sprint1-evolution-merged.md`](_review-sprint1-evolution-merged.md)）；Sprint 1 接线已开工（2026-07-31）。  
> **Method**: 4 路并行对抗（魔鬼代言 / 主用户 persona / 工程事实 / 竞品护城河）→ 主会话综合裁决。  
> **Persona**: 独立开发者本人（dashboard v2 已锚定；非团队 lead、非布道场景）。

---

## 0. 一页终裁

### 0.1 定位（不变，收紧表述）

**VibeSOP = 跨 Agent 的本地技能操作系统**：找对技能 → 记住有效路径 → 纠错写回 → 在人离开后跑**该跑且敢开**的自治任务。

**不是**：Agent harness 工作台（LLM Space）、云端 Trace SaaS（Langfuse）、技能内容包（superpowers/gstack）。

**护城河一句话**（竞品视角）：

> 换 Agent 不换记忆与技能晋升账本；纠错会写回本地路由——不是又一个 trace 面板。

### 0.2 北极星指标（替换虚荣指标）

| 采用 | 废弃作为主 KPI |
|------|----------------|
| **纠错后 7 日：同类意图命中/采纳率提升** | hit_rate 卡片 alone |
| **用户真实 accept / dismiss ≥1 次/周**（非作者自嗨） | suggestion 条数 |
| **replay 采用率**（提示出现后用户选 Y） | cluster 个数、embedding separation |
| **Task 可回放率**（真实任务 30s 内定位失败/贵 step） | span fill-rate alone |
| **外部价值 loop ≥1 跑满 14 天且影响过一次真实决策** | loop 创建数量 |

**一句话 aha（主用户）**：

> 「它指出了我的路由蠢，我点了一次，第二天就好了；第三次直接回放上次。」

做不到这句 → **禁止**对外宣称「闭环 / 记忆 OS 已发货」。

### 0.3 对 07-31 草案的关键修正

| 原草案 | 对抗结论 | 终裁 |
|--------|----------|------|
| P0 = 闭环写回（route-auditor 元审计优先） | 魔鬼：元产品自慰；用户：要的是「纠错生效」不是审计报告 | **保留写回，改对象**：默认写回是 **preference/instinct 经人审**，不是先做元 OS 自检大盘 |
| Phase4 memory 后置 | 工程：memory ~85% 已落地；用户：replay 要在热路径 | **Memory 前移为运营化**，不是绿野重建 |
| Phase2 Task Artifact 在闭环后 | 魔鬼+v2：Work Task 契约是信任前提 | **Task 真相与写回并行**，CLI 先于漂亮 Map |
| Phase3 Loop 全套产品化 | 用户：babysit OS 会关；竞品：loop 是场景护城河非技术 | **先 1–2 外部模板 + 可感知**；metric 接线服务写回，不做 loop 市场 |
| 三层 Observe/Remember/Operate 并行建 | 魔鬼：三个半成品产品线 | **压成一条黄金路径**（§2），其余是支线 |

---

## 1. 四路对抗摘要（证据）

### 1.1 魔鬼代言（Kill / Demote）

- **最大风险**：3 个月建成「只有作者消费的自改进 OS」，日常仍无法 30 秒讲清「刚才那个任务」。
- 闭环作北极星易变成 **精致地服务自己**（route-auditor 优化 OS，而非帮用户干活）。
- 两套 Task 语义未合并（`hash(query)` vs Work Task session 树）就谈回放 = 文档自欺。
- **裁决吸收**：禁止 meta-auditor 当 onboarding 默认；Task 语义必须统一；KPI 换效用。

### 1.2 主用户 persona

- Top 痛：skill 装了等于没装 (9) → 同类活从零演 (8) → 系统不可见=不可信 (7) → CI 无人盯 (6)。
- 会用：可读建议 + 一键 accept；热路径 replay；出事才开 Dashboard。
- 永不打开：6 导航显微镜、跨项目默认 memory、auto-write skill 热路径、Prompt IDE。
- **裁决吸收**：热路径 > Dashboard；Inbox 式控制面；Loop 必须模板化且敢开。

### 1.3 工程事实（完成度倒挂）

```
task-memory (Phase4)     ████████████░░  ~85%  已是产品面，勿当绿野
loop CRON (Phase3)       ████████░░░░░░  ~55%  运维可用；METRIC/guard/可见性缺
task+API (Phase2 data)   █████████░░░░░  ~60%  DAG/reflection API 齐；UI ~10%
METRIC 闭环 (Phase1)     ███░░░░░░░░░░░  ~25%  schema+aggregator 有，调度/写回断
```

- **METRIC**：模型有，`vibe loop tick` 只走 cron — **GAP 仍真**。
- **SpanAggregator**：已有 `vibe trace metrics` 消费；**无** loop/instinct 生产写回。
- **InsightAnalyzer**：仅存在于 docs。
- **task_id / clustering / recall / replay / skill_promote / dag_rebuilder / reflection API**：**已实现**；旧决策文部分过时。
- **Dashboard Phase C**：`index.html` 仍四 tab，无 Map/Reflection UI。
- **最高杠杆接线**：`MetricCondition × SpanAggregator × loop tick`；其次薄 UI 接已有 DAG API。

### 1.4 竞品护城河

- 可守 12 个月的是 **本地可审计写回 + 跨宿主同一 `.vibe/` 账本**，不是 dashboard/loop/memory 功能词。
- 适配器清单 = 桌面筹码；**跨平台同一记忆与路由状态** = 仍可能是护城河。
- **时机风险**：day-1 路由不信任时堆 loop/memory → 固化错误路径 → 卸载。
- 楔子功能：`recall + 纠错写回 + 下次 route 生效` 的 30 秒路径（LLM Space / Langfuse 难同构复制）。

---

## 2. 产品进化主轴：一条黄金路径，不是四条产品线

把演进压成 **一条用户可感知的路径**（Spine），支线全部服务它。

```text
  [日常] vibe route / hook 注入 skill
       │
       ├─(可见) 为什么选 X、跳过 Y     ← Trust
       ├─(可纠) 标错 → pending → 人审 → 下轮更准  ← Write-back  ★护城河
       ├─(可记) 同类 → recall / replay 提示 [Y]     ← Memory 热路径 ★已有代码
       │
       ▼ 事件落入 .vibe/ (task_id + spans + outcome)
       │
       ├─(可回看) vibe task show / 薄 Dashboard 出事页  ← Task Truth
       │
       └─(可自治) 模板 loop：外部价值 OR 只读分析
                 写操作 loop 门控；METRIC 驱动分析  ← Autonomy gated
```

### 2.1 四条 Axis（并行能力，有门控依赖）

| Axis | 名称 | 用户价值 | 代码起点 | 门控 |
|------|------|----------|----------|------|
| **A** | **Trust & Write-back** | 纠错后系统真的变准 | instinct `record_outcome`、pending、promote presets | 无「可读 + accept」则不算完成 |
| **B** | **Hot-path Memory** | 少重复讲同一类任务 | `recall` / `replay` / `skill_promote` **已齐** | gold 依赖 outcome 密度；先修 outcome 再推 cluster 质量 |
| **C** | **Task Truth** | 出事 30s 定位；可讲述 | `task_id`、`rebuild_dag`、reflection API | UI 可薄；**语义统一**优先于 Cytoscape |
| **D** | **Gated Autonomy** | 下班后真有人盯 | `vibe loop` CRON + launchd + instinct presets | 默认模板 **外部价值**；写仓类 loop 只读分析门控 |

**依赖（硬）**：

- D 的「按 skill 周期执行改仓」**禁止**在 A 的纠错写回未证明前默认开启。  
- A 的 analyzer 若无足够 Task/outcome 事件 → **禁止**噪声写 pending（魔鬼+竞品 timing）。  
- C 的漂亮 Map **禁止**在 `rebuild_dag` 真实 trace 无 step 节点时开工美化（工程 kill）。

---

## 3. 90 天进化计划（终裁排序）

### Sprint 0（3–5 天）— 叙事与债务诚实

| 动作 | 完成定义 |
|------|----------|
| 文档对齐代码 | 更新过时 GAP：memory 已发货；METRIC 未接；PROJECT_STATUS 补 observability |
| 统一术语 | **Work Task** = 一次用户意图的执行实例（session/orchestration 树）；**task_id** = 意图软键 `hash(normalize(query))`，用于 recall/cluster；两者 JOIN，禁止混称 |
| 冻结 non-goals | 同 positioning 红线 + 本文件 §6 |

### Sprint 1（约 2 周）— **黄金 aha 路径**（Axis A + B 最小环）

**目标**：主用户安利句可演示。

| # | 交付 | 验收 |
|---|------|------|
| 1.1 | **Pending 人话建议队列**（可先 CLI）：低置信路由 / 用户纠正 / 高频未命中 skill → 落盘 pending | `vibe instinct pending`（或等价）列出 ≤3 条/日、可读中文 |
| 1.2 | **accept / dismiss** 写回生效路径 | accept 后 7 日内同类 query 路由偏好可测变化；dismiss 不静默重现轰炸 |
| 1.3 | **Replay 热路径默认可用** | route 后出现「上次 A→B→C？」；Y 注入；统计采用率 |
| 1.4 | **outcome 密度** | 明确 `record_outcome` 何时写；无 outcome 时 recall 不假装 gold |

**可不做**：InsightAnalyzer 大框架、Cytoscape、METRIC 全量、跨项目。

**Kill**：14 天真实使用 **0 次** accept/dismiss 且 **0 次** replay Y → 停扩 analyzer，先修信号与文案。

### Sprint 2（约 2 周）— **Task 真相 + 薄控制面**（Axis C）

| # | 交付 | 验收 |
|---|------|------|
| 2.1 | `vibe task show <id|latest>`：decision + cost + 失败 step + 子会话链接 | 本人真实失败任务 30s 内指出问题 step |
| 2.2 | Dashboard **薄切片**：打开即 Inbox（pending 数 · loop DEAD · 最近贵/失败任务）；单任务页接已有 `/api/orchestration/dag`（**树/JSON 先于 Cytoscape**） | 无 pending 时 Inbox 诚实为空并引导开 analytics |
| 2.3 | Reflection 最小 UI 或 CLI：对 task 挂一条 reflection | API 已有 → 前端或 CLI 二选一可写回 |

**Kill**：3 条真实 orchestration 无法 `rebuild_dag` 出 step → **先修写入侧**，不做 Map 美化。

### Sprint 3（约 2 周）— **自治可感知 + METRIC 接线**（Axis D）

| # | 交付 | 验收 |
|---|------|------|
| 3.1 | **外部价值模板 1 个优先**：`ci-watcher` 或 `daily-pr-digest`（不是 route-auditor 默认） | 真实项目 14 天；至少 1 次影响决策 |
| 3.2 | **METRIC 接线**：tick 评估 `metric_conditions`；cooldown + min_samples；OR with cron | fixture spans 可点燃；文档与 CHANGELOG 去「假已具备」 |
| 3.3 | **只读分析 loop**（可选第二模板）：`route-health` 输出报告 → pending，**不**自动改路由 | 与 1.1 合流 |
| 3.4 | Loop 可观测：`vibe loop status` / Inbox 卡片 DEAD；guard 最小（max_failures 已有 + 醒目 DEAD） | 装完 launchd 用户能回答「在不在跑」 |

**Kill**：装了仍不知道在跑 / DEAD 静默 → 本 sprint 只做可见性。

### Sprint 4（约 2 周）— **Memory 运营化**（Axis B 加深，非重建）

| # | 交付 | 验收 |
|---|------|------|
| 4.1 | 默认路径文档 + e2e smoke on **真实** `.vibe`：route → spans → recall → replay → scan → human promote | 报告 gold_rate / candidate 数 |
| 4.2 | promote 人审 UX 打磨（CLI 足够）；**禁止** auto 注入 discovery 路径 | 保持 skill_promote 隔离 |
| 4.3 | 仅当 Sprint 1 kill 已过：软 cluster 质量一轮 | 用 task-memory 既有 kill criteria |

**Kill**：14 天 gold_rate 全 0 → 修 outcome，不推 promote UI 动画。

---

## 4. Phase 评级对照表（旧 → 新）

| 旧 Phase | 魔鬼 | 用户 | 工程 | **终裁** |
|----------|------|------|------|----------|
| 1 闭环写回 | Demote | Yes（人话+accept） | ~25% 需接线 | **Keep 改义 → Sprint 1 黄金路径**（对象=纠错写回，非元审计大盘） |
| 2 Task+薄盘 | Keep↑P0 | CLI 重、盘 Inbox | 数据 60% / UI 10% | **Sprint 2**；Cytoscape 延后 |
| 3 Loop 产品化 | Demote | 模板后 Yes | CRON 55% | **Sprint 3 瘦身**；外部模板优先 |
| 4 Task-memory | Merge→2 | Yes 省时间 | **~85% 已发货** | **Sprint 1 热路径 + Sprint 4 运营化**；禁止当绿野 |

---

## 5. 与既有文档的关系

| 文档 | 关系 |
|------|------|
| [PHILOSOPHY.md](../PHILOSOPHY.md) | 信仰与 L0–L3 **不变**；L0 实现上加「门控与外部价值优先」 |
| [positioning-vs-llm-space](2026-07-31-positioning-vs-llm-space.md) | 定位/红线/可吸收 UX **有效**；**执行排序以本文为准** |
| [dashboard-v2-final](2026-07-27-dashboard-redesign-v2-final.md) | Work Task 实体、solo persona、写操作 dry-run **有效**；IA 全量降为 Sprint 2 之后 |
| [dashboard-v3 Map+Reflection](2026-07-27-dashboard-v3-orchestration-map-and-reflection.md) | 数据层已部分 ship；**UI 在 Sprint 2 薄切片之后**再上 Cytoscape |
| [observability-loop-closure](2026-07-22-observability-loop-closure.md) | METRIC GAP **仍真**；「0 Aggregator caller」**过时**（有 `trace metrics`）；InsightAnalyzer 仍可不建大框架 |
| [task-memory-product-design](2026-07-29-task-memory-product-design.md) | 原则与 kill criteria **有效**；状态改为 **largely shipped，运营化优先** |

---

## 6. 明确不做（90 天冻结）

1. 桌面 Prompt / Thread IDE、LangGraph 导出作产品主轴  
2. Dashboard 视觉军备 / 完整六导航作主线  
3. Cytoscape+ELK 在 DAG 真实质量未达标前  
4. 跨项目 memory **默认开**  
5. Auto-write skill 进路由热路径  
6. route-auditor / 元审计 loop 作为 **唯一** onboarding 默认  
7. 适配器数量竞赛式「支持第 N 个 Agent」当 slogan  
8. 新建第二套前端而不先消费内嵌 dashboard 已有 API  

---

## 7. 决策过滤器（以后每个 PR / session）

```
1. 是否让用户更可能说出 aha 句（纠错生效 / 回放省时）？
2. 是否增加「跨宿主本地账本」的写回或可信度？
3. 是否只是更好看的观察表面？
4. 是否在 outcome/Task 数据不足时制造噪声写回？

(1|2)=true 且 (3|4)=false → 做
否则 → 不做或降级为内部工具
```

---

## 8. 建议的立即下一 session

**唯一推荐入口（综合四路最大公约数）**：

> **Sprint 1 开工：黄金 aha 路径**  
> pending 人话建议 + accept/dismiss 生效 + replay 热路径统计 + outcome 密度检查。

并行可选（不挡主路径）：文档诚实化（Sprint 0）— 修正 CHANGELOG / PROJECT_STATUS / 过时 GAP。

**不要**下一 session 就开：完整 Cytoscape、InsightAnalyzer 框架、loop Guard 通知全家桶。

---

## 9. 终裁陈述（可对外 / 对内）

**对内**：我们不是缺零件，是缺 **一条响得起来的用户路径**。Memory 与 Task API 已超前于叙事；METRIC 与写回调度落后于叙事。进化方向 = **接线 + 效用验收**，不是新赛道开荒。

**对外**：VibeSOP 让你在多 Agent 世界里 **少记 skill 名、少重复踩坑、纠错会留下、该盯的活下班后仍盯着**——用本地 `.vibe/` 账本，而不是又一个 trace 网站。

**对抗后保留的锋芒**：闭环写回仍是差异化核心。  
**对抗后丢掉的幻觉**：把「OS 自检」和「显微镜 UI」当成 P0 会杀死产品。

---

## 附录 A — 对抗参与方

| 角色 | 焦点 | 关键一击 |
|------|------|----------|
| Devil | 杀元产品自嗨 | P0 对象错了会建成作者自用 OS |
| Solo user | JTBD | aha = 点一次第二天更准 + 第三次回放 |
| Eng realism | 代码完成度 | Phase4 已在；Phase1 METRIC 断线；最高杠杆 wiring |
| Competitive | 12 月 moat | 写回+跨宿主账本；功能词是公地；day-1 信任门控自治 |

## 附录 B — Work Task vs task_id（必须统一）

| 概念 | 定义 | 用途 |
|------|------|------|
| **Work Task** | 一次用户意图的运行实例：root session、子 agent、plan/steps、状态、成本 | Dashboard Live、失败定位、编排 Map |
| **task_id** | `hash(normalize(query))` 意图软键 | recall、cluster、跨次「同类」 |
| **JOIN** | Work Task 元数据携带 `task_id`；spans 两侧都写 | 回放包 = 实例细节 + 历史同类 |

在未文档化 JOIN 契约前，禁止再开「第三套 task 语义」。
