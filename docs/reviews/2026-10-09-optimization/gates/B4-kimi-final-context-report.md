# B4 parent/CH-only final-context reconciliation — Kimi 终审报告

- **裁决**：**APPROVE**
- **审查人**：Kimi（技术负责人，final pre-gate）
- **日期**：2026-10-09
- **性质**：只读终审 + 自有复跑/探针。未改任何源码/测试/CHANGELOG/patch/receipt；未 commit/push/PR；未用子代理/其他模型/API；未动 auth 全局、provider、spawn 配置；未运行 Docker（真实 Docker 证据走父已归档日志核对）。仅写本报告与自有探针/原始输出于 `/tmp/vibesop-opt-20261009`。

---

## 1. 身份、目标与冻结核验

| 项 | 值 | 实核 |
|---|---|---|
| 批次 | B4（D09 overlay policy roundtrip / D10 sandbox build 合同） | roadmap §B4 |
| 审查目标 | `/private/tmp/vibesop-opt-20261009/snapshots/B4-final-context-pre` | worktree |
| Parent | `beda9953c981336f6e2da1989307da0e94490c56` | `git log` HEAD 一致（其上为 B2 `7d1160f0`、B8 相关提交） |
| 全量 diff | `.omx/artifacts/diagnosis-B4.diff`，70772 bytes | 实读全部 1688 行 |
| **Full SHA256（新）** | **`1dd4a88029e4600e0e42f66bca0aff7abc2a17a7fe2b999bab7c999b4af77429`** | `shasum -a 256` 逐字符一致，等于 `B4-frozen.json.patch_sha256` |
| 冻结收据 | `/tmp/vibesop-opt-20261009/B4-frozen.json`（parent `beda9953…`） | 8 路径 source SHA256 逐条实核一致 |
| 关键源 SHA | pack_installer.py `72551cbd…`（pack725）、test_pack_install_order.py `d18e3c58…`（testd18） | 与历史批准收据完全相同 |

## 2. 与历史批准 863d 的对账（核心问题）

历史：`patches/history/B4-approved-before-B8-863d4e2e488ea24f.json/.diff`（71018 bytes，SHA `863d4e2e…`，parent `d9d7804f…`）。

自有逐文件比对脚本 `B4-kimi-final-context-compare.py`：对两个 diff 按文件抽取全部 `+`/`-` 变更行（忽略 context 与 hunk 头）逐条比较：

- **7 个文件（CHANGELOG.md、overlay.py、pack_installer.py、4 个测试文件）变更行序列全部逐字节相同**（142+334+817+84+28+17+4 行）。
- 全量差异仅为：CHANGELOG.md 的 after 态（父 CHANGELOG 现已含 B8/B2 条目，B4 条目本身不变）与各 hunk 的 context/行号偏移——即 **B2、B8 提交之后的 parent/CH context 平移**，无任何代码语义漂移。
- `src/vibesop/builder/manifest.py` 在两条 diff 中均无 hunk（`apply_overlay` 本就委托 `OverlayMerger`），receipt 两版 SHA 相同，与历史批准口径一致。
- 工作树 8 路径 SHA256 与两版收据全部相符（含 testd18）。

结论：**代码/测试字节与批准的 863d 完全相同，唯一变化是 parent/CH 上下文**。历史 Kimi `B4-kimi-windows-pre-report.md` APPROVE 与 GLM `B4-glm-cross-report.md` APPROVE（128 项自有探针）的批准对象在新 diff 上逐字成立，无需重新论证。

## 3. R1（此前唯一条件）—— 现已满足

- `logs/B4-windows-source-real-docker.log`：`1 passed in 0.79s`（真实 Darwin 宿主 + Linux 容器，opt-in `VIBESOP_B4_DOCKER_E2E=1`）。
- `B4-windows-source-real-docker-receipt.json`：source SHA 精确锁定 pack725 / testd18，`"matches_current_frozen_sources": true`。这两个文件在新旧 diff 中字节相同，故真实 Docker 证据对当前新补丁完全有效。
- 父的补跑义务（R1）按此证据**关闭**；本轮按令未自行运行 Docker。

## 4. 本轮自有复跑（本机 darwin）

- `uv run --extra dev --frozen pytest -q -p no:cacheprovider tests/builder/test_overlay.py tests/builder/test_manifest.py tests/installer/test_pack_install_order.py tests/installer/test_pack_installer.py` → **82 passed, 1 skipped in 6.98s，exit 0**（原始输出 `B4-kimi-final-context-tests-stdout.txt`）。
- 唯一 skip 经 `-rs` 单独复跑确认 = `test_pack_install_order.py:894` 的 `VIBESOP_B4_DOCKER_E2E` opt-in 真实容器 e2e 守卫。**skip 未充 pass**。
- `ruff check` 6 个 touched 文件全过；`ruff format --check` already formatted。

## 5. 本轮自有最小探针（22/22 通过）

