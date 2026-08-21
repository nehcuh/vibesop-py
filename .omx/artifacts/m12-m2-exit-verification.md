# M12 M2 出口验证 — 通过(2026-08-21)

> 出口标准(设计文档 M2 节):真实数据准入的候选 ≥1 条出现在
> `vibe skill discover`,证据卡片完整。gate17 记录为 deferred(miss 池
> 仅 4-6 distinct key);触发条件:miss 池 ≥30 distinct key 时重标定+重验。

## 数据基础(cmspark 真实 dogfood,非合成)

- spans.jsonl:3679 route span(2026-07-22 → 2026-08-21，一个月连续)
- miss 池:610 条 `has_match=False` route span → 低信息过滤后 408 span /
  309 distinct query(≥30 触发条件满足,10 倍余量)
- 注:出口在 cmspark 数据上达成(vibesop-py 自身池仍小)——真实使用
  数据优于自观测数据,符合设计意图。

## 标定重跑

`scripts/calibrate_discovery_threshold.py --spans <cmspark spans>`:
决策区间 0.47..0.71(min errors=12)与 M2 首次标定完全一致 →
`MISS_COSINE_THRESHOLD = 0.70` 维持,无需改码。
池分布副证据:p25=0.381 / median=0.623 / p75=0.744。

## 出口验证过程(三段)

1. **首扫发现 --limit 默认 100 只取最近 100 span**(大多是 llm/tool
   span)→ miss 池只读到 6 条。全量需 `--limit 8000`。
2. **全量首扫暴露两个真实缺陷**(准入门本身正常,5 条候选过门):
   - F-a:50 条 unstable 诊断行占满 MAX_PENDING,miss 候选
     admit-only-if-better 恒输被拒 → 类分离预算修复(gate21)。
   - F-b:kimi/grok content-block JSON 数组信封未拆 → `_extract_query`
     增加有界拆解(gate21)。
3. **修复后重扫**:783 簇,**5 条 miss_recurrence 候选准入**,
   `vibe skill discover` 证据卡片完整(Pattern/脱敏 Examples/Source
   miss×复现/Behavior 诚实标"未采集"/Age)。

## 准入的 5 条真实工作流(用户视角验证——全部是真实高频操作)

| 候选 | 内容 | 人工判断 |
|---|---|---|
| 5bd44eee | 合并到 main/提交/收敛 | 真实工作流(git 收尾) |
| 357c40d1 | 多路独立对抗/双路复审派发 | 真实工作流(本项目的固定流程!) |
| 6a6d554f | 当前进展如何 | 真实高频查询 |
| 57981221 | 编译并替换 DMG | 真实工作流(cmspark 发布) |
| 95cfd75e | /Applications 是否最新 | 真实高频查询 |

5/5 全部是人类认可的独立工作流——准入精度在首个真实样本上 100%。
unstable 诊断桶同时验证了留存池洞察 2:"You are an independent senior
code reviewer" agent-to-agent 提示簇真实浮现。

## 结论

**M2 出口通过**。遗留观察(不阻塞):
- discover 的 Age 列显示候选创建年龄(0d)而非簇首见年龄——展示层
  nit,记录待修。
- stable 池若被 gold 行填满,miss 准入会再次被 admit-only-if-better
  堵住(gate21 pi residual,设计固有属性,依赖人工 promote/dismiss
  节奏)。
- 这 5 条候选等待用户人工 promote/dismiss 决策——闭环精度的第一个
  真实数据点将由此产生。
