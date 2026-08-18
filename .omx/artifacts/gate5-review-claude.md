复审完成，所有关键声明已对照实际代码验证。以下是复审结论。

---

## 门禁 5 复审：M5

**逐项**

1. **守卫判据一致性**[executed]:triage_service.py:172 与 ：306 完全同式(`is_session_end_skill and not is_explicit_session_end_signal`),均对全量候选集校验 trigger,非 prefiltered 窗口。一致。
2. **前缀判据**[inspected]:`lstrip().startswith("<system-reminder")` 覆盖生产日志观察到的“整条 query 即注入块”形态；讨论标记的字面 query(标记在中后部)不误杀。残留缺口：注入块前有正文时不拦——但子串判据已被否(误杀面更大)，纵深防御归属其他层，可接受。
3. **短路位置**[executed]:orchestrator.py:196 在 detection(:209)/decompose(:236)之前;`vibe orchestrate`→unified.py:986 委托同一路径。**但 `.decompose(` 全仓 4 个调用点**:`vibe decompose`(main.py:1084)、`agent.decompose()`、`agent.build_plan()` 自动分解均无守卫。三处是显式诊断/程序化 API,非 harness 注入生产路径，nit 不 blocker。
4. **sys.modules None**[inspected]:CPython 文档化行为(None 条目使 import 必 raise ImportError),比旧 pop 手法强在“环境真装了包也能模拟未安装”。可靠。
5. **tracker 折衷**[executed]:test_analytics.py:335 双实例交错钉死“对比自身缓存而非交错写”，:401 钉死单实例+缓存生效。真钉死。
6. **预算单条 WARNING**:exhausted 不再重复 log,成本进 trip reason;90% 档只覆盖未耗尽区间。与声明一致。

**专项攻击**

7. **标定“不动 0.20”**[executed]:artifact 论证成立且诚实——结论是“数据不可区分”而非“0.20 更优”(n=31,相邻档差 ≤2 条属噪声；弱集 ≥0.20 零信号；top1 决策逐条一致故无回退 bigram 理由)。精度优先定位(0.889)匹配索引层补充角色。附带发现如实记 follow-up 未改。站得住。
8. **守卫拦截无 last-good**[inspected]:fresh 命中时 stale 恒为 None(lookup 语义)，拦截后走门控 LLM;门关闭则 triage 返回 None 落下游 keyword/scenario 层。行为正确：被守卫条目本身就是错误路由，用它兜底等于故意路由错；该场景仅出现在 trigger 变更后，低频。付一次 LLM 是合理代价。可接受。

**结论：PASS_WITH_NITS**

Nits(不阻塞，建议下轮)：
- `vibe decompose`/`agent.decompose`/`agent.build_plan` 三个无守卫 decompose 入口，显式 API 暴露面小，可复用 `_is_junk_query` 补齐；
- junk 的 LayerDetail reason 写 "contains",实际判据是前缀，文案改 "starts with" 更准；
- `index_match_threshold` 不在 RoutingConfig 已记录，确认其进 follow-up 队列即可。
