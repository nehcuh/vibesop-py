# gate20 复审指令 — hook 路径 has_match 盲区修复

你是资深代码评审员。仓库:/Users/huchen/Projects/vibesop-py(Python,包在 src/vibesop)。随附 diff 是本次待审改动:修复 hook 路径(agent_runtime)的 miss 盲区。

## 背景(缺陷机理)

`AgentRuntimeResult.has_match`(agent_runtime.py:76)是 mode 派生属性(`intercepted and mode in ("single","orchestrate","multi_agent_squad")`),不是 router 真实命中。orchestrate 分支在 `single_result["skill_id"]` 为空(真实 miss)时也设 `mode="single"` → span metadata 的 `has_match` 恒 True → `gold_detection.is_route_miss_span`(route span + has_match=False + mode≠not_intercepted)永远看不到 hook 路径的 miss → M12 miss 池只吃 CLI 路径数据。

## 改动内容

- `AgentRuntimeResult` 新增 `router_matched: bool = False` 字段承载 router 真实判定;mode 派生 `has_match` 属性不动(instinct 桥、hook JSON 等现有消费者语义不变)。
- 非编排分支:`router_matched = bool(routing_result.has_match)`;编排分支:多意图 `bool(plan.steps)`、单意图 `bool(single.get("skill_id"))`(依据:`agent/__init__.py:347-351` 构建 single_result 时 miss 则 skill_id=None);异常路径 False。
- span metadata 的 `has_match` 改写 `result.router_matched`(真实判定),注释声明与属性的刻意不对称。
- 测试:新类 TestRouterMatchedSpanVerdict 6 例(hook miss 入谓词/ match 不入/编排单意图 miss/match/多意图 plan/属性语义不变)。

## 评审重点

1. **正确性**:`bool(single.get("skill_id"))` 作为编排单意图分支的真实判定是否可靠(核实 agent/__init__.py:347-351 的实际构建逻辑);多意图 `bool(plan.steps)` 是否等价于命中;异常路径 False 是否安全方向。
2. **语义回归风险**:span metadata `has_match` 从 mode 派生改为真实判定——除 miss 谓词外还有哪些消费者读 span 的 has_match?行为变化是否都在预期内(grep 消费方核实)。
3. **属性不对称**:`has_match` 属性(mode 派生)与 metadata `has_match`(真实判定)同名不同义——注释是否足够,是否有更不易混淆的选择。
4. **测试质量**:6 例是否锁住关键行为;谓词集成断言是否真实走 span 持久化格式。

## 输出格式(严格遵守)

- 先给总评 verdict:PASS / PASS_WITH_NITS / FAIL(有任一 BLOCK 即 FAIL)
- findings 按严重度:BLOCK / NIT,每条含 文件:行号、问题、建议
- 最后列 residual risks
- 用中文,简洁,拿证据说话
