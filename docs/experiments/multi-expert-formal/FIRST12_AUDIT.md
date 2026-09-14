# FIRST12_AUDIT

本文件是正式 cohort 的早期日志/冻结审计，**不是**组织方式结论。胜负不作为停止理由。未做 hidden evaluation 的失败不称为实现 bug。

Run root: `docs/experiments/multi-expert-formal/runs/20260913T023645Z`

## 清单核验

| 项 | 结果 |
|---|---|
| manifest 分配数 | **360**（一次性写入，未先切成 12） |
| 本批实际执行 | 12 |
| 剩余 pending | 348 |
| 冻结包校验 | live 与 `frozen-sources/` 逐项 sha256 一致，`drifted=False` |
| 原始 usage 与 ledger | 12/12 对齐（prompt/completion 之和 = used_i/used_t） |
| 隐藏评测器泄漏 | workspace 中无 `oracles.py`/`cases.py`/`evaluate.py`/`qa_bank.py` |
| 重跑/覆盖 | 无；本批无 interrupted |
| 并发 | 8；独立 client/ledger/workspace/recorder |
| seed | 20260913 |
| 资源 | T=24000 I=400000 K=120 hang=600；Docker `sha256:d764629ce0ddd8c71fd371e9901efb324a95789d2315a47db7e4d27e78f1b0e9` |

## 本批 12 条（manifest 顺序）

| allocation_id | status | error | T | I | K | hidden checks |
|---|---|---|---:|---:|---:|---|
| route-priority-table-v1-full-A-r0 | passed | | 2291 | 18075 | 19 | 9/9 |
| route-plan-dag-v1-full-C-r0 | failed | stage_budget_exhausted:independent-0 | 2400 | 21714 | 19 | none |
| config-render-resolve-v1-full-A-r1 | passed | | 2115 | 20601 | 15 | 9/9 |
| match-lot-calendar-v1-full-E-r1 | passed | | 9154 | 178190 | 52 | 6/6 |
| etl-join-aggregate-v1-brief-D-r2 | failed | stage_budget_exhausted:independent-0 | 2400 | 18866 | 18 | none |
| route-priority-table-v1-full-B-r1 | passed | | 5510 | 68679 | 40 | 9/9 |
| etl-join-aggregate-v1-full-C-r1 | failed | stage_budget_exhausted:independent-0 | 2400 | 23984 | 23 | none |
| route-lifecycle-v1-brief-B-r0 | passed | | 6119 | 57360 | 56 | 17/17 |
| route-plan-dag-v1-full-D-r1 | failed | stage_budget_exhausted:independent-0 | 2400 | 22654 | 23 | none |
| config-adapter-vs-entry-v1-brief-D-r0 | failed | stage_budget_exhausted:independent-0 | 2400 | 23429 | 14 | none |
| config-home-isolation-v1-full-E-r1 | failed | budget_exhausted:I_precheck | 8042 | 264649 | 54 | none |
| route-lifecycle-v1-full-E-r2 | passed | | 5212 | 133806 | 54 | 17/17 |

6 passed / 6 failed / 0 error / 0 interrupted。C/D 五次在 independent-0 的 10%T（2400）上耗尽，属该阶段额度下的真实消耗，不是日志覆盖。一次 E 在 I 预检失败。这些分配原样保留，不删除、不重开。

没有 hidden evaluation 的 6 次失败：**不**称为任务代码有 bug。

## 下一条 resume 命令

监督审计后恢复**同一** 360 manifest 的剩余 348，不重抽：

```bash
PYTHONPATH=docs/experiments/multi-expert-formal uv run python -m harness.runner --phase formal --i-understand-formal --resume docs/experiments/multi-expert-formal/runs/20260913T023645Z --max-new 348
```

本回合不执行。
