核查完毕。以下为第二轮复审结论。

## Verdict
PASS_WITH_NITS

## Findings

**MAJOR 修复验证（全部通过）**

- pi-MAJOR / claude-NIT-3（跨 scope 批量 dismiss 复活）：已正确修复 `[inspected]`。`_discover_dismiss_shape_agent_echo`（skill_commands.py:2752-2774）对每个目标 cluster_id 在 project+global 两个 store 各自查 `store.get(cid)`，仅 `status=="pending"` 才翻；`flipped` 只计真实 pending→dismissed，`flipped_ids` 簇数与行数分开输出，文案如实；预检还避免了覆盖镜像行既有 terminal reason。`dismiss()` 自身带 flock + 锁内重读（skill_promote.py:957-999），get→dismiss 的 TOCTOU 良性。「重扫不会复活」有 store 契约背书（skill_promote.py:433-439,597,1618）。测试 `test_cross_scope_mirror_rows_flipped_together`（global 去重胜出仍双翻、队列与 --all 均不复活）+ `test_already_terminal_mirror_not_counted` 覆盖到位。
- claude-MAJOR-1（基线未落痛点语料）：已修复 `[executed]`。`.omx/artifacts/gate35-echo-measure-cmspark.md` 存在（project_root=cmspark，2026-08-22T13:28:08Z）；我对 cmspark 复跑脚本，五组数字逐位一致（miss 池 525、完整谓词 4.8%、前缀 3.0%、卡片 9/21=42.9%、风险人口 1.7%）。两个重议门槛均未触发（42.9%<80%、1.7%>1%），与修订 G「不做清单」自洽。
- claude-MAJOR-2（(b) 卡片口径漏 global scope）：已修复 `[inspected]`。`_pending_cards`（measure_echo_share.py:85-113）读 project+`Path.home()` 双 scope；去重规则与 `_gather_scoped_candidates`（skill_commands.py:2281-2290）、`_load_scoped_candidates`（_discoveries.py:109-122）三方 lockstep（project-first 迭代 + 仅严格更大 project_distribution 替换）；`list_pending(include_unstable=True)` 等价于裸 jsonl 的 status=="pending" 过滤（容量 cap 只作用于插入/prune 不作用于读）。`test_global_only_cards_counted` 锁定该口径。
- 我 r1 其余 NIT 对账：scan 口径文案钉死「本次扫描范围」（skill_commands.py:1552-1557）✓；flipped 计数虚高修复 ✓；`source_outcome_stats` 全零桶不渲染 + `reviewed_at=None` fail-open 披露（discovery.py:693-698）✓；脚本 legacy age-out 偏差已披露且行号引用核实准确（1404-1408、1446-1449）✓；--history shape-batch 单列不进 Dismissed 表（skill_commands.py:2614-2619）✓；冻结谓词一字未动（skill_promote.py diff 纯增量）✓。

**新问题 / 残留（均 NIT）**

- [NIT] r1 测试残留 NIT-7 未修，与「已全部修复」声明不符：tests/core/observability/test_discovery.py:321-325 在 `test_observe_flocks` 尾部仍重复 monkeypatch+observe+断言；tests/cli/test_skill_discover_echo.py:322,349 在 `discovery_env` fixture（:65 已 patch）之上重复 patch `_get_candidate_store`。均无害冗余。
- [NIT] 脚本 (b) 分母与 discover 队列默认视图的可见性过滤不同集：脚本只滤 `status!="pending"`，但旧路径 `discover dismiss <id>` 只写指纹负名单不翻池状态（skill_commands.py:2829-2843），被负名单/静音隐藏的 pending 行仍进 (b) 分母——方向上可高估卡片回声率。lockstep 声明只覆盖去重规则，未覆盖可见性过滤；当前 42.9% 距 >80% 门槛远，不构成决策风险，但重议时需知晓（measure_echo_share.py:87-113）。
- [NIT] `_load_all_rows` 的 no-dedup 理由对批量路径不成立：docstring 称「同 cluster_id 双 scope 各 dismissed 是两个决策」（_discoveries.py:125-134），而新批量路径一次 `--yes` 机械镜像翻转两 scope——镜像簇的 shape_batch 在 CLI/看板统计中计 2。审计行计数本身可辩护，但文案理由错误且「每次用户决策」与展示数字会背离（discovery.py:649-697 同口径）。
- [NIT] 规格文本漂移残留（r1 NIT-1 已处置，非回归）：§3 阶段一 item 2「按 cluster_fingerprint 分组沉底可展开」仍为打标+平铺沉底，无决策记录。另 tests/dashboard/test_server_endpoints.py 混入 ~150 行纯 ruff 重排版噪声，掩埋 3 个真实新增测试。

验证声明：静态结论均 `[inspected]`（工作树与 r2.diff 对账一致）；cmspark 基线 `[executed]` 复跑复现；pytest 因权限被拒未运行，「零回归」未独立复核。
