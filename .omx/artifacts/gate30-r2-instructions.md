# Gate 30 Round-2 复审 — 候选池 upsert 重叠合并（findings 收敛后）

## Round-1 结论与处置

- pi:BLOCK — M1（守卫只看最佳重叠行，merge 吸收全部重叠行 → gold 证据可被绕路销毁）+ N1–N5。
- claude:PASS_WITH_NITS — MAJOR-1（守卫把 unstable 诊断行算作"更强证据"，可大面积错杀 miss 候选）、MAJOR-2（池身份与 W5.1 复合键不一致，跨项目后果未分析）+ NIT-1–5。

## Round-2 修复内容（请验证是否真正闭环）

1. **pi M1**：守卫改用 `find_all_overlapping_pending`（全集），任一重叠 pending 非-miss 行即跳过；`find_overlapping_pending` 降级为展示用 best-match 包装（tie-break 修正为分数最高/平局最早）。
2. **claude MAJOR-1**：守卫排除 unstable 行（不算"更强证据"）;merge 匹配集加同类限制（`r.is_unstable == candidate.is_unstable`),stable miss 候选不再吸收 unstable 诊断行。代价：跨类重复可共存（rare gate21 flip case,30 天 TTL 兜底），已注释。
3. **pi N1**:exact 命中与重叠匹配合并为统一 matched set——簇尺寸稳定的存量重复对也能自愈。
4. **pi N2 / claude NIT-3**：比较改严格 `>`——两个 3 任务簇共享 2 任务（J=0.5）不合并。
5. **claude MAJOR-2**：显式决策（a)——池层模式身份 = project-agnostic task_id 词汇集，W5.1 复合键只管 span 归因；merge 时 project_distribution 跨行求和并集，保住 [XP] 跨项目证据。注释已记录。
6. **claude NIT-1**:cap 守恒注释改写（总量守恒，per-class 在 exact-id flip-merge 时可瞬时 +1,gate21 同族）。
7. **claude NIT-2**：被守卫跳过的 miss 候选计入新 ScanSummary 字段 `miss_guard_skipped_count`,CLI scan 输出可见。
8. **pi N4**:legacy None-TTL——全部匹配行都无 TTL 时结果保持 None（与旧 refresh 一致）；有则取最早。
9. **pi N5 / claude NIT-4**：新增测试——strict 0.5 边界、跨类不吸收、分布并集、exact 命中吸收兄弟行（直写文件模拟 legacy 池）、守卫集成（漂移 gold 阻挡 + unstable 不阻挡）。
10. **夹带修复**（本 diff 暴露的存量测试 fixture 问题）:CLI 两测试文件的 `_candidate` helper 共享常量 task_ids，在 merge 语义下会互吸——改为按 cluster_id 派生；`test_scan_candidates.py` 的 ScanSummary 键集断言补新字段。

## 复审重点

- 统一 matched set 的正确性：exact-id 行 + 同类重叠行的并集、最早值保留、分布并集求和。
- 守卫逻辑：全集 + 非-miss + 非-unstable + exact-id 兜底（成员全换血时 task 集零重叠仍挡）。
- 同类限制是否引入新洞（如 unstable incoming 与 stable 存量重复对不再互愈——是否有实际危害）。
- 新测试是否真的覆盖修复点（尤其 TestGuardOverlapExtension 两例）。

## 输出要求

PASS / PASS_WITH_NITS / BLOCK 三档结论；findings 按 BLOCK/MAJOR/NIT 分级，每条给文件：行号与理由。
