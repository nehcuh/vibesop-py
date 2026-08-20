# M11 设计 A：Keyword/TFIDF 层证据化评分（覆盖率归一 + 语料级 IDF + 锚点闸门）

> 状态：设计定稿（模拟验证完成）  作者：设计方 A  日期：2026-08-20
> 验证方式：运行时 monkeypatch 重放三套 eval（不改生产代码），脚本在 /tmp/m11_grid.py、/tmp/m11_stats.py、/tmp/m11_final_scores.py。

## 1. 问题机制分析

### 1.1 评分函数的三个结构性缺陷（`strategies.py` KeywordMatcher._score L131-184）

最终分 = `min(1.0, base + min(partial,0.4) + min(substring,0.5) + name_bonus)`，三个 bonus 全部加性、与 query 覆盖率脱钩：

1. **partial_bonus 跨 pair 累加**：对每个 query token 遍历所有 candidate token，前缀 +0.15 / 子串 +0.08。239 候选的描述文本 token 集很大，任何 ≥20 token 的 query 对任何候选都能凑满 0.4 cap。实测 15 条误中里 11 条 partial 顶满 0.4，而 base（Jaccard）仅 0.01-0.07。这不是匹配信号，是文本长度的函数。
2. **substring_bonus 无特异性**：任意一个 meaningful query token 落在 name/keywords_text 里就 +0.25。「复审」「review」「design」这类泛化词命中即 +0.25，两个就封顶 0.5。
3. **name_bonus 无守卫**：`name in query_lower` 即 +0.4。单词通用名（"design"、"review"、"prototype"）出现在任意长句中即触发。

叠加效果：100 token 的生产日志 query 里 2 个泛化词命中 name/keywords → 0.9+（kimi-gated-fix 实测 0.92/0.96/0.98）。

### 1.2 接受路径

matcher pipeline（`matcher_pipeline.py` try_matcher_pipeline）跨 matcher 按 max confidence 聚合，winner ≥ `min_confidence`（本机 prefs 注入 0.6，注意：RoutingConfig 默认 0.3，manager.py:598 会被用户 prefs 覆盖）即被接受。AI triage 在 eval 环境无 LLM 不可用，长 query 的 force triage 落空后直接进 matcher pipeline —— keyword 层的高分误中因此直达最终路由。

### 1.3 为什么阈值调参不够

误中分数分布 0.63-0.98，而 base eval 真阳性（走 matcher pipeline 的 9 条）分布 0.69-1.00 —— 两者几乎完全重叠（0.69 vs 0.63 仅差 0.06），任何全局阈值要么杀不动误中要么杀掉真阳性。问题在分数的构造，不在门槛。

## 2. 方案：证据化评分（v5，已模拟验证）

核心思想：**bonus 必须由「证据」支撑 —— 证据 = 特异性（IDF 锚点）× 覆盖率（cov）**。三个机制对应任务书的 a/b/c，外加 TFIDF 结果级闸门（d 的最小化版本）。

### 2.1 语料级 IDF（机制 b）

候选池即为语料。文档 = 每个候选的 name+description+intent+keywords token 集（与 _score 现有的 candidate_tokens 完全一致）。

```
w(t) = (ln((N+1)/(df(t)+1)) + 1) / (ln(N+1) + 1)     # 归一化到 (0,1]
```

- 对数压缩使其对池大小弱敏感：N=239 与 N=60 下 w 的相对排序基本不变（实测本池 w 范围 0.36-1.0）。
- 注入点：`KeywordMatcher.warm_up(candidates)`（当前是 no-op；`unified.py:369 _warm_up_matchers` 在候选加载时调用）。TFIDFMatcher 同理共享。warm_up 重建时清 keyword `_cache`。
- 注意 pool 环境相关（239 含本机 pack）：w 值会漂移，机制不依赖具体 w 绝对值，只依赖「泛化词 w 低、领域词 w 高」的排序性质（见 §5 风险 R1）。

实测关键权重（N=239）：design 0.465 / review 0.497 / code 0.523 / workflow 0.523 / 代码 0.786 / 复审 0.893 / 修复 0.893 / 诊断 0.83 / instinct 0.83 / not 0.786（!）。

