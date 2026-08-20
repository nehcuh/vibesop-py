执行验证完成 —— 75 个真实路由 span，0 个可提取查询，0 个聚类。这是决定性的发现。以下是评审意见。

---

# Gate 15 评审报告 — M12 产品设计（对话中语义洞察 → 技能发现）

## 1. 裁定正确性：行为采集为核心 — 裁定成立，但论据需修正两处

**结论：裁定本身成立，且最强的论据其实是需求保真而非结构断点。** 用户需求原文「处理方式类似 → 归结为完整工作流」使行为数据成为定义性需求，这一条独立于任何代码事实就足以驳回 A 的「v1 不采行为」。

两条引用的事实核验结果：

- **PostToolUse 捕获「已上线」**：代码层面属实 `[inspected]` — `claude_code.py:393-402` 注册 settings、`:655-675` 安装 hook、`_sequences_enabled()` 默认 true、模板把完整 payload 喂给 `vibe sequence record-tool`（CLI 存在于 `sequence_cmd.py:47`）→ `.vibe/tool_sequences.jsonl`。**但运行层面不成立** `[executed]`：本仓库（旗舰 dogfood 项目）`.vibe/` 下**不存在** `tool_sequences.jsonl`——hook 代码数周前已 ship、`.vibe/dist/claude-code/hooks/vibesop-tool-seq.sh` 已渲染，却在重度假使用中产出为零。hook 模板 `>/dev/null 2>&1 || true` 吞掉一切失败，通道静默死亡无人知晓。「缺的不是采集而是桥」这句话在代码上为真、在数据上未证实。
- **gold 门结构断点**：方向正确、表述不精确 `[inspected]`。`scan_candidates`（skill_promote.py:776-788）对纯 miss 簇（gold_rate=0.0，`gold_detection.py:72/96` 证实无 gold 时为 0.0）并不是「永远成不了候选」——`0.0 < 0.30` 会落入 **unstable 桶**并被 upsert；但 `list_pending()` 默认只返回 stable（skill_promote.py:334-348），admit-only-if-better 按 gold_rate 驱逐低值行。精确表述应为「永远进不了**人审可见、可提升**的 stable 候选」。结论不受影响。

**合成是否丢了有价值的东西**：A 的信任优先/零打扰/一次性提示/粘性 dismiss 全部保留；诚实降级（两路共识）保留。丢了一样值得捡回的：**A 的「14 天无新增成员自动降档冷却」**（CLI 不再提示、看板可见）。合成的风险清单只有 TTL 30 天，没有冷却档——陈旧候选会持续占提示位。便宜且杀噪音，建议恢复。

## 2. 数据流可行性：架构对，但「复用 clustering.py 直接可用」被实测证伪

**阻断性问题 #1（核心）**：M2 的前提「miss query 已产生 route: span → clustering.py 直接可用」在本仓库真实数据上**不成立** `[executed]`：

```
uv run python: SpanWriter().query_recent(limit=300)
→ 169 spans, 75 route spans
→ _extract_query 可提取 query 数: 0
→ cluster_queries(spans) 簇数: 0
```

根因：`_extract_query`（clustering.py:342-367）**只读 `input_data`**，而两处 route span 生产方（agent_runtime.py:452-457、cli/main.py:755-764）都只把 query 放进 `metadata`（JSON 字符串）和 span name，`input_data` 恒为 null。佐证：两个 span 文件中 `"input_data": {"query"` 计数均为 0；`.vibe/observability/` 下**从未产生过** `cluster_candidates.jsonl`。即 W1-W4 的整条聚类候选链在本项目真实数据上从未跑通——`cluster_queries` 在无 query 可提取时**静默返回 []**（clustering.py:274-275），不报错。探索报告把「hard group 按 (project_id, sha1(query))」列为已核实事实，A、B、合成三层全部继承了这条未兑现的「直接可用」。

这正是本仓库有前科的失败类（v3 addendum 实测 1573 spans 发现 task_id 填充率 0%，W5.0 专门修 instrumentation）。M1+M2 作为「可 demo 的最小闭环」照现设计交付会 demo 出**空队列且无任何报错**——恰是合成用来驳回 A 的那个「名不副实」结局，只是换了一层皮。

修复本身很小（`_extract_query` 加 metadata 回退，或两处 emitter 补 `set_input`，二选一并声明兼容策略），但设计必须把它变成显式里程碑内容 + 真实数据验收（例如「对本项目 spans.jsonl 跑 scan，簇数 > 0 且含 miss 簇」），否则不构成阻断解除。

