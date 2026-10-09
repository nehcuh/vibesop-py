# B2 Kimi 预 commit 完整 diff 门禁报告（GLM 批次，新基线 d9d7804f）

日期：2026-10-09
裁决：**APPROVE**
审查对象：`/private/tmp/vibesop-opt-20261009/snapshots/B2-glm-pre`（隔离快照，工作树 = 待提交 B2 补丁）
父提交：`d9d7804ffd1dfb92f6a82138e5a07f5304a11df0`
完整二进制补丁：`.omx/artifacts/diagnosis-B2.diff`，89405 字节，SHA256 `cc3a9539572b64c827d0033516f35f81e869a0aea358034ea4f44385333021df`
冻结收据：`/tmp/vibesop-opt-20261009/B2-frozen.json`
审查者身份：**Kimi Code CLI（本会话，Kimi 技术负责人最终门禁角色）**；未委派子代理、未调用任何其他 CLI 模型/provider、未做任何认证/provider 探测。本报告不沿用、不替代任何前次批准，全部证据为本轮亲自执行。

## 1. 收据与补丁完整性核验（全部亲自重算）

| 核验项 | 结果 |
| --- | --- |
| 补丁文件 SHA256 / 字节数 | `cc3a9539572b…21df` / 89405 —— 与收据逐字符一致 ✅ |
| 工作树增量 = 补丁文件 | `git diff HEAD -- <11 paths>` 与 `.omx/artifacts/diagnosis-B2.diff` **逐字节相同**（`cmp` 通过）✅ |
| 11 个文件工作树 sha256 vs 收据 `source_sha256` | **逐一相符**（`shasum -a 256` 全部比对）✅ —— 源码字节相对 pre-GLM 历史冻结收据零漂移 |
| 补丁在新父提交上可前向应用 | `git archive HEAD` 抽取 11 个原始文件至 `/tmp/vibesop-opt-20261009/B2-applycheck` 后 `git apply --check` → **通过**（新父/CHANGELOG 上下文有效）✅ |
| HEAD / 父提交 | HEAD 恰为 `d9d7804f`，merge-base 一致 ✅ |

## 2. 新基线增量核验（相对前次批准的 ed8227dc 基线）

`ed8227dc..d9d7804f` 仅两个提交：`57b6169d`（B3，step_runner/workflow_engine/execution_protocol + 测试）与 `d9d7804f`（B3-r2，execution_protocol/step_runner + 测试）。

- **文件级**：`git diff --stat` 确认两提交对 B2 的 10 个 src/测试文件**零触碰**；唯一交集是 CHANGELOG.md（两提交各自追加了 B3/B3-r2 条目）。
- **补丁级**：剔除 CHANGELOG 后的 src/测试 hunk 段（87162 字节，sha256 `279f07db…e23c9`）与上一轮已批准段的 `b2-new-src-tests.patch` **逐字节相同**（本轮重抽 `/tmp/vibesop-opt-20261009/B2-glm-src-tests.patch`，`cmp` 通过）。本补丁相对上一轮的唯一差异是 CHANGELOG hunk 对新基线的适配。
- **语义级**：B3/B3-r2 作用于 agent 执行 lane；B2 作用于路由候选缓存与 loader 发现，无共享状态。
- **CHANGELOG 工作树终态已直接读取**（前 40 行）：Changed 节 B2 条目正确插于 B3 条目之上，Fixed 节 B2 条目正确插于 B3-r2 条目之上；B2 条目文本与实际代码一致（schema v5 指纹覆盖 markdown/YAML discovery 集 + governance projection；disable/scope/lifecycle/ownership/同时间戳失效；未改动字节复用解析快照）；B1/B3/B3-r2 及更早条目上下文完好。

## 3. 完整 diff 已全文通读（2034 行，9 个文件有 hunk）

范围声明：本补丁将路由候选缓存从「路径+mtime 指纹、loader 缓存不联动」升级为「内容+governance+registry 指纹（schema v5）、分层缓存一致失效」，修复诊断报告 D04/D05，对应路线图 B2 批次（owner Grok）。

通读结论（正确性/安全/并发逐项过）：

- **指纹正确性**：`_hash_labeled` 长度前缀 framing 无边界碰撞；`_dedup_paths`/`discovery_input_files` 与 loader glob（`*.md`、`*.yaml/*.yml` 减 non-skill YAML）同源，fingerprint、mtime walk、磁盘缓存三线共用 `_fingerprint_search_paths()`（含 loader 默认附加根，回归 test_default_project_skills_root_is_fingerprinted 覆盖）。
- **失效链路**：`_cached_reload_locked` 先 `_invalidate_discovery_caches()`（skill map + external pack cache）再查盘/重扫，重扫后重算指纹才落盘——D05「旧 metadata 写入新指纹」断链；`_load_from_disk_cache` 拒收 schema≠5；`reload()` 先删盘文件；`_usable_index_cache` 经 `index_cache_epoch` 使 router 侧语义索引缓存随 reload 失效。
- **governance 热路径**：`_governance_changed_locked` 在 `_cache_lock` 内每条 route 检查 auto-config projection（与 `get_skill_config` 共享 content-addressed `_ConfigSnapshot`），绕开 5s 深度 walk 间隔；`usage_stats` 不入投影（不抖动池）。
- **安全**：无注入/密钥/路径越界新增；指纹只读搜索根与固定配置路径下的文件，无网络/壳调用。
- **API 兼容**：既有 API 全部保留——`SkillLoader.clear_cache` 语义不变（仅清 skill map），`discover_all(force_reload)` 不变，`reload_candidates()` 公开语义不缩；新增接口全部为 additive（`invalidate_discovery_cache`、`discovery_search_paths`、`discovery_skill_files`、`is_non_skill_yaml_path`、`ExternalSkillLoader.clear_cache`、`invalidate_config_cache`/`governance_projection`/`config_content_version`、`index_cache_epoch`）。**register-only 债务保留**：`core/config/manager.py load_registry` 内存缓存仅审计登记、未被本批改动（`_registry_files` docstring 明示），与路线图一致。`SkillManager.reload_skills`（manager.py:246-247，`_config`=`ConfigManager`，`clear_cache` 存在于 core/config/manager.py:957）不受影响。

