# 优化点收敛：可实验验证的需求点集

状态：**提案，未实现、未验证**。本文不声称任何代码已完成，不含测试结果。
基线：撰写时工作树为 `~/Projects/vibesop-py`（未锁定 commit；实施前须先固定 commit 作为基线）。
背景材料：`docs/specs/2026-09-09-verification-contract.md`（验证语义）、`docs/dev/routing-benchmark.md`（门禁范式）、`core/routing/benchmark.py`、`core/observability/behavior_consistency.py`。

---

## 0. 问题陈述

已观察到的现象：**对同一份代码库反复做 AI 评审/优化诊断，每次都能发现新的优化点；某次宣称"已全部检查并修复完成"，下一次重新打开又出现新的优化点与缺陷。**

本项目内部有该现象的现成物证（下文 R1 会引用）：同一日生成、彼此独立、无共享账本的 `optimization-plan.md` → `-p1.md` → `-p2.md` → `-auto-opt.md` 四连发；以及 `gate1..gate45+` 的"评审→修复→再评审"循环。

根因（第一性原理，非本文重点，仅作为需求依据）：

```
观测到的"新发现" = 真新发现（有限，几何衰减，最终趋近 0）
                 + 改写型伪影（无限，每轮大致常数）   ← 题眼
                 + 修复引入的新发现（脉冲式）
                 + 标准漂移带来的"新发现"（阶跃式）
```

只有当"问题集合有限可判定 + 评审确定性 + 上下文全覆盖 + 标准不漂移"四条同时成立，"再也发现不了新问题"才可能出现。四条在本项目语境下均不成立。**因此需求目标不是"消灭新增"，而是：把真实新增与度量伪影分开、把决策收敛从发现收敛中解耦。**

### 术语（本文强制统一）

| 类别 | 定义 | 是否有终点 |
|---|---|---|
| **D 类** | 可判定：能被确定性工具/编译/测试判定的违反 | 有（有限集合） |
| **T 类** | 可检验：有测试或可观测行为作证的缺陷 | 有（取决于覆盖度） |
| **J 类** | 主观判断："可以更优雅""建议拆分""可扩展性欠佳" | **无（空间无限）** |

任何未标注类别的"优化点"计数在本文语境下**不可用于门禁**。

---

## 1. 需求点总览

| 编号 | 需求点 | 独立性 | 主要落点 | 依赖 | 优先级 |
|---|---|---|---|---|---|
| **R1** | 发现账本 + λ(n) 新增衰减曲线 | 新增模块，不改现有门禁 | `core/observability/finding_ledger.py`（新）、`scripts/measure_finding_convergence.py`（新） | 无 | P1（基建） |
| **R2** | 发现级语义去重 + 账本入库 | 依赖 R1 的数据结构 | 同上 + knob | R1 | P1（基建） |
| **R3** | 强制发射偏差：空报告率度量 | 独立脚本，零侵入 | `scripts/measure_null_report_rate.py`（新） | 复用 hermetic posture | **P0（最便宜）** |
| **R4** | `behavior_consistency` 阈值 0.5 标定收口 | 独立，已有残留风险记录 | `core/observability/behavior_consistency.py`、`scripts/calibrate_behavior_threshold.py` | 无 | **P0（现成缺口）** |
| **R5** | 提出者/验证者同源检测 | 独立，仅扩展记录字段 | `core/observability/promote_verifier.py`（或验证记录路径） | 无 | P2 |
| **R6** | 标准漂移指纹扩展 | 独立，仅扩大指纹输入集 | `core/routing/benchmark.py` + `docs/dev/routing-benchmark.md` | 无 | P2 |
| **R7** | 净发现度量 + 决策收敛判据（severity × 佐证） | 依赖 R1/R2/R3 | 新增 gate 模块 + `scripts/` | R1,R2,R3 | P3（收口） |

**建议实施顺序：R4 → R3 → R1 → R2 → R7 → R5 → R6。**
理由：R4 已有被明确记录的残留风险，改动最小、收益最确定；R3 成本最低且结论最清晰（能一举判定核心论点是否成立）；R1/R2 是 R7 的前置基建；R5/R6 是加固项，可穿插。

