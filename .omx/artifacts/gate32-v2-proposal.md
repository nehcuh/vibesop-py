# Gate 32 v2 设计提案 — 路由层优化（四路对抗收敛后）

> 状态：v1 经四路独立对抗（失败模式/用户场景/工程架构/数据闭环）大修。本文档是
> claude+pi+grok 三路评审的对象。

## 对抗评审的收获（四路确认的增益）

1. **P2（预填 triggers）是真闭环缺口，四路一致认为是必做项**：渲染器不写 triggers
   （skill_promote.py:1876+），确定性层没人消费 triggers(idf.py:370-386 只读
   name/description/intent/keywords)——skill 作者写的 triggers 至今没有强语义。
2. **cmspark 真实回放证实收益**：用真实技能池 triggers 按 exact+containment 规则回放
   3787 条 route span,P0 规则可命中 377 span,其中 245 条当时是 miss——目标分布真实存在。
3. **"发现断粮"反噬论被否证**:miss_recurrence 入场券是跨日复现（≥3 (task,day) 对)——
   P0/P2 消化的是"已有技能的反复 miss"，这类候选只会与现有技能重叠（gate30 做
   overlap-merge 就是在擦这个屁股），拿走它们是提纯不是断粮。
4. **precision > recall 的排序被用户视角确认**：错技能触发会把会话劫持进错误工作流，
   而 fallback_llm 至少正常回答；尤其 miss 流量 64% 是子 agent 提示词，误触发会
   静默污染子代理行为。

## 对抗评审发现的负面影响（v1 的病，按严重度）

- **S1（三路独立收敛）P1 打错靶子**:0.26 cosine 是对 `_candidate_text`（triage recall
  预筛，floor 0.25，能过）;0.45 是 semantic_index 的 `index_embedding_threshold`，其
  向量文本来自 `indexer._compute_profile_text`(indexer.py:419-426)——embed 的是 LLM
  profile 的 scenarios/query_patterns/confidence_boosters,**spec 的 triggers 字段根本不在
  里面**。v1 把两套 embedding 系统混为一谈。
- **S2 P0 不是新层**:`explicit_guarded_skill_match`(triage_service.py:541）已实现
  归一化 substring containment → 0.95 置信，只是限定 guarded skills;guarded-explicit
  插入点（unified.py:660）已存在。v1 的"新层插在 scenario 后"与真实结构冲突——
  scenario 和 semantic_index 是 `_try_early_layers` 并行 best-of，且 scenario 命中强制
  triage 仲裁（有固定置信误路由前科）。
- **S3 containment 的长度门槛防不住真实误伤**:"adversarial review"(18 字符）会劫持
  子代理 prompt;"先别合并到 main"极性盲区；高置信误命中绕过 routing_pending 人工
  纠正回路（_WEAK_MATCH_LAYERS 只有 levenshtein/custom/fallback_llm)——错命中不留痕。
- **S4 P0 无数据裸奔**:113 技能仅 7 个有 triggers,6% 覆盖率，还有 `<trigger1>` 占位
  脏数据。P0 的价值完全绑定 P2 或人工维护。
- **S5 验证基线失真**:miss 口径三数不一（433 vs 650/646/324);span name ~79 字符截断
  使长 query 无法忠实回放；metadata 偶发非法 JSON;64% miss 是 agent 提示词（本应 miss)。
- **S6 隐私边界冲突**:global 草稿刻意省略示例 query(M12 M5),triggers 预填在 global
  路径要显式降级，不能静默绕过。

## v2 提案

### 本 gate 范围（做）

**A1 — 渲染器预填 triggers + query_patterns(P2 强化版）**
- `_render_skill_md` frontmatter 写 `triggers:`（簇内 query 样本，≤5 条，沿用现有样本）。
- global scope:triggers 留 TODO 注释占位（隐私边界显式降级，不静默）。
- 同时把簇内 query 写入 index profile 的 `query_patterns`（激活/索引时）——让
  `_compute_profile_text` 的 0.45 门直接看到真实用户原话。**用户视角评审认为这是全提案
  杠杆率最高的一行改动**。

**A2 — P1-lite-c:`_compute_profile_text` 加 spec triggers**
- profile 文本 = scenarios + query_patterns + confidence_boosters + differentiation
  **+ triggers**。一行级改动，直接修 0.45 层的稀释。
- 重建索引后 0.45/margin 阈值视分布决定要不要动（标定集只有 8 个确认正例，
  margin 有 0.071 vs 0.0702 的脆性记录——能不重标就不重标）。

**A3 — 验证基线修复（先于一切收益声明）**
- miss 口径统一为 `is_route_miss_span` 谓词现跑数字；
- 回放剔除 ~79 字符截断的 span（或标记不可忠实回放）;
- 收益度量升级：miss→hit 转化数 + **hit identity diff**(A→B 改判）+ 抽样人工裁决
  正确率 + agent 提示词误触发数（精度回归指标）。

### 明确推迟（记录触发条件，不在本 gate）

**B1 — P0-lite（泛化 explicit_guarded_skill_match 到全池）**，带全套护栏：
containment 需要 IDF 特异性门槛（idf.py IDFTable 现成）而非字符长度；否定词黑名单；
机器负载 wrapper 剥离；新路径加入 `_WEAK_MATCH_LAYERS` 观察至少一个周期；多技能碰撞
仲裁规则；过 `filter_management_candidates`。
**启动条件（可观察）**:P2 落地 2-4 周后，活跃技能 triggers 覆盖率 >60% 且
verbatim-trigger 仍 miss 的 query 数 >0。

**B2 — P1 完整版（per-field max-pooling)**：等 A1/A2 落地后重测 verbatim 分数再定；
若做，recall 排序（0.25 地板）与 index(0.45）是两个独立系统，分开改分开标定。

**B3 — P3 灰区**：先上 shadow 指标（短查询记录"若跑 semantic 得多少分"，不改路由
行为），灰区边界从真实分布长出；若放行，预算与长 query triage 隔离（防全局熄灯）。

**B4 — miss 池卫生门**：聚类入池前过滤 agent 提示词形状（>150 字符、`ou are `/
`system-reminder` 前缀等）——保护未来 triggers 预填不给垃圾贴金。独立 gate。

### 留给三路评审裁决的分歧点

**P0 本 gate 做还是等数据？** 对抗四路分两派：失败模式/工程派主张"P0-lite 带护栏
现在就能做（回放已证 245 条真实 miss 可接）"；数据闭环派主张"先只 A1-A3,P0 等覆盖率
触发条件"。请三路评审就此给出明确裁决及理由。

## 请评审回答

1. 本 gate 范围（A1-A3）是否成立？A1 写 query_patterns 的做法有无副作用？
2. P0 现在做 vs 等触发条件——裁决。
3. v2 是否还有四路对抗没看到的洞？
