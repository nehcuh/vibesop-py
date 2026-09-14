# grok Review: Task-Anchored Memory + Safe Skill Promote

> 评审时间：2026-07-29
> 模式：grok --prompt-file（single-turn，无 tool 调用）

---

### Q1 — 被动金标准规则

**评级：P0**

**理由：** 把"快 + 无 routing_miss + completed"当成金标准，会系统性标中"短路成功"（早退、跳过关键步骤、低价值 task），在 n=2 时 p50 几乎无统计意义，规则在单用户低频场景下先退化再误导后续 promote。

**替代：** 用**多信号门禁 + 最小样本量**：`n_task ≥ 3` 才参与金标准；加至少 1 个正向信号（用户未立即重试 / 无 follow-up 纠错 span / 存在 `positive_pattern` 或用户显式 accept）；duration 用相对同 task 历史的分位区间（如 p25–p75）而非硬切 p50，n 不足时只标 "candidate success" 不标金标准。

---

### Q2 — BM25 Recall

**评级：P1**

**理由：** BM25 对同词根/同 task_id 有效，对"表述不同、意图相同"召回弱；但在单用户、task 文本短、库小的场景，错召回的伤害确实可能大于无召回——尤其 W3 会把错误"上次路径"注入 system prompt。

**替代：** 先做 **exact/fuzzy task_id + 词重叠阈值门槛**（top-1 score 与 top-2 拉开、或绝对分阈值），注入默认 off、仅 CLI 先验证；embedding 作为 W2 后的 **kill 续命选项**（本地小模型 + 阈值），不要在 MVP 默认路径里当主召回，避免"有 recall 但更糟"污染信任。

---

### Q3 — "≥3 跑且 ≥2 金标准"

**评级：P0**

**理由：** 阈值是直觉启发式：≥2 金标准在 10 次跑、成功率 20% 时仍会触发 promote，把"偶然成功"当成可推广 skill；且候选池无过期/无审阅 SLA 时，极易变成无人审的草稿坟场，kill 的 "approve 率" 也会因分母垃圾而失真。

**替代：** 改为 **成功率门禁**（如金标准率 ≥60% 且 n≥3）+ **失败族诊断**（高 rerun / 高 routing_miss 走"task 有问题"队列而非 draft）；候选池加 **28 天 TTL / 最多 N 条 / 未审则降权不注入**，W4 kill 看 approve 率时排除过期垃圾。

---

### Q4 — 砍掉 Joined DAG

**评级：P1**

**理由：** 砍 viz 合理，但把 "跨 run 的步骤共现 / support count" 一并砍掉，Skill Promote 只剩 task_id 级成功标签，**无法区分 canonical motif 与偶然路径**，抽出的 SKILL 容易变成"整段黑盒流程"而非可复用步骤，粗粒度是结构性风险，不是 UI 偏好问题。

**替代：** 不做跨 trace 大图、不做 LLM 猜边；在**同一 task_id 内**对 span 序列做轻量 motif（如 `span_kind` + skill/role 序列的最长公共子序列或 n-gram support≥2），仅用 support 写 draft 里的 "core steps vs optional"，成本远低于 AgentTrails 全套。

---

### Q5 — 最大风险

**评级：P0（致命点）**

**最致命：闭环不闭合（信任链断裂）**

**理由：** 产品叙事是 "agent 记住你做过什么"，但 4 周路径是 **被动错标金标准 → 可能错召回 → 注入 prompt → 草稿堆积且不自动 promote**；任一步质量差都会把错误记忆写进路由，而真正的价值闭环（人审 → active skill → 可观测变好）被红线推迟，用户感知停在"多了一堆不可信建议"，kill 指标（自用次数 / 金标准数量）也会在错误闭环上虚高或虚低。

---

### 总判（结构）

方向对：**task_id 锚定 + 人审 promote + 拒 ML 聚类** 适合单用户 SkillOS。
必须先修：**金标准定义（Q1）与 promote 触发逻辑（Q3）**；否则 W3/W4 放大噪声。
可接受延后：embedding、Joined DAG 全量、Dashboard。
不可接受延后：**同 task 内步骤共现（轻量）+ 注入/候选的默认安全阀**。
