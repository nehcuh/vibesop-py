# Project Context

## Current project scope — 2026-10-22

VibeSOP 是多代理 AI 工程工作流系统：把请求路由到合适的技能或代理，按明确标准验证交付，并记录可观测的执行证据；围绕主线还提供技能选择、发布放行的治理，以及跨代理的经验/知识积累。SkillOS 是技能管理子系统；任务计划与验证交付、执行观测、经验检索、定时任务和实验研究共同构成当前仓库。

- 定位依据与边界：[docs/POSITIONING.md](docs/POSITIONING.md)。
- 源码与包元数据为 **8.6.0**（2026-10-22）。PyPI 与 GitHub Release 由 tag `v8.6.0` 的 Release workflow 发布。8.5.0 仍是上一公开版本，其只读 `vibe observe routing` 观测器保持不变，见[项目状态](docs/PROJECT_STATUS.md)。
- 工程主线继续验证选择和交付的可信性；未合并 evo 分支和未完成固定角色实验不算已发行能力。
- 旧 worktree 已归档，当前保留主目录与 `.experiment/worktree`。原始数据和未提交成果的恢复见[维护索引](docs/maintenance/README.md)。

## Historical session handoff

以下为当时的交接记录，日期相关的 Next Steps 不自动代表当前待办；涉及保留实验容器和证据的约束继续有效。

<!-- handoff:start -->
### 2026-10-22 S101 END · 8.6.1 发版未开工

**Workspace**：main @ `06f2a45b`，超前 origin 1（S100 session，未推）。tag `v8.6.0` = `c88caada`，不要移动。PyPI 仍是 8.6.0。未入库：`.pi/`、`Makefile`、`.grok/hooks/`、pptx。

**完成**：用户要求标准发版，收工前只做了调查。下一版定为 **8.6.1 patch**（Unreleased 只有界内依赖，无行为面变化）。[executed] CI 39736145997 job 级全绿，含 Windows 3.12/3.13。未改 `pyproject.toml`，未打 tag，未 push。

**Next**：按 standard-release 切 8.6.1。CHANGELOG 半开区间；历史 8.6.0 证据留下；session/memory 不混进 release commit。

### 2026-10-22 S100 END · 8.6.0 已发布，Dependabot 收口

**Workspace**：当时 main @ `34ad78a0`。tag `v8.6.0` = `c88caada`。PyPI 8.6.0。

**完成**：正式发布 8.6.0（Release 39727715512，E2E 39727710603）。Dependabot 收成 `44722385` 与 `34ad78a0`。Anthropic 维持 `<1.0.0`。NumPy 下限维持 `>=1.26.0`。

**Next**：已被 S101 取代。CI 39736145997 现已 job 级全绿。用户随后要求把 Unreleased 依赖发成新版本。

<!-- handoff:end -->