### 2.2 覆盖率归一（机制 a）

```
meaningful = [t for t in query_tokens if _is_meaningful_token(t)]
hit(t) = 1.0 (exact∈candidate_tokens) | 0.6 (前缀) | 0.32 (子串) | 0.0
cov = min(1, Σ w(t)·hit(t) / Σ w(t))          # idf 加权覆盖：泛化词命中几乎不贡献
g   = min(1, cov / keyword_coverage_ref)       # 门控系数
```

### 2.3 锚点闸门（特异性硬门）

```
anchor(t) ⟺ t ∉ STOPWORDS ∧ w(t) ≥ keyword_anchor_idf_min(0.78)
            ∧ (t exact 命中 ∨ t ∈ name ∨ t ∈ keywords_text)
无任何锚点 → score 封顶 keyword_anchor_cap(0.25)
```

STOPWORDS 为小型英文虚词表（not/do/the/for/with/to/…）。**必须存在**：本语料是 name/keywords/技能描述，英文虚词在里面反而罕见（"not" df=3, w=0.786），纯 IDF 会把 "not" 当高特异词 —— E4 "Do not re-implement code" 的唯一锚点就是 "not"。CJK 不需要停用词表：bigram 化已把虚词绑定进语境。

### 2.4 多锚点豁免（防误杀真聚焦 query）

```
nk_anchors = [t for t in anchors if t ∈ name ∨ t ∈ keywords_text]   # 只认策展字段
len(nk_anchors) ≥ 2 且 cov ≥ keyword_multi_anchor_cov_floor(0.08) → g = 1.0
```

这是 base 正例存活的关键：真阳性 query（"帮我深度诊断…优化建议"）cov 只有 0.139，线性缩放必死；但它有 ≥2 个高特异锚点落在候选的 keywords 里 —— 这才是「聚焦」的正确定义。锚点限 name/keywords（不含 description 的 exact 命中）是因为 description 是自由文本，命中不算策展证据。

### 2.5 name_bonus 守卫（机制 c）

```
name_tokens = meaningful tokenize(name)
name_bonus = 0.4 仅当 len(name_tokens) ≥ 2 或 max w(name_tokens) ≥ 0.7
name_bonus 不被 g 缩放（用户点名 ≈ 显式意图）
```

"design"（w 0.465）出现在长 query 中不再触发 0.4；"instinct"（w 0.83）被点名仍触发（保住 base 正例 "查看一下我的 instinct 学习状态"）。

### 2.6 partial_bonus 改为 per-qt-best

每个 query token 只取其最优 pair 的贡献（前缀 0.15 / 子串 0.08），而非对所有 candidate token 累加。消除「文本越长分越高」的长度偏差。

### 2.7 TFIDF 结果级锚点闸门（机制 d 的最小版）

`TFIDFMatcher.match` 的结果逐一过锚点检查（同 §2.3 定义），无锚点丢弃。TFIDF 内部已有 IDF，分数本身问题不大；2 条误中（omx/review 0.75、setup-pre-commit 0.63）都是「短 query + 泛化词命中」，锚点闸门正好切掉，且不必动 TFIDF 的数学。

### 2.8 新评分公式（完整）

```
score = min(1.0, base_jaccard + g·(min(partial_per_qt_best, 0.4) + sub') + name_bonus_guarded)
sub'  = min(0.5, Σ 0.25·(0.4 + 0.6·w(t))  for t ∈ meaningful ∩ (name ∪ keywords_text))
无锚点 → min(score, 0.25)
```

## 3. 模拟验证结果（三套 eval，真实 router 端到端）

最终配置 REF=0.5 / AW=0.78 / MFLOOR=0.08 / TG1 开：

| 集合 | 基线 | 新机制 | Δ |
|---|---|---|---|
| base (routing_eval.yaml) | 31/34 | **31/34** | 0 回归 |
| oneshot (routing_eval_oneshot.yaml) | 10/11 | **10/11** | 0 回归 |
| extended (routing_eval_extended.yaml) | 81/107 | **98/107** | +17，0 回归 |

