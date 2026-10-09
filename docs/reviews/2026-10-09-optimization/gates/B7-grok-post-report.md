# B7 提交后 Grok 只读第二门禁

**结论: APPROVE**（父提交补齐后复核，结论不变）

发现列表为空。没有需要退回 Kimi 修改的缺陷。

审查对象是已提交的 `df927f4231f59fc8dc294018d1d26bf6045ef52b`（`fix(recall): preserve skill identity across persisted span replay`，作者 huchen，`Co-Authored-By: Kimi Code`）。本轮只读隔离副本，未改源码、测试、文档、配置或基线，未提交，未调用其他模型或子代理。

## 材料怎么对齐到 HEAD

追溯：第一轮审查时，提交对象里的父 SHA 已经是 `49901afe401a3f6fd25ba33c4854ce6329e1e44c`，但该对象当时不在隔离库里。`git diff 49901afe… HEAD` 返回 `fatal: bad object`，`git show HEAD` 因此把整棵树展开成全部新文件。那一轮的五文件增量改读 `.omx/artifacts/diagnosis-B7.diff`（+297 / -16）。这是当时副本的准备限制，不是提交本身缺父。

调度器随后用 `git fetch --unshallow` 补上父历史。本轮亲证现状：

- [executed] `git rev-list --parents -n 1 HEAD` → `df927f4231f59fc8dc294018d1d26bf6045ef52b 49901afe401a3f6fd25ba33c4854ce6329e1e44c`
- [executed] `git cat-file -t 49901afe401a3f6fd25ba33c4854ce6329e1e44c` → `commit`
- [executed] `.git/shallow` 已不存在
- [executed] `git show --numstat --format= HEAD` 恰好五个路径，合计 **+297 / -16**：

| 路径 | 增 | 删 |
| --- | --- | --- |
| `CHANGELOG.md` | 7 | 0 |
| `src/vibesop/core/observability/recall.py` | 18 | 15 |
| `src/vibesop/core/observability/span_utils.py` | 55 | 0 |
| `src/vibesop/dashboard/server.py` | 4 | 1 |
| `tests/core/observability/test_recall.py` | 213 | 0 |

[inspected] `git show --format=fuller HEAD` 的完整补丁（420 行输出）与第一轮读过的 diagnosis diff 是同一组 hunk。`git show` 的文件顺序是 CHANGELOG、recall、span_utils、dashboard、test_recall；diagnosis diff 把 span_utils 放在最后。post-image index 前缀不变：`e2e30d4e`、`510fb7be`、`bb761062`、`714d58cf`、`150d9f8d`。

五个 post-image 再次与第一轮记录的 blob 相同，`git rev-parse HEAD:<path>` 与工作树 `git hash-object` 也相同：

| 路径 | blob |
| --- | --- |
| `CHANGELOG.md` | `e2e30d4e7466de1d4cc068d51125c0e6ae7bc36f` |
| `src/vibesop/core/observability/recall.py` | `510fb7be8c08b28f14a3c091c3cb90e00d8a3365` |
| `src/vibesop/dashboard/server.py` | `714d58cfaf526d4e78eac65d5d853a81b4ed5d64` |
| `tests/core/observability/test_recall.py` | `150d9f8d5a8a9dd73de44c5e85225a43eabde65a` |
| `src/vibesop/core/observability/span_utils.py` | `bb76106202f4dd2572fb27f5c91f65b76456b8b6` |

[executed] 复核时 `git status --porcelain --untracked-files=all` 仍只有未跟踪的 `.omx/artifacts/diagnosis-B7.diff`。被跟踪的源、测试和配置相对 HEAD 没有变化，所以没有重跑已通过的 45 个 recall 测试。下面的合同读的是这同一组已提交 blob。

## 生产合同

Writer 不在本提交里，格式保持原样。`SpanWriter.write_span`（`span_writer.py` 116–133 行）把 `input_data`、`output_data`、`metadata` 都 `json.dumps` 成字符串再写入 JSONL。`query_recent`（193–206 行）只对整行 `json.loads`，不把 `metadata` 解回 dict。`Span.to_dict`（`models.py` 98–126 行）没有顶层 `skill_id`；当前 CLI（`cli/main.py` 970–974 行）和 agent runtime（`agent_runtime.py` 962–985 行）把技能写进 `metadata["skill_id"]`，未命中写 `""`，不写 `fallback-llm`。

共享 helper（新文件 `span_utils.py`）：

- `decode_span_metadata`：dict 原样返回；JSON 对象字符串解成 dict；坏 JSON、非对象 JSON、缺字段、非 dict/非 str → `{}`，不抛。
- `span_skill_id`：非空字符串的顶层 `skill_id` 优先，否则取 metadata 里的非空字符串 `skill_id`。空串和非字符串视为没有。这里不过滤 `fallback-llm`。

Recall `_extract_skill_id`（`recall.py` 378–414 行）先用 `span_skill_id`，没有候选时再读 `output_data`（dict 或 JSON 对象字符串）里的非空字符串 `skill_id`。坏 metadata 不会挡住后面的 output。最后若候选是 `fallback-llm` 则返回 `None`。众数统计只计入这个函数返回的非空技能，所以 sentinel 不进入 mode。

