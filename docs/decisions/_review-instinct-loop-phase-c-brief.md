# Phase C Milestone — Review Brief

**Date:** 2026-07-23
**Scope:** launchd plist 生成 + `vibe loop install/uninstall-launchd` CLI + `delete` 自动清 plist
**Plan v2:** `/Users/huchen/.claude/plans/starry-herding-stream.md` §5c
**Phase A merged:** `fdafbcb` | **Phase B merged:** `953df2b`
**Phase C diff:** ~1094 行（launchd.py + test_launchd.py 新建；loop_cmd.py + test_loop_cmd.py 改动）
**Verification:** 4528 passed / 13 skipped（含两个 pre-existing test_trace_replay 失败，与 Phase C 无关），ruff clean，basedpyright 0 errors

## What Phase C changes

### `src/vibesop/core/loop/launchd.py` (NEW, 237 行)

Cron → launchd plist 转换器：

- `cron_to_start_interval_seconds(cron_str) -> int | None`：检测 `*/N * * * *`（N 必须整除 60），返回 N×60
- `cron_to_start_calendar(cron) -> dict | None`：解析后的 CronExpr → launchd StartCalendarInterval dict（wildcard 字段省略，launchd 默认 wildcard）
- `schedule_for_cron(cron_str) -> LaunchdSchedule`：先试 StartInterval（simple），否则回退 StartCalendarInterval
- `render_plist(spec, *, project_root, vibe_prefix, ...) -> bytes`：用 `plistlib.dumps(FMT_XML)` 生成 plist。ProgramArguments = `shlex.split(prefix) + ["loop", "tick", "--name", name]`
- `bootstrap_command(plist_path) / bootout_command(loop_name) -> list[str]`：现代 launchctl（`gui/$(id -u)` 形式，E.3）

**关键设计选择**：
- plist 调用通用的 `vibe loop tick --name <NAME>`，不直接烘焙 command_args。这样同一模板适用 skill/query/workflow/command_args 四种 target，且 tick 的 PAUSED/DEAD/RETIRED 过滤照常生效。
- 用 `plistlib` 而非手写 XML：自动处理转义（路径含空格 / 特殊字符 / unicode），无 shell 注入面（ProgramArguments 是数组，launchd 不经 shell）。
- 优先 StartInterval 处理 `*/15` 等整除模式（更简单，launchd StartInterval 不需要展开成数组）。

### `src/vibesop/cli/commands/loop_cmd.py`（改动）

- 加 `import sys` / `from pathlib import Path`
- 新 `_bootstrap_launchd(plist_path, *, console, loop_name) -> bool`：现代 launchctl bootstrap，**refresh 路径**（FLAW #2 修复）——如果已注册则 bootout→bootstrap 重新加载
- 新 `_bootout_launchd(loop_name, *, console, missing_ok=False) -> bool`：现代 launchctl bootout，`missing_ok=True` 时 "Could not find" 算成功
- 新 `install-launchd NAME [--vibe-prefix X] [--dry-run]`：渲染 plist → 写盘 → bootstrap（FLAW #1 修复：bootstrap 失败清 plist；FLAW #4 修复：shlex 错误抛出）
- 新 `uninstall-launchd NAME [--keep-plist]`：bootout + 删 plist（幂等）
- 改 `delete`：检测到 plist 时先 bootout（FLAW #5 修复：bootout 失败保留 plist 作为恢复凭证 + 警告 launchd label 可能仍活跃）

### Tests

- `tests/core/loop/test_launchd.py`（NEW, 32 tests）：cron 转换、plist XML 结构、path-with-spaces、env_overrides、shell 注入防御、launchctl 命令形态
- `tests/cli/test_loop_cmd.py`（+11 tests, 共 19 个 Phase C 测试）：install dry-run / 写盘 / refresh / bootstrap 失败 / shlex 错误、uninstall bootout/keep-plist/幂等、delete 清 plist / bootout 失败保留 plist / 无 plist 不调用 launchctl

## Adversarial review (Phase C.5)

Agent (opus) verdict: **FIX BEFORE EXECUTE** → 6 flaws，5 个真 bug + 1 个 test fragility：

