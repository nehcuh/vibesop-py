# B2 Kimi 收批核证报告（批次关闭）

- 日期：2026-10-09
- 核证人：Kimi 技术负责人（收批关闭角色，新会话独立执行链上核验；未委派子代理、未调用任何其他模型/provider、未做任何认证探测）
- 约束遵守：未改库内任何文件、未 commit/push、未跑 pytest/Docker、未调 API/provider；全部 git/哈希/日志复核为只读，唯一写入即本报告
- 裁定：**BATCH_CLOSE_APPROVE**

## 一、提交链独立核验（本会话亲自重算）

| 项 | 结果 |
| --- | --- |
| HEAD | `7d1160f0c22375c85505e12c37b1dc3a6e0ce6da`（subject `fix(routing): invalidate discovery caches after governance and content changes`）✅ |
| parent | `d9d7804ffd1dfb92f6a82138e5a07f5304a11df0`，与 `B2-post-frozen.json`、`B2-commit-receipt.json` 逐字符一致 ✅ |
| 完整补丁 | `git diff d9d7804f 7d1160f0` = **89405 字节**，SHA256 `cc3a9539572b64c827d0033516f35f81e869a0aea358034ea4f44385333021df`（本会话重算），且与 `B2-glm-worktree.diff` `cmp` 逐字节相同 ✅ |
| 提交路径 | `git diff-tree -r HEAD` 恰为收据 `committed_paths` 的 9 条，无增减 ✅ |
| 收据 11 路径 sha256 | 本会话对 post 快照工作树逐一 `shasum -a 256` 复算，与 `source_sha256` **11/11 全部吻合**（含 2 个未变审计测试文件）✅ |
| 2 个未变定向审计测试 | `tests/unit/core/routing/test_matcher_rewarm.py`、`tests/core/routing/test_demo_skills.py` 在聚焦集内，parent→HEAD blob 相同（未提交，符合预期）✅ |
| tree / archive | HEAD tree `cfc1341190c04d64a3fede7a9a4fc3691aed4bfe`、`git write-tree` 同值、`git archive --format=tar HEAD` SHA256 `9f1a95776f46d80e1f822e045db52683d237bebad275192088a87a571bbd7d9e`（本会话重算，与 post-frozen `archive_sha256` 一致）✅ |
| 工作树 | post 快照跟踪文件对 HEAD 干净；仅 3 组未跟踪诊断产物（`.omx/artifacts/diagnosis-B2.diff`、`docs/plans/2026-10-09-diagnosis-optimization.*`、诊断归档目录），全部在提交之外 ✅ |

收据（commit-receipt 与 post-frozen）二者互洽且与链上实况一致，**未发现任何伪造项**。

## 二、三道门禁链（全部 APPROVE，证据同源同补丁）

1. **Kimi 预 commit 门禁**（`B2-kimi-glm-pre-report.md`，APPROVE）：基线 d9d7804f，同一补丁 sha/字节；11 路径 sha256 复现、前向 apply 通过、CHANGELOG 终态直读、全文 2034 行通读；定向 pytest 121 passed + ruff；本人独立 producer/consumer 反例 7/7 PASS。
2. **GLM 交叉审**（`B2-glm-cross-report.md`，APPROVE）：审查者 Claude Code CLI 2.1.153，后端模型 **GLM-5.3**（身份证据：config receipt、session receipt、`logs/claude-glm-identity.jsonl` 流日志 sha 复核链）。独立重跑 121 passed、7 个探针 80 断言全 PASS、ruff/format/basedpyright 全绿、hermetic 0 drift。**身份为客户端级证据（config/init/modelUsage），无人主张 provider 服务端 attestation** —— 该限制已在原报告中声明，收批予以确认。
3. **Grok 只读 post-commit 闸**（`B2-grok-post-report.md`，APPROVE）：独立新会话、**非作者**；在重建的非浅克隆快照（1084 提交）上亲证：HEAD/parent/tree/补丁 sha 全部重算吻合、121 passed、ruff/format/pyright、独立探针 13/13 PASS、hermetic 重跑 59 matched / 6 known / 0 drift；并复核了前两条门禁的会话日志（GLM 流日志中 `claude-sonnet` 仅为源码字符串，modelUsage 键只有 GLM-5.3）。

## 三、容器日志（如实记录，不加修饰）

