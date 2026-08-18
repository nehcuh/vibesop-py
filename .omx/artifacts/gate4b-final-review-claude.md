# 门禁 4b 终审判定

**1. 顺序正确** [inspected+executed]
prefilter 执行条件恰为“无可用 fresh 命中且 budget/circuit 双放行”：budget 拒绝(triage_service.py:209)与 circuit 拒绝(:230)均在 prefilter 之前完成 last-good 尝试并 return,gate 关闭+缓存 miss 不付召回成本成立；fresh 命中在 gate 之前返回，零召回零 LLM。lookup/store 均哈希全量 candidates,lookup 因此前置于 prefilter,自洽。

**2. last-good 三路径全部可达**
budget 耗尽、circuit 打开、LLM 异常三条路径均接 `_last_good_route`,各有专测(test_triage_cache.py:233/275/299);存活校验对全量 candidates、×0.7 衰减且原值留 metadata、candidates_sent=0。74 项目标测试全过 [executed]。

**3. stale 留存链路闭环** [inspected]
lookup 只降级不删除，条目留盘直至同 key store 覆盖(含旧哈希口径自愈，triage_cache.py:52)或 MAX_ENTRIES LRU 驱逐；IO/锁异常 fail-open 返回 (None,None),不破坏主流程。

**4. to_dict 补 description 兼容** [inspected]
纯新增键；TriageCache.store 与 fresh 反序列化均 `.get()` 兜底，旧持久化条目缺键安全降级为空串，无破坏面。

**Nit(不阻塞)**
- 复审包 diff 落后于 HEAD:fresh-hit 路径现含 session-end 防御，被防命中会刻意降级为 miss 并继续走 prefilter/LLM(即存在“fresh 命中仍付召回”的有意例外)，复审包应同步该事实。
- `_last_good_route` 的 metadata `recall_method` 在 budget/circuit 路径读取实例残留值(仅 prefilter 内重置；CLI 单发为 None,长生命周期进程可能带上一次请求的值)，纯元数据口径瑕疵。

**结论:PASS_WITH_NITS**
