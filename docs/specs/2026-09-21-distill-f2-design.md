# Lane F2 设计 — 技能消费分账（Pi）

**Status: DESIGN LOCKED**

- Lane：F2（pi）· worktree `/Users/huchen/Projects/vibesop-distill-pi` · 分支 `feat/distill-f2`
- 基线：`f57f7faa`
- 上游：`docs/specs/2026-09-21-skill-distill-landing.md`（总计划 §4/§7）、
  `docs/specs/2026-09-21-distill-lane-pi.md`（本 lane 任务书）、
  `docs/research/2026-09-09-agent-skills-paper.md` 建议 #3、
  `docs/research/research-survey.md` §7 F2 / §9.3、
  `.omx/artifacts/skill-distillation-review-20260921.md` P1「F1/F2/F9 未沉淀为技能或机制」
- 产品原则约束（总计划 §7）：**消费证据优先于评分**；分账是「技能有没有进上下文」的前置判据，
  **不是**新的成功率分数；零新 CI 门禁；不改匹配分数、不改注入正文。

本文锁定 Phase 2 的实现契约。顶部 `Status: DESIGN LOCKED` 之后才动 `src/`。

---

## 0. 一句话

把论文建议 #3 的「分开记录选中、读到、适用、执行、验收」落成一条**只读、只记事实、绝不外推**的
消费分账：`selected` 本轮真落，`read / applicable / executed / accepted` 本轮**诚实置空**
（`state: null` + `reason`），另附两枚**明确标注为代理变量**的旁证（注入尝试、读类工具调用数），
让 R6 那种「路由赢了但技能根本没进上下文」在账本上第一次可见。

---

## 1. 为什么需要分账（判据来源）

R6（`ab-jet-weak-report-r6.md` §3 P4/§4）与 R5 的同题对照：

| 观测 | R5（强模型） | R6（弱模型） | 说明 |
|---|---|---|---|
| `vibe route` 调用 | 5 | 2（hook +1.5min、模型自调 +44min） | 两臂都调过路由 |
| 路由命中 | 有命中 | **2/2 no-match**（`selected_skill: null`） | 瓶颈在路由层 |
| SKILL.md 读取 | **80 次** | **0 次** | 技能内容从未进入上下文 |
| 工具调用中的「读」类 | — | 10 次（目标是 `TASK.md` 与自己的产物） | **读 ≠ 读技能** |
| 总分 | 23.5 / 25 | 22 / 25 | 表面接近 |

结论链：`22/25 ≈ 23.5` 若不查消费就会写成「弱模型 + 技能 ≈ 强模型」。**R6 那 10 次读类工具调用
一次都没读 SKILL.md** —— 这直接钉死了本设计的两条纪律：

1. 分账必须**分段**：命中（selected）不能替代读到（read）。
2. 读类工具调用只能当**代理变量**，永远不能把 `read.state` 写成 `yes`。

---

## 2. 五段操作定义（生产者 / 数据源 / 何时记 / 缺测时的值）

统一信封：每段 = `{"state": <值|null>, "reason": <str|null>, ...段内附加证据}`。
**`state` 为 `null` 时 `reason` 必非空**（诚实空值必须自带理由，不许裸 `null`）。

### 2.1 `selected` — 路由选中（本轮落地）

| 项 | 定义 |
|---|---|
| 生产者 | route span 生产者（`agent/runtime/agent_runtime.py:handle_query`、`cli/main.py` 的 `vibe route` 路径）；本轮**不新增生产者** |
| 数据源 | route span（`span_kind="task"` ∧ `name.startswith("route:")`）的 `metadata.has_match` / `metadata.skill_id` / `metadata.top_skills` / `metadata.demoted_skill_id` / `metadata.mode` |
| 何时记 | 消费账本**装配期**（`tool_call_bridge` 的 assembly fan-out）派生并落盘，不在 hook 热路径 |
| 取值 | `yes`：`has_match is True` ∧ `skill_id` 非空且 ≠ `fallback-llm`；`no`：`has_match is False`；`null` + `reason`：见下表 |
| 缺测时的值 | `null` + `reason`（三种：`missing_has_match` / `hit_without_real_skill_id` / `non_boolean_has_match`） |

