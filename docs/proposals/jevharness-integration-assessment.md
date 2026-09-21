# JevHarness 集成评估 — 能否用于 VibeSOP

> **日期**: 2026-09-21
> **状态**: 📝 评估完成（未实现；三条路径待决策，无代码改动）
> **版本**: 8.5.0
> **评估基线**: `main` @ `0fbe1e9c`（先拉取最新变更，再据此评估；拉取前本地落后 11 个提交）
> **对象仓库**: `TianyuCodings/JevHarness`（外部）→ 本项目 `nehcuh/vibesop-py`
> **作者**: 用户（提问）+ CMspark（静态评估）

---

## 📋 背景与问题

用户提问：**「当前项目是否可以用到我们的项目 github.com/nehcuh/vibesop-py 中？」**

即：把外部项目 **JevHarness**（让 LLM 为 Jev 写任务专用 harness、可选奖励+轨迹反思进化）应用到本项目的技能/路由/评测体系里，是否可行、以什么形式可行。

本文档只回答「怎么接、接哪里、哪些接不了」，不承诺集成，也不改动任何源码。

---

## 🔬 评估方法与证据边界

**方法**：只读静态阅读两个仓库的公开页面（GitHub 网页 + raw 文件），**未 clone、未安装、未运行任何代码、未做集成验证**。因此本文结论是**设计层判断**，不是实测结论。

实际读取的证据（可复核）：

| 证据 | 用途 |
|---|---|
| JevHarness README（中/英） | 定位、能力、延迟数据、运行环境与凭据要求 |
| JevHarness `skills/jev-harness/SKILL.md` | 技能契约、frontmatter 字段、「无通用 CLI / 无内置 TaskAdapter」声明 |
| JevHarness `pyproject.toml` | 包名 `auto-jev`、Python 下限、依赖版本区间 |
| JevHarness 仓库根目录树 | 交付形态（插件 + 技能 + `auto_jev/` 包），**根目录无 LICENSE 文件** |
| 本项目 README / `docs/INDEX.md` | 定位、研究线、文档结构 |
| 本项目 `src/vibesop/` 目录树 | 子系统划分（adapters/agent/builder/cli/core/llm/spec/security/market…） |
| 本项目 `core/skills/` 目录树 | 内置技能清单与命名 |
| `docs/EXTERNAL_SKILLS_GUIDE.md` | 外部技能包安装与 namespace 机制（接入路径 A 的依据） |
| `docs/skill-format-spec-v3.md` | SKILL.md 必填字段与校验命令（路径 A 的缺口依据） |
| `docs/skill-market-search-and-feedback-loop.md` | 本项目已有的市场/反馈环/数据地基建制（用于判断重叠） |
| `pyproject.toml`（本项目） | 依赖区间、Python 下限、包形态（路径 A/B 的冲突依据） |

> 说明：延迟/胜率等数字均为 JevHarness 自述的**选择集示例结果**，上游也明确声明「不是对未见对局的独立估计」，本项目不应直接引用为收益承诺。

---

## 🧭 两者定位对比

| 维度 | JevHarness | VibeSOP（本项目） |
|---|---|---|
| 一句话定位 | 让 LLM 写「任务专用 harness」：代码算特征 → Jev 小模型做 choice/score/noul 判断 → 组合为动作，可选 GEPA 反思进化 | 多 agent 的 AI 工程工作流：技能路由 → 计划 → 验证 → 轨迹/可观测 → 经验召回 → 治理 |
| 优化对象 | **单个任务的决策质量** | **工程工作流的可信交付**（证据、可复现、放行权在人/确定性闸） |
| 交付形态 | SKILL.md 技能 + Claude Code 插件市场 + Python 包 `auto-jev` | SKILL.md 技能体系 + CLI `vibe` + 为 6 家 agent 生成配置 |
| 运行时 | Python 3.11+；**执行 Python 代码节点需 macOS 原生沙箱**（不可用则拒绝执行） | Python 3.12+；跨平台（含 Windows CI） |
| 外部凭据 | Jev 托管模型：`AI_GATEWAY_API_KEY` 或 `TYPESAFE_API_KEY`；可选反思模型 | 按 provider 配置（`ANTHROPIC_API_KEY` 等），核心路径无需第三方托管判断服务 |
| 治理/信任 | 冻结产物绑定 spec+runtime+evaluator+资源；候选不得改写 reward/evaluator | 三级信任、hash 校验、pack-lock、构建门、验收证据 |
| 成熟度 | 7 commits、6 stars、单人、无 LICENSE、无公开 CI 证据 | 已公开发行、千级 commits、MIT、CI/文档检查器齐全 |
| 许可 | **仓库根目录无 LICENSE 文件**（pyproject 亦无 license 字段） | MIT |

