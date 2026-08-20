验证完成。这是我的 gate15b 确认评审。

---

# Gate 15b 确认评审 — M12 产品设计 v2

## 1. gate15 发现逐项核验

### claude BLOCK-1（聚类前提证伪）— 已解除

- v2 新增 **M0**：`_extract_query` metadata 回退（声明兼容策略）+ 真实 span smoke，出口标准「本项目 spans.jsonl 上 scan 产出含 miss 簇的簇数 > 0」。 fresh 复核代码事实：`_extract_query`（clustering.py:342-367）确实只读 `input_data`、null 即返回 None；两处 emitter（agent_runtime.py:457、main.py:760）确实只把 query 放 metadata。v2 引用的 169/75/0/0 数字与我 gate15 实测逐字一致。
- 出口标准放在 M0 比我原建议的 M2 更早、更严（M0 不通过则 M1/M2 不开工）。这是对齐 v3 Phase A rebuild_dag 真实数据 smoke 先例的正确形态。**解除成立**。

### claude BLOCK-2（捕获通道零产出 + 静默吞错）— 已解除

M1 范围明确含「失败不吞 + last-capture 时间戳」，出口标准「dogfood 中 tool_sequences 真实产出 + join 命中率 > 0」；卡片呈现「捕获年龄」（用户旅程 3）。静默空转的头号风险在 M0/M1/M2 三层都有真实数据关卡。**解除成立**。

### claude nits（9 项）

| Nit | v2 处置 | 核验 |
|---|---|---|
| gold 门表述 | 「unstable 桶、进不了人审可见的 stable 候选」 | ✓ 准确 |
| cursor 争用 | 单读者扇出到双消费者 | ✓ 且可行——`assemble_tool_sequences`（tool_sequences.py:113）本就是唯一推进 cursor 的读者、内部已喂 `learner.record_sequence`（:161），桥挂同一读者即可 |
| 重问 join 键 | span 内 task_id，弃 query_hash | ✓ task_id 在两条路径都是 span 字段（agent_runtime.py:454、main.py:758），全文派生无损；重问降为弱负（兼收 pi 谨慎意见） |
| 隐私「只存工具名」 | 已改，明说 v1 是文字漂移 | ✓ |
| knob 归属 | 模块常量 + CLI flag，未来 DiscoveryConfig | ✓ |
| 准入单位定义 | 见 §3 —— **处置有误** | ✗ |
| 0.82 标定 | calibrate 纪律 + 30-50 标注 miss 对 | ✓ |
| 14 天冷却 | 恢复（不再提示、看板可见） | ✓ |
| --history 精度指标 + M11 池承认 | 均在 | ✓ |

### pi 发现

- **#1 join 键**：M1 含 route hook session_id 前向修复或时间窗 join + 歧义拒挂，CLI 路径明确排除。✓（且「claude-code 路径 join 成立」没有被当作已成立的事实用——join 命中率 > 0 本身就是 M1 出口标准，断言被关卡包住，这是正确姿态。）
- **#2 miss 源**：直接读 spans 的 has_match。fresh 核验 core/models.py:217-219 确认 `has_match` 排除 `FALLBACK_LLM`；agent 路径 span 在 agent_runtime.py:593-597 富化 skill_id/mode/confidence/has_match。✓（一个残留见 Nit-B。）
- **#3 --activate 矛盾**：编辑守卫或 --force；看板只读、变更 CLI-only。✓ 采纳 pi 建议。
- **#4 评测**：标定语料 + promoted/(promoted+dismissed) + route-hit≥5 闭环 ✓；但 pi 的 (a) **同日/跨日 synthetic injection test 被丢了**（见 §3，这个丢失和下面的数学错误直接相关）。
- **#5-#10**：50MB 轮转 ✓（并纠正 TTL/留存混淆）、200/500 截断纠正 ✓（orchestrator.py:49 vs :80 印证）、[XP]-or-force ✓、--mute/evidence_score 排序/--history 恢复 ✓、M11 池构成承认 + 熔断绑定 ✓、embedding 成本 --days/--limit + EmbeddingCache ✓。
- **pi §5 冷启动**（成性预期/回填）：**文档里没有**。grep 全文无冷启动/回填/backfill 相关表述。这是确认评审简报与文档之间的出入——简报声称已加、实际未加。属 pi 叙述性观察而非编号 nit，不构成 verdict 违约，但需补一句话或修正变更摘要。

## 2. 特别关注：静默空转防线是否足够

