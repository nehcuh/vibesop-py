# Harness 验证语义优化路线图 — default-deny 翻转与可达性补全

> **日期**: 2026-11-02
> **状态**: 🗺️ 路线图（评审完成，未实施；本文档不含代码改动）
> **版本**: 8.8.0
> **评估基线**: `main`（8.7.1 发版后）
> **触发链路**: X 文章《Unlock Opus 5.5: The Harness Guide for Agents That Actually Ship》（Trackmind, 2026-10-23）→ 公式映射 → Claude Code 六路独立子代理只读取证（review_readonly）→ 本路线图
> **作者**: 用户（决策）+ CMspark（映射与汇总）+ Claude Code（file:line 取证）

---

## 📋 背景与问题

一篇行业实践文章提出 agent harness 七条公式（Task Contract/Done when、Map not manual、Evidence gate、权限外置、失败分类重试、状态外置、教训→基建）。初步映射后经 Claude Code 六路独立子代理对疑点 A–E 逐路取证，结论：

**VibeSOP 的 harness 骨架已齐（L1 ✅、L2 强、L3 大半），差距不在「缺组件」，而在两类问题：**

1. **验证语义默认放行**（P0）：三处判定点把「非失败哨兵的任意输出」当作成功，evidence gate 名存实亡；
2. **形式上存在但实战不可达**（P1）：ESCALATE 死代码、失败不分类、done_when 无机器判据、OutputSchema 死代码、验证环仅 adversarial 模式生效。

本路线图按 成本/收益/依赖 排出五个 Phase，本文档只定方向与验收标准，不含实施。

---

## 🔬 评估方法与证据边界

**取证**：Claude Code（review_readonly 档）派 6 路独立子代理（疑点 A–E 各一路 + 整体架构对照），全部 file:line 级证据，未修改任何文件。B/E 与架构对照路在「同错停」判定上有一处分歧，已用代码证据裁决（见 Phase 2）。

**边界与免责**：

| 项 | 说明 |
|---|---|
| 文章出处 | 标题党称「Anthropic 论文」，实际引用的是 LangChain Terminal Bench 与 OpenAI Codex 实验的二手转述；**应引为行业共识实践，非 Anthropic 论文**。作者自报 8/20→16/20 数字无从验证 |
| 证据复核 | 本报告所有 file:line 为只读评审结论，**动工前须人工 diff 复核**，尤其 P0 三处（翻转默认值会改变现有测试预期） |
| 未覆盖 | `workflow_engine.py`（约 1100 行）未逐行通读但判定路径已覆盖；VerifierAgent 仓外 API 消费者未验证；kimi/pi/opencode 等 adapter 的 permissions 生成未逐一穷尽 |

---

## 🧭 Level 现状判定

| 级别 | 判定 | 依据 |
|---|---|---|
| L1（contract+map+tools） | ✅ 已实现 | 计划/步骤结构、技能体系、根文件索引（产物侧） |
| L2（state+checks+bounded loop） | 强 | checks 与 bounded loop 已实现；state 有 JSONL 计划状态 + resume（`plan_tracker.py:98-156`），缺「风险/下一步」叙事字段 |
| L3（permissions+traces+recovery+审批门） | 大半 | traces（`tracer.py`）、recovery（`reorchestrator.py`）、审批门（`--guided` 人审）✅；permissions 仅计划级 TrustLevel 三档，**无工具级三档**（`core/loop/models.py:215-222` 官方注释 "Not yet implemented"） |

---

## 🚀 Phase 1 · P0 止血：default-deny 翻转（1 个 PR，最小 diff）

**目标**：验证判定从「白名单式放行」翻转为「默认拒绝」，使 evidence gate 成立。这是后续所有验证增强的地基。

