# Gate39 设计稿三路评审任务书

你是独立高级评审，复审 VibeSOP 项目 gate39 的设计综合稿。项目根：/Users/huchen/Projects/vibesop-py。

## 被审对象

`.omx/artifacts/gate39-synthesis.md`（r1，随附全文）。三路独立对抗后的裁决稿。主项是 Lane C 提出的新提案 `vibe skill outcomes` 只读出口；搭车两项（bridge dev/prod 文件名镜像、RetentionPolicy 死代码删除）；砍/推迟四项（verdict backfill、dashboard 端点、薄样本字母档、性能）。

## 历史裁决参照（先读）

- `.omx/artifacts/gate38-synthesis.md`（§5 记档清单——本稿与之有实质偏离，偏离合理性是评审重点）
- `.omx/artifacts/gate37-synthesis.md` §4、`.omx/artifacts/gate34-synthesis.md` 不做清单

## 评审要点

1. **新主项攻击**（最重要）：`vibe skill outcomes` 是不是换皮？它与 gate37 健康列、gate38 hit outcome 披露的关系是否如稿所述"同构可视化"？设计里有没有暗藏的比率/分数/处置派生？join 键（outcome.span_id → span id）在真实数据上的可靠性（Lane C 声称 cmspark 2437/2437 全命中——抽查验证）？三 reason 分列 + 脚注纪律够不够防"reask 多=技能差"的误读？
2. **砍/推迟裁决攻击**：backfill 砍除的三条理由（答错问题/时空错位/刷不动触发器）是否成立？dashboard 推迟的重议触发条件是否合理？薄样本推迟的"F 规则唯一燃料"冲突（feedback_loop.py:147）是否属实？
3. **搭车项正确性**：bridge 镜像的 fixture churn 预警（pytest 下 is_dev_environment() 为真导致现存 fixture 失配）是否属实、代价评估是否合理？RetentionPolicy 删除的引用清单（candidate_manager.py:265、feedback_loop.py:122、evaluator.py:86）是否完备（全仓 grep 兜底）？
4. **证据核查**：抽查至少 8 处 文件:行号（重点：promote_verifier.py:11-12 verdict 语义、skill_health.py:41-47/:97-133、tool_call_bridge.py:130/:229/:273、span_writer.py:55/:64-69、retention.py:51-190 无生产调用方、cmspark outcomes 行数与 join 命中率）。
5. **完整性**：这个范围有没有漏掉明显更该做的事？主项的 CLI 形态（独立子命令 vs skill list 加列）裁决是否该在评审层定死？

## 输出格式（严格遵守）

```
## Verdict
PASS / PASS_WITH_NITS / BLOCK

## Findings
- [BLOCK|MAJOR|NIT] 描述（附 文件:行号）
```

只读核查（grep/read），不要修改任何文件，不要客套。
