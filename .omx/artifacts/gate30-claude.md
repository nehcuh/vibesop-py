四项对抗场景全部执行确认。评审完成，结论如下。

---

# Gate 30 复审结论：**PASS_WITH_NITS**

核心修复（漂移去重）正确且执行验证通过：559 个 observability 测试全绿、ruff 干净、8 个 TestOverlapMerge 覆盖 multi-absorb / terminal 不粘 / cap 绕过 / tie-break。但扩展面引入了两个需要处理的 MAJOR（一个是守卫语义错误，一个是与 W5.1 复合身份的未分析互斥），沿用 Gate24 先例（PASS_WITH_NITS 携带须在依赖前修复的 MAJOR）。

## MAJOR

**MAJOR-1 守卫把 unstable 诊断行当“更强证据”，可大面积错杀 miss 候选** — `src/vibesop/core/observability/skill_promote.py:1538-1542`（守卫条件）+ `:942-970`（`find_overlapping_pending` 无 class 过滤）

守卫跳过条件只看 `status == "pending" and source != "miss_recurrence"`，不看 `is_unstable`。`[executed]`：unstable 行（gold_rate=0.0，task_ids {m1,m2,m3,o1}）对 miss 候选 {m1,m2,m3}（J=0.75）→ guard skip = True。语义自相矛盾：守卫的理由是 "stronger evidence wins"，但 unstable 行恰是**最弱**证据（gold_rate < 0.30 的诊断桶），而 miss 候选过了 recurrence 门。触发面是常态而非边角：gold path（全 span、0.80 阈值）产生的 mixed 簇中 miss 任务占多数时 gold_rate 必然 < 0.30 → 入 unstable 桶且包含 miss 簇大半 → 此后每轮 scan 的 miss 候选都被挡，直到 unstable 行被人工处理或 30 天 TTL 过期——部分回潮了 F-a 刚修掉的“miss 候选不可见”问题。exact-id 版本 pre-existing（要求 key 集合完全相同，实际不可达）；gate30 把触发面扩大到 ≥0.5 重叠才是新的。修法：条件加 `and not existing.is_unstable`；注意权衡——放行后 upsert 的 merge 会吸收 unstable 行（mixed 簇中非 miss 任务的诊断证据随整行替换丢失），fix 时需一并决定。

**MAJOR-2 池身份从 W5.1 复合 key 退化为非复合 task_id 集合，跨项目后果未分析** — `skill_promote.py:351-357, 616-621` + `clustering.py:315-330`

`cluster_id` = sha1(sorted **(project_id, task_id)** composite keys)（W5.1 为防跨项目同 task_id 碰撞而专门复合化）；而 candidate 存的 `task_ids` 是非复合、可含重复的 lossy 投影（clustering.py:60-67 docstring 自己声明），Jaccard 又经 `set()` 去重。`[executed]` 两项：(a) 两项目同 query 模式（复合 id 不同、W5.1 设计上应共存）→ J=1.0 → proj1 行被 proj2 行吸收消失；(b) [XP] 跨项目行（重复 tid）被单项目碎片 J=1.0 吸收，`project_distribution` 异质性信号销毁——而窗口变窄（`--days`、age-out）是常态时这不是“下次全窗重扫再生”能自愈的保守失败。另有最早 created_at/first_seen_at 跨项目嫁接（provenance 混淆）。这正是 memory 里记录过的教训同型（v2 互斥设计、特性互斥检查）。需二选一：(a) 显式接受并在 gate30 注释块 + W5.1/W5.2 文档记录“池层模式身份 = task_id 集合”及 [XP] 吸收后果；(b) Jaccard 改复合 key（`ClusterCandidate` 需增 `task_keys` 字段，legacy 行回退）。

## NIT

- **NIT-1 cap 绕过的守恒性表述不准** — `skill_promote.py:614-615`。"net-reduces the row count" 对总量成立、对 per-class 不成立：吸收行可与 incoming 不同 class（gate21 class-flip 经 merge 路径重现），incoming class 每次 flip-merge +1 超 cap，靠后续同类 insert + 下轮 prune 自愈——与 gate21 接受的 transient 语义同族、行为可接受，但注释的守恒理由不构成 per-class 证明，建议改写。
- **NIT-2 被守卫 skip 的 miss 候选脱离账目** — `skill_promote.py:1543-1550`。`continue` 绕过 `miss_admitted/miss_rejected` 两计数器（exact 碰撞情形 pre-existing，gate30 扩大到重叠碰撞），M2 exit criterion 的可见性受损。
- **NIT-3 小簇边界算术未标定** — `MERGE_JACCARD_THRESHOLD`（:128）。`[executed]`：{t1} vs {t1,t2} → J=0.5 整 → 合并；{a,b,c} vs {a,b,x} → 0.5 → 合并。标定数据（0.88–0.99 vs ≤0.41）来自 61–63 任务大簇；`min_cluster_size=3` 作用于 span_count 而非 distinct task_ids（单 task_id 跨天重复即合法入池），小簇共享 1–2 个泛化 task 即达阈值。失败方向不必然自愈（两模式持续同游 ≥0.5 时永远只剩一行，evidence 替换不求和）。建议注释补记或设最小集合尺寸下限。
- **NIT-4 测试缺口** — `tests/core/observability/test_skill_promote_store.py` / `test_miss_recurrence_admission.py:474`。守卫的**重叠扩展路径零直接测试**（旧 gate17b 测试预置同 cluster_id + 同 task_ids，exact/overlap 两路径都能过，不区分）；缺 MAJOR-1 的 negative 测试（unstable 行不该挡）；merge 的 `first_seen_at` 保留（:637-641）无断言；跨 class 吸收无测试。
- **NIT-5 守卫 TOCTOU** — `find_overlapping_pending` 在 store 锁外读，guard 判定与 upsert 间并发 scan 可插入行；单写者 cron 假设下理论性，且 upsert 锁内重算 overlap，最坏是漏挡一次而非数据损坏。

## 复审重点逐项

| 重点 | 结论 |
|---|---|
| multi-absorb / 最早值保留 / terminal 不粘 | ✓ 正确（tests + 执行验证） |
| cap 绕过守恒性 | 总量守恒 ✓；per-class 不守恒（NIT-1） |
| 与 gate21 class-flip 语义 | 不冲突——整行替换语义与 gate21 接受的 refresh 一致，只是 flip 面扩大 |
| miss/gold 守卫新跳过路径 | 引入（MAJOR-1，`[executed]`） |
| `landed = store.get(...)` | ✓ 合并后行保留 incoming cluster_id，gold 路径 ：1476 与 miss 路径 ：1562 两处均正确 |
| 测试覆盖 | store 层充分；scan 层守卫扩展缺失（NIT-4） |

**条件**：MAJOR-1 在下一轮依赖 miss 候选可见性的 scan 前修（一行条件 + negative 测试）；MAJOR-2 需显式决策（接受并记录，或复合 key 化）。另：`_make_candidate` 默认 task_ids 改为从 cluster_id 派生是必要且正确的（旧共享默认值在 gate30 下会让全文件行互吸）。

需要的话我可以把这份评审写入 `.omx/artifacts/gate30-claude.md`（刚才写 `.omx/` 被权限拒绝，需你放行）。
