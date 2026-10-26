# Project Context

## Current project scope — 2026-10-26

VibeSOP 是多代理 AI 工程工作流系统：把请求路由到合适的技能或代理，按明确标准验证交付，并记录可观测的执行证据；围绕主线还提供技能选择、发布放行的治理，以及跨代理的经验/知识积累。SkillOS 是技能管理子系统；任务计划与验证交付、执行观测、经验检索、定时任务和实验研究共同构成当前仓库。

- 定位依据与边界：[docs/POSITIONING.md](docs/POSITIONING.md)。
- 源码与包元数据为 **8.6.1**（2026-10-26）。PyPI 与 GitHub Release 由 tag `v8.6.1` 的 Release workflow 发布。8.6.0 仍是上一公开版本，见[项目状态](docs/PROJECT_STATUS.md)。
- 工程主线继续验证选择和交付的可信性；未合并 evo 分支和未完成固定角色实验不算已发行能力。
- 旧 worktree 已归档，当前保留主目录与 `.experiment/worktree`。原始数据和未提交成果的恢复见[维护索引](docs/maintenance/README.md)。

## Historical session handoff

以下为当时的交接记录，日期相关的 Next Steps 不自动代表当前待办；涉及保留实验容器和证据的约束继续有效。

<!-- handoff:start -->
### 2026-10-26 S102 END · 8.6.1 已切版已 push，CI 红四根因已修，3 提交待推、tag 未打

**Workspace**：main @ `a1069631`，超前 origin 3：`2cd5d80a`（setup-uv pin 笔误修正）、`08c898db`（filelock 3.29.7→4.2.4，清 CVE-2026-112907/112913/112940）、`a1069631`（42 处单机链接去链接化 + artifact-links baseline 干净再生）。版本面 8.6.1 已随 `9a583849` 由用户 push；agent 推 main 受权限边界限制，待推提交由用户执行 `git push origin main`。8.6.0 的发布 tag 仍指 `c88caada`，不要移动。未入库：`.pi/`、`.grok/hooks/`、pptx。

**完成**：Kimi 多路对抗复审 DeepSeek 4 commits（确认 5/驳回 5/0 未证）+ 修复 4 commits；8.6.1 标准切版（CHANGELOG 8.6.1 段含全部修复条目）；push 后 CI run 40273955136 红诊断出 4 独立根因并全部修复。本地验证：干净 worktree（`/tmp/vibesop-ci-sim`，脏、可 `git worktree remove --force` 后重建）两 checker PASS、新 27 测试过、pip-audit exit=0。

**Next**：push 待推提交 → `gh run watch` job 级验证 14 job 全绿 → `git tag -a v8.6.1 -m "VibeSOP v8.6.1"` + push tag → Release workflow → 验 PyPI 8.6.1 + GitHub Release + attestation。备查三项：`docs/dev/releasing.md` 称版本由 hatch-vcs 生成与实际（pyproject 静态版本）不符；`check_doc_versions --fix` 不覆盖 `(current: vX.Y.Z+)` 形态；Dependabot #174-180 未收。

### 2026-10-22 S101 END · 8.6.1 发版未开工

**Workspace**：main @ `06f2a45b`，超前 origin 1（S100 session，未推）。8.6.0 的发布 tag 指向 `c88caada`，不要移动。PyPI 仍是 8.6.0。未入库：`.pi/`、`Makefile`、`.grok/hooks/`、pptx。

**完成**：用户要求标准发版，收工前只做了调查。下一版定为 **8.6.1 patch**（Unreleased 只有界内依赖，无行为面变化）。[executed] CI 39736145997 job 级全绿，含 Windows 3.12/3.13。未改 `pyproject.toml`，未打 tag，未 push。

**Next**：已被 S102 执行：8.6.1 已切版，剩 push 修复 + tag + 发布验证。

<!-- handoff:end -->