附加字段（同一段内，取自 span，不额外推断）：

- `primary`：`metadata.skill_id`（字符串，原样；可能为空串）
- `skill_ids`：`[skill_id, *metadata.top_skills]` 去重保序、剔除 `""` 与 `fallback-llm`、≤3
- `demoted_skill_id`：命中但正文加载失败被降级时非空（「装坏了」≠「没命中」，沿用 M12 口径）
- `mode`：`metadata.mode`

明确**不写** `selected.state=yes` 的两种情形（宁缺毋滥）：

- `has_match is True` 但 `skill_ids` 为空（gate41 记录过的 `has_match=true ∧ skill_id=""` 洞）→
  `state: null, reason: "hit_without_real_skill_id"`；
- `has_match` 不是 bool（pre-W5.0 span、CLI 错误路径）→ `state: null, reason: "non_boolean_has_match"`。

### 2.2 `read` — SKILL.md 进入上下文 / 被读（**本轮只能 `null`**）

| 项 | 定义 |
|---|---|
| 生产者 | **不存在**。hook 路径把正文塞进 `additionalContext`（`AgentRuntimeResult.to_hook_response`），但**没有任何生产者把「注入发生/正文长度/被读」写进 span 或账本**；`tool_sequences` 按隐私规则只存 `{"tool","ts","session"}`，**永不存 `tool_input`**（含路径） |
| 数据源 | 无 → `state: null, reason: "no_harness_receipt"` |
| 何时记 | 每行都写这一空值（不是省略键） |
| 缺测时的值 | `state: null`，`reason: "no_harness_receipt"` |

`read.evidence` 里附两枚**代理变量**（都不得提升为 `state`）：

| 代理 | 定义 | 能证明什么 | 不能证明什么 |
|---|---|---|---|
| `injection_attempted` | `selected.state=="yes"` ∧ `route_population=="hook"`（bool；hook 路径会把正文作为 `additionalContext` 交出去） | 正文**被交到 harness 手上** | harness 是否真把它放进模型上下文；模型是否读了 |
| `read_like_tool_calls` / `tools` | 该 route span 名下已桥接的 `tool_call` span（`parent_span_id == route span id`）中，工具名命中读类白名单的数量与去重工具名 | 这一轮**发生过文件读取**（R6 的 10 次） | **读了哪个文件**（路径不存在于任何工件中）——R6 的 10 次读全是 TASK.md 与自家产物 |

读类白名单（保守、大小写不敏感，只收录已知平台的读工具名）：
`read` / `read_file` / `readfile` / `view` / `view_file`。白名单外的一律不计（宁可少算）。
`tools` 记录该 route span 下**全部**工具名（去重排序），让消费者自己判断，而不是让白名单替它判断。

> 为什么不做「canary 计数」或「prompt token 差对账」：survey §9.3 已写明 token 差对账需要注入前后的
> 双侧埋点（属于生产者改造，不在 F2 可写面）；canary 只能测「记得住」，测不出「按流程做事」。
> 两者都留给后续 lane，见 §9。

### 2.3 `applicable` — agent 判定适用（**本轮只能 `null`**）

| 项 | 定义 |
|---|---|
| 生产者 | 不存在。没有任何 harness 上报「agent 认为该技能适用于本任务」的自评 |
| 数据源 | 无 → `state: null, reason: "not_observable"` |
| 何时记 | 每行都写这一空值 |
| 缺测时的值 | `state: null`，`reason: "not_observable"` |

**不假装能测**：任务书明写「不要假装能测『适用』」。任何用关键词/相似度反推「适用」的做法都是
把未验证启发式塞进账本，且会重新引入总计划禁止的「用弱启发式当闸」的同类错误。