## 4. 定向复验（uv，新基线 d9d7804f 实跑）

- `uv run pytest tests/unit/core/routing/test_candidate_manager.py tests/core/skills/test_loader.py tests/core/routing/test_skill_governance.py tests/unit/core/routing/test_matcher_rewarm.py tests/core/routing/test_demo_skills.py -q` → **121 passed**（1.51s）。
- `uv run ruff check`（全部 5 个 src + 3 个有改动测试文件）→ All checks passed!

## 5. 本人亲自执行的 producer/consumer 反例（7/7 通过）

探针 `/tmp/vibesop-opt-20261009/B2-glm-probe.py`（自写、独立、真实公共入口，非引用他人结论），输出 `/tmp/vibesop-opt-20261009/B2-glm-probe-stdout.txt`，工作目录 `/tmp/vibesop-opt-20261009/b2glm-gs7zd_oh`（全程不写仓库；首轮 3 个 FAIL 均为探针自身场景污染/时序假设错误——共享 CONFIG 残留与「disable 后指纹本应变化」——修正探针后 7/7 通过，产品侧无对应缺陷）：

| # | 反例 | 结果 |
| --- | --- | --- |
| P1 | D04：真实 `update_skill_config(enabled=False)` → 热实例重建并把新指纹写入磁盘 → 新 `CandidateManager` 消费（sentinel 证明磁盘命中路径，文件 mtime 未变）且不复活被禁技能 | PASS |
| P2 | 同 mtime auto-config 改写 enabled:false：内容寻址快照读者、热池、新实例、磁盘文件四者一致剔除 | PASS |
| P3 | D05：同 mtime SKILL.md 正文改写：声明间隔后自动刷新 + 显式 `reload()` 均返回新正文，磁盘仅存新正文于新指纹 | PASS |
| P4 | 伪造 schema v3/v4 磁盘条目（paths_hash 恰好相同）被 `_load_from_disk_cache` 拒收 | PASS |
| P5 | `reload()` 后 router `_index_layer_cache` 经 epoch 失效，stale profile 被清 | PASS |
| P6 | `usage_stats` 写入不移动指纹；enabled 写入移动指纹 | PASS |
| P7 | 5s 深度 walk 间隔已 armed 时，scope 改写仍在下一条 route 可见（governance 热检不占间隔） | PASS |

## 6. 分级发现（P0 必须修 / P1 应修 / P2 建议）

- **P0：无。**
- **P1：无。**
- **P2（不阻塞，登记）**：
  1. `src/vibesop/core/skills/loader.py:81-84` —— `try/except OSError` 包住 `root.rglob(...)` 调用无法捕获惰性迭代期的 OSError（权限错误仍会向上传播）。属补丁前既有的同型暴露（旧 `_compute_paths_hash`/`_compute_skill_mtimes` 亦同），非本批回归。
  2. `src/vibesop/core/skills/config_manager.py:393-399` —— 内联解码在 locale 回退时不再记录旧 `read_text_with_fallback` 的「非 UTF-8」警告，回退静默化。纯可观测性差异。
  3. 每 5s 深度检查为 O(全部 discovery 文件字节数) 重读，超大技能树下有 CPU/IO 成本——系声明设计（CHANGELOG 已载明 5s 间隔保留），登记备查。
  4. `reload()`/`pin_search_paths` 在 `_cache_lock` 外改 `_candidates_cache`/`_governance_token_cached` 等——与补丁前 `reload()` 的既有无锁模式一致，CLI 单线程语义下不构成新风险。

## 7. 边界与未覆盖声明

- 未 commit/push；未改动库内任何源码/测试/CHANGELOG/补丁/收据；全部写入限于 `/tmp/vibesop-opt-20261009`（探针、stdout、切片、applycheck 目录、B2-glm-worktree.diff、B2-glm-src-tests.patch）。
- 未委派、未调用其他 provider/CLI 模型、未做认证探测。
- **本报告是代码审查，不是原生 Windows 证明**：Windows 3.12/3.13+wheel CI 在源码提交后仍为必需项。
- 本门禁不替代流程中的其他角色：Grok 作者的 Claude 独立交叉审（预 commit 并行闸）与提交后 Grok 第二道闸（`git archive HEAD` 隔离复跑）仍以各自结论为准；hermetic 路由评测与容器全量回归属收批/终轮验证，本批不触碰 SKILL.md/registry 源文件，基线不应 STALE。
- 前次 Kimi 批准（`B2-kimi-final-pre-report.md`，APPROVE@ed8227dc）不构成本次批准的依据；本轮对全部关键证据独立重算。

## 8. 结论

补丁字节与冻结收据完全一致；源码字节相对 pre-GLM 历史收据零漂移；src/测试 hunk 与此前批准段逐字节相同，唯一增量（CHANGELOG）经全文读取与干净树前向应用核验正确；新基线两提交与 B2 零文件重叠（除 CHANGELOG 上下文，已适配）；121 项定向测试与 ruff 全绿；本人独立执行的 7 个真实 producer/consumer 反例全部通过；P0/P1 发现为零，仅 4 条 P2 登记项。**APPROVE**，B2 可进入提交流程（以 §7 所列其余流程角色与提交后 CI/Windows 验证为条件）。
