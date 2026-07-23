# Phase C Milestone — Merged Kimi + Pi Review

**Date:** 2026-07-23
**Brief:** `docs/decisions/_review-instinct-loop-phase-c-brief.md`
**Phase C diff:** ~1094 行（launchd.py + test_launchd.py 新建；loop_cmd.py + test_loop_cmd.py 改动）
**Verification:** 70/70 Phase C tests passed, ruff clean
**Adversarial pre-review:** FIX BEFORE EXECUTE → 6 flaws fixed (#1-#5) + 1 documented (#6)

## Reviewer sessions

- **kimi**: 撞月度配额中断（403），输出 844 行未完成正式 verdict 但分析完整。本 merged 提取其 findings。
- **pi**: 完整评审，CONDITIONAL（1 P1 + 3 P2）。

## Merged verdict

| | kimi | pi | Consensus |
|---|---|---|---|
| **总判定** | 部分（quota 中断）→ 含 2 个 pi 漏掉的 P1 | CONDITIONAL (1 P1, 3 P2) | ⚠️ **CONDITIONAL — 3 个 P1 必修** |
| Q1 paused loop 在 launchd | acceptable | acceptable | ✅ |
| Q2 refresh 路径自动触发 | acceptable | acceptable（建议修 N2） | ✅ |
| Q3 delete 保留 plist | acceptable | acceptable | ✅ |
| Q4 日志路径冲突 | ⚠️ **设计错** — 目录不存在 | acceptable（**missed**） | ❌ **kimi 对，pi 漏** |
| Q5 command_args 不暴露 | defer to Phase D | defer to Phase D | ✅ defer |
| Q6 exit 125 + stderr fallback | acceptable（launchd 不本地化） | defer-needed（建议 launchctl print） | ✅ acceptable w/ note |
| Q7 测试盲区 | FileNotFoundError 补（P2） | FileNotFoundError 补（P1） | ⚠️ **取严：补** |

## P1 必修项（merge 前处理）

### K-P1-1: 日志路径与 store 路径不一致（**kimi 独家发现，pi 漏**）

**问题**：`LoopStore.base_dir = Path.home() / ".vibe" / "loops"`（global），但 `render_plist` 把 `StandardOutPath`/`StandardErrorPath` 写到 `project_root / ".vibe" / "loops" / spec.name / {out,err}.log`（local）。该 project-local 目录从未被创建（`LoopStore` 只创建 home 下的，install-launchd 也不创建）。

**后果**：launchd 无法打开 StandardOutPath 父目录 → "Service could not initialize" → job spawn 失败 → feature **开箱即坏**。

**修法**：`launchd.py` 把 `loop_dir` 改为 `Path.home() / ".vibe" / "loops" / spec.name`。这样日志跟 spec/state 同目录（store 已 mkdir），与 plist_label 的 home 位置一致。

### K-P1-2: launchd 默认 PATH 不含 Homebrew（**kimi 独家发现，pi 漏**）

**问题**：launchd 进程默认 PATH = `/usr/bin:/bin:/usr/sbin:/sbin`，**不含 `/opt/homebrew/bin` 或 `~/.local/bin`**。但默认 `vibe_prefix = "uv run vibe"`，`uv` 通常装在 Homebrew 或 cargo 路径。`uv` 找不到 → 每次 tick 失败。

**后果**：在大多数 Mac（Homebrew uv）上 launchd tick 直接坏。`VIBESOP_RUN_PREFIX` 可以绕，但 default broken = P1。

**修法**：`install_launchd` 在用户没传 `--vibe-prefix` 时，用 `shutil.which("uv")` 解析绝对路径。解析不到则保留 `uv` 并 warn。`render_plist` 不变（接 prefix 字符串）。

### P-P1-1 (pi N1): FileNotFoundError 未捕获

**问题**：`_bootstrap_launchd` / `_bootout_launchd` 直接 `subprocess.run(...)`，未 try/except `FileNotFoundError`。launchctl 不在 PATH（容器化、PATH 损坏）时 traceback 而非友好提示。

**修法**：两个 `subprocess.run` 外加 `try/except FileNotFoundError`，console 打印友好错误，return False。

## P2 defer 项（Phase D 起步时优先）

| # | 来源 | 描述 | 处理 |
|---|------|------|------|
| D-1 | pi N2 | refresh 路径 re-bootstrap 失败时 plist 被 unlink → 用户失去注册 | Phase D 改为 refresh 失败保留 plist + 打印手动恢复指令 |
| D-2 | pi N3 / kimi | stderr "already bootstrapped" 字符串 fallback 在非英语 locale 失效 | kimi 指出 launchd daemon 字符串实际不本地化（low risk）；Phase D 改为 `launchctl print gui/<uid>/<label>` 前置查询更稳 |
| D-3 | pi N4 | 缺 refresh 失败路径测试（bootout 失败 / re-bootstrap 失败） | Phase D 补两个回归测试 |
| D-4 | kimi | 同分钟 double execution（manual tick + launchd tick sequential） | tick 加 `last_run_at` 分钟级 dedup；Phase D 处理（pre-existing，launchd 放大） |
| D-5 | kimi | plist write 非 atomic（write_bytes direct） | Phase D 改用 `atomic_writer.write_bytes` |
| D-6 | kimi | subprocess.run 无 timeout | Phase D 加 timeout=30 |
| D-7 | kimi | Day+Weekday AND/OR 语义（POSIX OR vs launchd）| 已被前序对抗 review 验证为 OR 一致；low-confidence note，不改 |

## Phase C 落地（基于评审）

| 改动 | 来源 | 状态 |
|------|------|------|
| `launchd.py` cron→plist 转换器 + bootstrap/bootout 命令 | plan v2 §5c | ✅ |
| `loop_cmd.py` install-launchd / uninstall-launchd + 改 delete | plan v2 §5c | ✅ |
| 对抗 FLAW #1: bootstrap 失败清 plist | 对抗 review | ✅ |
| 对抗 FLAW #2: refresh 路径（bootout→bootstrap） | 对抗 review | ✅ |
| 对抗 FLAW #3: warning 用 loop_name 而非 plist_path.stem | 对抗 review | ✅ |
| 对抗 FLAW #4: shlex ValueError 不 fallback | 对抗 review | ✅ |
| 对抗 FLAW #5: delete bootout 失败保留 plist + warn | 对抗 review | ✅ |
| **K-P1-1 修：log 路径改用 `Path.home()/.vibe/loops/<name>/`** | kimi | ✅ |
| **K-P1-2 修：install-launchd 用 `shutil.which` 解析 uv 绝对路径** | kimi | ✅ |
| **P-P1-1 修：FileNotFoundError try/except** | pi | ✅ |

## Phase D 待办（来自本次评审）

- [ ] `vibe instinct auto-promote`（plan §5d）
- [ ] `vibe instinct feedback-collect`（plan §5e）
- [ ] `vibe loop create --command` flag（plan §5a，解开 Q5）
- [ ] D-1 ~ D-6 P2 修复（见上表）
- [ ] `--preset instinct-{assemble,promote,feedback}` 快捷方式（plan §5a + §7）

## Phase C 资产

- `src/vibesop/core/loop/launchd.py` — plist 生成（log 路径已修）
- `src/vibesop/cli/commands/loop_cmd.py` — install/uninstall/delete（uv 绝对路径 + FileNotFoundError 已修）
- `tests/core/loop/test_launchd.py` — 32 + 新增 log-path-via-home 测试
- `tests/cli/test_loop_cmd.py` — Phase C tests + 新增 uv-resolve + FileNotFoundError 测试
- `docs/decisions/_review-instinct-loop-phase-c-brief.md` — brief
- `docs/decisions/_review-instinct-loop-phase-c-kimi.md` — kimi 部分 review（quota 中断）
- `docs/decisions/_review-instinct-loop-phase-c-pi.md` — pi 完整 review
- `docs/decisions/_review-instinct-loop-phase-c-merged.md` — 本文

## Reviewer limitations

**kimi**：撞月度配额（403），输出在 844 行处中断。分析部分完整，但未产出正式 verdict 表。Phase D/E 评审需用 pi 主力 + 自对抗补位，或等 kimi 配额刷新。

## Review sessions

- kimi: 配额中断，无 session id（`/Users/huchen/.kimi-code/logs/kimi-code.log`）
- pi: 通过 `pi -p` 一次性评审（无 session id）
