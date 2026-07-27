# 2026-07-27 — Dashboard 重新设计（第一性原理分析 v0）

> **Status**: Phase 1 — First Principles Analysis（待对抗讨论 + 外部评审）
> **Author**: Claude
> **Predecessor**: 2026-07-17 Panel Redesign v1（已归档）、2026-07-22 Observability Loop Closure v8.2（P1 已 ship）
> **Scope**: 当前 `src/vibesop/dashboard/` 的 FastAPI server + 单页 HTML

---

## 0. TL;DR

当前 dashboard 鸡肋的根因不是 UI 丑，而是**它只完成了「数据展示」(L1)，没有完成「信息组织」(L2) 和「洞察驱动」(L3)**。本草案从第一性原理出发，重新定义 dashboard 的角色：**"AI 协作的显微镜 + 教练"**，并给出新的信息架构（Now / Work / Skills / Agents / Insights / Cost）与设计哲学。本稿作为对抗讨论和 grok+pi 二次评审的靶子。

---

## 1. 现状诊断（基于代码摸清）

### 1.1 当前实现速写

- **后端**（`server.py` 380 行）：5 个数据源 → 8 个 API
  - `.vibe/analytics.jsonl` — 路由历史（每次 vibe route）
  - `.vibe/traces/*.json` — 路由决策树（4 层级联）
  - `.vibe/observability/spans.jsonl` — agent 内部 spans（task / llm / tool_call / file_edit / workflow_node，已支持 schema_version + project_id + cost_usd）
  - `.vibe/conversations/*.json` — 多轮会话 + sub-agent mirror（Path-1 + Path-2 已 ship）
  - `.vibe/session/*.json` — session 状态

- **前端**（`index.html` 639 行）：单文件 SPA，原生 CSS+JS，4 个 tab
  - Overview — 数字 cards + top skills bar + mode distribution badges
  - History — 路由记录表格
  - Traces — routing + agent spans 混合表格
  - Conversations — 会话列表表格 + 详情（含 thinking/tools/results mirror）

### 1.2 用户三个痛点的根因诊断

| 用户痛点 | 表面现象 | 根因 |
|---------|---------|------|
| **缺组织层次和洞察** | 全是平铺表格 | IA 按数据源分（Overview/History/Traces/Conversations），而不是按用户任务分。回答不了"我的系统健康吗？哪条路由错了？哪个 skill 该改进？" |
| **conversation 定位奇怪** | 每次打开只有一条 | `files[:limit]` 默认 20，但 sub-agent mirror 后会话数翻倍且混杂；更深的问题是：conversation 被当成"数据行"而不是"工作叙事" |
| **UI 丑** | GitHub dark + 表格 | 缺视觉层次（typography/spacing/color hierarchy）、缺动效（实时感）、缺焦点（一打开不知道看哪里）、单页无路由（不可深链/分享） |

### 1.3 数据已经捕获但 dashboard 没用上的东西

这些是 v8.2 P1 刚 ship 的"富矿"，dashboard 完全没反映：

