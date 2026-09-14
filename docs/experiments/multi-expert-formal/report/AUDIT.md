# 正式 360 审计说明

机器可读：`audit360.json`。统计实现：冻结的 `harness/analysis.py`（未改）。

本文件只描述展示/审计层。主执行 freeze 未改。

## 核对

| 项 | 结果 |
|---|---|
| 分配 | 360，唯一 360 |
| 状态 | passed 149，failed 211，error 0，interrupted 0，pending 0 |
| 每组 | 72 |
| 每任务 | 30 |
| 每任务×规格×组 | 重复 3 |
| freeze vs live | 无漂移 |
| 原始 prompt/completion vs ledger | 360/360 一致 |
| cache vs ledger.cache_hit | 360/360 一致 |
| 请求与 response/error 异或配对 | 通过 |
| monotonic call id | 通过 |
| task_hash | catalog == manifest，且每条 result.task_hash 与 catalog 一致（`task_hash_drift=false`）。先前实现把「manifest 是否含 task_hashes」误报成漂移，已在审计层纠正，未改原始结果。 |
| manifest sha256 | `0b9b5f8ea460e4d496302f559f7e3900835dafc1e7f95b637435aa49ceb0d2f4`，与 first12 同一文件 |
| 隐藏评测模块进入请求 | 无（`HIDDEN_MARKERS` 模块名/mutant 未命中） |
| 泄漏候选（仅 assistant 文本） | 11 条提到 “hidden tests/acceptance”；均为参与者对隐藏验收的泛化推理，不含 evaluator 源。保留候选 + 假阳性裁定，不删旗。 |
| Docker digest | 与 manifest 一致；argv 仍为 tag `python:3.12-slim` |
| 所有权违规但标 passed | 0；E 有 11 条 `ownership_or_conflict` 记失败，与预注册一致 |

无静默改写原始 `result.json`。

进入隐藏验收的产物 160 条全部通过；严格成功 149。本电池没有「隐藏测试实现失败」的主实验反例。

结束时 image inspect：`sha256:d764629ce0ddd8c71fd371e9901efb324a95789d2315a47db7e4d27e78f1b0e9` `[python:3.12-slim]`。

## 图

中文字体改为本机已验证的 Songti SC / Heiti SC / Hiragino Sans GB（PingFang.ttc 在本机不存在）。已目视 PNG：标题与轴标签可读，非 tofu。资源箱线保留离群点，纵轴按最大值留白。
