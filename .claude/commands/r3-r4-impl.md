---
description: 实现 R3 空报告率度量 + R4 阈值就绪度检查（含硬性约束与验收自证）
argument-hint: [可选：额外约束或范围裁剪]
allowed-tools: Read, Grep, Glob, Edit, Write, Bash(uv run *), Bash(git status), Bash(git rev-parse *), Bash(git add -f *), Bash(git diff *)
---

# 任务：实现 R3 空报告率度量 + R4 阈值就绪度检查

> 项目：VibeSOP（`/Users/huchen/Projects/vibesop-py`）
> 基线 commit：`60fd0487` — 开工前先 `git rev-parse --short HEAD` 核对；
> **不一致就停下来问我，不要跨基线工作。**
> 补充约束（若有）：$ARGUMENTS

---

## 第一步：先读，不要先写

按顺序读完这 9 份，其中第 2、3 份是**判据**，第 4 份解释了为什么现在标定不了：

1. `docs/specs/2026-09-11-optimization-convergence-requirements.md` — 需求全集，看 R3、R4 两节
2. `.omx/artifacts/optimization-convergence-r3-prereg.md` — **R3 预注册，判据已写死**
3. `.omx/artifacts/optimization-convergence-r4-prereg.md` — **R4 预注册，判据已写死**
4. `.omx/artifacts/m3-behavior-calibration.md` — R4 前序报告（**必读**）
5. `src/vibesop/core/observability/behavior_consistency.py` — R4 目标模块（**只读**）
6. `docs/specs/2026-09-09-verification-contract.md` — 验证契约（纪律来源）
7. `docs/dev/routing-benchmark.md` + `src/vibesop/core/routing/benchmark.py` — 退出码与指纹惯例
8. `scripts/calibrate_behavior_threshold.py` — **已存在，不要重写**
9. `scripts/calibrate_discovery_threshold.py` — 标定脚本的纪律范式

读完先用 **plan mode（Shift+Tab）** 给我一份实施计划，经我确认后再动手。

## 第二步：理解为什么做这个

对同一份代码库反复做 AI 评审，每次都能发现"新优化点"；某次宣称已修复完成，下次又冒出来。

根因不是模型不行：**真实新增**（D 类规则违反 + T 类可检验问题）是有限集合、会衰减；
**主观建议**（J 类）空间无限、永不衰减，且换个措辞就被记成"新发现"。
结论：**"没有更多问题"不可达**，必须把"决策是否收敛"与"发现是否收敛"解耦。

R3 提供支撑该结论的量化数据；R4 把一个已记录的待收口项收口。

## 第三步：交付物（只许动这 4 项）

**D1 — 接线 `scripts/measure_null_report_rate.py`**

骨架已存在，`--runner stub` 自检已通过（Wilson CI、分层统计、产物落盘、退出码均正常）。
你只做一件事：实现 `make_llm_runner()`，替换 `TODO(r3-wire)`。

- **只读调用**，不得写回任何生产状态
- 固定温度与配置，配置哈希写入产物
- **必须调用既有 LLM 增强路径**（候选：`scripts/eval_routing.py --hermetic` 的 posture 构造 + 既有 adapter/templates 调用链）——**不要新写 LLM 客户端**
- 显式调用，不做全局自动注入
- 完成后回填 prereg §6，删除 `TODO(r3-wire)`
- 另需：按 prereg §3 生成 A 组（机械样板）样本 ≥30 条的能力

**D2 — 实现 `scripts/check_behavior_calibration_readiness.py` 的门槛计算**

实现 `check_readiness()`，替换 `TODO(r4-wire)`。

- **硬性要求：复用 `behavior_consistency` 的既有口径**（`tool_sequence_items_for_tasks`、`_bigrams`），**禁止复写第二套实现**——双处定义会让两个数字互相矛盾（gate24 pi#7 单一来源原则）
- 若签名不匹配，**不要改既有函数**，在本脚本内做适配层并注释理由
- 四条门槛阈值已在 prereg §1 写死（正例对 ≥30、负例对 ≥30、producer ≥2、至少 1 簇 ≥2 条序列）——**不得调整**

**D3 — 测试**（沿用既有惯例命名）

- `tests/core/observability/test_behavior_calibration_readiness.py`
- `tests/test_measure_null_report_rate.py`（先确认 scripts 测试的既有位置惯例）

必须覆盖：`wilson_interval` 边界（`n=0` 抛异常，**不得**返回 `(0.0, 1.0)`）／样本不足 exit 2 且 verdict 为 `SAMPLE TOO THIN`／`--runner llm` 未接线 exit 2／三条判定线分界（CI 下端 ≥0.90 FALSIFIED、CI 上端 <0.50 SUPPORTED、否则 INCONCLUSIVE）／R4 门槛任一不满足 exit 1／缺字段样本抛异常（**不得静默跳过**）。