---

## 2. 逐条需求点

### R1 — 发现账本与 λ(n) 新增衰减曲线

#### 缺口证据（本项目内）

- `.vibe/optimization-plan.md`：`Generated: 2026-07-20`，`Based on: Phase 1 Deep Diagnosis (10 Map + 6 Cross-cut + Synthesize)`，产出 P0-A/P0-B/P0-C 三批。
- `.vibe/optimization-plan-p1.md`、`.vibe/optimization-plan-p2.md`：同为 `2026-07-20`，p2 标注 `Method: adversarial-optimization workflow`，产出 P2-A/B/C 三批。
- `.vibe/optimization-plan-auto-opt.md`：又一轮。
- **四份计划之间没有共享账本、没有去重、没有"是否已收敛"的判定**，因此无法回答"第 4 轮相对第 1 轮，真实新增是增加了还是减少了"。
- 条目族示例：p2 的 `P2-A1 atomic_writer.py tests`、`P2-A2 cost_tracker.py tests`、`P2-A3 router_factory.py tests`、`P2-A4 builder/overlay.py tests`、以及 `P2-B1 _shared.py split`。**"给模块 X 补测试""把文件 Y 拆分"在任何规模代码库上都不会自然终止**——这是典型的 J/T 混合类，天然不收敛。

#### 需求

新增 append-only 发现账本，每条发现必须携带以下字段（缺任一字段则该条不入账）：

```
finding_id        # 稳定标识（内容指纹派生，非自增序号）
criterion_id      # 命中的准则/检查项标识；无准则归属者不入账
evidence_anchor   # file:line 或可执行证据（命令 + 期望/实际）
class             # D | T | J   （三选一，无默认值）
claim_fingerprint # 核心断言指纹（见 R2）
source            # 产出该发现的分析入口（optimize/stale/suggestions/feedback 等）
round             # 第几轮观测到
observed_at       # ISO 时间
```

并实现 λ(n) 计算：对冻结 commit 连续 N 轮执行同一分析入口，输出每轮"新增（去重后）"数量，并按 D/T/J 分层。

#### 落点（严格限定）

- 新增 `src/vibesop/core/observability/finding_ledger.py`
- 新增 `scripts/measure_finding_convergence.py`
- 新增 `tests/core/observability/test_finding_ledger.py`
- **不修改**现有 routing / evaluation / feedback 的行为；接入以显式调用为主，不做全局自动注入（沿用项目既有约束）。

#### 验收标准（机器可检查）

1. `scripts/measure_finding_convergence.py --rounds N --entry <入口>` 对冻结 commit 输出：每轮新增数、D/T/J 分层曲线、累计账本大小。
2. 缺字段的发现**必须**被拒绝入账，且拒绝原因可区分（不是一个笼统的 False）。
3. 退出码沿用 `core/routing/benchmark.py` 的既有语义：`0` 收敛（连续两轮去重后新增为 0）、`1` 仍有新增、`3` 基线失配（commit 或入口配置与基线不符——**不得跨基线比较**）。
4. 账本条目单调不减；重复执行同一轮不产生重复条目（幂等）。
5. 定向单元测试 + ruff + 类型检查真实通过（不用退出码 3 兜底——本项目 F/G 项已确立该条纪律）。

#### 实验验证（H2/H3）

| 项 | 内容 |
|---|---|
| 假设 | H2：去重后新增数随轮次几何衰减；H3：**J 类不衰减，D/T 类衰减** |
| 设计 | 冻结一个 commit，固定入口与配置，连续 N=40 轮；分别统计全部 / D / T / J 的 λ(n) |
| 拟合 | 对 D、T 分层拟合 `U·p·(1−p)^n`，报告估计的 U（全库可发现数）与 p（单轮命中率）及置信区间 |
| 指标 | λ(n) 曲线、U 与 p 的点估计与 CI、J 类 λ(n) 的斜率 |
| 证伪 | 若 **J 类 λ(n) 也显著衰减至 0**，则本文核心命题被推翻；若 D/T 分层也不衰减，则"覆盖抽样"解释不成立 |