其余数据流核验均通过 `[inspected]`：
- **join 可行性**：近期 route span 携带真实平台 session UUID（实测样本 `25280df5-…` 等，7/30 的老 span 是 `"default"`，属 W5.0 前遗留）；tool-seq hook payload 同源 session_id。claude-code 路径 join 成立。CLI 路径每次 mint 新 UUID（main.py:745）不参与 join，B 的 R2 风险评估准确。
- **消费者真实**：aggregator.py:173/201（tool_call_distribution、连续 tool_call 分组）、dag_rebuilder.py:384、trace_cmd.py:398；src 无生产方，`SpanKind` 已含 `tool_call`（models.py:21）。`SpanWriter.query_recent`（span_writer.py:156）存在。
- **miss 判定可用**：route span metadata 带 `has_match/skill_id/confidence`（agent_runtime.py:594-597），且 `has_match` 明确排除 FALLBACK_LLM（models.py:217-219）——M2 可纯从 spans 过滤 miss，不需要 join MissCounter。

**阻断性问题 #2（次级，必须进 M1 出口标准）**：见 §1 第一条——claude-code 捕获通道在本仓库产出为零且失败被 hook 静默吞掉。M1 的 spike 只写了 kimi/pi 可行性；必须加上「**验证既有 claude-code 通道在 dogfood 中真实产出数据 + 给出活性信号**」（如 `vibe sequence` 记录 last-capture 时间戳、scan 报告捕获年龄）。否则 M3 行为门永远跑在空文件上，所有候选都是 `behavior_evidence: unavailable`——特性退化为 A 的 v1 却背着 B 的全部复杂度。

**设计未覆盖的交互——cursor 争用**：`assemble_tool_sequences` 会**先推进共享水位再消费**（tool_sequences.py:147），现有消费者是 `InstinctLearner.record_sequence`。B 的桥「按 cursor 水位读新条目」——若共用一个 cursor，两个消费者先到先得、互相饿死（序列模式建议饿死）；若各用 cursor，rotation 时 `_rotate_if_oversized` 只重置主 cursor（tool_sequences.py:107-108）且旧轮转文件会被覆盖，第二 cursor 的语义未定义。需明确「单读者扇出到双消费者」或「per-consumer cursor + rotation 处理」。

## 3. 阈值哲学：方向可辩护，三处欠债

- ≥3 次 / 跨 ≥2 自然日 / cosine 0.82 / bigram-Jaccard 0.5 作为**起点**可辩护，宁缺毋滥的取向与 dismiss 单向收紧的回流是这个特性的正确形态。
- **0.82 的标定债**：0.80 是为「gold 簇吸收 screenshot-adjacent 近邻」标定的（clustering.py:193-195 注释），分布是 near-miss；miss-vs-miss（尤其中文短句 miss 彼此之间）是另一个分布，0.82 = 0.80+0.02 不是标定而是拍脑袋。B 自己引了 M11 `calibrate_index_threshold.py` 惯例给 behavior_sim，却没有给 query 阈值同样的待遇。
- **准入单位未定义**：A 的「归一化 query 全同只计 1 次」与现有 `span_count` 语义冲突（同一句重问 = 同一 task_key，span_count 会堆叠），「≥3 次」到底是 3 个不同 task_key、3 次出现还是 3 个 (task_key, 自然日) 对？按 A 的字面去重，同一句跨 3 天复现——最常见的真实模式——**永远到不了 3**。建议定义为「distinct (task_key, 自然日) 对 ≥3」：既防同日刷量又保留跨日同句复现。
- **M11 交互**：M11 收紧弃权后 FALLBACK_LLM/no-match 池变大（`has_match` 排除 fallback，这些全进 miss 池）。阈值是计数制不是比率制，不会被淹没，且 miss 池的「含金量」 arguably 变高（以前被弱匹配吸收的查询现在如实暴露为 miss）。真正的影响是 scan 时 distinct task_key 增多 → O(n²) cosine 与 embedding 量上升（已有 `--days/--limit` 缓解，EmbeddingCache 本地 MiniLM 持久缓存，成本可接受）。设计值得加一句话承认这个池子构成变化，并把 dismiss 率 >50% 的熔断（已有）明确绑定到「M11 后 miss 池扩大」的观测上。

## 4. 隐私：与既有惯例一致，一处文字漂移

- 实测 span metadata 中 query 已脱敏（`[REDACTED_PATH]` 在真实 span 中出现）——写入侧集中脱敏的惯例在工作。全局草稿剔除示例 query 是相对现状（W4 promote 会附 ≤5 条）的**收紧**，方向正确。全局默认 N 双重确认沿用 W5.2 惯例。
- **文字漂移**：合成写「工具序列只存工具名与**参数 key**（沿用 conversation_import 的隐私惯例）」——但现有 `record_tool_event`（tool_sequences.py:67-90）**只存工具名 + ts + session，不存任何参数 key**，B 的 span schema 也保持 `input_data=None`。行为门（工具名 bigram）不需要参数 key。写宽了实际采集面。应改回「只存工具名」——隐私声明必须与实现逐字对齐，这是本仓库的既有红线风格。

## 5. 范围切割：切割本身正确，最可能的失败模式恰好是静默空转

