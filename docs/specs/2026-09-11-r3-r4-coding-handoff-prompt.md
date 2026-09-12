# R3 + R4 编程接力任务提示词

> 用途：把本文件**从下方分隔线之后**的正文整段复制给终端编程助手（Claude Code / Codex / Cursor 等）。
> 生成日期：2026-09-11 · 基线 commit：`60fd0487`
> 配套文档：`docs/specs/2026-09-11-optimization-convergence-requirements.md`（需求全集 R1–R7）
> 本任务只做 **R3、R4 两项**（P0），其余五项不在本轮范围。

---

## 任务：实现「空报告率」度量（R3）与「行为一致性阈值就绪度检查」（R4）

### Goal

在一个已有成熟工程纪律的 Python 代码库中，补齐两个**可实验验证**的小交付物。二者共同的目的是：把"AI 说已经全部检查/没问题"这类**不可反驳的断言**，转化为**可测量、可复现、可证伪**的数字。

具体两项：

1. **R3 — 空报告率度量**：回答"当输入确实无问题时，LLM 增强分析路径会不会如实报告'无问题'？"
2. **R4 — 阈值就绪度检查**：把 `_BEHAVIOR_JACCARD_THRESHOLD` 复检的触发条件从"靠人记得"变成"可机器检查"。

**本任务不授权你做任何"顺手优化"。** 除下方列出的文件外，不得修改任何既有代码。

### Workspace

- 仓库：`/Users/huchen/Projects/vibesop-py`
- 基线 commit：`60fd0487`（开工前先 `git rev-parse --short HEAD` 核对；不一致就停下来问，不要跨基线工作）
- 语言/工具：Python 3，`ruff`、类型检查脚本、`pytest`
- 未跟踪的既有文件（**不是你的产出，不要动**）：
  - `docs/specs/2026-09-11-optimization-convergence-requirements.md`
  - `scripts/measure_null_report_rate.py`（R3 骨架，见下）
  - `scripts/check_behavior_calibration_readiness.py`（R4 骨架，见下）

### 必读（开工前，按顺序）

1. `docs/specs/2026-09-11-optimization-convergence-requirements.md` — 需求全集，含 R3/R4 的缺口证据、验收标准、实验设计
2. `.omx/artifacts/optimization-convergence-r3-prereg.md` — **R3 预注册（判据已写死，不得改）**
3. `.omx/artifacts/optimization-convergence-r4-prereg.md` — **R4 预注册（判据已写死，不得改）**
4. `.omx/artifacts/m3-behavior-calibration.md` — R4 的前序标定报告（**必读，理解为什么现在没法标定**）
5. `src/vibesop/core/observability/behavior_consistency.py` — R4 的目标模块（**只读，不得修改**）
6. `docs/specs/2026-09-09-verification-contract.md` — 本项目的验证契约（**纪律来源**）
7. `docs/dev/routing-benchmark.md` + `src/vibesop/core/routing/benchmark.py` — 退出码惯例与指纹惯例的来源
8. `scripts/calibrate_behavior_threshold.py` — **已存在的标定脚本，不要重写**
9. `scripts/calibrate_discovery_threshold.py` — 标定脚本的纪律范式（分布 + 决策带 + 刀刃对，不拍点估计）

### 背景（一段话说清为什么做这个）

对同一份代码库反复做 AI 评审，每次都能发现"新优化点"；某次宣称已全部修复完成，下次重新打开又冒出来。根因不是模型不行：真实新增（D 类规则违反 + T 类可检验问题）是有限集合、会衰减；而主观建议（J 类）空间无限、永不衰减，且换个措辞就会被记成"新发现"。**结论：追求"没有更多问题"不可达，必须把"决策是否收敛"从"发现是否收敛"中解耦。** R3 提供支撑该结论的量化数据，R4 把一个已记录的待收口项收口。

### 交付物（只允许新增/修改这些文件）

#### D1 — 完成 `scripts/measure_null_report_rate.py` 的真实 LLM 接线

骨架**已存在且 harness 已被验证可用**（`--runner stub` 自检通过，Wilson CI、分层统计、产物落盘、退出码均正常）。你要做的只有一件事：

