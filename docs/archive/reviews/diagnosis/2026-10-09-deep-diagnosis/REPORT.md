# VibeSOP 深度诊断：价值、架构、实现、创新与证据

日期：2026-10-09（Asia/Shanghai）。审查对象：8.5.0 源码，HEAD `49901afe401a3f6fd25ba33c4854ce6329e1e44c`，以及审查开始时的未提交改动。不是针对 PyPI 历史 wheel 的安全审计，也不是完整外部市场调查。

## 结论先行

**这个项目有值得继续投入的价值，但应优先兑现“跨宿主技能治理与交付证据”的窄承诺。执行状态、文件边界和经验读写的几个具体漏洞，正在削弱它所强调的可靠性。下一阶段应该修通最短闭环，再增加平台、角色或工作流类型。**

综合判断：**工程与研究基础较强，核心可靠性合同尚未闭合。** 这不是一个没有价值的技能集合，也不能由模块齐全、上千测试通过推导出已可靠的通用自治系统。当前文档已经主动区分源码、发行、研究、计划和实际执行，值得肯定；本次诊断针对当前实现，不沿用旧宣传或历史评审的结论。

本轮确认的主清单为 **15 项：8 个 P1、7 个 P2；没有确认 P0**。严重度依据可触发行为及影响，不依据模型投票。另有低曝光 helper 债务和设计语义问题，不混入主缺陷数。全部高优先级问题都有临时文件/注入执行器的具体反例；安装越界、配置密钥落盘、回放消费断链还经过独立公开入口复核。未改业务源码、未修复、未提交、未创建 PR、未合并。

## 1. 方法、范围与可信度

三个独立审查工作面分别做子系统 mapping→diagnose，之后交叉审 architecture / correctness / security / tests / ops / integration 六个视角。主控重新核准证据、收窄影响、在 arm64 Linux Docker 内复现，最终综合判断。审查覆盖 routing/LLM、skills、runtime、orchestration、verification、loop、adapters、builder、hooks、installer、packs、dashboard、integrations、instinct、recall、storage、observability、CI 与研究资料。

开始时存在用户未提交的 `.pi/docs/skills.md`、两个 Pi extension、`.pi/prompts/vibe-help.md`、`.pi/settings.json`、`Makefile`，以及未跟踪的 `.grok/hooks/` 与演示 PPTX。本轮保留这些文件；隔离副本复制跟踪文件的当前内容及 hooks，PPTX 未进入代码测试范围。源代码规模实测：337 个 Python 模块、109,693 物理行（包含注释/文档）、412 个 test 文件、23 个 builtin SKILL.md。规模不是缺陷，真正证据是不同入口出现可运行的不一致。

证据等级：

- **已执行**：确定性反例、真实 CLI/磁盘读写、Docker 回归、wheel 冷安装、部署脚本、真实 DeepSeek 调用。
- **已检查**：源码、合同、CI 配置、研究报告与统计摘要。
- **判断/建议**：产品方向、投资优先级、结构调整、研究外推边界；不包装成客户需求统计或算法首创认证。

容器不挂载用户 HOME、凭据目录或 Docker socket。测试密钥落盘仅用哑凭据；DeepSeek 通过环境传入，含密钥的临时配置只存在于最终删除的容器，导出日志替换完整密钥。Grok 用本地 CLI 自行复用登录态，未导出 auth.json。

## 2. 价值判断：应该为谁解决什么问题

