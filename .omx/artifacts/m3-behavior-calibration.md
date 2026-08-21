# M3 行为一致性阈值标定 — bigram-Jaccard

> **日期**: 2026-08-21(gate24 复审后更新:同 trace 防泄漏 + folded/unfolded 双口径 + 薄样本 exit 2)
> **脚本**: `scripts/calibrate_behavior_threshold.py`(纪律仿照 `calibrate_discovery_threshold.py`:分布 + 决策带 + 刀刃对,不拍点估计)
> **数据**: cmspark 真实 `.vibe/observability/spans.jsonl` (7595 spans) + `cluster_candidates.jsonl` (28 rows,标签 = M2 聚类结果)
> **结论**: **决策带证据不足,`_BEHAVIOR_JACCARD_THRESHOLD = 0.5` 维持为待验证起点**(模块常量,`behavior_consistency.py`)。

## 标注方案(自监督)

- 正例对:同一候选簇内两条带工具序列的 trace(同工作流)。
- 负例对:跨簇 trace 配对(不同工作流)。
- 簇标签来自候选池 `task_ids`(经 spans 反查展开为 (project_id, task_id) 复合键,gate24 MAJOR-B 口径);promoted/pending 行都算有效标签。
- **防泄漏(gate24 MAJOR-A)**:cmspark 池实测 254 个 task_id 横跨 ≥2 候选(跨扫描窗口重叠)。配对前按 trace 分组键去重——同一 trace 的任何配对(无论簇标签)不进正例也不进负例;同一 cluster_id 的重复池行同样防正例自配。否则同一条 trace 会以 Jaccard=1.0 自配成"负例",污染决策带。

## 数据实况(cmspark, 2026-08-21)

- 159 条 tool_call span,只覆盖 **10 条 trace**(3 条有 ≥2 个工具调用;其余 7 条为老 producer 形状的单工具 span)。
- 连续同名调用对 99/157 —— 生产口径做**连续同名折叠**,理由(gate24 MINOR-C 诚实版):`_bigrams` 返回 set,长重复段不存在"数量淹没";真正理由是 (X,X) 自环 bigram 在 set 语义下无区分度,折叠后 bigram 集反映"不同工具间的转移"而非重复执行。**已知方向性偏差:折叠抬高含长重复段 trace 的得分**(gate24 claude 实测一例 0.5 → 1.0;本次双口径对照 0.300 folded vs 0.333 unfolded 是反方向的一例——样本太少,两个方向都只在 n≥ 数十对时才有意义);非连续重复(Read→Grep→Read)保留(真实"回看"信号)。
- tool span 与父 route span 的 task_id 一致率 152/152(7 条老 span 无 task_id,走 parent_span_id 关联)。
- **候选池 28 条中,只有 2 条候选各有 1 条带工具序列的 trace**(7becaeb9 folded len=32 / e05c142b folded len=10);没有任何候选簇有 ≥2 条序列。
- 根因:kimi 平台 hook 未接入(M1 已知边界),tool span 仅来自 claude/grok 侧;而带 tool span 的 trace 几乎不落在候选簇内。

## 标定输出(原文,exit code = 2)

```
spans: 7595  candidates: 28

### folded (production口径 — consecutive same-tool collapsed)
clusters with tool sequences: 2
  7becaeb9: 1 sequence(s), lengths [32]
  e05c142b: 1 sequence(s), lengths [10]
total sequences: 2
pairs: positive (same cluster) = 0, negative (cross cluster) = 1
negative jaccards: min=0.300 p25=0.300 median=0.300 p75=0.300 max=0.300

### unfolded (对照 — raw sequences)
clusters with tool sequences: 2
  7becaeb9: 1 sequence(s), lengths [70]
  e05c142b: 1 sequence(s), lengths [50]
total sequences: 2
pairs: positive (same cluster) = 0, negative (cross cluster) = 1
negative jaccards: min=0.333 p25=0.333 median=0.333 p75=0.333 max=0.333

## folded pairs: positive = 0, negative = 1

SAMPLE TOO THIN: decision-band evidence insufficient (positive=0, negative=1).
0.5 stays as the provisional, unverified starting threshold — re-run once more
hook-bearing traces land in candidate clusters.
```

## 解读

- 正例对 = **0**:无法估计"同工作流"的 Jaccard 分布下沿,决策带扫描无意义,脚本拒绝给带并以 **exit 2** fail-closed(gate24 pi#8a,供未来 gated 调用)。
- 唯一负例对 0.300(folded)/ 0.333(unfolded)< 0.5,方向符合预期但不构成证据(n=1)。
- **0.5 维持为待验证起点**。复检触发条件:任一候选簇积累 ≥2 条带工具序列的 trace(kimi hook 接入后,或 claude/grok 侧 trace 落入候选簇)。
- 聚合方式(mean of pairwise Jaccard)同样无数据可比较,按保守性原则选定并在 `behavior_consistency.py` 注释记录:min 让单条异常 trace 否决整个簇(过敏感),median 在 n=2 时与 mean 等价。

## 三态语义(设计修订记录)

设计原文只写 consistent/unavailable 两态(gate24 已修订为三态,见 m12-product-design.md M3 段)。实现三态(代码注释同步记录于 `behavior_consistency.py` / `discovery.behavior_evidence_label`):

- `consistent`:有效序列 ≥2 且 mean Jaccard ≥ 阈值
- `divergent`:有效序列 ≥2 但低于阈值 —— "有数据且不达标"不能诚实归入 unavailable
- `unavailable`:有效序列 <2(平台无 hook / 单工具 trace 无 bigram)
- 字段缺失(None)= 未采集(展示层 "未采集",`behavior_evidence_label` 既有逻辑)

> **快照声明(gate24 pi#8b)**:以上计数是 2026-08-21 扫描时点的快照;候选池随每次 scan 变动,复检必须重跑脚本取新数,不得引用本文件旧计数。
