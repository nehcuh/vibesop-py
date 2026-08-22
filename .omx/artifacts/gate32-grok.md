先按路由协议匹配技能，再完整读提案和它引用的代码，逐条核实事实后再给裁决。路由还在跑，同时开始读提案和对照文档。路由命中 `kimi-gated-fix`（82%），那是修代码工作流，不适合设计提案评审。按用户指定的三路独立评审来做，先把引用代码和对照文档全部读完。继续核实渲染器、IDF、query_patterns 写入通路和相关护栏。路由命中 `kimi-gated-fix` 是误配（修代码工作流，不是设计评审）。按你指定的三路独立评审执行；下面所有机制判断都对过源码。

---

# Gate 32 v2 评审（grok）

**Verdict: `PASS_WITH_NITS`**

本 gate 范围 A1–A3 方向成立；S1「两套 embedding」归因已经说对。P0-lite **本 gate 不做**。A1 把簇内 query 写入 `query_patterns` 是全提案副作用最大的一行，必须带约束才能进实现，否则实现 PR 应按 BLOCK 打回。

---

## 1. 机制事实核对

| v2 声称 | 判定 | 证据 |
|---|---|---|
| 0.26 cosine 来自 recall 预筛 `_candidate_text`，floor 0.25 | **对** | `triage_recall.py:41-51, 206-216`：拼 `id+description+intent+triggers+keywords+scenarios`，`DEFAULT_MIN_SIMILARITY=0.25`，且只在候选数超过 triage window 时才当预筛 |
| 0.45 是 `index_embedding_threshold`，embed 文本是 `_compute_profile_text` | **对** | `indexer.py:419-426`：`scenarios + query_patterns + confidence_boosters + differentiation`；`_layers.py:452`；默认 0.45 在 `manager.py:230-240` |
| spec `triggers` 不在 0.45 那路被 embed 的文本里 | **对** | `SkillProfile` 根本没有 `triggers` 字段（`indexer.py:56-72`）。LLM prompt **输入**含 Triggers（`:31, :476`），但输出 JSON 只有 scenarios/query_patterns/…。v1 把两套系统混为一谈，v2 纠正成立 |
| `explicit_guarded_skill_match` 已是归一化 substring → 0.95，只限 guarded | **对** | `triage_service.py:541-566`；置信 0.95 在 `unified.py:983-989` |
| 插入点在 `unified.py:660`，早于 early layers | **对** | Layer 0.6，在 `filter_management_candidates`（`:685`）和 `_try_early_layers`（`:688`）之前 |
| scenario 与 semantic_index 是并行 best-of；scenario 命中强制 triage 仲裁 | **对** | `unified.py:877-914, 692-700` |
| 渲染器不写 `triggers` | **对** | `_render_skill_md` frontmatter 到 `cluster_id` 为止（`skill_promote.py:2006-2017`）；query 只进 body「When to Apply」，global 还故意省略（`:1931-1935`） |
| IDF 只读 name/description/intent/keywords | **对，但推论过满** | `idf.py:370-386` 确实如此。可是 **TFIDF 吃 triggers**（`strategies.py:530-553`，2× 权重）。Keyword 锚点门仍不含 triggers，所以「作者写的 triggers 没有强语义」方向对，说成「确定性层没人消费」不准确 |
| `_WEAK_MATCH_LAYERS` 只有 levenshtein/custom/fallback_llm | **对** | `routing_pending.py:506`；`should_enqueue_from_route:559-560`。0.95 KEYWORD / SEMANTIC_INDEX 命中不进 pending |
| miss_recurrence 入场券是跨日复现 | **基本对** | 合取：`(task,day) pairs ≥ 3` **且** `distinct days ≥ 2`（`skill_promote.py:150-151, 166-167`）。v2 只写了 pairs，漏了 days |
| 短查询旁路 15 字符 | **对** | `_layers.py:224-239`；`ai_triage_short_query_bypass_chars` 默认 15。生产里 `keyword_match_max_chars` 也是 15（`manager.py:190`），不是 v1 暗示的 5–15 死区 |

**S1 裁决：两套 embedding 的归因这次是对的。** 还要补第三套，见 MAJOR-2。

---

## 2. 分歧点裁决：P0 现在做 vs 等触发条件

**裁决：等。本 gate 只做 A1–A3（A1 带约束）。P0-lite 按 B1 的可观察触发条件启动，不要提前。**

