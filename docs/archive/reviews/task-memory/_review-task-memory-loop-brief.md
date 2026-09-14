# Review Brief: Task-Anchored Memory + Safe Skill Promote

> Brief for grok + pi 二轮对抗评审
> Topic: VibeSOP dashboard 接下来 4-12 周的产品方向
> 请聚焦 5 个结构性问题，不要逐行校验

---

## 背景（30 秒版）

**VibeSOP**：本地 AI SkillOS，给独立开发者用 Claude Code / Grok / Kimi / Pi 等多 agent 写代码时做 skill 路由/编排/生命周期管理。

**已 ship 的现状**：
- Dashboard v3 Phase A+B：11 个 endpoint（含 `/api/orchestration/dag`、`/api/reflections`），前端 4 tab（Overview/History/Traces/Conversations）
- Span 数据完整：`task_id` / `role_id` / `parent_span_id` / 7 种 span_kind
- 7 类 Reflection（routing_miss / skill_misuse / trigger_vague / cost_blow / agent_choice / positive_pattern / context_note），但**目前手动 0 条**
- 1573 个 span 已采集；早期 task_id 填充率 0%，Phase A 后修复
- 已有但孤立的件：`MissedQueryTracker`（Jaccard 聚类失败 query）、`SkillDistiller`、`InstinctLearner.record_outcome(success)`

**两个外部参照**：
1. **Mastra Trace Intelligence**（竞品，2026-07 发布）：LLM 给 trace 生成 4 信号 → UMAP+HDBSCAN 聚类。SaaS，纯观测，不闭环。
2. **AgentTrails 论文**（VLDB 2026 workshop）：trace → provenance graph → 跨 trace capsule 聚类 → joined graph。论文承认用 LLM 猜依赖边不 scale。

## 第一轮 workflow 结论（待评审）

跑了 5 阶段 workflow：定调 → 发散（3 视角 agent）→ 对抗 → 收敛 → 产品化。

**Lead Direction**：**"会记事的 agent 操作系统" — Task-anchored memory + Safe skill promote**

核心叙事：**"Mastra 让您看清楚 agent 在做什么；VibeSOP 让 agent 记住您做过什么。"**

### 4 周 MVP（按周拆）

- **W1 被动金标准检测**（无 UI，纯后端）：扫 spans 按 `task_id` group；规则 `routing_miss_count == 0 AND duration_ms <= p50(task) AND status == completed`；新增 `/api/tasks` 端点
- **W2 Recall CLI**：`vibe recall "<query>"` 用 BM25 over `task_id + root_span.input_data`；返回 top-3 历史 trace 摘要 + 金标准步骤序列；**不引入 embedding**
- **W3 路由层透明注入**：`vibe route` 命中时若 recall 返回金标准，在 system prompt 注入"上次走了 X→Y→Z（trace_id=...）"；可关闭
- **W4 Skill Promote 候选池**：触发条件 `同 task 跑 ≥3 次且 ≥2 次金标准`；自动生成 SKILL.md 草稿到 `.vibe/skill_drafts/`；**红线：4 周内不做任何自动 promote 到 active skill 的路径**

### Kill Criteria

- **W2 末**：`vibe recall` 自用 <3 次/周 → 痛点假设错，停后续
- **W4 末**：金标准检测产出 <5 个 task → 数据密度不够，pivot 或 freeze
- **W12 末**：候选池 approve 率 <20% → 抽取质量太差，归档已抽 skill

### 关键架构选择（共识）

3 个视角 agent 罕见地在两点上对齐：
1. **拒绝 ML 聚类**（不用 UMAP/HDBSCAN，用 task_id 直接 group）
2. **拒绝 auto-write skill**（候选池隔离 + 必须人审）

### 关键反转

- 砍掉 **Multi-trace Joined DAG**（AgentTrails 主菜）—— 怀疑论者指出 task_id 语义漂移 + schema 迁移成本
- 砍掉 **Provenance Copilot**（LLM 查询接口）—— 无向量库 + hallucination 不可逆破坏信任
- **Dashboard UI 推后**：persona 自己承认"4 个 tab 看一眼就关了"，先做 CLI push 不做 viz

---

## 5 个评审问题

### Q1 — 被动金标准规则靠谱吗？

规则 `routing_miss == 0 AND duration <= p50 AND completed` 把"快且没失败"等同于"金标准"。
- **是否会把"敷衍但快速完成"的 trace 误标为金标准？**
- **单用户低频场景下，p50 统计本身稳吗？**（某 task 只跑过 2 次，p50 就是平均值，规则退化）
- **有没有更靠谱的被动信号？**（例：用户是否复用过这条 trace 的输出？是否在之后留下 positive_pattern reflection？）

### Q2 — Recall 用 BM25 真的够吗？

明确拒绝了 embedding/UMAP。理由是单用户低频场景下 ML 是噪声。
- **BM25 over `task_id + root_span.input_data` 能召回"语义同义但表述不同"的 task 吗？**（"修 dashboard 反思 bug" vs "ReflectionStore 修锁"）
- **如果 80% 的 recall 都是错召回，会不会比"没有 recall"更糟**（用户被骗一次后弃用）？
- **应该不应该至少做一个最便宜的 embedding 兜底**（如 sentence-transformers 本地模型）？

### Q3 — Skill Promote 候选池的"3 次金标准"阈值是怎么定的？

触发条件 `同 task 跑 ≥3 次且 ≥2 次金标准`。
- **这是直觉还是有依据？** 3 次是否足够区分"真 pattern"vs"巧合"？
- **如果某 task 跑了 10 次但只有 2 次金标准（20% 成功率）—— 它应该被 promote 还是应该被诊断为"这 task 本身有问题"？**
- **候选池会不会变成"永远没人审的垃圾堆积"？** （单用户没有外部压力审 skill）

### Q4 — 砍掉 Joined DAG 是不是把 AgentTrails 最有价值的部分丢了？

砍掉的理由：task_id 漂移 + schema 迁移成本 + User 没要求 viz。
- **但 Joined DAG 的 support count 不只是 viz —— 它是"判断哪些步骤是 canonical"的唯一信号**。砍掉之后，Skill Promote 怎么知道一个 motif 是"3 次都出现"还是"3 次中有 2 次出现"？
- **如果只看 task_id 维度（不看 DAG motif），抽取出来的 skill 会不会过于粗粒度**（整个 task 一刀切，而不是 task 内的子流程）？

### Q5 — 真正最大的风险是什么？（开放题）

排除以上 4 问已覆盖的，**您认为这个 4 周 MVP 最可能死在哪？**

候选（不限于此）：
- 假设错：用户其实不需要"agent 记事"
- 数据密度不够：单用户根本攒不到 3 次同 task
- 工程量低估：4 周做不完
- 闭环不闭合：人审 skill 这一步永远不被触发
- 其他？

请给出**最致命的那一个**+ 一句话理由。

---

## 评审输出要求

每问给：
- **评级**：P0（必须改）/ P1（应该改）/ P2（nit）
- **一句话理由**
- **如有替代方案，给一句话建议**（不要展开设计）

总长度 < 800 词。不要逐行校验实现细节。