- REF 在 0.4-0.6 区间结果完全相同（0.4/0.45/0.5/0.55/0.6 五档全部 31/10/96+），参数不敏感。
- 仅 keyword 改动（无 TG1）:extended 96/107；加 TFIDF 闸门再 +2。
- 15 条 keyword 误中的新分数全部 ≤ 0.25 —— 不仅低于本机 0.6，也低于默认 0.3 的 matcher min_confidence，对 min_confidence 配置漂移鲁棒。

## 4. 26 条 errors 逐条预判

### 修复（17 条）

| # | 误中 | old→new | 机制 |
|---|---|---|---|
| 1 | finishing-a-development-branch | 0.67→0.25 | 无锚点（branch w=0.66<0.78）封顶 |
| 4 | receiving-code-review | 0.89→0.25 | 唯一锚点 "not" 被停用词表排除 |
| 5 | prototype | 0.65→0.17 | 无锚点（type w=0.72<0.78）+ cov 0.14 |
| 7 | kimi-gated-fix（复审+pi） | 0.92→0.24 | 单锚点复审，cov 0.13 → g=0.26 |
| 10 | kimi-gated-fix | 0.67→0.17 | 锚点「具体」只在 description，nk 锚点仅 1，cov 0.115 |
| 12 | kimi-gated-fix | 0.90→0.08 | 单锚点验证，cov 0.04 |
| 13 | grill-with-docs | 0.68→0.25 | with/to 皆停用词，无锚点 |
| 15 | verification-before-completion | 0.65→0.06 | 无锚点（for 停用词）+ cov 0.05 |
| 16 | omx/code-review | 0.63→0.25 | 无锚点（code w=0.52） |
| 17 | improve-codebase-architecture | 0.63→0.06 | 无锚点 + cov 0.06 |
| 18 | ui-ux/design | 0.82→0.06 | design w=0.465：锚点失败 + name 守卫失败 |
| 19 | receiving-code-review | 0.63→0.22 | 无锚点（review 0.50/implementation 0.55） |
| 22 | ui-ux/design | 0.90→0.09 | 同 18 |
| 23 | deep-diagnosis-optimization | 0.64→0.18 | 单锚点代码（w=0.786），cov 0.14 |
| 25 | skill-craft | 0.70→0.11 | 2 锚点但 cov 0.049 < 0.08 地板，豁免不触发 |
| 6 | omx/review (tfidf) | 0.75→丢弃 | dual 不在其 token 集，review w 低 → 无锚点 |
| 24 | setup-pre-commit (tfidf) | 0.63→丢弃 | commit w=0.724 < 0.78 → 无锚点 |

### 不修（9 条）及原因

| # | 层 | 原因 |
|---|---|---|
| 0, 3, 9 | scenario | scenario 层固定 0.9 的 regex 命中，不走评分函数；需 scenario 自己的机制（超出本设计范围） |
| 2, 8, 11 | fallback_llm | 假阴性（expect 非空但未召回）：worktree 清理类 query。本机制只降误中分，不产生召回；需触发词/索引侧增补 |
| 14, 20 | semantic_index | index 层 trusted-floor 边界问题，M10 机制管辖 |
| 21 | keyword | baseline 即为错（fallback miss，expect=deep-diagnosis）。新机制下多锚点豁免（复审+优化 ∈ kimi-gated-fix keywords，cov≈0.15）反而让它变成 wrong-accept —— **仍是 error，但失败模式从弃权变误接**，需知悉。这是豁免机制的真实代价 |

## 5. base/oneshot 正例依赖分析（哪些正例依赖被削弱的 bonus）

走 matcher pipeline 且以 keyword 胜出的 base 正例共 9 条，逐条核验（old→new，全部 ≥0.69）：

