文件写入被权限拦截（同 round-2），评审结论直接输出如下，可粘贴到 `.omx/artifacts/gate30-r3-claude.md`。

---

# Gate 30 Round-3 复审结论（claude）

**结论：PASS_WITH_NITS** — round-2 的 BLOCK-1/MAJOR-1（exact-id 跨类销毁 unstable 诊断行）真实闭环，8 项修复声明全部落地；剩 2 个 NIT 均为文档/注释漂移，不阻塞合并。

验证方式：通读 `skill_promote.py` 守卫/upsert 实现行；核对 `clustering.py:308,317-318` 的 cluster_id 派生（sorted 复合键 + `\x1f` join + `[:16]`）与测试预计算一致；核对 `__post_init__`/`from_dict` 的 TTL 恒填充不变量。[executed] touched 5 文件 188 tests 全绿；tests/core + tests/cli 全量 3683 passed / 3 skipped / 0 failed（60.6s）；ruff 全清。变异验证（改回 round-2 的洞再跑测试）因 src 写权限未授权未执行，回归敏感性以静态论证替代（见下）。

⚠️ **流程注记**：`gate30-r3-pi.md` 内**没有 pi 评审结论**——只有一次 `vibe route` 调用的 shell 报错回显（标题里的中文括号 `）` 破坏了引号）。本轮实际只有 claude 单评审，双评审闭环未成立；若需 pi 侧确认请转义后重跑。

## Round-2 findings 闭环确认

- **pi BLOCK-1 / claude MAJOR-1（闭环）**：守卫侧修复 skill_promote.py:1590-1597。三根支柱均核实：
  1. miss 候选恒 `is_unstable=False`（skill_promote.py:1545）——同类 overlap 吸收 unstable 行的路径结构性不存在，exact-id 是唯一残留的 miss→unstable 销毁路径；
  2. 去重条件 `all(r.cluster_id != exact.cluster_id for r in blocking)` 正确——stable exact 行经 J=1.0 已在 blocking 全集（同 cluster_id ⟹ 同复合键集 ⟹ 同 task_ids），仅 unstable exact 行可达 append 分支，与注释 1579-1589 论证一致；
  3. 回归测试 `test_exact_id_unstable_row_blocks_miss_candidate`（tests/core/observability/test_miss_recurrence_admission.py:853）用真实 sha1 预置（`sorted("test|kN")` + `\x1f` join + `[:16]`，与 clustering.py 派生逐项一致），断言 source/is_unstable/span_count 不被替换——round-2 代码下三条全挂，钉住力充分。[executed] 通过。
  - gold 路径类翻转保留 + 测试钉住：`test_exact_id_cross_class_flip_preserved_for_gold_path`（tests/core/observability/test_skill_promote_store.py:841）。pi 方案（upsert 加类条件）确实会引入同 id 双行/get() 歧义——守卫侧是更优解。
- **pi NIT-1（闭环）**：死代码可达性论证进守卫注释（1579-1589）。
- **pi NIT-2 / claude NIT-1（闭环）**：skill_promote.py:113-114、367-374、593-594；discovery.py:110-111；CHANGELOG:14 全部改为复合键表述。
- **pi NIT-4（闭环）**：plain `min()`（656-662）；`__post_init__`:447-448 恒填充 + `from_dict` 走构造器重跑 post-init，None-TTL 不可达论证成立。
- **claude NIT-2（闭环）**：`find_overlapping_pending` 在 src 零残留（grep 证实）；测试改用 `find_all_overlapping_pending`，新 fixture 数学正确（probe J=5/9≈0.56 两行各自命中、互间 J=5/13≈0.38 共存、unrelated 排除）。
- **claude NIT-3（闭环）**：`if existing_idx is None or len(matched) > 1`（644）——exact 命中吸收兄弟行现在有日志。
- **pi NIT-5（闭环）**：merge 注释 614-620 补记 wholesale 替换字段清单 + 跨项目 query 样本丢失的 accepted 理由。
- **pi NIT-3（闭环）**：`test_full_set_guard_blocks_when_best_match_is_miss_row`（test_miss_recurrence_admission.py:801）fixture 数学核实：incoming {k1..k4}，miss 行 J=4/5=0.8（best-match 会赢）、gold 行 J=4/7≈0.57、两行互间 J=4/8=0.5 恰好不合并（严格 >）。若守卫退化为 best-match，upsert 会同 class 吸收 gold 行，断言必挂——真回归测试。[executed] 通过。

## Findings

### NIT-1 — CHANGELOG 宣传已删除的 API + 测试计数过期

**位置**：CHANGELOG.md:34-36。

**理由**：round-3 删除了 `find_overlapping_pending()`（claude NIT-2），但 round-1 写下的条目“新增 `find_all_overlapping_pending()` / `find_overlapping_pending()`：全集（守卫用）与最佳匹配（展示用）两个公开重叠查询”未同步——正是本 gate 系列反复抓的 brief-vs-code drift 类。同条目测试计数也过期：写“12 例 + 2 例”，实际 TestOverlapMerge 13 例（含新增 flip-preservation）、TestGuardOverlapExtension 4 例（round-3 新增 2 例未计入）。纯文档，建议随手改。

### NIT-2 — 三处注释写 "Jaccard ≥"，语义是严格 >（边界承重）

**位置**：tests/core/observability/test_skill_promote_store.py:11、:51；tests/cli/test_skill_discover_cli.py:48。

**理由**：代码口径是 `_task_set_jaccard(...) > MERGE_JACCARD_THRESHOLD`（skill_promote.py:635），且 0.5 边界是刻意排除的承重决策——`test_exact_boundary_half_does_not_merge` 专门钉住“恰好 0.5 不合并”（pi N2）。fixture 注释说 ≥ 与被钉行为直接矛盾，未来按注释理解会误设 fixture。纯注释。

### 附注（不计 finding）

守卫注释"cluster_id equality ⟹ identical membership"（skill_promote.py:1580）是 64 位截断哈希下的工程近似（clustering.py:318 `[:16]`）；碰撞后果偏保守（守卫多挡一次 miss 入池），upsert exact-arm 的碰撞暴露是 gate30 之前的存量，生日界在 ~50 行池上 ≈1e-15 量级，不可操作，仅记录。

## 复审重点逐项

1. **BLOCK-1 修复方向**：✅ 守卫侧不动 upsert，保住 gate21 wholesale-refresh 语义与 get() 单义性；miss 恒 stable（1545）使同类限制论证无死角。
2. **守卫完备性重扫**：unstable 行的全部变更路径枚举——miss exact-id（守卫挡，新测试钉）/ miss overlap（跨类不吸收，1545 保证）/ gold exact-id（gate21 翻转，显式 accepted + 测试钉）/ gold 同类 overlap（同类刷新，语义不变）/ cap 驱逐 / TTL（均存量语义）。无新洞。
3. **测试真实性**：两个新回归的失败模式静态论证成立（各自在 round-2 / best-match 语义下必挂）；[executed] 全量 3683 绿。
4. **文档同步**：⚠️ NIT-1/NIT-2——代码侧闭环，文档侧两处漂移。

---

两点提醒：pi 的 r3 实际没跑成（引号问题），如需双评审闭环需重跑；两个 NIT 若要清掉，改 CHANGELOG.md:34-39 和三处 `≥`→`>` 注释即可，都是一分钟的事。
