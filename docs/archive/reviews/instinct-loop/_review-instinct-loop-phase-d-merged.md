# Phase D merged verdict — instinct auto-promote + feedback-collect

**评审来源**：pi（kimi quota exhausted，未参与本轮）

**范围**：`vibe loop create --command`、`vibe instinct auto-promote`、`vibe instinct feedback-collect`、3 个测试文件

---

## P1 blockers（已全部修复）

### P-P1-1 — Watermark 非原子 + FIFO 假设不成立（pi C）

**问题**：
1. `_save_watermark` 用 `path.write_text()`，崩溃中途会留下截断的 JSON，下次 `_load_watermark` 触发 try/except 兜底返回空 set → 已处理的 hash 全部丢失 → 同一批 miss 会被重复 decay。
2. `list(hashes)[-10000:]` 假设 set 迭代是 FIFO 插入序，但 Python set 受 `PYTHONHASHSEED` 影响，跨进程重启后顺序不稳定，砍掉的可能是"最新的"而非"最旧的"。

**修复**：
- `_load_watermark` 改返回 `dict[str, None]`（Python 3.7+ dict 保序），同时获得 O(1) 成员查询 + FIFO trim 语义。
- `_save_watermark` 改用 `vibesop.utils.atomic_writer.write_text`（temp + rename）。
- 新增辅助函数 `_add_watermark`：re-add 时把 hash bubble 到尾部，确保"最近见过的"优先保留。
- 新增回归测试 `test_watermark_preserves_insertion_order`。

### P-P1-2 — `_generate_id` 私有方法被外部调用（pi E）

**问题**：`_candidate_to_instinct` 直接调 `learner._generate_id(pattern)`，破坏封装。如果 learner 内部归一化逻辑（`lower().strip()` + md5）变化，auto-promote 的"重跑幂等"承诺静默失效。5 个调用点：learner.py 内部 ×2 + context_mixin.py + instinct_cmd.py + 2 个测试。

**修复**：
- 重命名 `_generate_id` → `generate_id`（public），加 docstring 说明"public so callers can derive the same id `learn` would have produced"。
- 更新全部 5 个调用点。
- 没有保留 `_generate_id` 别名（项目 CLAUDE.md：避免 BC shim）。

---

## P2 defer-ok（部分本轮修，部分入 Phase E）

### P-P2-1 — growth_cap cold start（pi A）

**结论**：合理（max(1, ...) 兜底），不改逻辑。改善 help text：
> "单次 promote 数量上限 = 当前 instinct 数 × pct%（防失控）。冷启动（before=0）时强制允许 1 个。"

### P-P2-2 — boost 分支改迭代 all_instincts（pi B）

**结论**：可接受，本轮加一层 `total_applications >= 1` 地板，防止从未被匹配过的 instinct 被 boost 复活。Wilson score + early-stop 提供自纠。

### P-P2-3 — `decay_frequent` 全局减半误伤（pi D）

**结论**：本轮修。给 `decay_frequent` 加 `hashes: set[str] | None = None` 参数；feedback-collect 只传实际 decay 过的 hash 集合，未关联的 cluster 保留原 count。
- 新增回归测试 `test_decay_frequent_hashes_filter_skips_unrelated_clusters`（直接测 miss_counter）。
- 新增回归测试 `test_decay_frequent_only_touches_decayed_pattern`（端到端：early-stop 的 instinct 的 miss hash 必须未被衰减）。

### P-P2-4 ~ P-P2-10 — Phase C defer 项继续 defer

D-1（launchd ProcessType）、D-2（log rotation）、D-3（throttling）、D-4（--command deny-list）、D-7（dry-run 输出不对称）入 Phase E 队列或后续迭代。

---

## Phase C P2 残留确认

| Item | Status |
|------|--------|
| D-1 ProcessType | 入 Phase E |
| D-2 log rotation | 入 Phase E |
| D-3 throttling | 入 Phase E |
| D-4 --command deny-list | 入 Phase E（pi A 没强制要求；shlex + LoopSpec 4-way xor 已是双保险） |
| D-5 watermark LRU | ✅ 本轮 P-P1-1 已解决 |
| D-6 decay_frequent 误伤 | ✅ 本轮 P-P2-3 已解决 |
| D-7 dry-run 输出不对称 | 入 Phase E |

---

## Pre-existing failures（非本轮 regression）

`tests/cli/test_trace_replay.py::TestMetricsCommand::test_metrics_returns_aggregated_values` 与 `test_metrics_project_id_filter` 在 main 分支已失败（`source == 'spans'` 断言失败，可能涉及 SpanAggregator 集成）。不阻塞 Phase D 提交。

---

## 验证

```
505 passed, 3 skipped in 1.80s
ruff: 0 new errors（pre-existing ARG002 in context_mixin.py:128 不在本轮范围）
basedpyright: 0 errors（pre-existing sentence_transformers warning）
```

手测：
- `decay_frequent(min_count=3, hashes={h_alpha})` → alpha 6→3、beta 6→6（未动）✓
- `feedback-collect` 端到端：early-stop 的 saturated instinct 的 miss hash 保留 5 不变 ✓