### 2.4 `executed` — 按技能步骤做事的证据（**本轮只能 `null`**）

| 项 | 定义 |
|---|---|
| 生产者 | 不存在。orchestrate 计划的步骤级执行/验证结果存在 `plan.steps[*].verification_result`，但 **plan 对象不写入 span metadata**，也不落盘到任何 `.vibe/` 工件 |
| 数据源 | 无 → `state: null, reason: "no_step_receipt"` |
| 何时记 | 每行都写这一空值 |
| 缺测时的值 | `state: null`，`reason: "no_step_receipt"` |

说明：`read_like_tool_calls > 0` **不是** executed。R6 有 10 次读、88 次工具调用，依然没有按任何技能
步骤做事（技能从未进上下文）。工具活动 ≠ 步骤执行，本轮绝不外推。

### 2.5 `accepted` — 验收通过（**本轮只能 `null`**）

| 项 | 定义 |
|---|---|
| 生产者 | 不存在。`builtin/verify-result` 的裁决在 orchestrate 计划里，未落到 span；`route_outcomes.jsonl` 的
`weak_positive` 是**弱先验信号不是标签**（`tool_call_bridge` 明确「weak prior signals, not labels」），拿它当验收是通过伪证 |
| 数据源 | 无 → `state: null, reason: "no_verification_receipt"` |
| 何时记 | 每行都写这一空值 |
| 缺测时的值 | `state: null`，`reason: "no_verification_receipt"` |

**与 verify-result 的对齐契约（本轮只留位，不接线）**：未来生产者把验证裁决写进
route span `metadata["verification_result"]`（形状：`{"status": "pass"|"fail"|"blocked", "skill_id": "builtin/verify-result"}`）后，
本段取值规则为 `status=="pass" → state:"yes"`、`"fail"/"blocked" → state:"no"`、缺键 → 现空值。
**不新门禁**：该字段只进账本，不参与任何 exit code、CI job 或 promote 判定。

---

## 3. 本轮能落地 vs 只能 `unknown`（诚实清单）

| 段 | 本轮状态 | 依据 |
|---|---|---|
| `selected` | **落地**（`yes` / `no` / `null+reason`） | route span 已有该事实，纯派生 |
| `read` | **`null`** + `reason:"no_harness_receipt"`（附 2 枚标注代理） | 无生产者收据；`tool_sequences` 按隐私不存路径 |
| `applicable` | **`null`** + `reason:"not_observable"` | 无自评信号；拒绝启发式冒充 |
| `executed` | **`null`** + `reason:"no_step_receipt"` | plan 步骤结果不进 span |
| `accepted` | **`null`** + `reason:"no_verification_receipt"` | 无验证收据；弱信号不可当验收 |

即：**5 段里 1 段有事实、4 段是诚实空值**。这不是未完成，这是本轮的唯一诚实答案——
论文的要求是「分开记录」，不是「假装都测到了」。测试会把这些空值连同 `reason` 一起钉住
（§6），任何未来的 `state` 提升都必须先改测试、再改生产者。

---

## 4. 存储

### 4.1 路径与轮转

| 文件 | 路径 | 说明 |
|---|---|---|
| 活账本 | `<project_root>/.vibe/observability/skill_consumption.jsonl` | 每 route span 一行，JSONL |
| 轮转档 | `<project_root>/.vibe/observability/skill_consumption.0.jsonl` | 仅保留一代，覆盖式；`MAX_LEDGER_BYTES = 8 MiB` |

- **无 dev/prod 变体**：与 `route_outcomes.jsonl` 一致（只有 `spans.jsonl` 有 `spans.dev.jsonl`），
  已知不对称，沿用 gate39 §4.7 先例，不新造规则。
- 轮转时机：upsert 写入前，若活账本已超 `MAX_LEDGER_BYTES` → 重命名到 `.0.jsonl`（覆盖旧档），
  活账本从空开始。总占用 ≤ ~2× 上限，与 `tool_sequences` 的「保留一代」惯例同构。
