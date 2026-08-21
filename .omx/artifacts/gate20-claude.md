核实完毕:`runVibeRoute` 走 `vibe route --json`(RoutingResult.to_dict),与本次改动无关。测试全绿(agent_runtime 22 passed;observability+conformance 531 passed)。以下是复审结论。

---

# gate20 复审结论

## Verdict: **PASS_WITH_NITS**

改动方向正确、核心依据属实、无 BLOCK 级问题。已执行验证:`uv run pytest tests/agent/runtime/test_agent_runtime.py`(22 passed)、`uv run pytest tests/core/observability/ tests/conformance/test_agent_runtime.py`(531 passed)。

## 事实核实(评审重点逐项)

**1. 正确性 — 通过**

- `bool(single.get("skill_id"))`:已核实 `agent/__init__.py:347-351`,`single_result["skill_id"]` 构建为 `primary.skill_id if has_match else None`;`RoutingResult.has_match`(models.py:216-219)= `primary is not None and layer != FALLBACK_LLM`。因此 truthy skill_id ⟺ 真命中，且 fallback-llm 在此路径 skill_id 为 None → 判 miss,与 CLI 路径语义(cli/main.py:843 写 `routing_result.has_match`,fallback 同为 False)一致。可靠。
- 多意图 `bool(plan.steps)`:见 NIT-1。
- 异常路径：实测方向安全——routing 异常在 agent_runtime.py:631-634 提前 `return`,发生在 L663 metadata 写入**之前**，span 根本不带 `has_match` → 两个谓词均视缺失为 unknown、不入池。保守方向正确(任务描述中“异常路径 False”实际不触及 span,无影响)。

**2. 语义回归 — 通过，但有一个未申报的消费方变化(见 NIT-2)**

全量 grep span metadata `has_match` 消费方:`gold_detection.is_route_miss_span`(目标)、`tool_call_bridge`(:377 解析 / :490 谓词)、`skill_promote.py:925`(仅 docstring)、`cli/main.py:843`(CLI 生产者，不受影响)。pi TS 模板消费的是 `vibe route --json` 的 `RoutingResult.to_dict()`,与 span 无关。属性消费方(instinct 桥 agent_runtime.py:674、loop/executor.py、`to_hook_json` L104-119 显式 dict 不含新字段)均未变。

**3. 属性不对称 — 可接受**

metadata key 复用 `has_match` 是对的选择：CLI 路径早已用该 key 写真实判定(cli/main.py:843),改名 key 会导致两生产者分叉 + 需放宽谓词。现修法使 metadata.has_match 全局统一为“router 真实判定”。字段声明处(L74-82)与写入处(L655-663)注释均已交代不对称原因。

**4. 测试质量 — 良好**

谓词集成断言真实从 spans.jsonl 读持久化 span(metadata 为 SpanWriter 序列化的 JSON 字符串，`_metadata` 与谓词各自兼容 str/dict),非内存对象直传。`test_property_semantics_unchanged` 钉住属性语义。缺口见 NIT-3。

## Findings

**NIT-1** `agent_runtime.py:548-550` — 注释"each step carries a skill_id"不精确：PlanBuilder 的 step skill_id 可以是 `"fallback-llm"`(plan_builder.py:321-339 显式 "using anyway";squad 分支 ：626 字面量 `"fallback-llm"`)。后果：多意图全-fallback plan 判 `router_matched=True`,而单意图同场景(fallback-llm)判 miss——同修复内两分支不对称。失败方向保守(漏检 miss,不产生假 miss),不阻塞。建议：修正注释，或改用 `any(s.get("skill_id") not in ("", "fallback-llm") for s in steps)` 语义(需权衡，现实现可接受)。

**NIT-2** `agent_runtime.py:655-663` — 修复有一个未申报的第二消费方:`tool_call_bridge._is_miss`(tool_call_bridge.py:490)同样读 metadata `has_match`,修后 hook miss 会进入 outcome 信号推导(route_outcomes.jsonl)。方向核实为正确：hook 模板转发平台 session_id(vibesop-route.sh.j2:24-28、80-82),`session_moved_on` 证据可存在，且 re-ask 证据走跨进程 task_id——不构成 CLI 排除理由(gate16 pi nit)所防的 hollow weak_positive。但 gate17 交叉注释明确要求"change one, re-read the other",diff 注释只提 `is_route_miss_span`,未提 bridge 侧。建议：在写入处注释补一句 bridge 影响，或补一条 bridge 侧测试。

**NIT-3** `tests/agent/runtime/test_agent_runtime.py` — 两处覆盖缺口:(a) 多意图 **空 steps** → miss 的 `bool(steps)=False` 分支无测试;(b) routing 异常路径 span 无 `has_match`(unknown,双谓词均不入池)无测试。

## Residual Risks

1. **历史数据盲区仍在**：已落盘的 pre-fix hook span 带错误 `has_match=True`,M12 池扫旧数据时盲区照旧；新旧 span 无 schema 版本区分，混扫时语义不可辨。
2. 多意图全-fallback plan 对 miss 池不可见(NIT-1 的保守漏检)。
3. 理论边缘：真命中但 skill_id 为空串 → 假 miss(SkillRoute.skill_id 必填，实际不可达)。
4. `router_matched` 未暴露进 `to_hook_json`——外部 hook 消费方仍看不到真实判定(本修复不要求，仅记录)。
