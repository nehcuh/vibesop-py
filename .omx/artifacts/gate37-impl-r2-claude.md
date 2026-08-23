核查完毕。输出第二轮复审结论。

## Verdict
PASS_WITH_NITS

## Findings

**逐项修复验证（全部核实）：**

- **pi-MAJOR 已正确修复**。dismiss 分支（scripts/build_eval_from_logs.py:262-265）要求 `dismissed is true` **或** `retention_reason` 字段，且需 `needs_review: false` + 空 expect 三条件同时成立；无标记 `expect: []` 落入 remaining（:285-286）保持 scored no-match 语义，与 eval_routing.py:74-88 的三元判断一致。**零迁移可信**：bash 执行审批被拒未能复现实证 run，但演绎证明成立——Grep 证实真实 routing_eval_extended.yaml 全文件 0 处 `dismissed`/`retention_reason`（107 条 = 102 条内联 `expect: []` + 5 条多行正例），无标记则 retention 分支不可达，0 条可被迁移；`test_unmarked_empty_expect_is_not_swept_to_retention` 锁定该行为且已实际跑过通过。注：修复声明称“100 条负例”，实际文件为 102 条——计数小出入，不影响实质结论。workflow 文档（docs/dev/eval-set-append-workflow.md:32-43）三分支（正例/无标记 no-match/显式标记 dismiss）表述与代码精确一致。
- **claude-NIT-1 已修复**：redact 先于判重/回填（build_eval_from_logs.py:249-258），dedup 键与回填（`main_queries.add(key)`/`retention_queries.add(key)`）均用 redact 后形态；`test_merge_redacts_before_dedup`（两 email 同 redact 形态只落一条）锁定。
- **claude-NIT-2 已修复**：`test_real_loader_populates_source_key` 走真实 `_load_skills()` 断言所有候选 source ∈ 三值集，实际执行 PASSED。
- **claude-NIT-3 已修复**：CLI_REFERENCE "an already-installed skill returns early and is not re-linted" 与 skill_installer.py:92-110 早退位置一致。
- **pi-NIT-1 已修复**：`TestParseSpanTime` 四用例逻辑核过（wall 29d20h/+08:00 = UTC 30d4h 排除、wall 30d4h/-08:00 = UTC 29d20h 计入——偏移方向正确）。
- **pi-NIT-2/3 已修复**：`_append_entries` comment-only 头保留（:166-195）；retention 迁移条目保 `needs_review: false` + 必带 `retention_reason` + `dismissed` 键消费（:274-280）；文档 Discipline 段区分存量池（原 weak label）与 gate37 dismiss（expect:[]）两种 schema。
- 其余不变量抽查无回归：`_is_agent_prompt_shape` 与 skill_promote.py 零改动（git status 未列）；lint 骨架 5 个字面量逐条对上 skill_promote.py:2074/2158/2163/2179/2187；`spans_file_for` 与 span_writer.py:65 dev/prod 选择逐字镜像；反馈走 `get_records()`（feedback.py:381-391），`get_skill_summary`/evaluator/aggregator 新代码零引用；lint 挂载独立于 `_audit_skills` 不进 is_safe/has_high；工作树与 r2 diff 全量一致无旧版漂移；4 个测试文件 57 passed。

**新问题：**

- [NIT] extended 重写路径丢失 40 行人审 provenance 头部（scripts/build_eval_from_logs.py:298-302）。pi-NIT-2 修复给 main/retention 两个写点加了头部保留，但第三个 sibling 写点——extended 文件重写——仍是裸 `yaml.safe_dump(remaining)` 全量覆盖。真实 extended 文件头部承载 tier3 label-audit 出处、环境依赖说明、130=107+22+1 算术等审计信息；文件现有 5 条 `needs_review: false` 正例待合并，下一次真实 `--merge` **必然**触发重写并静默丢头（数据条目无损，git 可找回）。建议该写点同样走头部保留，或重写时回写头注释。
- [NIT] merge redaction 只覆盖 `query`，其余键原样落盘（scripts/build_eval_from_logs.py:255、:274）。具体：(a) 正例条目上手写 `note:` 不经 redact 进入主集——流程文档自己鼓励可选 note（eval-set-append-workflow.md:35-36），修订 I 的“落盘前强制 redact”未覆盖这唯一的自由文本伴随字段；(b) 正例分支只剥 `needs_review`/`weak_label`，矛盾输入（expect 非空 + `dismissed: true`）会把 dismiss 标记键泄漏进主集 schema。人写文本威胁面小，严重度低，但与写边界脱敏纪律不完全自洽。