| # | Severity | Description | Resolution |
|---|----------|-------------|------------|
| 1 | MEDIUM | bootstrap 失败时 plist 遗留在 LaunchAgents | **Fixed**: 失败时 unlink |
| 2 | MEDIUM | "already bootstrapped" 静默成功 → refresh 时新 plist 不生效 | **Fixed**: bootout→bootstrap 自动 refresh |
| 3 | LOW | warning 消息用 `plist_path.stem`（含前缀），用户照抄会构造错误 label | **Fixed**: 改 `_bootstrap_launchd` 签名收 `loop_name` 参数 |
| 4 | LOW | shlex ValueError 静默 fallback 到空格分割，破坏路径 | **Fixed**: 抛出 ValueError，install 时报错 |
| 5 | LOW→HIGH | `delete` 忽略 bootout 失败 → 留下 zombie label + 无 plist 可恢复 | **Fixed**: bootout 失败保留 plist + 大声警告 |
| 6 | LOW | 测试用 monkeypatch `Path.home` 而非 `os.environ['HOME']`，未来重构易绕过 | **Accepted**: 当前 `launchd.py` 仅用 `Path.home`，无问题；备注 |

非 flaw 的验证项：
- CronExpr Day+Dow 都是 OR 语义（POSIX 和 launchd 一致）
- plistlib 正确处理 XML 转义
- RunAtLoad=False / KeepAlive=False 正确（不想 login 即触发 / 不想 crash 旋重启）
- `*/N` StartInterval 漂移：tick 的 per-loop lock 保证同分钟去重
- 125 退出码确实是 "already bootstrapped"

## Key questions for kimi+pi

1. **plist 调用通用 `vibe loop tick --name X`**：这意味着 paused loop 的 launchd tick 仍会触发（虽然 tick 内部会跳过）。如果用户不想 paused loop 留在 launchd，应该手动 uninstall。这个 trade-off 可接受吗？

2. **refresh 路径（bootout→bootstrap）**：现在 install-launchd 遇到 "already bootstrapped" 会自动 bootout 再 bootstrap。如果用户的 launchd 状态很乱（比如 label 已注册但 plist 路径不对），这个 refresh 会更乱吗？是否应该让用户显式 `--refresh`？

3. **`delete` 保留 plist 的语义**：bootout 失败时保留 plist 但删 spec。结果是 launchd label 可能仍活跃，每分钟对不存在的 spec 报错。是否应该改为：bootout 失败时 abort delete（让用户先修 launchd）？

4. **plist 日志路径**：`<project_root>/.vibe/loops/<name>/{out,err}.log`。这意味着如果用户从 A 目录 install，然后从 B 目录用同一个 name 创建另一个 loop，两个 loop 的日志会冲突。但 LoopSpec 是 name-unique 的（store 层校验），所以同名 loop 只能有一个。够吗？

5. **`vibe loop create` 不暴露 command_args**：当前 install-launchd 对 command_args loop 也工作（plist 调用 tick，tick 内部 dispatch），但用户没办法从 CLI 直接创建 command_args loop。这留给 Phase D。够吗？

6. **bootstrap exit 125 检测**：跨 macOS 版本是否稳定？我用 stderr "already bootstrapped" 字符串作为 fallback，但 stderr 文案可能本地化。

7. **测试覆盖**：缺什么？目前没测：
   - launchctl 不在 PATH 的情况（FileNotFoundError）
   - 同时跑 manual tick + launchd tick 的 race
   - plist XML 用 plutil 校验语法（目前只验证 plistlib.loads 能解析）

## Phase C 资产

- `src/vibesop/core/loop/launchd.py` — 新文件（237 行）
- `src/vibesop/cli/commands/loop_cmd.py` — 新增 ~150 行（install/uninstall/refresh + 改 delete）
- `tests/core/loop/test_launchd.py` — 32 tests
- `tests/cli/test_loop_cmd.py` — 11 个 Phase C tests（含 4 个 FLAW 回归测试）
- `docs/decisions/_review-instinct-loop-phase-c-brief.md` — 本 brief

## Verdict sought

- **SHIP TO PHASE D**: Phase C 正确，可以接 Phase D（vibe instinct auto-promote + feedback-collect CLI）
- **CONDITIONAL**: 列出必修项
- **REJECT**: 设计根本问题

关注重点：
- plist quoting 路径正确性（E.1）
- modern launchctl（E.3）
- refresh 路径的可靠性
- `delete` 保留 plist 语义是否符合 F-08（隐私清理）vs 可恢复性
- 任何 Phase D 的 blocker
