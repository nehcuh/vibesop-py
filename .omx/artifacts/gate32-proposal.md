# Gate 32 设计提案 — 路由层短查询/语义稀释优化

> 状态：待对抗评审。本文档是评审对象，不是已决方案。

## 已验证的病灶（实测证据）

1. **语义层稀释**:`triage_recall._candidate_text`(src/vibesop/core/routing/triage_recall.py:206）把
   id+description+intent+triggers+keywords 拼成一个长文档做单次 embedding。实测:verbatim
   trigger（原句逐字在候选文本里）cosine 也只有 0.26（mean pooling 稀释）。阈值 0.45。
2. **短查询盲区**:ai_triage <15 字符旁路(_layers.py:224-239，理由：短查询通常是显式关键词，
   传统匹配更快更准);levenshtein 层是 Latin token typo 容错导向(strategies.py:710+，有 gate7
   casual/causal 误路由前科),不接 triggers 包含匹配。实测:"帮我合并到 main 吧"(9 字符)
   落到 fallback_llm;加长变体全部命中(0.72-0.82)。
3. **闭环断在最后一厘米**:M12(miss→聚类→候选→promote)产出技能，但渲染器不填 triggers
   字段，激活后接不住产生它的 query 模式。实测:手工补 triggers + 重建索引后 2/3 技能
   立即从不命中变命中。

## 提案(按杠杆率排序)

### P0 — 触发器词典层(新确定性层，插在 scenario 之后、semantic_index 之前)

- 归一化后 query == trigger(不限长度)→ 高置信命中;query 包含 trigger 且 trigger ≥6 字符
  → 高置信命中。不做 fuzzy。
- 数据源:skill spec 现成的 `triggers` 字段。
- 目标场景:miss×复现候选的特征分布——同一句话反复说。
- 缓解:containment 限 ≥6 字符;泛化短词("提交")只走 exact。

### P1 — 语义层 per-field max-pooling

- 每个 trigger/字段单独 embed，候选得分 = max(字段向量与 query 的余弦),替代整文档单向量。
- 预期:verbatim trigger 0.26 → ~1.0。
- 成本:N 倍 embedding 向量,走现有持久 cache(content-hash keyed)。
- 连带:0.45 阈值需用 scripts/calibrate_index_threshold.py 重标定(max 会抬高分布)。

### P2 — 渲染器预填 triggers(gate32 本体)

- `_render_skill_md` 把簇内 query 样本写进 frontmatter `triggers:`。
- 编辑守卫(content-hash)保证人工过目才激活,无 over-match 风险。

### P3 — ai_triage 灰区放行

- 短查询旁路保留;semantic 最佳分落灰区(如 [0.30, 0.45))时破例进 triage。
- 灰区阈值从 P0/P1 落地后的真实分布长出,不拍脑袋。

## 验证方案

- cmspark `.vibe/observability/spans.jsonl` 有 433 条真实 miss query——修复前后各跑一遍
  路由回放,命中率差值 = 收益直接度量。
- orbstack e2e 基线:smoke 65/65 + routing 7/7 防回归。

## 建议执行顺序

P0+P2 一个 gate(小、确定性);P1 单独 gate(要重标定);P3 最后。

## 对抗评审要回答的问题

1. 每个 P 的收益是否真实?有没有更简单的替代?
2. 负面影响:误命中(错技能触发比不命中更糟?)、层间交互、缓存/性能、对 M12
   发现信号的反噬(路由变准 → miss 池萎缩 → 发现断粮?)
3. 执行顺序对不对?有没有被漏掉的更大杠杆?