理由（按证据强度）：

1. **P0 的独特剩余价值还没测出来。** cmspark 回放 245 条 miss 是「exact+containment vs 当时路由」的差，不是「A1/A2 落地之后还剩多少 verbatim miss」。A1 把原话塞进 index、A2 让 0.45 路看见 triggers 之后，那 245 会少一块。P0 要修的是短查询确定性命中，应在 A3 基线上重测残差，而不是拿 v1 时代的 245 当开工令。
2. **覆盖率配不上 0.95 快路径。** 本机扫描 90 个 SKILL.md，非空 triggers 8 个（8.9%），和 S4「6%」同量级。现成短触发里已经有 `audit`、`审计` 这种泛词（`.vibe/skills/cross-cutting/fuck-my-shit-mountain.skill/SKILL.md`）。泛化 `explicit_guarded_skill_match` 等于给这些词 0.95，且插在 `unified.py:660`，**绕过** `filter_management_candidates`。
3. **护栏本身是未标定的新匹配面。** IDF 门槛 + 否定词黑名单 + wrapper 剥离 + `_WEAK_MATCH_LAYERS` + 多技能碰撞 + management 过滤，体量不小于 A1–A3，还没有标定集。IDF 对未见 token 给 `weight=1.0`（`idf.py:411-413`），`<trigger1>` 这类脏数据会**通过**特异性门，不是拦住。
4. **高置信错命中不留痕。** 0.95 KEYWORD 不进 pending（`routing_pending.py:506, 554-561`）。S3 的「错命中不留痕」在 P0 落地当天就会成真。
5. **失败模式派的 245 条不能直接当本仓库开工证据。** 那是 cmspark 技能池 triggers 的回放；本仓库 triggers 覆盖率和质量都不够，数字不可平移。

B1 启动条件建议改成可执行版，而不是「活跃技能 60%」这种现有 113 个不会被 A1 自动填满的口径：

- A1 已上，**新 promote 且已激活**的技能 triggers 覆盖率 >60%（或另做一次人工/半自动 backfill）
- A3 基线上：**A1/A2 之后** verbatim-trigger 仍 miss 的 query >0
- 观察期：新路径先挂 `_WEAK_MATCH_LAYERS`（或 shadow）至少一个周期

工程派若只想「现在就吃 245」，正确动作是 A3 回放 + A1 填字段，不是上 0.95 快路径。

---

## 3. A1–A3 范围是否成立？A1 `query_patterns` 副作用

**A1 写 SKILL.md `triggers`（project）+ global TODO：成立。** 这是真闭环缺口，编辑守卫还在（`skill_commands.py:1870+, 2084`），人必须改过草稿才能激活。

**A1 把簇内 query 写入 index `query_patterns`：成立，但必须降级成「从 SKILL.md triggers 派生」，禁止第三条静默通道。** 用户视角说这是杠杆最高的一行——杠杆最高的原因正是它同时打中 SEMANTIC_INDEX 的**两条**通路，而不只是 0.45 embedding。

### A1 `query_patterns` 副作用面（必须写进实现约束）

**副作用 1 — 真正先开火的是 Jaccard 0.20，不是 embedding 0.45。**  
`try_index_layer` 先做 token overlap，阈值 `index_match_threshold=0.20`（trusted）/ `0.30`（external），打中就返回，置信缩放到 0.65–0.95，**短路 cascade**（`_layers.py:639-670, 704-710`；`unified.py:701-708`）。embedding 0.45 只是 Jaccard miss 之后的 fallback。v2 把杠杆说成「让 0.45 门看见原话」，实现上是给 0.20 词重叠送原话。这是比 P0 更软、但同样会静默改判的确定性命中。

**副作用 2 — 长 agent prompt 会同时造成稀释和劫持。**  
Jaccard：`score = |overlap| / max(|q|, |p|*0.5)`（`_layers.py:324-331`）。5 条长 prompt 把 `|p|` 撑大后：短原话分母爆炸 → 目标 verbatim 反而 miss；另一条带 `You are` / `system-reminder` 套话的 prompt 分子变大 → 误命中。Embedding 是整文档 mean pool（`indexer.py:419-426, 445-458`），同样被拉向 agent-prompt 空间。64% miss 是子代理提示词；B4 还在本 gate 之外，A1 等于给垃圾贴金。

