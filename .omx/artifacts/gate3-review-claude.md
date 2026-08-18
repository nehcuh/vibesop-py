验证完毕。以下为门禁 3 复审结论。

---

## 结论:PASS_WITH_NITS

**攻击点 1 裁决：recall_method 标记真实。** prefilter 入口先置 None,embedding 成功标 "embedding"、返回 None 标 "keyword"、无需预筛(len≤max_skills)保持 None。三条路径均如实反映当次行为，无虚标。

**攻击点 2 裁决：权威废除未落空。** scenario 全文件唯一产生点是 `_try_early_layers` keyword 分支(unified.py:664),降级覆盖完整;orchestrator.py:170 走 `_single_skill_route`,同样被覆盖。短查询 bypass 下 scenario 恒胜是设计内——keyword 短查询本就无 triage 仲裁，与改动前等价，且 `scenario_fallback: true` 可度量；LLM 模式(use_keyword=False)scenario 根本不跑，triage 天然权威。SEMANTIC_INDEX best-of 胜出走 elif 直接返回，与声明一致。

**逐项：**
- **embedding 回退完备**:`recall()` 全捕获→None→keyword;model 加载 sticky 失败、候选编码 strict zip 异常、锁竞争读失败均收敛到 None。fail-open 成立。
- **bigram**:regex `+` 保证空段不可能；单字保留 unigram;混合文本按连续 CJK 段切分正确;`_tokenize_query` 对 skill 侧(:273/:294)与 query 侧(:449)对称使用，Jaccard 口径一致。边界无洞。
- **垃圾过滤**：guard 在 telemetry 块之前早退(:881 < :896),miss counter/analytics 均不写；返回形状与 no-match sentinel 一致。验证成立。

**Nit(不阻门禁，建议下个 PR):**
1. **垃圾过滤绕过面大于声明**：声明只提 orchestrate(),实测 orchestrator.py:170 与 sessions/context.py:155 均直调 `_single_skill_route` 绕过 guard。建议 guard 下沉到 `_single_skill_route` 头部，两处自动覆盖。
2. **M3a 换模型声明不准确且实际更糟**：cache 无 model 字段，换同维模型不是“回退 keyword”而是静默复用旧空间向量算 cosine(语义错误)；维度不同才异常回退。model 名入 cache key 一行可修。
3. 锁竞争读失败时 `_write_cache` 用仅含当前候选的 dict 整体覆盖文件，丢其他 skill 条目(自愈，纯性能)。
4. triage 胜出时 scenario 层 counter 未记(`routing_path` 有、`_record_layer` 无)，layer 统计低估 scenario 参与率。

**Replay 数据诚实度**：口径不可比、scenario=0、embedding --no-llm 不可验，三条均如实声明未虚报。两项 headline 功能实际仅由单测背书，建议补一次带 LLM 的 smoke 再关 M3 周期。
