# Lane F2 Handback — 技能消费分账（Pi）

**Status: DONE**

- Lane：F2（pi）· worktree `/Users/huchen/Projects/vibesop-distill-pi` · 分支 `feat/distill-f2` · 基线 `f57f7faa`
- 总计划：`docs/specs/2026-09-21-skill-distill-landing.md`（§4 文件所有权 / §6 完成定义 / §7 产品原则）
- 本 lane 任务书：`docs/specs/2026-09-21-distill-lane-pi.md`

---

## 1. 交付物

| # | 交付 | 路径 | 状态 |
|---|---|---|---|
| 1 | Phase 1 设计文档（含 `Status: DESIGN LOCKED`） | `docs/specs/2026-09-21-distill-f2-design.md` | 完成 |
| 2 | 消费分账模块（派生 + 落盘 + 读取 + 报告契约） | `src/vibesop/core/observability/skill_consumption.py`（新建，约 700 行） | 完成 |
| 3 | 装配期最小接线 | `src/vibesop/core/observability/tool_call_bridge.py`（+1 调用、+1 统计字段、+1 helper、docstring） | 完成 |
| 4 | CLI 子命令 | `src/vibesop/cli/commands/observe_cmd.py`（+`vibe observe consumption`） | 完成 |
| 5 | 文档级交叉引用（零行为变更） | `src/vibesop/core/observability/route_observe.py`（docstring 一段） | 完成 |
| 6 | 测试 | `tests/core/observability/test_skill_consumption.py`（新建，46 测试） | 完成 |
| 7 | 本 handback | `.omx/artifacts/distill-lane-f2-handback.md` | 完成 |

改动文件清单（`git status --short`，commit 前）：

```
 M src/vibesop/cli/commands/observe_cmd.py
 M src/vibesop/core/observability/tool_call_bridge.py
?? docs/specs/2026-09-21-distill-f2-design.md
?? src/vibesop/core/observability/skill_consumption.py
?? tests/core/observability/test_skill_consumption.py
```

**未越界**：没有改 `skill_injector.py`、`registry.yaml`、`promote`/`promote_verifier.py`、路由匹配器、
`benchmark.py`、`memory/project-knowledge.md`、`cli/main.py`、`agent_runtime.py`。

---

## 2. 产品结论（一句话）

论文建议 #3 的「分开记录选中、读到、适用、执行、验收」落成只读台账
`vibesop.observability.skill_consumption` v1：**5 段里只有 `selected` 本轮有事实，
`read` / `applicable` / `executed` / `accepted` 诚实置空（`state: null` + `reason`）**，
另附两枚明确标注的**代理**（`injection_attempted`、`read_like_tool_calls`），
并把这些空值写进测试钉死。R6 的「路由 2/2 no-match、SKILL.md 读取 0 次、总分 22/25」
在本台账上第一次可直接读出。

---

## 3. 实现要点（给合入者）

1. **五段信封**：`{"state": <值|null>, "reason": <str|null>, ...}`；`state=null` 必带非空 `reason`。
   理由码（测试钉住）：`missing_has_match` / `non_boolean_has_match` /
   `hit_without_real_skill_id` / `no_harness_receipt` / `not_observable` / `no_step_receipt` /
   `no_verification_receipt`。
2. **只落 `selected`**：由 route span 的 `metadata.has_match` / `skill_id` / `top_skills` /
   `demoted_skill_id` / `mode` 派生。`has_match=true` 但无真实 skill id（gate41 记录的洞）
   → `null` + `hit_without_real_skill_id`，**永不写成命中**。
3. **`read` 恒 `null`**：无生产者收据；`tool_sequences` 按隐私只存工具名，路径根本不存在。
   R6 的 10 次读类工具调用是「读过文件」而非「读过技能」，因此 `read_like_tool_calls`
   只作代理，测试有一条负向断言专门守住「不得提升为 `read.state`」。
4. **存储**：`.vibe/observability/skill_consumption.jsonl`（每 route span 一行）+ 一代轮转档
   `skill_consumption.0.jsonl`（8 MiB 触发，覆盖式）。读取 union 两档、`span_id` 活档优先。
   **零 query 原文**：只存 `task_id`（`sha1(normalize(query))[:16]`）；工具名沿用 bridge 的
   「只记名字」隐私级别。
5. **upsert 而非 write-once**：该 route span 名下的 tool_call 逐步桥接，`read` 代理会变完整；
   内容变化才写（`recorded_at` 保留首次值），无变化时**一个字节都不写**（mtime 不变，测试钉住）。
   与 `route_outcomes.jsonl` 的 write-once 语义**刻意不同**，理由写在模块 docstring。
