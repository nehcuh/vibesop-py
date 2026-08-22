# Gate34 Lane B 架构评审：D1–D4 可行性、路线与排序

调查范围：已通读 `src/vibesop/core/observability/skill_promote.py`（全文 2289 行）、`clustering.py`、`gold_detection.py`、`tool_call_bridge.py`、`discovery.py`、`span_writer.py`、`dashboard/_discoveries.py`、`scripts/replay_routing_baseline.py`、`scripts/measure_index_embedding_shift.py`、`scripts/calibrate_behavior_threshold.py`、`tests/conftest.py`、`skill_commands.py` promote/activate 段、`indexer.py:455`、`triage_recall.py:206`。未运行任何测试（只读代理）。

## 关键事实先行（评审前提）

- `_is_agent_prompt_shape` 位于 `src/vibesop/core/observability/skill_promote.py:366`，单一真源，`scripts/replay_routing_baseline.py:52` 刻意 import 复用。**注意它内含 150 字符上限**（`_AGENT_PROMPT_MAX_LEN`，skill_promote.py:363）——这对 D2 是重大陷阱。
- miss 池 intake 在 `skill_promote.py:1429-1433`：`is_route_miss_span(s) and not _is_low_information_query(...)`，**目前没有形状过滤**。
- promote 流程：`skill_commands.py` `promote_cmd`（materialize 在 1959 行，store.promote 在 1967 行）→ `_activate_promoted_draft`（2024 行，guard chain：draft 存在 → draft_sha256 编辑守卫 → global 隐私确认 → 注册）。
- spans 写入唯一收口是 `SpanWriter._locked_append`（`span_writer.py:110`），被 tracer（2 处）、tool_call_bridge、recall/pool CLI 共用；POSIX fcntl 内联，被 `tests/benchmark/test_span_emit_overhead.py::test_enabled_tracer_under_100us_p95` 的 **100µs p95** 门禁卡住。
- spans.jsonl **没有轮转机制**（tool_sequences.jsonl 有单轮转，spans 是无限 append）。
- 全局 embedding stub（tests/conftest.py:281）把 `sentence_transformers` 置 None，一切走 fail-open；测试禁内建 `hash()`。
- 分源字段已存在：`ClusterCandidate.source ∈ {gold, miss_recurrence}`，miss 路**已经有自己独立的准入门**（`miss_cosine_threshold`/`miss_min_pairs`/`miss_min_days`）——D3 的"分源阈值"其实部分已存在。

## D1 — Promote verifier 通道：可行，复杂度中等，建议先 shadow 后 gate

### 接入点与数据流

1. **触发侧**：`replay_routing_baseline.py` 的 `build_trigger_index` + `p0_shadow` + `build_hit_hijack_risks`（139–275 行）已经就是"捕获率 + 误劫持率"的离线实现，只是目前面向存量技能全集。把它改造成可接收"额外一个草稿技能"的参数即可（`skills` dict 注入 draft）。
2. **embedding 侧**：两条线必须分开测，尊重双 embedding 分离铁律——recall 预筛：`EmbeddingRecall._candidate_text`（triage_recall.py:206，floor 0.25）；index 0.45 门：`indexer._compute_profile_text`（indexer.py:455）+ `measure_index_embedding_shift.py` 的 per-query top-1/margin 逻辑（margin 极脆：0.071 vs 0.0702）。
3. **挂载点**：`promote_cmd` 在 `store.promote`（skill_commands.py:1967）之后跑 `verify_draft(candidate, skill_path, project_root)`；结果落 `.vibe/observability/promote_verdicts.jsonl`（新 store，fcntl+threading.Lock 双锁 + 坏行跳过，照抄 `DiscoverySignalStore` 风格）。`_activate_promoted_draft` 的 guard chain 里加一环：读该 cluster_id + 当前 draft hash 的最新 verdict，FAIL 时拒绝（`--force` 可绕过但打印 verdict 摘要）。
4. **上看板**：`dashboard/_discoveries.py` 是只读 read-model。**卡片只来自 `list_pending`，promoted 行从看板消失**，所以 FAIL 不能挂在卡片上，得在 payload 加独立 `verdicts` 段（按 cluster_id 平铺，看板渲染成"待处理裁决"区）。

### 会破坏什么 / 不会破坏什么

