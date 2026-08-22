文件写入需要授权（评审全文如下，若拒绝写文件则以本回复为准）。

---

# Gate 32 v2 评审 — claude

**结论：PASS_WITH_NITS**（附 4 项 MAJOR must-fix，均为规格缺口而非方向错误）

**分歧点裁决：P0 等触发条件（数据闭环派胜）——但触发条件本身必须先修，否则“等”=“永不做”。**

## 一、机制事实核实（全部实读代码）

| v2 声称 | 核实 | 证据 |
|---|---|---|
| S1 两套 embedding 系统 | ✅ 终于说对 | 系统 A：`triage_recall.py:51` floor=0.25、`:206-216` _candidate_text 含 **triggers**；系统 B：`indexer.py:419-426` _compute_profile_text = scenarios+query_patterns+confidence_boosters+differentiation，**无 triggers**；0.45 门 `_layers.py:452` + margin 门 `:473`。同一 MiniLM（`triage_recall.py:38`/`indexer.py:438`），不同文本/缓存/阈值/角色。v1 确实混了；B2“分开改分开标定”是正确推论 |
| S2 P0 不是新层 | ✅ | `triage_service.py:541-566` 归一化 containment；`unified.py:660` Layer 0.6、0.95 置信（`:985`）、限 guarded（`:491-498`）；scenario/index 并行 best-of（`:877-914`）；scenario 命中降级为 triage 仲裁候选（`:691-714`） |
| S3 错命中不留痕 | ✅ | `routing_pending.py:506` = {levenshtein, custom, fallback_llm}；semantic_index/scenario/guarded-explicit 全不在弱层集 |
| 渲染器不写 triggers | ✅ | `skill_promote.py:1876-1960`；global 省略 example queries（M12 M5，`:1931-1935`） |
| idf.py 只读 4 字段 / IDFTable 现成 | ✅ | `idf.py:370-386`、`:389-408` pool 归一化 (0,1] |
| is_route_miss_span 存在 | ✅ | `gold_detection.py:108` |
| 回放数字（3787/377/245、64%、113/7、79 字符截断） | ⚠️ [assumed] | 代码外分析，无法独立核实；v2 自标 S5 并用 A3 修——自洽 |

## 二、Findings

**MAJOR-1 — A1×B4 次序倒置：本 gate 就在消费 B4 要过滤的垃圾。** `skill_promote.py:1392` 入池只有 `_is_low_information_query`（`:250-280`，滤空内容/相位词/选项回复），**不滤 agent 提示词形状**。B4 自己承认要加（>150 字符、`ou are `、system-reminder 前缀）却推迟独立 gate，而 A1 本 gate 就把簇内 query 写进 triggers + query_patterns（后者直接进 embedding 文本）。64% miss 是 agent 提示词——不过滤 = 给垃圾贴金。修复便宜：3 个谓词折进 A1 样本选择，同 gate 吸收。

**MAJOR-2 — A1 的 query_patterns 注入载体未指定。** profile 是 LLM build 时生成（`indexer.py:39-52`），SkillProfile 无 triggers 字段。(a) 改 LLM prompt → 全池 content_hash 失效全量重 LLM vs (b) build 时从 frontmatter post-merge（cached-hit 路径 `indexer.py:296-303` 也得补 stamp），成本迥异，推荐 (b)。附带不对称：global triggers 是 TODO 占位 → global 技能 query_patterns 注入**天然不发生**——“杠杆率最高的一行”对 global 半边无效，必须写明。

**MAJOR-3 — M7 F3 已裁决先例未回应。** `skill_promote.py:1913-1921`：name/description 刻意中性化，因为“raw query 做 routing-match magnet 会让未编辑草稿一注入就 over-match”。A1 把簇内原话写进**未编辑草稿**的 triggers——正是 F3 防的风险族，且 verbatim containment 语义强度高于 name 的 token containment。v2 全文未提。必须二选一：继承 fail-safe（triggers 首次人工编辑前不生效）或显式 override 给理由。另：v1 的“编辑守卫(content-hash)”在 src 中无对应机制，v2 静默丢弃了该安全前提且无替换物。

**MAJOR-4 — B1 触发条件不可达（裁决的硬前置）。** A1 只给新 promote 草稿预填；存量 113 技能（7 个有 triggers）无任何 backfill 路径。“覆盖率 >60%”可见未来不可达；“仍 miss 的 query 数 >0”平凡真。修：分母改“复现 miss 涉及的技能”或补 top-N backfill；>0 改有意义下限；加硬性复评日期。

**NIT-1** — “确定性层没人消费 triggers”过强：TF-IDF matcher（`strategies.py:527-557`）、relevance 评分（`unified.py:452-484`）、recall embed（`triage_recall.py:212`）、LLM prompt（`triage_service.py:271-273`）都在消费。准确说法是“无 phrase-level verbatim containment 消费者”。后果双向：A1 杠杆更大，且 over-match 风险 P0 之前就存在——**A3 精度指标必须同样 gate A1**。
**NIT-2** — A3 剔除截断 span 对精度估计偏乐观：containment 劫持恰发生在长 query（截断重灾区）。剔除对收益估计 OK，精度估计必须含或单独处理长 query 群体。
**NIT-3** — A2 非“一行级”（SkillProfile 加字段 + to_dict/from_dict + 双路径 population），但 `_compute_embeddings` 每次 build 全量重算（`:348-352`），我专门查过的“cached 旧 embedding 静默 no-op”陷阱不成立。
**NIT-4** — triggers 需逐条 `_sanitize_yaml_value`；空白折叠破坏 substring 语义（containment 只归一 case/apostrophe）；建议 ≤40 字符上限。
**NIT-5** — 重叠簇（gate30 overlap-merge 证明存在）→ 两技能 query_patterns 收敛 → margin 收缩双弃权。分布移动是“大概率”非“视情况”；A3 的 identity-diff + 抽样裁决应写成 A1/A2 **验收关卡**而非仅度量。
**NIT-6** — semantic_index 不在 _WEAK_MATCH_LAYERS：S3 对 P0 的批评同样适用于 A1/A2 放大的 0.45 层，gate 后无持续观测；identity-diff 宜常驻 instinct loop。
**NIT-7** — 假性吸收残留：triggers 接住“新技能萌芽”的相邻 query；建议 A1 样本仅取 gold 簇（W1 assess_gold_status 现成）切断错误 hit 自增强。

## 三、分歧点裁决：P0 等数据（修正触发条件后）

1. **混杂**：A1/A2 改语义层输入、P0 加 0.95 新层，同 gate 无法归因精度回归，违背 v2 自己的 A3 原则。
2. **收益不腐烂**：miss_recurrence 跨日复现 = 人群存活到下 gate，等有界。
3. **成本结构**：P0-lite 真实成本在护栏集，B1 自要求“观察至少一个周期”——时序要求天然反对同 gate 并行。
4. **循环论证**：245 产自 v2 自己宣布失真的基线（S5）。

反向制衡：不修 MAJOR-4 则“等”退化为设计性否决——245 是用现有 triggers 测出的真实价值，不该被不可达门槛永久埋葬。

**证据等级**：file:line 结论 [executed/inspected]；回放统计 [assumed]。
