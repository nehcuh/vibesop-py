# M11 设计 B:matcher 层证据门(Evidence Gate)——对抗性独立设计

> 设计方 B(对抗性独立设计)。日期:2026-08-20(v2,B4→B5 修订)。
> 基线:extended 75.7%(81/107),base 31/34,oneshot 10/11。
> 验证方式:全路由复放(monkeypatch 临时脚本 /tmp/m11_collect.py、/tmp/m11_sim.py,不改生产代码);
> 基线复放与 /tmp/m11-baseline.json 完全一致(31/34、10/11、81/107)。

## 0. 修订记录(诚实声明)

**v1 的「B4 全绿 31/34」声明有参数依赖性,裁决方复现为 29/34,原因已定位**:B4 报告的成绩对应 T_IDF=0.15,而 /tmp/m11_sim.py 的 T 默认值是 0.2(`sys.argv[2]` 缺省)。复现命令 `B4`(不带 T)跑出 29/34,回归 2 条 instinct 正例——它们的 idf_share 为 0.19/0.16,恰好落在 (0.15, 0.2] 区间。这暴露了 B4 的真实缺陷:**门槛骑在边界上,不是平台**。v2 用 B5(§4)消除该边界依赖,T∈[0.2, 0.3] 全程 31/34。

**v1 对路线 A 的批判部分错误,在此更正**:v1 模拟的「A」是自行重演的简化版(纯覆盖率归一 + IDF 加权 + name 守卫),**遗漏了 A 真实设计(m11-design-a.md §2.4)的「≥2 name/keywords 锚点且 cov≥0.08 豁免」和英文停用词表**。用 A 自己的 harness(/tmp/m11_grid.py)独立复跑其最终配置 `REF0.5_AW0.78_MF0.08_TG1`,实测 **base 31/34、oneshot 10/11、extended 98/107(+17),零回归**——A 声称的成绩属实。v1 批评#2(覆盖率归一必杀 base 正例)被多锚点豁免证伪;批评#1(IDF 反向)只适用于「IDF 线性加权/df 入口抑制」(B2 实测修复 0 条仍成立),不适用于 A 的「IDF 作锚点门槛 + 停用词兜底」用法。修正后的路线对比见 §3。

## 1. 问题分析:15 条 keyword 误中的真实共性

逐条提取特征后(/tmp/m11_features.json),15 条 keyword 误中的共性**不是打分不准,而是「该不出招时出招」**:

- 胜者覆盖的 query 信息量极小:meaningful-token 精确覆盖率 cov ≤ 0.125(多数 < 0.08),IDF 份额 idf_share ≤ 0.141;
- 高分全部来自加性 bonus 堆积:substring_bonus(+0.25/token, cap 0.5)+ name_bonus(0.4),与 query 覆盖脱钩(strategies.py L131-184);
- 接受门槛只有 `min_confidence`(matcher_pipeline.py L130)和一个 0.95 提前退出——**没有任何「证据质量」概念**。误中分数 0.63–0.98,门槛形同虚设;
- 反直觉发现:**污染元凶不是泛化词,而是稀有词**。`复审` df=1、`提炼` df=1、`修复` df=1——线性 IDF 视角下它们是池中「最特异」的 token。kimi-gated-fix 的 0.92–0.98 正是被自家声明的 df=1 关键词驱动的。239 池上原始 IDF 分布被压缩(p25=5.09 / 中位 5.38 / p75=5.79),线性加权无区分度。

对照组:extended 81 条正例中 79 条是 no-match 断言,keyword 层正例仅 1 条(session-end 快速通道,不经 pipeline)。真正的 keyword 正例在 base/oneshot。

## 2. 裁决链现状(代码事实)

- `unified.py:675-818`:early layers(scenario+index best-of)→ AI triage → matcher pipeline → 守卫技能检查 → no-match。
- `matcher_pipeline.py:88-131`:keyword/tfidf/embedding 并行打分,max-confidence 聚合,唯一接受条件是 `merged_matches[0].confidence >= min_confidence`。
- Levenshtein 已降级为 last-resort 二遍执行(`unified.py:820-871`);M10 的 trusted/external 仲裁只在 semantic_index 层(`_layers.py:486-526`),**matcher 层没有对应物**——本方案补这个洞。
- 守卫技能检查(`unified.py:789-797`)是先例:在 pipeline 之后、接受之前做「证据资格」裁决。B5 是它的推广。