Dashboard `/api/spans` 的 `skill_id` 过滤改为 `span_skill_id(r) == skill_id`。这条路由的记录来自 `_read_jsonl`，而 `_read_jsonl` 在过滤前已经调用 `_normalize_span_metadata`（`server.py` 58–94 行）：SpanWriter 写出的 JSON **对象**字符串会先变成 dict。对这种生产行，过滤结果仍是 metadata 里的 `skill_id` 相等。helper 另外接受尚未归一化的字符串，并多认一个顶层 `skill_id`。当前 `Span.to_dict` 不写这个顶层字段，所以它是向前兼容，不改变现有磁盘行的过滤结果。历史行里如果 metadata 仍是 `fallback-llm`，dashboard 在查询恰好等于该值时仍会命中（与归一化之后的旧 `.get("skill_id")` 相等比较一致）；recall 继续不把它当成技能。

接受链：`_maybe_prompt_replay`（`cli/main.py` 2431–2495 行）用默认 `SpanWriter().query_recent` 和 `InstinctLearner()`，再走 `should_replay` → `recall_similar`。`top.skill_id` 有值时，确认 Y 会返回该技能并 `record_outcome_for_query`。`is_dev_environment` 先看 `VIBESOP_OBSERVABILITY_MODE=prod`，再看 pytest（`dev_detect.py` 47–51 行），所以链测试里的 writer 和消费者读的是同一份 `spans.jsonl`。

## 测到了什么

`tests/core/observability/test_recall.py` 新覆盖：

- helper：dict 透传、JSON 对象字符串、坏 JSON、JSON 数组、缺失、非 dict（`42`）、顶层优先于 metadata、空串和数字 `skill_id` → `None`。
- recall：JSON 字符串 metadata 的技能、其中的 `fallback-llm` → `None`、坏 metadata 字符串不抛且技能为 `None`、JSON 字符串 `output_data.skill_id`、dict metadata 仍可读。
- 真实 writer 链 `test_writer_reader_consumer_chain`：真实 `Span` + `SpanWriter.write_span`，`query_recent` 断言 `metadata` 是 `str`，`recall_similar` 读出 `cmspark-rotate-keys`，`should_replay` 为 `gold_match` 且带同一技能，`_maybe_prompt_replay` 在交互确认 Y 后返回该技能，新的 `InstinctLearner()` 从磁盘读到 `success_count >= 1`。技能只可能来自磁盘 metadata：这条 span 的 `output_data` 为空，`Span.to_dict` 也没有顶层 `skill_id`。

相似度被 `EmbeddingCache._compute` 换成确定性假向量。同一查询的余弦是 1，能过 `should_replay` 的默认阈值 0.70。磁盘 JSON、recall、replay 判定、CLI 接受者和 instinct 落盘是真实对象。

## 没测什么（边界，不是缺陷）

- dashboard `/api/spans?skill_id=` 没有新测试。生产对象 metadata 在 `_read_jsonl` 归一化之后，与旧的 dict `.get("skill_id")` 相等结果一致；这是读代码得出的，不是这条测试文件执行出来的。
- `output_data.skill_id` 的 JSON 字符串用例是手写 `json.dumps`，没有再经 `SpanWriter` 回环。writer 对 `output_data` 和 `metadata` 使用同一套 `json.dumps`（`span_writer.py` 116–133 行）。
- 坏的 `output_data` 字符串、`output_data` 里的 `fallback-llm`、空顶层 `skill_id` 再落到 metadata、多条 span 的众数，都没有单独断言。对应分支在 `_extract_skill_id` 里按上述顺序处理。
- 链测试把 `ObservabilityTracer(..., enabled=False)` 传给消费者，不断言 `emit_replay_span` 写入溯源 span。返回值和 instinct 落盘有断言。
- `skill_health`、`skill_consumption`、`route_observe`、`aggregator` 仍用各自的本地 decode。`span_utils` 的模块说明把本次共享范围写成 recall 和 dashboard。
- 全套、Docker、basedpyright 本门禁没有重跑。提交说明里的「宿主与新 Docker 各 45 passed、basedpyright --level error 0」保持为既有声明。

## 已执行

- [executed] `PYTHONDONTWRITEBYTECODE=1 uv run --extra dev --frozen pytest tests/core/observability/test_recall.py -q -p no:cacheprovider` → `45 passed in 2.23s`（exit 0）。额外的 `-p no:cacheprovider` 和字节码开关只为避免把 pytest 缓存写进副本；收集的就是这一个文件。uv 提示外来 `VIRTUAL_ENV` 与项目 `.venv` 不一致并已忽略，随后在副本里创建了 gitignore 的 `.venv`。删除该目录被 shell 拒绝策略挡住。`git status --porcelain` 之后仍只有未跟踪的 `diagnosis-B7.diff`，没有被跟踪文件改动。
- [executed] 第一轮：五文件 `HEAD` blob 与工作树 `git hash-object` 一致；当时父对象缺失，行数来自 diagnosis diff，+297 / -16。
- [inspected] 第一轮：`span_writer.py`、`span_utils.py`、`recall.py`、`dashboard/server.py` 的读取与归一化、`models.py` `to_dict`、CLI 与 agent runtime 的 metadata 写入、`_maybe_prompt_replay`、`dev_detect.is_dev_environment`。
- [executed] 父提交补齐后：`git rev-list --parents -n 1 HEAD`、父对象类型 `commit`、`.git/shallow` 不存在、`git show --numstat` 为上表 +297 / -16。五个 `HEAD:<path>` blob 与工作树 hash、与第一轮记录逐字相同。完整 `git show HEAD` 已逐 hunk 读过。源未变，测试未重跑。

## 发现

无。父提交缺失是第一轮副本的准备限制，补齐后的 `git show HEAD` 没有引出新的源或测试差异。