**足够。** M0（真实 span scan >0 簇含 miss 簇）→ M1（dogfood 真实产出 + join 命中 >0 + 失败不吞 + last-capture）→ M2（可 demo 闭环 + 标定），三层真实数据关卡；运行期衰减由捕获年龄信号覆盖。我逐条找了「仍被断言为 works 但未在真实数据上验证」的项：唯一候选是 join 本身（尚无 tool_call span 存在、join 从未端到端跑过），但 v2 把它做成了 M1 出口标准而非既成事实——断言被关卡包住，不违规。M4/M5 无显式出口但骑在 M2 非空队列上，可接受。

## 3. 新引入的矛盾（阻断项）

**准入闸门的数学断言为假，且静默删除了 v1 自称的核心闸门。**

阈值哲学写：「准入：distinct (task_key, 自然日) 对 ≥ 3（**跨 ≥2 自然日蕴含其中**）」。这个蕴含关系**不成立**：3 个不同 task_key 落在同一天 → 3 个 distinct 对、仅 1 个自然日。反例恰是最常见的真实场景——**一个下午的迭代式改写**（同一需求的 3 次语义相似但字面不同的 miss query）即满足字面准入，零跨日确认。v1 把「跨 ≥2 自然日」称为「**反一次性需求的核心闸门**」；v2 的操作性规则（数据流与阈值两处均只写 pair 计数，从未把 ≥2 日写成合取条件）把它删掉了，再用一个假蕴含宣称它还在。文档内部自相矛盾：风险 #2 的缓解措施写「distinct-day 闸门」，而操作性定义提供的闸门不覆盖 distinct-key 同日爆发。「防同日刷量」只防同一 task_key 重复，防不了同日多 key。

这是对 gate15 nit #6 的错误处置——我提 pair 计数是为了解决「去重 vs 跨日同句复现」的张力、预期与 2 日闸门**并用**，v2 把它变成了替代品并宣称等价。此类设计文档中的数学-逻辑错误在本仓库评审纪律下是 P0 级（先例：task-memory v2 的互斥设计被 grok+pi 独立抓出）。若照字面实现，误报疲劳（设计自己列的 #2 风险）直接兑现。修复是一行：**≥3 distinct pairs 且 spanning ≥2 distinct days（合取）**。pi 的同日/跨日 synthetic injection test（被 v2 丢掉的 eval (a)）本可抓住它——两个残留相互印证，应一并恢复。

## 4. Nits（非阻断）

- **Nit-A（即 §3 的修复伴随项）**：恢复同日/跨日 synthetic injection tests 作为 M2 验收的一部分。
- **Nit-B**：「route span metadata 已有 has_match/skill_id/confidence」是 agent 路径事实的 blanket 表述——CLI 路径 span（main.py:759-764）metadata 只有 query/platform/mode/source，错误路径 span（agent_runtime.py:575 提前 return）不经富化，pre-W5.0 老 span 也没有。scan 的 miss 过滤需声明 has_match 缺失时的处理（建议：视为 unknown、不进 miss 池，保守方向）。
- **Nit-C**：准入的 task_key 在 M0 修复后将从 **200 字符截断后**的 metadata query 派生，而重问检测的 task_id 是全文派生——同一管道里「同 query」有两种派生。长 prompt 共享 >200 字符前缀会碰撞（本仓库 gate-review 长提示词正是高危形态；方向上是 undercount、保守可接受）。更干净的方案：准入直接复用 span 上已有的全文派生 task_id 计 distinct，与重问检测统一。标定语料也应基于管道实际看到的截断文本。
- **Nit-D**：pi 的「ScanSummary 加 layer-share 分布（上线前后）」只被部分采纳（熔断绑定了池构成变化，但无层份额监控）。
- **Nit-E**：冷启动预期/回填一句话缺失（简报与文档不一致，二者取其一修正）。

## 裁定理由

两处 gate15 阻断项都以真实数据出口标准的形式正确解除，静默空转防线完整，pi 全部编号 nit 与我从 A 捡回的项均已落地，代码事实引用经 fresh 复核全部准确。但修订在解决「准入单位」nit 时引入了一个新的数学-逻辑矛盾：操作性规则静默删除 v1 的跨日核心闸门、括注断言一个不成立的蕴含定理，文档内部（风险 #2 缓解 vs 操作性定义）自相矛盾。修复成本一行，方向不动摇——与 gate15 同一处理原则：设计文本不得携带假断言进入实施。

**阻断项（1 项）：**

- **BLOCK**：准入闸门改为合取——distinct (task_key, 自然日) 对 ≥3 **且** 跨 ≥2 自然日；删除「蕴含其中」的假断言；同步恢复同日/跨日 synthetic injection tests（Nit-A）作为该闸门的验收手段。

`VERDICT: BLOCK`