**副作用 3 — 隐私：global triggers 留 TODO，query_patterns 却可能绕过。**  
M12 M5 在渲染器里把 global 示例 query 抹掉（`skill_promote.py:1906-1911, 1931-1935`）。若「激活/索引时」把簇内 query 写进 `~/.vibe/skill-index.json` 的 `query_patterns`，这是对 M12 的静默绕过。现有 `query_patterns` 是 LLM 造的典型问法，和用户原话不是同一类数据。

**副作用 4 — 人看不见、也改不了。**  
`query_patterns` 活在 index JSON，不在 SKILL.md。编辑守卫只 hash 草稿文件。索引时另写一条通道 = 激活后行为不受人工过目约束。这和 M7 F3 把 draft `name` 设成 `draft-{cluster}`、禁止把 raw query 当 name（`skill_promote.py:1913-1918`）是同一类过匹配风险，只是换了字段。

**副作用 5 — 样本选取是任意切片，不是「代表」。**  
`Cluster.queries` 是按 sorted `(project_id, task_id)` 各取一条代表（`clustering.py:333`）。`candidate.queries[:5]`（`skill_promote.py:1938`）不是按频次、也不是离 centroid 最近。A1「沿用现有样本」会把排序键上的前 5 条写进路由磁铁。

**副作用 6 — 立即改 TFIDF / recall，即使不做 P0。**  
A1 一旦把 `triggers:` 写进 frontmatter：TFIDF 2× 计入（`strategies.py:552-553`）、recall 预筛 embed（`triage_recall.py:212`）、triage prompt 展示（`triage_service.py:271-273`）。Keyword 锚点仍不含 triggers，所以短词不一定能打穿 keyword 层，但 recall 排序和 TFIDF 分数会动。这是加分也是污染面，A3 必须有 hit-identity diff，不能只报 miss→hit。

**A1 约束（不满足则实现按 BLOCK）：**

1. 单一真源：只把 **SKILL.md `triggers`** 在 index 时 merge 进 `query_patterns`（类似 cache-hit 重盖 `pack_owner`，`indexer.py:296-302`）。禁止从 candidate store 另开通道。
2. 写入前做 **B4-lite**：长度上限、拒绝 `you are` / `system-reminder` / `<user_query>` 形状、拒绝 placeholder。不要等独立 gate。
3. global：triggers TODO **且** 不把用户原话写入 global index `query_patterns`。
4. merge，不覆盖 LLM 的 3–5 条 paraphrase；硬帽总条数。
5. 实现后必须跑 A3 的 hit-identity + 人工抽样，禁止只报 miss→hit。

**A2 成立，但不是一行。** `SkillProfile` 无 `triggers`；cache-hit 复用旧 profile（`indexer.py:284-290`），只改 `_compute_profile_text` 而不在 cache-hit 上从 live metadata 盖字段，就是空操作。Jaccard 路径（`_layers.py:337-339`）也不含 `differentiation`，A2 若只改 embedding 文本，两条 SEMANTIC_INDEX 通路会再次分叉。阈值：「能不重标就不重标」和配置自己写的脆性记录冲突——唯一正例 margin 0.071 vs 噪声 0.0702（`manager.py:253-258`）。A2 之后必须 **测量** 分布；可以不改阈值，不能不测。

**A3 成立，且应先于 A1/A2 发收益声明。** 但「剔除 ~79 字符截断 span」写错了对象，见 MAJOR-3。

---

## 4. Findings

### BLOCK
（无。整份提案不 BLOCK；下面 MAJOR 是实现准入条件。）

### MAJOR

**M1. A1 `query_patterns` 打中的是 Jaccard 0.20 快路径，不是 0.45 embedding。**  
`src/vibesop/core/routing/_layers.py:639-670` + `:318-341`；阈值 `src/vibesop/core/config/manager.py:200-212`。  
未过滤的簇内 query 会以 0.65–0.95 短路路由，且不进 `_WEAK_MATCH_LAYERS`。必须按上面 5 条约束改写 A1；否则不要做「写入 query_patterns」这一行。