**预注册要求**：沿用本项目既有 `*.prereg.md` 惯例（见 `.omx/artifacts/ab-quant-r7-prereg.md`、`ab-jet-weak-prereg.md`），在跑之前写下假设、N、拟合模型与证伪线，跑完不得改判据。

---

### R2 — 发现级语义去重与账本入库

#### 缺口证据

- `core/routing/benchmark.py` 已对 **routed universe** 做内容哈希指纹（`fingerprint = sha256 over CONTENT hashes only`，排除 mtime 与绝对路径），设计注释明确"posture 变化必须使所有基线失效，而不是静默跨 posture 比较"。
- **但"发现/优化点"这一层没有等价物**：没有任何机制判定"两条发现是不是同一个问题"。
- 后果物证：`optimization-plan.md` 与 `-p1/-p2/-auto-opt` 之间无法判断是否存在重复条目；p0 的 `C1–C3 命名冲突`与 p2 的 `P2-B2 ClaudeCode dedup`、`P2-B3 GrokBuild refactor` 是否部分重叠，**当前不可判定**。
- 外部同类事故（可迁移的教训）：某真实项目发布门禁跑 10+ 次未收敛，其根因之一即"台账只记 file+class，换个措辞或文件归属即被判为新发现"，且**台账存放于被 gitignore 的临时目录、每台机器重置**。

#### 需求

1. 实现发现判等：两条发现判等 ⟺ `claim_fingerprint` 相同 **或** 语义相似度 ≥ 阈值。
2. 阈值 knob 归属沿用本项目惯例：**不进 `RoutingConfig`**，用模块常量 + CLI flag（与 `behavior_consistency._BEHAVIOR_JACCARD_THRESHOLD`、`skill_promote` 的 miss knob 同例）。
3. **账本必须入库版本化**（提交到仓库，或明确落在被跟踪的路径）。若账本位于 gitignored 路径，等于没有账本——这是外部事故的直接教训，须在文档中显式声明。

#### 落点

`core/observability/finding_ledger.py` 内的 dedup 子模块 + 常量 + CLI flag；`scripts/measure_finding_convergence.py` 暴露 `--dedup on|off`（供 R7 的对照实验使用）。

#### 验收标准

1. 构造标注集：**≥30 组**"同一问题的多种措辞"（正例对）与 **≥30 组**"两个真不同问题"（负例对）；来源可用本项目历史 `optimization-plan*.md` + `gateN-*.md` 的人工标注。
2. 去重召回（正例对被判等）≥ 0.90；误合并率（负例对被判等）≤ 0.05。
3. 输出标定报告，含：正负例对数量、选定阈值、点估计与 95% CI、留出集上的表现。
4. **证据不足时的诚实降级（强制）**：若可用正负例对低于 30/30，报告必须标注"未标定起点"，并**不得**宣称阈值已标定——严格比照 `behavior_consistency.py` 现有写法（"决策带证据不足，0.5 维持为待验证起点"）。这是本项目已确立的文化，须延续。

#### 实验验证（H5）

| 项 | 内容 |
|---|---|
| 假设 | 观测到的"新发现"主要是**去重伪影**，而非真实缺陷增长 |
| 设计 | 同一语料、同一入口、N=10 轮，`--dedup off` 与 `--dedup on` 双组；其余完全一致 |
| 指标 | 两组的 λ(n) 曲线差异；去重后新增数的下降幅度与绝对量 |
| 证伪 | 若开/关去重对 λ(n) 无显著差异，则"去重伪影是主因"被推翻 |

---

### R3 — 强制发射偏差：空报告率度量（P0，建议最先做）

#### 缺口证据

