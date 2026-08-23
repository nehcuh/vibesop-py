/bin/sh: 30: No such file or directory
# Gate37 三路评审：独立复审报告

## Verdict
PASS_WITH_NITS

五个裁决全部站得住，核心代码事实核查通过。两个 MAJOR 均为 L2-lite 两列数据源的规格欠指明——恰是本稿 §0 声称已根除的"拿空表/假指标"风险在自家范围内复发，但正确数据源存在、实施时可一句话锁定，不构成 BLOCK。

## Findings

- [MAJOR] **L2-lite"显式反馈原始计数"未指明数据源，存在踩 analytics 陷阱的实装风险**。显式反馈主路径 `cli/feedback.py:38-44` 把满意度写进 **AnalyticsStore（opt-in 默认关，unified.py:1216）**，且每次反馈"读出末条记录→改写→追加新行"会虚增该 skill 命中计数——正是 Lane B 陷阱 2。真正 always-on 的按 skill 正/负原始数是 `ExecutionFeedbackCollector`（core/feedback.py:352，`<project>/.vibe/execution_feedback.jsonl`，由 cli/feedback.py:73-92 `_sync_to_evaluator` 写入 was_helpful/execution_success）。裁决稿只说"反馈原始计数"不写来源，实装者很可能选错源，复现本稿 §0 想消灭的空表问题。
- [MAJOR] **L2-lite"来源（market/promote/手工）"与数据模型不符**。已装技能只带 `source ∈ {builtin, project, external}`（external_loader.py:22-27 `SkillSource`），candidate dict 实测 `source` 值仅 external/builtin/project（239 个候选实测）。"promote"出处只在候选池 `source_skill_id`（skill_promote.py:928-945），"market"须经 pack lock 反查——三分类需要 2-3 个 join 或改口径，非"今天就有"的现成事实。另：fire 计数来自**项目本地** `spans.jsonl`，全局技能（~/.claude/skills 等）在任意项目里 fire 都记在当项目，`vibe skill list` 的 30 天 fire 对全局技能系统性欠报。
- [NIT] **"650 miss 语料 64% 回声"无实证支撑，且与实测不符**。gate35-echo-measure-cmspark.md:8-13 实测：miss 池 **525**、卡片回声 **9/21=42.9%**、池回声 4.8%。裁决 3 把 Lane C 的这两个数字原样吸收进否决理由；方向（回声污染）成立，量级差约 2 倍。L3 否决不依赖该数字，但裁决稿不应引用未测量数值。
- [NIT] **L3 重启条件从 Lane C 的 promote ≥30 降到 ≥10，无记档理由**。Lane C 原判"消融对象 n≈1"，重启线应至少对齐其原判；synthesis §2 裁决 3 定为 promote ≥10 且 verdict ≥30，L2b 却要单技能月 fire ≥30——同为 n 门槛，两处量级不一致且未说明。
- [NIT] Lane B"extended 集 5/8 正例"与实际不符：文件头自述 **4 of the 7 positives** 需 omx+superpowers 包（routing_eval_extended.yaml 头部注释）。环境依赖缺口本身（ci.yml:184-202 只跑 `pytest -m benchmark`，无 eval_routing.py）已核实成立。
- [NIT] "skill list 健康叙事雏形（skill_commands.py:94-119）"实际在 `_skill_overview`（vibe skill 无子命令回调，:48-49），`list_skills` 表格（:135-136）目前只有 ID/Name/State/Scope/Version 五列、无健康叙事。"该屏已有雏形、零新认知负荷"的理由指向了错误的屏——实施目标 list_skills 是对的，只是背书错位。
- [NIT] **spans 读取口径有两处未写进规格**：① `SpanWriter` 按 `is_dev_environment()` 分流 `spans.dev.jsonl`/`spans.jsonl`（span_writer.py:65），L2-lite reader 必须镜像该文件选择逻辑，硬编码 spans.jsonl 在 dev 下读错文件；② metadata 在文件中是**序列化字符串**（span_writer.py:83-92 json.dumps + 截断 + 脱敏），reader 需 json.loads；且 not_intercepted 分支（agent_runtime.py:508）的 span 无 skill_id/has_match（本仓 130 条 route span 中 54 条缺 has_match），fire 谓词必须写 `has_match is True` 而非存在性判断。
- [NIT] L4"小追加脚本"与既有 `scripts/build_eval_from_logs.py --merge` 管线（stratified+weak label+needs_review）功能重叠，应复用而非另造；追加样本应在追加脚本测试里顺带用 eval_routing.py smoke-run 验证可解析可跑，否则样本的路由后果无人检验。
- [NIT] L1 规则 4"description 非纯营销句式"是未标定启发式——Lane C"直觉冒充测量"的反对在弱意义上同样适用；保住它的条件是严格 lint 形态（只警告、无分数），裁决稿已如此，但建议与"可路由性阈值"的否决理由区分记档。
- [NIT] skill_id 改名/重装导致 30 天 fire 断链（Lane B 陷阱 9）在 L2-lite 规格中无任何处理；"n<30 不下结论"纪律部分覆盖，但改名后旧计数永久丢失值得在列头或文档注明。