| query | 候选 | old→new | 存活依据 |
|---|---|---|---|
| 帮我深度诊断…优化建议 | deep-diagnosis | 0.82→0.77 | 2 nk 锚点（诊断/优化）→ g=1 |
| 全面审查这个仓库的代码质量 | deep-diagnosis | 0.72→0.72 | 4 nk 锚点（审查/码质/质量/代码） |
| 把最近踩过的坑沉淀下来 | experience-evolution | 1.0→1.0 | 锚点充足（沉淀/再犯/的坑…） |
| 查看一下我的 instinct 学习状态 | instinct | 1.0→1.0 | instinct 高 IDF 点名 +0.4 不缩放 |
| 从我的工作流里学习一个新的本能模式 | instinct-learning | 0.93→0.93 | nk 锚点 本能/模式（0.83/0.786 ≥0.78） |
| 帮我安装一个技能包 | slash-install | 0.76→0.76 | 锚点 安装/能包 |
| 这个 bug 在 router.py…修复它并验证 | kimi-gated-fix | 0.69→0.69 | nk 锚点 修复/验证，cov 0.36 |
| 把这段对话提炼成一个新技能 | skill-craft | 1.0→1.0 | 锚点 提炼/新技/对话 |
| 让 agent 自主运行一组实验… | autonomous-experiment | 1.0→1.0 | 锚点充足 |

其他正例不受影响：session-end/riper 走 KEYWORD 标签的快速通道（`_try_session_end_layer`/`_try_guarded_explicit_layer`，固定 0.95，不经过 _score）；oneshot 6 条正例全走 semantic_index；base 的 5 条 explicit 走显式层。

TFIDF 闸门下的 base tfidf 正例（模拟已验证全存活）："vibe 这个工具怎么用"→slash-help 0.83、"列出所有可用技能"→slash-list 1.0、"help me write a unit test"→omx/help 0.86。oneshot 的 "review 这个 PR"→omx/review 是 expect=[] 的 anti-reject 用例，闸门无论怎么判都不影响判定。

**依赖被削弱 bonus 的正例：无。** 9 条 pipeline 正例的分数在新机制下全部来自「锚点充分 → g=1」，bonus 数值几乎不变；被削弱的只有「无锚点/低覆盖」的分数路径，而现存正例无一依赖该路径。这是覆盖率归一 + 多锚点豁免组合的设计目标，也是它比纯阈值/纯缩放安全的原因。

## 6. 实施步骤（按文件）

1. **`src/vibesop/core/matching/idf.py`（新建，~70 行）**
   - `class IDFTable`：`build(candidates) -> IDFTable`（df 统计 + N）、`weight(token) -> float`、`fingerprint`（池内容 hash，用于缓存失效）。
   - 纯函数、无依赖，单测直接。
2. **`src/vibesop/core/matching/strategies.py`**
   - `KeywordMatcher`：新增 `_idf: IDFTable | None`；`warm_up(candidates)` 建表并清 `_cache`（当前 L204 是 `pass`）；`_score` 按 §2.8 重写；`_idf is None` 时退化为旧公式（防御：未 warm 的独立使用场景，如 `score()` 单候选调用）。
   - `TFIDFMatcher.match`：结果过滤循环加锚点检查（复用 IDFTable + 共享 `_anchors_of(query, candidate)` 帮助函数）。
   - 共用逻辑（anchors、cov、STOPWORDS）放 `idf.py` 或 `strategies.py` 模块级私有函数。
3. **`src/vibesop/core/config/manager.py` RoutingConfig 新字段**（全部带标定依据注释）：
   - `keyword_coverage_ref: float = 0.5` — 门控饱和点。标定：0.4-0.6 区间三套 eval 结果不变；取中点。
   - `keyword_anchor_idf_min: float = 0.78` — 锚点特异性下限。标定：区间 (0.724, 0.78]（type=0.724 必须非锚点；模式=0.786 必须是锚点）；0.78 是带内最保守值。注意这是归一化 w，非绝对 IDF。
   - `keyword_anchor_cap: float = 0.25` — 无锚点封顶。标定：低于 matcher min_confidence 默认 0.3，保证默认配置机器上也弃权。
   - `keyword_multi_anchor_min: int = 2`、`keyword_multi_anchor_cov_floor: float = 0.08` — 豁免条件。标定：floor ∈ (0.049, 0.139)（E25 vs 深度诊断正例），取 0.08 居中对数中位。
   - `keyword_name_idf_min: float = 0.7` — 单 token 名享受 name_bonus 的特异性下限。标定：design 0.465（须守卫）vs instinct 0.83（须放行）。
   - `tfidf_anchor_gate_enabled: bool = True`。
   - 管线：matcher 构造处（`unified.py` __init__，L312 前）把 RoutingConfig 值注入 MatcherConfig（需给 MatcherConfig 加对应字段或传 RoutingConfig 引用）。
