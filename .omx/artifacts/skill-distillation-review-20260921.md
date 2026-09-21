# 评审：智能体研究/论文发现是否沉淀为可复用技能并内化到项目

> **性质**：CMspark 编程接力 · review mode · 只读评审，不含代码改动。
> **日期**：2026-09-21 · **基线**：main `ff82b942`（origin/main 同步点）。
> **证据基线**：`docs/research/research-survey.md` 终稿 v1.0（1688 行）、`core/skills/` 22 个内置技能、`ci/decision-source.yaml`、`memory/` 三层、`.omx` 产物库（358 个 tracked 文件）。
> **证据标注**：`[inspected]` = 本次实读文件/git 元数据；`[executed]` = session 记录中当时实跑验证（S87）；`[assumed]` = 推断待核。

## 总体判断

**部分沉淀（F1-F10 中约 4 条已操作化），内化呈三层分化：**

| 层 | 状态 | 证据 |
|---|---|---|
| 评审方法论线（F4/F5/F6/F10） | ✅ 已沉淀为技能 + CI 机制 | 3 个内置技能（S87, commit `88998cbe` + `ff82b942`）；`ci/decision-source.yaml` 已进 main（`042e679c` fail-closed 守卫）[inspected] |
| 工程/实验踩坑（R6 等） | ✅ 已入 project-knowledge | 「弱模型 agentic 实验三坑」`memory/project-knowledge.md`（R6, 2026-08-29 条目）[inspected] |
| 实验线 I/III/IV 核心发现（F1/F2/F7/F8/F9） | ⚠️ 仅文档层 | 只在 research-survey §7/§9.2，无技能、无机制承载 [inspected] |
| 论文笔记 4 条「下一步建议」 | ⚠️ 落地 <1/2 | 建议#3/#4 未实现（grep `反例\|前提\|counterexample` 于 core/skills → 0 命中）[inspected] |

## Findings（按严重度）

### [P1] F1/F2/F9 未沉淀为技能或机制（沉淀断层）

- **F1**（技能价值以 spec 缺口为前提）：22 个内置技能无一承载「spec 写满时别指望技能、先写满任务书」（survey §9.2 #1）→ 写满场景仍会全量注入冗余技能，R1-R3/R7 五连平的教训只活在文档里。
- **F2**（消费证据比评分诚实 / 弱模型先修路由）：论文笔记建议#3「分开记录选中、读到、适用、执行、验收」未实现；survey §9.3 仍列为开放问题。
- **F9**（学习环防自污染）：echo 展示层守卫是产品代码 ✅，但 promote 准入纪律（笔记建议#4「候选技能写清前提、反例、验证方法与来源成败」）未进 skill-craft / instinct / experience-evolution 的晋升模板。

### [P1] 两个承重证据挂账过期

- **R8 盲评未结算**（session S84 Next 项；next-opt 设计明文「R8 盲评未结算则 E4 不开工」）→ F1「粗=显形」半边停在人评级，H3b 流水线整机被阻塞；最新 session（S87, 09-16）仍无结算记录。[inspected]
- **gate43 T+21 回声复检**：预定到期 2026-09-14，本文写作日 2026-09-21，**过期 7 天无产物**（本机 `.omx` 无任何 t21 文件）→ F9「治理可持续 vs 回滚」悬而未决。[inspected]

### [P2] F9 关键测量 artifact 不在 tracked 路径 —— F10 失败模式复发

综述通篇引用 `gate43-t7-echo-measure.md` / `gate43-t14-echo-measure.md`，但 `git ls-files | grep gate43` 为空、本工作区磁盘亦无 → 回声三部曲证据链疑似只存于 macOS 单机（综述成稿机）。这正是综述案例 2c（「gitignored 账本 = 没有账本」）与 §4.9⑤（S57/S67/S76 三份对抗评审报告已丢）的再次发生：358 个 `.omx` 文件已入库，唯独承重的回声测量不在其中。[inspected, 本工作区口径]

### [P2] 知识分层缺口：F 系结论未进 warm 层

