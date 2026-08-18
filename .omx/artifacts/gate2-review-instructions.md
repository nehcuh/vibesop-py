你是资深代码 reviewer,对 VibeSOP 路由系统改造做门禁 2 复审。用中文,只给判断和论据,不要客套。

## 背景

M2 内容:LLM triage 持久化缓存(`vibe route` 是 CLI,进程内缓存无效,故新增 .vibe/triage_cache.json)。设计:
- key = sha256(redact → collapse whitespace → lowercase 的 query),文件不含原文
- value = {skill_id, confidence, source, description, candidates_hash, ts}
- candidates_hash = 排序后候选 skill id 列表的 sha256[:16],skill 集变更则条目失效(保留作 last-good)
- TTL 默认 72h(config: triage_cache_ttl_hours);过期 miss 但保留作 last-good
- last-good:LLM 失败/超时时降级返回旧条目(metadata 标 last_good: true),且仅当 skill 仍在当前候选集
- 超时:daemon 线程硬超时(config: ai_triage_timeout_seconds 默认 15s)
- 容量 1000 条按 ts 淘汰;cross_process_lock blocking=False;损坏自愈;一切异常静默降级不影响路由

M1 收尾:build_eval_from_logs.py join 前对 triage 侧 query 过 redact_sensitive、merge 缺 query 键跳过+原子写;replay_routing.py 加 --project-root(未指定从 --log 路径推导);analytics.py 删 query_hash 死字段、负秒 clamp。

## 开发者自查声明的三个最弱环节(请重点攻击)

1. 非阻塞锁下并发写丢失=缓存建立变慢,无重试。
2. daemon 线程超时不真正中断 HTTP 请求,长驻进程会堆积后台线程。
3. last-good 置信度未衰减,与新鲜结果同权,下游自动执行可能有风险。

## 复审要求

1. 逐文件审:正确性 bug、并发/race、缓存一致性(过期/淘汰/候选变更的交叉场景)、向后兼容(旧 triage_service 调用方、MagicMock 单测)、配置字段校验。
2. 专门回答:last-good 置信度不打折是否应列为阻塞项?candidates_hash 全量失效策略在"上游频繁装卸 skill"场景是否代价过高,有无更优解?
3. 门禁结论:PASS / PASS_WITH_NITS / BLOCK;BLOCK 列必须修复项(编号、文件、原因)。
4. 600 字内。

## 复审包