6. **查询面**：`vibe observe consumption [--ledger|--route-span-id|--session|--task-id|--since|--until|--limit|--json]`，
   机器契约 `vibesop.observe.consumption` v1，**raw counts only**（无比率/评分/grade）。
   退出码 0 有报告（**账本缺失也是 0 + 空结构**）、2 用法错误、3 账本不可读；**没有 healthy/warn 判定**。
7. **接线最小**：`tool_call_bridge._run` 末尾一次 `_derive_consumption(root, stats)`（在
   `_derive_hit_outcomes` 之后，确保本轮的 tool_call span 已落盘）；`BridgeStats` 加
   `consumption_rows`。失败只记 debug 日志 + `stats.notes`，绝不打断装配。

---

## 4. 命令 + 退出码（本次实跑）

```bash
cd /Users/huchen/Projects/vibesop-distill-pi

# 1) lint
uv run ruff check src/ tests/ --quiet
# exit 0

# 2) 本 lane 新测试（spec 建议的 -k consumption 落在新模块名上）
uv run pytest tests/core/observability/ -q --tb=short -k "consumption or ledger"
# 46 passed, 650 deselected — exit 0

# 3) 相邻面回归（观测/路由观测/分层守卫）
uv run pytest tests/core/observability/ tests/unit/test_route_observe.py tests/architecture/test_layering.py -q --tb=short
# 937 passed, 1 skipped — exit 0

# 4) 宽回归 A
uv run pytest tests/core tests/unit tests/cli tests/architecture tests/hooks -q --tb=short
# 1 failed, 5652 passed, 4 skipped — exit 1（唯一失败为**既有**基线问题，见 §6）

# 5) 宽回归 B
uv run pytest tests/agent tests/conformance tests/scripts tests/integration -q --tb=line
# 542 passed, 10 skipped — exit 0

# 6) hermetic 指纹/基线（总计划硬边界：不得改变）
uv run python scripts/eval_routing.py --hermetic --check
# === Routing Baseline Check: OK (exit 0) ===
# entries matched: 59 | new-fails: 0 | new-passes: 0 | drift: 0 | known-fails: 6

# 7) 产物引用守卫
uv run python scripts/check_artifact_links.py
# check_artifact_links: 1108 reference(s) — 640 ok, 0 dangling, 468 stale. — exit 0
```

### CLI 端到端实跑（R6/R5 形状的合成 fixture，非生产数据）

```bash
uv run vibe observe consumption --ledger <tmp>/.vibe/observability/skill_consumption.jsonl
```

```
skill consumption ledger (vibesop.observability.skill_consumption v1)
generated_at: 2026-09-21T03:03:58.429111+00:00
ledger: path=…/skill_consumption.jsonl rotated=…/skill_consumption.0.jsonl exists=True mtime=1789959837.6942267
filters: span_id=None session_id=None task_id=None since=None until=None limit=20
counts: n_rows=3 n_rotated_rows=0 n_matched=3 n_printed=3 n_corrupt=0 n_skipped=0 n_no_ts=0
selected: yes=1 no=2 unknown=0 reasons={}
read: unknown=3 reasons={"no_harness_receipt": 3} injection_attempted=1 injection_unknown=0 read_like_tool_calls=10 rows_with_read_like_tool_calls=1
applicable: unknown=3 reasons={"not_observable": 3}
executed: unknown=3 reasons={"no_step_receipt": 3}
accepted: unknown=3 reasons={"no_verification_receipt": 3}
rows (3 of 3):
  span=r6r0 ts=2026-09-21T02:58:36+00:00 pop=hook selected=no(-) read=None(no_harness_receipt) injection=False read_like=10
  span=r6r1 ts=2026-09-21T02:59:36+00:00 pop=hook selected=no(-) read=None(no_harness_receipt) injection=False read_like=0
  span=r5r0 ts=2026-09-21T03:58:36+00:00 pop=hook selected=yes(superpowers-test-driven-development) read=None(no_harness_receipt) injection=True read_like=0
note: raw counts only: this ledger records what happened to skill consumption, not whether skills helped (no rates, no success score, not a gate)
```

读法（对应设计文档 §7）：两次 R6 形状的路由都是 `selected=no` 且 `injection_attempted=false`
（没命中 ⇒ 正文根本不会进 `additionalContext`），那 10 次读类工具调用摆在 `read_like=10` 上，
而 `read.state` 仍是 `None`。R5 形状的命中行则是 `selected=yes` + `injection_attempted=true`，
`read.state` 依旧 `None`。**「命中」与「读到」在同一条记录里被分开，且都没有被夸大成效用。**

