# Merged Review: Task-Anchored Memory + Safe Skill Promote

> grok + pi 二轮评审整合（2026-07-29）
> Brief: `_review-task-memory-loop-brief.md`
> 原始输出: `_review-task-memory-loop-grok.md` / `_review-task-memory-loop-pi.md`

---

## 评审分布对比

| 问 | grok | pi | 共识 |
|---|---|---|---|
| Q1 金标准规则 | **P0** | P1 | 都说规则不可靠；pi 给更准的修法 |
| Q2 BM25 | P1 | P1 | 都说够 MVP，但要留 embedding 后路 |
| Q3 Promote 阈值 | **P0** | P1 | 都说阈值是直觉 + 候选池没生命周期 |
| Q4 砍 Joined DAG | P1 | P2 | grok 担心，pi 觉得 4 周内不致命 |
| Q5 最大风险 | **P0**（信任链断） | **P0**（认知负荷 + kill 指标错） | **都点名闭环不闭合，但死法诊断不同** |

**双 P0 共识**：Q3 + Q5。两个 reviewer 独立点名同一件事 = 必改。

---

## P0 必改项（合并后）

### P0-1 — 金标准规则用现成信号，别重造轮子

**grok 原话**："把'快 + 无 routing_miss + completed'当成金标准，会系统性标中'短路成功'"

**pi 原话（更尖锐）**："`InstinctLearner.record_outcome(success)` 已经存在，说明系统有显式成功信号，但金标准规则完全没用它。这相当于手里有测谎仪却只用秒表判断。"

**合并修订**：
- 主信号改用 `InstinctLearner.record_outcome(success)` 已有数据
- 辅信号：`status==completed AND duration<=p50`
- 门控：`min_samples >= 5`（grok 提议 3，pi 提议 5——取严）
- n < 5 时只标 `candidate_success`，不进金标准池
- duration 不用硬切 p50，用 p25-p75 区间（grok 建议）

### P0-2 — Skill Promote 加成功率门禁 + 候选池生命周期

**grok 原话**："≥2 金标准在 10 次跑、成功率 20% 时仍会触发 promote，把'偶然成功'当成可推广 skill"

**pi 原话**："'10 次仅 2 次金标准'不是 promote 信号，而是该 task 本身不适合标准化——可能步骤变体太多"

**合并修订**：
- 触发条件改为：`n>=3 AND gold_rate >= 60%`（grok）
- **反条件**（pi 新增）：`gold_rate < 30%` → 标 `unstable`，进诊断队列不进候选池
- 候选池 TTL = 30 天（pi）
- 候选池硬上限 N 条（防积压）
- 未审候选**不注入** prompt（grok）

### P0-3 — W3 从"hint 注入"改为"可执行 replay"

**这是 pi 的核心产品洞见，grok 没看到这层**：

**pi 原话**："W3 在 system prompt 注入'上次走了 X→Y→Z'是一个纯提示（hint），不自动执行。用户必须：(a) 主动 `vibe recall` →（b）手动比对自己当前场景 →（c）决定是否复用。三步都是认知负荷，不是节省。对比 Copilot 的 tab-complete——零动作、即时价值——这个 loop 差了两个数量级。"

**pi 替代方案**：`vibe route` 命中金标准时直接给出"按上次方案执行？[Y/n]"，一键重放。

**合并修订**：W3 砍掉"hint 注入"，改为 `vibe route --replay` 一键回放金标准 step 序列。Hint 模式作为 fallback 保留（用户可在 config 里选），但**默认是 replay 提示**。

### P0-4 — Kill criterion 本身错了（pi 独家发现）

**pi 原话**："W2 kill criterion 测的是'自用频次'，测不出效用。作者可能出于好奇连用 5 次、觉得有趣但没用、停止使用——kill criterion 却显示'pass'。价值感知延迟 + 习惯养成成本 + 无效度量 = 最可能静默死亡。"