- 实现 `make_llm_runner()`，替换其中的 `TODO(r3-wire)`。
- 接线约束：
  - **只读调用**，不得写回任何生产状态；
  - 固定温度与配置，并把配置哈希写入产物（`--config-hash`）；
  - 必须调用**既有**的 LLM 增强分析路径（候选入口：`scripts/eval_routing.py --hermetic` 的 posture 构造 + 既有 adapter/templates 调用链），**不要新写一套 LLM 客户端**；
  - 显式调用，不做全局自动注入。
- 接线完成后：把实际入口与配置回填到 `r3-prereg.md` §6，并删除 `TODO(r3-wire)`。
- **同时新增** `--samples-synth` 子命令或等价能力，用于按 prereg §3 生成 A 组（机械样板）样本 ≥30 条；B/C 组样本来源见 prereg。

#### D2 — 完成 `scripts/check_behavior_calibration_readiness.py` 的门槛计算

骨架**已存在**（CLI、四条门槛定义、退出码、JSON 输出均就绪）。你要做的：

- 实现 `check_readiness()`，替换其中的 `TODO(r4-wire)`。
- **硬性要求：必须复用 `core.observability.behavior_consistency` 的既有口径**（`tool_sequence_items_for_tasks`、`_bigrams`），**禁止在本脚本内复写第二套实现** —— 双处定义会让两个数字互相矛盾（gate24 pi#7 单一来源原则）。
- 若既有函数签名与本脚本所需不匹配，**不要改既有函数**；在本脚本内做适配层，并在注释里写明适配理由。
- 四条门槛与阈值在 `r4-prereg.md` §1 已写死（正例对 ≥30、负例对 ≥30、producer ≥2、至少 1 簇 ≥2 条序列）——**不得调整**。

#### D3 — 测试

新增，命名沿用既有惯例：

- `tests/core/observability/test_behavior_calibration_readiness.py`
- `tests/test_measure_null_report_rate.py`（或放既有 scripts 测试所在位置，先确认惯例）

测试必须覆盖：

1. `wilson_interval` 的边界：`n=0` 抛 `ValueError`（**不得**返回 `(0.0, 1.0)` 让上游误判）；`k=0`、`k=n` 的区间。
2. **fail-closed**：有效样本 `< min_samples` 时 `build_report` 给出 `SAMPLE TOO THIN` 且 `main` 返回 **2**。
3. `--runner llm` 未接线时返回 **2**（不得静默成功）。
4. 三条判定线的分界：CI 下端 ≥0.90 → FALSIFIED；CI 上端 <0.50 → SUPPORTED；否则 INCONCLUSIVE。
5. R4 门槛：四条中任一条不满足 → `ready is False` 且 `main` 返回 **1**。
6. 缺字段样本 → `load_samples` 抛 `ValueError`（**不得静默跳过**，跳过会让 M 悄悄变小）。

> **注意**：`tests/core/observability/test_no_bare_asserts.py` 是既有约束，你的测试必须符合它。

#### D4 — 文档

- 若 `docs/` 下需要登记新脚本，按既有惯例更新对应索引（先确认是否存在此类索引，没有就**不要新建**）。

### 约束（违反即视为交付失败）

1. **不得虚构任何数字。** 不得在代码、注释、文档、提交信息或你的回复中写入任何未经真实执行的测量结果。R3 的 `p̂` / CI、R4 的对数 / FPR / FNR，**在你没有真实数据时一律写"待填"**。
2. **不得放宽门禁换绿灯。** 退出码语义照抄既有惯例（0 正常 / 1 未就绪 / 2 样本不足 / 3 配置失配）。
3. **不得用退出码 3 兜底类型检查或测试。** `docs/specs/2026-09-09-verification-contract.md` F/G 项已确立此纪律。
4. **不得改判据。** 两份 prereg 里的判据、阈值、证伪线均已在开工前写死。若你认为判据有误，**停下来提出**，不要自行修改。
5. **不得修改** `behavior_consistency.py`（R4 只做就绪度检查，标定是后续独立工作）。
6. **新阈值不进 `RoutingConfig`**，用模块常量 + CLI flag（沿用 `behavior_consistency` / `skill_promote` 的 knob 归属惯例）。
7. **不做全局自动注入**，不读环境变量决定行为。
8. **证据不足时诚实降级。** 数据不够就输出"证据不足"，并保持 gate 为 `unavailable`；**不得**用 `consistent` 兜底。
9. **不引入新依赖**（Wilson CI 已用 `math` 闭式实现，不要引入 scipy）。
10. 隐私：R4 只读 span 的 `name`，**绝不读 `input_data` / 参数值**。