`B4-kimi-final-context-probe.py`，输出 `B4-kimi-final-context-probe-stdout.txt`（`ALL_CHECKS_PASSED`，exit 0）。隔离纪律：**`PackLockStore.LOCKS_DIR` 显式 monkeypatch 到 scoped temp 下的 isolated-locks 目录；`HOME` 重定向到 scoped temp；所有锁只写 isolated 目录，用户全局 `~/.config/skills/.pack-locks` 零写入（已实查）**。独立生产者载荷 `kimi-final-context-artifact-v1`，仅替换网络 clone 与 docker 启动，保存的 `subprocess.run` 真实执行，无伪造 CompletedProcess：

- **SUCCESS**：install True；产物字节精确落盘；锁写 isolated 目录；argv = `docker run … --network none`，唯一 `-v <isolated>:/work:rw`，无 `docker.sock`。
- **REQUIREDFAIL**：子进程先写部分产物后 exit 7 → `(False, "Required build failed: … exit 7")`；isolated 目录无锁；失败 target 已清理。
- **NEGATIVE**（symlink artifact）：`PackBuildError("refusing symlink build artifact: generated/leak")`；`generated/` 未持久化；活树内外无任何 `leak`；无锁。
- **COPYFALLBACK**：注入 `OSError` 使目录 symlink 创建被拒 → 真实目录发布、非 link；`COPY_SOURCE_MARKER` 指向 central skill 解析路径；产物仍经沙箱写回；锁写入 isolated 目录。

## 6. R4 锁目录实查与精确清理

- 审查前、两轮测试复跑后、探针后三次实查 `~/.config/skills/.pack-locks/`：**仅历史锁 `ui-ux-pro-max-skill.json`（Jul 24, 317 bytes）**，内容完好，历史保留。
- 本轮测试/探针**零误写**全局锁（receipt 风险 R4 的复现路径在本轮被探针隔离纪律阻断），无需删除任何文件；无清理动作即是最精确的清理验证。
- 历史 Kimi 报告登记的 2 枚误写锁此前已删除，本次实查确认未再出现。

## 7. Windows 边界（口径维持，无越界声明）

- 本机 darwin，**无原生 Windows 证明**。本 diff 与 863d 变更行完全相同，Windows 夹具修正（Python `sys.executable` 入口、固定后缀 `rsplit(":/work:rw")` 盘符解析、production argv/安全断言）逐字未变。
- 盘符/中文/空格解析为字面字符串测试；Python entry/safety/public install/CLI 断言不变；无 skip 充 pass。
- **Windows Docker Desktop + Linux containers = 未验证（≠ 不支持）**；Docker 构建合同边界维持 Linux 容器。本报告不作任何 Windows 已验证声明，Windows 证明统归 Windows CI 路由。

## 8. GLM 遗留 findings 处置核对

F1（内存索引无上限）/F2（首冒号 vs 尾冒号解析不对称，fail-closed）/F3（skip 通知非失败，预存产品决策）均为非阻塞 Low/Info 登记，按批准口径**不扩大源码修改**；本轮对账确认新 diff 未引入任何额外变更。无 P0/P1/P2 新发现。

## 9. 证明路径

| 证据 | 路径 |
|---|---|
| 本报告 | `/tmp/vibesop-opt-20261009/B4-kimi-final-context-report.md` |
| 全量 diff（新 SHA 已核） | `…/B4-final-context-pre/.omx/artifacts/diagnosis-B4.diff` |
| 冻结收据 | `/tmp/vibesop-opt-20261009/B4-frozen.json` |
| 863d 对账脚本 + 结果 | `/tmp/vibesop-opt-20261009/B4-kimi-final-context-compare.py`（输出：7 文件 SAME-CHANGE-LINES, IDENTICAL-CHANGE-LINES） |
| 定向测试原始输出（82p/1s） | `/tmp/vibesop-opt-20261009/B4-kimi-final-context-tests-stdout.txt` |
| 自有探针 + 输出（22 checks） | `/tmp/vibesop-opt-20261009/B4-kimi-final-context-probe.py` / `…-probe-stdout.txt` |
| R1 真实 Docker 证据 | `/tmp/vibesop-opt-20261009/logs/B4-windows-source-real-docker.log`、`/tmp/vibesop-opt-20261009/B4-windows-source-real-docker-receipt.json` |
| 上游输入 | 历史 `B4-approved-before-B8-863d…json/.diff`、`B4-kimi-windows-pre-report.md`、`B4-glm-cross-report.md` |

**Kimi final pre-gate 终审：APPROVE**
**完整新补丁 SHA256：`1dd4a88029e4600e0e42f66bca0aff7abc2a17a7fe2b999bab7c999b4af77429`**（70772 bytes，parent `beda9953c981336f6e2da1989307da0e94490c56`）

条件全部关闭：R1 已由父真实 Docker 日志+receipt 满足；R4 全局锁目录实查干净、历史保留；Windows 证明维持 CI 路由口径。
