独立复审 gate37 裁决稿。先按路由协议匹配技能，再只读核对材料与代码事实。路由还在跑。我并行读评审技能、剩余材料，并抽查代码事实。路由把这次任务拆成 6 个技能，但用户要的是一份只读裁决复审、固定输出格式。我按独立评审做事实抽查，不跑访谈/改文件。行号对上了。接着核对 spans 口径、反馈存储、lint 重叠，以及 L2-lite 的数据源是否真的 always-on。代码事实已对上。下面按指定格式给裁决复审。

## Verdict
PASS_WITH_NITS

战略五裁可开工；实施范围按现状会交出两列假事实（来源、反馈）和一条全库 WARN。MAJOR 必须写进开工前补丁，不改层裁决。

## Findings
- [MAJOR] L1 第三条「有 when-not-to-use」在仓库里没有 schema/正文惯例：`SkillMetadata` 只有 `trigger_when`/`triggers`（`spec/models.py:101-102`），全仓 `SKILL.md` 无 "When not to use"。按字面实施会对存量（含 builtin）100% WARN，正是 Lane C 的 D4 告警疲劳。实施前删掉或改成可操作谓词（例如 body 仍含 gate31 TODO 槽）。[inspected]
- [MAJOR] L1 第四条「description 非纯营销句式」就是刚否决的「可路由性阈值」换皮：无标定、无反例集。现成硬门已是 `_is_valid_skill` description≥10（`pack_installer.py:630-645`）。第四条不进 gate37，规则集回到 Lane C 的 ≤3。[inspected]
- [MAJOR] L2-lite「来源 market/promote/手工」无数据。`_get_skill_source` 只返回 `builtin|project|external`（`candidate_manager.py:309-315`）。promote 不写 provenance 到 SkillConfig。列上写「手工」是说谎。先用现有三值，或显式不做来源列。[inspected]
- [MAJOR] L2-lite「显式反馈原始计数」未指定 store，默认安装下是空列：analytics 默认关（`unified.py:1216-1237`）；`_collect_feedback` 仅 TTY `vibe route`（`cli/main.py:1469-1470`）；hook 主路径无反馈 UI。fire（spans，hook+CLI）与反馈（CLI TTY / `vibe feedback record`）来自不相交总体。必须钉死 store，空数据展示「无记录」禁止暗示「中性」。[inspected]
- [MAJOR] fire 计数口径未写死，复用 `SpanAggregator` 会直接违纪：`total_executions` 计所有带 skill_id 的 task span，`success_count = status=="ok"`（管道没抛错，`aggregator.py:126-131`），默认 24h 且 `use_analytics_fallback=True`。正确谓词已在仓库：`span_kind=="task"` 且 `name.startswith("route:")` 且 `metadata.has_match is True`（`gold_detection.py:108-163`；producer：`agent_runtime.py:461-692`、`cli/main.py:827-914`）。metadata 经 SpanWriter 变成 JSON 字符串，必须反序列化。一次扫描全表，禁止 per-skill 重读，禁止对 `spans.jsonl` 持 flock（writer 是 LOCK_EX，`span_writer.py:47-50`；list 持锁会卡住 hook 热路径）。[inspected]
- [MAJOR] 仓内已有假 L2，三路和裁决稿都当它不存在：`vibe skills report` 输出 Grade/Score/Success% 和 ±boost/demote（`_quality.py:62-107`）；`RoutingEvaluator.quality_score` 在 `total_routes==0` 时仍返回 ~0.5（`evaluator.py:64-66`）；`FeedbackLoop.analyze_all(auto_deprecate=True)` 会自动 deprecate F 档（`feedback_loop.py:66-86`），与「永久不做自动降级」冲突。gate37 不做清单必须点名：list 列不得调用 evaluator/aggregator.success_rate；`stale --auto` 保持人审闸，本 gate 不接线。[inspected]
- [MAJOR] `_audit_skills`（`pack_installer.py:270-281`）是安全审计挂载点，输出 `PASS if audit.is_safe else WARN`；前置 CRITICAL/HIGH 已 fail-closed（`:208-213`）。内容 lint 若喂进 `is_safe`/`has_high` 会把 advisory 变成闸。必须挂在安全审计之后、只追加独立 advisory 行；`skill_installer.install_skill` 的 `warnings[]`（`:73`）才是单技能入口，不要混进安全 PASS/WARN。[inspected]
- [NIT] 「`skill_commands.py:94-119` 已有健康叙事雏形」张冠李戴：那是 skill hub（`all healthy` 来自 evaluator+stale），真正的 `vibe skill list` 只有 ID/Name/State/Scope/Version（`:145-177`）。加列合理，但不是「该屏零新认知负荷」。Lane A P0「不借助其他命令能指出可疑及原因」在「lint 不上看板」后也不成立——装完 finding 蒸发。[inspected]
- [NIT] L3 重启条件 internally 打架：Lane C `promote≥30`，裁决稿改 `promote≥10 且 verdict≥30`，无论证。n=10 按技能分摊仍是个位数。绑 `verdict≥30` 即可，promote 阈值不要私自放松。[inspected]
- [NIT] L4「107 条 scored」只描述 `routing_eval_extended.yaml`；全套是 34+107+11+22=174。追加应走已有 `scripts/build_eval_from_logs.py --merge` + `needs_review`（retention 集已有 22 条 `needs_review: true`），不要新脚本。cmspark 已裁决 query 不在本仓，本项依赖 dogfood 导出；MCP cmspark 本会话连不上。[executed 计数 / inspected 管线]
- [NIT] `count_skill_route_hits` docstring 仍写 analytics 是「唯一按 skill 命中流」（`discovery.py:43-47,604-617`）。L2-lite 禁止走它；反馈 duplicate-append（`cli/feedback.py:38-44`）会继续虚增该计数。skill_id `/` vs `-` 规范化（`candidate_manager.py:140-141`）join 会断。[inspected]
- [NIT] 「一天级」四项含全量 pytest/e2e 偏紧；list 读 spans 必须 file-missing→空、不 mkdir（看板守卫在 `_discoveries.py:29-33`）。conftest embedding stub（`tests/conftest.py:282-323`）与「本 gate 不做 embedding lint」一致，无新风险。看板只读未被本 gate 触达，保持。[inspected]

