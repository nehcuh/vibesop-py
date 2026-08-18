核对完毕：diff 与实码一致，路由工厂 `router_factory.py:174` 的 `cache_dir=<root>/.vibe/cache` 确认持久缓存随 project_root 落 `.vibe/`,`route(record_telemetry=False)` 存在。复审结论如下。

## 门禁2 结论：PASS_WITH_NITS

### 逐文件

1. **triage_cache.py**:无阻塞 bug。TTL×候选集交叉(过期/变集→stale、损坏自愈、非阻塞锁竞争降级、按 ts 淘汰)语义正确且均有测试[executed:test_triage_cache.py 全绿逻辑]。非阻塞锁丢写只丢“对方进程刚写的条目”，锁内 RMW+rename 原子，只慢不坏。
2. **triage_service.py**:构造器 `isinstance(cache_dir,(str,Path))` 守卫使 MagicMock 旧测试安全;`triage_cache` 尾参注入向后兼容。
3. **manager.py**:timeout ge=1/le=120、ttl ge=1 校验合理;ttl 为 int 表达不了 <1h,fail-loud,可接受。
4. **unified.py**:M1a 改标 SEMANTIC_INDEX 正确，回归测试到位。
5. **build_eval_from_logs.py**:主 eval 是顶层 list,文本追加 safe_dump 的 list 合法；triage 侧 redact 后 join 与 analytics 落盘 redact 对齐，正确。NIT:main_text 末尾无换行会拼坏 YAML,加一行防护。
6. **replay_routing.py**:record_telemetry=False 已隔离 analytics/last_route;但 TriageService.store 不受该 flag 控制，LLM 开启的 replay 会写真实 triage_cache——行为无害，补文档一句。

### 最重要发现(非阻塞但应排最前修)

**熔断/预算 gate(triage_service.py:98-112)在持久缓存查找(139 行)之前**。后果：LLM 持续故障 3 次熔断 open 后，last-good 与 fresh 命中**全部不可达**——恰恰是 last-good 的目标场景只剩前 3 次失败的窗口；预算耗尽同理连零成本的 fresh 命中都跳过。建议把持久 lookup(至少 fresh 分支)提到熔断 gate 前。

### 专答两问

**last-good 不衰减：不阻塞**。触发链需 LLM 失败，且 store 时的 session-end 显式守卫+last-good 的 skill 存活校验已封两个高危面；当前下游仅 min_confidence 门槛、无自动执行，metadata.last_good 已暴露。列为 P1:一旦出现按 confidence 自动执行的下游，必须先加衰减或 clamp 到阈值下。

**candidates_hash 全量失效：当前可接受**。单项目装卸频率低，代价=每次变更后逐 query 重建；全量失效换正确性简单。更优解：条目存 id 集合，失效条件改“出现条目未知的新 id”(超集检查)——卸载无关 skill 不失效、仅新增才失效。等命中率数据证明装卸频繁再迁，现在不必。

### 开发者三自评裁定

①丢写：真实、有界、自愈，可接受。②线程堆积：真实但受传输超时(~30s 自然死亡)+熔断 cooldown 限速，CLI 主路径无害，长驻场景换 future/cancel 为后续项。③见上，P1 不阻塞。
