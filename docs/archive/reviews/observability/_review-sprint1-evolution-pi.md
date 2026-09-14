Now I have all the evidence I need. Let me compile the review.

---

# Pi Review: Product Evolution + Sprint 1

## Verdict: CONDITIONAL

## Part A — Strategy findings

### A1 北极星 aha 句正确，但代码未兑现（P0）

"纠错后第二天更准，第三次回放上次"——对 solo-dev 的痛点映射精确。**但**当前 replay Y 只写入 provenance span，明确**不注入** prior skill 到路由（`main.py:1928`: *"Y does NOT inject the prior skill into routing context"*）。aha 句夸大了代码能力。Sprint 1 必须要么兑现注入，要么诚实降级 aha 表述为 "Y 标为回放，手动参考步骤"。

### A2 降级 meta-auditor、提升 write-back + replay——正确（P1）

降级 route-auditor 为默认的决定正确。`InstinctLearner.record_outcome_for_query` 已连到 `UnifiedRouter.record_feedback_outcome`（`context_mixin.py:114-126`），feedback-collect loop preset 每天 04:37 跑 decay/boost。**但** METRIC 仍断线——`MetricCondition` 模型存在于 `models.py:89`，`executor.py` 中 0 引用。不做元审计可以，但不能同时连写回触发都靠 cron-only。

### A3 内部矛盾——3 处文档 vs 代码不一致（P1）

| 文档声称 | 代码真相 | 严重度 |
|----------|----------|--------|
| "Memory ~85% 已发货" | recall/replay/skill_promote API 齐，但 gold detection 依赖 outcome 密度——outcome 只在 satisfaction feedback 写，不在 route 热路径写。无 outcome 则无 gold → recall 永远 non-gold → replay 永不触发。 | **高** |
| "METRIC 未接"（承认 GAP） | 确认：`MetricCondition` 模型孤岛，无消费者。 | 中（已知） |
| "SpanAggregator 已有消费" | `vibe trace metrics` CLI 可消费，但 loop tick 不调用。Aggregator 存在 ≠ 闭环存在。 | 中 |

### A4 P0 阻断——无（P2）

没有必须停止 Sprint 1 的单项阻断。但有**累积风险**：若 Sprint 1 的 4 个交付项都以 "scaffolding exist but not plumbed" 状态交付，14 天后 kill criteria 必定触发（0 accept/dismiss + 0 replay Y），浪费 2 周。

### A5 缺失 kill criteria——1 项（P1）

当前 kill：*"14 天 0 accept/dismiss AND 0 replay Y → stop"* 过于宽松。应加：

> **14 天 outcome density = 0**（`record_outcome` 在 route 热路径从未被调用）→ **先停扩 analyzer，修信号采集**。

原因：没有 outcome 就没有 gold → 没有 replay Y 可能。kill 条件不应惩罚 "无信号导致无动作"。

---

## Part B — Sprint 1 findings

### B1 Existing vs gap（逐项证据）

#### 1.1 Pending 人话建议队列（≤3条/天，中文可读）

| 已有 | 缺口 |
|------|------|
| `SkillSuggestionCollector` — pending/dismiss/created 生命周期完整（`suggestion_collector.py`） | 建议来源是 **sequence patterns**（工作流重复），非**低置信路由/用户纠正**。无 "路由置信度 < 0.5" → pending 的管道 |
| `vibe skills suggestions` — 列表 + `--dismiss` + `--json`（`_discovery.py:37-70`） | 无 `vibe instinct pending` 专令。brief 要求的 "列出 ≤3 条/日、可读中文" 对应 CLI 尚不存在 |
| `vibe instinct eval` → 自动推入 suggestion_collector（`instinct_cmd.py:157-162`） | 无 ≤3/日 限流。`_market_search_budget_allows` 有频率控制但仅用于 market-search |
| `vibe instinct feedback-collect` — decay/boost 基于 miss counter（`instinct_cmd.py:568-650`） | feedback-collect 调整 instinct 置信度，但 adjusted instinct 不产生 pending suggestion |

**实际完成度：30%**。Suggestion 基础设施有，但 "路由低置信 → pending" 的关键管道未建。

#### 1.2 accept / dismiss 写回生效路径