---

## 5. 测试证据（46 条，重点）

- 真实形状 fixture：route span 经 `SpanWriter` 写（`metadata` 为 JSON 字符串），另有一条用
  `Span.to_dict()`（`metadata` 为 dict）写盘，覆盖两种线上形状；**不手搓 key**。
- 诚实空值负向断言：四段的 `state is None` + 精确 `reason`；R6 形状（10 次读类工具调用）
  下 `read.state` 仍为 `None`；`read` 段不存在 `skill_read` / `skill_path` 之类伪字段。
- 代理分离：CLI 标记（`platform="vibe-cli"` 或 `source="cli"`）即使命中 `injection_attempted=False`；
  读类白名单大小写不敏感、白名单外工具名只进 `tools` 不计数；只统计 `parent_span_id` 指向该
  route span 的 `tool_call` span。
- 落盘：幂等（二次运行 0 行、内容与 mtime 不变）、tool_call 后补时刷新且保留 `recorded_at`、
  spans 文件消失后旧行保留、轮转档生成、坏行被丢弃、**账本不含 query 原文**（sentinel 断言）。
- 查询：缺账本 fail-soft `exit 0` + 空结构、账本不可读 `exit 3`、坏时间戳 `exit 2`、
  窗口丢无时间戳行计入 `n_no_ts`、活档优先于轮转档、坏行/缺 `span_id` 分别计数、
  同输入两次报告 JSON 完全一致（固定 `now`）。
- 契约守卫：报告顶层键集合固定；序列化文本不得出现 `rate`/`ratio`/`score`/`grade`/`success`
  之类字段名（「不把分账当成功率」的可执行化）。
- 装配接线：经 `bridge_entries(...)` 真跑一次，`stats.consumption_rows == 1` 且该行
  `read_like_tool_calls == 1`。
- 项目既有守卫：`tests/core/observability/test_no_bare_asserts.py`（新模块零 `assert`）、
  `tests/architecture/test_layering.py`（新模块只依赖 core + 标准库）均通过。

---

## 6. 「我无法验证的部分」（诚实清单）

1. **生产账本未跑过**：本 worktree 没有真实 `.vibe/observability/spans.jsonl` 流量，
   端到端只用了合成 fixture。真实 hook 会话下的字段分布（尤其 `route_population` 的 hook/cli 比例）
   需要 grok 在主仓实跑一次 `vibe observe consumption` 才作数。
2. **注入是否真进模型上下文未验证**：`injection_attempted` 只断言 hook 路径把正文交给了 harness
   （`additionalContext`），不验证平台是否应用该字段、更不验证模型是否读了。这正是 `read.state`
   恒为 `null` 的原因，不是遗漏。
3. **`applicable` / `executed` / `accepted` 完全不可观测**：见设计文档 §2.3–§2.5 与 §9 的后续生产者清单。
4. **`vibe data purge` 无 observability 目标**（既有缺口，非本轮引入）：`spans.jsonl` /
   `route_outcomes.jsonl` / 本新账本都不在 purge 目标里（`data_cmd.py` 的 targets 只有
   analytics/traces/preferences/instincts/memory/sessions/miss-counter/tool-sequences/feedback/pack-locks）。
   账本不含 query 原文，风险等级与既有文件相同；是否单开一轮补齐 purge 目标由 grok 定。
5. **一项既有测试失败（非本 lane 引入，已亲证）**：
   `tests/unit/test_check_artifact_links_baseline.py::test_committed_baseline_matches_current_stale_multiset`
   在本分支基线 `f57f7faa` 上就失败：`assert 1108 == 1109`（FROZEN_REF_TOTAL 冻结值比当前扫描多 1 条
   `ok` 引用；stale 468 条一致）。验证方法：`git worktree add --detach /tmp/f2-base f57f7faa` 后在
   干净检出里跑同一测试，得到**同样的 1108 vs 1109**。**我没有改它**（该文件与 `ci/artifact-links-baseline.json`
   归 F9/grok 处理）。注意：本 lane 新增的 tracked 文档会引用 3 处 `.omx/artifacts/`（
   `skill-distillation-review-20260921.md`、`ab-jet-weak-report-r6.md`、本 handback）——实测守卫
   从 `1108 reference(s) — 640 ok, 0 dangling, 468 stale` 变为 `1111 reference(s) — 643 ok, 0 dangling,
   468 stale`（**只增 `ok`，0 dangling、stale 不一致**，exit 0）。合入后如要重新冻结
   `FROZEN_REF_TOTAL`，请把这次 +3（以及上面那 1 条既有缺口）一并计入。
