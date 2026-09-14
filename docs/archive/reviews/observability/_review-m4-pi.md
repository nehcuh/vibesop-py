好了，代码和 schema 都读完了。以下是我的独立审查。

---

## A — 逐项评分

**1. Tree 渲染正确性：2/5**

- `_render_trace_tree` 构建了 `by_id` dict 但从未使用，子节点查找是 O(n²) 的线性扫描。死代码本身不致命，但意味着作者写了一半就放弃了正确的 O(1) 实现。
- **中间层孤儿静默丢弃**：`roots` 从 `not parent_span_id` 的 span 中筛选，fallback「如果没有 root 就把所有 span 当 root」只在 `roots` 为空时触发。如果一个 trace 里有 root-A，以及 child-B（parent=root-A），再加上 orphan-C（parent=某个不存在的 span-id），orphan-C 永远不会被渲染——它不在 roots 里，也没有任何已渲染节点以它为子节点。没有警告，用户不知道丢了数据。
- `duration_ms == 0` 被 `if dur:` 错误地显示为 `-`。`duration_ms=0` 是完全合法的值（亚毫秒 span），不应被当作 falsy 吞掉。
- 上述三个问题都是代码级别的硬伤，不是审美问题。

**2. CLI 表面的人机工效：3/5**

- 没有「显示最近一次 trace」的快捷方式。用户刚跑了 `vibe route hello`，想立即看到 replay，必须自己去 spans.jsonl 里翻 trace_id。
- `--trace-id` 前缀匹配无歧义处理：匹配到 3 个 trace 就静默输出 3 个。对调试场景，用户更想要「匹配到多个，请精确化」而非默默接受。
- 默认 `--limit 10`。如果 spans.jsonl 积了 500 个 trace，启动就是 10 个全量渲染，没有分页、没有流式、没有「只显示最近 1 个」的合理默认值。调试场景通常只想看最后一次。

**3. Orphan 行为：4/5**

- 跳过 `trace_id=""` 的 span 并打印 notice，逻辑正确。扣 1 分因为：notice 是 `[dim]` 样式，在大输出里极易被忽略，应该用 `[yellow]`。

**4. 测试充分性：2/5**

8 个测试，缺了以下用户实际会踩到的场景：

| 缺失场景 | 为什么重要 |
|-----------|-----------|
| 中间层 orphan span（parent 指向不存在的 span-id）| 见 A.1 — 会被静默丢弃 |
| `status="error"` 的 span 渲染 | `SpanWrappedProvider.fail_span()` 生产环境会触发 |
| `metadata` 为空 dict `{}` 的 span | `SpanWriter` 对空 `metadata` 不序列化为 JSON string，和其他 span 的类型不一致 |
| 混杂损坏 JSON 行的文件 | 只 catch 了 `JSONDecodeError`，没测试该路径 |
| `duration_ms=0` 或 `None` | 见 A.1 |
| 多个 trace 命中同一个 `--trace-id` 前缀 | 前缀匹配过于宽松时用户会看到意外结果 |
| 树缩进测试只比较了列位置而非父子关系 | `grandchild_line.index("F") > child2_line.index("X")` 只在两者都是 root 时也能通过 |

**5. 生产兼容性：2/5**

- **`metadata` 类型不一致是定时炸弹**：`SpanWriter.write_span()` 对非空 metadata 做 `json.dumps` 后存入，对空 `{}` 则不处理直接存 dict。结果：同一个 spans.jsonl 中，`metadata` 字段有时是 JSON string，有时是 dict。`_decode_span_field` 能兜住，但这是靠运气，不是靠设计。M3 如果有人在 metadata 里放非 JSON-serializable 的对象，`_decode_span_field` 会吃掉异常返回空 dict——数据静默丢失。
- **`cost_usd` 的 0 vs None 语义混乱**：`_format_cost` 用 `if not cost_usd` 同时处理 `None` 和 `0.0`，都显示 `-`。M3 引入真实定价后，免费 tier 的 `$0.00` 会被显示为 `-`，用户无法区分「没有定价数据」和「这次调用是免费的」。应该用 `if cost_usd is None`。
- `input_data` / `output_data` 在 `SpanWriter` 中也被序列化为 JSON string，但 `_load_spans` 完全没有解码它们——replay 不消费这些字段所以不炸，但如果未来有人扩展 replay 去读 `input_data`，会拿到原始 JSON string 而非 dict。

---

## B — 最可能咬到用户的两个问题

1. **中间层 orphan span 静默丢弃**。生产环境中 span 写入是 best-effort（`SpanWriter` 没有 retry），root span 写入失败但子 span 写入成功是完全可能的场景。用户打开 replay 看到一棵看似完整的树，实际上少了一整条分支，没有任何提示。

2. **元凶：没有「显示最近一次 trace」的零参数快捷方式**。调试工作流是 `跑 route → 看 replay → 改 → 再跑 route → 再看 replay`。目前每次都得多打 `--trace-id <去spans.jsonl里翻出来的id>`。这个摩擦会让用户放弃使用 replay，回到 `print` 调试。

---

## C — 最有用但没实现的功能

**`--follow` / `-f` tail 模式**。和 `tail -f` 一样持续读取 spans.jsonl，有新 span 就增量渲染。这是「我刚刚跑了个 route，让我看看 agent 内部在干什么」最自然的交互方式。目前 M4 只能做静态事后回放，做不到实时观察。而且 JSONL 天然适合 tail——不需要特殊索引。

第二缺：`--kind llm` / `--kind tool_call` 过滤。想只看 LLM 调用的 token 和 cost 时，现在只能肉眼从整棵树里找。

---

## D — 一句话总评

**能用但浅——演示够、真调试不够：tree 渲染有三个硬 bug（中间层孤儿丢弃、0ms 显示为 `-`、O(n²) 死代码），CLI 缺了调试工作流最关键的「给我看刚才那次」的零摩擦路径。**