**M2. v2 仍把 SEMANTIC_INDEX 当成「一套 0.45 embedding」。它是两段，外加第三套 embedding。**  
- Jaccard 0.20（先）→ embedding 0.45+margin（后），字段还不完全相同（Jaccard 不含 `differentiation`）。  
- 第三套：matcher pipeline `EmbeddingMatcher._candidate_to_text` 只用 `name+description+intent`（`strategies.py:687-692`），不含 triggers，也不含 profile。  
A2/B2 必须按通路分别改、分别标定（B2 这句话对 recall vs index 是对的，但 index 内部还有 Jaccard vs embedding）。

**M3. A3 把 span **name** 截断（~80）当成回放 query 源。**  
Name：`agent_runtime.py:453`、`cli/main.py:748-749`（`[:80]` / `[:77]+"..."`）。  
真正的 query：`metadata["query"]`，cap **200**（`agent_runtime.py:466`、`cli/main.py:760`、`tool_call_bridge.py:100-102`）。  
按 v2 字面丢掉 name 被截断的 span，等于丢掉几乎所有 >77 字符的真实 query，基线会再次失真。应：回放用 `metadata.query`；`len==200` 标成截断；name 只当展示。

**M4. B4 不能独立于 A1。**  
`_is_low_information_query`（`skill_promote.py:250-288`）只滤「继续 / 短 Latin / 阶段词」，不滤 agent prompt。A1 本 gate 就要把 query 写成 triggers。B4-lite 是 A1 的前置，不是「未来保护」。

**M5. A2「一行」在现结构上是空操作或半拉子。**  
`SkillProfile` 无 triggers（`indexer.py:56-72, 531-537`）。cache-hit 不重读 SKILL.md。要：profile 加字段或 index 时从 live metadata 盖上；cache-hit 与 `pack_owner` 一样 restamp；决定 Jaccard 加不加；全量 `_compute_embeddings`；对照 eval 测 0.45/margin。`INDEX_VERSION` 该 bump。

### NIT

**N1.** 「确定性层没人消费 triggers」过满。TFIDF 2× 吃 triggers，但锚点门（`strategies.py:465-484, idf.py:370-386`）会丢掉「只在 trigger 里命中、name/keywords 无锚点」的结果。建议改成：「Keyword/IDF 不读 triggers；TFIDF 读但被锚点门掐掉；index embedding 不读。」

**N2.** miss_recurrence 是 pairs≥3 **且** days≥2，不是只写 pairs。

**N3.** B1「活跃技能覆盖率 >60%」对存量技能不可达——A1 只填新草稿。改成「新激活技能」或明确 backfill。

**N4.** B1 若插在现有 0.6 层（`unified.py:660`），默认**不过** `filter_management_candidates`（`:685`）。文档写了要过，实现很容易抄错插入点。`explicit_guarded_skill_match` 还是 list 里第一个命中获胜（`triage_service.py:559-566`），全池泛化必须先有碰撞规则。

**N5.** IDF 特异性门挡不住未见 token / placeholder（`idf.py:411-413`，unseen → 1.0）。P0 启动时要有字面 denylist，不能只靠 IDF。

**N6.** `unified.py:1019` `keyword_match_max_chars` 的 getattr 默认是 5，`RoutingConfig` 默认是 15。和本 gate 无关，但是短查询故事里的陷阱。

---

## 5. 对三个评审问题的直接回答

1. **A1–A3 范围成立吗？A1 写 `query_patterns` 有没有副作用？**  
   范围成立。写 SKILL.md triggers 是该做的。写 `query_patterns` 有实质副作用（Jaccard 0.20 短路、稀释/劫持、global 隐私、人审盲区、任意[:5] 切片、TFIDF/recall 立即漂移）。按 M1 约束做则是本 gate 最大杠杆；不约束就不要做这一行。

2. **P0 现在做还是等？**  
   **等。** 先 A1–A3（A1 带约束）+ 用修好的基线量残差。P0 的 245 不能当本 gate 开工令。

3. **还有四路没看到的洞吗？**  
   有：Jaccard 0.20 才是 A1 的主击发面；第三套 EmbeddingMatcher；A3 截断对象写错；B4 是 A1 前置；A2 不是一行；IDF unseen=1.0；query 样本是排序键切片不是代表。

---

**本 gate 建议执行序：** A3 冻结基线 → A1（triggers + 受约束的 query_patterns 派生）→ 强制重建 index → A2（profile 真正吃到 triggers）→ 测 0.45/margin/Jaccard 分布和 hit-identity → 不声明收益除非 A3 指标三套都有数。P0 不进本 gate。
