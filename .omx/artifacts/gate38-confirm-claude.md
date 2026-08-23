核查完毕。所有代码锚点与断言已对账，输出裁决。

## Verdict
PASS_WITH_NITS

## Findings

**第一轮 6 MAJOR 逐条核对（全部解决，代码锚点实测）**

- grok-MAJOR-1 ✅ §2.0 伤害链更正与代码一致：`evaluate_all_skills` 纳入口径实为 feedback/preferences/execution 三源（evaluator.py:246-254），D+60d warn 先 return（feedback_loop.py:140-152）且 warn 永不写生命周期；§2.6 联合 must-NOT 改为真实 `SkillEvaluation(total_routes=0, last_used=90d前)` 过 `analyze_all(auto_deprecate=True)` 断言 grade/suggestions/set_lifecycle 三条件，不再可空转绿。
- grok-MAJOR-2 ✅ 原子对 + §6 例外；F 规则链（feedback_loop.py:119-125）的风险推演与代码相符。
- grok-MAJOR-3 ✅ §2.2.8 删“唯一”、两入口枚举、§0.1 定性修正；boost 复活入 log 已进 §2.3（但见 NIT-2）。
- grok-MAJOR-4 ✅ §2.2.6 + dry-run must-NOT；构造 bug 实在 :105（`FeedbackLoop(evaluator)` 位置参数撞 project_root）、:148 同 bug 先于 :149 不存在的 `apply_auto_actions()`，均实测属实。
- grok-MAJOR-5 ✅ 展示面逐点全部对上代码：_health.py:156-162 图标链 else→🗑️、_quality.py:102 `:.0%`、status_cmd.py:38-43/:70-72、badges.py:203-223（`"?"` 阻断徽章=与今日 D 同结果，核实成立）、_config.py:246-248、_listing.py:245、optimization_service.py:184 ≥3 闸 + `.get(grade, 0.0)` 免疫。
- grok-MAJOR-6 ✅ 行级 `population:"hook"` + 双挂点披露覆盖 miss 侧；miss 侧确为 hook-only（tool_call_bridge.py:488-492 排除 CLI），缺省方向正确。

**两条驳回裁定——均接受，不重提**

- expiry 仅增量生效（驳回成立）：miss 侧回灌本就无日期闸（_classify :495-539），引入部署日期常量会造成 hit/miss 行间消费者可见的数据洞且与“未定”态不可区分；`hit_session_expired` 前缀可过滤把稀释问题留在消费端；且 write-once + spans 轮转依赖（§5 已记档）下，现在写入反而保住会被轮转掉的弱信号。
- CLI hit 落盘（驳回成立）：与 top_skills 的关键不对称——outcome 是派生数据（spans 仍在，未来可补派生），非写时不可回填；miss 侧 gate16 先例（:473-477）已论证 CLI 一次性 session 只能产出空洞 expiry 弱阳性，纳入即噪音。

**新问题（修订引入/残留）**

- [NIT] §2.2.10 替代能力表述过强（gate38-synthesis.md §2.2.10 / feedback_loop.py:155 / loader.py:149-165 / evaluator.py:246-254）：stale --auto 的 archive 规则要求 `grade in ("C","D","F")` 且技能在 evaluator 纳入口径内；零样本技能改后 grade="?" 永不命中，usage_stats-only 技能根本不进 evaluate_all_skills。而 loader 暗道原先是**不论 grade、不论有无评价数据**归档 DEPRECATED≥90d。即 gate38 后 DEPRECATED+"?"/无评价技能不存在任何到达 ARCHIVED 的路径（显式或自动）；且 loader 过滤只排 ARCHIVED 不排 DEPRECATED（loader.py:166），这些技能将永久留在可路由池。删暗道方向正确（已核实无既有测试 pin 此行为，删除零测试冲击），但应把“archive 显式入口只覆盖 C/D/F 档；DEPRECATED+?/无评价技能永久保持 DEPRECATED 并留在发现池”写成已知后果进 §2.2.10/CHANGELOG，不要暗示等价替代。
- [NIT] §2.3 三类动作收集机制未定义到“实际写入”粒度（gate38-synthesis.md §2.3 / feedback_loop.py:85-90,185-204）：`analyze_all` 不返回哪些写入真实发生——`_apply_boost` 仅在 lifecycle=="deprecated" 时写（:199-201），deprecate/archive 失败被 except 吞掉（:185,:193）。若按字面“收集全部三类动作的 suggestion”，log 与 "Applied Optimizations" 会包含未复活的 boost 与失败动作——正是“日志撒谎”的镜像。需 `_apply_*` 返回 bool（或 analyze_all 返回 applied ids）按实际 set_lifecycle 调用收集，并补 must-NOT：已 active 技能的 boost suggestion 不得出现在 log。

**抽查覆盖说明**：本轮实测约 25 处 文件:行号 断言全部相符，含 §1.2 bridge 锚点（docstring :32-47、SESSION_COMPLETE_HOURS :91、SPANS 硬编码 :97/:195、_run :221、_derive_outcomes :414-467、_is_miss 尾 :493、_classify 尾 :539）、agent_runtime.py:619-626/:668、cli/main.py:903-936（含 MagicMock 守卫惯例）、eval_routing.py:80/:91/:128/:174 恒 0、ci.yml:11 workflow_call 与 :105-110 观察期注释结构（证明“永久 report-only”注释确有必要）、extended yaml 四条目 :100-104/:118-121/:190-193/:302-304 与头部 :23-32 残余噪音自述、GOALS.md:104 / ARCHITECTURE.md:597 过时宣传、test_evaluation.py:40-50 双 pin、test_tool_call_bridge.py:496 先例、retention.py:72 "?" 词表冲突、dashboard/server.py:73-82 容忍解析、RetentionPolicy 死代码（全仓无生产调用方）。调用点全量清点：默认 True 的生产调用恰为 5 处，§2.2 覆盖无遗漏（retention.py:162 是 RetentionPolicy 自有方法、无 auto_deprecate 参数，不受默认翻转影响；skill_commands.py:451 走 end_of_session_check 即 §2.2.3）。