### 验收标准（机器可检查，逐条自证）

| # | 验收项 | 自证方式 |
|---|---|---|
| A1 | `ruff check scripts/ tests/` 通过 | 贴出命令与退出码 |
| A2 | 既有类型检查脚本通过（**非** exit 3 兜底） | 贴出命令与退出码 |
| A3 | `pytest tests/ -k "readiness or null_report"` 全绿 | 贴出命令与结果摘要 |
| A4 | `--runner stub` 自检：harness 可用且 stderr 有 stub 警告 | 贴出命令与输出 |
| A5 | `--runner llm` 在未接线时 exit 2 | 贴出退出码 |
| A6 | 样本不足时 exit 2 且判定为 `SAMPLE TOO THIN` | 贴出退出码与 verdict |
| A7 | 就绪度脚本在门槛不满足时 exit 1 | 贴出退出码 |
| A8 | `git status --short` 只出现约定文件 | 贴出输出 |
| A9 | 既有测试未回归 | 贴出相关测试结果 |
| A10 | 回填 prereg §6 时**只写"待填"或真实结果**，无编造 | 贴出 diff |

### 非目标（明确不许做）

- 不实现 R1/R2/R5/R6/R7（发现账本、语义去重、同源检测、指纹扩展、决策收敛判据）——本轮只做 R3+R4。
- 不重新标定 `_BEHAVIOR_JACCARD_THRESHOLD`（就绪度未通过就不该标定；通过了也只是"可以开跑"，标定是后续独立任务）。
- 不修改 `behavior_consistency.py` 的任何行为。
- 不追求"零新增发现"。
- 不把通用验收偷偷换成代码评审（`verification-contract` 既有禁令）。
- 不自动调参。

### 已知陷阱（前人踩过的，别再踩）

1. **`.omx/` 在 `.git/info/exclude` 第 7 行**：新文件放进去会被**静默忽略**（已有 356 个 `.omx/` 文件是历史强制加入的）。你若新增 artifact，必须 `git add -f`，否则它不会进版本控制 —— 这正是"账本放在被忽略路径等于没有账本"的翻车点。
2. **`/tmp` 不在 MCP 允许目录内**（实为 `/private/tmp`），写临时文件注意。
3. `behavior_consistency.py` 已有三态语义（`consistent` / `divergent` / `unavailable`），且 `_VALID_BEHAVIOR_STATES` 是**单一来源**的定义（gate24 pi#7：不双处定义）—— 若需引用，从该模块 import，不要重新声明。
4. 单工具 trace 的 bigram 集为空、不参与成对计数，这是**已知且已接受**的盲区（gate24 pi#5）。R4 预注册 §4.1 要求本轮二选一收口（显式计入 / 暴露可见），**不允许"保持现状"**。
5. 标定数据是按 trace 分组键防泄漏的（同一 trace 的任何配对既不入正例也不入负例）—— 若你的就绪度统计绕过该规则，会得到虚高的正例对数。

### 交付回报格式（Handback）

完成后用如下结构回报，**逐条给证据，不要只给结论**：

```
## 基线
commit: <git rev-parse --short HEAD>

## 改动文件
<git status --short 原文>

## D1 接线
- 实际调用入口: <路径 + 函数>
- 固定配置与 config-hash: <值>
- TODO(r3-wire) 是否已删除: 是/否

## D2 门槛计算
- 复用了哪些既有函数: <清单>
- 是否新增了第二套实现: 是/否（应为否）
- 适配层理由（若有）: <文字>

## 验收自证
A1: <命令> → <退出码>
A2: ...
A3: ...
（A4–A10 同）

## 未完成 / 阻塞
<如实列出。没有就写"无">

## 我无法验证的部分
<如实列出。例如：没有真实 LLM 凭证所以 R3 未产出任何数字>
```

**最后一条最重要**：如果你因为缺少凭证、数据或环境而**没有**产出某些数字，就在"我无法验证的部分"里**明确写出来**。本项目宁可拿到"未完成"，也不要拿到一个看起来完成、实际编造的交付。你自己声称的"已完成"，在拿到工具证据之前一律不成立。