| 维度 | 判断 | 依据与边界 |
| --- | --- | --- |
| 用户问题 | 多宿主、多技能源、多仓库之间的选择与约束漂移，是真实可定义的问题 | 配置生成、来源追踪、scope、no-match、阻断交付都有实现；是否产生足够付费需求仍无本次用户数据 |
| 直接价值 | 技能管理、可解释路由、保留人工显式控制，以及追踪选了什么/交付了什么 | README、routing、adapter、runtime 与真实 wheel hook 验证；不能推出宿主已读取或正确执行所有技能 |
| 可靠性价值 | 把缺技能、不安全正文、缺证据、失败和通过拆开，有明确工程意义 | verification contract 强于单纯提示词；执行 bridge 仍破坏这些状态的连贯性 |
| 经验价值 | 检索既往处理方式、展示来源、人工确认，有可用工具价值 | 未证明“记忆越多越好”；本轮发现存储覆盖和磁盘格式断链 |
| 研究价值 | 保留失败、中断、预算和限制，能纠正过度编排的直觉 | 有冻结协议及摘要；大部分技能 A/B 是 case-study，原始大数据不随 Git clone 发布 |
| 采用摩擦 | 功能广度大，用户需要理解 routing、plan、delivery、runtime、loop、recall 各自的边界 | 文档已经诚实，但让用户理解边界不应代替内部合同统一 |

最合适的早期对象是：已经使用两个以上编码宿主、维护多个技能源，并有审计或可重复交付需求的开发者/小团队。单宿主、低频简单任务用户的净收益尚需证明；增加一层配置、路由、模型调用和提示词可能只是增加操作成本。这是适用性推断，不是市场调查结论。

建议最小产品主张：**让指定技能在指定宿主中可预测地被选择和交付，并留下可核对的执行与验收证据。** 最短链应是“明确选择→实际正文交付→宿主读取→任务执行→机器验收→来源可追踪的回放”。先把一个真实仓库/一个宿主的这条链稳定做成示例，再扩展。

商业与采用判断仍缺：外部活跃用户、安装后留存、人工纠错负担、误注入/误召回率、相同预算下的任务成功与返工变化。没有这些数据，既不应宣称 PMF，也不应断言项目无人需要。

## 3. 架构：已有边界与实际裂缝

核心分层总体合理：CLI 负责组合，core 提供路由与工作流模型，adapter/builder 负责宿主投影，runtime 负责交付与执行桥接。`tests/architecture/test_layering.py` 真正扫描 core 对外层的 import；loop 已用 Protocol 注入 runtime，避免 core 直接依赖 agent。wheel 与研究仓库分开，语义观测保持 report-only，均是好的结构选择。

但依赖方向正确，不等于业务语义只有一个来源。当前主要风险是：

1. **重复状态机。** StepRunner、ParallelScheduler、WorkflowEngine、runtime guide/manifest、ExecutionProtocol 分别解释执行结果。静态路径正确处理 blocked/failed，并不能保证 squad 和 dynamic 路径也处理。D06–D08 是具体后果。
2. **缓存没有完整描述依赖。** 候选取决于技能文件与 auto-config，fingerprint 却主要追踪文件路径/mtime；loader 内缓存和候选缓存刷新不同步。D04–D05 说明“重新加载”目前不是稳定合同。
3. **写文件原语缺少调用者的根边界。** 来源内容 audit、安全路径 helper、原子写都存在，但目标 ID 拼接或先 resolve 的调用会绕开原本的保护。D01–D03 不能仅靠再加一层文本扫描解决。
4. **证据缺少动作身份与信号阶段。** feedback、用户接受回放、执行成功、机器验收还容易使用同一个 success 词。动作变更继承旧证据、stale snapshot 覆盖事实，会让“经验可靠性”失真。
5. **生产格式与内存模型之间有缝。** SpanWriter 把 payload 编码为 JSON 字符串，recall 对 skill_id 却只读 dict；这是 producer→consumer 合同问题，单组件覆盖率不容易揭示。

较大的协调文件包括 `skill_commands.py` 3,197 行、`cli/main.py` 2,577 行、`skill_promote.py` 2,357 行、`unified.py` 1,614 行、`agent_runtime.py` 1,314 行、`workflow_engine.py` 1,176 行。不要先做机械拆文件；先确定唯一的 StepOutcome、PlanOutcome、技能身份/版本与持久事件格式，再将各公开入口变成适配器。

