先按路由协议匹配技能，再对照工作树核对第一轮 MAJOR 与修订稿事实。路由还在跑；同时开始核对修订稿与源码行号。路由命中 `kimi-gated-fix`，与只读设计复审不符；按用户指定的确认制流程核查工作树事实。对照第一轮 6 条 MAJOR 与新增 loader 暗道，开始抽查源码行号与语义。抽查完第一轮 6 条 MAJOR 对应正文与行号；expiry 驳回成立。新范围只剩 §2.2.10 的 `continue` 未钉死。## Verdict
PASS_WITH_NITS

## Findings
- [MAJOR] §2.2.10 只下令删 `set_lifecycle` 写入、测试只锁「discovery 不写生命周期」，没钉 `continue`。`loader.py:149-165` 在写入后立刻 `continue` 把技能踢出 `_skill_cache`。只删写入、留 `continue`，会得到新暗道：DEPRECATED≥90d 状态仍是 DEPRECATED，却按 `usage_stats.last_used` 从发现集消失（无 flag、无生命周期变化）。两种实现都满足现文案与现测试。须二选一写死：(a) 删整个 149-165 块（含 `continue`），DEPRECATED 不论 last_used 都留在 `discover_all` 返回值，ARCHIVED 仍走 `:166-167`；(b) 明确保留 last_used 隐藏并把它写成只读策略。测试必须断言可见性，不能只 `set_lifecycle assert_not_called`。路由命中不受影响——`lifecycle.py:85` / `candidate_manager.py:347-348` 已把 DEPRECATED 当不可路由；受影响的是发现集/索引（`candidate_manager.py:129`、`indexer.py:283,684`）。另外「显式 archive 能力经 stale --auto 的 archive 规则保留」不是等价替换：loader 谓词是 lifecycle==DEPRECATED ∧ `usage_stats.last_used`≥90d；`feedback_loop.py:154-155` 是 grade∈(C,D,F) ∧ `evaluation.last_used`≥90d。gate38 后 usage_stats-only 的 DEPRECATED 会变成 grade `"?"`，stale --auto 永远归档不到它们。
- [NIT] §1.1 hook 插入点 `agent_runtime.py:668` 在 span `has_match = result.router_matched`（`:692`）之前。`:671-675` 已写明 `result.has_match` 属性在 intercepted miss 上仍为 True。实施必须用 `result.router_matched`（或挪到 `:692` 之后），否则会在 hook miss 上写出 `["", alt…]`，把 r2「仅 has_match True 写键」打回第一轮脏数据。
- [NIT] `optimize_cmd.py:109-133` 展示路径只映射 deprecate/warn/boost，丢掉 archive。构造 bug 修好后 dry-run 预览不到 `--apply` 会执行的 archive（`:154-164`）。与 §2.3「三类动作全收集」同构，展示侧应对齐。

第一轮 grok-MAJOR-1…6 均已正确回写（§2.0 伤害链、§2.6 真实 `SkillEvaluation`、§2.1/§6 原子对、§2.2.8 两入口、§2.3 三类入 log、§2.2.6 dry-run must-NOT、§2.1 展示面、`population:"hook"` + 双挂点）。抽查行号属实：`loader.py:160-165`、`optimize_cmd.py:105/106/148-149`、`feedback_loop.py:66/119-155/196-208/246`、`evaluator.py:64-66/246-254`、`agent_runtime.py:619-626/668`、`cli/main.py:906/1707`、`tool_call_bridge.py:90/221/414-493/540`、`ci.yml:11/110`、`eval_routing.py:80/91/128/174`、`_health.py:156-162`、`status_cmd.py:38-43/70-72`、`_quality.py:102`、`GOALS.md:104`、`ARCHITECTURE.md:597`。

§1.2 驳回「expiry 仅增量生效」成立：要新日期常量且与 miss 侧回灌失对称；`reason` 前缀可滤；write-once 下延迟 expiry 只会把淹没从 T0 推迟约 24h，不是更优方案。
