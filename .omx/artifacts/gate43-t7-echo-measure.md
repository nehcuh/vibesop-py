# gate42 一周观察 + gate43 T+7 验收 — 测量记录（2026-08-31）

> 数据源：`~/Projects/cmspark/.vibe/observability/{spans,route_outcomes}.jsonl`（只读，未改动任何数据/代码/配置）。
> 关键时刻：gate42 cutover = span_ts `2026-08-24T09:31Z`；gate43 T0 = `2026-08-24T10:42Z`（18:42 CST）；T+7 = `2026-08-31T10:42Z`（本次测量时已过）。
> 规格原文：`gate42-synthesis.md` §4/§6、`gate43-synthesis.md` §1.4。前序产物：`gate42-t24h-measure.md`（已读取，未缺失）。
> 9-7 T+14 复检**必须比对本文**并沿用本文锁定的口径定义（§B.0）。

## 总裁决

| 项 | 裁决 | 一句话 |
|---|---|---|
| A. gate42 一周观察 | **PASS**（gate42 自身范围内） | 幻影绝对计数 **0/409**；占比对 expired 同量级、对 moved_on 未达平价，残余 mass 根因是**正交的跨平台 hook 双发**，非 gate42 修复对象 |
| B. gate43 T+7 减频 | **PASS**（硬验收双条件全过，stretch ≥50% 亦过） | 回声口径 14.4 → **3.57 对/天（−75.2%）**，95% CI [2.31, 5.27] 不含基线；hook 单发量稳定、divergent=0、真人残量未消失 |

无回滚建议（两项均 PASS；回滚条款不触发）。

---

## A. gate42 一周观察

### A.1 新增行盘点 [executed]

新增行 = span_ts > `2026-08-24T09:31Z`（cutover），共 **733** 行，span_ts 范围 `2026-08-25T00:47:26Z` .. `2026-08-31T07:01:54Z`：

| reason | n | 占比 |
|---|---|---|
| reask_same_task_id | 305 | 41.6% |
| session_expired_without_reask | 158 | 21.6% |
| hit_reask_same_task_id | 104 | 14.2% |
| session_continued_without_reask | 82 | 11.2% |
| hit_session_moved_on | 59 | 8.0% |
| hit_session_expired | 25 | 3.4% |

outcome：weak_negative 409 / weak_positive 324。

按日（span_ts）：08-25=184、08-26=133、08-27=119、08-28=223、08-29=42、08-30=0、08-31=32。
注意：outcome 派生有 ≥24h 滞后（expiry 类需满 24h 才可判），08-30/31 的行数尚不完整——9-7 复检时"新增行"会自然增长，属正常非违规（t24h 已预告同一现象）。

### A.2 只增不减核对 vs t24h [executed + 1 处 inspected 异常]

同切片（cutover < span_ts ≤ `2026-08-26T14:40:47Z`，t24h 测得 258 行）：现为 **304 ≥ 258 ✓**。
分布变化：expired 51→93、hit_expired 10→15（t24h 预告的派生补齐 ✓）；continued 33=33、hit_reask 41=41、moved_on 25=25；**reask_same 98→97（−1，异常）**。
−1 排查 [executed]：全文件 4029 行 span_id 全唯一（无重复行）；09:30Z–10:42Z 无边界行；append-only 文件计数不应回退。判定：t24h 侧计数边界疑点（[inspected]，无法从现行文件复现 98），不影响任何闸门指标。

### A.3 硬验收：幻影绝对计数 [executed]

真 reask 行 = reason ∈ {reask_same_task_id, hit_reask_same_task_id} 共 **409**。
逐候选归因（复刻新谓词与 t24h 口径：同 task_id、started_at 晚于行 span_ts、id ≠ 行 span_id 的候选中跳过 CLI、取最早非 CLI route span 为触发器；is_cli = platform=="vibe-cli" ∨ source=="cli"，复刻 `tool_call_bridge.py:437` [inspected]）：

| 归因 | n |
|---|---|
| hook 触发（合法） | **409**（其中夹心样本——候选集含 ≥1 个 CLI——31 条） |
| CLI 触发形态（违规/幻影） | **0** |
| 无后继（不可复核） | **0** |

**幻影绝对计数 = 0/409 ✓**。基线对照：8-24（修复前）新增 outcome 55/55 全是 CLI 幻影；t24h 139/139 全 hook；一周 409/409 全 hook——CLI 幻影通道在整周持续为零。

### A.4 占比验收：与 moved_on/expired 同量级 [executed]

