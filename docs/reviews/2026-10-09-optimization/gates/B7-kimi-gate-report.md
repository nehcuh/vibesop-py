# B7 预 commit 门禁报告 — Kimi 独立复审

- **批次**：B7（观测回放合同，D12），wave W4，owner Claude（真实鉴权 401，由实际 Kimi 临时开发，本报告为**新会话独立复审**，不代表 Claude）
- **复审人**：Kimi Code（独立会话，未调用任何其他代理/模型）
- **日期**：2026-10-09
- **输入**：`.omx/artifacts/diagnosis-B7.diff`，18658 字节，SHA256 `b83ed66c5d0bb0c0529abeda465e2d8038c8b3a9e2ea44deff49ebbfbe9176f0` — **全文读取并逐字校验一致**
- **工作区**：隔离副本 = HEAD(49901afe) + B7 修复 + CHANGELOG，`git status` 仅 4 改 1 新（span_utils.py 为 untracked 新文件），无其他批次混入
- **裁决**：**APPROVE**

---

## 1. 实跑证据（本复审人亲自执行，与推论分离）

| 验证 | 命令/方式 | 结果 |
|---|---|---|
| 目标测试 | `uv run pytest tests/core/observability/test_recall.py -q` | **45 passed** |
| 观测+dashboard 全量 | `uv run pytest tests/core/observability tests/dashboard -q` | **765 passed, 1 skipped** |
| CLI 消费者回归 | `uv run pytest tests/cli -q -k "recall or replay or instinct"` | **64 passed**（`tests/core/instinct` 目录在本副本不存在，与作者记录一致，无遗漏） |
| Lint/格式 | `ruff check` + `ruff format --check`（4 个改动文件） | 全过 |
| **回归有效性（非破坏复验）** | 用 pytest 插件（/tmp，pytest fixture monkeypatch）将 `recall.span_skill_id` 替换为修复前 dict-only 逻辑，不改库文件 | `test_skill_id_from_json_string_metadata` 与 `TestD12RealSpanWriterConsumerChain::test_writer_reader_consumer_chain` **均如预期失败**（后者精确失败在 `assert None == 'cmspark-rotate-keys'`，`RecallResult.skill_id=None`）；恢复后 45 全绿。证明新测试针对的正是 D12 缺陷，非空转 |
| **真实 TestClient 复验 dashboard** | 真实 `SpanWriter` 写 3 span（2 个带 `metadata.skill_id`，1 个无）→ 真实 `TestClient(create_app())` 请求 `/api/spans?skill_id=skill-x` | **恰好返回 1 条匹配**；`skill_id=nonexistent` 返回 `[]`。注意：响应中 metadata 已被 `_read_jsonl` 归一化为 dict（见 §3 观察） |

## 2. 合同核验（代码级，逐项）

- **Producer 合同**：`span_writer.py:126-133` 确认 `metadata` 落盘前 `json.dumps` 为字符串（`:116-124` 对 input/output_data 同）；diff 中 reader 变更与工作区逐字一致。
- **Reader**：`recall.py:378-414` `_extract_skill_id` — metadata 经共享 `span_skill_id`（容忍 dict/JSON-string），output_data 补 string 容忍，sentinel `fallback-llm` 在最终出口统一排除（语义与旧版逐分支排除等价）；优先级 top-level → metadata → output_data 保持。
- **共享 helper**：`span_utils.py` — 畸形 JSON/非 dict payload/缺失/非对象（int）→ `{}` 不抛异常（`test_decode_span_metadata_malformed_or_missing` 覆盖 42、`"[not a dict]"`、`"{not json"`）；dict 直通；空/非字符串 skill_id → None。
- **CLI 接受消费者**：`cli/main.py:2401 _maybe_prompt_replay` — 真实默认路径 `SpanWriter().query_recent` + `InstinctLearner()` + `should_replay`；链测试 `monkeypatch.chdir(tmp_path)` 使消费者默认路径（`Path.cwd()/.vibe/...`，span_writer.py:87、learner.py:211）自然命中测试文件，**无类替换、无 dict-literal span 充当 producer**；测试还锁定「磁盘 metadata 为 JSON 字符串」并在 producer 格式变化时响亮失败。
- **反馈 producer**：消费者 Y 后 `learner.learn(..., source="replay_confirm")` + `record_outcome_for_query`；测试用全新 `InstinctLearner()` 从磁盘读出 `success_count>=1`，端到端闭合。
- **未越界**：`grep span_utils|_extract_skill_id` 全库仅 recall/dashboard 两处消费；sibling 文件零改动。

## 3. Mock/误测审查

- 链测试 mock 仅 4 处，全部定向且必要：`cache._compute`（固定向量隔离 embedding 模型，与本文件既有 W3 测试同法）、`recall.get_embedding_cache`（把 `should_replay` 默认 cache 指向确定性测试 cache）、`typer.confirm`/`_is_interactive_stdio`（TTY 交互打桩）。**writer/reader/recall/should_replay/learner/CLI 消费者全部真实**，无假消费者、无宽泛 mock。
- `TestD12StringMetadataSkillId` 用 dict-literal span 直接测 reader — 属 reader 单元层，producer 真实性由链测试层负责，分层合理；现有 dict 形态测试全部保留并通过。

## 4. Sibling 审计独立抽验

作者登记的容忍点我抽验三处属实：`skills/skill_health.py:78-83`（string-or-dict，参考模式）、`skill_consumption.py:180 _decode_metadata`（容忍）、`skill_promote.py:1169-1171`（**仅认 dict，磁盘 span 的 steps 提取静默跳过 — 确认为潜在同类债务，超出 B7 ownership，登记立项即可，不阻断本批**）。其余 sibling 未在本 diff 中触碰，无回归面。

## 5. 观察（不阻断）

1. **dashboard 改动实际为行为中性**：`server.py:80 _read_jsonl` 在读入时已通过 `_normalize_span_metadata`（:85-94）把 string metadata 归一化为 dict，旧过滤在真实路径上并非作者所述「恒不匹配」。改动仍是正确的防御性对齐（且按批准计划「helper 化则一并修 server.py:353」在 ownership 内），并小幅扩展为认可 top-level `skill_id`（超集行为）。仅指出原描述略有夸大，不构成问题。
2. CHANGELOG 两条目与实际行为一致（writer 格式不变、reader 容忍、malformed 安全忽略）。
3. Docker 容器复跑按批次流程归 Codex 在 diff 冻结后执行，本门禁未跑 Docker（按派工禁止）。

## 6. 结论

修复精确、最小、落在批准 ownership 内；全链真实 producer→reader→consumer 测试成立且经我非破坏复验证明针对 D12 缺陷；目标/邻近套件全绿；sentinel 排除、畸形容忍、dict 兼容均覆盖。**APPROVE**，可进入 commit（commit 与容器复跑仍按流程由对应角色执行）。
