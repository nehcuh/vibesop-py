已有全貌。以下是独立评审。

---

## 评审报告：M2 SpanWrappedProvider 实现

---

### A — 逐项打分

**1. `create_provider` 是否是正确包裹点？ 评分：5**

是的。追踪了所有 14 个运行时调用点（`distiller.py`, `agent_runtime.py`, `cli/main.py`, `skill_commands.py`, `init.py`, `_index.py`, `quickstart_runner.py`, `pack_installer.py`, `triage_service.py` via factory, `indexer.py` via factory, `orchestration_mixin.py` via factory, `unified.py` via factory），全部经 `create_provider` 或 `create_from_env`（后者复用 `create_provider`）。无直接 `OpenAIProvider(...)` 或 `AnthropicProvider(...)` 构造逃脱包裹。

**2. BaseException 处理是否正确？ 评分：4**

正确覆盖了 `KeyboardInterrupt` (SIGINT) 和 `asyncio.CancelledError`（Python 3.9+ 都是 `BaseException` 子类）。`fail_span` 内部 `_persist` 有 try/except 兜底日志，不会在清理时覆盖原始异常。

**扣 1 分的原因**：`fail_span(span, str(e))` 丢失了 traceback。当 span 状态为 error 时，`spans.jsonl` 里只有一行 `"upstream failure"`，没有堆栈。生产排障会很痛苦。应该在 `metadata` 中附加 `traceback.format_exc()`。

**3. Token/Cost 记账选择是否合理？ 评分：3**

- `cost_usd=0.0` + `metadata.cost_estimation="p1_not_available"` — 合理 ✓
- **50/50 拆分 `tokens_used` 的问题**：当 `input_tokens=None, output_tokens=None, tokens_used=99` 时，记录为 `tokens_input=49, tokens_output=50`，与正常 token 数据无法区分。下游聚合器（`SpanAggregator.get_skill_metrics` L110-114）会把这些估算值当作真实值统计进 `avg_tokens` 和 `llm_success_rate`。没有 metadata 标记表明这些是估算值。这会在 M3 引入 pricing table 后造成成本核算偏差。

**4. 测试覆盖面是否足够？ 评分：3**

已覆盖：委托、sync 成功、async 成功、错误传播、禁用 tracer、token fallback。

缺失：
- **没有 `asyncio.CancelledError` 专项测试**。只测了 `RuntimeError`。`CancelledError` 在 asyncio 中的传播语义与普通异常不同（re-raise 后 event loop 会重新注入），应专项验证。
- **没有 `KeyboardInterrupt` 专项测试**。
- **没有 `start_span()` 在无活跃 trace 时的集成测试**（standalone span——这在 hook 路径（非 CLI `vibe route`）中是常见场景）。
- **没有验证 spans.jsonl 写入后格式正确的端到端测试**。`_read_spans` 手动解码 JSON 但未验证 `schema_version`、`parent_span_id`、`project_id` 字段就绪。
- **`_build_metadata` 中 `model=None` 走 `default_model()` 的逻辑未覆盖**。

**5. 能否真正关闭 GAP-1？ 评分：5**

是。M2 部署后，所有通过 `create_provider` 的调用都会自动产生 llm-span。之前 308 次裸调用现在全部被包裹。GAP-1 关闭。

---

### B — Top 3 生产风险

**1. Token 估算无标记，污染下游聚合**

50/50 拆分没有 metadata 标记。当 `SpanAggregator` 或未来的 M3 cost tracker 读 `spans.jsonl` 时，无法区分「API 返回的真实 token 数」和「从 tokens_used 估算的拆分值」。修复：在 `_extract_tokens` 走 fallback 路径时，在 span metadata 中写入 `"token_accounting": "estimated_50_50_from_tokens_used"`。

**2. 无 trace context 时产生孤儿 llm-span**

`start_span` 在没有活跃 trace 时创建 standalone span（`trace_id = _Span.new_trace_id()`，`parent_span_id=None`）。Hook 调用路径（非 CLI `vibe route`）可能没有外部 `with tracer.trace(...)` 包裹，这时每个 LLM 调用产生一个孤立的顶级 llm-span。这本身不崩溃，但 `SpanAggregator.get_skill_metrics` 按 `skill_id` 过滤，这些孤儿 span 不包含 `skill_id`（`_build_metadata` 里没有），会**静默丢失**——GAP-1 关闭了但 GAP-3 拿不到数据。

**3. `call()` / `acall()` 中 span 生命周期逻辑完全重复**

两个方法中 ~30 行几乎相同（`start_span` → `set_input` → try/except → `_extract_tokens` → `with_tokens` → `set_output` → `finish_span`）。在 P1 中不算 bug，但任何一处的修复必须同步到另一处。建议抽取 `_execute_with_span(prompt, model, ..., executor: Callable)` 私有方法。

---

### C — Duck-typing 审计补充

你已检查：`distiller.py`, `agent_runtime.py`, `cli/main.py`, `skill_commands.py`, `init.py`, `_index.py`, `quickstart_runner.py`, `pack_installer.py`。全部走 `create_provider`。

**遗漏的路径**：

1. **`src/vibesop/core/ai_enhancer.py:48`** — 接收 `llm_provider: Any` 参数，不自己构造。但调用方是 `skill_commands.py:630`（`AIEnhancer(llm_provider=create_from_env())`），所以没问题。

2. **`src/vibesop/core/prompt_chain/generator.py:415-419` 和 `validator.py:378-381`** — 是 E2E Docker 脚本中的内联 Python 代码字符串，硬编码 `create_provider`。不走运行时，不是逃脱路径。

3. **唯一真实风险**：如果有外部调用方（第三方插件、hooks 脚本）直接 `from vibesop.llm.openai import OpenAIProvider` 并绕过工厂构造，则不会被包裹。这是 API 设计层面的风险——`OpenAIProvider` 等具体类是 public API。建议在 `__init__.py` 中标记它们为 semi-private，或在 M3 中将 `LLMProvider.__init__` 改为自动注册 tracer。

**结论：代码库内部无逃脱路径；外部 API 面存在理论风险。**

---

### D — Schema 回归风险

**不会崩溃。** `SpanAggregator._read_spans_in_window` 只是逐行 JSON 解析，不做类型断言。关键路径：

- `get_skill_metrics` 按 `metadata.skill_id` 过滤 → 新 llm-span 不含 `skill_id` → 被排除，不崩溃
- `get_pattern_sequences` 只取 `span_kind == "tool_call"` → 不受影响
- `get_anomaly_events` 调用 `get_skill_metrics` → 同上
- `has_data` 只读文件大小 → 不受影响

**但存在语义回归**：新 llm-span 通过 `start_span` 创建时继承当前 thread-local trace context 的 `trace_id`。如果该 trace 的 task span 有 `skill_id`，llm-span 共享 `trace_id` 但自身 metadata 无 `skill_id`，聚合器按 `skill_id` 过滤时找不到它。这是 GAP-3 需要解决的——需要让聚合器沿 `parent_span_id` 向上查找 task span 的 `skill_id`，或让 SpanWrappedProvider 在 metadata 中写入 `skill_id`。

---

### E — 一句话总评

**实现干净、包裹点正确、测试基本充分，但 token 估算无标记 + 孤儿 span 无法被聚合这两个问题会在 M3 返工——现在修成本最低。**