- reask 家族 409（55.8%）vs expired 家族 183（25.0%）→ **2.2×，同量级 ✓**
- reask 家族 409（55.8%）vs moved_on 家族 59（8.0%）→ **6.9×，同数量级但未达平价 ✗（严格平价口径下）**
- 对照修复前：8-24 新增 55/55 = 100% reask → 现显著下降。

### A.5 残余 reask 构成定性（新发现，正交机制）[executed]

409 行触发器的时序/来源结构：Δt p10=1s / **p50=3s** / p90=8s / max≈22.4h；<60s 占 386/409；**397/409 触发器与行 span 同 session**。这不是真人重问（真人重问基线 p50≈24h、跨 session），而是**同一 prompt 在同一会话内被两套 hook 各路由一次**：

| 行平台 → 触发器平台 | n |
|---|---|
| grok-build → claude-code | **305** |
| claude-code → claude-code | 74 |
| claude-code → grok-build | 23 |
| claude-code → kimi-cli | 6 |
| generic → generic | 1 |

即 cmspark 的 grok 环境**同时活跃 grok 原生 hook 与 claude 兼容通道 hook**，每次 prompt 双发（间隔 ~5s），后者把前者判成 reask。重复 query 聚簇佐证：top-12 task 只占 22%（"继续"×24、"对"×17 等），说明是机制性双发而非少数 query 反复。

### A.6 A 结论

- gate42 的修复对象（CLI 触发幻影）**全周零复发**，硬验收过。
- "reask 占比降到与 moved_on/expired 同量级"：对 expired 达成（2.2×）、对 moved_on 未达平价（6.9×）；未达部分由 A.5 的跨平台双发机制驱动，与 gate42 改动无关（gate42 只收窄触发器来源，双发的触发器是 hook span，属合法证据）。
- **不构成回滚条件**（回滚只会复活 CLI 幻影通道，严格更差）。建议：把「grok 原生 hook × claude 兼容通道双发去重」列为后续 gate 候选（与 gate33/41 的层互斥是不同层面的重复注册）。

---

## B. gate43 T+7 回声对验收

### B.0 口径锁定（9-7 复检沿用）[executed 反推 + inspected 复核]

原始 lane 测量脚本未归档；本次以数据反推复刻，两项基线均精确复现，据此锁定：

- **route span**：span_kind=="task" ∧ name 以 `route:` 开头（复刻 `_load_route_spans`/`_as_route_span`，`tool_call_bridge.py:406-441` [inspected]）。
- **对（pair）**：同 task_id 的 (hook span h, cli span c)，c.ts > h.ts，**全组合**（每个 h×c 组合计 1 对）；对的时间锚 = c.ts（CLI span）。
- **宽口径** = 全部对（复现：快照锚 ≤ 8-24T00:00Z 时 611 对 ÷ 30.05 天 = **20.33/天** ≈ 钉死 20.4；Δt p50 = **17.9s 精确复现**）。
- **回声口径（验收口径）** = h.has_match==True ∧ Δt ≤ 90s（复现：同快照 431 对 ÷ 30.05 = **14.34/天** ≈ 钉死 14.4，差 0.4%；60s/90s 阈值在快照端点漂移下 bracket 14.4 [13.81, 15.34]，取 90s）。
- 基线窗 = 锚 ≤ `2026-08-24T00:00Z`（eod23 快照），分母 30.05 天（613/20.4 镜像）。
- T+7 窗 = 锚 ∈ (`2026-08-24T10:42Z`, `2026-08-31T10:42Z`]，分母 7 天。

### B.1 主指标 [executed]

| 口径 | 基线 | T+7 | 降幅 |
|---|---|---|---|
| **回声口径（验收）** | 431 对 = **14.34/天**（钉死 14.4） | **25 对 = 3.57/天** | **−75.1%（对复算基线）/ −75.2%（对钉死 14.4）** |
| 宽口径（对照） | 611 对 = 20.33/天 | 58 对 = 8.29/天 | −59.2% |
| 14 天滚动（构成对齐） | (T0−14d, T0] 253 对 = 18.07/天 | 3.57/天 | −80.2% |

- 硬验收①：方向性下降 ≥25% → **75.2% ✓**（stretch ≥50% 亦 ✓）
- 硬验收②：CI 不含 0 → T+7 观测 25 对，基线下期望 100.4 对；精确 Poisson 95% CI **[16.2, 36.9] 对 = [2.31, 5.27]/天**，基线 14.34/14.4 整体在区间外 → **显著 ✓**（单侧 p = 2.4e-19）
- T+7 回声对按日：08-25=10、08-26=5、08-27=3、08-28=7、08-29..31=**0**；Δt p50 28.9s（基线宽口径 17.9s → 变慢）。
- 工作日/周末构成：T+7 含 2 个完整周末日（2/7=28.6%）；基线 30d ≈30%、pre-14d 28.6% → **对齐 ✓**，无需改 14 天滚动为主口径（滚动值已列作稳健性）。

