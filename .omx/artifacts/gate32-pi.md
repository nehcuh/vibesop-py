Usage: vibe route [OPTIONS] {query}
Try 'vibe route --help' for help.
╭─ Error ──────────────────────────────────────────────────────────────────────╮
│ Got unexpected extra argument(s) (embedding 系统\的归因是否终于说对了） 2.   │
│ 裁决分歧点:P0-lite 本 gate 做（带护栏)vs                                     │
│ 等覆盖率触发条件——给出明确裁决和理由 3. 找 v2 还没看到的洞 4. 评估 A1 把簇内 │
│ query 写入 index profile query_patterns 的副作用面  输出:PASS /              │
│ PASS_WITH_NITS / BLOCK 三档 + findings(BLOCK/MAJOR/NIT 分级,文件:行号+理由)  │
│ + 对分歧点的明确裁决。 # Gate 32 v2 设计提案 — 路由层优化（四路对抗收敛后）  │
│ > 状态：v1                                                                   │
│ 经四路独立对抗（失败模式/用户场景/工程架构/数据闭环）大修。本文档是 >        │
│ claude+pi+grok 三路评审的对象。  ## 对抗评审的收获（四路确认的增益）  1.     │
│ **P2（预填 triggers）是真闭环缺口，四路一致认为是必做项**：渲染器不写        │
│ triggers    （skill_promote.py:1876+），确定性层没人消费                     │
│ triggers(idf.py:370-386 只读    name/description/intent/keywords)——skill     │
│ 作者写的 triggers 至今没有强语义。 2. **cmspark                              │
│ 真实回放证实收益**：用真实技能池 triggers 按 exact+containment 规则回放      │
│ 3787 条 route span,P0 规则可命中 377 span,其中 245 条当时是                  │
│ miss——目标分布真实存在。 3. **\发现断粮\反噬论被否证**:miss_recurrence       │
│ 入场券是跨日复现（≥3 (task,day) 对)——    P0/P2 消化的是\已有技能的反复       │
│ miss\，这类候选只会与现有技能重叠（gate30 做    overlap-merge                │
│ 就是在擦这个屁股），拿走它们是提纯不是断粮。 4. **precision > recall         │
│ 的排序被用户视角确认**：错技能触发会把会话劫持进错误工作流，    而           │
│ fallback_llm 至少正常回答；尤其 miss 流量 64% 是子 agent 提示词，误触发会    │
│ 静默污染子代理行为。  ## 对抗评审发现的负面影响（v1 的病，按严重度）  -      │
│ **S1（三路独立收敛）P1 打错靶子**:0.26 cosine 是对 `_candidate_text`（triage │
│ recall   预筛，floor 0.25，能过）;0.45 是 semantic_index 的                  │
│ `index_embedding_threshold`，其   向量文本来自                               │
│ `indexer._compute_profile_text`(indexer.py:419-426)——embed 的是 LLM          │
│ profile 的 scenarios/query_patterns/confidence_boosters,**spec 的 triggers   │
│ 字段根本不在   里面**。v1 把两套 embedding 系统混为一谈。 - **S2 P0          │
│ 不是新层**:`explicit_guarded_skill_match`(triage_service.py:541）已实现      │
│ 归一化 substring containment → 0.95 置信，只是限定 guarded                   │
│ skills;guarded-explicit   插入点（unified.py:660）已存在。v1 的\新层插在     │
│ scenario 后\与真实结构冲突——   scenario 和 semantic_index 是                 │
│ `_try_early_layers` 并行 best-of，且 scenario 命中强制   triage              │
│ 仲裁（有固定置信误路由前科）。 - **S3 containment                            │
│ 的长度门槛防不住真实误伤**:\adversarial review\(18 字符）会劫持   子代理     │
│ prompt;\先别合并到 main\极性盲区；高置信误命中绕过 routing_pending 人工      │
│ 纠正回路（_WEAK_MATCH_LAYERS 只有                                            │
│ levenshtein/custom/fallback_llm)——错命中不留痕。 - **S4 P0 无数据裸奔**:113  │
│ 技能仅 7 个有 triggers,6% 覆盖率，还有 `<trigger1>` 占位   脏数据。P0        │
│ 的价值完全绑定 P2 或人工维护。 - **S5 验证基线失真**:miss 口径三数不一（433  │
│ vs 650/646/324);span name ~79 字符截断   使长 query 无法忠实回放；metadata   │
│ 偶发非法 JSON;64% miss 是 agent 提示词（本应 miss)。 - **S6                  │
│ 隐私边界冲突**:global 草稿刻意省略示例 query(M12 M5),triggers 预填在 global  │
│ 路径要显式降级，不能静默绕过。  ## v2 提案  ### 本 gate 范围（做）  **A1 —   │
│ 渲染器预填 triggers + query_patterns(P2 强化版）** - `_render_skill_md`      │
│ frontmatter 写 `triggers:`（簇内 query 样本，≤5 条，沿用现有样本）。 -       │
│ global scope:triggers 留 TODO 注释占位（隐私边界显式降级，不静默）。 -       │
│ 同时把簇内 query 写入 index profile 的 `query_patterns`（激活/索引时）——让   │
│ `_compute_profile_text` 的 0.45                                              │
│ 门直接看到真实用户原话。**用户视角评审认为这是全提案                         │
│ 杠杆率最高的一行改动**。  **A2 — P1-lite-c:`_compute_profile_text` 加 spec   │
│ triggers** - profile 文本 = scenarios + query_patterns + confidence_boosters │
│ + differentiation   **+ triggers**。一行级改动，直接修 0.45 层的稀释。 -     │
│ 重建索引后 0.45/margin 阈值视分布决定要不要动（标定集只有 8 个确认正例，     │
│ margin 有 0.071 vs 0.0702 的脆性记录——能不重标就不重标）。  **A3 —           │
│ 验证基线修复（先于一切收益声明）** - miss 口径统一为 `is_route_miss_span`    │
│ 谓词现跑数字； - 回放剔除 ~79 字符截断的 span（或标记不可忠实回放）; -       │
│ 收益度量升级：miss→hit 转化数 + **hit identity diff**(A→B 改判）+            │
│ 抽样人工裁决   正确率 + agent 提示词误触发数（精度回归指标）。  ###          │
│ 明确推迟（记录触发条件，不在本 gate）  **B1 — P0-lite（泛化                  │
│ explicit_guarded_skill_match 到全池）**，带全套护栏： containment 需要 IDF   │
│ 特异性门槛（idf.py IDFTable 现成）而非字符长度；否定词黑名单； 机器负载      │
│ wrapper 剥离；新路径加入 `_WEAK_MATCH_LAYERS` 观察至少一个周期；多技能碰撞   │
│ 仲裁规则；过 `filter_management_candidates`。 **启动条件（可观察）**:P2 落地 │
│ 2-4 周后，活跃技能 triggers 覆盖率 >60% 且 verbatim-trigger 仍 miss 的 query │
│ 数 >0。  **B2 — P1 完整版（per-field max-pooling)**：等 A1/A2 落地后重测     │
│ verbatim 分数再定； 若做，recall 排序（0.25 地板）与                         │
│ index(0.45）是两个独立系统，分开改分开标定。  **B3 — P3 灰区**：先上 shadow  │
│ 指标（短查询记录\若跑 semantic 得多少分\，不改路由                           │
│ 行为），灰区边界从真实分布长出；若放行，预算与长 query triage                │
│ 隔离（防全局熄灯）。  **B4 — miss 池卫生门**：聚类入池前过滤 agent           │
│ 提示词形状（>150 字符、`ou are `/ `system-reminder` 前缀等）——保护未来       │
│ triggers 预填不给垃圾贴金。独立 gate。  ### 留给三路评审裁决的分歧点  **P0   │
│ 本 gate 做还是等数据？** 对抗四路分两派：失败模式/工程派主张\P0-lite 带护栏  │
│ 现在就能做（回放已证 245 条真实 miss 可接）\；数据闭环派主张\先只 A1-A3,P0   │
│ 等覆盖率 触发条件\。请三路评审就此给出明确裁决及理由。  ## 请评审回答  1. 本 │
│ gate 范围（A1-A3）是否成立？A1 写 query_patterns 的做法有无副作用？ 2. P0    │
│ 现在做 vs 等触发条件——裁决。 3. v2 是否还有四路对抗没看到的洞？)             │
╰──────────────────────────────────────────────────────────────────────────────╯
All code verification done. Here is my review.

---

# Gate 32 v2 三路评审 — PI 独立评审

## 0. 事实核实结果（先于裁决）

我对提案引用的全部关键代码做了逐行核对。**S1（两套 embedding 系统的归因）这次终于说对了**，S2/S3/S5/S6 也基本属实。但发现一处四路对抗都没抓到的结构性错误（A2 的数据源不存在），以及 A1 的一个被低估的行为面。

| 提案声称 | 核实结果 |
|---|---|
| S1: recall `_candidate_text` 含 triggers、floor 0.25；index `_compute_profile_text` 不含 triggers、0.45 | **属实**。`triage_recall.py:37`（0.25）、`:205-213`（id+desc+intent+triggers+keywords+scenarios）；`indexer.py:419-425`（scenarios+query_patterns+confidence_boosters+differentiation，无 triggers）；`config/manager.py:230`（0.45）+ `_layers.py:473-481`（margin 0.05） |
| S2: `explicit_guarded_skill_match` 已存在、0.95、只限 guarded；guarded-explicit 插入点在 unified.py:660；scenario+index 并行 best-of；scenario 命中强制 triage 仲裁 | **属实**。`triage_service.py:530-556`；`unified.py:985`（0.95）、`:660`、`:877-914`、`:691-702` |
| S3: containment 长度门槛防不住 "adversarial review"（18 字符）；`_WEAK_MATCH_LAYERS` 只有 levenshtein/custom/fallback_llm | **属实**。`routing_pending.py:504-507`。高置信命中不进 routing_pending 观察回路，验证成立 |
| S5: span name ~79 字符截断；433 条 miss；miss 口径不一 | **属实**。route: span name 实测 max 86（含 `route:` 前缀 → query ~79）；`spans.before.jsonl` 434 行（433 可用）；`gold_detection.py:108 is_route_miss_span` 与 `tool_call_bridge._is_miss` **刻意分歧**（后者更严，排除 CLI/slash）——"口径不一"部分是 design，不是 drift |
| S6: global 草稿省略示例 query | **属实**。`skill_promote.py:1948-1953`、`:2003-2017` |
| 对抗收获 1: "确定性层没人消费 triggers(idf.py:370-386 只读 name/description/intent/keywords)" | **过度陈述（NIT）**。IDF 语料确实不含 triggers，但 **TFIDFMatcher 消费 triggers**（`strategies.py:530-556`，2 倍加权）；guarded-explicit 与 session-end 路径也消费。真实缺口是"无高置信 exact/containment 通路"，不是"没人消费" |
| 回放 3787/377/245、113 技能 7 个有 triggers、`<trigger1>` 占位 | **本仓库不可验证**（本地池 6 project + 1 global，0 个有 triggers）。外部 cmspark 语料，不影响设计方向，但"245 条可接"是上限不是精度（见分歧点裁决） |

## 1. 总体裁决：**BLOCK**（A1/A2 按现文不可落地；A3 通过；方向成立）

四路对抗的收敛质量高，S1-S6 修正全部正确。但 **A1 和 A2 按文档现状无法实现**，且其中两个错误会导致把"未经人工审阅、未做隐私分域、未过卫生门"的原始 trace query 写进一个**有误路由前科且无 margin 保护的实时打分路径**。方向不改，spec 要返工。

---

## 2. Findings（BLOCK / MAJOR / NIT）

### BLOCK-1 — A2 的数据源不存在，"一行级改动"是错的
`indexer.py:55-93`：`SkillProfile` **没有 `triggers` 字段**（只有 skill_id/scenarios/query_patterns/differentiation/confidence_boosters/pack_owner/content_hash/embedding）。LLM 分析输出 schema（`indexer.py:31-52`）也没有 triggers。因此 `_compute_profile_text` 加 `+ triggers` 引用不到任何东西。A2 实际需要三件事：① 给 SkillProfile 加字段 + to_dict/from_dict + 索引版本号；② indexer 从 spec frontmatter 读 triggers 填入 profile（这条通路今天完全不存在——frontmatter triggers 只进 LLM prompt，不进 profile）；③ 才是那一行文本拼接。"一行级改动"把 ② 藏起来了。

### BLOCK-2 — A1 的 query_patterns 写入路径未定义 + 不持久 + 有绕过编辑守卫风险
今天 `query_patterns` **只来自 LLM 分析**（`indexer.py:530-537 _parse_profile` 整体替换）。任何一次重索引（content_hash 变化即触发，任何 spec 编辑都会）都会把注入的 query_patterns 冲掉。提案写"激活/索引时"但没说：
- 数据源是 **cluster 原始 query** 还是**人工编辑后的 SKILL.md frontmatter triggers**？若取前者，则 `promote --activate` 的 M5 草稿 sha256 编辑守卫（`skill_commands.py` 存在，未编辑的草稿拒绝激活）被 index 层静默绕过——同一份数据，文件路径有人工过目，索引路径没有。
- 写入机制是 indexer 学习合并 frontmatter，还是 promote 直接改索引文件？后者与下次 `vibe skill index` 打架。
"杠杆率最高的一行改动"的前提（存在一个持久、尊重人工审阅的写入通路）恰恰是没写的部分。

### BLOCK-3 — A1 同时动了无 margin 保护的 bigram 路径，且改变行为先于 A3 基线
`query_patterns` 不只喂 0.45 embedding：`_build_profile_token_index`/`_score_overlap`（`_layers.py:312-338`、`:628-660`）也用 query_patterns+scenarios+confidence_boosters，阈值 **0.20/0.30，无 margin gate**，且配置注释自述该路径历史精度差（0.05 处 accepted precision 0.455；M9 的 27/40 残余误路由是 marginal index hits）。verbatim 真实 query 入 profile 后，任何与簇共享词汇的 query 都能把 token-overlap 推过 0.20 → index 命中 → **unified.py:696-701 显示 index 命中直接 return，不经 triage 仲裁**、不进 routing_pending、不留痕。提案把 A1 框成"让 0.45 门看到原话"，漏掉了它同时降低无护栏那条路径的门槛。连带：A1 落地的分布移动本身就是 A2 "能不重标就不重标" 的前提破坏者——先 A1 后 A2 再宣称"分布没变不用重标"不自洽。**A3 的基线必须先于 A1/A2 落**（文档把 A3 排在前面是对的，但实现顺序要强制 A3→A1/A2 串行）。

### MAJOR-1 — A1 在 B4 之前嵌入垃圾（自相矛盾的时序）
提案自己说 miss 流量 64% 是子 agent 提示词（S5），又说 B4 要过滤 agent 提示词形状（>150 字符、`you are`/`system-reminder`）——但 B4 是独立 gate 推迟。现有 `_is_low_information_query`（`skill_promote.py:250-290`）只挡退化词/短 Latin/续聊/枚举回复，**明确不挡长 agent-prompt 形状**（docstring 甚至注明故意放行长枚举回复）。而 A1 本 gate 就从 `candidate.queries`（=未过形状卫生的簇 query）取样。同一批数据，一边说它是垃圾要单独建门过滤，一边本 gate 就把它 embed 进实时路由。至少要把 B4 的最小形状过滤（长度上限 + 前缀黑名单）折进 A1，或 A1 的 query_patterns 半部分推迟到 B4。

### MAJOR-2 — 隐私分域不对称
S6/渲染器对 global scope 的降级只写了 frontmatter triggers（TODO 占位），**index profile 的 query_patterns 写入没有 scope 条件**。若一个 `--scope global` 激活的技能把原始簇 query 写进 global 索引 profile（`~/.vibe/skill_index.json`，跨机器传播），M12 M5"global 草稿绝不携带原始 query"边界在索引层被打破。注入路径必须与渲染器同享 scope 门。

### MAJOR-3 — B1 的 IDF 护栏按现状实现是**反向**的（裁决 P0 的关键依据）
`idf.py`：`candidate_token_set` = name+description+intent+keywords，**不含 triggers**；`IDFTable.weight` 对未登录 token 返回 1.0（最高特异性）。推论：
- "adversarial"/"review" 这类**误伤类** trigger——若是语料外新词 → weight 1.0 → 门槛放行（正是 18 字符劫持案例）；
- "合并"/"review" 这类**正例类** trigger——出现在多个技能 description 里 → weight 低 → 门槛拒绝（"帮我合并到 main" 正是要救的案例）。
即 B1 声称"现成"的护栏会放行它要拦的、拦掉它要放的。要修必须把 triggers 纳入 IDF 语料，而那会**全局移动 KeywordMatcher 的 anchor 权重**（跨切面改动）。"P0-lite 带全套护栏现在就能做"的前提不成立。

### MAJOR-4（推迟项，不影响本 gate）— 系统地图仍不完整：实际有**三套** embedding 文本
v2 修正成"两套"（recall / index），但还有第三套：matcher pipeline 的 `EmbeddingMatcher`（`strategies.py:686-690`，文本=name+description+intent，不含 triggers）。默认 `enable_embedding=False`（`config/manager.py:144`）所以是 opt-in，但 B2 若做 per-field max-pooling，三个分布要分开标定，且 verbatim 收益不会传导到这条路径。建议在 B2 触发条件里补上"若 enable_embedding=True 需一并评估"。

### NIT-1 — "确定性层没人消费 triggers"过度陈述（见核实表）
修正为："IDF 语料与 KeywordMatcher 不用 triggers；TFIDF 弱消费（2 倍加权）；无高置信 exact/containment 通路"。不改变 P2 的价值，但"四路一致"的共识项 1 里有一处事实错误。

### NIT-2 — A3 的"统一 miss 口径"要小心：两个谓词是**刻意**分歧
`gold_detection.py:108` 的 docstring 明确：`is_route_miss_span`（发现信号）vs `tool_call_bridge._is_miss`（outcome 信号）分歧是有意设计，改一个必须重读另一个。A3 统一到 `is_route_miss_span` 用于发现类数字是对的，但不应强行让 bridge 口径也相等——写清楚每个数字用哪个谓词即可。

### NIT-3 — frontmatter triggers 需要 YAML **列表**消毒器
`_sanitize_yaml_value`（`skill_promote.py:1733`）是标量消毒器，默认 max_len=80——而回放数据里 query 就有 ~79 字符，双层截断会静默毁掉长 trigger；且它产出带引号标量而非 `- item` 列表项。A1 的"沿用现有样本"漏掉了列表形态的消毒（query 常含冒号/换行，会像 grok P1 那样炸 ruamel 解析）。

### NIT-4 — 回放数字的外部性
113/7/6%、3787/377/245 在本仓库不可复现（本地池无 triggers 技能）。不构成 BLOCK，但建议把回放脚本与数据路径写进 A3 的验收（"用哪个 corpus 复现 245"）。

---

## 3. 分歧点裁决：**P0 = 本 gate 不激活，但立即上 P0-shadow（记录不动路由）**

**裁决：数据闭环派胜，但"纯等"是错的——两派各退半步：本 gate 把 P0 规则做成 shadow 仪表（确定性规则零成本），只记录 would-fire 决策 + 复用 A3 的抽样人工裁决，不触碰路由行为。触发条件不变（覆盖率 >60% 且 verbatim-trigger 仍 miss 的 query >0），加一条 shadow 精度门槛。**

理由（按权重）：

1. **"回放已证 245 条真实 miss 可接"是上限，不是精度。** 回放把"P0 规则命中"计为转换，但命中集合里恰好包含 S3 点名的全部误伤类——18 字符 containment、极性盲区、子代理 prompt 劫持。这 245 条里有多少是"应该接住的正例"vs"规则命中的误伤"，回放无法区分；区分它需要的人工裁决机器正是本 gate 的 A3。**没有 A3 就做 P0，等于在没有尺子的情况下装一个已知会误伤的行为。** 这是数据闭环派最硬的一击，我采纳。
2. **B1 的护栏有根是坏的（MAJOR-3）。** "带全套护栏现在就能做"的前提不成立——IDF 特异性门槛按现状实现是反向的，修复要动全局 anchor 语料。护栏重做 + 跨切面改动 + 行为激活挤一个 gate，是工程派自己最反对的打包。
3. **误伤严重度不对称。** 错技能触发劫持会话/子代理（用户视角已确认，对抗收获 4），且高置信命中绕过 routing_pending 人工纠正回路（S3 已验证）——在 6% 覆盖率信号下，早期激活的期望值直到数据长出来之前都是负的。
4. **但"纯等"浪费选项价值。** P0 是确定性规则，shadow 成本≈0、风险≈0。失败模式/工程派"现在做点什么"的诉求由 shadow 满足，数据派"不动路由"的诉求也由 shadow 满足。2-4 周触发条件因此从"感觉"变成"shadow 精度数据 + 覆盖率数据"双可观测。**这是对四路分歧的合取解，不是折中解。**

## 4. 给本 gate 的返工清单（BLOCK 的解除条件）

1. **A2**：明确 SkillProfile 加 `triggers` 字段 + indexer 从 frontmatter 读入（附索引版本 bump）；"一行级改动"改为"字段+通路+一行"三段。
2. **A1**：写死数据源 = **人工编辑后的 frontmatter triggers**（尊重 M5 编辑守卫），机制 = indexer 合并（保证重索引持久）；global scope 的 query_patterns 注入与渲染器共享降级；把 B4 的最小形状过滤折进本 gate 或推迟 A1 的索引半部分。
3. **实现顺序强制 A3 → (A1+A2)**，且 A1+A2 作为**同一校准单元**一起重测 0.45/margin（"能不重标就不重标"要基于 A1+A2 联合分布，不是 A2 单独）。
4. A3 在口径统一里写明 `is_route_miss_span` 与 bridge 的刻意分歧，不强行抹平。

---

**一句话**：v2 把四路对抗的病治好了大半（S1-S6 全部经代码核实成立），方向正确；但 A1/A2 的落地规格里藏着三个会实际伤到实时路由的错误（数据源缺失、写入路径未定义、动了无 margin 的 second path），P0 该等且该 shadow。BLOCK 是规格级返工，不是方向性否决。
