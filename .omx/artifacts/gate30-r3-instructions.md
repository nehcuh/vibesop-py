# Gate 30 Round-3 复审 — pi BLOCK-1 / claude MAJOR-1(exact-id 跨类）修复验证

## Round-2 结论

- pi:BLOCK — BLOCK-1:exact-id 路径绕过同类限制，stable miss 候选经 exact-id 整行替换 unstable gold 诊断行（已真实复现）;NIT-1（守卫 exact 兜底死代码论证）、NIT-2（注释把 cluster_id 误述为 task_ids sha1，实为复合键）、NIT-3（守卫测试未钉住 full-set vs best-match)、NIT-4(None-TTL elif 不可达）、NIT-5（被吸收行 queries/gold_rate 等丢失未记录）。
- claude:PASS_WITH_NITS — MAJOR-1 与 pi BLOCK-1 同洞；NIT-1 同 pi NIT-2;NIT-2(find_overlapping_pending 零生产调用方）;NIT-3(exact 命中多吸收无日志）。

## Round-3 修复（请验证闭环）

1. **BLOCK-1/MAJOR-1（修在守卫侧，不动 upsert)**：守卫的 exact-id 例外去掉 `not is_unstable` 条件——同 cluster_id ⟹ 同成员 ⟹ J=1.0，非-unstable 的 exact 行必然已在 blocking 全集里，该分支仅对 unstable exact 行可达；同簇身份下 unstable 行即该模式的当前证据，miss 候选必须跳过（upsert 的 exact-id wholesale replace 是 gate21 语义，gold 路径类翻转保留——有测试钉住）。此方案避免 pi 修复方向（upsert 加类条件）会引入的同 cluster_id 双行并存/get() 歧义问题。
2. **pi NIT-1**：死代码论证已吸收进守卫注释（说明该分支仅 unstable exact 行可达）。
3. **pi NIT-2 / claude NIT-1**：三处注释 + CHANGELOG 段首改为"(project_id, task_id) 复合键集合的 sha1";discovery.py:110 同款存量错误一并修正。
4. **pi NIT-4**：不可达的 `elif existing_idx: ttl=None` 分支已删（__post_init__ 恒填充，from_dict 重跑），注释改为 plain min()。
5. **claude NIT-2**:`find_overlapping_pending`（零生产调用方的投机 API）已删除，测试改用 `find_all_overlapping_pending`（新 fixture：两行分别与 probe J=5/9>0.5、互间 J=5/13<0.5 共存）。
6. **claude NIT-3**:exact 命中且吸收兄弟行（len(matched)>1）现在也记 INFO 日志。
7. **pi NIT-5**:merge 注释补记——跨项目合并时被吸收行的 queries/gold_task_ids/gold_rate/span_count 整体被 incoming 替换（增长型重复无损；跨项目合并丢被吸收项目的 query 样本，下次全窗重扫再生，accepted)。
8. **pi NIT-3（测试）**：新增 full-set 回归——池中 miss 行（J=0.8,best-match 会放行）+ gold 行（J=0.57)，守卫必须因 gold 行跳过；新增 exact-id unstable 阻挡回归（真实 sha1 预置，断言 source/is_unstable/span_count 不被替换）。

## 输出要求

PASS / PASS_WITH_NITS / BLOCK； findings 按 BLOCK/MAJOR/NIT 分级，给文件：行号与理由。
