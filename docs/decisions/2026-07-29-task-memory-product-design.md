# Product Design: Agent Memory (v3 — 复审后)

> 2026-07-29 — 综合 workflow + v1 评审 + 真实数据预检 + v2 评审
> 取代 v1 / v2（同文件前两版）

---

## 0. v3 修订动因

v2 提出后跑 grok + pi 复审，**两个 reviewer 独立抓到 v2 的设计自相矛盾**：

> v2 一边把 `project_path` 放进 task_id hash，一边把"跨项目 cluster"作为核心卖点。这两个设计数学上互斥——同一 query 在不同项目算出不同 task_id，跨项目 cluster 永远聚不起来。

详见 `_review-task-memory-loop-v2-merged.md`。

**v3 修复路径**：MVP 退回单项目 + task_id 纯 query 派生。跨项目作为 opt-in feature defer 到 W4+ 或 post-MVP。

---

## 1. 定位（v3 微调）

**VibeSOP = "会记事的 agent 操作系统"**

核心叙事（简化、去掉"跨项目"修饰）：**"Mastra 让您看清楚 agent 在做什么；VibeSOP 让 agent 记住您做过什么。"**

跨项目记忆是 **post-MVP feature**，不是 MVP 卖点。

---

## 2. 架构原则（v3 终版）

| # | 原则 | 来源 |
|---|---|---|
| 1 | 拒绝 auto-write skill，候选池隔离 + 人审 | v1 grok+pi 共识 |
| 2 | **Embedding 是主路径**，BM25 仅 fallback | 预检 Finding 3 |
| 3 | **task_id = `hash(normalize(query))[:16]`**，纯 query 派生，不含 project_path | v2 grok+pi 双 P0 |
| 4 | **MVP 单项目**（cmspark 验证）；跨项目 defer | v2 grok+pi 共识 |
| 5 | dev/prod 自动检测（PYTEST_CURRENT_TEST），不靠 env var | v2 grok+pi 共识 |
| 6 | normalize 规则冻结 + 金标准 fixture | v2 grok P0 |
| 7 | W0 mini-benchmark 选 embedding 模型（不直接选 MiniLM） | v2 grok+pi P1 |
| 8 | W3 是可执行 replay 不是 hint | v1 pi |
| 9 | Kill criteria 测效用不测频次 | v1 pi |
| 10 | 金标准主信号用 `InstinctLearner.record_outcome` | v1 pi |

---

## 3. v3 的 4 周 MVP

### W0 — Instrumentation Fix + 模型选型（2.5 天）

**Task A**: task_id 纯 query 派生（v3 修订）
- 新增 `core/observability/task_id.py`
- `derive_task_id(query) -> str`：normalize + sha1[:16]
- normalize 规则：去首尾空格 / 折叠内部空白 / lowercase / NFKC unicode normalize / 去标点（保留中日韩字符）
- **配套 fixture**：`tests/fixtures/task_id_normalize.jsonl`，含 10+ 组"同义不同表述"query 对，全部必须算出同 task_id
- 在 `cli/main.py:724` 的 `trace()` 调用传 `task_id=derive_task_id(decision.query)`

**Task B**: dev/prod 自动隔离
- 新增 `core/observability/dev_detect.py`：`is_dev_environment()`
- 检测：`PYTEST_CURRENT_TEST in os.environ` / `pytest in sys.argv[0]` / 调用栈含 `tests/`
- 是 dev → 写到 `.vibe/observability/spans.dev.jsonl`
- env var `VIBESOP_OBSERVABILITY_MODE` 仅作显式覆盖

**Task C**: embedding mini-benchmark
- 候选：`paraphrase-multilingual-MiniLM-L12-v2` + `bge-m3` + `e5-multilingual-small`
- 数据：cmspark 截图权限 10 query（已知金标准）+ vibesop-py 一些干扰 query
- 指标：cosine separation（金标准内部均值 vs 金标准-干扰均值）
- 选 separation 最大的进 W1

**验收**：
- `vibe route "<q>"` 两次，spans.jsonl 新条目 100% 有 task_id，两次同 query 同 task_id
- 跑测试不影响 prod spans 文件（自动检测 + 隔离写）
- mini-benchmark report 落盘 `docs/decisions/w0-embedding-benchmark.md`

### W1 — Embedding + Cluster + 金标准（5 天）

**Task A**: 集成 W0 选定的模型 + cache
- 加载模型（lazy singleton）
- cache：`hash(model_id + normalize(query))` → embedding，落盘 `.vibe/cache/embeddings.npz`
- 模型升级 bump model_id，旧 cache 作废

