# Lane D1 Handback — eval_routing 双向误差报告（report-only）

**Status: DONE**

- Worker: claude · worktree `/Users/huchen/Projects/vibesop-evo-D1-claude` · branch `feat/evo-D1`
- Commit: `a5f4878d` `feat(eval): report two-sided no-match error counts`（未 push）
- 基线：`60fd0487`

## 改动文件清单

| 文件 | 改动 |
|---|---|
| `scripts/eval_routing.py` | +57 行，纯增量。主循环内累积双向计数器；`metrics` 追加 8 键（`n_pos` / `n_neg` / `over_reject` / `over_inject` / `no_match_by_layer` / `no_match_rate` / `n_near_miss` / `near_miss_over_inject`）；人读 stdout 加 2 行；docstring 补字段定义段 |
| `tests/unit/test_eval_routing.py` | +91 行，纯增量。3 个新测试（FakeRouter / `_run_eval` 既有风格，8 个旧测试零改动） |

口径实现（与任务书表格逐条对齐）：

- `n_pos` = 已评分条目中 `expect` 非空（skipped_env 在路由前 `continue`，天然不进）
- `n_neg` = `category == must_not_inject` **或**（`expect` 空且无 `reject` 的 no-match 断言），并集每条计一次
- `over_reject` = `n_pos` 里 `result.has_match` 为 False
- `over_inject` = `category ∈ {must_not_inject, near_miss}` 里 `has_match` 为 True
- `no_match_by_layer` = 有 match 的按 primary layer 计数 + `"no_match"` 桶；`no_match_rate = no_match / total`（total=0 时 0.0）
- `n_near_miss` / `near_miss_over_inject` = `subclass: near_miss` 或 `category: near_miss`；题集没有时输出 0（实测 0）

## 命令 + 退出码

```
$ uv run pytest tests/unit/test_eval_routing.py -q
...........                                                              [100%]
11 passed in 0.87s
exit 0

$ uv run ruff check scripts/eval_routing.py tests/unit/test_eval_routing.py
All checks passed!
exit 0

$ uv run python scripts/eval_routing.py --json --json-out /tmp/d1-main.json   # 额外自查
exit 0
新字段实测：n_pos=31 n_neg=6 over_reject=5 over_inject=0
no_match_by_layer={keyword:15, semantic_index:6, explicit:5, tfidf:2, no_match:11}
no_match_rate=0.2821  n_near_miss=0  near_miss_over_inject=0
旧键（total/top1_accuracy/recall_at_3/skipped_env/errors/confusion_pairs）全部在位
```

（首次 `uv run pytest` 因 worktree 未建 venv 报 exit 2，`uv sync --extra dev` exit 0 后复跑通过——环境初始化，非代码问题。）

## 是否改动了 `--check` 退出码路径

**否。** 证据：

1. `git diff` 纯增量 148 行、0 删除；`baseline_records` 构造、`must_not_inject_fails` 硬拒绝列表、`evaluate_against_baseline` / `write_baseline` / `check_update_absorption` / `compute_fingerprint` 调用行、所有 `return` 语句零触碰（grep 变更行无命中）。
2. `--check` / `--update-baseline` 只消费 `fingerprint` + `baseline_records`（benchmark.py:321/:390）；新计数器只进 `metrics` dict（print / `--json` / `--json-out`）与 stdout，不进 baseline。
3. `over_reject=5` 非零时 report-only 路径 exit 0（上节实测），证明新数字不影响退出码。
4. `must_not_inject` ok1 判定与 `--update-baseline` 硬拒绝列表继续只看 `category == "must_not_inject"`；near_miss（双形态）只进 `over_inject` / 专字段，未加入硬拒绝列表——任务书红线遵守。

## 我无法验证的部分

- `--hermetic --check` 实跑（任务书明确不在本单测跑，太重）：本 worktree 单测只覆盖非 hermetic 路径。静态证据（上节 1/2 条）表明 gate 消费链零接触，但 exit 0 的最终确认留给 grok 集成验收（`uv run python scripts/eval_routing.py --hermetic --check`）。
- CI step summary / artifact 渲染：本地验证了旧键在位，未跑真实 CI job。
- D2 加 near_miss 题目后的真值表现：本 lane 只钉了计数口径（`test_near_miss_sublayer_counts` 覆盖 `category: near_miss` 与 `subclass: near_miss` 两形态），题目本身归 D2。

## 对 hermetic fingerprint / CI 的影响

- **指纹**：零影响——`HERMETIC_POSTURE`、`compute_fingerprint` 输入（registry / skill_roots / dataset / posture）均未动；题集 YAML 属 D2。
- **CI routing-eval job**（report-only）：只增 JSON 键，step summary 读的 5 个旧键全部在位，预期照常绿。
- **CI routing-benchmark job**（gate）：消费路径零接触，预期 `--hermetic --check` 仍 exit 0。
- `per_query` / `baseline_records` 键集未动（byte-level failing-set diff 职责保持）。

## 建议 grok 下一步

1. 集成验收：`uv run python scripts/eval_routing.py --hermetic --check`（期望 0）+ 四个 lane 的单测合跑（优化计划 §6 命令）。
2. Wave 1.5 合入时注意 D2 会改题集 YAML → 先预期 exit 3（指纹变）再 `--update-baseline`，与 D1 改动无交叉文件。
3. 实测 `over_reject=5`（本机非 hermetic 路径）是方向 D 想要的第一个信号：阳性题有 5 条无 real match（多在 fallback_llm）。hermetic 口径的数字以 CI gate job 为准。
