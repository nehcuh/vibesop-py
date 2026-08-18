核对完毕(_layers.py、triage_service.py、unified.py、四个调用方均已实读)。

## 修复判定

1. **scenario force**:闭合。原事故(13 字 scenario 命中短路级联)现在必经 triage 仲裁；triage 无果回退 scenario 且带 `scenario_fallback` 标记，可区分“默认胜出”与“仲裁胜出”。
2. **model 字段**：闭合。旧 entry 无 `model` 自然判 stale 重编码一次；换 `MODEL_NAME` 不再静默复用错向量。
3. **guard 下沉**：闭合。

## force=True 是否引入新问题：无实质问题

- **skip_ai_triage 交互**：检查在 `_layers.py:170`,先于 force 判断——PlanBuilder 子任务豁免保留，force 不越权。
- **budget/熔断**：持久缓存 fresh 命中在 gate 之前(`triage_service.py:145-148`),重复 scenario query 零成本；未命中仍过 budget(174)+ 熔断(187)。force 只跳过短-query bypass,不越过 gate;gate 拒绝 → 回退 scenario(有标记)，fail-open 合理。
- **成本面**：仅首个未见过的 scenario query 付一次 LLM 调用，受 budget 封顶。
- scenario 的 SkillRoute 每次现建(`_layers.py:140`),metadata 标记不跨 query 泄漏。

## 四路径安全

orchestrator.py:170、sessions/context.py:157、plan_builder:307、workflow_engine:633 均有 `primary is None`/`has_match` 分支，junk 结果形状同 disabled fallback,安全；guard 位于 stats/tracing 之前，junk 不进统计；route() 入口 guard 保留在遥测块前。

## Nits(不阻塞)

- embedding 缓存 RMW 分两次加锁，并发写会丢 entry(下次自愈，benign,但建议合并为单锁内 read-modify-write);
- 子串匹配会误杀字面含 `<system-reminder` 的正常 query(本仓自身开发时会碰到)；
- 长 junk no-match 仍可经 `_heuristic_check` 进 decompose——既有行为，已声明，未加重。

## 结论：PASS_WITH_NITS

三项修复均闭合，无新增缺陷；三条 nit 记 backlog 即可。