- 本项目已具备构造"已知无问题"输入的完整能力：`scripts/eval_routing.py --hermetic` 的六步 hermetic posture（`docs/dev/routing-benchmark.md` 详述），可把机器相关输入全部中和，得到确定性、可复现的输入。
- 但**没有任何度量回答**："当输入确实无问题时，LLM 增强路径会不会如实报告'无问题'？"
- 该缺口直接决定项目内所有"已全部检查/无优化点/已验证通过"类结论的可信度。现有 `verify-result` 技能正文已确立"缺证据标 blocked、以代理自述代替证据不可接受"的原则，**但缺少支撑该原则的量化数据**。

#### 需求

构造 M 个经人工判定确实无问题的输入（建议：已通过 hermetic 确定性基线的用例、机械生成的样板配置、空 diff），走 LLM 增强分析路径，统计其产出"无新增/无需优化"的比率（空报告率），并给出二项 95% 置信区间。

#### 落点

新增 `scripts/measure_null_report_rate.py`；复用既有 hermetic posture 构造干净输入；**不修改** `core/routing/`、`core/skills/` 下任何现有逻辑。

#### 验收标准

1. 输出：M、空报告数、空报告率、二项 95% CI、每样本的原始产出留档。
2. CI 下端显著低于 1（例如 < 0.5）时，输出必须显式给出结论：**"无问题"类自述不可作为验收依据**。
3. 该结论若成立，须有对应的下游动作建议（不自动实施）：把"已全部修复完成/无优化点"类判定强制降级为 `unsupported`，并纳入 `verify-result` 的拒收语义。**是否实施需另行授权，本轮不自动改现有验证逻辑。**

#### 实验验证（H4）

| 项 | 内容 |
|---|---|
| 假设 | 存在"强制发射偏差"：即使输入干净，模型也倾向报出问题而非报"无问题" |
| 设计 | M ≥ 50 个已知干净样本 × ≥ 2 个模型后端（避免单模型结论） |
| 指标 | 空报告率 + 二项 95% CI；按模型后端分层 |
| 证伪 | 若空报告率 ≈ 1（几乎总能如实报告无问题），则"强制发射偏差"在本项目语境下不成立 |

**说明**：这是全部需求点中**成本最低、结论最清晰**的一条，且无论结论正负都有价值（正 → 改变验收语义；负 → 排除一种解释，收窄根因范围）。

---

### R4 — `behavior_consistency` 阈值 0.5 标定收口（P0，现成缺口）

#### 缺口证据（代码注释原文，非推测）

`src/vibesop/core/observability/behavior_consistency.py` 模块常量处记录：

> `_BEHAVIOR_JACCARD_THRESHOLD = 0.5`
> 占位起点（M12 设计 §阈值哲学 "bigram-Jaccard ≥ 0.5, 标定后固化"）。
> **gate M3 标定结果**（`.omx/artifacts/m3-behavior-calibration.md`）：cmspark 真实数据上候选簇内**同簇正例对 = 0**，**跨簇负例对 = 1** —— **决策带证据不足，0.5 维持为待验证起点，待更多平台 hook 数据后复检。**

同文件另记录一条**已知残留风险**（gate24 pi#5，标记 accepted）：

> 单工具 trace 的 bigram 集为空，不参与成对计数 —— 一个簇若夹着单工具离群 trace，`consistent` 判定可能对这类簇高估（**离群 trace 被静默排除而非拉低分数**）。序列提取侧不区分"平台无 hook"与"该 trace 恰好一次调用"，这是**诚实盲区，记录在案**。

**正例对 = 0、负例对 = 1，意味着阈值 0.5 在真实数据上从未被真正检验过。** 这不是缺陷指控——该状态已被如实记录，符合项目文化——但它是一个**明确的、可独立收口的、可实验验证的缺口**。

#### 需求

1. 补足标定数据：目标 **≥30 正例对、≥30 负例对**（跨簇负例对需从多个候选簇抽样，避免单簇偏差）。
2. 给出：选定阈值、点估计、95% CI、留出集上的 FPR / FNR。
3. 处置三种结果之一，**必须显式选择其一并在文档中写明理由**：
   - **已标定** → 阈值固化，去掉"待验证"标注；
   - **证据仍不足** → gate 输出保持 `unavailable`，**不得用 `consistent` 兜底**（诚实降级优先于给绿灯）；
   - **降级为 advisory** → 不再参与任何硬判定。