**共同点（接口所在）**：两者都围绕「把 LLM 的判断策略固化成可执行、可复现、带证据的东西」，且都吃 SKILL.md 生态。

**差异（重叠边界）**：JevHarness 管「**单任务决策策略的固化与进化**」；VibeSOP 管「**工程流程的可靠性与治理**」。真正的重叠区是三件事：*技能/策略的离线优化*、*评测驱动的改进*、*证据与冻结语义*。

---

## ✅ 结论

**能用，但不是「加一条依赖」那种用法。** 可行的三条路径按性价比排序：

1. **路径 A（最直接）**：把 `jev-harness` 当作**外部技能包**装进 VibeSOP，零改动 core，用户自选安装。
2. **路径 B（研究价值最高）**：把 JevHarness 当作**本项目路由策略的离线优化/评测 harness**（写一个 vibesop 任务适配器，reward = held-out 路由准确率），产出冻结策略再回灌路由。
3. **路径 C（零依赖即可落地）**：只吸收它的**设计契约**（失败语义、冻结绑定、评测分离、候选越权禁止），写进本项目文档。

**不建议**：把 `auto-jev` 作为依赖并入本项目包（路径见下节「硬约束」，`openai` 版本区间不相交）。

---

## 📦 路径 A：作为外部技能装进 VibeSOP

### 依据

`docs/EXTERNAL_SKILLS_GUIDE.md` 明确：本项目自 4.1.0 起支持从外部技能包**动态加载与执行**技能（superpowers / gstack / omx 是先例），走 `vibe install <repo>` + namespace 管理。JevHarness 的仓库结构恰是标准包形态：

```
JevHarness/
├── SKILL.md                 （可选：包级描述）
└── skills/
    └── jev-harness/
        └── SKILL.md
```

### 缺口（必须先补，否则校验不过）

按 `docs/skill-format-spec-v3.md`，合法 SKILL.md 必须具备非空 `id`、`name`、`description`、`version`（SemVer）；而 JevHarness 的 frontmatter 目前只有 `name` + `description`。建议在 fork/本地副本上补齐（示意）：

```yaml
---
id: jevharness/jev-harness
name: jev-harness
description: Build, evaluate, and optionally evolve task-specific code and Jev decision pipelines.
version: 1.0.0
namespace: jevharness
type: workflow
user_invocable: true
scope: global
---
```

### 试用命令（示意）

```bash
vibe install https://github.com/<your-fork>/JevHarness
vibe skills list --namespace jevharness
vibe spec validate --all
```

### 注意

- **不要 vendor 进本项目仓库**：上游无 LICENSE，vendored 副本会给 MIT 项目带来授权不确定性；保持 out-of-tree、用户按需安装。
- 该技能自带 Claude Code 插件安装路径（写 `~/.claude/skills/jev-harness`），与本项目 `vibe build claude-code --output ~/.claude` **写同一棵目录树** → 需留意命名/所有权冲突（本项目已有 hook 内容 hash 校验机制可用于核对）。

---

## 🧪 路径 B：当路由策略的离线优化 / 评测 harness

### 为什么契合

本项目已有：路由评测集与 held-out probe、证据清单、`docs/experiments/`（ruff 配置中已把 *frozen research harnesses* 明确标注为「数据而非受维护源码」）、以及「技能/规范/编排何时真的提升效果」的研究问题。

JevHarness 提供的恰好是这套流程缺的另一半：**任务适配器边界（评测器在候选之外）+ GEPA instance frontier 的父子同批次比较 + 保留被拒提案的真实谱系 + 冻结产物（spec/runtime/evaluator/资源绑定）+ 完整决策轨迹**。

### 概念映射

| JevHarness 概念 | 映射到本项目 |
|---|---|
| 任务适配器（observations / legal actions / scoring） | 请求文本 + 候选技能清单 / 合法技能集 / held-out 路由准确率 |
| Harness（特征构建 + Jev 判断 + 决策逻辑） | 路由决策策略（特征 + 判据 + 阈值） |
| Jev `choice` 问题 | 「该请求应路由到哪个技能」 |
| GEPA 反思与候选谱系 | 路由策略候选的离线搜索与谱系记录 |
| 冻结产物（spec+runtime+evaluator+资源） | 冻结的路由策略 + 评测器版本 + 数据快照 |

