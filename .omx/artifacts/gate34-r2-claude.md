## Verdict
PASS_WITH_NITS

## Findings

- [MAJOR] **§3 实施路线与修订 C/E/F 未同步，文档内部自相矛盾**。§3 阶段一第 2 步仍写“agent-echo 打标（复用 `_is_agent_prompt_shape` 只读调用）”，与修订 C“新增 `_has_agent_prefix`（仅前缀、无 150 长度规则）”直接冲突——且代码证实两谓词语义实质不同：`_is_agent_prompt_shape` 对 `len(q)>150` 无条件判真（skill_promote.py:376-377，OR 语义），粘贴 traceback 的合法长 query 会被旧谓词误标沉底，恰是修订 C 要修的 bug。§6 收尾句“按修订 A/B/D/J 实施”只点名阶段二修订，阶段一适用的 C/E/F/G/I 无一回写，实施者按 §3 原文动工就会做出修订 C 明确禁止的事（同 session-end 三层断裂教训：裁决层与执行层不同步）。修法廉价：§3 对应步骤加“以修订 X 为准”或直接改写。

- [NIT] **修订 J 的 PASS 定义未规定 embedding `unavailable` 时的语义**。修订 B 的双线 embedding 是 fail-open；无模型环境下 trigger 线全过 + 两线 `unavailable` 的降级运行，按 J 字面定义（“trigger lint 全过 且 shadow 捕获全部 query”）仍可发 PASS。降级运行不得发 PASS，应写死：任一线 `unavailable` → 至多 WARN/degraded，不发 PASS。

- [NIT] **修订 G 的测量谓词未钉死，与修订 C 展示口径可能分叉**。“队列卡片回声率 >80%”的重议门槛没说明用冻结谓词（含 >150 判真）还是 prefix 谓词测——两口径在长合法 query 上结果不同，未来重议会拿错证据。应写死：卡片口径用 C 的 prefix 谓词（与展示一致），池子口径可双报。

- [NIT] **修订 I 的 D3 dismiss 列未显式排除 dismiss_reason=shape-batch**。I 只写“不含指纹负名单”；E 的批量翻转走池状态并单列 dismiss_reason（skill_commands.py:2539 已渲染该字段，属现存机制非 schema 变更）。若 D3 per-source dismiss 计数把 shape-batch 翻转计入，机器回声会灌满 miss_recurrence 的 dismiss 列——第一轮 MAJOR-2 的污染以另一形式回归。I 应补一句“排除 shape-batch（或单列展示）”。

- [NIT] **修订 A“离线、廉价”只在 trigger 线成立，且未规定降级重跑的覆盖规则**。按 B，重跑含 embedding 双线（index 线需 `_compute_profile_text` + 模型，indexer.py:455）；无模型环境下 activate 自动重跑产出的是 `unavailable` 降级 verdict——须规定降级重跑不覆盖 promote 时的完整 verdict（标 degraded 并保留旧记录），否则 stale 重跑用更少信息覆盖更好记录。

**吸收质量核查**：claude-MAJOR-1→修订 D、claude-MAJOR-2→修订 E 均正确吸收且代码引用属实（M5 边界 skill_promote.py:1954-1959、sanitize_body_text 公开化 ：1814-1825、双机制分工 skill_commands.py:2629-2632、容量释放 list_pending 仅计 pending :818、dismiss_reason 字段现存 ：451）；修订 B 的 p0_shadow 偏离自述（replay_routing_baseline.py:157-164）、生产匹配器（triage_service.py:541）、recall 线 floor（triage_recall.py:51）双线引用全部属实；修订 F 字段清单与 ClusterCandidate 定义（:425-452）逐一相符；修订 K 与 ：2036-2052 现状相符。