### B.2 归因对照（防假阳性）[executed]

1. **hook 无故障**：hook route span 量 118.3/天（基线 30d）→ 109.6/天（T+7，含完整周末）；**单发 hook span**（无同 task CLI 后继 ≤90s）100.0/天 → **102.3/天，稳定 ✓**。CLI route span 15.3/天 → 5.6/天（下降集中在回声类，见③）。
2. **模板祈使形态占比确实下降 ✓**（双指标）：
   - hook_hit∧≤90s 对（文案针对的"已注入仍重跑"类）14.34 → 3.57/天（−75%）；hook_miss∧≤90s 对（no-match 后复查类）3.99 → 3.71/天（基本不变）——下降精确落在文案目标类。
   - echo 族内 fast（≤30s）占比 82% → 61%；族内 Δt p50 16.6s → 23.8s——残余对变慢、更偏人形。
3. gate41/42 滞后效应排除：两 gate 只改 outcome 派生谓词，不改 span 生成；本指标在 span 层面测量，机制上不受其影响 [inspected]。

### B.3 gate17 护栏 [executed]

CLI miss span 分解（has_match==False 的 CLI span；divergent = 前继 hook 命中 ∧ Δt≤300s；slow = 前继 hook 但 Δt>300s；cli_only = 无前继 hook）：

| 窗 | n | fast_echo | divergent | slow | cli_only | 真人类残量（slow+cli_only） |
|---|---|---|---|---|---|---|
| 基线（eod23，30.05d） | 60 | 22 | 28 | 9 | 1 | 10（0.33/天）✓ 对上 lane "~10 条/33 天" |
| T+7 | 11 | 8 | **0** | 1 | 2 | 3（0.43/天） |

- 护栏①：真人 CLI miss 残量**未同步消失**（3 条 > 0）✓
- 护栏②：新增 divergent 伪 miss = **0** ✓

### B.4 第四观察项：instrumentation 入流体积 [executed]

| 类别 | 基线 30d | pre-14d | T+7 |
|---|---|---|---|
| route span | 137.5/天 | 142.7/天 | **139.6/天（稳定）** |
| tool span | 694/天 | 1490/天 | **8745/天（×12.6）** |
| llm span | 102/天 | 129/天 | 70.9/天 |
| orchestrate span | 37.8/天 | 50.3/天 | 16.3/天 |

- 采集无故障：route 入流逐日稳定；tool span 自 08-23 起暴涨（工具桥物化上线：08-20=0 → 08-23=10,621），T+7 量升不降。
- llm/orchestrate 下降（−31%/−57%）是 agent 行为面变化（更少编排/子代理流），与回声对下降同向、互不构成采集故障误读。

### B.5 B 结论

**PASS**：硬验收两条（≥25% 降幅；CI 不含 0）全部满足且大幅富余（−75.2%，p=2.4e-19），stretch ≥50% 亦过；归因对照与护栏全绿（hook 健康、下降落在文案目标类、divergent=0、真人残量保留）；宽口径与 14 天滚动两个稳健性口径同向。无回滚建议。9-7 做 T+14 复检：验证**不回升**（口径按 §B.0 锁定值），并对 A.5 双发机制决定是否立项。

---

## 证据分级汇总

- [executed]：本文全部对 `~/Projects/cmspark/.vibe/observability/` 两文件的直接计算（脚本为一次性只读分析，未落仓）。
- [inspected]：is_cli/解析口径复刻自 `tool_call_bridge.py:406-441`（§A.3/B.0）；gate41/42 对 span 层零影响的机制判断（§B.2③）；A.2 的 −1 异常定性。
- [assumed]：钉死基线 14.4/20.4 的原始 lane 快照端点（8-24 00:00Z–10:42Z 之间）无法精确复原——已用 20.33/14.34 + p50 17.9s 的复现收敛其漂移 ≤0.5%；对验收判定无影响（−75% 远离任何阈值线）。

## 9-7 T+14 复检清单

1. 沿用 §B.0 锁定口径；回声对/天在 (T+7, T+14] 窗应 **≤3.57/天量级、不回升向 14.4**。
2. gate42 侧：重跑 A.1–A.3（新增行会因派生滞后继续增长），幻影绝对计数必须仍为 0。
3. 检查 A.5 双发机制是否已立项处理；若未处理，重测 grok-build→claude-code 对计数作趋势基线（本周 305）。
4. 本文件为比对基准：T+14 报告须并列本表数字。