- 读取（CLI）：**活账本 ∪ 轮转档**，同一 `span_id` 以**活账本优先**（确定性去重），
  按 `route_started_at`（缺失则 `recorded_at`）升序、`span_id` 次序稳定排序。
- 文件缺失 → 空账本（**不 mkdir**，与 `skill_health` / `skill_outcomes` 只读模型惯例一致）。

### 4.2 行 schema（v1）

```json
{
  "schema": "vibesop.observability.skill_consumption",
  "schema_version": 1,
  "span_id": "…",
  "trace_id": "…",
  "task_id": "…",
  "session_id": "…",
  "agent_id": "claude-code",
  "project_id": "default",
  "route_started_at": "2026-09-21T02:58:36+00:00",
  "route_population": "hook",
  "mode": "single",
  "selected":   {"state": "yes", "reason": null, "primary": "…", "skill_ids": ["…"], "demoted_skill_id": null, "mode": "single"},
  "read":       {"state": null, "reason": "no_harness_receipt",
                 "evidence": {"injection_attempted": true, "read_like_tool_calls": 0, "tools": []}},
  "applicable": {"state": null, "reason": "not_observable"},
  "executed":   {"state": null, "reason": "no_step_receipt"},
  "accepted":   {"state": null, "reason": "no_verification_receipt"},
  "recorded_at": "2026-09-21T03:10:00+00:00"
}
```

- `route_population` ∈ `hook` | `cli`（判定与 `tool_call_bridge._CLI_PLATFORM` 保持同一口径，
  代码内互相交叉引用注释；CLI span 不产生注入，故 `injection_attempted` 恒 `false`）。
- 不写行的 span：`mode ∈ {"not_intercepted","slash_command"}`（不是路由尝试，与 bridge 的
  池判据同口径）；非 route span；`span_kind != "task"`。
- 行内**没有** `query` 文本（见 §4.3）。

### 4.3 隐私

- **零 query 原文**：账本只存 `task_id`（`derive_task_id` = `sha1(normalize(query))[:16]`，
  纯派生、截断安全、跨进程可算）。span 里的 `metadata.query[:200]` **不复制**。
- `session_id`：harness 会话 UUID，`route_outcomes.jsonl` 已有同口径先例，保留（session 级查询需要）。
- 工具名：`tool_call_bridge` 已确立「只记工具名，永不记参数/路径/响应」，账本沿用同一隐私级别；
  `tools` 因此只可能出现 `Read` / `Bash` 这类名字。
- 已知缺口（不在本 lane 可写面）：`vibe data purge` 目前**没有** observability 目录的清理目标
  （`spans.jsonl` / `route_outcomes.jsonl` 同样没有）。账本不含 query 原文，风险等级与既有文件相同；
  建议在 handback 交给 grok 决定是否单开一轮补齐 purge 目标。

### 4.4 幂等与并发（upsert，不是 append-once）

- **upsert 语义**：每次装配期重算被扫描到的 route span 的行；内容有变化才写。
  span 消失（`spans.jsonl` 已轮转）的旧行**原样保留**，不删。
  > 与 `route_outcomes.jsonl` 的 write-once 不同是**刻意的**：outcome 一旦可判定就永不改变，
  > 而消费账本的 `read.evidence` 会随该 route span 名下 tool_call span 陆续桥接而变得更完整；
  > write-once 会把「读类工具调用尚未桥接」的中间态永久冻住，那才是失真。
- **无内容变化则一个字节都不写**（文件 mtime 不变）——测试钉住。写入用 `vibesop.utils.atomic_writer.write_text`
  （与 `tool_call_bridge_state.json` 同例）。
- 并发：与 bridge 现状一致——装配期是唯一读取者，`run_bridge` 仅手动；
  **未加跨进程锁**，沿用 bridge 的 gate16b 说明（上日程前必须补锁）。本 lane 不引入新的调度。

---

## 5. 查询面（CLI）