### 必做工作

技能内明确声明：**没有通用 CLI、没有内置 `TaskAdapter` 类，其 CLI runner 均为领域示例，不得臆造**。因此本路径等于「自己写 vibesop 适配器 + 小 runner」，不是拿来即用。

**最小可行实验**（建议顺序）：

1. 只读适配器 + mock 管道跑通 validate_spec / 编译图 / 契约检查；
2. 一次最小真实推理，验证 transport 与响应 schema；
3. 与现有基线（当前路由）在同一批次比较；
4. 检查完整决策轨迹；
5. 再决定是否扩大搜索与费用。

### 成本与风险

- 需新引入 Jev 凭据与调用费用；上游明确「无上限 ≠ 允许无限花费」，本项目也应显式设定轮次/额度/停止条件。
- 上游自述延迟为托管服务的示例测量，本项目不应据此做性能承诺。

---

## 🧱 路径 C：只吸收设计契约（零依赖，可立即落地）

| 契约（来自 JevHarness 文档） | 与本项目现有立场的关系 | 建议落点 |
|---|---|---|
| 超过配置字节上限的输入 **归档并拒绝**，绝不「截断后继续」 | 与「证据必须来自被评估的那次执行」一致 | `docs/specs/` 证据章节 / 轨迹契约 |
| 反思输入包含每条选中 episode 的**完整决策、节点 I/O、问答应、记忆、失败**，无损去重 | 可强化 trace/replay 的完备性要求 | 可观测性文档 |
| **候选不得改写 reward / labels / hidden state / action 权限 / evaluator** | 与「模型自己的批准不是完成证明」同源 | 评测与放行原则 |
| 冻结产物绑定 spec+runtime+evaluator+声明的任务资源 | 与 pack-lock / 构建门思路同构，可互参 | 冻结语义说明 |
| **托管模型别名锁不住提供方未来行为**；存储响应与新调用可复现性不同 | 现有可复现性论述可引用该提醒 | 研究/证据文档 |
| 选择集上的改进**不等于**未见数据的独立估计（需明示） | 与现有「不把 R8 当发现」的表述风格一致 | 实验报告模板 |

这几条是纯文字收益，**不引入任何依赖**，建议优先采纳。

---

## ⛔ 硬约束与不可行项

### 1. 依赖区间冲突（决定性）

| 依赖 | JevHarness (`auto-jev`) | VibeSOP | 结论 |
|---|---|---|---|
| `openai` | `>=2,<4` | `>=1.60.0,<2.0.0` | ❌ **不相交** |
| `anthropic` | `>=0.70,<2` | `>=0.45.0,<1.0.0` | ✅ 交集 0.70–1 |
| `httpx` | `>=0.28,<0.29` | `>=0.28.0,<1.0.0` | ✅ |
| `fastapi` / `uvicorn` | `>=0.115,<1` / `>=0.34,<1` | `>=0.115.0,<1.0.0` / `>=0.30.0,<1.0.0` | ✅ |
| `python-dotenv` | `>=1.1,<2` | `>=1.0.0,<2.0.0` | ✅ |
| Python | `>=3.11` | `>=3.12` | ✅（3.12 环境同时满足） |

→ **唯一硬冲突是 `openai`**。要接入必须**进程级隔离**（独立 venv / 子进程 / 外部技能包），不得并入本项目依赖。

### 2. 非库形态

上游技能明确：没有通用任务 CLI、没有内置 `TaskAdapter`，现有 runner 是领域示例。接入成本 = 自写适配器，不是 import 即用。

### 3. 平台

执行 Python 代码节点**需要受支持的 macOS 原生沙箱**，隔离不可用则**拒绝执行**。本项目面向跨平台（含 Windows CI），这条对本项目用户群是硬门槛（纯表达式/Jev 流程不启动这些 Python 工作进程，可绕开但功能受限）。

### 4. 凭据与可复现性

Jev 是托管小模型，需新凭据；上游明确指出「托管模型别名无法锁定提供方未来行为」——这会在本项目强调「证据可复现」的语境下削弱闭环强度。

### 5. 许可

上游仓库**根目录无 LICENSE**。任何 vendoring / 代码复用前必须取得授权；否则只能走「外部技能、用户自装」形态。

### 6. 成熟度

7 commits、6 stars、无公开 CI 证据。适合作为**可选外部技能 / 研究参照**，不适合进核心路径。

---

## ⚠️ 风险登记册

