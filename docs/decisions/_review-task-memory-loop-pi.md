# pi Review: Task-Anchored Memory + Safe Skill Promote

> 评审时间：2026-07-29
> 模式：pi -p（inline brief，无 tool 调用）
> 注：首次跑（br4q6djxw）卡 5+ 分钟无输出，重跑（brf32q91y）使用 inline brief 立即完成

---

## Q1 — 被动金标准规则靠谱吗？

**评级：P1**

规则的核心缺陷不是"太快误标"——brief 中 `InstinctLearner.record_outcome(success)` 已经存在，说明系统有显式成功信号，但金标准规则完全没用它。这相当于手里有测谎仪却只用秒表判断。p50 在 n=2 时退化为均值，但对于 MVP 实验性假设验证，这可以接受——前提是设一个 `min_samples >= 5` 的下界，把低频 task 排除出金标准候选，等数据积累后再进入。

替代方案：金标准 = `status==completed AND (duration<=p50 OR instinct_success==true)`，并以 `min_samples=5` 做门控。

---

## Q2 — Recall 用 BM25 真的够吗？

**评级：P1**

BM25 对"同义不同词"天然盲。比如"修登录 bug"←→"debug auth 报错"零词重叠，BM25 全漏。但在单用户低频场景，用户词汇漂移有限，且 W2 kill criterion 会直接判死刑——这是正确的实验设计。

真正的问题是：**BM25 + task_id 匹配几乎退化为 task_id 索引**。task_id 是精确值，BM25 对它不做模糊化；root_span.input_data 的文本又可能很短。结果就是查"deploy"只能召回 task_id 里带"deploy"的，而不是所有部署类 task。

替代方案：W2 用 BM25 但 W2.5 埋一个 low-cost local embedding（all-MiniLM-L6，200MB，纯 CPU）做离线评估——不阻塞 W2 交付，但让 kill 决策有数据支撑。

---

## Q3 — Skill Promote 候选池的"3 次金标准"阈值是怎么定的？

**评级：P1**

阈值本身可调，不是核心问题。核心问题是**候选池没有生命周期管理**——没有过期、没有自动清理、没有 review SLA。技能草案积压到 50 个没人看是确定的结局。另一个隐藏问题是："10 次仅 2 次金标准"不是 promote 信号，而是**该 task 本身不适合标准化**——可能步骤变体太多，或环境依赖强。但规则不做区分，会照常生成草稿。

替代方案：（1）候选池加 `stale_after=30d`，到期自动归档；（2）增加一个反条件：`金标准率 < 30%` 时标记为 "unstable"而非生成草稿，转为诊断条目。

---

## Q4 — 砍掉 Joined DAG 是不是把 AgentTrails 最有价值的部分丢了？

**评级：P2（4 周 scope 内）**

砍的理由（task_id 漂移、迁移成本、user 无 viz 需求）是诚实的 MVP 剪裁。不加 DAG motif，skill 抽取就是"这个 task 的全量 step 序列"，粒度确实会偏粗——可选步骤被无条件固化进 skill。

但 4 周内这不致命，因为 MVP 目标是验证"记忆→召回→复用"假设，不是产出高质量 skill。只要在 post-W4 roadmap 里标记：**skill 生成前需要在 task_id 内做一次简单的 step-level frequency count**（"步骤 A 在 3 次 trace 中出现 2 次，标记为 optional"），无需完整 DAG join，成本极低。

---

## Q5 — 真正最大的风险是什么？

**闭环不闭合。**

W3 在 system prompt 注入"上次走了 X→Y→Z"是一个纯提示（hint），不自动执行。用户必须：（a）主动 `vibe recall` →（b）手动比对自己的当前场景 →（c）决定是否复用。三步都是认知负荷，不是节省。对比 Copilot 的 tab-complete——零动作、即时价值——这个 loop 差了两个数量级。

更致命的是：W2 kill criterion 测的是"自用频次"，测不出效用。作者可能出于好奇连用 5 次、觉得有趣但没用、停止使用——kill criterion 却显示"pass"。价值感知延迟 + 习惯养成成本 + 无效度量 = 最可能静默死亡。

替代方案：W3 不做 hint，做**可执行 replay**——`vibe route` 命中金标准时直接给出 "按上次方案执行？[Y/n]"，一键重放。这才是闭环。