v1 不做自动正文/自动激活/实时打断/云端，promote 草稿 + 人审闸门零改动（skill_commands.py:1695-1719 实证止步于草稿 + 手动 copy 提示）——切割是对的，防住了「自动技能工厂」。

最可能的失败模式不是噪音而是**空转**：P1（聚类死）+ P2（捕获死）叠加，M1+M2 交付一个永远为空、永不报错的发现队列——用户不会抱怨，特性只是不存在。这比误报疲劳更隐蔽，且现设计的所有阈值/护栏都对此无感。次级气球风险：M4 三管道呈现合一与 M5 activate 状态机（hash 守卫回滚）各自都是不小的工程，若 M1+M2 的空转没先修，会在错误的地基上并行铺开。

## 6. 缺失件

1. **发现质量的可评测方法**（最重要缺失）：设计有基建验收、没有质量验收。建议：(a) 0.82 与 ≥3/≥2-day 走 M11 calibrate 脚本纪律，用 30-50 组人工标注的 dogfood miss 对标定；(b) `--history` 记录 promoted/(promoted+dismissed) 作为发现精度指标（A 的 dismiss 熔断保留为其下界触发器）。
2. **M0 前置里程碑**：修 `_extract_query`/emitter + 真实 span smoke + 捕获通道活性验证——现里程碑表里没有位置安放这些前置事实修复。
3. **重问检测的 join 键**：B 用「同 query_hash 出现于 MissCounter/pending」——routing_pending 的 query_hash 与 MissCounter 的加盐 hash 都是对**全文**做的，而 span metadata query 截断 200 字符，长查询（本仓库大量 gate-review 长提示词）hash 必然失配。改用 span 内 task_id 复现（全文派生、无损）即可，一行决策。
4. **knob 归属矛盾**：合成说「写入 RoutingConfig 惯例的配置 knob」；B §9 明确说不进 RoutingConfig（observability 域，模块常量 + CLI flag，未来入 DiscoveryConfig——skill_promote.py 惯例）。采 B。
5. A 的 14 天冷却降档（见 §1）。

## 逐项回答评审焦点

1. **裁定是否成立**：成立（需求保真是主论据）；gold 门论据表述不精确但不影响结论；A 值得捡回的只有 14 天冷却，B 的兼容性关切全部保留。
2. **数据流是否可行**：架构可行、消费者真实、join 键（claude-code session UUID）实测成立；但聚类复用前提被实测证伪（0/75 spans 可提取），捕获通道实测零产出。
3. **阈值**：起点可辩护；0.82 无标定、准入单位未定义、M11 池膨胀需一句承认 + dismiss 熔断绑定。
4. **隐私**：一致且有收紧；「参数 key」文字漂移必须改。
5. **范围**：切割正确；最可能失败 = 静默空转而非误报疲劳。
6. **缺失**：质量评测方法、M0 前置、重问 join 键、knob 归属、冷却档。

---

## 裁定理由

架构方向、产品哲学、隐私边界、范围切割全部成立，两路对抗的精华都被保留。但设计最核心的可行性断言——「clustering.py 直接可用、只缺装配桥」——在本仓库真实数据上被**执行**证伪（75 个 route spans、0 个可提取 query、0 簇），且既有 claude-code 捕获通道从未产出过任何数据、失败被 hook 静默吞掉。按现设计交付 M1+M2 会得到一个静默为空的发现队列。修复成本很小（一个提取函数 + smoke + 活性验证），但必须作为显式里程碑范围与验收条件进入设计，而不是留给实现时"发现"。

**阻断项（2 项，修复成本低、方向不动摇）：**

- **BLOCK-1**：M2 聚类复用前提被实测证伪。设计必须新增前置范围：修复 query 提取（`_extract_query` metadata 回退或 emitter `set_input`，声明兼容策略），并以「本项目真实 spans.jsonl 上 scan 产出含 miss 簇的簇数 > 0」为 M2 出口标准（对齐 v3 Phase A 用 rebuild_dag 真实数据 smoke 的先例）。
- **BLOCK-2**：claude-code 捕获通道「已上线」仅为代码事实、运行零产出。M1 出口标准必须加入「dogfood 中验证既有通道真实产出 tool_sequences 数据 + 提供捕获活性/年龄信号」，与 kimi/pi spike 并列；否则行为门整条跑空，特性名不副实。

**Nits（修订时一并吸收）**：gold 门表述改为「进不了人审可见的 stable 候选」；cursor 争用明确单读者扇出或 per-consumer cursor；重问检测 join 键改 task_id；隐私文字改「只存工具名」；knob 归属采 B 的 DiscoveryConfig/模块常量；准入单位定义为 distinct (task_key, 自然日) ≥3；0.82 补标定计划；恢复 A 的 14 天冷却；`--history` 增加发现精度指标；承认 M11 后 miss 池构成变化。

判定：阻断（BLOCK）
