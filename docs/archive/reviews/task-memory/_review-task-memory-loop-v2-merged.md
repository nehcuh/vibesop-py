# Merged Review v2: Task-Anchored Memory（复审整合）

> 2026-07-29 — grok + pi 复审 v2 设计
> Brief: `/tmp/v2-review-prompt.md`（未归档到 docs/，因为内容已合并在 design doc v3 里）
> grok 原文：`_review-task-memory-loop-v2-grok.md`
> pi 原文：`_review-task-memory-loop-v2-pi.md`

---

## 双 P0 共识：v2 核心自相矛盾

两个 reviewer **独立**抓到 v2 的设计悖论：

| 维度 | v2 设计 | 矛盾 |
|---|---|---|
| task_id 派生 | `hash(query + project_path)` | project_path 进 hash → 同 query 跨项目算出**不同** task_id |
| 核心卖点 | 跨项目 cluster | 跨项目 cluster 需要同 query **相同** task_id |

**结论**：v2 的两个核心设计**数学上互斥**。必须二选一：
- **选项 A**：task_id 不含 project_path → 跨项目 cluster 数学上可行
- **选项 B**：task_id 含 project_path → 放弃跨项目，单项目做透

**两个 reviewer 都推荐选项 B**——MVP 单项目，跨项目 defer 到 W4+ 或 post-MVP。理由：
- 跨项目引入 mission creep（grok）
- 隐私 / 商业敏感（pi）
- 语义错配：同 query 在不同项目的"正确解法"可能相反（pi）

---

## P0 修订清单

### P0-1 — task_id 重新设计（Q1）

**原 v2**：`task_id = sha1(normalize(query) + "|" + project_path)[:16]`

**grok/pi 共识替代**：
- `task_id = sha1(normalize(query))[:16]`（**纯 query 派生**，不含 project_path）
- `project_path` 作 facet/filter，不进 hash

**配套**：normalize 规则必须冻结 + 金标准 fixture（含繁简、同义表述、空格/标点变体），任何 normalize 改动必须过 fixture。

### P0-2 — 跨项目 defer 出 MVP（Q3）

**原 v2**：W0-W2 全部含跨项目

**grok/pi 共识替代**：
- **MVP 只做单项目**（cmspark 验证假设）
- 跨项目 recall = W4+ opt-in，默认 off
- 隐私：W4+ 启用时走 allowlist 项目白名单，不默认扫 `~/Projects/*`

### P0-3 — dev/prod 自动检测，不靠 env var（Q4）

**原 v2**：`VIBESOP_OBSERVABILITY_MODE=dev|prod` 环境变量

**grok/pi 共识替代**：
- `is_dev = ("PYTEST_CURRENT_TEST" in os.environ) or ("pytest" in sys.argv[0]) or (调用栈含 tests/)`
- 自动路由到 `.vibe/observability/spans.dev.jsonl`
- env var 仅作显式覆盖

---

## P1 修订清单

### P1-1 — Embedding 模型 W0 跑 mini-benchmark（Q2）

**原 v2**：直接选 paraphrase-multilingual-MiniLM-L12-v2

**grok/pi 共识替代**：
- W0 加 0.5 天跑 mini-benchmark：3 个候选模型（MiniLM + bge-m3 + e5-mistral 小变体）× 截图权限 10 query 金标准
- 选 cosine separation 最好的进 W1
- cache key = `hash(model_id + normalize(query))`，模型升级必须 bump model_id

### P1-2 — Kill switch 加 precision + 稳定性（Q5）

**原 v2**：单一硬指标"截图权限 cluster ≥10 query"

**grok/pi 共识替代**：
- **Recall**：金标准集合 ≥10 进同一 cluster（连通分量）
- **Precision**：cluster 内无关 query ≤1
- **稳定性**：换 seed / 阈值 ±0.02 结果不崩
- **多 cluster**：至少 2 个真实 cluster 验证（不只截图权限）
- **人工抽检**：5 条边界 pair
- **fail 处理**：允许"换模型 / 降阈值"一次，不整条砍

---

## 双方分歧（小）

| 项 | grok | pi | 取舍 |
|---|---|---|---|
| Q1 sha1[:16] 碰撞 | P2（可忽略） | 未单独评 | 取 P2 |
| Q3 隐私严重度 | P1 | P0 | 取 P0（defer 出 MVP 解决） |
| Q4 严重度 | P0 | P1 | 取 P0（自动检测必做） |
| Q5 模型抽风风险 | P2 | P1 | 取 P1（"连续 2 周不达标才 kill"） |

---

## 最严的新风险（两 reviewer 共识）

**"跨项目数据合并模型"在架构上不可实现**——task_id 含 project_path 与跨项目 cluster 数学冲突。带着这个矛盾进 W0-W2 = 全部无效工程。

**修复路径**：放弃 MVP 期的跨项目，task_id 改纯 query 派生（v3 修订）。

---

## v3 修订要点（替换 v2）

| 维度 | v2 | v3 |
|---|---|---|
| task_id | `hash(query + project_path)` | **`hash(normalize(query))`** |
| MVP scope | 跨项目 | **单项目（cmspark）** |
| 跨项目 | W0-W2 必做 | **W4+ opt-in，默认 off** |
| dev/prod 隔离 | env var | **自动检测 pytest** |
| Embedding 模型 | 直接选 MiniLM | **W0 mini-benchmark 3 模型选 1** |
| Kill switch | 单一硬指标 | **Recall + Precision + 稳定性 + 多 cluster** |

---

## 一句话总结

**v2 的核心设计自相矛盾**——两个 reviewer 独立点名。修复路径简单：**MVP 退回单项目 + task_id 纯 query 派生**，跨项目作为 opt-in feature 推后。这不是退步，是把"听起来很酷但数学不成立"的特性 defer 出 MVP。