6. **并发未加锁**（沿用既有约束）：`record_consumption` 与 bridge 的 state/outcomes 一样是
   「单读取者 + 手动重跑」假设下安全的；上日程/并发前必须补跨进程锁（bridge 的 gate16b 说明已记录）。
7. **未做性能剖析**：装配期多一次 O(spans) 全扫 + 仅在内容变化时的整档重写；hook 热路径零影响
   （账本只在装配期写）。未实测大盘（百万行 span）下的重写耗时。

---

## 7. 对 hermetic / CI / promote「灯不是闸」的影响

- **hermetic**：`scripts/eval_routing.py --hermetic --check` → `OK (exit 0)`，`new-fails: 0`、
  `new-passes: 0`、`drift: 0`、`entries matched: 59`。指纹未变（未碰 `benchmark.py`、
  registry、技能正文、评测集）。
- **CI**：零新 required job、零新 workflow 改动、零阈值/评测集改动。新增文件只在
  `src/`、`tests/`、`docs/specs/`、`.omx/artifacts/`。
- **promote「灯不是闸」**：不受影响——账本既不参与 promote 判定，也不被 promote 读取；
  没有新增 WARN/FAIL 语义。
- **route_observe**：只加 docstring 交叉引用；`vibesop.observe.routing` v1 契约、退出码、
  阈值全部未动（`tests/unit/test_route_observe.py` 全绿）。
- **既有行为**：`tool_call_bridge` 的 span/outcome 输出与判据一字未改；新增的只是装配末尾
  多写一个文件（并且内容不变时不写）。

---

## 8. 建议 grok 写入 `memory/project-knowledge.md` 的 F2 条目草稿

```markdown
### F2 消费分账：命中 ≠ 读到，读文件 ≠ 读技能（lane F2 / pi，2026-09-21）

- 论文建议 #3「分开记录选中、读到、适用、执行、验收」落成 `vibesop.observability.skill_consumption` v1：
  `.vibe/observability/skill_consumption.jsonl`（每 route span 一行，装配期 upsert，含一代轮转档 `.0.jsonl`，
  读取时活档优先）。查询：`vibe observe consumption [--session|--task-id|--route-span-id|--since|--until|--limit|--json]`。
- 本轮 5 段里只有 `selected` 有事实（route span 的 `has_match`/`skill_id`/`top_skills`）；
  `read`/`applicable`/`executed`/`accepted` **诚实置空**（`state: null` + 固定 `reason`），测试把这些空值钉死。
  没有 harness 收据就不编「读到了」——论文「读取 ≠ 有效」的字面落地。
- 两枚**代理**（永不得提升为 `read.state`）：`injection_attempted`（hook 命中 ⇒ 正文交给了 harness）
  与 `read_like_tool_calls`（该 route span 名下的读类工具调用数）。R6 的 10 次读全给了 TASK.md 与自家产物，
  证明读文件 ≠ 读技能；R6 两行账面即 `selected=no` + `injection_attempted=false` + `read=None`。
- 纪律：账本与 CLI **raw counts only**（无比率/评分/grade，测试用负向断言守住），
  账本缺失 fail-soft `exit 0` + 空结构，无 healthy/warn 判定；不改匹配分数、不改注入正文、不当门禁。
- 已知缺口（交后续 lane）：`read` 需要生产者收据（hook 写注入路径/长度，或 survey §9.3 主臂的
  token 差双侧对账）；`accepted` 需要 verify-result 裁决进 span metadata；
  `vibe data purge` 尚无 observability 目标；账本写入未加跨进程锁（沿用 bridge 的既有约束）。
```

---

## 9. 后续动作清单（交给 Wave 1.5 / grok，不在本 lane 实施）

1. 合入本分支到 worktree 后，在主仓跑一次真流量：`vibe sequence assemble` 或正常 `vibe route`，
   再 `vibe observe consumption --json` 看真实分布。
2. 用户可见文档：`docs/user/CLI_REFERENCE.md`、`docs/user/COMMAND_HANDBOOK.md` 补
   `vibe observe consumption` 条目（本 lane 文件所有权不含这些文档，故未写）。
3. `tests/unit/test_check_artifact_links_baseline.py` 的冻结总数按 §6.5 重新冻结。
4. 决定是否单开一轮补齐 `vibe data purge` 的 observability 目标（含本账本、spans、route_outcomes）。
5. 生产级 `read` 收据与 `accepted` 对齐契约见设计文档 §9（需要 `agent_runtime` / 验证链的 owner 参与）。
