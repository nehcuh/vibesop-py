# VibeSOP 的项目定位

> 更新：2026-09-15。面向本仓当前源码与研究资料；发行状态单独见 [PROJECT_STATUS.md](PROJECT_STATUS.md)。

## 一句话

**VibeSOP 是围绕可靠 AI 辅助开发的多代理 AI 工程工作流与实证研究项目。**

它把请求路由到合适的技能或代理，按明确标准验证交付，记录可观测的执行证据，对什么可以放行发布进行治理，并跨代理积累经验与知识；同时通过对照实验检验技能、规格、编排、评审、治理与记忆在什么条件下有用。

English: **A multi-agent AI engineering workflow and empirical-evidence project for reliable AI-assisted development.**

“可靠”是工程目标，不能仅凭项目定位宣称已达成。“SkillOS”描述技能的发现、安装、路由、作用域和生命周期管理，是整个项目的一部分；VibeSOP 还覆盖路由、验证、观测、发布放行治理与经验/知识积累。

## 三个组成部分

| 部分 | 当前内容 | 能力边界 |
|---|---|---|
| 工程工具 | Python 包与 `vibe` CLI；平台适配；路由、计划、验证交付；执行观测与在线证据；发布放行治理；经验检索与反馈、定时任务 | 各命令、平台和执行路径分别有契约；配置生成不等于所有平台均已端到端验证 |
| 实证研究 | 技能/规格/harness 对照、路由评测、评审与学习闭环研究、多专家与固定角色实验 | 研究代码、未合并分支和本地数据不自动成为发布包能力；未完实验不充当最终结果 |
| 工程方法 | 需求和验收标准、证据记录、独立评审、失败分类、可恢复归档 | 是实践原则与待验证假设，不是已经证明有效的通用自动开发流水线 |

## 代码依据

| 能力 | 仓库依据 |
|---|---|
| 选择与管理技能 | [路由](../src/vibesop/core/routing/)、[技能](../src/vibesop/core/skills/)、[平台适配](../src/vibesop/adapters/) |
| 计划与交付 | [编排](../src/vibesop/core/orchestration/)、[Agent Runtime](../src/vibesop/agent/runtime/)、[验证交付合同](architecture/verification-contract.md) |
| 执行证据 | [观测模块](../src/vibesop/core/observability/)、[机器验收记录工具](../scripts/record_acceptance.py) |
| 发布放行治理 | [CI decision-source 注册表](../ci/decision-source.yaml)、[治理检查脚本](../scripts/check_ci_decision_source.py) |
| 经验检索与反馈 | [recall CLI](../src/vibesop/cli/commands/recall_cmd.py)、[反馈](../src/vibesop/core/feedback.py)、[Instinct](../src/vibesop/core/instinct/) |
| 持续任务 | [loop 模块](../src/vibesop/core/loop/)、[部署指南](loop-setup-guide.md) |
| 研究与证据 | [研究索引](research/README.md)、[实验登记册](experiments/README.md) |

这些模块支持同一套工作流程，但模块存在不等于从需求到交付的全过程已自动接通，更不等于其效果已被证明。

## 对外表述规则

- **技能按需选择。** no-match 是正常结果；增加技能和角色数量不作为成功指标。
- **执行有具体主体。** hook 路径把上下文交给宿主代理；Runtime、loop 和验证工具还各有显式执行路径，不能笼统说“VibeSOP 从不运行命令”，也不能说它替代全部编程代理。
- **完成需要证据。** 缺证据、执行失败和验收通过分别记录；模型评审是输入材料，不能独自承担发布放行权。
- **记忆只承诺可检索。** trace、聚类与 recall 已有实现；“使用越久越准确”或“跨项目必然产生收益”需要独立实验。
- **研究保留边界。** 当前样本、任务、模型和预算下的结果不推广成“技能总有效”“多代理总无效”等普遍定理。
- **版本不跟口号走。** 软件包版本来自 `pyproject.toml`；公开发布以 PyPI / GitHub Release 为准；技能规范版本和实验协议版本独立维护。

## 读者与入口

- 使用工具的开发者：[快速开始](QUICKSTART_USERS.md)与[命令手册](user/CLI_REFERENCE.md)。
- 集成到宿主代理的开发者：[Agent 集成](agent-integration.md)与[架构导览](dev/architecture-overview.md)。
- 评估方法是否有效的研究者：[研究综述](research/research-survey.md)与[实验登记册](experiments/README.md)。

产品近期重点仍是选择和交付的可信性、结果可追溯、研究可复验；新增默认专家组织、市场扩张或通用自动开发流水线不因这次定位更新自动进入承诺范围。优先级见 [ROADMAP.md](ROADMAP.md)。
