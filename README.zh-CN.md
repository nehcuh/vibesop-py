# VibeSOP

> **围绕可靠 AI 辅助开发的工程工具与实证研究。**
>
> [English](README.md) · [文档总索引](docs/INDEX.md) · [项目状态](docs/PROJECT_STATUS.md) · [研究](docs/research/README.md)

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](pyproject.toml)
[![Version](https://img.shields.io/badge/Version-8.4.1-blue.svg)](https://github.com/nehcuh/vibesop-py/releases/tag/v8.4.1)
[![PyPI](https://img.shields.io/pypi/v/vibesop.svg)](https://pypi.org/project/vibesop/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

VibeSOP 提供跨代理的技能选择、任务计划、交付检查、执行证据记录和历史经验检索工具。这个仓库也通过实验研究：技能、规格、编排、评审与记忆何时改善工作，何时只是增加成本。

**SkillOS 继续描述技能管理子系统。** 整个项目还包含工作流工程与实证研究。“可靠”是目标；拥有这些模块不等于全过程已经自动接通，也不等于一条通用自动开发流水线已被证明有效。详见[项目定位](docs/POSITIONING.md)。

## 版本与可用范围

| 对象 | 状态 |
|---|---|
| 当前源码与包元数据 | **8.4.1** |
| 上一公开版本 | **8.4.0**，发布于 2026-09-14 |
| 提交与日志中的 8.3.1 | 内部修复批次标签；尚不存在 8.3.1 公开发行 |
| 技能格式 | SKILL.md v3.0，与软件包版本独立 |
| 固定角色委员会 v2 | 尚未完成的研究，与安装包分开 |

下文能力描述针对本次发行。本地实验数据不属于安装包。[项目状态](docs/PROJECT_STATUS.md)列出版本依据与发布边界。

## 能做什么

| 需求 | 当前源码中的工具 | 边界 |
|---|---|---|
| 选择和维护技能 | `vibe route`、技能安装、作用域与生命周期管理 | no-match 是正常结果，不要求每个任务都注入技能 |
| 计划工作与检查交付 | 执行计划、依赖跟踪、验证器选择、不可交付计划阻断 | 生成计划或模型说“通过”不代表任务完成 |
| 看清实际发生了什么 | trace、回放、观测与机器验收凭据 | 证据必须对应被评价的那次执行 |
| 检索过往经验 | `vibe recall`、反馈、聚类与跨项目 pool | 已实现检索，不承诺越用必然越准 |
| 持续执行约定任务 | `vibe loop` 与调度器集成 | 实际行为取决于执行器、调度配置和环境 |
| 检验工程方法 | 研究报告、协议、对照实验和证据清单 | 实验分支与研究结果不自动成为已发行功能 |

hook 路径把技能上下文交给宿主编程代理；Runtime、loop 和验证工具各有显式执行路径。平台配置生成、hook 支持和端到端验证需要分别检查，见[集成指南](docs/agent-integration.md)。

## 快速开始

需要 Python **3.12+**。使用 uv 安装公开版本：

```sh
uv tool install vibesop
vibe --version
vibe quickstart
```

路由演示走本地轻量路径；LLM 增强路由需要配置提供商。使用前核对选中的技能与计划。

从源码开发或使用：

```sh
git clone https://github.com/nehcuh/vibesop-py.git
cd vibesop-py
uv sync --extra dev
uv run vibe --version
uv run vibe quickstart
```

在源码目录里，用 `uv run vibe` 替代下文的 `vibe`，避免误调用旧的全局安装包。

## 平台集成

为使用的代理生成配置，然后重启该代理：

| 代理 | 命令 |
|---|---|
| Claude Code | `vibe build claude-code --output ~/.claude` |
| Grok Build | `vibe build grok-build --output ~/.grok` |
| Kimi CLI | `vibe build kimi-cli --output ~/.kimi-code` |
| Pi | `vibe build pi --output .pi` |
| OpenCode | `vibe build opencode --output ~/.config/opencode` |
| Cursor | `vibe build cursor --output ~/.cursor` |

这些是配置生成目标，不代表各平台运行行为完全相同。使用 `vibe doctor` 和对应平台文档检查本机环境。

## 配置 LLM API

CLI 子进程需要配置支持的提供商，例如：

```sh
export ANTHROPIC_API_KEY="your-key"
vibe route "帮我调试代码"
```

进程内集成可以通过 `AgentRouter.set_llm()` 提供宿主 LLM。提供商选项和平台设置见[配置指南](docs/SKILL_LLM_CONFIG_GUIDE.md)与[Agent 集成指南](docs/agent-integration.md)。

## 工作流示例

```sh
vibe route "帮我调试代码"
vibe plan list
vibe recall "合并配置时丢失用户 hooks"
vibe loop list
vibe doctor
```

`recall` 需要已有 trace 和相应 embedding 依赖。跨项目检索需要显式使用 `--cross-project`，并有可用的项目 pool。被阻断的计划应先解决报告中的问题，不能当作已完成或可执行计划。详见[验证交付合同](docs/architecture/verification-contract.md)。

完整命令与实际场景见 [CLI 参考](docs/user/CLI_REFERENCE.md)、[命令手册](docs/user/COMMAND_HANDBOOK.md)和[使用场景](docs/USE_CASES.md)。

## 研究与工程原则

我们的实验关注规格、技能、模型与运行环境之间的关系；更多评审者或固定专家角色是否值得其成本；以及储存经验能否改善后续工作。

- [研究索引](docs/research/README.md)：发现、来源与适用范围。
- [实验登记册](docs/experiments/README.md)：已结算批次与尚未完成的 v2 研究。
- [研究综述](docs/research/research-survey.md)：更完整的证据记录。
- [工程方法论](docs/enterprise-agent-methodology.md)：将已测零件与未整机验证的假设分开。
- [文章集](docs/essays/README.md)：面向更广泛读者的解释。

技能按需选择，先定义验收标准，保留失败和中断记录，将模型评审与实际执行证据分开。不能仅凭技能更多、代理更多、trace 更多就推断普遍收益；报告中的结果需要同时交代数据集、模型、预算与测量条件。

部分原始 runs 保存在带校验清单的本地冷归档中，**不随 Git 克隆或 wheel 分发**。各实验的 evidence manifest 说明位置和恢复要求。研究协议与软件包各自维护版本。

## 开发

```sh
uv sync --extra dev
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run basedpyright --level error
uv run pytest
```

列出测试命令不代表当前工作区已通过这些检查。每次改动或报告应记录实际验证范围和时间。

开发入口：[架构导览](docs/dev/architecture-overview.md)、[贡献指南](CONTRIBUTING.md)与[当前路线图](docs/ROADMAP.md)。下次发行需要核对源码变更、迁移说明和发布检查；定位文案更新本身不触发版本升级。

## 文档与项目历史

[文档总索引](docs/INDEX.md) · [项目状态](docs/PROJECT_STATUS.md) · [设计原则](docs/PHILOSOPHY.md) · [变更日志](CHANGELOG.md) · [历史评审](docs/archive/reviews/README.md) · [工作目录恢复](docs/maintenance/README.md)

## 许可与致谢

[MIT](LICENSE)。VibeSOP 集成 [superpowers](https://github.com/obra/superpowers)、[oh-my-codex](https://github.com/Yeachan-Heo/oh-my-codex) 等社区技能生态及其他可安装技能包。技能和宿主代理保留各自的作者归属、许可与运行要求。

问题反馈与讨论见 [GitHub](https://github.com/nehcuh/vibesop-py)。
