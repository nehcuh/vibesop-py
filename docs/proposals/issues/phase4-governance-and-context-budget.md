# [FEATURE] Phase 4 · 治理与上下文预算：根文件瘦身 + 事故可追溯入库

> 对应路线图: `docs/proposals/harness-verification-roadmap.md` Phase 4（P2，穿插做）

## Feature Description

三个子项：根文件压成 ≤40 行索引型；builder 加常驻配置行数预算；经验入库加 `incident_ref` 事故追溯字段并作为 auto-promote 门槛。

## Problem Statement

1. **根文件超重**（违反文章「Map not manual」原则，仓库自身是反面教材）：
   - `CLAUDE.md` = 101 行、`AGENTS.md` = 109 行（手册型，编码标准/测试/部署全量铺开）；
   - 仅 `PROJECT_CONTEXT.md` = 30 行合规。
2. **生成配置常驻超预算**：`adapters/templates/claude-code/CLAUDE.md.j2` = 72 行（索引型✓），但 rules/ 常驻 ≈202 行（behaviors 114 + routing 33 + memory-flush 55）→ 每会话常驻 ≈280 行，远超 40 行注意力预算；builder 无行数预算机制。
3. **教训入库无事故门槛**：
   - `core/feedback.py:18-28` FeedbackRecord 无 incident/trace 字段；
   - `core/instinct/learner.py:44-59` Instinct 自由文本即入库，`:74,141` 晋升纯统计阈值（≥3 次+成功率 0.6 / ≥5 次+0.8）；
   - 事故溯源目前只存在于**注释惯例**（`routing_pending.py:14` 引用真实 M7 dogfood 事故）与**人审关**（`observability/skill_promote.py:28` W4 通道「未审不注入」），未制度化。

## Proposed Solution

| 项 | 动作 |
|---|---|
| 根文件瘦身 | CLAUDE.md / AGENTS.md 压成 ≤40 行索引型，细节外移到 docs/ 对应文档 |
| 生成配置预算 | builder 渲染时统计常驻行数，超预算（建议 100 行）告警或截断 |
| 事故追溯 | FeedbackRecord/Instinct 加可选 `incident_ref`；auto-promote 阈值要求非空（现有人审通道可豁免） |

## Alternatives Considered

事故追溯用硬必填——被否：存量数据无事故可指认，硬必填阻断入库；先可选 + promote 门槛软着陆。

## Additional Context

文章公式 ⑦ 的完整表述：「explain it → checklist it → automate the check → enforce it。每条规则都必须能指认背后的真实事故，指不出来就是噪音。」

## Priority

- [ ] Critical
- [ ] High
- [x] Medium

## Implementation Ideas

根文件瘦身注意 CLAUDE.md 的规则每条都有真实事故来源（文章原话 "I can name the night behind each one"），外移不是删除。

## Willing to Contribute

- [ ] Yes, I'd like to implement this feature
- [ ] No, I don't have time to implement it
- [x] Maybe, I'd need guidance

## Additional Notes

与 Phase 1–3 无依赖关系，可并行穿插。