| 运行 | 镜像 | 结果 | 性质 |
| --- | --- | --- | --- |
| 首跑 `logs/B2-glm-target-container.log(.result.json)` | `vibesop-next-val:node24` | exit 1，501.21s，`numpy==2.5.2` 下载网络超时，**依赖安装阶段失败、日志中无 pytest 会话** | 环境/网络失败，原样保留，**不算 PASS** |
| 重试 `logs/B2-glm-target-retry-container.log(.result.json)` | `vibesop-opt-depcache:20261009` | exit 0，4.1s，**121 passed in 1.58s** | 容器内通过 |

两条日志的 `patch_sha256` 均为 `cc3a9539…21df`，与提交补丁一致；测试路径集合与聚焦五文件一致。

## 四、D04/D05 语义与边界核验

- **D04 governance 即时**：enabled/scope/lifecycle/owner-hash 变更在下一路由可见（content-addressed projection，不占 5s 深度间隔；usage_stats 不入投影）；**D05 内容 5s**：同 mtime 正文改写经声明的 5s 窗口后自动刷新、显式 `reload()` 立即刷新 —— 三路报告独立复证一致，`_RELOAD_CHECK_INTERVAL = 5.0`，CHANGELOG 已载明该设计。
- **schema v5 拒旧**：`_load_from_disk_cache` 拒收 v3/v4 磁盘条目（伪造同 paths_hash 探针 PASS，三路各自执行）。
- **hermetic 路由评测**：GLM 与 Grok 各自独立重跑 `eval_routing.py --hermetic --check` → 均为 **59 entries matched / known-fails 6 / new-fails 0 / drift 0**，与冻结基线一致（本会话直读 GLM 原始输出复核）。
- **边界**：提交 diff 中**无 `core/skills/**/SKILL.md`、无 `core/registry.yaml`**（roadmap §1.1），路由基线不负刷新义务，与 0-drift 结果自洽。

## 五、债务如实结转（登记制，无「全部修复」主张）

- **Kimi P2 ×4**：`loader.py` rglob 惰性迭代 OSError 暴露（补丁前同型）、config 内联解码丢失非 UTF-8 警告（纯观测性）、5s 深度 walk 的 O(总字节) 成本（声明设计）、`reload()` 无锁形状（与补丁前一致）。
- **GLM P3 ×3 + Grok 同型 P2**：内容寻址带来的深度检查成本上升（D05 的正确性代价，已量化登记）、盘命中亦清解析缓存/ bump epoch 的过度失效（方向为多做功，永不引入陈旧）、`filter_routable` DEPRECATED 警告分支不可达（pre-existing，Grok P2 与 Kimi P2.1 同型登记）。
- **register-only**：`core/config/manager.py` `load_registry` 内存缓存 blob `8bb2bded…` 与 parent 相同，仅审计登记，未被本批改动；`SkillManager.reload_skills` 契约不受影响。
- 以上均为**登记项**，任何报告均未主张「bug 全部修复」。

## 六、用户原始 9 文件守卫（亲证）

- B2 提交 9 路径与守卫 9 文件**零交集**；其中 6 个跟踪文件（`.pi/*`、`Makefile`）parent→HEAD **blob 全部相同**。
- 本会话在实盘工作库 `/Users/huchen/Projects/vibesop-py` 对 `original-user-changes.json` 逐字节复算：**9/9 全部 OK**，用户原始文件自基线以来未被触碰。
- 说明：post 快照内这些文件与守卫值不同属预期 —— 快照为 `git archive` 已提交内容，用户未提交的本地版本不在归档中；守卫的对象是用户工作树，已在实盘验证。

## 七、限制与范围（provenance）

- **原生 Windows 3.12/3.13 + wheel CI 仍 pending**：本批次关闭不构成 Windows 证明，CI 为后续必需项。
- node24 首跑容器失败为环境/网络（依赖安装阶段），非代码缺陷；该失败记录保留于日志链。
- GLM-5.3 身份仅客户端级证据（config/init/modelUsage/流日志），无 provider 服务端 attestation。
- 本会话收批核证未重跑测试/Docker：对链上可复算项（HEAD/parent/补丁 sha/字节/11 blob/tree/archive sha/守卫 sha）**全部亲自重算**，对执行型证据（121 测试、探针、容器、hermetic）复核其原始日志与三道独立报告的互洽性。
- **本次关闭仅覆盖 B2 源码批次，不代表整个项目完成**；其余批次与整体验收不在本裁定范围内。

## 八、结论

提交链、收据、三道独立门禁、容器日志、hermetic 基线与用户文件守卫**七线证据互洽且无矛盾**；可复算项本会话全部亲算通过；债务全部如实登记结转。B2 源码批次关闭裁定：

# **BATCH_CLOSE_APPROVE**