4. 修掉"单工具 trace 被静默排除"的诚实盲区二选一：**要么**显式计入（如定义单元素集与空集的相似度语义），**要么**在输出与展示层暴露"被排除的 trace 数量"，使其可见。

#### 落点

`src/vibesop/core/observability/behavior_consistency.py`、`scripts/calibrate_behavior_threshold.py`、新增/更新定向测试；标定报告归档至 `.omx/artifacts/`（沿用现有惯例）。

#### 验收标准

1. 标定报告含：样本构造方法、正/负例对实际数量、阈值、CI、FPR/FNR。**样本量不足时不得输出"已标定"结论。**
2. 三态语义（`consistent` / `divergent` / `unavailable`）在数据不足时**必须**落到 `unavailable`。
3. 被排除 trace 的数量在输出中可见（若选择"显式计入"路线，则需给出单元素集的语义定义与测试）。
4. 定向测试 + ruff + 类型检查真实通过。

#### 实验验证

| 项 | 内容 |
|---|---|
| 假设 | 0.5 在补足样本后仍不可用（即真实数据下正负例对相似度分布高度重叠） |
| 设计 | 构造正/负例对，计算 bigram-Jaccard 分布，画 ROC；对多组候选阈值算 FPR/FNR |
| 指标 | 分布重叠度、最佳阈值、该阈值下的 FPR/FNR、CI |
| 证伪 | 若某阈值能以 FPR ≤ 0.1 且 FNR ≤ 0.3 分离两类，则假设被推翻（阈值可用） |

---

### R5 — 提出者/验证者同源检测

#### 缺口证据

- 项目**已在实践中做异构复审**：`.omx/artifacts/` 中每个 gate 都并存 `gateN-claude.md` 与 `gateN-pi.md`（外加 `gateN-instructions.md`、`gateN.diff`），共 45+ 轮。这是宝贵的、已完成的事实基础。
- `docs/specs/2026-09-09-verification-contract.md` 已确立原则：**"模型评审与机器验收分别记录"**、**"不能以代理自述代替证据"**。
- **但缺少运行时约束**：没有任何地方记录/检测"验证者与提出者是否同源"，同源时验证结论不降级。

#### 需求

在验证记录中落以下字段并据此判定：`proposer_model_id`、`verifier_model_id`、`information_boundary`（验证者可见信息是否严格少于提出者）。**同源或信息边界不成立时，验证结论标记为 `unsupported`，不得判 passed。**

#### 落点

`src/vibesop/core/observability/promote_verifier.py` 或实际承载验证记录的模块 + 定向测试；字段语义若影响 `verify-result` 契约，须同步 `docs/architecture/verification-contract.md`（该文件由 D 路建立，**改动前先确认归属**）。

#### 验收标准

1. 验证记录含上述三字段；缺失时按"不成立"处理（fail-closed，不默认通过）。
2. 同源记录**不得**被判 passed，且拒绝原因与"证据不足"可区分。
3. 不改动现有 verify-result 的准入语义（新增字段是增量）。

#### 实验验证

| 项 | 内容 |
|---|---|
| 假设 | 同源验证的"独立复现率"显著低于异构验证 |
| 设计 | 复用既有 gate 语料（45+ 轮 claude × pi 双复审）做回测：把"同源"设为对照臂，比较独立复现率与假阳性放行率 |
| 指标 | 独立复现率、效应量、假阳性放行率 |
| 证伪 | 若同源与异构无显著差异，则"必须异构"缺乏数据支撑（仍可作为保守默认，但须标明是约定而非实证） |

---

### R6 — 标准漂移指纹扩展

#### 缺口证据

`core/routing/benchmark.py` 的指纹当前覆盖：registry、skill-definition 文件、dataset、canonical posture（`HERMETIC_POSTURE`）。设计注释明确：

> changing the posture (re-enabling a layer, unpinning the universe) must invalidate all baselines, not **silently compare across postures**.

**但以下会改变"什么叫问题"的输入尚未纳入指纹**：