1. **真实 LLM 成本**（`spans.jsonl` 的 `cost_usd`，已接 pricing table，2026-07-23 ship）
2. **每 skill 的成功率 / 平均 token / 平均成本**（`vibe trace metrics <skill>` CLI 已有，dashboard 没暴露）
3. **sub-agent 树状结构**（Path-2 mirror 已有 `parent_session` / `agent_type`，dashboard 只显示成扁平列表）
4. **路由决策树**（4 层级联 + 置信度分布，traces/*.json 已有，dashboard 只显示 "matched/no-match"）
5. **instinct 学习曲线**（routing 命中 → instinct boost → 命中率变化）
6. **loop 任务执行历史**（`loop-manager` 已有，dashboard 没接入）
7. **session 间的工作流叙事**（哪个会话启发了哪个 instinct？哪个会话触发了哪个 skill 改进？）

---

## 2. 第一性原理：dashboard 的本质是什么？

### 2.1 错误的定义

> "Dashboard 是把数据展示出来的网页。"

这个定义导致当前的鸡肋。它只回答了"如何展示"，没回答"为什么展示"和"给谁看"。

### 2.2 正确的定义（草案）

> **Dashboard 是让用户从原始事件流中提取意义，从而做出更好决策的界面。**

这包含三个递进层次：

```
L1: Data → Information    把原子事件组织成「在发生什么」
L2: Information → Insight 把「在发生什么」提炼成「什么值得关注」
L3: Insight → Action      把「什么值得关注」转化为「我该做什么」
```

当前 dashboard 停在 L1（数据展示），偶尔触及 L2（hit_rate / p95 / top_skills），完全没有 L3。

### 2.3 三个层次的对照

| 层次 | 当前 dashboard | 应该有的 dashboard |
|------|---------------|-------------------|
| L1 | "过去 50 条路由记录" | "你的 agent 们正在做什么" |
| L2 | "hit rate 76%" | "code-review skill 命中率本周下降 18%，因为新增了 review-related 触发词" |
| L3 | ❌ 无 | "建议：合并 review-related 和 code-review 触发词（点击查看影响范围）" |

---

## 3. VibeSOP 哲学如何映射到 dashboard

VibeSOP 的五大核心信念，每一个都对 dashboard 设计有直接含义：

### 3.1 发现 > 执行 (Discovery over Execution)

**含义**: 找到正确工具比执行更重要。

**对 dashboard 的含义**: dashboard 应该帮用户"发现"他们的工作模式、skill 效果、改进机会。不是"展示执行结果"，而是"揭示看不见的模式"。

❌ 反例：列出 50 条路由记录
✅ 正例：揭示"你 70% 的 debug 任务都用了同一个 skill，但成功率只有 60%——可能需要新的 debug-advanced skill"

### 3.2 匹配 > 猜测 (Matching over Guessing)

**含义**: 理解意图比猜测命令更重要。

**对 dashboard 的含义**: dashboard 应该"理解用户想看什么"，而不是让用户在 4 个 tab 里猜。默认视图应该回答"用户最可能问的问题"。

❌ 反例：4 个平级 tab，让用户自己挑
✅ 正例：默认进入「Now」视图，回答"现在我的系统在做什么、健康吗"

### 3.3 记忆 > 智能 (Memory over Intelligence)

**含义**: 记住什么有效比"更聪明"更重要。

**对 dashboard 的含义**: dashboard 应该是 VibeSOP 的「记忆界面」——让用户看到系统学到了什么 instinct、哪些 skill 在被用、哪些用户偏好被记录。当前完全不可见。

❌ 反例：完全没有 instinct 演化的可视化
✅ 正例：「Instinct 时间线」展示过去 30 天每条 instinct 的命中次数、boost 幅度、为路由贡献的命中率提升

### 3.4 开放 > 封闭 (Open over Closed)

**含义**: 开放生态比封闭系统更有价值。

**对 dashboard 的含义**: dashboard 应该平等展示内置 skill 和外部 skill（gstack / superpowers / omx 等）的表现。当前 top_skills 是按 skill_id 字符串排序，没有 pack 归属、没有外部/内置区分。

❌ 反例：所有 skill 在一个扁平列表里
✅ 正例：按 pack 分组的 skill 健康视图，能看出"superpowers pack 命中率 85%，omx pack 命中率 62%——omx 需要更新"

### 3.5 延续 > 启动 (Continuity over Starting)

**含义**: 设定一次持续运行 > 每次手动触发。

**对 dashboard 的含义**: dashboard 应该突出"持续运行的东西"——loop 任务、instinct 学习、自主监控。当前 dashboard 完全是"过去事件的快照"，没有"持续过程"的视觉表达。

❌ 反例：完全没有 loop 任务的实时状态
✅ 正例：「Loops」视图展示所有正在运行的自主任务（CI watcher、daily digest），下一次触发时间、上次结果、累计影响

---

## 4. 重新定义 dashboard 的角色

### 4.1 一句话定义

> **VibeSOP Dashboard = 「你的 AI 协作的显微镜 + 教练」**

- **显微镜** (Microscope): 让你看到 agent 内部在做什么（已有数据：spans / traces / conversations）
- **教练** (Coach): 告诉你哪些做得好、哪些可以更好、下一步该练什么（缺失：insights / suggestions / trends）

### 4.2 两个互补隐喻

| 隐喻 | 关键问题 | 视图特征 |
|------|---------|---------|
| **Observability tool** (Datadog / Honeycomb) | 系统在做什么？ | 实时流、span 树、metric 图 |
| **Fitness tracker** (Strava / Apple Health) | 我的表现在如何？趋势？ | 时间线、趋势图、个性化建议 |

当前 dashboard 只是 #1 的雏形，完全缺 #2。

### 4.3 哲学思考：为什么需要 dashboard？

VibeSOP 的核心命题是"让 AI agents 像有技能和直觉的同事一样工作"。当同事是 AI 时，**协作的记忆和反思**变得困难：
- 你不知道 agent 为什么选了这个 skill
- 你不知道 agent 学到了什么 instinct
- 你不知道哪次会话贡献了最大的价值
- 你不知道下一个 skill 该优化什么

**Dashboard 是这种"协作记忆与反思"的具象化界面。** 它不是给运维看的监控屏，是给"AI 协作者"看的镜子。

类比：
- GitHub 是"代码的记忆"
- Notion 是"知识的记忆"
- Linear 是"决策的记忆"
- **VibeSOP dashboard 应该是「AI 协作的记忆与反思」**

---

## 5. 信息架构（IA）重新设计

### 5.1 核心转变

```
旧 IA（数据源分类）              新 IA（用户旅程分类）
─────────────────             ─────────────────
Overview                      → Now       （现在正在发生什么）
History                       → Work      （我和 agent 们做了什么）
Traces                        → Skills    （每个 skill 表现如何）
Conversations                 → Agents    （每个 agent 在做什么）
                              → Insights  （数据驱动的改进建议）
                              → Cost      （token / 费用 / ROI）
```

### 5.2 为什么这样切？

**用户问的真实问题**（不是数据源）：
1. "现在我的 agent 们在做什么？" → **Now**
2. "我刚才那个任务是怎么完成的？效果如何？" → **Work**
3. "我的 skill 装得有用吗？哪个该优化？" → **Skills**
4. "Claude / Kimi / Pi 各自的表现和成本？" → **Agents**
5. "数据告诉我应该改进什么？" → **Insights**
6. "我花了多少钱？ROI 如何？" → **Cost**

### 5.3 每个 view 的设计草图

#### 5.3.1 Now（实时）

**核心问题**: 现在我的系统在做什么？

**布局**:
- 顶部：实时事件流（SSE/WebSocket，新 span 新会话滑入）
- 中部：今天的关键数字（routes / active sessions / cost today / loops running）
- 底部：active loops 状态条（下次触发倒计时 + 上次结果）

**视觉**:
- 类比 Twitter feed / Vercel deployment log
- 新事件带渐入动效
- 异常事件（error span、低置信度路由）自动浮到顶部并高亮

#### 5.3.2 Work（工作会话）

**核心问题**: 我刚才那个任务是怎么完成的？

**布局**:
- 时间线视图（不是表格），按"工作任务"聚合（不是按 JSON 文件）
- 每个工作任务展开后：sub-agent 树状图 + 决策路径 + 产出物 + 用了哪些 skill
- 支持搜索、按 skill 过滤、按时间过滤

**关键洞察**: 把 conversation 从"数据行"重定义为"工作叙事"——用户回看的不应该是"turn 1, turn 2..."，而应该是"我用 Claude 做了 X，它调度了 Explore sub-agent 查代码、调度了 Code sub-agent 写实现，总共花了 $0.23 和 4 分钟，触发了 code-review skill 但没改成功"。

**视觉**:
- 类比 GitHub Activity timeline / Linear ticket view
- 树状结构清晰展示 sub-agent 层级
- 每个 span 可点击展开看 prompt/response

#### 5.3.3 Skills（技能健康）

**核心问题**: 我的 skill 装得有用吗？哪个该优化？

**布局**:
- 按 pack 分组（builtin / superpowers / omx / gstack / 自定义）
- 每个 skill 一张卡片：命中率、平均置信度、平均成本、用户满意度、最近 7 天趋势 sparkline
- 排序：按"需要关注程度"（低命中率 + 高使用量 = 最该改进）

**关键洞察**: 当前 top_skills 是"用得最多的"，但用户真正想知道的是"哪些 skill 在拖后腿"。需要一个"健康度"复合指标。

**视觉**:
- 类比 Vercel deployment dashboard / Sentry project list
- 健康度 = 综合（success_rate × confidence × satisfaction）的 0-100 分
- 红黄绿色彩编码

#### 5.3.4 Agents（agent 视角）

**核心问题**: Claude / Kimi / Pi 各自的表现和成本？

**布局**:
- 每个 agent 一张大卡片（Claude Code / Kimi / Pi / Grok / OpenCode 等）
- 卡片内容：本周调用次数、平均延迟、token 消耗、cost、错误率、最常调用的 skill
- 跨 agent 对比图表（哪个 agent 用得最多？哪个最便宜？哪个最准？）

**关键洞察**: 当前 dashboard 完全没有"agent 维度"。但用户经常问"我用 Claude 还是用 Kimi 完成这类任务更划算？"——dashboard 应该用数据回答。

**视觉**:
- 类比 cloud provider cost explorer
- 每个agent logo + 关键 metric
- 趋势线对比

#### 5.3.5 Insights（数据驱动建议）

**核心问题**: 数据告诉我应该改进什么？

**布局**:
- 卡片瀑布流，每张卡片是一条数据驱动的建议：
  - "🔍 code-review skill 本周 12 次低置信度命中（0.42-0.65），触发词和 review-related 重叠——建议合并或区分"
  - "💰 你 35% 的成本来自 Pi 调用 superpowers/code-review，但成功率只有 58%——考虑改用 Claude"
  - "📈 instinct 'debug-task' 自 7-15 创建后被命中 47 次，为路由贡献了 23% 的提速——可以考虑提升 boost 权重"
  - "⚠️ loop 'daily-digest' 上次执行失败（24h 前），未触发任何 alert——可能需要检查"
- 每条建议带操作按钮（"查看证据"、"应用建议"、"忽略"）

**关键洞察**: 这对接 v8.2 P2 的 InsightAnalyzer（route_mismatch + skill_underuse）。Dashboard 是 analyzer 输出的"用户界面"。

**视觉**:
- 类比 Linear inbox / GitHub insights
- 严重程度色彩编码（critical=红 / warn=黄 / info=蓝）
- 可按 skill / severity / kind 过滤

#### 5.3.6 Cost（成本与 ROI）

**核心问题**: 我花了多少钱？ROI 如何？

**布局**:
- 顶部大数字：今日 / 本周 / 本月 cost + 趋势
- 按 skill 分解的成本条形图
- 按 agent 分解的成本饼图
- ROI 视图：每个 skill 的"价值"（用户满意度 × 使用次数 / cost）

**关键洞察**: 当前完全没有 cost 视图，但 v8.2 P1 已经在 span 里记了 cost_usd（pricing table 已 ship）。这是"现成数据但没暴露"的最大盲点。

**视觉**:
- 类比 Stripe dashboard / Vercel billing
- 大数字 + 趋势 sparkline
- 颜色编码（绿=省钱 / 红=贵）

---

## 6. 视觉与交互设计原则

### 6.1 视觉原则

**P1 — 不要抄 GitHub dark theme**

当前 `#0f1117` + `#1a1d27` + 表格 = 工程师审美。VibeSOP 用户确实是技术人，但密度可以有"层次"——主干稀疏，展开后密集。

**P2 — 参考这些产品（按推荐度排序）**

| 产品 | 学什么 |
|------|--------|
| **Linear** | 极简、阴影层次、键盘驱动、issue 详情布局 |
| **Vercel dashboard** | 密度与留白平衡、metric 卡片、deployment log 流式 |
| **Raycast** | 命令面板、键盘交互、卡片hover |
| **Arc Browser** | 视觉大胆、色彩、动效 |
| **Honeycomb / Datadog** | observability 视图、span 树、查询构建器 |

**P3 — 字体与色彩**

- 字体：**Inter** 或 **Geist Sans**（不要 system font），等宽用 **JetBrains Mono**
- 主色：保留 dark theme，但加 `gradient` + `glow`（首屏视觉冲击）
- 强调色：保留 accent blue，但增加状态色（success/warning/danger/info）饱和度

**P4 — 焦点元素**

每屏必须有 1-2 个"焦点元素"——大数字、关键趋势、关键建议。当前 dashboard 没有焦点，4 个 tab 都是平铺。

### 6.2 交互原则

**I1 — First load 必须有意义**

打开 dashboard 不能是空表格或单一会话。应该立即看到"现在在发生什么"——这就是为什么默认 tab 改为「Now」。

**I2 — Progressive disclosure**

主视图稀疏（只展示关键信息），点击展开看完整 detail。当前 dashboard 是反过来的——主视图已经是密集表格。

**I3 — Storytelling for conversations**

Conversation 不是表格行，是叙事。Work 视图应该是时间线 + 树状结构，不是 table。

**I4 — Real-time feel**

SSE 或 WebSocket 流式更新（"活着"的感觉）。当前是手动 refresh，毫无"实时感"。

**I5 — Actionable insights**

每条 insight 都附带"建议行动"按钮，不是只展示问题。点击应该能跳转到相关 Work / Skills / Cost 视图。

**I6 — Cross-view linking**

点 insight 跳到相关 conversation/span；点 conversation 看到涉及哪些 skill；点 skill 看到所有相关 insight。当前完全孤岛。

**I7 — Keyboard-first**

Power user 会想用键盘：`cmd+k` 命令面板、`j/k` 导航、`enter` 展开、`/` 搜索。参考 Linear / Raycast。

**I8 — Deep-linkable**

每个视图、每个会话、每个 skill、每条 insight 都应该有独立 URL（hash route），可分享可深链。

### 6.3 技术约束下的取舍

- **保持单 HTML 文件**：不引入 React/Vue 等框架（增加构建复杂度）。用原生 JS + 少量 CDN 库（Alpine.js / htmx 可选）。
- **FastAPI 后端**：复用现有 API，新增 SSE 端点（`/api/stream`）和聚合端点（`/api/insights` / `/api/cost/summary`）。
- **后端聚合先行**：metric 计算放后端，前端只做展示。避免前端处理大量 spans。

---

## 7. 关键取舍（trade-offs）

### 7.1 实时 vs 离线分析

- **实时流（看正在发生）** vs **定期分析（看趋势）**
- **取舍**: 两者都要，但**实时是主导**（让人感到"活着"），分析是辅助（每周一次的"教练报告" + Insights 视图的离线分析）

### 7.2 工程师视角 vs 用户视角

- 工程师看 span 树、token 明细；用户看"任务完成度、用了哪些 skill、效果如何"
- VibeSOP 用户是"用 AI 编程的开发者"——同时是工程师也是用户
- **取舍**: **两个视角并存，用户视角为主**，工程师视角是一键展开（点 span 节点查看原始 JSON）

### 7.3 信息密度 vs 美观

- 密度高 = 工程师友好但丑陋；美观 = 留白多但信息少
- VibeSOP 用户偏好密度，但密度可以有"层次"
- **取舍**: **分层密度**——首屏稀疏（焦点 + 关键数字），展开后密集（完整 spans、原始 JSON）

### 7.4 单页 SPA vs 多页应用

- 当前单 HTML 文件 639 行原生 JS
- 多页应用开发成本高
- **取舍**: **保持单页，加 hash route**（`#now`, `#work`, `#skills`, `#agents`, `#insights`, `#cost`）以便深链；不超过 2000 行

### 7.5 默认 tab 选谁

- 当前默认 Overview（数字 cards）
- 新设计默认应该是？
- **取舍**: **默认 `Now`**（实时正在发生什么），因为这是最高频的"打开 dashboard 想知道的事"

### 7.6 数据时间窗口

- 当前不区分，全量
- **取舍**: 默认窗口"过去 7 天"，每个视图可切换（24h / 7d / 30d / all）

---

## 8. 与 v8.2 Observability Loop Closure 的对接

v8.2 P1 已 ship（spans.jsonl 富数据 + pricing + vibe trace metrics）。P2 会引入 InsightAnalyzer + LoopSpec target refactor。Dashboard 应该：

1. **复用 v8.2 数据**: spans.jsonl 已有 cost / project_id / schema_version，dashboard 直接消费
2. **接入 P2 analyzer**: Insights 视图直接对接 `suggestions.jsonl`（route_mismatch + skill_underuse）
3. **可视化 instinct 演化**: Work / Skills 视图展示 instinct 命中 / boost 历史
4. **Loop 任务监控**: Now 视图展示 active loops（CI watcher / daily digest）

**Dashboard 是 v8.2 闭环的「最后一公里」**——没有 dashboard，spans/analyzer 数据对用户不可见，闭环不成立。

---

## 9. 未解决的问题（留给对抗讨论 + grok/pi 评审）

1. **MVP 范围**: 6 个视图（Now / Work / Skills / Agents / Insights / Cost）是否太多？应该先做哪 3 个？
2. **实时更新的工程成本**: SSE/WebSocket 值得吗？还是 30s 轮询够用？
3. **Conversation 重定义为"工作叙事"**: 如何聚合多个 conversation 成一个"工作任务"？按什么 key？
4. **Insights 视图依赖 v8.2 P2 analyzer**: 现在还不可用，dashboard 应该先做空壳还是等 P2？
5. **Agents 视图的"agent"如何识别**: 从 span 的 `agent_id` 字段？从 conversation metadata？跨 agent 数据完整性如何？
6. **Cost 视图的"ROI"如何定义**: 用户满意度 × 使用次数 / cost？这个公式合理吗？
7. **键盘交互的复杂度**: 引入 cmd+k 命令面板是否过度设计？
8. **视觉重设计的工程量**: 单 HTML 文件多大算合理？引入轻量 CSS 框架（Tailwind CDN）值得吗？
9. **Insights 操作按钮"应用建议"如何实现**: dashboard 能直接修改 skill 文件吗？还是只是"标记待办"？
10. **多项目支持**: dashboard 如何处理多个 .vibe 目录？当前只读 cwd 的 .vibe。

---

## 10. 下一步流程

1. **Phase 2 — 对抗 sub-agent 多视角辩论**: 启动 5 个 sub-agent，分别从产品/IA/视觉/怀疑论/工程视角攻击本草案
2. **Phase 3 — grok + pi 二次评审**: 把修订后的草案发外部评审
3. **Phase 4 — 最终设计文档**: 合并所有反馈，输出可实施的设计 spec

---

*Phase 1 complete. 等待对抗讨论。*
