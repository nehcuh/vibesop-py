# gate18 复审指令 — M12 M4+M5

你是资深代码评审员。仓库：/Users/huchen/Projects/vibesop-py（Python，包在 src/vibesop）。随附的 diff 是本次待审改动（M12 里程碑 M4+M5 + 一个时间炸弹测试修复）。设计契约见 `.omx/artifacts/m12-product-design.md`（重点：72-78 行 M5 契约、104-120 用户旅程、122-129 隐私边界、172-175 里程碑定义）。

## 本次改动范围

**M4 看板发现页（只读）**
- 新增 `src/vibesop/dashboard/_discoveries.py`（读模型装配，复用 `discovery.build_queue(observe=False)` 与 CLI 同口径，GET 零写入——store 构造会 mkdir，全部用存在性检查前置挡住）
- `server.py` 加 `GET /api/discoveries`；`templates/index.html` 加只读 Discoveries 页签
- 有意不做：聚合扫描统计（ScanSummary 无持久化落盘，GET 里跑扫描越界，诚实省略）
- 测试：tests/dashboard/test_server_endpoints.py +7

**M5 promote --activate + 编辑守卫 + 全局隐私护栏**
- `skill_promote.py`：`ClusterCandidate.draft_sha256`（向后兼容）；`store.promote(..., draft_sha256=)` 仅新写草稿时记录（re-promote 不 re-baseline）；`_render_skill_md` 全局 scope 剔除示例 queries/project 标识；`ScanSummary.miss_share_by_layer`（读 span metadata layer，无则 "unknown"，空 miss 池为空 dict）
- `skill_commands.py`：从 `add` 提取 `_audit_skill_or_exit`/`_install_skill_or_exit` 共享函数（零逻辑复制）；`promote --activate/--force` 守卫链：文件缺失→legacy None hash→hash 未变拒绝→全局需 [XP] 证据或 --force→`typer.confirm(default=False)`（--force 也不跳过确认）；scan-candidates 渲染 miss share
- 测试：store +6 / render +5 / admission +3 / CLI TestPromoteActivate +10

**时间炸弹修复（HEAD 预存失败，与 M4/M5 无关，stash 验证过）**
- test_route_replay_cli.py / test_recall.py 三处硬编码 `2026-07-2x` 日期撞上 replay.py `_DEFAULT_DAYS_WINDOW=30` 滚动窗口（今天 2026-08-21,07-21 已 31 天前被窗口感除）。改为 `datetime.now(UTC) - timedelta(...)` 相对时间。

## 评审重点

1. **正确性**:--activate 守卫链顺序与边界（legacy None hash、文件缺失、re-promote 不 re-baseline）；全局隐私剔除是否真堵死示例 query 泄漏；_discoveries 读路径是否真零写入（包括任何隐蔽的 mkdir/写副作用）；miss_share_by_layer 统计口径。
2. **设计一致性**：看板只读（无写操作、无 mutation helper 暴露）；变更单入口在 CLI；隐私边界（全局草稿无 query/项目标识，确认默认 N)。
3. **安全性**：注入面（example queries 进入 API 响应是否脱敏）、typer.confirm 能否被 --force 绕过（不应能）、路径处理。
4. **测试质量**：新测试是否锁住关键行为而非实现细节；时间炸弹修复是否根治（窗口内余量是否足够）。
5. **一致性**：与仓库既有的防御式存储风格（坏行跳过、双锁等）是否对齐。

## 输出格式（严格遵守）

- 先给总评 verdict:PASS / PASS_WITH_NITS / FAIL（有任一 BLOCK 即 FAIL)
- findings 按严重度：BLOCK / NIT，每条含 文件：行号、问题、建议
- 最后列 residual risks
- 用中文，简洁，拿证据说话（引用代码行，不要泛泛而谈）
