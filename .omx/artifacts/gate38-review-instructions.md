# Gate38 设计稿三路评审任务书

你是独立高级评审，复审 VibeSOP 项目 gate38 的设计综合稿。项目根：/Users/huchen/Projects/vibesop-py。

## 被审对象

`.omx/artifacts/gate38-synthesis.md`（随附全文）。它是三路独立对抗（设计/怀疑/用户视角）后的裁决稿，范围三项：L2a 仪表化（span metadata top_skills + hit 侧 outcome 派生）、假 L2 处置（evaluator 零样本 + auto_deprecate 五调用点 + optimize_cmd 死代码）、report-only CI（requires_packs schema + continue-on-error job）。

## 历史裁决参照（先读）

- `.omx/artifacts/gate37-synthesis.md`（§4 不做清单、修订 B/C/I、裁决 2/4）
- `.omx/artifacts/gate34-synthesis.md`（不做清单）

## 评审要点

1. **换皮检查**：本稿三项是否真的是 gate34/gate37 明文 deferred 的项？有没有被永久否决方向的换皮复活（尤其：CI 是否变相硬阻断、是否新增比率/分数/自动处置）？
2. **不变量**：三套 trigger 匹配语义、双 embedding 分离、`_is_agent_prompt_shape`（skill_promote.py:366 冻结）、gate30 upsert、`_is_miss`/`_classify` 语义、存储双锁风格、spans 热路径 100µs p95。设计是否零触碰？
3. **裁决合理性**（重点攻击三处裁定）：
   a. top_skills 保留（Lane C 主张砍）：不可逆性论证（写时数据 vs 派生数据）是否成立？无消费方数据是否违反项目自己的最小化纪律？
   b. hit outcome 仅非 CLI + 口径披露：B 揭示的"fire 列含 CLI、hit outcome 不含 CLI"双总体矛盾，docstring 披露是否足够？还有更优解吗？
   c. `optimize --apply` 起死回生（A 案）而非删除（B 案）：哪个对？
4. **证据核查**：设计稿中的 文件:行号 引用抽查至少 10 处，确认真实存在且含义相符（尤其 evaluator.py:64-66 零样本分支、feedback_loop.py:66/196-204/208/246、optimize_cmd.py:106/140-157 死代码断言、tool_call_bridge.py:414-539、agent_runtime.py:620-626/667-700、cli/main.py:899-936/1700-1721、eval_routing.py:174 恒 return 0、ci.yml:110 continue-on-error 先例、release.yml:15-21 workflow_call）。
5. **完整性**：设计有没有漏掉的消费者/调用点（全仓 grep `.grade`、`analyze_all`、`quality_score` 兜底）？测试计划能否抓住声称的行为？假 L2 修复的顺序依赖（先拆 auto 再改数值）在单提交原子落地的裁定下是否还有残余风险？

## 输出格式（严格遵守）

```
## Verdict
PASS / PASS_WITH_NITS / BLOCK

## Findings
- [BLOCK|MAJOR|NIT] 描述（附 文件:行号）
```

只读核查（grep/read），不要修改任何文件，不要客套。