| 已有 | 缺口 |
|------|------|
| `UnifiedRouter.record_feedback_outcome` → `record_outcome_for_query`（`context_mixin.py:114-126`） | 仅在 orchestration satisfaction feedback 触发（`feedback.py:51`），不在 route 后触发——单路由 fast path 无 feedback prompt |
| `UnifiedRouter._record_routing_decision` 自动 learn query→skill（`unified.py:995-1005`）——**仅高置信度（≥0.7）** | 低置信路由**不**写 instinct，也不产生 pending。高置信才写，等于只记成功、不记可疑 |
| `dismiss()` / `dismiss_all()` 在 suggestion_collector（`suggestion_collector.py:192-198`） | dismiss 只影响 suggestion，**不写回路由层**（不影响 `_record_routing_decision`） |
| instinct confidence 更新通过 `Instinct.update(success)`——Wilson score（`learner.py:50-67`） | 置信度变化后，**下次 route 是否使用？**路由优先走 10 层匹配栈，instinct 不在热路径——`UnifiedRouter.route()` 不查询 `find_matching()` |

**关键发现**：accept/dismiss → "下次 route 更准" 的链条在代码中断了 3 处：
1. 单路由不 prompt feedback
2. 低置信路由不产生 pending
3. instinct 置信度变化后，路由路径不重新查询 instinct preference

**实际完成度：25%。**

#### 1.3 Replay 热路径默认可用

| 已有 | 缺口 |
|------|------|
| `should_replay` — gold match 检测（`replay.py:120-155`） | gold 依赖 `record_outcome`——outcome 只在 satisfaction feedback 写，单路由不写 → gold 罕见 |
| `_maybe_prompt_replay` — Y/n 提示 + emit span（`main.py:1912-1988`） | **Y 不注入 skill**（`main.py:1926`: explicit "Routing is unchanged"）——brief 要求 "Y 注入" 未实现 |
| `emit_replay_span` — provenance span（`replay.py:158-196`） | 无统计采用率——emit 后无 counter/metric |
| `--no-replay` flag（`main.py:540-543`） | 无 |

**实际完成度：40%。** scaffolding 完整但 gold 密度低 + injection 缺失。

#### 1.4 outcome 密度

| 已有 | 缺口 |
|------|------|
| `record_outcome` / `record_outcome_for_query`（`learner.py:450-468`） | 调用点仅 3 处：satisfaction feedback（`feedback.py:51`）、auto-promote（instinct_cmd）、feedback-collect（instinct_cmd）。**route 热路径 0 处调用** |
| `get_instinct_for_query`（`learner.py:470-482`） | 用于 gold detection，但因为 outcome 稀疏，gold 极少 |

**实际完成度：35%。** API 存在但调用点不足，outcome 密度取决于用户是否走 orchestration + 是否填 feedback——这对 fast-path `vibe route` 是空白。

### B2 Hazards（危险复用错误）

| # | 风险 | 细节 |
|---|------|------|
| **H1** | **conflating skill-suggestions with routing instincts** | `SkillSuggestionCollector` 管 sequence→skill draft（工作流模板化），Sprint 1 要的是 "这条路由错了/置信低"（路由质量反馈）。两个完全不同的对象、不同的写回目标。当前共用一个 collector 会污染 suggestion 队列 |
| **H2** | **replay 当作 injection** | brief 说 "Y 注入"，代码说 "Y ONLY emits provenance span"。若以 brief 为验收标准，交付即撒谎 |
| **H3** | **feedback-collect loop 等价于 accept/dismiss** | `vibe instinct feedback-collect` 是 cron 批量 decay/boost，不是用户交互式 accept/dismiss。不能拿 cron loop 假装 Sprint 1 交互路径已通 |
| **H4** | **`_record_routing_decision` 只记高置信（≥0.7）** | 等于只收集 "路由已经对了" 的信号，不收集 "路由可疑" 的信号。Sprint 1 需要的是后者 |

### B3 Minimal plan（≤8 steps if CONDITIONAL → GO after fixes）

