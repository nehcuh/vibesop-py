# VibeSOP Project Status

> 核对日期：2026-09-14。本文区分源码状态、公开发行和研究进度；不以历史测试记录宣称整个工作区已验收。

## 项目定位

VibeSOP 是**围绕可靠 AI 辅助开发的工程工具与实证研究项目**。SkillOS 描述技能管理子系统；当前仓库还包含任务计划与验证交付、执行观测、经验检索、定时任务及相关实验。定位依据与边界见 [POSITIONING.md](POSITIONING.md)。

## 版本事实

| 对象 | 已核对状态 | 依据 |
|---|---|---|
| 当前源码版本 | **8.4.0** | [pyproject.toml](../pyproject.toml)；[uv.lock](../uv.lock)；本机 `uv run vibe --version` |
| 当前包元数据 | **8.4.0** | 本分支 release commit；公开发行 tag/publish 尚未完成 |
| 当前 PyPI 发行 | **8.3.0** | [PyPI 元数据](https://pypi.org/pypi/vibesop/json)；8.4.0 待后续 publish |
| 当前 GitHub Release | 8.3.0 | [GitHub Releases](https://github.com/nehcuh/vibesop-py/releases)；8.4.0 待后续 tag |
| 上一公开版本 | **8.3.0**，2026-09-14 发布 | [CHANGELOG](../CHANGELOG.md) |
| 8.3.1 修复记录 | 源码提交与 CHANGELOG 中的内部修复批次标签 | [CHANGELOG](../CHANGELOG.md)，包括计划拒绝态、交付路径和跨平台修复；属于 8.3.0，不是独立软件包版本 |
| SKILL.md 规范 | v3.0，独立协议版本 | [格式规范](skill-format-spec-v3.md) |
| 本分支 | **8.4.0 Trust & Evidence** | 分支 `codex/v84-trust-evidence`；观测工具与必选 CI 治理已进入源码与 changelog。切片、数字与后续闸见 [ROADMAP.md](ROADMAP.md) |

当前**源码与包元数据是 8.4.0**。公开发行（PyPI / GitHub Release）在 tag 与 publish 完成前仍是 8.3.0。8.4.0 增加双向路由评测、near_miss 负例、生产 no-match 聚合、CI `decision_source` 注册表，以及产物引用守卫。8.3.0 汇总了验证器与计划交付合同、路由与阻断行为、跨平台修复，以及项目定位和研究资料结构；内部“8.3.1 修复批次”属于 8.3.0 发行范围。

## 工程能力与验证边界

| 范围 | 当前源码情况 | 不据此推断 |
|---|---|---|
| 技能与平台 | 技能发现/安装/作用域/路由/生命周期；多个代理的配置适配 | 所有平台具有相同 hook 或工具执行语义 |
| 计划与交付 | 计划跟踪、验证器选择、可用性和内容安全阻断；[合同](architecture/verification-contract.md) | 生成计划就已执行；模型声称通过就可发布 |
| 观测与经验 | trace、回放、聚类、recall、反馈与项目 pool | 记忆量增加必然提高任务成功率 |
| 持续任务 | loop 存储、调度及显式执行路径 | 任意任务均能无需监督地安全完成 |
| 8.3.0 文档与发行 | 同步定位、发行说明、入口文档与 CLI 介绍 | 未完成研究自动成为已发行产品能力 |
| 8.4.0 Trust & Evidence | 双向路由评测、near_miss 负例、no-match 聚合、decision_source 注册表、全量 tracked markdown 产物引用守卫（1109 refs / 0 dangling / 468 stale occurrences across 460 keys）；详见路线图 | 源码已升版本即 PyPI 已发布；评测数字即可靠性证明 |

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
