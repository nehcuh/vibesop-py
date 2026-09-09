# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-09-07 S75 [vibesop-py] 喷气机 R5/R6 预览恢复 + 起停备忘

**Session Summary**:
- 主机 `/tmp/ab-jet-out` 已被清。R5 grok 双臂从容器 grok 会话 `rewind_points.jsonl` 的 `after_snapshots` 还原（treatment 8 文件/1987 行，control 9 文件/2491 行，对上 R5 报告）；R6 27B 仍在 `vibesop-ab-treat:/work`。
- 用户截图后要求停服务。8801–8803 与 `vibesop-ab-{treat,ctrl,base}` 已 `docker stop`（未 rm）。
- 静态缓存 `.vibe/experiments/ab-jet-preview/`（gitignored）；再起：`./scripts/ab-jet-preview.sh start`。备忘 `.omx/artifacts/ab-jet-preview.md`。

**Key Decisions**:
- 实验产物不要放 `/tmp`；容器可写层 + grok after_snapshots 才是源。禁止 `docker rm` 那三个 ab 容器。
- 预览默认只绑 127.0.0.1；R7/R8 量化台端口 8811+ 不要混。

**Next Steps**:
1. 人评分数仍待用户；再看 `./scripts/ab-jet-preview.sh start`
2. Dependabot 9 PR（#102-114）非 major 批量合
3. gate43 T+14 到期日即今日，cron one-shot 勿在本 session 提前跑

### 2026-09-07 S70 [vibesop-py] CLI help/man 三入口 + -h 全树支持（已 push CI 全绿）

**Session Summary**:
- Ship：`vibe -h`/`--help`/`vibe help [COMMAND...]` 三入口 + `vibe man [COMMAND...]`（`--roff`）。root Typer 全树继承 `-h`；dashboard/skills feedback 已占用 `-h` 则只留 `--help`。
- 3 commits 已 push（`987cf95` + `7cf81fc` + `67d14c4`）；CI 10/10 + E2E + CodeQL 绿。

**Key Decisions**:
- Typer≥0.26 vendored `typer._click` 不是 click 子类——反射一律 duck typing

**Next Steps**:
1. 本机 `uv tool install --reinstall --force .` 后 dogfood help/man
<!-- handoff:end -->
