你是资深代码 reviewer,这是门禁 2 第二轮复审(聚焦 BLOCK 修复)。用中文,只给判断,600 字内。

## 第一轮结论回顾

- pi:BLOCK — B1:进程内内存缓存(_get_cache,键不含候选集,TTL 1h)先于持久缓存执行,长驻进程下已卸载 skill 仍可从内存缓存命中并直接成为最终路由,绕过 candidates_hash 失效与"已删不复活"契约。
- claude:PASS_WITH_NITS,但指出:持久缓存 lookup 在熔断/预算 gate 之后,LLM 持续故障熔断 open 后 fresh 命中与 last-good 全不可达。

## 本轮修复(开发者声明)

1. B1:内存缓存命中后用 `_skill_in_candidates()` 校验 skill_id 在当前 candidates 中(全量候选集,精确+小写兜底),不在则视为 miss;last-good 复用同一 helper。
2. 排序:prefilter/query 增强/内存缓存/持久缓存 fresh 命中整体上移到预算/熔断 gate 之前;stale/last-good 留在 LLM 失败路径不变。
3. nit:merge_confirmed 尾换行防护;replay docstring 注明缓存写入不隔离。
4. 附带行为变化(需你裁决):内存缓存命中也随块上移到 gate 之前;内存缓存校验用全量 candidates 而 last-good 用 prefilter 后集合(有意的不对称)。

## 复审要求

1. 读 diff,判定 B1 与排序问题是否真正闭合,有无引入新问题(如 prefilter 上移后的副作用、gate 计数语义变化、metadata 标记一致性)。
2. 裁决开发者声明的两点不对称是否可接受。
3. 结论:PASS / PASS_WITH_NITS / BLOCK。

## 复审包