```bash
vibe observe consumption [--ledger PATH] [--route-span-id ID] [--session ID] [--task-id ID]
                         [--since ISO] [--until ISO] [--limit N] [--json]
```

- 默认 `--ledger` = `<cwd>/.vibe/observability/skill_consumption.jsonl`。
- 过滤器可叠加（AND）；`--route-span-id` 精确匹配 `span_id`。半开窗口 `[--since, --until)`，
  naive 时间按 UTC 读（与 `route_observe.parse_window` 同口径），`since >= until` → 用法错误。
- 输出机器契约 `vibesop.observe.consumption` v1：

```json
{
  "schema": "vibesop.observe.consumption", "schema_version": 1,
  "generated_at": "…",
  "ledger": {"path": "…", "rotated_path": "…", "exists": true, "mtime": 1234567890.0},
  "filters": {"span_id": null, "session_id": null, "task_id": null,
              "since": null, "until": null, "limit": 20},
  "counts": {"n_rows": 12, "n_rotated_rows": 3, "n_matched": 12,
             "n_printed": 12, "n_corrupt": 0, "n_skipped": 0},
  "segments": {
    "selected":   {"yes": 1, "no": 11, "unknown": 0},
    "read":       {"unknown": 12, "injection_attempted": 1,
                   "read_like_tool_calls": 10, "rows_with_read_like_tool_calls": 4},
    "applicable": {"unknown": 12},
    "executed":   {"unknown": 12},
    "accepted":   {"unknown": 12}
  },
  "rows": [ … ]
}
```

- **raw counts only，无任何比率/百分比/评分**（与 `skill_health` / `skill_outcomes` 同一纪律）。
  分账不当成功率：账本里没有分母分子，也没有 grade。
- `segments.*` 只统计 `n_matched` 命中的行；`read.read_like_tool_calls` 是求和（不是行数），
  `rows_with_read_like_tool_calls` 才是行数——两者分开，避免把「10 次读」误读成「10 行读过技能」。
- **fail-soft**：账本不存在 → `exists: false` + 空 `rows` / 全 0 `segments`，`exit 0`。
- 退出码：`0` 报告已产出（含空）；`2` 用法错误（坏时间戳 / `since>=until` / `limit<0`）；
  `3` 故障（账本存在但读不动，`error.kind="unreadable_ledger"`）。
  **没有 healthy/warn 判定**，因此不存在「分账不健康」这种退出码——它不是闸。
- 人类可读渲染：逐行打印 `span_id / route_started_at / selected / read / …`，末尾打印 counts 与
  segments 计数 + 一句「这是事实台账，不含成功率」的说明。

`route_observe.py` 只加**文档级**交叉引用（说明账本与 routing observer 的分工），不改行为、不改字段。

---

## 6. 测试计划（钉真实形状，不手搓 key）

落点：`tests/core/observability/test_skill_consumption.py`（+ 复用 `test_tool_call_bridge.py` 的
fixture 风格）；CLI 契约测试并入该文件（`typer.testing.CliRunner`，与 `tests/unit/test_route_observe.py` 同法）。

纪律（项目既有）：fixture 用**真实 `Span.to_dict()` / `SpanWriter` 序列化形状**产出
（`metadata` 在 SpanWriter 里是 JSON 字符串、`to_dict` 里是 dict，两种都要覆盖），
**不手搓 key**；不允许裸 `assert` 落在 `src/vibesop/core/observability/`（已有 guard 测试）。

必测项：

1. **派生**：`has_match=True` + `skill_id` → `selected.state=="yes"`，`skill_ids` 去重保序、剔 `fallback-llm`；
   `has_match=False` → `"no"`；缺键 / 非 bool / `has_match=True` 且 `skill_id==""` → `null` + 三条不同 `reason`。
2. **诚实空值（负向断言，最关键）**：`read/applicable/executed/accepted` 的 `state is None` 及其
   `reason` 精确字符串；并断言**不存在**把 `read_like_tool_calls>0` 或 `injection_attempted` 提升为
   `read.state` 的路径（R6 形状：命中为 `no` 但有 10 次读类工具调用 → `read.state` 仍是 `null`）。