| # | 改动点 | 现状（file:line） | 目标 |
|---|---|---|---|
| 1 | VerifierStatus 默认值 | `core/orchestration/verifier.py:60-63`：`status` Pydantic 默认 = **PASSED** | 去默认值，或默认 ERROR |
| 2 | DebateProtocol 解析失败默认 | `core/orchestration/collaboration_protocol.py:327-338`：解析失败 → `passed=True` | 解析失败 → `passed=False` |
| 3 | 步骤成功判定 | `core/orchestration/verification_loop.py:49-52` + `agent/step_runner.py:120-126`：非 `blocked:`/`failed:` 哨兵前缀的任意散文 = SUCCESS | 要求正向判据（`passed:`/枚举匹配）才算成功 |

**验收标准**：
- 新增回归测试：无证据输出、无哨兵散文、解析失败三类输入**不得**记 SUCCESS/PASSED；
- 现有测试基线同步更新并说明每处预期变化的原因。

**风险与缓解**：
- 翻转默认值改变现有测试预期 → 先盘点受影响测试清单再动手；
- `verification_loop.py:49-52` 的 `is_acceptance_failure` 是共享谓词（execution_protocol 亦引用），语义翻转需保持哨兵侧不变、只收紧成功侧。

---

## 🚀 Phase 2 · P1 可达性与重试语义（本迭代主线）

### 2.1 激活 ESCALATE 死分支

- 现状：`verification_loop.py:134-179` 首次 failed → TERMINATE 即 break，`escalation_threshold=2`（`:64-71`）永不可达；ESCALATE 仅落为 error 字符串 "user intervention required"（`:420-421`），无升级通道。
- 目标：连续失败 ≥ 阈值走 ESCALATE；ESCALATE 接真实出口（写 plan_tracker 状态 + CLI 呈现给人）。

### 2.2 失败分类枚举 + 同错签名停

- 新增 FailureCategory 枚举接入 decide_action；错误签名（type + message 归一化哈希）比较，**同签名两次 → ESCALATE**。
- **复用已有资产**：`core/loop/executor.py:64-106`（cron 子系统）已有 TRANSIENT/PERMANENT 关键词分类（timeout/429→重试；perm-denied/bad-args→不重试），迁移到编排链路，不是从零建。
- 注意与 `core/loop/models.py:210-214`（连续失败 ≥3 → DEAD）语义对齐：那是「状态类别计数」，非「同一错误」——本项补的正是同一性判断。

### 2.3 验证环扩域（产品决策点）

- 现状：验证环仅 `workflow_pattern=="adversarial"` 生效（`verification_loop.py:362`），SEQUENTIAL/PARALLEL 计划无验证环。
- 建议：至少让含 fallback / 低信任（QUARANTINE）步骤的计划默认走验证。

**顺手修复**：`agent/step_runner.py:7` docstring 宣称 "Configurable error recovery (skip / retry / abort)"，实际只有 skip/abort——修文档或补实现，二选一。

---

## 🚀 Phase 3 · P1 地基：done_when 契约化（可拆两期）

**一期（字段 + 语义）**：
- `core/models.py:319-410` ExecutionStep（24 字段无验收判据）加可选 `done_when`，类型三选一：sentinel / command / section-schema；
- `task_decomposer.py:22-31,105-129` 分解 prompt 增加该键的生成；
- `verifier.py:105-110,233-281` verify rubric 从步骤契约取判据，替代通用四维打分。

**二期（机器执行）**：
- 激活 `collaboration_protocol.py:52-65` + `models.py:925` 的 **OutputSchema 死代码**（定义后全仓无实例化、无校验消费）做最小校验；
- 补 `models.py:1078-1103` 完成判据的机器解析：当前 `<!-- [StepCompleted:N] -->` marker 仅生成、无判定点。

完成后文章公式 ①（TASK CONTRACT 的 Done when）才真正闭环。

---

## 🚀 Phase 4 · P2 治理与上下文预算（穿插做）