**合并修订**：原 kill criteria 全部重写——
- ❌ 原 W2: `vibe recall` 调用次数 ≥10 次/周（频次 ≠ 价值）
- ✅ 新 W2: **`vibe recall` 结果被用户 follow 的比例**（即 recall 返回后，用户是否真的去了那条 trace / 执行了 replay）
- ❌ 原 W12: approve 率 <20%（分母可能全是过期垃圾）
- ✅ 新 W12: **active skill 在 routing 中被命中 ≥3 次/月**（端到端效用）

---

## P1 应该改项

### P1-1 — BM25 留 embedding 后路

**pi 原话**："W2 用 BM25 但 W2.5 埋一个 low-cost local embedding（all-MiniLM-L6，200MB，纯 CPU）做离线评估——不阻塞 W2 交付，但让 kill 决策有数据支撑。"

**合并修订**：W2 ship BM25；W2.5（半周）做 embedding 离线对比，作为 W2 kill 决策的辅助信号。

### P1-2 — Joined DAG 用轻量 in-task motif 替代

**grok 原话**："在同一 task_id 内对 span 序列做轻量 motif（如 `span_kind` + skill/role 序列的最长公共子序列或 n-gram support≥2），仅用 support 写 draft 里的'core steps vs optional'，成本远低于 AgentTrails 全套。"

**pi 也同意**（虽 P2）：4 周内不致命，但 skill 生成前需要在 task_id 内做一次 step-level frequency count。

**合并修订**：W4 Skill Promote 流程内嵌一步 **step frequency count**——同一 task_id 多次执行里，每个 step 的出现频次 → core（100%）/ common（≥60%）/ optional（<60%）。不引入跨 task JOIN。

---

## P2 / Defer

- Joined DAG 全量 viz（Cytoscape）：确认 defer，不进 4 周 MVP
- Dashboard Timeline UI：维持 defer，等 CLI 跑通验证价值再考虑

---

## 评审双方分歧（保留双方观点）

| 项 | grok | pi | 我的判断 |
|---|---|---|---|
| Q1 严重度 | P0 | P1 | 取 P0（pi 的修法更对，但严重度按 grok） |
| Q4 严重度 | P1 | P2 | 取 P1（轻量 motif 必做，但 4 周内只做 frequency count 不做完整 DAG） |
| Q5 死法 | 信任链断（数据层） | 认知负荷（产品层） | **两个都对，互补**——P0-3 修产品层，P0-1/P0-2 修数据层 |

---

## 修订后的 4 周 MVP（替换原方案）

### W1 — 被动金标准检测（v2）

- 主信号：`InstinctLearner.record_outcome(success)` 已有数据
- 门控：`min_samples >= 5`，n<5 标 `candidate_success`
- duration 用 p25-p75 区间
- 新增 `/api/tasks` 端点

### W2 — Recall CLI（BM25 + 离线 embedding 对照）

- `vibe recall "<query>"` 用 BM25
- top-1 score 与 top-2 必须拉开（绝对分阈值），否则视为无召回
- **W2.5**：跑 all-MiniLM-L6 离线对照（不进 prod）

### W3 — Replay 模式（替代 hint 注入）

- `vibe route --replay` 一键回放金标准 step 序列
- 默认提示"按上次方案执行？[Y/n]"
- Hint 注入作为 config fallback

### W4 — Skill Promote with 频次 + 生命周期

- 触发：`n>=3 AND gold_rate >= 60%`
- 反条件：`gold_rate < 30%` → unstable 诊断队列
- step frequency count → core/common/optional 标注
- 候选池 TTL=30d，硬上限，未审不注入

### Kill Criteria（重写）

- **W2 末**：recall **follow 率**（用户看完 recall 是否真去 trace 或执行 replay）≥30% → 否则停
- **W4 末**：金标准 task ≥5 个，候选池积压 <10 条 → 否则 freeze
- **W12 末**：active skill 在 routing 中**实际命中** ≥3 次/月 → 否则归档

---

## 一句话总结

**两边独立点名闭环不闭合是最大风险**——但 grok 看到的是数据层（坏数据→坏注入），pi 看到的是产品层（认知负荷+度量错）。修订后的方案：**P0-1/P0-2 修数据层 + P0-3 改 replay 修产品层 + P0-4 重写 kill criteria 修度量层**。**任一层不修，闭环都断**。
