# 敏感性 144 审计说明

机器可读：`audit144.json`。统计实现：冻结的 `harness/analysis.py`（未改，仅把 D_soft 映射为 D 供函数使用）。

本文件只描述展示/审计层。敏感性 freeze 与原始 request/response **未改写**。

## 核对

| 项 | 结果 |
|---|---|
| 分配 | 144，唯一 144 |
| 状态 | passed 130，failed 6，error 0，interrupted 8，pending 0 |
| 每组 | A 72，D_soft 72 |
| 每任务 | 12（2 spec × 2 arm × 3 repeat） |
| freeze vs live | 生成时核对 |
| 已终态 136 行 prompt/completion vs ledger | 应一致；不一致列入 `usage_mismatches` |
| 8 个 interrupted | **无最终 ledger**。用量从 response.usage + tools.jsonl 派生，见 `interruption-audit/derived-usage.json`。不能记 0。 |
| 开放 HTTP | 7 个分配缺最后一次 response（request 已落盘，可能已计费，token **未知**）。1 个分配 11 request / 11 response（`route-priority-table-v1-brief-D_soft-r0`），仍无 ledger，仍标下界。 |
| 不得声称 | 144/144 请求-响应完美配对 |
| 中断原因 | Grok headless 600s 后台超时杀 runner；不是 DeepSeek API / 模型失败 |
| 恢复 | 先归档 8 份原始 running `result.json`，再 `--resume` 只跑 13 个未开始项；8 个标 interrupted 且 `rerun=false` |
| Docker digest | 与 manifest 一致；argv 仍为 tag `python:3.12-slim` |

无静默改写原始 `result.json`（resume 只把 8 个 `running` 标为 `interrupted` 并写入 `interrupted_at`/`rerun`）。原始 running 快照在 `interruption-audit/running-snapshots-before-resume/`。

泄漏候选 9 条：均为 assistant 提到 “hidden tests/acceptance” 的泛化推理（例如清理自建 `hooks/` 以免干扰隐藏验收）。抽查 `config-param-passthrough-v1-brief-D_soft-r1/call-029-request.json`：不含 evaluator 源或 `oracles.py`/`cases.py`。保留候选 + 假阳性裁定，不删旗。`HIDDEN_MARKERS` 模块名未命中。

`n_ok=144` 只表示无**意外**问题；8 行仍有预期中断缺口。不得读成 144/144 日志完美。

## 图

中文字体：Songti SC / Heiti SC / Hiragino Sans GB。资源箱线不含 interrupted（避免把缺 ledger 画成 0）。
