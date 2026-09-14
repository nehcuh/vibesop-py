# 预注册（正式 360）

主比较 **D−A**。本文件在任何正式模型调用之前冻结。正式结果出现后不得更换方法。

## 问题与范围

同一模型、同一工具、同一全局 T/I/K 下，带专家角色的委员会（D）是否比单体（A）在隐藏 CLI 验收上交付更多成功产物？

这是受控小型 CLI 基准，不是异质真实专家团队，也不是整库工程结论。

次要比较（探索，不做未注册显著性宣传）：D−C、B−A、E−A、E−D、规格、类别。

## 样本

12 基础任务 × 2 规格（full/brief）× 5 组 × 3 重复 = **360**。

推断单位是 **12 个基础任务**。规格与重复不是独立任务。校准任务与历史 75 次校准运行排除在 360 之外。

## 成功定义

一次分配成功当且仅当：在 T/I/K 内 deliver，全部隐藏验收通过，且无所有权/路径违规。`failed` / `error` / `interrupted` 均记 0。分母包括全部 360 个分配。没有 hidden evaluation 时，不把失败称为代码 bug。

LLM 评分 **不是** 放行闸（`not LLM`）。

## 主比较估计

对每个基础任务，有 full/brief × 3 repeat 共 **6 个配对观测**。配对内计算 `1[D passed] - 1[A passed]`，再对 6 个差取平均，得到 12 个任务等权的任务均值；总点估计是这 12 个均值的等权平均。

## 区间

95% **cluster bootstrap percentile** 区间：

- 重复 20000 次
- seed = `20260913`
- 每次有放回抽取 12 个 **task 索引**
- 被抽中的 task **保留其全部 spec 与 repeat**（即保留该 task 的任务均值，不把 6 个配对拆开再抽）
- 百分位用相邻次序统计量的线性插值
- 实现：`harness/analysis.py`；先用 toy 数据校验符号、聚类与端点

## 阈值解释（方向与工程价值分开）

工程采用阈值 = +10 个百分点。

| 区间 | 判定 |
|---|---|
| lower > +10pp | 支持在本电池上达到预定采用阈值（`support_adoption_threshold`） |
| upper < +10pp | 排除这一最低收益，**不**证明等价（`rules_out_minimum_gain`） |
| upper < 0 | 支持更差（`support_worse`） |
| 整段落在 (0, +10pp) | 小正效应但不足采用阈值（`small_positive_below_threshold`） |
| 区间跨越上述界限 | 未定（`unresolved`） |

不得把 “upper < +10pp” 写成等价，也不得把 “(0, +10) 小正效应” 写成一无所知。

## 资源与执行（冻结）

T=24000，I=400000，K=120，hang=600s。各组共享，A 可使用全部额度。并发 **8** 个独立运行（独立 client/ledger/workspace/recorder）。分配 seed=`20260913`。Docker 以 **image id**（digest）为准，不以浮动 tag 为准。

K=40 批次的耗尽是该资源包络下的真实成本观察，不是日志覆盖类缺陷，不称为假象。正式结论以 T/I/K=24000/400000/120 为条件。

## 可恢复性

360 行一次性写入不可变 manifest。`--max-new` 只跑尚未开始的分配。`--resume` 继续同一 manifest。`passed`/`failed`/`error`/`interrupted` 不重跑、不覆盖。中断的 `running` 记 `interrupted` 并保留原调用。