代码事实抽查（7 处）：analytics 默认关、outcomes 只覆盖 miss、反馈重复行、tracer 默认开、eval yaml/`eval_routing.py` 存在、`_audit_skills:270`、hub `:94-119` —— 均成立。唯一用词误差：668-692 是 **task span**（`name=route:…`），不是独立 route span kind；消费者约定见 `gold_detection.is_route_miss_span`。[inspected]

## 对各裁决点的意见
**裁决 1 L1 极简 lint —— 做。** 层裁决正确：零数据依赖、advisory、挂现成安装链、embedding 不做。规则集不能按原文四条开工：when-not-to-use 无字段、营销句式是未标定阈值。落到 ≤3 条可测谓词（triggers 非空且非全 `_is_agent_prompt_shape` / 正文非 TODO 空壳 / description 已有 ≥10 硬门不必再造），并与安全 WARN 分列。

**裁决 2 L2 拆三层 —— L2-lite 现在、L2a gate38、L2b 推迟。** 拆法正确，fire→成功率/preemption 缺数据源的判断成立，词汇 hijack vs preemption 该分开。L2-lite 实施稿漏了口径：来源词表、route-span∧has_match 谓词、反馈 store、单次无锁扫描、以及仓内已存在的假记分卡（`skills report` / `stale --auto`）。不补这五项会把「只读事实」做成新的自欺列。

**裁决 3 L3 否决当前形态。** 成立：n≈1、第三份回放、离线≠活体。基座用 `eval_routing.py` 而不是 `replay_routing_baseline.py` 的纠正对。重启条件保留 `verdict≥30` + 一次性报告、不建 harness；不要把 promote 门槛从 30 悄悄改成 10。

**裁决 4 L4 不做 CI 硬阻断，只追加真实样本。** 与 gate34 D4 同构论证成立，CI 硬阻断应永久否决。增量应 merge 进现有 yaml + 现有 builder，不要新 harness；report-only job 留 gate38 合理。本项的真实依赖是 cmspark 已裁决标签能否导出，不是再写一套评测器。

**裁决 5 meta 换皮检查。** 成立，应升级为流程。落地要指定对照物路径（gate34 不做清单 + 本裁决书 §4），否则第三次换皮时仍会「先写四层再被三路拆掉」。
