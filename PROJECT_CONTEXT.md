# Project Context

## Current project scope — 2026-09-14

VibeSOP 是围绕可靠 AI 辅助开发的工程工具与实证研究项目。SkillOS 是技能管理子系统；任务计划与验证交付、执行观测、经验检索、定时任务和实验研究共同构成当前仓库。

- 定位依据与边界：[docs/POSITIONING.md](docs/POSITIONING.md)。
- 源码元数据为 **8.3.0**；截至核对日，公开 PyPI / GitHub Release 最新为 **8.2.0**。内部 8.3.1 修复标签不等于发行，见[项目状态](docs/PROJECT_STATUS.md)。
- 工程主线继续验证选择和交付的可信性；未合并 evo 分支和未完成固定角色实验不算已发行能力。
- 旧 worktree 已归档，当前保留主目录与 `.experiment/worktree`。原始数据和未提交成果的恢复见[维护索引](docs/maintenance/README.md)。
- 当前文档与整理改动尚未提交或推送；源码版本未因定位更新而递增。

## Historical session handoff

以下为当时的交接记录，日期相关的 Next Steps 不自动代表当前待办；涉及保留实验容器和证据的约束继续有效。

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
