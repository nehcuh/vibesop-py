核查全部完成。以下为 r2 确认制复审结论。

---

## 核查摘要(证据基础)

我第一轮 3 MAJOR + 3 NIT 逐条对照 r2,并按任务指定的三个重点做了代码级核查：6 个加载点全部实读(strategies/learner/triage_recall/promote_verifier/_layers/indexer)、sentence-transformers 5.7.0 `local_files_only` kwarg 实测存在、`HF_HUB_OFFLINE` import 时冻结实测确认(huggingface_hub/constants.py 模块级常量)、hook 模板绕过 CLI 实测确认(templates/shared/vibesop-route.sh.j2:70-82 直呼 `AgentRuntime`)、项 4 三个写点(agent_runtime.py:668/:692、cli/main.py:904-930)与全部 span-metadata 读者(skill_health/gold_detection/tool_call_bridge/recall)逐一读侧扫描、两仓 spans 数据实测(cmspark 被会话沙箱拦截，未能复核，标注)、feedback_loop/evaluator/server.py 引用行号全部核实。

## Verdict

```
PASS_WITH_NITS
```

r1 三 MAJOR 全部正确解决：claude-MAJOR-1 → §1.2 重设计(废弃理由三条全部实证成立，Python 侧 helper 是唯一能覆盖绕 CLI 的 hook 模板的方案)；claude-MAJOR-2 → §4 双 conjunct(反例测试纳入，`routing_accuracy` 数据可得性在 evaluator.py:43 核实)；claude-MAJOR-3 → §3.2 rescope 纯遥测(:653/:727 消费者核实，miss 侧对称已钉)。重设计引入一处真实新问题(MAJOR,一句话可钉)，按本流程惯例不 BLOCK。

## Findings

- [MAJOR] 项 4 重设计引入 span 内部新矛盾：top_skills 未入“钉死不动”枚举。(a) hook 侧 agent_runtime.py:722-724 的 `top_skills` 由 `result.skill_id`(=steps[0],可为 "fallback-llm")+ `result.alternatives` 构建——按 §3.2 改 :668 的 metadata.skill_id=首真步后，活洞群 B 新行将出现 `skill_id=真技能 ∧ top_skills[0]="fallback-llm"` 的同 span 自相矛盾(r2 用 grok“只改 skill_id 会自相矛盾”钉住了 result 面的 skill_name/alternatives,但 top_skills 不是 result 契约面，它本身就是 span metadata)。(b) CLI 侧 cli/main.py:924 的 top_skills 门读 `result.has_match` property——只改 :914 写值后，all-fallback 新行将 `has_match=false ∧ top_skills 仍在`，直接违反 ：915-920 既有注释"Gated on the SAME expression as metadata['has_match'] above";且 §3.2 引用的改动范围 ":903-914" 恰好不含 ：924,实施者照稿做必漏。实测佐证：vibesop prod 7 行 sentinel fire 行均无 top_skills(早于 gate38),矛盾尚未在存量出现，但 gate38 写路径已生效、case-B 新行必现。修复：两写点 top_skills 与新谓词同源(hook 按首真步序列重建;CLI :924 门改用新谓词)或明文记录 divergence+理由；测试计划补一条 pin(has_match=false → top_skills 缺席)。
- [NIT] 主项 helper 异常契约未钉，§1.2“双败→走各加载点既有 fail-open(行为与今天完全相同)”有隐含前提：helper 须原样 re-raise 第二次(在线)异常且只捕 `Exception`。6 处捕获形态各异——learner.py:697 仅捕 `(ImportError, OSError, RuntimeError)`,matcher_pipeline.py:115 仅捕 `(OSError, ValueError, KeyError, MatcherError)`,strategies.py:599-604 是 6 处中唯一裸抛非 ImportError 的(其 fail-open 实际由上游窄元组提供，§1.2 的“各加载点既有 fail-open”对这处不精确)；helper 若包装异常类型或捕到 BaseException 吞 KeyboardInterrupt,“完全相同”即不成立。一句话钉死即可。
- [NIT] 项 4 fallback 计数机制未钉:`_route_hit_skill_id` 对 sentinel 返回 None 后，skill_outcomes.py:92-95 的 `_span_skill_map` 失去 sentinel 信息，这些行会落 unjoined 而非新 fallback 桶，对账式 Σ三列+unjoined+fallback=hit总数 无法成立；且 skill_outcomes.py:7-8 "reuses `_route_hit_skill_id` verbatim" 的 docstring 同步要改。需钉：保留 raw 提取、bucketing 层排 sentinel 并计数。
- [NIT] 项 4 读侧读者枚举不完整：recall.py:377-400 `_extract_skill_id` 是 span metadata skill_id 的第三个读者(r2 只钉 fire/outcomes),今天不排 sentinel,会把 "fallback-llm" 当技能展示进 recall 结果与 W3 replay prompt。影响边际(其 metadata 分支仅处理 dict 形态，磁盘 spans 为字符串形态)，但枚举应补并裁决是否同排。
- [NIT] 活洞群 B 数字差 1:vibesop prod spans.jsonl 按 fire 谓词(`skill_id="fallback-llm" ∧ has_match=true`)实数 7 行(6 行 08-17/18 + 1 行 2026-07-31 mode=orchestrate),r2 §3.1 记 6 行。应在 §7 承诺的测量档案口径中对齐(cmspark 侧本 session 沙箱拦截，pi 口径 85 行未能独立复核)。
- [NIT] 项 2 随双 conjunct 过时的文内记载:feedback_loop.py:122-127 规则 docstring("< 3 uses → deprecate"/"90+ days unused → archive")与 ：152-155 reason 字符串("only {n} use(s)")需同步改写，§4 只点了模块 docstring 第 4 行。
- [NIT] 引用微漂移:optimization_service 直调实为 routing/optimization_service.py:180(r2 记 ：184,同文件)；另有 `_listing.py:88`、`slash_commands.py:383` 两处 `evaluate_all_skills` 直调同样受益于 §2 形态，可顺带入档。

MAJOR 修复(钉 top_skills)后即可进入实施；其余 NIT 可随实施批处理。
