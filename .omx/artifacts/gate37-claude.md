核查全部完成（测试收集 6137 条）。以下是评审。

## Verdict
PASS_WITH_NITS

## Findings

事实核查确认：任务书列出的 10 项代码声称**全部属实**——analytics 默认关（unified.py:1216-1237，F-06 opt-in）；route_outcomes 仅 miss（tool_call_bridge.py:429 过滤 `_is_miss`，:420-424 write-once 弱信号声明）；反馈重复行（cli/feedback.py:39-44 读末条→改→`record()` 追加新行）；spans always-on 且 route span 带 skill_id/has_match（agent_runtime.py:668-692；tracer.py:44-52 `enabled=True` 默认，生产无 `enabled=False` 调用点）；routing_eval*.yaml（34+107+22+oneshot 条，needs_review 字段齐全）+ eval_routing.py + build_eval_from_logs.py 均在 git；`_audit_skills`（pack_installer.py:270-282）、`install_pack`（:98）、`_is_valid_skill` desc≥10（:630-645）；skill list 健康叙事（skill_commands.py:91-99 "all healthy"）；ci.yml:184-202 仅跑 `pytest -m benchmark`、eval_routing.py 从未进 CI；conftest embedding stub（conftest.py:299）；promote_verifier :11-15 scope 声明与 :431-449 lint 件可复用。测试基线实测 6137 collected（任务书 6123，已有增量，非问题）。

- [MAJOR] L2-lite “显式反馈原始计数”未指定数据源，而现存反馈存储**三分裂且读写错位**：`vibe skills feedback` 写全局 `~/.vibe/execution_feedback.jsonl`（_quality.py:153 默认构造器），交互式反馈写项目级 `<project>/.vibe/execution_feedback.json[l]`（cli/feedback.py:85），`RoutingEvaluator` 读项目级 `.vibe/feedback.json` + `execution_feedback.json`（core/skills/evaluator.py:141-148），analytics 路径默认关。读任何单一文件都只见部分数据——这正是 Lane B 用 F-06 否掉原提案的那类“以为有数据源”错误，三路与 synthesis 均未发现。开工前必须裁决口径（或合并读取），且应复用 `ExecutionFeedbackCollector.get_skill_summary`（core/feedback.py:393）而非新写解析器。
- [MAJOR] fire 计数 spans 读取口径未定：spans.jsonl 按项目落盘（tracer.py:4,51，CWD 相对路径），技能全局中心化（pack_installer.py:110-113 `~/.config/skills`）。`vibe skill list` 只能数当前项目的 fire，技能在他项目的命中不可见 → “从未 fire”列将系统性误报（与 Lane A 自己的“窄触发技能误杀”警告叠加）。W5.1 已有 cross-project pool 先例；至少列头须标注口径为“本项目”。另需明确 is_cli route span 是否计入（tool_call_bridge.py:488 对 miss 的 CLI 排除不自动适用于 hit 计数）。
- [MAJOR] 裁决 4 最小版缺脱敏强制项：cmspark 真实 query 进 git-tracked yaml 是一次性泄漏，与本仓 F-06（为隐私把 analytics 默认关）同构。机制现成——build_eval_from_logs.py:32 已用 `redact_sensitive`、promote_verifier.py:458 有 `_redact_query`——但 synthesis §3.3 只说“沿用 needs_review/retention 标注纪律”，未把脱敏列为追加流程的强制步骤。
- [NIT] 裁决 1 自称“采纳三路交集”但列出 4 条规则，超 Lane C 明确的 ≤3 上限；且“非纯营销句式”“具体步骤（非软措辞）”与被砍掉的“可路由性阈值”同为未标定文本启发式——advisory 定位下危害有限，但应要么砍到 3 条、要么给 must-NOT-catch 反例测试兜底。
- [NIT] 裁决 3 重启阈值从 Lane C 的 promote ≥30 无论证放宽到 ≥10；基座改选 eval_routing.py 有 Lane B 论证支持、正确，但阈值变动应记理由。
- [NIT] Lane B 陷阱 9（skill_id 改名后 spans 旧 id 计数断链）未落进 L2-lite 实施清单——promote 改名技能的 fire 列会静默归零，与“展示而非处置”纪律冲突面小但会误导人审。
- [NIT] yaml 追加须沿用 wrapper 剥离 + redact 后 join 的纪律（build_eval_from_logs.py:111-125 `strip_wrapper(redact_sensitive(query))`）；手抄路径会破坏与 analytics 侧标签的 join。建议追加流程直接规定“只走脚本，不手改 yaml”。

## 对各裁决点的意见

**裁决 1（L1 极简 lint）**：站得住。挂载点、复用件（promote_verifier.py:431-449 三条 lint 检查现成）、advisory 不阻断的边界全部核实，与安装链 CRITICAL/HIGH fail-closed 不冲突。瑕疵仅是规则数与两条未标定启发式（见 NIT）。

**裁决 2（L2 拆三层）**：拆法正确，L2b 前置条件沿用 Lane C 合理，L2a 的“不改 _is_miss/_classify 语义”约束与 tool_call_bridge.py:479-492 的 gate17 交叉引用注释直接呼应、必要。但 L2-lite 两个“今天就有数据源的事实”各有一半不成立——反馈源三分裂、fire 计数跨项目盲区——两个 MAJOR 都是开工前一句话能定但必须定的口径，定完本裁决即成立。

**裁决 3（L3 否决）**：否决正确（n≈1、第三份回放设施、回声掏空语料三论据均成立）；基座选 eval_routing.py 而非 p0_shadow 是正确的技术裁决；“一次性报告不建常驻 harness”形态好。唯一瑕疵是重启阈值 30→10 的无论证放宽。

**裁决 4（L4 不做 CI 硬阻断）**：正确。D4 同构论证成立，ci.yml 现状也证实 eval_routing 从未进过任何门；report-only job 推迟 gate38 与 L2a 绑定议是有依赖意识的安排。最小版可行，但必须把脱敏写成强制步骤、追加只走脚本（见 MAJOR/NIT）。

**裁决 5（meta 换皮检查）**：正确且必要。建议加一条配套规矩：凡新提案声称“已有数据源/已有 80% 现成件”，立项时必须附 文件：行号 核查清单——Lane B 本轮已示范此做法，而 L2-lite 的反馈源分裂恰是缺这道工序的产物。
