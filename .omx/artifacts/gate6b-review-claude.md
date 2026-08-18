复审完成，全部证据已收齐。以下是 gate6b 复审报告。

---

# Gate 6b 复审报告：D BLOCK 修复 + 同轮 nits

## 1. BLOCK 修复闭环验证 — ✅ 闭环

| 验证项 | 证据 | 等级 |
|---|---|---|
| 渲染内容分支写标记 | base.py:533-536（`write_skill_marker(skill_dir, skill_id, "render")`） | [inspected] |
| copy 兜底分支写标记 | base.py:614-618（"pack-copy" + 源路径） | [inspected] |
| pack_installer 写标记 | pack_installer.py:795-804 | [inspected] |
| 旧测试还原为真实路径 | `test_clean_orphan_skills`（tests/adapters/test_base.py:312-322）走真实 `_render_skill_content`，仅 stub 内容来源查找 `_find_skill_content`，标记写入本身未 stub | [inspected] |
| 回归测试钉死 | `test_rendered_skill_is_cleaned_after_manifest_removal`；**突变验证**：将 `write_skill_marker` 替换为 no-op（模拟修复前），渲染产物无标记且 `clean_orphan_skills` 返回 `[]` —— 测试两条断言均失败 | [executed] |
| 无旁路调用方 | file_based.py:312、pi_coding_agent.py:143 均经继承的 `_render_skill_content` 产目录后才调清理（:320 / :146） | [inspected] |

## 2. 五个攻击点逐一回应

**P1 源标记优先的语义冲突 — 无冲突。** 平台目录标记的唯一消费者是 `clean_orphan_skills` 的存在性检查（base.py:245），grep 全仓确认 `.vibe-manifest.json` 的唯一解析点在 storage.py:606 `_read_metadata`，仅作用于 central storage 路径。copytree 带来的 central 标记（id 含 `/` 命名空间）与 `write_skill_marker` 的 flat_name 命名空间不同，但 id 字段在平台目录无任何消费者；保留 central 溯源比覆盖为 "pack-copy" 语义上更准确。[inspected]

**P2 标记写失败仅 warning — 可接受，含自愈。** 失败方向保守（不清理、不删用户内容），且 skill 仍在 manifest 时下次 build 会重渲染并重试写标记——只有“SKILL.md 写成功而同目录小标记文件持续写失败”这种奇异性条件才会留下永久无标记目录。但发现一个次级残余（见 NIT-1）。

**P3 lazy import 循环 — 无风险。** base.py 模块级只 import models/security，不依赖 installer；pack_installer 已有同模式 lazy import 惯例（:816 indexer、:817 factory）。[inspected]

**P4 还原后测试真实性 — 通过。** 见上表第 4 行；copy fallback 测试 stub 的 `is_pack_installed`/`can_create_dir_symlink` 均为环境探测，copytree 与两个 marker 写入真实执行并断言 JSON 内容。[inspected + executed]

**P5 CLI_REFERENCE 逐字核对 — 一致。** "0/false/no" 与 triage_service.py:471 `os.getenv(...).lower() in ("0", "false", "no")` 逐字对应；"fresh hits still served" 对应 LLM gate 移至 cache lookup 之后（:202-211）；"full kill switch" 对应 ：122-123 的 `enable_ai_triage` 前置短路；`.vibe/triage_cache.json` 文件名与 TestCacheDirResolution 一致。[inspected]

## 3. 自行挖掘

- **LLM gate 移动的次生效应已验证安全**：gate（:207-211）位于 budget/circuit 的 last-good 分支（:230/:243）之前，LLM unconfigured 时 stale-only entry 不会泄入 last-good —— 与注释声明一致。[inspected]
- **write_text 非原子**（base.py:58）：崩溃可留空/半写标记，但 cleanup 只查存在性且平台目录无解析者，失败方向正确（视为 vibe-managed 可清理）。无后果，不立 nit。[inspected]
- **junk JSON 输出 schema 一致**：junk 分支与正常分支均为 `{"query", "sub_tasks"}`（main.py:1086 vs 1108-1124），与 route --json（:1055）同用 print 通道。[inspected]

## 4. 同轮 4 nit 收敛质量

- **A1** ✅ [executed]：双分支均 print，160 字符长 query 的 `json.loads` 测试通过。
- **A2** ✅ [inspected]：agent/__init__.py:200-207 docstring 准确（含 CLI 区分说明）。
- **B1** ✅ [inspected verbatim]：环境变量表与代码逐字一致；CHANGELOG 两条款语义准确。两处微瑕见 NIT-3。
- **env=0 测试** ✅ [executed]：monkeypatch.setenv 真实 env 路径 + `init_llm_client` spy 断言未调用 + fresh 命中返回。env=0 + miss 无专测，但该路径已由 `test_miss_short_circuits_without_llm` 的 unconfigured-LLM miss 覆盖，可接受。

## 5. 测试执行记录 [executed]

- 5 个改动/新增测试文件：**153 passed**
- tests/unit/core/routing + tests/core/routing：**590 passed, 2 skipped**
- tests/agent：**141 passed**；tests/cli：**659 passed**
- ruff（全部 12 个改动文件）：**通过**
- 突变验证（write_skill_marker no-op）：回归测试两条断言均失败 → 测试钉死修复 ✅

## 判定

**NIT-1**：base.py:610-624 copy 兜底中 `write_copy_source_marker` 与 `write_skill_marker` 共用一个 try——前者抛 OSError 会连带跳过 ownership marker，留下无标记拷贝。建议 ownership marker 先写或拆分 try。

**NIT-2**：`_fallback_skill_content` stub 分支（base.py:628-652）不写标记，stub 目录离开 manifest 后永不清理。包内已披露为后续候选；方向保守，确认 NIT 级。

**NIT-3**（B1 微瑕）：CHANGELOG "raises a ValidationError at startup" 实际发生在首次 RoutingConfig 加载（CLI 场景等效启动）；config 描述 "(see bigram threshold calibration notes)" 指向 `.omx/artifacts/`（内部归档）而非 docs/，对外是悬空引用，建议改指 `scripts/calibrate_index_threshold.py`。

---

## 最终结论：**PASS_WITH_NITS**

D BLOCK 修复真实闭环：三条主路径全部写标记，旧测试还原为真实渲染路径，回归测试经突变验证确认钉死修复，无旁路调用方。3 个 NIT 均为保守方向的残余缺口或文档微瑕，不构成阻断。
