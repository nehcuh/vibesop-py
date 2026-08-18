# Bigram 得分方向验证 + `index_match_threshold` 标定

> 日期： 2026-08-18
> 来源： pi 复审遗留 — M3 把 `_tokenize_query` 改为 CJK bigram 后，`_score_overlap`
> 得分分布变化（"提交" vs "提交代码" 1.0 → 0.67)，而 `index_match_threshold`
> （默认 0.20）从未标定。
> 脚本： `scripts/calibrate_index_threshold.py`（可重跑）
> 数据： `~/.vibe/skill-index.json`(110 profiles)×
> `tests/benchmark/routing_eval.yaml`(31 条带 expect 的强标注）+
> `tests/benchmark/routing_eval_extended.yaml` 中 `needs_review && weak_label`
> 且 expect 非空的 116 条弱标注。

## 1. 得分方向验证（pi 的论断成立）

| tokenize | score("提交" vs "提交代码") | 主集 mean top1 得分 | 弱集 mean top1 得分 |
|---|---|---|---|
| bigram（当前） | **0.667** | 0.115 | 0.043 |
| unigram（旧，每字一 token) | **1.000** | 0.128 | 0.051 |

pi 指出的方向正确：bigram 在子串情形下得分下降，整体 top1 得分分布下移约 10%。

## 2. 但路由决策（top1 命中）两方案完全一致

- 主集 31 条 query,bigram 与 unigram 的 unthresholded top1 命中**逐条相同**
  （disagree 列表为空）,top1 准确率同为 0.419。
- bigram 的区分度优势体现在**错误接受**上：低阈值档 bigram 的 wrong-accept 更少
  （主集 0.15 档 1 vs 2;0.05 档 8 vs 9；弱集 0.05 档 42 vs 46)，与 M3 改动动机
  （unigram Jaccard 对 CJK 近似噪声）一致 → **不需要回退 bigram**。

## 3. 阈值扫描（top1 准确率 = top1 命中且得分 ≥ 阈值）

### 主集（31 条，强标注）

| threshold | bigram | unigram |
|---|---|---|
| 0.05 | 0.387 | 0.387 |
| 0.10 | 0.290 | 0.323 |
| 0.15 | 0.258 | 0.258 |
| **0.20（当前）** | **0.258** | **0.258** |
| 0.25 | 0.226 | 0.226 |
| 0.30 | 0.161 | 0.129 |
| 0.35 | 0.032 | 0.032 |
| ≥0.40 | 0.000 | 0.000 |

### 主集 — 接受覆盖率 / 错误接受数 / 接受精度（bigram)

| threshold | cov | wrong | prec |
|---|---|---|---|
| 0.05 | 0.645 | 8 | 0.600 |
| 0.10 | 0.355 | 2 | 0.818 |
| 0.15 | 0.290 | 1 | 0.889 |
| **0.20** | **0.290** | **1** | **0.889** |
| 0.25 | 0.226 | 0 | 1.000 |
| 0.30 | 0.161 | 0 | 1.000 |

### 弱标注集（116 条，低置信）

所有阈值档准确率 ≤0.069;≥0.20 时两方案覆盖率均为 0。该集对阈值标定基本无信号
 （生产日志长噪声 query,token overlap 层本就不该接住；弱标签本身不可靠）。

## 4. 结论与决定

- **不调整默认值（保持 0.20)，不改动 `manager.py`。** 理由不是"0.20 更优",
  而是**数据不足以区分各候选阈值**:
  1. bigram 与 unigram 两方案的 top1 决策在主集完全一致（disagree 为空）,
     准确率逐档相同，无优劣之分；
  2. 相邻阈值档之间的差异（如 0.20 vs 0.25：覆盖率 0.290 vs 0.226、
     wrong-accept 1 vs 0）都在 1 条 query 级别，n=31 下纯属噪声——既不足以
     证明升档的精度收益，也不足以证明降档的覆盖收益；
  3. 弱标注集在 ≥0.20 无信号，无法提供额外证据。
- **维持现状，待更大 eval 集 A/B。** 任何方向的阈值调整都需要更大的强标注
  集（或生产 A/B）支撑后再做；当前数据下"动"与"不动"无法被区分，按最小
  改动原则不动。
- **置信度：低。** 主集仅 31 条有效 query，所有候选阈值间的差异都在 ±2 条
  query 以内；弱标注集 116 条但标签未人工确认且 ≥0.15 档几乎无命中。

## 5. 附带发现（follow-up，未改动）

- `index_match_threshold` 并不存在于 `RoutingConfig`(`config/manager.py`),
  仅由 `_layers.py:465` 的 `getattr(router._config, "index_match_threshold", 0.20)`
  兜底。用户无法通过配置文件覆盖该阈值。若未来要标定/开放该参数，应先在
  `RoutingConfig` 显式声明字段。
- 索引层对主 eval 集的独立 top1 准确率仅 0.419(unthresholded)——主集多数 query
  设计上由 scenario/keyword/LLM 层接住，索引层是补充而非主力，评估其阈值时应
  以"不引入错误接受"为先（精度优先），0.20 当前精度 0.889 属合理区间。
