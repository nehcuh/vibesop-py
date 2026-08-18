你是资深代码 reviewer,门禁 4b 复审(M4 收尾修复,第二轮)。用中文,只给判断,500 字内。

## 背景

门禁 4 双 PASS_WITH_NITS。pi 的核心 nit:triage 的 candidates_hash 基于 prefilter 后 top-N 计算,导致 prefilter(含 embedding recall,昂贵)被排在缓存 lookup 与 budget/circuit gate 之前——缓存可命中或 gate 关闭时白付召回成本。

## 本轮修复(开发者声明)

1. hash 改基于全候选集,lookup 提到 prefilter 之前(fresh 命中零召回零 LLM);prefilter 移到 lookup 后、gate 前。
2. _last_good_route 存活校验改对全量 candidates(原 top-N 是保守收窄)。
3. fresh 命中 metadata:candidates_sent=0、recall_method=None(grep 确认无下游消费)。
4. configured()=False 时缓存也不参与,注释改准确;衰减 0.7 提为常量。
旧口径缓存条目一次性 stale,自愈。

## 复审要求

1. 判定重排正确性:lookup 提前后 fresh 命中的候选有效性(全量 hash 能否替代 top-N hash 的失效语义)、stale 留存链路、store 与 lookup 两端口径一致性、augmented_query 上移的一致性(持久 key 与 LLM 输入)。
2. metadata 变化有无隐患。
3. 结论:PASS / PASS_WITH_NITS / BLOCK。

## 复审包