F1-F10 在 `docs/research/research-survey.md`（tracked ✅）和 `memory/session.md` S84（hot 层），但 `memory/project-knowledge.md` 无任何 F 系条目——按 memory-flush 规则（strategy decision → project-knowledge.md），下次会话查「为什么技能没用」只能撞到踩坑条目，撞不到研究结论。[inspected]

### [P3] 技能↔workflow 命名漂移 + `.grok/workflows/` 未入库

S87 为修 demo IDF 污染将技能改名 `adversarial-panel`/`adversarial-arbitration`（`ff82b942`），但 `core/skills/adversarial-panel/SKILL.md` 第 3 步仍引用注册 workflow 名 `adversarial-review`；且 `.grok/workflows/` 处于 untracked → 新 clone 上该技能第 3 步悬空（与 F10 同族：机制依赖了不入库的东西）。[inspected]

### [NIT] 论文三臂对照实验未跑

论文笔记建议#2（无技能 vs 历史记录 vs 提炼技能同题三臂）未执行；survey §9.3 草图无功效计算。逐条对照表本身已在 §8.5/E23 完成（E1-E26 逐条核验）✅。

## Files of interest

| 文件 | 角色 |
|---|---|
| `core/skills/adversarial-panel/SKILL.md` | F5/F6 沉淀 ✅（5 独立镜头 + refute-first verifier） |
| `core/skills/adversarial-arbitration/SKILL.md` | F4/H5 沉淀 ✅（D/T/J、「发现不收敛，决策才收敛」、合成器不作放行闸） |
| `core/skills/babysit-main/SKILL.md` | 收尾盯 CI 流程 |
| `core/registry.yaml`（约 826-862 行） | 三技能注册 ✅（S87 [executed]：hermetic 6 query 全中、生产路由 88%、CI 全绿） |
| `ci/decision-source.yaml` | F10 机制已进 main ✅ |
| `docs/research/research-survey.md` | F1-F10 / E1-E26 研究总账（终稿 v1.0） |
| `docs/research/2026-09-09-agent-skills-paper.md` | arXiv 2608.14036 核验笔记 + 4 条待验证建议 |
| `docs/research/README.md` | 研究入口索引 ✅ |
| `memory/project-knowledge.md` | R6 三坑已入；F 系缺口所在 |
| `memory/session.md` S84/S87 | 沉淀过程与挂账项 |
| （缺失）`gate43-t{7,14}-echo-measure.md` | 应入库未入库（P2） |

## Residual risks

1. **引用违规风险**：T+21 结算前引用「回声已治理」、R8 盲评结算前引用「粗题显形」违反项目自己的不声称纪律——综述里有限定语兜着，但无机制强制。
2. **过灌风险持续**：F1 条件性结论不在路由层，spec 写满场景仍全量注入。
3. **promote 无前提/反例模板** → 未来晋升技能可能重演 bd1bc217 式回声身份污染（F9 未被制度化挡住）。
4. **证据链单机化**：回声测量等唯一副本在成稿机，换机/清盘即永久丢失。

## 值得肯定

- 评审线沉淀质量高：技能把裁决转成可执行步骤（D/T/J 分类表、"Do not re-run finders to get consensus"、human sign-off 步骤），带 When-NOT-to-use 与 Anti-Patterns——是真「内化」而非「引用」。
- 沉淀走系统管道而非一次性手工：instinct → skill-craft → registry → routing_eval（CN/EN）→ hermetic 基线刷新 → demo 测试全链路，S87 全程 [executed] 验证。
- decision-source 注册表 fail-closed 守卫是「纪律变机制」的正例（F10 落地）。

## 建议的后续（供下个 session 取用）

1. 结算两个挂账：R8 盲评（解锁 E4）、gate43 T+21 复检（F9 终裁）——各自按 prereg 判据执行，结果回写 survey §3.15/§6 待填清单。
2. 把 F1/F2/F9 的可操作面沉淀为技能或机制：spec-缺口判据进路由/注入层或写一份 task-briefing 技能；消费证据（读计数）进 telemetry；promote 模板补「前提/反例/验证方法/来源成败」四要素。
3. 抢救证据链：从成稿机找回 `gate43-t{7,14}` 测量原件并入库；`.grok/workflows/` 入库或改引 tracked 路径。
4. F 系结论摘要补进 `memory/project-knowledge.md`（warm 层）。