- 不动 upsert 语义、不动 store schema（新文件，不动 ClusterCandidate 字段）→ gate30 语义零风险。
- **e2e 风险**：verifier 的 embedding 侧在 docker 镜像里模型不可用，必须像 `load_embedding_model`（replay 脚本 297 行）一样失败即降级（verdict 标 `embedding: unavailable`，触发侧仍出结论），否则 `e2e_command_smoke.py` 65/65 会红。测试同理：stub 下 embedding 侧 unavailable，只钉触发侧与降级路径。
- **口径建议**：PASS/FAIL 阈值第一版只做 report-only（shadow verdict 上看板不挡 activate），跑 2–4 周攒 verdict 分布后再固化阈值——复用 gate32 "只记录不动路由"哲学。

## D2 — 子代理轨迹去重：方向正确，但谓词直接复用会误伤，需要先拆分

### (a) intake 形状过滤

在 `skill_promote.py:1429` 的 miss_spans 推导上加形状过滤。**陷阱**：该谓词把**任何 >150 字符的 query 判 True**（150 上限是为"草稿 trigger 预填"设计的；在 pool intake 误杀意味着长 query 永远进不了候选池，是数据丢失方向）。真实用户长指令（粘贴 traceback、长需求描述）在 miss 池里是合法成员。**路线**：把谓词拆成两个——`_has_agent_prompt_prefix`（前缀黑名单，可安全用于 intake）与长度规则（留在预填侧）；或者 intake 侧用更高长度上限（如 500）。动手前先在真实 spans 上量一下 ">150 字符且非 agent 形状" 的 miss 占比，用数据定拆分点。谓词演进只改 skill_promote.py 一处的单一真源惯例必须保持（replay 脚本 import 它）。

### (b) Jaccard>0.8 近重复折叠

**不要动 `clustering.py`**。cluster_id = sha1 of sorted (project_id, task_id)，在聚类层折叠会改变 cluster_id → 池内 pending 行漂移。overlap-merge（Jaccard>0.5）大概率能吸收，但折叠后集合同比缩小，Jaccard 可能跌破 0.5 → 新旧行并存（旧行 30 天 TTL 自愈，可接受但要记录）。**正确挂载点是 `scan_candidates` 的候选构造层**（skill_promote.py:1521 附近）：

- 新增 `_fold_near_duplicate_queries(task_keys, queries, threshold=0.8)`，token 集 Jaccard（纯文本，不吃 embedding——conftest 的 stub 下可测）；
- 折叠后 **gold_rate 按去重后成员重算**（gold_task_ids 与保留集求交 / 保留集大小），`task_ids`/`queries` 存保留集（保证 `find_all_overlapping_pending` 守卫看到的集与展示集一致），`span_count` 保留原始值 + 新增可选字段 `dedup_folded_count: int | None = None` 做审计；
- `ClusterCandidate.from_dict` 对缺键老行容忍（新字段给默认值），round-trip 测试加一条；
- **不改** `gold_detection.assess_gold_status`——它服务 Cluster 层，改它会波及 W1 is_gold 口径。

### 不变量核查

- upsert 匹配集（exact-id ∪ 同类 Jaccard>0.5）、terminal 不粘、unstable 不经 overlap 阻挡但 exact-id 挡——全部不动，零接触。
- `cluster_fingerprint`（discovery.py:107）输入变为去重后 queries → dismiss 指纹变化，已记录的 dismiss 可能"漏粘"——该模块已显式接受的失败模式（docstring 在案），不是新问题。
- miss 谓词分歧（`is_route_miss_span` vs `_is_miss`）：本方案两者都不改。

## D3 — 分源阈值：技术上琐碎，但被数据和外部触发器卡死

### 实施路线

1. **测量脚本**（新增 `scripts/measure_promote_success_by_source.py`）：join `cluster_candidates.jsonl` 的 promoted 行 × `count_skill_route_hits`（discovery.py:550，阈值 `HISTORY_HIT_THRESHOLD=5` 现成）→ 每 source 的 promote→activated→命中≥5 成功率分布。照抄 `calibrate_behavior_threshold.py` 的纪律：分布 + 决策带，样本不足 exit 2 fail-closed。
2. **代码侧改动极小**：miss 路本来就有独立 knobs；gold 路若需细分，`scan_candidates` 的 kwargs 已经是入口。