## 对各裁决点的意见

- **裁决 1（L1 极简版做）**：站得住。零数据依赖、挂载点现成（pack_installer.py:270 `_audit_skills` 逐 SKILL.md 循环，install_pack :156/:227 已调用）、gate36 lint 件可复用（promote_verifier.py:431-449 triggers_nonempty/triggers_not_all_hygiene）、advisory 形态守住 gate36"灯不是闸"纪律。唯一软肋是规则 4 的未标定启发式，须保持纯 lint 性质。
- **裁决 2（L2 拆三层）**：方向正确且被代码证实——spans always-on、route span 带 skill_id/has_match（agent_runtime.py:668-692）确凿，30 天 fire 计数可行；fire→成功率"无数据源"的判断也正确（route_outcomes 只过滤 miss，tool_call_bridge.py:414）。但 L2-lite 三列中两列（反馈计数、来源）数据源未指明，见 MAJOR 1/2，实施前必须锁定。
- **裁决 3（L3 否决）**：结论正确——消融对象 n≈1、回放设施已有两份（replay_routing_baseline.py 的 p0_shadow 与 eval_routing.py）、离线回放答不了活体因果，且 eval_routing.py 为基座的方向比 replay_baseline 正确（后者 p0_shadow 与生产刻意分歧，已核实）。瑕疵：重启线 30→10 无理由、引用未测量数字，均需修正。
- **裁决 4（L4 不做 CI 硬阻断）**：正确。gate34 D4 同构成立（技能池是数据，硬阻断=合法操作变告警，gate34-synthesis.md:10/74），eval_routing 确实未进质量门（ci.yml 仅 `pytest -m benchmark`）；追加真实样本与 build_eval_from_logs.py 现有标注纪律一致。report-only job 留 gate38 与 L2a 捆绑议是合理的紧迫性排序。
- **裁决 5（meta 换皮检查）**：成立且有据——gate34 D1-D4 与 L1-L4 同构性从 gate34-synthesis.md:10-13 逐条可验。建议从"口头流程"固化为 gate34 不做清单 + 本裁决书的 checklist 项，并注明"第二次发生升级为流程"的触发源。

## 漏项（三路均未覆盖，供实施注意）

1. **spans 文件 dev/prod 分流 + metadata 字符串序列化**（span_writer.py:65,83-92）——L2-lite reader 与合成 fixture 测试必须镜像 SpanWriter 的文件选择与解析逻辑，否则 dev 下读错文件、解析崩。
2. **反馈口径失真**：`partial` 反馈在 `_sync_to_evaluator` 里被记成 `satisfied=False`（cli/feedback.py:33-35,58），execution_feedback 是二值，正/负原始数的"负"里混着"部分满意"。
3. **全局技能 fire 系统性欠报**（项目局部 spans，无全局聚合）——列头需注明口径为"本项目观测"，否则用户把欠报当"没被用"。
4. **Lane B 12 条陷阱仅 3 条进裁决稿**——其中陷阱 9（skill_id 改名断链）与 L2-lite 直接相关，建议在 gate37 内以一行文档处理而非全推给 gate38。

（只读核查，未修改任何文件。）
