# Gate39 实施双路复审任务书

你是独立高级评审，复审 VibeSOP 项目 gate39 的实施。项目根：/Users/huchen/Projects/vibesop-py。

## 设计规格

`.omx/artifacts/gate39-synthesis.md`（**r2 定稿**，含 §6 三轮收敛记录）是定稿规格。先读它，再读随附 gate39-impl.diff。

## 范围

主项 `vibe skill outcomes` 只读出口（新模块 core/skills/skill_outcomes.py + CLI + fire 列脚注补票）；搭车 A：tool_call_bridge dev/prod 文件名镜像（`_spans_filename()`）；搭车 B：RetentionPolicy 整文件删除 + 代码引用三处 + 文档引用四处。

## 评审要点

1. **规格符合性**逐条对照 r2 §1/§2/§3：
   - skill_outcomes：单次扫描双文件；复用 `_route_hit_skill_id` 谓词（metadata JSON 字符串容错+非空 str）；只处理 side=="hit"；**unjoined = span 缺失 ∪ skill_id 空/缺，对账式 Σ三列+unjoined=hit 总数**；last_at 取 span_ts（缺不更新）；排序字典序；spans 走 dev/prod 选择、outcomes 恒读 route_outcomes.jsonl；无比率/百分比/grade/处置。
   - CLI：五条脚注与 §1.2 r2 逐字一致；--json raw counts only；fire 列脚注补票行进 skill_commands.py:209-214 块。
   - bridge：`_is_miss`/`_classify`/`_is_hit`/`_classify_hit` 函数体零改动（diff 不得有这四函数的改动行）；读写两侧都走新选择；不镜像 exists-gate。
   - RetentionPolicy：整文件+测试文件删除；引用清单（candidate_manager/feedback_loop/evaluator + GOALS.md ×2 + skill-runtime-interface.md ×2）；收窄 grep 模式零残留；活符号（RetentionSuggestion/retention_actions/span_retention_days/retention-pool）未被误伤。
2. **不变量**：三套 trigger 语义、双 embedding、`_is_agent_prompt_shape`、gate30 upsert、存储双锁、spans 热路径。
3. **测试说服力**：混合 fixture 双锁（落空可察觉，不只测跳过）；must-NOT（含 --json）真能红；既有 miss 侧/bridge 测试断言语义零改动（WS2 申报只改文件名来源）。
4. **WS 申报的偏差裁决**：
   - WS1：unjoined 口径微扩（未知 reason 也计入，防御性保对账式）；unjoined 末行呈现为 `(unjoined: N)`；skill_commands.py 一处存量超长签名被 ruff format 折行（+4/-1 纯格式）；tests/cli/test_skill_list_health.py 加一条脚注断言。
   - WS3：skill-runtime-interface.md:266 保留未删（RetentionSuggestion 是活功能）。
   判断每项是否合理。
5. **文档同步**：CLI_REFERENCE outcomes 节（五条脚注、unjoined 说明、prune 交互提示）；CHANGELOG gate39 条目（叙事=数据第一次可见非效用结论、RetentionPolicy 破坏性变更点名、四个记档项）；check_docs 双过。
6. **隐藏破坏面**：grep `skill_outcomes|_spans_filename|RetentionPolicy` 兜底；`vibe skill outcomes` 与既有命令命名冲突；cmspark 真实数据验收快照（WS1 申报可归因 2400 + unjoined 37 = 2437，与 Lane C 基线吻合——可独立复核）。

## 输出格式（严格遵守）

```
## Verdict
PASS / PASS_WITH_NITS / BLOCK

## Findings
- [BLOCK|MAJOR|NIT] 描述（附 文件:行号）
```

只读核查（grep/read/跑测试），不要修改任何文件，不要客套。