### 致命约束：统计功效

池子上限 50+20，promote 是稀有事件（dogfood 至今个位数 promote），按 source 分桶后每桶样本量几乎必然落在 "SAMPLE TOO THIN" 区间。叠加挂着的外部触发器（grok hook probe 未过 → M3 不采信 grok 序列；M3 阈值复检未完成），**D3 现在做只能产出"数据不足"的结论**。

## D4 — 不可变路由记录：写时入链方案有硬伤，强烈建议改为离线 sealer

### 写时 hash chain 的正确性/性能分析

- 链需要前一行 hash，而写入是多进程并发——**必须在同一把 flock 内读文件尾再写**，即改 `_locked_append` 为 read-tail+append。多一次 open/read/seek 系统调用，直接顶在 100µs p95 门禁上（span_writer.py:113-120 注释：该路径当年连两次 `import fcntl` 都嫌贵）。
- spans.jsonl 无轮转（目前利好），但一旦未来加轮转，链需要 genesis 标记机制，复杂度继续长在热路径里。

### 推荐架构：离线 sealer（不动热路径）

- 新增 `src/vibesop/core/observability/span_sealer.py`：增量游标（照抄 `tool_call_bridge_state.json` 的 seen-keys/cursor 模式），把 spans.jsonl 的新增行逐条 sha256 并写 `spans.chain.jsonl`：`{seq, span_id, line_sha256, prev_chain_hash}`。文件截断/轮换检测（size < cursor → genesis 新链）。
- `replay_routing_baseline.py` 加 `--verify-chain`：重放 spans.jsonl 逐行重算，与 chain 文件对账，断链/改行/删行三类异常分列。
- **零热路径改动 → 100µs p95 门禁与 6041 测试天然安全**；代价是篡改检测是追溯性的——对"路由记录审计"用途，追溯性证据已经足够。

## 方向间依赖与冲突

- **D2 → D1（强）**：D2 改了 miss 池组成和 gold_rate 分母，D1 的捕获率分母随之变化。先做 D1 再改 D2，D1 攒下的 verdict 分布全部作废。顺序必须 D2 先。
- **D2 → D3（强）**：D3 的分桶成功率以 gold_rate/池口径为自变量，D2 改口径后历史 promote 记录与新口径不可比——强化"D3 等数据"判断。
- **D1 ↔ D4（弱）**：都碰 `replay_routing_baseline.py`，纯 git 层面冲突，语义正交。
- **D2 内部**：intake 过滤的谓词拆分若改 `_is_agent_prompt_shape` 本体，会同时改 replay 基线的分母口径（该脚本 import 同一谓词）——拆分必须保持"原谓词语义不变、新谓词另立"，否则 gate32 基线数据失去可比性。

## 独立优先级排序

**阶段一：D2**——数据卫生是一度元问题，D1/D3 的度量质量都由它决定；改动面小、不吃 embedding（stub 下可测）、不碰任何 gate30 不变量。风险点只有一个（150 字符上限误伤），可先用一次离线测量化解。

**阶段二：D1（shadow 模式）**——复用度最高（trigger 侧逻辑 80% 现成），verdict 先只记录不 gate。等 D2 上线 2 周后的干净数据喂它。

**阶段三：D4（sealer 架构）**——与 D1/D2 完全正交，可随时插入；不 unblock 任何学习闭环，故排第三。坚决不做写时入链版。

**阶段四：D3**——代码量最小但被外部触发器和统计功效双重阻塞。现在启动只能写测量脚本骨架（半小时），阈值固化必须等数据。

一句话：D2 是卫生，D1 是度量，D4 是审计，D3 是决策——决策必须等度量有数据，卫生必须先于度量。

## 残留不确定项

- ">150 字符非 agent 形状 miss 占比"未实测——D2 谓词拆分点依赖这个数据，建议实施第一步先跑这个测量。
- `e2e_command_smoke.py` 65 项是否覆盖 `vibe skill promote`/`scan-candidates` 未逐条核对；D1 挂载 promote 后必须确认 docker 镜像内 verifier 降级路径不红。
- D1 verdict 的 PASS/FAIL 阈值无任何现有数据支撑，shadow 期长度（两周）是拍的，可按 verdict 累积速度调整。
