---
name: vibesop-overview
description: VibeSOP 项目总览 — 可靠 AI 辅助开发的工程工具与实证研究，能力和发行边界
type: domain_knowledge
tags:
  - vibesop
  - overview
  - skillos
  - workflow
  - research
---

# VibeSOP 项目总览

## 当前定位

**VibeSOP 是围绕可靠 AI 辅助开发的工程工具与实证研究项目。** SkillOS 描述技能发现、安装、路由和生命周期子系统；仓库还包含任务计划与验证交付、观测和经验检索、定时执行，以及相应对照实验。

定位来源：[docs/POSITIONING.md](../../docs/POSITIONING.md)。不能将模块存在解释成通用自动开发流水线已经完成或已证明有效。

## 版本与状态（2026-09-14 核对）

- PyPI 包名 `vibesop`，CLI `vibe`，Python 3.12+，MIT。
- 当前源码与包元数据 **8.4.0**；最新公开 PyPI / GitHub Release **8.3.0**（8.4.0 待后续 tag/publish）。
- 提交中的 8.3.1 是内部修复批次名称，不代表实际发行。
- SKILL.md v3.0 是技能格式版本；固定角色委员会 v2 是研究协议版本，均不等于软件包版本。
- 最新说明与发布依据见[项目状态](../../docs/PROJECT_STATUS.md)。

## 能力及代码位置

| 范围 | 代码 |
|---|---|
| 技能和平台 | `src/vibesop/core/skills/`、`installer/`、`adapters/` |
| 技能选择 | `src/vibesop/core/routing/`；no-match 是正常结果 |
| 任务计划和交付 | `src/vibesop/core/orchestration/`、`agent/runtime/` |
| 执行记录与经验 | `src/vibesop/core/observability/`、`core/instinct/`、`cli/commands/recall_cmd.py` |
| 持续任务 | `src/vibesop/core/loop/` |
| 实证研究 | `docs/research/`、`docs/experiments/`；本地原始数据与 wheel 分开 |

## 使用边界

hook 把上下文交给宿主代理；Runtime、loop、验证工具还有各自显式执行路径。配置生成与端到端验证不是同一层能力。

检索和反馈机制不保证越用越准；模型评审不独自承担放行权；未完成实验与未合并分支不描述为已发行能力。历史准确率、QPS、测试数量和 CI 结果必须带测量出处与时间，不能当作当前全局保证。

## 更多入口

- [中英文 README](../../README.md)：安装、平台与当前能力。
- [架构导览](../../docs/dev/architecture-overview.md)：模块与执行边界。
- [研究索引](../../docs/research/README.md)、[实验登记册](../../docs/experiments/README.md)：发现与证据。
- [CHANGELOG](../../CHANGELOG.md)：源码变更与发行历史。
