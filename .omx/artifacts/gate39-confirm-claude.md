核查完成。三个 MAJOR 的处置全部对上源码；cmspark 数据面本会话仍被跨项目权限拦截（与第一轮相同），维持 [assumed]，r2 的验收快照处置不受影响。以下为评审结论。

## Verdict
PASS_WITH_NITS

## Findings

- [NIT] 我方 MAJOR-1 的修订仍留一个可挑刺的集合论断言：脚注「口径不同（**子集关系**非不相交）」（synthesis §1.2）在“路径覆盖”读法下成立（hook ⊂ hook+CLI），但两列时间窗不同（fire=30d，outcomes=全期含回灌），回灌主导项目（如 cmspark）数值上 outcome 计数可**大于** Fire 30d——“子集”按数字读法仍可证伪。建议脚注直接写事实差异「fire=30d 窗含 CLI；本表=全期仅 hook」，不再做任何集合关系断言（本轮 MAJOR 的教训是：防误读纪律里不放假的可证伪陈述）。
- [NIT] `unjoined` 计数语义未钉死边界：§1.2 只定义“join 落空”可见，但混合 fixture（span 不存在 + skill_id 空串）没有分别给出期望数——空串 skill_id 行（实测 37/2437，写侧洞 agent_runtime.py:668 已 defer 到 §4.6，会持续产生）到底计入 unjoined 还是仅 span-not-found 计入？若仅后者，这一活洞行类在输出中除静态脚注外零可见，部分复现 MAJOR-2 要防的静默缩水。钉一句定义即可（建议两者都计入，或拆两个计数）。
- [NIT] §4.3 记档「spans 无轮转、无界增长」忽略了**现存**的手动释放阀：`vibe trace prune --days N`（trace_cmd.py:611，按龄删 spans.jsonl）今天就能造成 outcome span_id 悬空——unjoined 计数不是“防未来轮转”，是防现存命令；记档 3 应补 prune 交互，且这反而强化了 unjoined 的必要性。
- [NIT] 行号漂移两处（均不影响定位，实施时顺手校准）：fire 列脚注实际块为 skill_commands.py:209-214（r2 引 ：212-215，:212-213 是脚注²尾行、:214-215 已入脚注③）；F 规则实际为 feedback_loop.py:143-148（r2 处置表写 ：143-147，闭合括号在 ：148）。

核查确认已解决（要点）：MAJOR-1 修订主体正确（skill_health.py:55-57 确证 fire 含 CLI，“禁止拼比率”保留）；MAJOR-2 unjoined+双锁 fixture 已入设计与测试规格；MAJOR-3 四处文档引用逐行坐实（GOALS.md:48/:105、skill-runtime-interface.md:265/:266/:341），收窄后 grep 模式确不误伤三个活符号（RetentionSuggestion=feedback_loop.py:29、retention_actions=skill_commands.py:465、span_retention_days=config/manager.py:553）。NIT 抽查全过：span_ts/字典序/--json raw-only 三项钉死；_route_hit_skill_id 复用（skill_health.py:68-78 谓词与空串守卫逐行核对）；「证据含任意路径后续路由」与 _classify_hit（tool_call_bridge.py:671-681 扫全部 route_spans 含 CLI）一致；dev 不对称先例属实（execution_feedback 无 dev 变体，feedback.py:85/evaluator.py:158）；bridge :129/:130/:229/:273、dashboard 五处 ：137/:195/:296/:330/:344、evaluator 三读 ：172/:204/:205、promote_verifier.py:11-13、`outcomes` 命名无冲突（skill 单数组命令清单核对）、fixture 集中 helper（test_tool_call_bridge.py:32-33/:72）全部精确。r2 新增陈述未见结构性新问题。