## 3. 路线对比(全部经全路由复放实测;★ = 已独立复核)

| 路线 | base | oneshot | extended | 修复数 | 回退风险 | 实现成本 | 机制纯度 |
|---|---|---|---|---|---|---|---|
| A-v1(我的简化重演,非 A 真实设计) | 25/34 ✗ | 10/11 | 96/107 | +15 | 高(7 条 base 死) | — | — |
| **A-v5(A 真实设计,独立复核★)** | **31/34 ✓** | **10/11 ✓** | **98/107** | **+17** | 低(A 文档 §5 逐条核验 9 条 pipeline 正例全存活) | 中(重写 _score + IDFTable + TFIDF 闸门) | 高(评分承载证据) |
| B2:入口 df>15% 抑制 | 31/34 | 10/11 | 81/107 | 0 | 无 | 低 | 无效(驱动词是 df=1 稀有词) |
| B3:仅 external 胜者门 | 31/34 ✓ | 10/11 ✓ | 91–92/107 | +10/+11 | 极低 | 低 | 好(与 M10 同构) |
| B4:门(idf_share≥T 或 ≥2 特异命中@idf≥中位) | 31/34 @T=0.15;**29/34 @T=0.2 ✗** | 10/11 | 94–95/107 | +13/+14 | **中:门槛骑边界** | 低 | 好 |
| **B5:B4 + name 锚点豁免 + 特异命中改 w≥0.7(终稿)** | **31/34 ✓** | **10/11 ✓** | **95/107** | **+14** | 低(T∈[0.2,0.3] 平台,实测 0.15/0.2/0.25/0.3 四档 base/oneshot 全平) | 低 | 好 |
| B6:B5 + 英文停用词剔除 | 31/34 | 10/11 | 95/107 | +14 | 同 B5 | 低 | 无增益,弃 |

