/bin/sh: 0.5: No such file or directory
三路核查完成(只读)。核对了我第一轮的三个 MAJOR,并针对重设计的三处焦点做了代码与数据实证核查。

## Verdict
PASS_WITH_NITS

## Findings

**我的 MAJOR 处置核查(全部解决)**
- [已解决·pi-MAJOR-1/3] 主项重设计成立:`local_files_only` 参数绕过 env-var import 冻结(方案不再用环境变量);缓存探测整个消掉;helper 落包代码,6 加载点全覆盖且覆盖 `vibesop-route.sh.j2:70-82` 的 `python -c AgentRuntime` 绕过路径(该模板确实 import 包,随包升级自动 rollout)。实证:6 加载点行号全中(strategies.py:599 / learner.py:695 / triage_recall.py:123 / promote_verifier.py:136 / _layers.py:403 / indexer.py:480);.venv 内 sentence-transformers 5.7.0 的 `SentenceTransformer.__init__` 确实接受 `local_files_only`;grok timeout=10(grok_build.py:189)、Kimi 15(kimi_cli.py:181)、Pi 15(vibesop-route.ts.j2:51)全属实;`enable_embedding` 默认 False(config/manager.py:144-146)未动。
- [已解决·pi-MAJOR-2] 读侧 sentinel 排除落地正确:`_route_hit_skill_id`(skill_health.py:50)确为 fire 列(count_skill_fires:124)与 outcomes 共享谓词(skill_outcomes.py:92)。实证:本仓 spans 恰好 6 行 has_match=true∧skill_id="fallback-llm"(08-17~18、mode=orchestrate),与 r2 §3.1 记载逐字吻合;fire 桶现含 'fallback-llm':6,排除后即消失,CHANGELOG 点名披露充分。

**重设计焦点核查(无新 MAJOR)**
- [NIT] helper fail-open 边界有一处未钉死:strategies.py:599 的 `_load_model` 只捕 `ImportError` 并重抛自定 message,其余异常(offline 的 OSError 等)原样上抛。helper 双败后必须**原样重抛在线尝试的异常类型**(不得包成新类型),否则该加载点 fail-open 行为与今天不一致;且 helper 应无状态(每调用独立),让 triage_recall/promote_verifier 的 sticky 语义仍由各加载点自持。r2 §1.2"行为与今天完全相同"未 pin 这两条(strategies.py:599-604, triage_recall.py:119-127)。
- [NIT] 项 4 改动范围未点名 `top_skills` 门:cli/main.py:925 的门注释明写"Gated on the SAME expression as metadata['has_match'] above"——has_match 写值改谓词后该门必须同步改,否则同一条 span 内 metadata 自相矛盾(当前 all-fallback orchestrated 下 alts 为空故 key 恰好省略,无数据影响,但不变式已破)。§3.2 范围钉的是 :903-914,门在 :925。
- [NIT] CLI single-mode miss 的 skill_id 未钉:single miss 时 primary.skill_id="fallback-llm"(result_mixin.py:314),§3.2"两生产者 miss 行 skill_id 一律 ''"括注只钉了 hook 侧,CLI miss 行写 "" 还是 "fallback-llm" 悬空(读侧 has_match=false 已排除,无火/outcomes 影响,纯写侧口径)。
- [NIT] 引用勘误三处:`optimization_service.py:184` 实际直调在 :180;server.py 无 `_spans_filename()` 函数(实际同型谓词是 skill_health.spans_file_for:41 / span_writer.py:62-63 内联选择);`constants.py:203` 不存在(文件仅 92 行,import 冻结机制本身属实,引用行号错)。
- [NIT] "feedback 文件均为空"措辞不准:两现场(本仓、cmspark)均**不存在** feedback.json/execution_feedback.json(而非空文件),"今天零行为变化"结论实质成立,仅措辞。
- [NIT] archive ≥3 闸同时改变薄样本 C/D 的 archive 路径(feedback_loop.py:178 闸作用于 C/D/F 三档,非仅 F),"证据门槛 1→3"的 CHANGELOG 叙述能覆盖,建议显式点一句。
- [NIT] 空 skill_id 分类学不完整:直接扫 spans 得 has_match=true∧skill_id="" 共 18 行,日期 07-30→08-23 含 'single' 模式,r2 §3.1 化石/活洞二分未覆盖 single-mode 空行(该行已被空串 guard 排除出 fire、outcomes 落 unjoined,无影响)。

**项 4 测试计划共存性(核查通过)**:property 不变 pin 与 span 写值翻转无冲突——result.has_match(property)与 span metadata 由不同表达式写出(cli/main.py:911 写 property、:906 写 skill_id),fix 只改 metadata 写值表达式,result 对象及注入门(agent_runtime.py:653)/instinct bridge 消费者不动;hook 侧 :560 的 result.skill_id=steps[0] 与 :668 的 span 写值分离,改 :668 即可,测试双断言独立成立。读侧排除对 fire/outcomes 既有数字的影响已披露且对账式扩展(Σ三列+unjoined+fallback)闭合。
