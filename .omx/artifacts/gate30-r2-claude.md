文件写入被权限拦截（本会话只读模式），评审结论直接输出如下，可自行粘贴到 `.omx/artifacts/gate30-r2-claude.md`。

---

# Gate 30 Round-2 复审结论（claude）

**结论：PASS_WITH_NITS** — 1 个 MAJOR 需在合并前处理（修复或显式接受+补测试），另 3 个 NIT。

验证方式：通读 diff 涉及的 `skill_promote.py` / `skill_commands.py` 实现行；核对 `clustering.py` 的 cluster_id 派生；执行 touched 测试（185 passed）+ 全 observability+cli 套件（1339 passed）+ ruff（clean）；MAJOR-1 附可执行复现。

## Round-1 findings 闭环确认

- **pi M1（闭环）**：守卫全集化（skill_promote.py:1582-1586）+ exact-id 兜底（1589-1597）覆盖成员全换血。`test_drifted_gold_row_still_blocks_miss_candidate` 是真回归测试——round-1 守卫下 drifted gold 行会被吸收、`store.get` 返回 None，必挂。
- **claude MAJOR-1（主路径闭环，例外见新 MAJOR-1）**：守卫排除 unstable（1585/1594）+ merge 同类限制（621）。`test_unstable_row_does_not_block_miss_candidate` 在 round-1 语义下因 unstable 行被吸收（`diag is None`）必挂。
- **claude MAJOR-2（闭环）**：分布求和并集（655-661）+ 决策注释。机制核对：cluster_id 实际按复合对派生（clustering.py:317-318），同词汇跨项目=不同 id → 经 overlap 路径 J=1.0 合并，[XP] 证据存活，与决策一致。
- **pi N1（闭环）**：统一 matched set（614-623）；直写文件测试模拟 legacy 池。
- **pi N2 / claude NIT-3（闭环）**：严格 `>`（622）+ 0.5 边界测试。
- **pi N4（闭环）**：全 None-TTL 且 exact 命中保持 None（644-648）；纯 overlap 吸收 legacy 行保留 incoming 新 TTL（不传播永不过期），合理。
- **claude NIT-1/2、pi N5 / claude NIT-4、fixture 修复（全闭环）**：cap 注释、`miss_guard_skipped_count`（含 CLI + 键集断言）、12+2 测试、fixture 派生。`test_merge_bypasses_class_cap` 真实检验了 merge 绕过 admit-only-if-better（gold_rate=0.0 走插入路径必被拒）。
- **claude NIT-5（闭环）**：TOCTOU 已声明接受，单写者 cron 下成立。

## Findings

### MAJOR-1 — exact-id 跨类吸收：unstable gold 诊断行可被 miss 候选整行替换

**位置**：skill_promote.py:614-616（`matched_idx.add(existing_idx)` 无条件，无 class/source 检查）× 1582-1597（守卫对 unstable 不设防）。

**理由**：守卫注释（1576-1581）声称“same-class merge restriction already guarantees the stable miss candidate cannot absorb them”——该保证只在 overlap 路径成立。exact-id 行无条件进 matched set：存量 **unstable gold** pending 行与 miss 候选 **cluster_id 相同**（同 task 集）时，守卫不挡（unstable 非更强证据——决策本身正确），upsert 随即整行替换诊断行（span_count/gold_rate/queries/step_freq 丢失，仅 created_at/ttl/first_seen/分布保留）。

**触发路径（现实）**：scan N 将 {k1,k2,k3} 以 gold_rate 0.15 归入 unstable 桶；scan N+1 该模式全 miss 化且跨天复发 → miss 路径以相同复合键 admit → 同 id → 吸收。line 1441 的子集检查只防**同扫描内**重复入池，防不了跨扫描存量行。unstable（低 gold 率）簇恰是持续失败、最易复发 miss 的模式——人群重合。

**[executed] 复现**（unstable gold 行 span_count=50/gold_rate=0.15 种子 + 3 跨天 miss span）：
```
RESULT: source=miss_recurrence is_unstable=False gold_rate=0.0 span_count=3
SUMMARY: miss_admitted=1 miss_guard_skipped=0
```

**是 round-2 回归**：round-1 守卫（exact get + `source != "miss_recurrence"`）会挡下此 miss 候选；round-2 移除阻挡（方向正确）但未把同类限制延伸到 exact-id 匹配。反向（miss 行被 unstable gold incoming 替换）为 gate21 前存量语义，不计入。危害有界（每次 1 行、桶 ≤20、模式反而在 review 可见性上升、created_at/分布连续），故不 BLOCK。

**处置（二选一）**：
1. exact-id 无条件匹配收紧为“同 source 才无条件”（gate21 flip 本就是 gold↔gold rescan 语义）；注意同 id 共存会造成 `get()` 歧义，需一并设计。
2. 显式接受为 gate21 同族：改写 1576-1581 注释（删除错误安全声明）+ 补 exact-id 碰撞回归测试钉住预期行为。

### NIT-1 — cluster_id 派生注释三处写错（+CHANGELOG）

**位置**：skill_promote.py:113、366-367、588-589；CHANGELOG gate30 段首。实际派生是 sorted **(project_id, task_id) 复合对** sha1（clustering.py:317-318，W5.1），非 "sha1 of sorted member task_ids"。drift 论证不受影响，但 MAJOR-2 身份讨论依赖此细节——正因 id 复合键派生，跨项目同词汇才产生不同 id、靠 overlap 合并；按现注释会推出“跨项目共享 id”的错误结论。`discovery.py:110` 有同款存量错误，本轮属新增传播。行为无恙（`_task_set_jaccard` 的 set 去重正确处理复合展开的重复 task_id），纯文档问题。

### NIT-2 — `find_overlapping_pending` 零生产调用方

**位置**：skill_promote.py:988-1006。守卫切到全集后，best-match 包装只剩测试调用。作为“展示用 companion”保留但无接线，属投机公共 API——接线到 CLI 展示路径或删除。

### NIT-3 — exact 命中路径的多吸收无日志

**位置**：skill_promote.py:627-637。`if existing_idx is None` 才记 INFO——exact 命中同时吸收漂移兄弟行（pi N1 自愈主场景）日志不可见，cron 排障只能看行数变化。

## 复审重点逐项

1. **matched set 正确性**：✅ 并集/最早值/分布并集/cap 交互（净变化 1−k ≤ 0）全部核实。
2. **守卫逻辑**：✅ 全集+非-miss+非-unstable+exact 兜底齐备，阈值同常数同口径——**除 MAJOR-1 的 exact-id 跨类例外**。
3. **同类限制新洞**：overlap 路径跨类共存=review 噪音+30 天 TTL 兜底，可接受已注释；真正的洞是 MAJOR-1 的 exact-id 反向。
4. **测试覆盖**：两例均为真回归测试（round-1 下各自必挂，失败模式不同），但都只覆盖 **drifted-id** 碰撞，未覆盖 exact-id 碰撞——正是 MAJOR-1 漏网处；处置时无论修复或接受都应补 exact-id 用例。