**Task B**: cluster 算法
- 同 task_id 直接 group（W0 后有了，硬 cluster）
- 不同 task_id 但 cosine ≥ 0.85 → soft cluster
- 不引入 HDBSCAN（单用户低频不需要）

**Task C**: 金标准规则（v1 grok+pi 修订全保留）
- 主信号: `InstinctLearner.record_outcome(success)`
- 辅信号: `status==completed AND has_match==true AND duration<=p50(cluster)`
- 门控: `cluster_size >= 5`，n<5 标 `candidate_success`
- duration 用 p25-p75 区间

**验收**（**新 kill switch，v2 grok+pi 修订**）：
- **Recall**: cmspark 截图权限金标准 ≥10 query 聚进同一 cluster（连通分量）
- **Precision**: 该 cluster 内无关 query ≤1
- **稳定性**: 换 seed / 阈值 ±0.02，结果不崩
- **多 cluster**: 至少 2 个真实 cluster 验证（不只截图权限，例如"合盖休眠"5 个 query）
- **人工抽检**: 5 条边界 pair
- **fail 处理**: 允许"换模型 / 降阈值"一次，不整条砍方向

### W2 — Recall CLI（4 天）

- `vibe recall "<query>"`：单项目，扫当前 project 的 `.vibe/observability/spans.jsonl`
- embedding cosine top-3，绝对阈值 ≥0.7
- 输出: top-3 历史 trace 摘要 + step 序列 + 来自 task_id
- 默认未达阈值视为无召回（防错召回污染信任）

**Kill criterion**: recall **follow 率**（用户看完是否真去 trace 或执行 replay）≥30%

### W3 — Replay 模式（4 天）

- `vibe route --replay` 命中金标准时一键回放
- 命中提示: "上次处理这个 task 走了 X→Y→Z（trace_id=...），按上次方案执行？[Y/n]"
- Hint 模式作 config fallback，默认 off

### W4 — Skill Promote（5 天）

- 触发: `cluster_size >= 3 AND gold_rate >= 60%`
- 反条件: `gold_rate < 30%` → unstable 诊断队列
- step frequency count → core/common/optional
- 候选池 TTL=30d + 硬上限 + 未审不注入
- **跨项目加分**: 暂不实现（v3 砍掉），W4+ 或 post-MVP 做

---

## 4. Post-MVP Roadmap（defer 出 4 周的）

- **跨项目 recall**（v2 删的特性）：单项目 MVP 验证通过后，加 allowlist + embedding-only index（不原文合并），promote 跨项目加分需人工确认
- **Timeline UI**：CLI 跑通后再考虑
- **Cytoscape DAG viz**：defer
- **Provenance Copilot**：defer

---

## 5. Kill Criteria（v3 最终版）

| 时点 | 测什么 | 阈值 | 不达标动作 |
|---|---|---|---|
| W0 末 | task_id 在新数据上填充率 + dev/prod 自动检测工作 + embedding 模型选定 | 100% / 工作 / 选定 | 阻塞 W1 |
| W1 末 | cmspark 截图权限 cluster + 合盖休眠 cluster + precision + 稳定性 | 见 W1 验收 5 条 | 换模型或降阈值，最多重试 1 次 |
| W2 末 | recall **follow 率** | ≥30% | 停后续 |
| W4 末 | 金标准 cluster 数 + 候选池积压 | ≥5 / <10 | freeze |
| W12 末 | active skill 在 routing 中**实际命中** | ≥3 次/月 | 归档 |

---

## 6. 与 v2 的 diff（变更摘要）

| 维度 | v2 | v3 | 变更原因 |
|---|---|---|---|
| task_id | `hash(query + project_path)` | **`hash(query)`** | v2 双 P0：含 project_path 与跨项目目标数学冲突 |
| MVP scope | 跨项目 | **单项目** | v2 双 P0：跨项目 mission creep + 隐私 + 语义错配 |
| 跨项目 | W0-W2 必做 | **W4+ opt-in** | 同上 |
| dev/prod | env var | **自动检测 pytest** | v2 双 P0：env var 必被忘设 |
| Embedding 选型 | 直接选 MiniLM | **W0 mini-benchmark 3 模型** | v2 grok+pi P1：绑死模型风险 |
| Kill switch | 单一硬指标 | **Recall+Precision+稳定性+多 cluster** | v2 grok+pi P1：单一指标误判风险 |
| Normalize | 未定 | **冻结 + fixture** | v2 grok P0：normalize 改动破坏 task_id 稳定性 |

