# gate18 复审报告 — M12 M4+M5

## Verdict: **PASS_WITH_NITS**

无 BLOCK。所有关键契约经执行验证（非仅静态检查）。

## 验证证据摘要

| 检查项 | 结论 | 证据 |
|---|---|---|
| 测试 | 全绿 | 改动文件 151 passed；CLI+dashboard 753 passed；observability 472 passed；ruff 全清 |
| 全局隐私剔除 | **实测零泄漏** | 直接渲染含 `SECRET-TOKEN` / `/Users/jane/...` 的全局草稿：query、路径、用户名全部不出现；`gold_task_ids` 是 sha1[:16] 哈希（task_id.py:96-113）、`core_steps` 仅工具名，符合“只存工具名”边界 |
| 看板零写入 | **实测确认** | fresh project + fresh home 调 `build_discoveries_payload` → 两处均无新目录。守卫链成立：candidate 文件存在性前置（`_discoveries.py:93-95`）；signal/observation store 仅在该 scope 有候选时构造（dir 必已存在，mkdir 为 no-op）；`build_queue(observe=False)` 跳过 `observe()` 写调用（discovery.py:489） |
| confirm 不可绕过 | 确认 | 空输入 → default False（`test_global_force_still_requires_confirmation` 锁定）；stdin EOF → click Abort → exit 1，非交互环境 fail-safe |
| re-promote 不 re-baseline | 确认 | `fresh_write` 在 materialize 前判定（skill_commands.py:1828-1831）；store `_apply` 仅在 hash 非 None 时写（skill_promote.py:519-524）；`test_repromote_does_not_rebaseline_hash` 锁定 |
| 守卫链顺序 | 符合设计 | 文件缺失(1910)→legacy None hash(1918)→hash 相同(1932)→全局 [XP] 证据(1948)→confirm(1958)，全部 exit 1 |
| fallback store hash 归属 | 确认 | 实测：候选在 project store、`--scope global` 提升时，hash 记录在被 reload 的同一 store 行上 |
| miss_share_by_layer 口径 | 正确 | 与 `miss_pool_size` 同一过滤后池（skill_promote.py:955-961）；dict/JSON-string 容差与 `is_route_miss_span` 声明一致 |
| 时间炸弹 | 预存确认 + 根治 | HEAD 版日期 `2026-07-21/22/23`（git show 验证），30 天窗口 cutoff 在 07-22 附近，今天 08-21 → HEAD 必挂。修复用 `now - timedelta(days=5-i)`（3-5 天前，25 天余量，相对时间永不衰减） |

## Findings

### NIT

1. **`src/vibesop/cli/commands/skill_commands.py:1725-1729`** — `--force` 语义过载：help 只说 bypass edit guard / evidence，但它还转发给 `_install_skill_or_exit(..., force=force)`（:1973）承担“强制重装”语义。建议 help 补一句（如 "also forces reinstall if the skill already exists"）。

2. **`src/vibesop/dashboard/_discoveries.py:41-44`** — 跨层导入 core 私有符号 `_sanitize_body_text`（不在 `skill_promote.__all__`）。与 CLI 层既有做法一致，但 dashboard → core 私有 API 耦合，重命名时会静默断。建议在 skill_promote 把它升为公开（或并入 `__all__`）。

3. **`src/vibesop/dashboard/_discoveries.py:81-104` vs `skill_commands.py:2095-2107`** — “更异质记录胜出”的去重规则在两处独立实现（CLI `_gather_scoped_candidates` / 看板 `_load_scoped_candidates`）。root 解析不同（cwd vs `_resolve_project_root`）导致无法直接复用，但规则漂移风险实在。建议任一侧注释指向另一侧（CLI 侧已有指向，看板侧 docstring 也提了——至少加个双向引用测试防止两处口径分叉）。

4. **`tests/dashboard/test_server_endpoints.py:589-598`** — `test_returns_empty_payload_when_no_stores` 未断言模块头部的 headline 保证“不创建新目录”。我已手工验证该行为，建议补一行 `assert not _global_obs_dir().exists()`（`tmp_project` fixture 预创建了 project 侧目录，只能锁 global 侧——也值得）。

5. **`src/vibesop/cli/commands/skill_commands.py:2212` vs dashboard** — CLI `discover` 默认隐藏 dismissed/muted（`--all` 才显示），看板默认全显 + 徽标。同一信号源、不同默认呈现。看板有 status 徽标 + by_status 统计补偿，属可辩护选择，但两处“队列默认视图”口径不同值得知晓。

## Residual Risks

- **编辑守卫可被任意字节变化满足**（含纯空白编辑）。实现忠于设计契约（内容 hash）；设计文档里“mtime 会被空白编辑骗过”的论据其实同样适用于 hash——hash 只证明“写过”不证明“实质改过”。守卫定位是防误激活的减速带而非安全边界（`--force` 本就存在），可接受。
- **skill_id 从 queries[0] 派生**：重扫后 queries 顺序变化 → skill_id 变 → 新路径 fresh draft 重新 baseline，用户编辑过的旧草稿孤儿化。守卫 fail-safe（新草稿未编辑 → 拒绝），预存派生逻辑，非本 diff 引入。
- **非交互环境全局激活必 Abort**（stdin 关闭 → click Abort）。符合隐私默认 N，但 hook/agent 场景下无法完成全局激活，需真人 TTY。
- **`miss_share_by_layer` 真实数据恒为 unknown 100%**——route-span 生产方不写 `layer` 字段，诚实降级已声明；待生产方补字段后才有信号价值。
- **M2 出口标准仍延期**（真实 miss 池数据积累，gate17 已记录）——M4/M5 不依赖该出口，不受影响。