4. **测试**
   - `tests/unit/core/matching/`：IDFTable 单调性/归一化；_score 五个机制各一个单测（锚点封顶、覆盖门控、多锚点豁免、name 守卫、per-qt-best）；未 warm_up 退化路径。
   - 重跑三集 eval 固化基线：`uv run python scripts/eval_routing.py --file tests/benchmark/routing_eval_extended.yaml --json-out /tmp/m11-after.json`（预期 98/107）。
5. **文档**：`docs/` 路由机制说明补一节；CHANGELOG。

## 7. 风险清单

- **R1（最大）：IDF 池依赖。** w 值随安装池漂移；本机 239 候选（含 pack）。归一化 + 对数压缩保证排序稳定，但边界 token（w≈0.78 附近：模式 0.786 / 代码 0.786 / not 0.786）在别的池里可能翻转侧。缓解：锚点取 name/keywords 策展字段（内容稳定）；停用词表兜住英文虚词；REF 宽带不敏感已验证。**回归防护：三集 eval 进 CI，池显著变化（新增 pack）后重跑。**
- **R2：多锚点豁免的误接面。** E21 已从弃权变误接（仍计 error，无指标回归，但用户体验上 wrong-answer 比 no-answer 更主动）。cov_floor 0.08 控制触发频率；若生产观察到滥用可提到 0.12（E10 类仍安全，深度诊断正例 cov 0.139 余量变薄——需重跑验证）。
- **R3：CJK 假锚点。** bigram 如「的坑/后别」w≈0.89 且可能命中候选文本成为锚点。实测方向有利（帮了 P3），但理论上错误候选也可能蹭到。闸门要求锚点必须在 name/keywords/exact 命中，泛化 bigram 同时满足 w≥0.78 且命中策展字段的概率低。
- **R4：TFIDF 闸门误杀未见真阳性。** 若某真阳性 query 只以泛化词命中（如 "review my code" 对 code-review 技能，review/code 皆非锚点），会被闸门丢弃 → 落到 fallback。base 3 条 tfidf 正例已验证存活，但覆盖面有限；故做成 `tfidf_anchor_gate_enabled` 可关。
- **R5：冷启动小池（方向已更正，gate14）。** 小池不是让闸门"形同虚设"，而是**变严**：归一化 w 在小池被压缩（N=10 时 df=2 的词 w≈0.68 < 0.78，而 N=239 时 df=2 → 0.83），有真实证据但非极稀有的 token 够不到锚点线 → 锚点门过度封锁 → 召回损失（错误方向是少路由，不是误路由）。机制本身不依赖特定池大小，但小池部署应下调 `keyword_anchor_idf_min`（见该字段注释）；未加代码守卫以避免未标定的行为分叉。
- **R6：scenario/semantic_index 层 9 条残余错误不动。** 本设计只覆盖 keyword/tfidf；scenario 固定 0.9 的问题是下一个里程碑的事。

## 8. 与「聚合层仲裁而非改评分」路线的取舍

聚合层仲裁（在 matcher_pipeline 出口对 keyword/tfidf winner 做证据检查，不达标则穿透 fallback）：

- 优点：改动集中在一个 chokepoint，评分函数不动，回归面小。
- 缺点：① keyword 分数仍被多处消费 —— 排序/alternatives、`top_confidence ≥ 0.95` 的早退短路（matcher_pipeline.py:110-113）、rejected_candidates 诊断 —— 烂分数继续污染这些路径；② 仲裁只能「毙掉 winner」，不能「让正确的候选赢」—— 证据在分数里已经丢失，事后无法恢复排序；③ 与 M10 trusted-floor 的语义不同：M10 仲裁的是「两个合格证据源之间的竞争」，而这里的问题是「分数本身不承载证据」，仲裁层拿不到所需信息（需要重新算一遍覆盖率和特异性，等于把评分逻辑搬到聚合层，分层更乱）。

