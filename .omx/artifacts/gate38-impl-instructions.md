# Gate38 实施双路复审任务书

你是独立高级评审，复审 VibeSOP 项目 gate38 的实施。项目根：/Users/huchen/Projects/vibesop-py。

## 设计规格

`.omx/artifacts/gate38-synthesis.md`（**r3 定稿**，含 §7 三轮收敛记录）是定稿规格。先读它，再读随附 gate38-impl.diff。

## 范围

三项：L2a 仪表化（span metadata top_skills + tool_call_bridge hit 侧 outcome 派生）、假 L2 处置（evaluator 零样本原子对 0.0+"?" 、auto_deprecate 默认翻转 + 5 调用点显式化 + optimize_cmd 死代码修复 + loader.py:149-165 静默 auto-archive 整块删除 + 展示面 "?" 逐点）、report-only CI（eval_routing skipped_env + requires_packs schema + ci.yml routing-eval job）。

## 评审要点

1. **规格符合性**：逐条对照 r3 §1/§2/§3 的每个 bullet。重点：
   - top_skills：仅 hit 写键；hook 侧用 `result.router_matched` 而非 `has_match` 属性；CLI 侧条件与 has_match 写入同表达式、数据源是 result 对象；≤3；MagicMock 守卫；非 hit 整键省略。
   - hit outcome：`side:"hit"` + `population:"hook"`；miss 行不回写；write-once + span_id 去重；CLI hit 排除；`_is_miss`/`_classify` 函数体零改动（diff 里这两函数不得有任何改动行）。
   - evaluator：0.0 与 "?" 同 diff 原子出现；feedback_loop 默认 False；`_apply_*` 返回 bool、applied 只含实际写入；loader 整块含 `continue` 删除、DEPRECATED 留在发现集；展示面四处（_health/_quality/status_cmd/slash_commands）"?" 处理。
   - eval_routing：skipped_env 不计分母不进 errors、expect 非空才 skip、presence 失败按存在、聚合不除零、退出码恒 0、**无 --strict**；ci.yml job continue-on-error + 永久 report-only 注释，既有 job 零改动。
2. **不变量**：三套 trigger 匹配语义、双 embedding 分离、`_is_agent_prompt_shape`（skill_promote.py:366）、gate30 upsert、存储双锁风格、spans 热路径 100µs p95。
3. **测试说服力**：must-NOT 是否真能红（防空测）；联合 must-NOT（零样本+90d+auto=True → grade "?" 且 suggestions 空）是否用真实 SkillEvaluation；loader 双锁（不写+可见性）；既有 miss 侧测试零改动（WS1 申报了 1 处最小偏差：test_unknown_and_not_intercepted_never_enter_miss_pool 的文件级断言改为过滤 side!="hit"——判断是否合理）。
4. **文档同步**：CHANGELOG gate38 条目五个行为变化点名；CLI_REFERENCE 三入口枚举/fire 列警示/零样本显示；GOALS.md:55,104、ARCHITECTURE.md:597,603、ROADMAP.md:45,354、USE_CASES.md + USE_CASES.en.md 的自动归档宣传是否全部清除或改写为显式入口；eval-set-append-workflow.md requires_packs 字段说明。
5. **隐藏破坏面**：全仓 grep `.grade`、`analyze_all`、`quality_score`、`set_lifecycle` 兜底，找规格清单外被行为变化波及的消费方（WS2 申报 cleanup_cmd.py 直调 `_apply_*` 返回值被忽略、_quality.py --grade help 已补 "?"——核实）。

## 输出格式（严格遵守）

```
## Verdict
PASS / PASS_WITH_NITS / BLOCK

## Findings
- [BLOCK|MAJOR|NIT] 描述（附 文件:行号）
```

只读核查（grep/read/跑测试），不要修改任何文件，不要客套。
