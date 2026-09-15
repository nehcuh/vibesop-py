# VibeSOP Project Status

> 核对日期：2026-09-15。本文区分源码状态、公开发行和研究进度；不以历史测试记录宣称整个工作区已验收。

## 项目定位

VibeSOP 是**多代理 AI 工程工作流**系统：把请求路由到合适的技能或代理，按明确标准验证交付，并记录可观测的执行证据；围绕主线还提供技能选择、发布放行的治理，以及跨代理的经验/知识积累。SkillOS 描述技能管理子系统，不是整个项目。当前仓库还包含任务计划与验证交付、执行观测、经验检索、定时任务及相关实验。定位依据与边界见 [POSITIONING.md](POSITIONING.md)。

## 版本事实

| 对象 | 已核对状态 | 依据 |
|---|---|---|
| 当前源码版本 | **8.5.0** | [pyproject.toml](../pyproject.toml)；[uv.lock](../uv.lock)；本机 `uv run vibe --version` |
| 当前包元数据 | **8.5.0** | wheel/sdist 均由 tag `v8.5.0` 的 Release workflow 构建 |
| 当前 PyPI 发行 | **8.5.0** | [PyPI 项目](https://pypi.org/project/vibesop/8.5.0/) |
| 当前 GitHub Release | **8.5.0** | [GitHub Release v8.5.0](https://github.com/nehcuh/vibesop-py/releases/tag/v8.5.0) |
| 上一公开版本 | **8.4.1**，2026-09-15 发布 | [CHANGELOG](../CHANGELOG.md) |
| 8.3.1 修复记录 | 源码提交与 CHANGELOG 中的内部修复批次标签 | [CHANGELOG](../CHANGELOG.md)，包括计划拒绝态、交付路径和跨平台修复；属于 8.3.0，不是独立软件包版本 |
| SKILL.md 规范 | v3.0，独立协议版本 | [格式规范](skill-format-spec-v3.md) |
| 8.5.0 发布依据 | **已完成** | [PR #124](https://github.com/nehcuh/vibesop-py/pull/124)；merge `fb16f19b`；tag `v8.5.0`；[Release workflow](https://github.com/nehcuh/vibesop-py/actions/runs/34922545572) |

当前**源码、包元数据、PyPI 与 GitHub Release 均为 8.5.0**。8.5.0 新增只读的在线路由证据观测器（`vibe observe routing`，`vibesop.observe.routing` v1，覆盖 no_match / near_miss / decision_source）以及 eval provenance fail-closed 校验；它不写路由注册表、评测集或阈值。8.4.1 是针对 8.4.0 CI 矩阵解释器、热路径基准标记、Release 产物 glob，以及 Python 3.13 符号链接环 fail-closed 的补丁。8.4.0 增加双向路由评测、near_miss 负例、生产 no-match 聚合、CI `decision_source` 注册表，以及产物引用守卫。8.3.0 汇总了验证器与计划交付合同、路由与阻断行为、跨平台修复，以及项目定位和研究资料结构；内部“8.3.1 修复批次”属于 8.3.0 发行范围。

公开产物已交叉核验：PyPI 与 GitHub Release 的 wheel SHA-256 均为 `252a5e64c37d43693bb1218a85e480b8f287c0914d0153b41212bfb286ba7b0f`，sdist SHA-256 均为 `c326fcbdf84564171fa5c3c295814b979fb66d3c2375a24a3bec88e5fee4c996`；两个制品均通过 GitHub build provenance 验证。从 PyPI 隔离安装后，`vibe --version` 返回 `VibeSOP v8.5.0`，`vibe observe routing --help` 正常加载。

## 工程能力与验证边界

| 范围 | 当前源码情况 | 不据此推断 |
|---|---|---|
| 技能与平台 | 技能发现/安装/作用域/路由/生命周期；多个代理的配置适配 | 所有平台具有相同 hook 或工具执行语义 |
| 计划与交付 | 计划跟踪、验证器选择、可用性和内容安全阻断；[合同](architecture/verification-contract.md) | 生成计划就已执行；模型声称通过就可发布 |
| 观测与经验 | trace、回放、聚类、recall、反馈与项目 pool | 记忆量增加必然提高任务成功率 |
| 持续任务 | loop 存储、调度及显式执行路径 | 任意任务均能无需监督地安全完成 |
| 8.3.0 文档与发行 | 同步定位、发行说明、入口文档与 CLI 介绍 | 未完成研究自动成为已发行产品能力 |
| 8.4.0 Trust & Evidence | 双向路由评测、near_miss 负例、no-match 聚合、decision_source 注册表、全量 tracked markdown 产物引用守卫（1109 refs / 0 dangling / 468 stale occurrences across 460 keys）；详见路线图 | 源码已升版本即 PyPI 已发布；评测数字即可靠性证明 |
| 8.5.0 online routing evidence（已发行） | 只读观测器 `vibe observe routing` + `vibesop.observe.routing` v1：半开窗口与 project 过滤、覆盖率/最小样本闸、Wilson 区间、decision-source 层分类、可选 hermetic eval provenance 校验、严格退出码；`scripts/aggregate_nomatch.py` 保持 8.4.0 兼容；无策略写入。指标口径与运维步骤见 [runbook](observe-routing.md) | 该命令不自动修改路由策略、评测集或阈值 |

历史测试结果保留在对应变更、验收凭据和研究报告中。当前可信度应按具体功能、执行路径与最近实际验证判断，不再使用“全部计划完成”“全项目 production-ready”作为总括。

## 研究状态

- 研究综述覆盖既有技能/规格/harness、路由、评审与学习闭环记录，见[研究索引](research/README.md)。它是有时间边界的证据汇总。
- 旧多专家主实验与敏感性队列已结算；固定角色委员会 v2 尚未完成。当前登记与后续记录见[实验索引](experiments/README.md)。
- evo 优化提交仍保留在分支中；未完成的固定角色实验保留单独 worktree。不能将这些成果直接描述为主线或 PyPI 已发行能力。
- 2026-09-14 已归档退役 26 个旧工作目录；研究原始数据有校验清单和恢复方法，见[清理结果](maintenance/cleanup-result-2026-09-14.md)。

## 接下来

1. 持续保持源码、包元数据、tag 与发行记录一致。
2. 优先验证技能选择、no-match 和计划交付的可信性；保持失败、缺证据、通过状态可区分。
3. 未完研究按各自协议收口，保留旧/新冻结版本和原始失败记录。
4. 评估记忆、规格和多代理方法的适用条件，达到证据要求后再决定产品化。

具体研发优先级见 [ROADMAP.md](ROADMAP.md)，文档入口见 [INDEX.md](INDEX.md)。