3. **代理分离**：`injection_attempted`：hook span + 命中 → `true`；CLI span（`platform="vibe-cli"` 或
   `source="cli"`）即使命中 → `false`；`read_like_tool_calls` 只数 `parent_span_id` 指向该 route span 的
   `tool_call` span，且白名单大小写不敏感，白名单外工具名（`Bash`/`Edit`）不计入但出现在 `tools` 里。
4. **落盘**：经 `bridge_entries`/`run_bridge` 装配后账本文件存在、行数 = route span 数；
   再次运行**不变**（幂等，mtime 不变）；路由 span 新增 tool_call 后重跑 → 该行 `read.evidence` 更新，
   其余行不动。
5. **跳过口径**：`mode="not_intercepted"` / `"slash_command"` 不产生行；非 route span、`span_kind!="task"` 不产生行。
6. **读取/查询**：活账本 ∪ 轮转档去重（活优先）；坏行计入 `n_corrupt` 且不炸；缺 `span_id` 的行计入 `n_skipped`；
   窗口/过滤器/limit 行为；排序确定性（同输入两次调用 JSON 完全相等）。
7. **fail-soft 与退出码**：账本不存在 → `exit 0` + `exists:false` + 空结构；
   账本是目录/不可读 → `exit 3` + `error.kind`；坏时间戳 → `exit 2`。
8. **隐私回归**：账本任意一行序列化文本**不含** query 原文（用 sentinel query 串断言），
   只含 `task_id`；不含 `tool_input`。
9. **轮转**：写超过 `MAX_LEDGER_BYTES`（用 monkeypatch 缩小阈值）→ 生成 `.0.jsonl`，活账本重置，
   读侧 union 仍能看到被轮转的行。

---

## 7. 用 R6 反推：这一轮账本会打印什么（自检）

假设 R6 的两条 route span 与那批工具调用进了本账本（hook 路径、session 均为宿主 UUID）：

| 字段 | 值 | 读法 |
|---|---|---|
| `selected.state` | `"no"` ×2 | 路由 2/2 no-match（与 R6 记录一致） |
| `read.state` | `null`（`no_harness_receipt`） | 没有收据，不编 |
| `read.evidence.injection_attempted` | `false` ×2 | 没命中就不会有 `additionalContext` → 技能注定进不了上下文 |
| `read.evidence.read_like_tool_calls` | 10（分布在该 session 的工具调用上） | 「读过文件」但**一条 SKILL.md 都不在其中** |
| `applicable/executed/accepted` | `null` ×2 | 不可观测 |

这张表现在能**直接反驳**「弱模型 + 技能 ≈ 强模型」：`selected=no` + `injection_attempted=false`
说明技能内容注定缺席，22/25 不可能是技能带来的。这正是分账要产出的一句话。

---

## 8. 非目标（本 lane 明令不做）

1. 不改路由匹配分数、阈值、注册表、评测集（`skill_id` 只读）。
2. 不改注入正文/注入策略（`skill_injector.py` 归 F1，本 lane 只读）。
3. 不当 CI 门禁、不加 required job、不改 `benchmark.py` 的 `HERMETIC_POSTURE`/指纹吸收守卫。
4. **不把分账当成功率**：账本与 CLI 输出里没有比率、没有评分、没有 grade、没有 disposition 建议。
5. 不改 `promote` 与「灯不是闸」语义（归 F9）。
6. 不用启发式反推 `applicable`/`executed`/`accepted`，也不把 `injection_attempted` 或读类工具调用
   提升为 `read.state`。
7. 不写 `memory/project-knowledge.md`（F 系 warm 层由 grok 合入后统一写）。

---

## 9. 影响面说明（hermetic / CI / promote）