- 提示词模板：`src/vibesop/adapters/templates/**`（含 `rules/*.md.j2`、`docs/*.md.j2`、`skills/SKILL.md.j2`）
- `core/skills/**` 技能正文（仅部分经 skill-definition 路径被覆盖，需核实是否完整）
- 注入知识 / `.vibe/prompts/`、`.vibe/rules/` 下的运行期内容

后果：只改一个提示词措辞即可在不触发任何基线失效的情况下改变评审/路由产出——**这正是"尺子在变"的工程形式**。

#### 需求

把上述输入纳入指纹；漂移必须导致基线失效（exit 3，refresh 而非静默比较）。

#### 落点

`core/routing/benchmark.py` 的指纹输入集 + `docs/dev/routing-benchmark.md` 同步说明；新增/更新 `tests/test_routing_baseline.py`。

#### 验收标准

1. 只改一个提示词措辞 → fingerprint 变化，`--check` 退出 3 且提示"标准已漂移，需重标定"。
2. 不改任何纳入项 → fingerprint 跨机器、跨 checkout 位置稳定（沿用现有"排除 mtime 与绝对路径"原则）。
3. 已有的 39 题固定路由题集预期与结果**逐项保持不变**（沿用 `verification-contract` B 补充的要求）。

#### 实验验证（H7）

| 项 | 内容 |
|---|---|
| 假设 | 标准漂移对产出的效应量可观（不可忽略） |
| 设计 | A/B：仅改提示词措辞/条目顺序/注入知识各一组，其余固定；对同一语料跑同轮次 |
| 指标 | 产出差异的效应量 + 方差分解（漂移项占总方差比例） |
| 证伪 | 若效应量 ≈ 0，则无需将提示词纳入指纹 |

---

### R7 — 净发现度量与决策收敛判据

#### 缺口证据

- `gate1..gate45+` 构成"评审 → 修复 → 再评审"的长序列，`optimization-plan` 四连发同样如此，**但没有"净发现数是否下降"的度量**，无法回答"这个循环是否正在收敛"。
- 项目已有成熟的 exit-code 门禁范式（`benchmark.py` 的 0/1/3）与 report-only vs hard-gate 的明确区分（`docs/dev/routing-benchmark.md`：`Routing Eval (report-only)` 永不做门禁，因其数字依赖机器）。

#### 需求

**(a) 净发现度量**：每次修复后重跑基线，记录净发现数（按 KLOC 归一），形成时间序列。

**(b) 决策收敛判据**：以 **severity × 佐证数矩阵**替代"零新增发现"作为门禁判据：

| 严重度 | 阻断条件 | 依据 |
|---|---|---|
| CRITICAL | 任意 1 个独立来源报出即阻断 | 漏掉代价过高 |
| HIGH | 任意 1 个独立来源报出即阻断 | 同上 |
| MEDIUM | 需 ≥2 个独立来源佐证，否则只登记不阻断 | 噪声主要集中于此 |
| LOW | 需 ≥2 个独立来源佐证，否则只登记不阻断 | 同一问题的多种措辞 |

**强制约束：记录与阻断解耦，零丢失。** 所有发现一律登记，矩阵只决定"是否阻断"，不决定"是否记录"。任何"未通过佐证即丢弃"的实现视为验收失败。

#### 落点

新增 gate 模块（**顺延现有 gate 序列，以仓库当前最大 gate 号为准**）+ `scripts/` 下度量脚本 + 定向测试。判据配置须为**人工所有**的配置项，**不做自动调参**（沿用项目"配置人工拥有、变更留痕"的既有取向）。

#### 验收标准

1. **关键验收（本条的核心）**：同一语料连续 N 次运行，**决策一致率达 100%，同时发现集合的 Jaccard < 1**。前者证明决策收敛，后者证明并非因发现收敛而"假收敛"。若决策一致率 < 100%，验收不通过。
2. 零丢失：矩阵判定为非阻断的发现**必须**出现在登记输出中。
3. 零新增发现时，退出码与既有 `benchmark.py` 语义一致（0 通过 / 1 有新增 / 3 基线失配）。
4. 提供"误阻断 / 误放行"率，基于历史语料回测（见下）。