---

## 7. v1/v2/v3 演进路径

- **v1**：基于 task_id 是好 anchor 的假设 → grok/pi 抓出 5 个 P0 → merged
- **v2**：吸收 v1 评审，但加了"跨项目"反应数据分散预检 → grok/pi 抓出自相矛盾
- **v3**：去掉跨项目，task_id 纯 query 派生，回到"先把单项目做透"的诚实路径

**教训**：每加一个特性，必须问"这个特性与已有特性数学上是否互斥"。v2 把互斥的两个设计塞同一方案，是设计 review 应该早抓的。

---

## 一句话总结

v3 = **v2 - 跨项目 - project_path salt + 自动 dev/prod 检测 + 模型 mini-benchmark + 多维 kill switch**。比 v2 简单，比 v1 严谨。**MVP 在 cmspark 单项目验证假设**，跨项目作为 opt-in feature 推后。

---

## 8. W0 Implementation Addendum (2026-07-29, post grok+pi review)

W0 shipped. Independent reviewers (grok + pi) approved entering W1 with
a punch-list (all resolved before W1 start). Capturing the W0 decisions
that **override or refine** what's written above:

### 8.1 W1 soft-cluster threshold: 0.85 → **0.80**

§3 W1 Task B originally specified cosine ≥ 0.85 for soft cluster. The
W0 benchmark (`docs/decisions/w0-embedding-benchmark.md`) showed:

| Threshold | Recall | Precision | FPR |
|---|---:|---:|---:|
| 0.75 | 0.644 | 0.784 | 0.08 |
| **0.80** | **0.622** | **0.824** | **0.06** |
| 0.85 | 0.489 | 1.000 | 0.00 |

At 0.85, MiniLM recall is 49% — half the gold cluster fragments into
singletons, failing the W1 kill switch "≥10 gold in one connected
component." **W1 default threshold is 0.80**, treated as a tunable
kill-switch parameter (one model-swap or threshold-shift retry allowed
per design §5).

### 8.2 W1 embedding model: **MiniLM-L12-v2**

Winner of W0.C mini-benchmark (separation −0.274 vs bge-small-zh −0.245
vs bge-base-en −0.209). Smallest (384-dim, ~120MB), fastest inference.

Cache key: `hash("minilm-l12-v2" + normalize(query))` — model_id in the
hash so future model swaps invalidate gracefully.

### 8.3 W0.C model substitution (deviation from §3 W0 Task C)

Design specified MiniLM + bge-m3 + e5-multilingual-small. Actual W0.C
ran MiniLM + **bge-small-zh-v1.5** + **bge-base-en-v1.5** because
FastEmbed's catalogue doesn't include bge-m3 or multilingual-e5-small
(only multilingual-e5-large, 2.2GB, skipped for a benchmark).

**Risk**: bge-m3 (multilingual, 1024-dim) may outperform MiniLM on a
cleaner gold set. Mitigation: W1 kill switch already allows one model
swap. If MiniLM@0.80 fails connectivity on the second cmspark cluster
(lid-sleep), re-run benchmark with sentence-transformers + bge-m3 as the
swap candidate.

### 8.4 task_id scope: per-query content identity, **not** session inheritance

Pure-query derivation has a consequence reviewers explicitly endorsed:
sub-agent CLIs (Claude Code, etc.) that **rewrite** the query get a
**different** task_id than the parent. This is by design:

- Parent and child share task_id only when the child sees the same (or
  normalize-equivalent) query text.
- Cross-process attribution for parent→child relationships that involve
  query rewriting is established via the existing DAG rebuilder joining
  on `metadata.parent_session` — not via task_id propagation.
- This means task_id answers "what user goal is this span about?" and
  the DAG answers "what spawned what?". They are orthogonal axes.

### 8.5 fastembed is an optional extra, not a runtime dep

Moved from `[project.dependencies]` to `[project.optional-dependencies].semantic`.
Install via `uv sync --extra semantic`. Production CLI runs without
embeddings (W1 will lazy-import when `vibe recall` first fires).

### 8.6 W0.D scope expanded beyond §3 design

Design asked only for `main.py:724` fix. W0.D also fixed the hook path
(`agent_runtime.py:409`, was hardcoded `task_id=None`). The hook path is
the production entry point — without fixing it, the bug would only be
fixed for CLI demos, not real agent use. Reviewers endorsed this as
required, not scope creep.
