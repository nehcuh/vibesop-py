/bin/sh: -c: line 0: unexpected EOF while looking for matching `"'
/bin/sh: -c: line 1: syntax error: unexpected end of file
评审完成。已核对 `agent/__init__.py:347-351` 构建逻辑、`models.py:217/791` 两个 `has_match` 属性定义、`gold_detection.is_route_miss_span`、`tool_call_bridge`、`cli/main.py:843` 生产者、`span_writer` 持久化格式,并运行 `tests/agent/runtime + tests/core/observability` 全量(523 passed)。

---

## 总评:**PASS_WITH_NITS**

无 BLOCK。核心机理判断正确、方向安全、测试走真实持久化格式。以下 NIT 均为覆盖面与文档问题。

---

## Findings

### NIT-1 — `tool_call_bridge` 是未申报的第二消费者(行为变更盲区)
- 文件:`src/vibesop/core/observability/tool_call_bridge.py:377-391`(`_as_route_span` 读 `meta["has_match"]`)、`:471-490`(`_is_miss`)
- 问题:span 的 `has_match` 消费方除 `is_route_miss_span` 外还有 bridge。hook 路径 span 的 `is_cli=False`(`:390`:`platform != "cli"` 且无 `source=="cli"`)、mode 为 `"single"`,修复后真实 miss 会**首次进入 bridge 的 miss 集**并参与 M2 outcome-signal 派生(这些 span 带真实 session_id,`:232` joinable,会产生 `strong_positive/re_ask/expired` 行)。方向与 bridge 设计一致(它排除 CLI 正是因 one-shot session 无意义),大概率是期望行为,但 diff 注释只声明 `is_route_miss_span` 影响,未提及 bridge,也无对应测试。
- 建议:在 diff/注释中补一句 bridge 语义一致性说明(或复用 `gold_detection.py:120-126` 与 `tool_call_bridge.py:477-485` 已有的"两谓词刻意分歧"交叉引用,声明本次 hook miss 对二者同向生效),并加一条 bridge `_is_miss` 对 hook miss 的断言。

### NIT-2 — 两个已声明路径缺测试
- 文件:`tests/agent/runtime/test_agent_runtime.py:283-458`(`TestRouterMatchedSpanVerdict`)
- 问题:(a) 异常路径(agent_runtime.py:594-597 提前 return,`router_matched` 保持 False 但 metadata 不写 → 谓词判 unknown、非 miss)的"安全方向"无测试锁定;(b) 多意图 **空 steps** 分支(`:550` `bool(steps)` 的 False 侧)只有 match 例,无 miss 例——恰恰是本次修复要让谓词看到的场景。
- 建议:补 `test_orchestrate_multi_intent_empty_steps_is_miss`(空 plan 断言谓词 True)与 `test_routing_exception_span_is_unknown_not_miss`(mock route 抛异常,断言 `has_match` 缺失且谓词 False)。

### NIT-3 — 编排单意图判定对"键缺失"的容错方向
- 文件:`src/vibesop/agent/runtime/agent_runtime.py:569`(`bool(single.get("skill_id"))`)
- 问题:已核实 `agent/__init__.py:347-351` 保证 miss 时 `skill_id=None`、match 时非空,今日判定可靠。但 `.get` 对**键缺失**返回 None → False,若未来另一实现(或重构)的 `single_result` 不含 `skill_id` 键,真实 match 会被标为 miss → miss 池污染(而非漏检)。属低风险远期点。
- 建议:在注释中把"键恒存在"列为前提,或显式 `single.get("skill_id") is not None` 与当前语义等价(现状可接受,仅提示)。

### NIT-4(轻微)— 不对称命名已充分注释,可接受
- 文件:`src/vibesop/agent/runtime/agent_runtime.py:73-81`(字段注释)与 `:655-662`(写点注释)
- 评价:metadata 键名必须保持 `has_match`(谓词 + bridge + 历史 span 都读它),property 不能改语义(instinct bridge `:674`、`to_hook_response` 是既有消费者)——不对称是修复的固有代价,两处注释已把"何时用哪个"讲清。无需改动;唯一残余是未来维护者需持续记住两义,建议后续可在 `is_route_miss_span` docstring 加一句"hook 路径 producer 现在写真实判定,与 CLI 一致"。

---

## Residual risks

1. **M2 bridge 产出量变化**:上线后 hook 路径 miss 首次进入 outcome-signal 派生,`session_expired` 等弱正例行数会上升——需观察 M2 精度指标是否有预期外偏移(见 NIT-1)。
2. **历史 hook span 不可回溯**:修复前已写入的 hook miss span 仍是 `has_match=True`,miss 池对存量数据不追溯(一次性失真,可接受,未处理)。
3. **两谓词同步演进**:`gold_detection.is_route_miss_span`(宽松,CLI+hook)与 `tool_call_bridge._is_miss`(严格,仅 hook)现在都收到 hook miss,二者既定分歧(CLI 排除)保持成立;未来改动需继续遵守 `tool_call_bridge.py:477-485` 的交叉引用约束。
4. **单意图 `skill_id` 键前提**:依赖 `agent/__init__.py` 的 `single_result` 构建恒含该键(今日成立),一旦该构建变更需同步重审 `:569`。

**证据摘要**:`agent/__init__.py:347-351` 确认 `skill_id = primary.skill_id if has_match else None`;`models.py:791` 确认"非空 step 列表即 match"与 `bool(plan.steps)` 等价;异常/拦截失败路径均在写 metadata 前 return(`:481/:513/:597`),span 无 `has_match` → 谓词 `gold_detection.py:154-157` 判 unknown;CLI 侧 `cli/main.py:843` 本就用 `RoutingResult.has_match` 真实判定,修复后 hook 与 CLI 语义对齐。