**D4 — 文档**：若 `docs/` 有脚本索引则更新；**没有就不要新建**。

## 第四步：约束（违反即失败）

1. **不得虚构任何数字。** R3 的 `p̂`/CI、R4 的对数/FPR/FNR，没有真实数据就一律写"待填"。这条覆盖代码、注释、文档、提交信息、以及你给我的回复。
2. **不得改判据。** 两份 prereg 的判据与证伪线均已写死。认为有误就**停下来提出**。
3. **不得放宽门禁换绿灯。** 退出码沿用既有惯例（0 正常／1 未就绪／2 样本不足／3 配置失配）。
4. **不得用 exit 3 兜底**类型检查或测试（verification-contract F/G 项）。
5. **不得修改 `behavior_consistency.py`**（R4 只做就绪度检查，标定是后续独立工作）。
6. 新阈值**不进 `RoutingConfig`**，用模块常量 + CLI flag。
7. **不做全局自动注入**，不读环境变量决定行为。
8. **证据不足时诚实降级**：保持 gate `unavailable`，**不得**用 `consistent` 兜底。
9. **不引入新依赖**（Wilson CI 已用 `math` 闭式实现）。
10. 隐私：R4 只读 span 的 `name`，**绝不读 `input_data` 或参数值**。

## 第五步：验收自证（逐条贴命令与退出码）

| # | 验收项 | 命令 |
|---|---|---|
| A1 | lint | `uv run ruff check src/ tests/` |
| A2 | 类型检查（**非** exit 3 兜底） | `uv run basedpyright src/` |
| A3 | 安全扫描 | `uv run bandit -c pyproject.toml -r src/` |
| A4 | 新增测试全绿 | `uv run pytest tests/ -k "readiness or null_report" -q` |
| A5 | stub 自检可用 + stderr 有警告 | 见脚本 docstring |
| A6 | `--runner llm` 未接线 exit 2 | 同上 |
| A7 | 样本不足 exit 2 且 `SAMPLE TOO THIN` | 同上 |
| A8 | 就绪度门槛不满足 exit 1 | 同上 |
| A9 | 既有测试未回归 | `HF_HUB_OFFLINE=1 uv run pytest -q tests/core/observability/ tests/core/skills/` |
| A10 | `git status --short` 只出现约定文件 | `git status --short` |

覆盖率门槛 ≥73%（分支）；本项目**从不用 pip，一律 uv**。

## 第六步：已知陷阱（前人踩过）

1. **`.omx/` 在 `.git/info/exclude` 第 7 行** —— 新文件放进去会**被静默忽略**（已有 356 个 `.omx/` 文件是历史 `git add -f` 加入的）。你若新增 artifact，**必须 `git add -f`**，否则不进版本控制。这正是"账本放在被忽略路径等于没有账本"的翻车点。
2. **`/tmp` 不在允许目录**（实为 `/private/tmp`）。
3. `behavior_consistency.py` 的三态语义与 `_VALID_BEHAVIOR_STATES` 是**单一来源**（gate24 pi#7）——需要就 import，不要重新声明。
4. **单工具 trace 的 bigram 集为空、不参与成对计数**，这是已知且**已接受**的盲区（gate24 pi#5）。R4 prereg §4.1 要求本轮二选一收口（显式计入／暴露可见），**不允许"保持现状"**。
5. 标定数据按 trace 分组键防泄漏（同一 trace 的任何配对既不入正例也不入负例）——绕过会得到虚高的正例对数。

## 第七步：非目标

- 不实现 R1／R2／R5／R6／R7（发现账本、语义去重、同源检测、指纹扩展、决策收敛判据）
- 不重新标定 `_BEHAVIOR_JACCARD_THRESHOLD`
- 不修改 `behavior_consistency.py` 的任何行为
- 不追求"零新增发现"；不自动调参；不把通用验收偷偷换成代码评审

## 第八步：回报（逐条给证据，不要只给结论）

```
## 基线
commit: <git rev-parse --short HEAD>

## 改动文件
<git status --short 原文>

## D1 接线
- 实际调用入口: <路径 + 函数>
- 固定配置与 config-hash: <值>
- TODO(r3-wire) 已删除: 是/否

## D2 门槛计算
- 复用了哪些既有函数: <清单>
- 是否新增第二套实现: 是/否（应为否）
- 适配层理由（若有）: <文字>

## 验收自证
A1–A10: <命令> → <退出码/结果>

## 未完成 / 阻塞
<如实列出，没有就写"无">

## 我无法验证的部分
<如实列出。例如：无真实 LLM 凭证，故 R3 未产出任何数字>
```

**最后一条最重要**：若因缺凭证、数据或环境而**没**产出某些数字，请在"我无法验证的部分"里**明确写出来**。
本项目宁可拿到"未完成"，也不要一个看起来完成、实际编造的交付。
**你自己声称的"已完成"，在拿到命令证据之前一律不成立。**