```
STEP 0 [前置必须]: 修 `_maybe_prompt_replay` — Y 时注入 prior skill_id 到 candidate list
   文件: src/vibesop/cli/main.py#L1977-L1982
   
STEP 1: Route 热路径加 outcome 写（hit 时 success=True, miss/low-conf 时 success=False）
   文件: src/vibesop/core/routing/unified.py `_record_single_route_execution` 附近

STEP 2: 单路由 fast-path 后加轻量 feedback prompt（仅低置信/fallback）
   文件: src/vibesop/cli/main.py route 命令, `--no-replay` 块之后

STEP 3: 建 `vibe instinct pending` CLI — 列出 instinct 中 confidence < 0.5 的条目，中文
   文件: src/vibesop/cli/commands/instinct_cmd.py 新命令

STEP 4: 建 accept/dismiss 写回路径 — accept → `record_outcome(success=True)` + boost 
   confidence; dismiss → `record_outcome(success=False)`, 不静默重现
   文件: instinct_cmd.py + learner.py（已有 API，主要是 CLI 接线）

STEP 5: 加 ≤3/天 限流 — 在 collector 存 last_prompted_at，同一天超 3 条不推
   文件: src/vibesop/core/skills/suggestion_collector.py

STEP 6: Replay 统计 — `emit_replay_span` 后 counter++，写 `.vibe/instincts/replay_stats.jsonl`
   文件: src/vibesop/cli/main.py `_maybe_prompt_replay`

STEP 7: outcome 密度检查 CLI — `vibe instinct stats` 显示 outcome 写次数/日
   文件: instinct_cmd.py `status` 扩展或新命令

STEP 8: E2E smoke: 低置信 route → pending 出现 → accept → 同 query 再 route 置信度提升
   不写新代码，跑一遍验证整条链路。14 天 real-use 后检查 kill criteria。
```

### B4 Acceptance tests（可执行）

```bash
# AT1: outcome 写入
vibe route "测试查询" --json | jq '.primary.confidence'
# 断言: .vibe/instincts.jsonl 新增 1 行，success_count > 0

# AT2: 低置信 → pending
vibe route "模糊查询导致低置信" --json
vibe instinct pending
# 断言: 输出 1+ 条，含中文描述 + 置信度

# AT3: accept → 路由变化
vibe instinct accept <id>
vibe route "同 query" --json | jq '.primary.confidence'
# 断言: 置信度比 AT1 提高或 skill 选择变化

# AT4: dismiss → 不重现
vibe instinct dismiss <id>
vibe route "同 query"
# 断言: 24h 内同一 pending 不再次出现

# AT5: replay Y → 注入
# 先制造一次成功路由（outcome=success），再用相似 query：
vibe route "相似 query"
# 出现 Gold match prompt，按 Y
# 断言: emit_replay_span 被调用，路由结果含 prior skill_id

# AT6: ≤3/天 限流
# 连续触发 4 次 pending
vibe instinct pending
# 断言: 只显示 ≤3 条

# AT7: outcome 密度统计
vibe instinct stats
# 断言: 输出 "outcomes_per_day: N" 字段，N > 0
```

---

## Must-fix before code（if CONDITIONAL → GO）

- [ ] **FIX-1**: `_maybe_prompt_replay` Y 必须注入 prior skill_id 到路由候选（当前只 emit span）—— 否则 1.3 "Y 注入" 无法验收。文件: `main.py:1977`
- [ ] **FIX-2**: Route 热路径必须写 `record_outcome`——hit 写 success、miss/low-conf 写 failure。否则 gold detection 永远 0，replay 永不触发。文件: `unified.py` `_record_single_route_execution`
- [ ] **FIX-3**: 低置信路由（`confidence < 0.5`）必须产生 pending instinct——不能只记高置信（当前 `_record_routing_decision` 门控 `≥0.7`）。文件: `unified.py:998`
- [ ] **FIX-4**: Sprint 1 scope 明确排除 METRIC 全量和 Cytoscape（文档已说）——但不能假装 feedback-collect cron loop 等价于交互式 accept/dismiss。两个独立路径，Sprint 1 需要后者。

---

## Explicit non-blockers（things NOT required for Sprint 1）

- METRIC 接线（`MetricCondition × SpanAggregator × loop tick`）→ Sprint 3
- InsightAnalyzer 大框架
- Cytoscape / Dashboard 视觉
- `vibe task show` 完整 CLI
- 跨项目 memory
- Auto-write skill 进路由热路径
- Route-auditor 元审计 loop
- 漂亮 Map UI（树/JSON 足够）

---

**总结**：代码骨架质量高——`InstinctLearner`、`SkillSuggestionCollector`、`replay` 模块、loop presets 都是真实存在的工程资产。但 Sprint 1 要求的 **"路由反馈 → accept/dismiss → 下次更准"** 这条黄金路径在代码中是断的：outcome 不在路由热路径写、低置信不产生 pending、replay 不注入、instinct 变化后路由不重查。**4 个 must-fix 解决后可以 GO，否则 14 天后 kill criteria 必然触发。**