| 项 | 现状 | 动作 |
|---|---|---|
| 根文件瘦身 | 仓库 `CLAUDE.md`=101 行、`AGENTS.md`=109 行（手册型）；仅 `PROJECT_CONTEXT.md`=30 行合规 | 压成 ≤40 行索引型，细节外移到 docs/ |
| 生成配置预算 | `adapters/templates/claude-code/CLAUDE.md.j2`=72 行（索引型✓），但 rules/ 常驻 ≈202 行，每会话常驻 ≈280 行 | builder 加行数预算机制 |
| 事故追溯门槛 | `core/feedback.py:18-28` FeedbackRecord 无 incident 字段；`core/instinct/learner.py:74,141` 晋升纯统计阈值（≥3 次+0.6 / ≥5 次+0.8） | 加可选 `incident_ref`；auto-promote 门槛要求非空。现状溯源只存在于注释惯例（`routing_pending.py:14` 引用 M7 事故）与人审关（`skill_promote.py:28` 未审不注入），未制度化 |

---

## 🚀 Phase 5 · 战略：工具级权限三档（单独立项）

文章公式 ④「The model recommends. The harness decides. The tool executes.」的完整形态：

| 层 | 现状（全部二态 allow/block，fail-closed） | 目标 |
|---|---|---|
| security 层 | `security/rules.py:13-26` RiskLevel 是严重度非权限档；`scanner.py:416-419`、`path_safety.py:120-126` bool/raise | 引入 PermissionTier（allow / require_approval / deny） |
| hook 层 | `adapters/hook_based.py:175-185` 仅注入 additionalContext，无 permissionDecision；"human confirmation"（`routing-protocol.md.j2:12,23`）是模型指令非 harness 强制 | hook 输出 permissionDecision |
| adapter 层 | `adapters/claude_code.py:580-586,708-745` settings permissions 仅 allow 数组 | 生成 ask/deny（Claude Code 支持 ask/deny 语法） |

设计要点（来自文章）：**closed lane ≠ very high threshold**——阈值会被赶时间的人调低，封死的车道保持封死（如 delete_data/rotate_credentials/publish_global/merge main）。改动横跨 security/ + adapters/ + hooks/，走正常立项流程，本路线图不展开。

---

## 📈 完成后的定位变化

```
现在          L1 ✅ | L2 强（checks/loop/state 大半）      | L3 大半（缺权限引擎 + 验证语义有洞）
Phase 1-2 后  L2 完整（默认拒绝 + 有界重试 + 真实升级通道）
Phase 3-5 后  L3 完整（契约化验收 + 事故可追溯 + 工具级权限）
```

---

## ✅ 不需要动的部分（相悖发现）

优化火力应集中在验证语义与可达性，以下**超过**文章要求的部分保持不动：

1. **状态外置（修法⑥）**：哨兵词表 + 状态机 + 结构化注入（`skill_injector.py:819-828`、`plan_executor.py:94-112` fallback 步骤禁装技能、`plan_tracker.py:98-156` JSONL 跨进程状态 + resume）——机器态部分已超过文章要求，仅缺「风险/下一步」叙事字段（并入 Phase 2.1 的 ESCALATE 出口顺带补）。
2. **反幻觉防线**：文章单条 "If blocked→write STATE.md" 指令，本项目已是多层结构，无需改。
3. **定位本身**：`docs/POSITIONING.md` 五层定位与七修法同构，仓内已有 `jevharness-integration-assessment.md` 验证文化——本项目不只是实现者，是实证研究者。

---

## 🔗 建议的验收链

每个 Phase 合并前：
1. 人工 diff 复核本路线图引用的 file:line（评审结论 ≠ 当前 HEAD 事实）；
2. 新增回归测试先行（尤其 Phase 1 的三类默认放行输入）；
3. CHANGELOG 记录语义变化（default-deny 是 breaking change，需 minor 版本 + 迁移说明）；
4. 走既有对抗复审流程（参考 8.7.1 的 kimi 对抗复审先例）。