建议结果模型至少独立表达：是否已运行、是否执行失败、是否缺证据、是否通过验收、是否需人工处理。调度“运行已结束”不能隐含“验收通过”；所有入口应共享同一终态汇总器，并保留恢复/重试的显式语义。

## 4. 创新：工程差异、研究发现与未证明假设

技能正文按需加载、路由、并行分工、orchestrator-worker、evaluator-optimizer 都已有公开标准或模式。因此这部分更适合称为工程组合与治理实现，不能由命名或工作流枚举数量推出算法首创。[Agent Skills 规范](https://agentskills.io/specification)、[Anthropic 的工作流模式说明](https://www.anthropic.com/engineering/building-effective-agents)提供了这些基础模式的官方参照；这里不是穷尽 prior art 的调查。

VibeSOP 更值得发展的是：跨宿主技能来源与控制、no-match/过拒/过灌分别观测、阻断交付合同、模型意见与机器验收分开、可回放的来源证据、保留失败与中断的实验纪律。这些机制已经有部分代码和验证，是可具体检验的差异。

现有研究不能推广为“多代理总有效/总无效”“记忆必然提高能力”：

- 多专家主实验为 360 unique runs，各组 72；敏感性队列 144=136 完成+8 中断，报告保留中断并说明 7 vs 1 不均衡。
- 单体基线 93.1% / 95.8% 时，理论最大增益只有 6.9 / 4.2 个百分点，任务集无法回答“至少提升 10pp”的正向效用假设。报告承认天花板，但下一轮需要换有足够难度余量的任务。
- 进入隐藏验收的产物通过率高，主要差异含流程终止、预算和所有权；不能将其泛化为复杂真实仓库代码质量的判决。
- 同作者设计任务、隐藏验收与 harness；改变角色组织时也改变关注面，纯角色因果效应未被分离。
- 综述明确多数技能 A/B 是 n=1/轮，并保留幸存者偏差、未标定 judge 和未结算实验的说明。
- 本轮只从已提交 supervisor/task_means 重算冻结 cluster bootstrap：点估计 -0.9305555556、区间 [-1.0,-0.8194444444] 与摘要一致。没有重跑 360 次模型实验，也没有重新核对全部冷归档原始 runs。
- v2 的 241 终态/4 缺终态/115 未启动是 09-14 文档登记，不能当 10-09 的实时运行状态。本轮未查看独立实验 worktree 的后续数据。

后续实验应把固定任务、预算与验收放在前面，使用 paired/randomized 对照检验 none/history/checklist/skill 或单体/多代理，报告任务成功、返工、误选择、误召回、人工操作和费用。路由命中率、trace 数量、委员会规模不能单独作为收益指标。

## 5. 已确认缺陷及优先级

P1：应在继续扩展相关能力前修复；P2：有限范围的可靠性、可维护性或验证缺口。每项都须用反例验收，不能由多数评审者赞同代替执行证据。

| ID | 级别 | 问题 | 源码位置 | 证据 |
| --- | --- | --- | --- | --- |
| D01 | P1 | 技能 metadata.id 可令安装写出预期根目录 | `installer/skill_installer.py:93` | 真实 `skill add` CLI，无 force、新目标、真实 audit 通过 |
| D02 | P1 | 配置生成沿已有 skill symlink 改写中央安装正文 | `adapters/base.py:373`、`:536` | 完整 Claude render；主机与容器 |
| D03 | P1 | 普通 OpenCode build 将环境密钥写入产物 | `adapters/opencode.py:166`、`:178` | 真实 build CLI，哑密钥，默认权限 0644 |
| D04 | P1 | 禁用技能未使候选缓存失效 | `core/routing/candidate_manager.py:75`、`:459` | 配置更新后热实例与新实例仍认为 enabled |
| D05 | P1 | SKILL 修改/显式 reload 后仍路由旧 metadata | `candidate_manager.py:328`、`core/skills/loader.py:140` | 临时真实 SKILL.md 修改；主机与容器 |
| D06 | P1 | fail_fast 在全成功并行批次后漏掉下游 | `agent/step_runner.py:565` | 真实 public runner，3 步只跑 2 步 |
| D07 | P1 | dynamic bridge 把失败数量硬编码为 0 | `agent/step_runner.py:384` | engine 为 failed，公开返回 failed=0 |
| D08 | P1 | squad bridge 绕开协作/评审合同并把 blocked 标完成 | `agent/step_runner.py:325`、`:348`、`:595` | 真实 public runner，blocked 输出记 completed |
| D09 | P2 | create_overlay 输出与 merger 读取的 policy schema 不一致 | `builder/overlay.py:162`、`:234` | 真实 helper→merger roundtrip 值未生效 |
| D10 | P2 | sandbox build 无法持久化正常产物，失败仍被安装视为成功 | `installer/pack_installer.py:469`、`:220`、`:267` | 正常 BUILD.sh、真实 arm64 Docker；完整链见证据 |
| D11 | P2 | stale learner 全量保存覆盖已落盘反馈 | `core/instinct/learner.py:350`、`:397` | 两实例、不同 id 也触发，计数 1→0 |
| D12 | P2 | 真实 disk span 格式使 recall 丢 skill_id | `core/observability/recall.py:400` | writer→reader→确认回放 consumer 返回 None |
| D13 | P2 | action 改变仍继承旧 action 的成功证据 | `core/instinct/learner.py:555` | 新 action 0 次验证却继承 3 次成功 |
| D14 | P2 | StepRunner 同步 callable 的“并行”实际阻塞串行 | `agent/step_runner.py:451` | 两个 .2s 同步任务合计约 .4s；机制可核 |
| D15 | P2 | 真实 LLM e2e 的降级断言依赖固定模型置信度 | `scripts/e2e_llm_routing.py:318` | 本次 .88×.7=.616，脚本无条件要求低于阈值 |

### 文件与配置边界：D01–D03

**D01**：正常 helper 的 frontmatter `id: ../../../outside` 通过真实安全审计。公开 `vibe skill add <local> --global --manual-config` 在隔离 HOME 下成功创建安装 root 外的目录，无需 force。独立入口探针仅替换交互默认答案及安装后的语义 index，同步/解析/audit/copy 均真实。没有证明远程零交互攻击，覆盖已存在目标一般需要 force；已证明用户选择安装来源，不足以限制来源 metadata 所决定的写入位置。修复应校验 logical ID、resolved containment 和目标各级 symlink，保留合法 namespace/skill。

**D02**：VibeSOP 自己会使用平台 skills symlink。完整 Claude render 遇到 `output/skills/demo -> installed-pack/demo`，会改写后者 SKILL.md 并写 ownership marker。原因是先 resolve，再把 resolved.parent 当安全 base；PathSafety 的拒绝 symlink 保护失去调用语境。应以平台输出根为锚，显式处理已有 link，保护中央安装内容与用户修改。它是已复现的写错文件，不是未证实的远程漏洞。

**D03**：`vibe build opencode --output <temp>` 无保存密钥 opt-in，仍将 ambient OPENAI/ANTHROPIC API key 值写入 llm-config.json；哑凭据实测 0644。父类已用 api_key_env，override 回退到原值。应默认保留环境引用；如宿主确实需要原值，应有独立显式导入与权限合同。本轮未证明真实密钥上传、提交 Git 或被他人读取。

### 路由控制与缓存：D04–D05

**D04**：候选落盘后 set_enabled(False)，同实例与新实例都继续把技能视作可路由，直到强制 cold reload 才消失。auto-config 不在 cache fingerprint 内，filter 使用旧 enabled。优先验收正常公开 CLI 的 disable→route 序列，以及 scope/archive 更新；明确显式点名禁用技能的产品语义，避免混淆自动路由与人工强选。

**D05**：改真实 SKILL.md description、确认 mtime 变化后，自动刷新和显式 CandidateManager.reload 都仍返回旧 description；其内部 SkillLoader `_skill_cache` 没清。新 fingerprint 还可能把旧 metadata 再写入磁盘。应统一 loader/candidate 的刷新版本，包含新增、删除、修改及自动配置变化。

### 执行语义：D06–D08、D14

**D06**：两个无依赖步骤成功、第三步依赖两者；fail_fast=True 应继续执行第三步，当前却无条件 break，completed=2/failed=0，下游验收或汇总留 pending。既有测试只覆盖发生失败时 fail_fast，漏掉该开关的全成功路径。

**D07**：LOOP_UNTIL_DRY 的 executor 抛异常；引擎正确记 failed，但 StepRunner dynamic 返回 failed=0/skipped=0，内部 failed_count 同样 0，final_status 没交付。不能宣称所有终态已被误放行：底层 plan 本身仍 failed。已证实公开结果与底层状态不一致，调用者不能依赖统一 counters；应同步 StepOutcome/终态/回调。

**D08**：PlanBuilder 生成的 RED_TEAM/DEBATE 含 agent_squad_id，先落进 StepRunner 简化 squad 分支，未进入 WorkflowEngine 的 handoff/review gate。公开 runner 的 reviewer 返回 `blocked: no evidence` 仍 completed；handoff context 缺失，执行按角色字母排序而非协作顺序。修复应让不同入口共用协作与结果归一，不只是增加另一段字符串判断。

**D14**：async coroutine 内直接调用同步 executor，没有 await/thread dispatch；两个 blocking callable 实际串行。应明确同步 API，或引入显式 async executor/受控线程执行。不要加易抖动的墙钟阈值测试；用 barrier/concurrency counter 验收实际重叠。

### 构建、经验与验证：D09–D13、D15

**D09**：create_overlay 将 security/routing 写顶层，merger 只读 policies.security/routing；输入 .9 的 threshold 得到默认 .6，无错误。修复 canonical schema、validator 与真实 helper roundtrip，覆盖更严格 policy，不能仅测试 YAML 可解析。

**D10**：正常 BUILD.sh 在 pack 内生成文件，容器 /work:ro 导致失败；输出只变为文本字符串，安装主链继续 audit/link 并返回 success。无需执行危险命令即可触发。应使用可写隔离副本→验收产物→原子回写，并让 required build 的失败显式失败/不完整；不能为了让测试过而直接把用户根目录或 Docker socket 暴露给 build。

**D11**：实例 A/B 均已加载 query A；A 保存成功反馈，B 仅新增 query B，之后磁盘 A success 从 1 变 0。锁序列化写入，却没有合并 stale snapshot 的字段；不是只有两个 writer 同时改同一个 id 才会丢。应在锁内读最新状态并应用 delta，或采用追加 outcome 事件。

**D12**：真实 SpanWriter 将 metadata/output 编为 JSON string，recall 对 skill_id 只接受 dict。三次不同 trace 可以得到 gold，但 skill_id=None；真实 consumer 接受用户 Y 后返回 None，显示 unknown、没有增加 outcome，后续 route 不得到历史 skill 偏好。embedding 固定向量仅隔离相似度依赖，没有替换生产 writer/reader/consumer。修复应基于真实生产 payload 做 roundtrip。

**D13**：同 pattern 从 action A 改 action B，仅 confidence 回到 .5，旧 3 次成功被保留；core 默认 is_reliable=True。生产 optimization 的 .6 门槛会先挡住，并非“所有路由马上使用新动作”；但新动作一次成功就借旧样本跨门槛。证据应绑定 pattern+action revision。

**D15**：真实模型给出 .88，last-good ×.7 后 .616，当前 threshold 允许接受，脚本却写死 .82→.574 并无条件要求 scenario fallback。该次 6/7 不是整体真实 LLM 路由失败，也不能证明新安全漏洞。应确定性测试衰减和阈值分支，真实 API 验证传输/解析；若产品要求 stale 一律仅提示，另加明确门禁，而非依赖乘数恰好低于 threshold。

## 6. 收窄、反驳与未纳入主清单的项

- WorkflowEngine squad 收到 passed=False 后标 COMPLETED：源码明确“run completed”含义，且结果仍携带 verdict。本次没有证实下游发布因此自动放行，因此从初审 P1 降为**终态语义/事件设计债务**。建议 plan_terminal 同时携带 execution 与 acceptance 结果，不让各 pattern 的 completed 含义变化。
- FileTransactionalInstaller 未恢复新文件的“不存在”状态：反例确实留下新文件并报 rollback_completed=True，但当前生产安装链不使用该 helper，列为低曝光维护项，不挤占第一批。
- 默认 dashboard 绑定 localhost；没有将 URL 拼接假设直接当远程路径遍历。git ext/file transport 防护、pack 的 TTY unsafe fallback、runtime scanner 失败时阻断均经源码反证，不报告未成立的 exploit。
- loop skill/query success 主要证明路由/交付结果，command target 则真实执行进程。源码明确这一差异；它是产品/证据阶段合同需清晰呈现，不是“定时任务全部没执行”的缺陷。
- 用户确认 gold replay 写 positive feedback，只证明接受选择，不证明当前任务已经执行通过。应建立反馈类型，不能由此声称全部历史证据伪造。
- 生产观测 sample gate 与 report-only 是刻意设计；未把小样本不产出绿色 verdict 当缺陷。

## 7. 验证结果与证据边界

| 检查 | 本次实际结果 | 能证明什么 / 不能证明什么 |
| --- | --- | --- |
| host ruff / format / basedpyright | 全部 exit 0 | 静态门禁通过；不能替代行为合同 |
| Linux arm64、Python 3.12、冻结 lock 回归 | **7636 passed / 37 skipped / 21 deselected**，181.5s | marker 排除 benchmark/slow；非全部功能/平台均已执行 |
| 分支覆盖率 | **80.58%**，闸 73% | 包括分支的 coverage.py 指标；不是端到端可靠性百分比 |
| Node 24 额外验证 | **223 passed** | Pi extension、process boundary、generation hook、tool-seq、layering；补主镜像 Node 20 跳过的 TS 执行 |
| hermetic 路由评测 | **53/59（89.8%）**，2 条环境跳过，6 条已知失败，0 新失败 | frozen baseline gate 通过不等于所有 query 正确；正例过拒4/37、负例过灌2/20、near-miss过灌2/14 |
| decision-source | 10 workflow jobs / 10 registrations，exit 0 | 声明齐全，不是对全仓模型依赖的形式证明 |
| fresh-checkout artifact guard | 1146 refs / 684 ok / 0 dangling / 462 stale，精确基线匹配 | 冻结债务仍有462条，不把基线通过称为债务归零 |
| wheel 冷安装 | 从本次源码 build wheel，源码目录外 `uv tool install`、两平台 quickstart 完成 | 发行形状和 builtin 资源能工作；fresh wheel按依赖范围解析，完整回归则使用冻结lock |
| 部署后 hook | Claude 真实生成 shell script执行；Grok host-shaped CLI输入均命中 builtin/commit-message | 证明部署产物/过程边界，不声称运行了真实宿主会话或后续任务验收 |
| 确定性缺陷探针 | 路由/runner、安装/overlay、真实disk回放与反馈在容器复现 | 临时数据+受控执行器，不依赖真实LLM意见；Pack完整链另从host调用真实Docker |
| DeepSeek真实 routing e2e | **6/7**，T0/T1/T2/T3/T5通过；T4失败，见D15 | T1真实AI请求、T2跨router持久cache、T3无污染；T1b/T5是观察项，不当独立强断言 |
| DeepSeek独立评审 | deepseek-v4-flash，17,185 input / 2,600 output tokens | 只读材料评审，输出达到token上限；不是独立运行验证或缺陷证明 |
| Grok | CLI 0.2.111 被服务端 HTTP426拒绝，要求>=1.0.13 | 没有取得Grok评审，不冒充双外部模型结论；未升级用户工具或搬运凭据 |
| 远程CI只读核查 | 远程main与审查HEAD相同；CI和Quickstart E2E success | 只覆盖已提交HEAD，不能包括用户未提交改动与本次新增报告 |

远程同一HEAD的结果：[CI](https://github.com/nehcuh/vibesop-py/actions/runs/37640009490)、[Quickstart E2E](https://github.com/nehcuh/vibesop-py/actions/runs/37640009670)。读取时间为本次审查日。当前工作区的未提交改动只由本轮实际检查覆盖。

保留的验证过程错误：初次复制副本没带Git元数据，出现 **7634 passed / 2 failed**；两项都是Git依赖检查。随后从原HEAD浅clone取得真实metadata，完整复跑得到7636通过，并非删除失败测试。原Dockerfile构建卡在registry frontend下载，改用已有arm64基础镜像派生并以当前lock重新同步依赖；最终镜像digest记于manifest。普通venv安装的Claude脚本探针返回空，改按公开文档的uv tool安装方式重跑，部署脚本才得到正确结果；该安装模式差异保留在证据，不报成正式产品缺陷。

主镜像37个skip包括缺少可选fastembed、外部pack/本地registry、jq和Node版本等；Node版本部分已用Node24专项补跑。没有本轮Windows/Python3.13容器复跑、实际Pi/Claude/Grok宿主会话，或完整semantic模型评测。证据据此划界。

一个关键反例是：StepRunner/WorkflowEngine/learner/recall的覆盖率分别约89.95%/91.81%/90.20%/86.96%，仍有本轮缺陷。因此优先加生产格式/公开入口的合同测试，胜过只提高整体百分比。

所有机器证据与可运行反例保存在本目录 `evidence/`，见 `evidence/manifest.json`。模型评审是意见，退出码/日志/产物/测试记录才是本次执行证据。

## 8. 后续行动：按依赖批次推进

1. **先保护用户文件与凭据（D01–D03）。** 以真实 CLI、namespace ID、已有 symlink、哑密钥、重复 render 为验收。仅修 path helper 或 chmod 不足；须验证真实调用者根边界与默认导出合同。
2. **恢复路由控制的真实性（D04–D05）。** 自动配置/技能版本进入完整 fingerprint，刷新所有 cache 层；验证热进程、新进程、修改/新增/删除/disable/archive/scope。
3. **统一执行结果与协作入口（D06–D08）。** OK/exception/failed sentinel/blocked sentinel/dependency failure/retry/cancel 矩阵跑过每个公开入口。统一结果模型后再调整并发（D14）。
4. **闭合真实持久化与构建合同（D09–D13）。** helper 输出、真实 JSON payload、两个 stale writer、新动作证据版本、required build 成败，均采用真实 producer→consumer 验收。
5. **修验证 oracle 并重跑所需门禁（D15）。** 每批独立模型评审、适当 host tests、全新容器 e2e；汇总 CI 与 release checks，再以可审查 PR 交付。不要将外部模型意见设为自动发布闸。

这些是本轮诊断后的修复计划，不代表修复已完成或已授权发布。修复最好按行为边界分小批，避免把全部问题和大规模重构塞进一个 PR。

未来一个研发周期，建议暂缓新增默认委员会、更多 workflow pattern、无对照收益的自动记忆优化与单纯技能数量扩张。保留路由/交付/观测核心，收口未完成研究，并提供公开可复验的小型证据包。

成功标准应是：用户不用理解内部多个状态机；禁用/修改配置即时可预测；build 不意外复制秘密或修改来源；失败和缺证据不能被公开结果解释为成功；一个真实宿主与仓库工作流能从需求走到机器验收，并可追踪到具体来源。达到这些标准后，扩平台与编排才有坚实基础。
