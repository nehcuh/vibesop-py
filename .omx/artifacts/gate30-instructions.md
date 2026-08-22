# Gate 30 复审 — 候选池 upsert 重叠合并

## 背景（复审必需的上下文）

VibeSOP 的技能发现管线：路由/执行 trace → spans.jsonl → `cluster_queries` 聚类 → `scan_candidates` → `ClusterCandidateStore`(JSONL 池）→ 人工 promote/dismiss。

**发现的 bug**:`cluster_id` = 排序后成员 task_id 集合的 sha1(clustering.py:317)。当重扫时簇吸收了新 task(miss 持续累积是常态）,sha1 变化 → upsert 的 exact-match 判为新候选 → 池里追加重复行。dogfood 项目 cmspark 的真实池：27 条 pending 中 8 对重复（如 61 任务行与 63 任务行是同一"合并 main"模式）。

**改动设计**(`src/vibesop/core/observability/skill_promote.py`):

1. `_do_locked_upsert`:exact id 未命中后，找所有 task_id 集合与 incoming 的 Jaccard ≥ 0.5(`MERGE_JACCARD_THRESHOLD`）的 **pending** 行，全部 absorb:incoming 行替换它们，保留最早 created_at / ttl_expires_at / first_seen_at。terminal(promoted/dismissed）行永不吸收。吸收净减行数，故与 refresh 路径一样绕过插入 cap 检查。
2. 新增公开方法 `find_overlapping_pending(task_ids)`:Jaccard 最高的 pending 行（≥ 阈值）。
3. gate17b miss/gold 冲突守卫（scan_candidates 内）从 exact `get` 扩展为重叠感知：防止 miss 候选经合并路径覆盖漂移后的 gold pending 行。
4. 阈值标定依据（真实池数据）：真重复对 Jaccard 0.88–0.99；语义不同但共享泛化 task("提交"等）的模式对 ≤ 0.41。0.5 双侧留距。
5. 已知边界（已在注释记录）：重扫把一簇劈成两碎片时，贪心合并可能让后到的碎片吸收前者——保守方向失败（池暂时丢一个碎片，下次全窗重扫再生），与 discovery.cluster_fingerprint 的"漏粘"记录同类。

**复审重点**:
- 合并语义正确性：multi-absorb、最早值保留、terminal 不粘、cap 绕过的守恒性。
- Jaccard 0.5 阈值的风险：小簇（2–3 任务）粒度粗；劈簇侵蚀；是否与 gate21 已接受的 class-flip 语义冲突。
- miss/gold 守卫扩展是否引入新的跳过路径（如把本该入池的 miss 候选错杀）。
- `landed = store.get(candidate.cluster_id)`(scan 内）在合并后是否仍正确。
- 测试覆盖是否充分（tests/core/observability/test_skill_promote_store.py::TestOverlapMerge)。

## 输出要求

PASS / PASS_WITH_NITS / BLOCK 三档结论；findings 按 BLOCK/MAJOR/NIT 分级，每条给文件：行号与理由。
