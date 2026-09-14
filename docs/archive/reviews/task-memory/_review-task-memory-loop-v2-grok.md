# grok Review v2: Task-Anchored Memory（复审）

> 评审时间：2026-07-29
> 模式：grok --prompt-file（single-turn）

## Q1 — task_id 派生

**P0** — `project_path` 作 salt 与「跨项目 cluster」目标直接冲突：同一语义 query 在不同项目得到不同 task_id，cluster 只能靠 embedding 事后拼，anchor 层已碎。
**替代**：`task_id = hash(normalize(query))[:16]`（语义锚）；`project_path` 单独作 facet/filter，不进 hash。

normalize 未定稿也是 **P0 级隐患**：未冻结规则（空格/标点/大小写/繁简）→ 同一问题多次执行拆成多个 task_id。
**替代**：W0 写死 `normalize` 规格 + 金标准 fixture（含繁简/同义表述），任何改动必须过 fixture。

sha1[:16] 单用户碰撞可忽略 → **P2**。

## Q2 — Embedding 模型

**P1** — MiniLM-L12-v2 对中文「问题描述」够用存疑；W1 kill 绑死在它上，模型本身可能是假阴性来源。
**替代**：W1 并行 2 模型（MiniLM + bge-m3 或 e5-mistral 小变体）同金标准对比，再定主路径；OpenAI API 作 optional 对照，不进默认依赖。

Cache：**P1** — 未定义 key/失效。
**替代**：`cache_key = hash(model_id + normalize(query))`，落盘 per-user；模型升级必须 bump model_id。

470MB/50ms 单用户可接受 → **P2**（装载冷启动写进 UX 预期即可）。

## Q3 — 跨项目 scope

**P0（MVP 范围）** — 跨项目是真实痛点，但与 task_id salt、隐私、解法错配三项叠乘，W0–W2 同时做是 mission creep。
**替代**：MVP **单项目做透**（cmspark 验证假设）；跨项目 recall 标为 W4+ opt-in，默认 off。

隐私/合并存储：**P1** — 扫 `~/Projects/*` 默认合并等于隐式跨租户索引，商业敏感 span 无边界。
**替代**：显式 allowlist 项目；索引只存 embedding+元数据，原文 span 仍就地。

语义错配（同 query 异解法）：**P1** — cluster 合并后 promote/replay 可能推错 skill。
**替代**：跨项目只作「相似问题提示」，promote 默认本项目；跨项目加分需人工确认。

## Q4 — dev/prod 隔离

**P0** — 纯 env var 必被忘设；v1 已证明 fixture 污染（90% 测试 query）。
**替代**：`is_vibesop_dev_environment()` 自动分桶：pytest/`PYTEST_CURRENT_TEST`、调用栈含 `tests/`、`VIBESOP_OBSERVABILITY_MODE` 显式覆盖；默认 **prod 只写非 test 路径**，宁漏写不污染。

## Q5 — kill switch

**P1** — 「≥10 query 聚成一团」只测 recall 量，不测边界与 precision；糊边界/脏并入都算 pass。
**替代**：
1. **Recall**：截图权限金标准集合 ≥10 进同一 cluster（或连通分量）
2. **Precision**：cluster 内无关 query ≤1
3. **稳定性**：换 seed/阈值 ±0.02 结果不崩

过严误杀：**P2** — 单一硬性门槛可因模型抽风误杀方向。
**替代**：硬门槛 + 人工抽检 5 条边界 pair；fail 时允许「换模型/降阈值」一次，不整条砍掉。

## 最严的新风险

**task_id 含 project_path 与「跨项目 embedding cluster」目标自相矛盾，再叠加默认跨项目扫盘 → anchor 碎裂 + 隐私面扩大 + 错解法 recall，三者在 W0–W2 同时落地，比 v1 的 BM25 失效更难回滚。**