- **hermetic 指纹**：本 lane 不改 `src/vibesop/core/routing/**`，不新增技能、不改 registry.yaml，
  指纹不应变（Phase 2 验收会实测并在 handback 贴结果）。
- **CI**：零新 required job；新增文件只有 `src/`、`tests/`、`docs/specs/`（本文件）、`.omx/artifacts/`（handback）。
- **promote「灯不是闸」**：不受影响——账本不参与 promote 判定，也不被 promote 读取。
- **route_observe**：仅文档级交叉引用，`vibesop.observe.routing` v1 契约与退出码不变。
- **性能**：装配期多一次 O(spans) 全扫（bridge 已是全扫 + outcomes 的 O(hits×spans)），
  加上一次（仅在内容变化时发生的）账本重写；hook 热路径零影响。
- **后手（交给后续 lane / grok 决策，不在本 lane 实施）**：
  - `read` 收据生产者：hook 路径写 `metadata["injected_skill_path"]` + 正文长度（作者：agent_runtime 的 owner），
    或按 survey §9.3 主臂做「注入前后 prompt token 差 vs 读计数」双侧对账；
  - `accepted`：verify-result 裁决进 span metadata（见 §2.5 契约）；
  - `vibe data purge` 的 observability 目标（含本账本）。

---

## 10. 建议 grok 写入 `memory/project-knowledge.md` 的 F2 条目草稿

```markdown
### F2 消费分账：命中 ≠ 读到，读文件 ≠ 读技能（lane F2 / pi，2026-09-21）

- 论文建议 #3「分开记录选中、读到、适用、执行、验收」落成 `vibesop.observability.skill_consumption` v1：
  `.vibe/observability/skill_consumption.jsonl`（每 route span 一行，装配期 upsert，含轮转档 `.0.jsonl`）。
- 本轮 5 段里只有 `selected` 有事实（route span 的 `has_match`/`skill_id`/`top_skills`）；
  `read`/`applicable`/`executed`/`accepted` **诚实置空**（`state: null` + `reason`），测试把这些空值钉住。
  没有 harness 收据就不编「读到了」——这正是论文「读取 ≠ 有效」的字面落地。
- 两枚**代理**变量（永不得提升为 `read.state`）：`injection_attempted`（hook 命中 ⇒ 正文交给了 harness）
  与 `read_like_tool_calls`（该 route span 名下的读类工具调用数）。R6 的 10 次读全给了 TASK.md 与自家产物，
  证明读文件 ≠ 读技能。
- 查询面：`vibe observe consumption [--session|--task-id|--route-span-id|--since|--until|--limit|--json]`，
  `vibesop.observe.consumption` v1，raw counts only（无比率），账本缺失 fail-soft `exit 0` + 空结构。
- 非目标钉死：不改匹配分数、不改注入正文、不当 CI 门禁、**不把分账当成功率**。
- 已知缺口（交后续）：`read` 收据需要生产者改造（hook 写注入路径/长度或做 token 差对账）；
  `accepted` 需要 verify-result 裁决进 span metadata；`vibe data purge` 尚无 observability 目标。
```

---

## 11. Phase 2 实施清单（本文件锁定后执行）

| 动作 | 文件 | 类型 |
|---|---|---|
| 新建消费分账模块（派生 + 落盘 + 读取 + 报告契约） | `src/vibesop/core/observability/skill_consumption.py` | 新建 |
| 装配期最小接线（一次调用 + 统计字段） | `src/vibesop/core/observability/tool_call_bridge.py` | 接线 |
| 文档级交叉引用（零行为变更） | `src/vibesop/core/observability/route_observe.py` | 注释 |
| CLI 子命令 | `src/vibesop/cli/commands/observe_cmd.py` | 新增子命令 |
| 测试 | `tests/core/observability/test_skill_consumption.py` | 新建 |
| Handback | `.omx/artifacts/distill-lane-f2-handback.md` | 新建 |

`core/` 分层纪律：新模块只 import core 自身 + 标准库（`tests/architecture/test_layering.py` 会验）。