| # | 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|---|
| R1 | 上游无 LICENSE，vendoring 引发授权问题 | 高（若 vendoring） | 中 | 只做 out-of-tree 外部技能；需复用代码前先取得授权 |
| R2 | `openai` 区间冲突导致环境解析失败 | 高（若并依赖） | 高 | 独立 venv / 子进程隔离；不并入本项目依赖 |
| R3 | Python 节点需 macOS 沙箱，Windows 用户不可用 | 中 | 中 | 限定为「可选、平台声明」；文档明示限制 |
| R4 | Jev 托管服务成为决策链路上的外部依赖 | 中 | 中 | 明确标注可复现性差异；不承诺冻结即等价复现 |
| R5 | 与本项目 `~/.claude` 生成物写同一目录树 | 中 | 低 | 用现有 hook 内容 hash 校验核对所有权 |
| R6 | 上游自述收益被误读为项目收益 | 中 | 中 | 引用时标注「选择集示例结果，非独立估计」 |
| R7 | 上游早期项目后续破坏性变更 | 中 | 中 | 固定 ref / 本地副本；仅外部技能路径依赖上游 |

---

## 🗺️ 建议动作与验收

### P0（零风险，先做）

- [ ] 补齐 `jev-harness/SKILL.md` frontmatter（`id` / `version` / `namespace` / `type`），在**本地副本**上走 `vibe spec validate` 与外部技能安装试用。
- [ ] 就上游无 LICENSE 一事联系作者或明确保持 out-of-tree。
- [ ] 采纳「路径 C」的 6 条设计契约到对应文档（纯文字）。

**DoD**：`vibe skills list --namespace jevharness` 可见；`vibe spec validate --all` 绿；文档改动通过 `scripts/check_docs.py` 与 `scripts/check_doc_versions.py`。

### P1（研究性，需预算决策）

- [ ] 在 `docs/experiments/` 下开一条「Jev 驱动的路由策略离线优化」实验线，先只读适配器 + mock 管道。
- [ ] 跑通后再做一次最小真实推理，并与现有路由基线同批次比较。

**DoD**：实验有协议、数据分离（train/selection/held-out）、停止条件与费用上限；结论按「选择集结果 ≠ 独立估计」表述。

### P2（可选项）

- [ ] 评估「冻结路由策略」产物格式与本项目 pack-lock/构建门的对齐方式。

### 明确不做（Won't）

- ❌ 把 `auto-jev` 并入本项目 `dependencies`
- ❌ vendor 上游代码进本仓库（无 LICENSE）
- ❌ 把 Jev 托管调用放进核心默认路径
- ❌ 在文档中把上游示例收益表述为本项目已验证收益

---

## ❓ 未验证项（诚实清单）

1. 未实际安装/运行 JevHarness；`vibe install` 对该仓库能否成功**未实测**。
2. 未验证 v3 frontmatter 补齐后能否通过全部校验器（`vibe spec validate` 行为仅据文档）。
3. 未与上游作者确认许可意图。
4. 未评估 GEPA 搜索在路由任务上的实际收敛性与费用。
5. 未做与现有路由基线的任何对照实验。

以上任一项若需推进，应在对应阶段单独验证，不得由本文档代为实现结论。

---

## 📎 附录：关键事实来源

| 事实 | 来源 |
|---|---|
| 本项目支持外部技能包动态加载 | `docs/EXTERNAL_SKILLS_GUIDE.md` |
| SKILL.md 必填字段与 `vibe spec validate` | `docs/skill-format-spec-v3.md` |
| 本项目已存在的市场/反馈环/数据地基 | [skill-market-search-and-feedback-loop.md](skill-market-search-and-feedback-loop.md) |
| 本项目定位、研究线与文档索引 | [../POSITIONING.md](../POSITIONING.md)、[../INDEX.md](../INDEX.md) |
| 本项目现行版本与发行状态 | [../PROJECT_STATUS.md](../PROJECT_STATUS.md) |
| JevHarness 包名/依赖/Python 下限 | 上游 `pyproject.toml`（`auto-jev`） |
| JevHarness 无通用 CLI / 无 TaskAdapter | 上游 `skills/jev-harness/SKILL.md` |
| JevHarness 迁移/运行环境与凭据 | 上游 README（含沙箱与凭据表） |
| 拉取后新增、可与路径 C 证据/台账契约对照的设计 | [../specs/2026-09-21-skill-distill-landing.md](../specs/2026-09-21-skill-distill-landing.md) |
