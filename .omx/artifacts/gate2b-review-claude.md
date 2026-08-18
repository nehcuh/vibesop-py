## 复审结论(门禁 2 第二轮)

**B1:已闭合。** 内存命中经 `_skill_in_candidates` 对全量候选做存活校验(triage_service.py:123),已卸载即视为 miss;持久 fresh 命中由 `candidates_hash` 等值保证 skill 必在当前 triage_candidates 内(64bit 截断哈希，碰撞可忽略)；last-good 再做显式存活校验。三条路径均无“已删复活”通道，且测试覆盖齐全(removed-skill miss / hash mismatch stale / last-good rejected)。

**排序：已闭合。** fresh 命中上移 gate 前，熔断 open、预算耗尽下仍可达(两条均有测试)。副作用核查:prefilter 纯 CPU 无副作用;`trip("budget_exhausted")` 触发频次降低但语义反而更准——gate 只守 LLM 调用路径，缓存命中本无需 trip,gate 计数无破坏；stale_entry 在 gate 拦截路径上算而不用，仅多一次文件读，无害。

**裁决 1(全量 vs prefilter 后集合)：可接受。** 两者皆为存活校验而非集合等价校验；last-good 用更窄集合反而更严——不会兜底出当前管线根本不会送 LLM 的 skill。逻辑自洽。

**裁决 2(内存命中前置 gate):可接受。** 零成本、零失败面，不污染熔断统计。

**残留 nit(不阻塞)：**
1. last-good 在熔断 open / 预算耗尽路径仍不可达(stale_entry 已在手却弃用)——第一轮 claude 观察只修了 fresh 一半；属声明的保守选择，可接受，建议后续在此二路径也兜底。
2. `_call_llm` 超时后 daemon 线程残留至 provider 传输超时才消亡，长驻进程反复超时会短暂堆积线程，量级可接受。
3. 缓存命中路径 metadata 的 `candidates_sent` 命名有歧义(实际未发送)，仅影响观测。

merge_confirmed 尾换行防护、replay docstring 披露均无问题。

**结论：PASS_WITH_NITS**