本设计的选择：**keyword 改评分（主犯，且分数被多处消费），tfidf 用结果级闸门（其内部分数健康，只是缺特异性护栏）**。两者共用同一份 IDF/锚点基础设施，仲裁逻辑不复制。若裁决更保守，可先落地 TFIDF 闸门 + keyword 锚点封顶（§2.3/§2.7 两个机制即可修 10 条），覆盖门控与多锚点豁免第二阶段再上。

## 附：验证工件

- `/tmp/m11_grid.py`：参数化 monkeypatch harness（REF/AW/MF/TG1 可组合），复现命令见文件头。
- `/tmp/m11_grid_REF0.5_AW0.78_MF0.08_TG1.json` 等：三套 eval 全量 per-query 记录。
- `/tmp/m11_final_scores.py`：15 条误中 + 9 条正例的分数分解表（本文 §4/§5 数据来源）。
- 候选池 239（含本机 pack），RouterConfig 生效 min_confidence=0.6（prefs 注入，非默认 0.3 —— 所有误中新分数 ≤0.25，两个配置下都弃权）。

## 附录 B：gate14 复审修复（2026-08-20）

- **BLOCK-1（pi，成立）**：ANCHOR_STOPWORDS 原表漏掉 get/make/can/will/who/there/should/would/could/because/most/same/some/such 等高频虚词（239 池上 get w=0.830）。复现 query "get this working on the new branch before the deadline" 对 mattpocock/grill-me：修复前 warm 态 0.343（掀开 0.25 封顶），修复后 **0.25**（< 0.3 matcher 地板，端到端 fallback）。修复：表扩为 DEFAULT_STOP_WORDS ∪ 标准虚词类（冠词/代词/情态/系动/介词/连词/常见副词/高频通用动词）的自含字面量并集（不引用 tokenizers.DEFAULT_STOP_WORDS——CJK 模式下该表不生效，引用会静默失效）。
- **claude nit 2**：find_anchors 的 name/keywords 子串证据对拉丁 token 加词界（"art" 不再锚中 "smart"）；CJK 保持朴素包含。substring_bonus 保留朴素包含（弱分级信号，避免重标定）——锚点是闸门，bonus 是信号，语义分层有意为之。
- **claude nit 3 / pi nit 3**：两处 `query_lower = " ".join(query_tokens)` 改 sorted join（含 legacy）。
- **claude nit 1**：§7 R5 方向更正——小池是锚点门**变严**（w 压缩，df=2 在 N=10 时 w≈0.68 < 0.78）导致召回损失，非形同虚设；config 注释与 routing-system.md 已补小池行为说明，未加代码守卫。
- **claude nit 4**：TFIDFMatcher.fit 仅在 len(candidates) ≥ 2 时建 IDF 表——score() 的单候选 fit 不再留下 1 文档表（w 全 1 → 闸门形同虚设）。
- **claude nit 5**：CHANGELOG "6 knobs" → 7。
- **claude nit 6**：_has_anchor 的 query tokenize 提升到 match() 循环外。
- **claude nit 7**：KeywordMatcher.warm_up 改显式重置（空池 → _idf=None 回 legacy + 清缓存），加测试钉死。
- **claude nit 8**：name 守卫 0.7 与锚点线 0.78 的 [0.7,0.78) 死区——注释说明不连贯但保守（点名证据强于裸 keyword 命中）。
- **pi nit 1**：cov-floor 拒绝侧单测（2 nk 锚点 + cov≈0.062 < 0.08 不免门，score 0.12 < 0.3）。
- **pi nit 2**：REF 带用**生产代码全机制**（含 TG1 闸门、新停用词表、词界）重跑，/tmp/m11_refband.py：REF ∈ {0.4, 0.45, 0.5, 0.55, 0.6} → extended 全部 **98/107**。config 注释已改准确。
- **pi nit 4**：reload_candidates 重 warm 直接单测（tests/unit/core/routing/test_matcher_rewarm.py）。
- **pi nit 5**：coverage_ref 除零守卫（max(ref, 1e-9)，0 退化为"门控关闭"），加单测。