#### 实验验证（H8）

| 项 | 内容 |
|---|---|
| 假设 | 门禁**决策**可以收敛，即使**发现**不收敛 |
| 设计 | 回测：以 `optimization-plan` 四连发 + `gate1..gateN` 历史语料为输入，跑 N 次多模型面板，套用多组 severity/佐证阈值配置 |
| 指标 | 决策稳定所需轮数、跨配置的决策一致率、误阻断率、误放行率（以历史已确认修复项为真实答案） |
| 证伪 | 若决策仍不收敛，或误放行率高到不可接受，则矩阵方案被推翻 |

---

## 3. 与既有验收文化的一致性声明

为使本文可直接进入项目流程，以下约束已内建：

1. **不以代理自述代替证据**（`verification-contract` 既有原则）：R1 要求 `evidence_anchor` 必填，R5 要求同源验证降级为 `unsupported`。
2. **证据不足时诚实降级，不给绿灯**：R2 的"未标定起点"标注、R4 的 `unavailable` 不兜底，均照抄现有 `behavior_consistency.py` 的写法。
3. **不放宽门禁换绿灯**：R1/R7 的退出码复用既有 0/1/3 语义；类型检查不使用退出码 3 兜底（`verification-contract` F/G 项已确立）。
4. **report-only 与 hard-gate 严格区分**：R1/R3 初期一律 report-only，取得标定证据后方可讨论是否升为 gate（沿用 `routing-benchmark.md` 对二者的界定）。
5. **不做全局自动注入**：所有接入点显式调用，不读环境变量决定行为。
6. **knob 归属约定**：新阈值不进 `RoutingConfig`，用模块常量 + CLI flag。
7. **实验预注册**：影响结论的实验先写 `*.prereg.md`（沿用 `ab-quant-r7-prereg.md` 惯例）。

---

## 4. 非目标（明确不做）

- **不追求"零新增发现"**：J 类空间无限，该目标不可达；追求它是本现象的一部分成因而非解法。
- **不把通用验收偷偷换成代码评审**（`verification-contract` 既有禁令）。
- **不扩大到自动经验进化、全文采集、多代理收益证明**（同上禁令）。
- **不自动调参**：所有 severity/佐证阈值、去重阈值均为人工所有。
- **不在本文档中声称任何实现已完成**：本文是提案，R1–R7 全部未实现、未测试。

---

## 5. 已知风险与诚实盲区

1. **R1 的 λ(n) 拟合需要足够轮次**：N=40 是预估；若真实 U 很小，衰减会在少数轮内完成，拟合 CI 会过宽——届时须报告"U 上界"而非点估计。
2. **R2 的标注集需人工投入**：≥30 正例对 + ≥30 负例对是硬成本，且标注者需理解 D/T/J 分类；建议先做小样本 pilot 估标注一致性（可算 Cohen's κ）。
3. **R3 的"已知干净样本"构造是最大难点**：任何"人工判定无问题"的样本都带主观性；建议用**机械生成**的样板（无逻辑分支、无依赖、无安全面）以最大化客观性。
4. **R4 的正例对依赖平台 hook 数据**：若 hook 数据仍不足，"证据仍不足"是合法结论，但必须显式选择不兜底路线。
5. **R5 的历史语料回测有混杂**：45+ 轮 gate 的模型组合并非随机分配，存在选择偏差；回测结论须标注为"观察性，非因果"。
6. **R7 的真实答案集不完备**："以历史已确认修复项为真实答案"存在幸存者偏差（未修复的项不在答案集中）。

---

## 6. 一句话总结

**不要把"没有更多优化点"当作验收标准——它不可反驳、无法测量、且被本项目的 `optimization-plan` 四连发与 45+ 轮 gate 实践反复证伪；换成"对 D∪T 检查表已穷尽，且无新增 J 类被 ≥2 个独立来源复现"，这条路可测、可门禁、可实验。**