**A vs B5 的诚实取舍**:A 修 17 条,B5 修 14 条。差距 3 条(#4/#10/#25)来自机制差异:A 的「无锚点 → 分数封顶 0.25」能杀掉「token 重叠真实但锚点全是中低 w 词」的胜者(如 #4:code/review 精确命中是真的,但二者 w≈0.5 非锚点,唯一高 w 词 "not" 被停用词表排除);B5 是接受门,胜者的重叠证据真实(idf_share 0.39)时就无法拒绝——**接受门只能问「证据够不够」,不能问「证据的词够不够格」**。B5 的优势在爆炸半径:评分函数不动,其全部下游消费者(0.95 早退短路、alternatives 排序、rejected 诊断、silent 模式建议)零影响;单 chokepoint,一个开关可整体回退;A 需要重标定分数的全部分布(A 已做,§2.8/§5,质量不错)。两者不互斥:B5 的门可以垫在 A 的评分之下作双保险,但叠加无增益(A 已把误中分数压到 0.25 以下,门不会再接到它们)。

## 4. 终稿方案:B5 证据门(具体到函数/配置)

### 4.1 机制

在 `MatcherPipeline.try_matcher_pipeline`(matcher_pipeline.py)聚合完成后、返回 LayerResult 前,对**胜者为 KEYWORD 或 TFIDF 层**的结果做证据资格审查(LEVENSHTEIN 胜者豁免——拼写纠错匹配本就没有精确 token 命中;EMBEDDING 有自己的阈值;scenario/index 不在此管线内):

```
accept ⟺ n_meaningful(query) ≤ 2                        # 短查询豁免(management gate 同款先例)
       OR idf_share(winner) ≥ T_share                    # 胜者占 query 信息质量的份额
       OR n_specific_hits(winner) ≥ 2                    # ≥2 个独立特异命中(单稀有词撞车常见,两个独立特异词同中一技能非偶然)
       OR name_anchor                                    # 单锚点豁免:query 含有「技能完整 name」的精确 token 且该 name 特异
```

其中:

- `w(t) = (ln((N+1)/(df(t)+1)) + 1) / (ln(N+1) + 1)`(归一化到 (0,1],与 A 的 IDFTable 同式,可共享实现);df/N 在**当前候选池**上计算,随 `reload_candidates` 重建;
- `idf_share = Σ idf(t ∈ meaningful ∩ candidate_tokens) / Σ idf(t ∈ meaningful)`(用原始 idf 或 w 均可,比值不变);
- `n_specific_hits`:meaningful query token 中,精确命中候选 token 集、或出现在 name/keywords 文本中,且 `w(t) ≥ W_SPECIFIC(0.7)` 的去重计数;
- `name_anchor ⟺ ∃ qt ∈ meaningful: qt == candidate.name(完整精确)∧ w(qt) ≥ W_NAME(0.7)`。**这是 v2 的关键修正**:「instinct」(w 0.83)被点名即放行;「design」(w 0.465)、「review」(w 0.50)、「code-review」单词命中不满足 w≥0.7 或不是完整 name;kimi-gated-fix 的「复审」只是 11 个 keywords 之一、不等于 name,**不会被放行**(实测三条 kimi-gated-fix 误中两条仍被拒,第三条见 §5);
- 拒绝 → pipeline 返回 None → 落入现有 no-match 路径(fallback_llm / silent 建议)。

### 4.2 配置(RoutingConfig,均带标定依据)

```python
matcher_evidence_gate_enabled: bool = True             # 总开关,一键回退
matcher_evidence_min_idf_share: float = 0.25           # 标定:T∈[0.2,0.3] 三集成绩平台(0.15/0.2/0.25/0.3
                                                       # 四档实测 base/oneshot 全平,extended 94→95 在 0.2 饱和),取平台中点
matcher_evidence_min_specific_hits: int = 2            # 标定:误中普遍单特异命中;base 正例(优化+诊断、本能+模式)≥2
matcher_evidence_specific_w_min: float = 0.7           # 标定:design 0.465/type 0.72 边界——type 必须非特异(单 hit 不足 2 仍拒),
                                                       # 模式 0.78/本能 0.83 必须特异;与 A 的 name 阈值同值可共享标定
matcher_evidence_name_anchor_w_min: float = 0.7        # 标定:instinct 0.83(须放行)vs design 0.465(须守卫)
matcher_evidence_short_query_max_tokens: int = 2       # 与 management gate 的短查询惯例一致
```

读取用 `_cfg_float` 同款 MagicMock 容错惯例。

### 4.3 实现注意(容易踩的坑)

1. **必须落在 pipeline 内,不是 unified._try_layers**:session-end / guarded-explicit 快速通道(`unified.py:912-991`)以 layer=KEYWORD 返回但不经 pipeline,放 unified 层会误杀「我先离开了」。pipeline 内天然豁免。
2. `fallback_mode="silent"` 的建议重跑(`unified.py:1061`)复用 pipeline——建议列表被门过滤是想要的行为,无需特判。
3. 二遍 Levenshtein 机制不受影响:门只看胜者 layer。
4. 拒绝后 alternatives 一并丢弃(与 guarded-skill 拒绝同款语义:次优已输过聚合投票)。
5. df/w 表挂 MatcherPipeline 或 CandidateManager,生命周期与 candidates 一致;warm/reload 时重建。

## 5. 逐 query 结果(B5@T=0.25,实测;与 T=0.2 完全相同)

**成绩:base 31/34(0 回归)、oneshot 10/11(0 回归)、extended 95/107(+14)。无任何 OK→BAD;无「基线错→另一种错」的模式变化。**

### 修复(14 条,全部 → fallback_llm/no-match)

keyword 12 条:finishing-a-development-branch(Implement M1 Task 6…)、mattpocock/prototype(TS2339)、kimi-gated-fix×2(「可以,使用 workflow…复审」「您提到的…sub agent 操作 tab」)、mattpocock/grill-with-docs(#mhwofh tool_calls)、verification-before-completion(Harden companion…)、omx/code-review(P1-3 evaluate…)、improve-codebase-architecture(grill N1-N10…)、ui-ux-pro-max-skill/design×2(Verify CONDITIONAL GO…、Implement W4+W5…)、receiving-code-review(Batch 2…Grok Review)、builtin/deep-diagnosis-optimization(当前 /Applications/CMspark.app…)。
tfidf 2 条:omx/review(做一轮 dual-review)、mattpocock/setup-pre-commit(按批次拆 commit)。

### 仍失败(12 条)及归因

- keyword 3 条:#4「Do not re-implement code. Dual external review」(idf_share 0.39,code/review 重叠是真的,「词对意图错」,接受门原则上接不住;A 靠锚点封顶+停用词修掉)、#10「先让 pi 和 claude 进入评审…」(复审+具体 凑满 2 特异命中,边界漏网;A 靠 nk 锚点限策展字段修掉)、#25「我设想在未来…会议记录…」→ skill-craft(提炼+生成 2 特异命中,query 确实在谈提炼/生成,关键词层面不可判);
- scenario 3 条、semantic_index 2 条:上游层,出门射程;
- fallback_llm 4 条:漏招(expect 非空),召回问题,两路线都不解决,建议另立工单。

### 良性 CHG(ok1 不变)2 条

- oneshot「compose a detailed requirement sheet…」:mattpocock/grill-with-docs → fallback_llm。基线即失败(expect oneshot-web-spec),现从 wrong-accept 变弃权,失败模式改善但计数不变。
- base「help me write a unit test for this function」:omx/help(tfidf)→ fallback。reject 条目,ok1 不变。

## 6. 对路线 A 的批判性审查(v2 修正版)

仍成立的批评:

1. **IDF 线性加权/df 入口抑制无效甚至反向**(B2 实测修复 0 条;复审/提炼/修复 df=1 是池中最特异 token)。注意这不适用于 A 的「IDF 作锚点门槛」用法——A 的锚点门 + 停用词表是有效的,v1 把两者混为一谈是批评错误。
2. **边界 token 不稳定**(A 自己列为 R1):w≈0.78 带上挤着 模式/代码/not 三个判定关键 token,换池可能翻转侧;三集 eval 进 CI 是必要缓解。
3. **E21 失败模式劣化**(A 自己披露):「根据评审意见…workflow…双路复审」从 fallback 弃权变成 kimi-gated-fix 误接——计数不变,但 wrong-answer 比 no-answer 更主动。B5 无此问题(该 query 在 B5 下仍是 fallback)。
4. **爆炸半径**:评分函数被多处消费(0.95 早退、alternatives、rejected 诊断、score() 单候选调用),改分需要重验全部下游;A 已逐条核验 9 条 pipeline 正例,但 silent 建议路径、未来新增消费者仍需警惕。

撤回 v1 的批评:#2(覆盖率归一必杀 base 正例——被多锚点豁免证伪)、#4 中「name 守卫守卫错目标」(A 的 name 守卫只是五机制之一,主机制是锚点门+覆盖门控)。

## 7. 残余风险与后续

- **门与 A 可叠加但无增益**:A 落地后误中分数 ≤0.25,不会再到达 B5 的门;若裁决选 A,B5 可作独立保险开关;若选 B5,#4/#10/#25 三条留待后续(需要「锚点资格」概念进证据门,等于向 A 靠拢)。
- scenario 层固定 0.9 是另 3 条错误的根源,建议 M12 处理。
- 4 条 fallback 漏招(worktree/fanout 词汇)走召回侧,与 M11 正交。

## 附:复现

```bash
uv run python /tmp/m11_sim.py base            # 31/34, 10/11, 81/107(与基线一致)
uv run python /tmp/m11_sim.py B4 0.15         # 31/34, 10/11, 94/107(v1 报告值)
uv run python /tmp/m11_sim.py B4 0.2          # 29/34 ✗(裁决方复现值,T 缺省=0.2)
uv run python /tmp/m11_sim.py B5 0.25         # 31/34, 10/11, 95/107  ← 终稿
uv run python /tmp/m11_sim.py B5 0.2          # 同上(T 平台 [0.2,0.3])
uv run python /tmp/m11_grid.py REF0.5_AW0.78_MF0.08_TG1   # A 真实设计独立复核:31/34, 10/11, 98/107
```
