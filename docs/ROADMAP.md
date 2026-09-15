# VibeSOP Roadmap

> **当前源码 / 包元数据 Current source**: 8.5.0 source candidate（online routing evidence）
> **公开发行 Public release**: 8.4.1（PyPI / GitHub Release 已对齐 8.4.1；8.5.0 待后续 tag/publish）
> **最后更新 Last Updated**: 2026-09-15
> **历史稿**: [roadmap-through-8.3.md](archive/roadmap-through-8.3.md)（冻结至 8.3.0 的 804 行原稿）

---

## 定位

VibeSOP 是**可靠 AI 辅助开发的工程工具与实证研究**。SkillOS 是技能管理子系统，不是整个项目。产品实现、研究发现和待验证假设分开管理；定位扩展不自动扩大本周期功能承诺。详见 [POSITIONING.md](POSITIONING.md)。

找不到匹配是正常结果。工具存在、评测可跑、CI 有闸，都不等于已经证明端到端可靠。

## 版本边界

| 对象 | 状态 | 说明 |
|---|---|---|
| 当前源码 / 包元数据 | **8.5.0** source candidate | 见 [PROJECT_STATUS.md](PROJECT_STATUS.md)、[pyproject.toml](../pyproject.toml) |
| 当前 PyPI / GitHub Release | **8.4.1** | 8.5.0 的 tag/publish 在后续发行阶段 |
| 本分支 `codex/v85-online-evidence-loop` | **8.5.0 online routing evidence** | 只读观测器 `vibe observe routing`、`vibesop.observe.routing` v1、eval provenance fail-closed |

8.5.0 作为 minor 的理由是新增公开的 operator CLI / 机器契约 / library 面（并在 `scripts/aggregate_nomatch.py` 保持 8.4.0 兼容），不是补丁级修复。源码版本上升不等于 PyPI 已发布，也不等于可靠性已被证明。

## 状态分层

不要把三类混写成同一句「已经完成」：

| 分层 | 含义 | 本文件中的位置 |
|---|---|---|
| **已实现（8.4.0 源码）** | 本分支源码与包元数据已有；公开发行待 tag/publish | 下一节 8.4 切片 |
| **计划中** | 下一轮优化，尚未当作交付 | 优先级 A–E |
| **研究阻塞** | 预注册实验未跑完或未结算；不得改判据迁就结果 | B、C |

## 8.4.0：Trust & Evidence

数字均为 2026-09-14 本 checkpoint 在本工作区执行所得。实现可观测，不等于可靠性已被证明。

### 双向路由评测与 `top_k` 传递

`scripts/eval_routing.py` 同时报告过拒（正例无真实匹配）与过灌（负例出现真实匹配）。双向计数 report-only，不改变 hermetic `--check` 退出码。`near_miss` 有单独计数器，不并入 `must_not_inject` 子集，但仍按 no-match 期望被 hermetic 评测计分。Embedding 匹配器接受 `MatcherPipeline` 的 `top_k`，避免 `enable_embedding=True` 时因签名不匹配崩溃。

Hermetic 数据集：**55** 条总计 / **53** 条计分 / **2** 条环境跳过。top-1 **47/53**。正例 **31**（过拒 **4**），负例 **20**（过灌 **2**），`near_miss` **14**（过灌 **2**）。已知失败 **6** 条。

### 14 条 `near_miss` 负例 / hermetic 基线

评测集增加 14 条形近触发词、域外的 `near_miss` 负例：单独报告计数器，不并入 `must_not_inject` 子集，但仍按 no-match 期望被 hermetic 评测计分。`uv run python scripts/eval_routing.py --hermetic --check` 本 checkpoint 为绿：与基线一致，0 条新失败，6 条已知失败。

### 生产 no-match 聚合（Wilson 区间）

`scripts/aggregate_nomatch.py` 对 `route:` span 做窗口化 no-match 率，主输出为 Wilson 95% 区间。缺 span 文件 fail-soft（exit 0 + 错误字段），不编造成功率，不接 CI 门禁。

### CI `decision_source` 注册表

`.github/workflows/ci.yml` 的每个 job 必须在 `ci/decision-source.yaml` 声明 `deterministic` 或 `human`。模型输出不得作为 required job 的放行依据。`routing-eval` 为 `human`（永久 report-only）。本 checkpoint：`scripts/check_ci_decision_source.py` **10/10** job 登记且交叉核对通过。

### 产物引用守卫 + 冻结债务基线

`scripts/check_artifact_links.py` 检查 tracked 文档对 `.omx/artifacts/` 的引用。默认扫描 `git ls-files` 中每一个 tracked `*.md`（含 `.omx/artifacts/`、`memory/`、`knowledge/`），与 fresh-clone 集合一致。dangling 一律失败。历史未跟踪引用冻结在 `ci/artifact-links-baseline.json`，精确匹配才过。提取在 ASCII `()` / `:` / `\\` 处截断，基线 key 必须是正规化 POSIX 产物路径/glob/目录，不是 `file:line` 或注解碎片。本 checkpoint： **1109** 条引用 = **641** ok + **468** 条历史非跟踪出现（**460** 个 key）+ **0** dangling，基线精确匹配。该基线是过渡账本，不是永久免责。

## 8.5.0：Online routing evidence（source candidate）

数字均为 2026-09-15 本 checkpoint 在本工作区执行所得。该切片 report-only，尚未接门禁。

### `vibe observe routing` 与 `vibesop.observe.routing` v1

只读消费 `.vibe/observability/spans.jsonl` 与可选 `--eval-json`，输出三个信号：

- `no_match` — 可计分 route span 的 no-match 率，带 Wilson 95% 区间；先过覆盖率（`scoring_coverage >= 0.80`）与最小样本（`n_scored >= 100`）闸，避免在极小可读切片上误报。
- `near_miss` — 可选 `--eval-json`（来自 `scripts/eval_routing.py --hermetic`）；未提供时为 `not_requested`，不伪装成绿。
- `decision_source` — `metadata.layer` 对 `RoutingLayer` 枚举分类；`unknown_share` 以 `n_scored` 为分母，非枚举值进入 `non_enum_layers`。

半开窗口 `[since, until)`、`project_id` 精确过滤、时间戳 UTC 归一（`started_at` 优先，回退 `legacy timestamp`）。退出码 `0/1/2/3/4` 是标签而非严重度排序，非 Nagios 兼容；`--report-only` 只抑制 verdict，绝不抑制 usage(2)/fault(3)；`--require-inputs` 把缺失输入升级为 fault；`--strict-payloads` 把损坏/未解析载荷升级为 fault。

### eval provenance fail-closed

`--eval-json` 的 `dataset` / `hermetic` / `generated_at` 必填且类型正确；`hermetic` 必须为 `true`；`dataset` 与预期身份精确匹配（分隔符/前导 `./` 归一，不做 basename 匹配）；`generated_at` 必须带时区、不得早于 24h、不得超前 5m。任一不满足即 `invalid_eval_provenance` fault（exit 3），`--report-only` 也不抑制。freshness 独立于 span 窗口。

### 兼容与后台改动

- `scripts/aggregate_nomatch.py` 成为 8.4.0 兼容 facade：解析/评分/Wilson 区间/字节级解码/BOM-CRLF 处理/文件错误均移到 library，CLI 契约不变（缺文件 fail-soft exit 0 + 错误字段）。
- `scripts/eval_routing.py` 的 `--json` / `--json-out` 增量添加 `dataset` / `hermetic` / `generated_at`；既有 `--check` 退出码与基線闸不变。

运维口径、阈值、退出表、JSON 契约与 cron/CI 包装见 [observe-routing.md](observe-routing.md)。本切片报告**不写**路由注册表、评测集、阈值或策略文件。

## 8.4 发行闸

包版本已在本分支 release commit 升到 8.4.0。公开发行（tag / PyPI）之前，须同时满足：

1. 相关检查与适当的完整检查绿。
2. hermetic baseline check 绿。
3. decision registry 与 workflow job 精确一致。
4. artifact baseline 精确匹配，且 fresh-clone probe 无 dangling。
5. CHANGELOG、版本元数据、状态文档同步。
6. 独立评审 0 个 P0 / P1 / P2。

本文件不把未执行的全量测试套件写成已绿。hermetic、artifact baseline、decision registry 三项观测检查曾在 8.4 工作区执行通过；release commit 之后须重跑。

## 下一轮优化（顺序固定；字母 A–E 仅本文件编号，不是 2026-09-11 提案 lane）

### A. 在线消费证据（先 report-only）— 8.5.0 source candidate 已实现

区分五件事，不要合成一句「用过了」：选择、投递/注入、实际消费/阅读、执行、机器验收。8.5.0 source candidate 先交付 report-only 的 `vibe observe routing`：no_match / near_miss / decision_source 与 `vibesop.observe.routing` v1。后续仍不接门禁，不把信号折成总分。

### 后续里程碑（8.5.0 不含，保持原计划）

- **性能基准方法论**：热路径与其他性能基准的预算、预热、采样与报告方法；不把单次墙钟对比当叙事。
- **第三方 action SHA 固定**：CI/release 第三方 action 的 SHA/tag 策略与复查节奏（安全关键 action 固定 SHA，通用 action 用版本 tag）。
- **固定角色委员会 v2**：见下方 C，仍为未完成研究。
- **stale 产物引用清理**：见下方 D，按有界批次削减。

### B. 收口预注册研究债（不改判据）

按原判据执行，不得事后放宽：

- R3 空报告率实验
- R4 行为阈值就绪度 / 标定
- R8 盲评结算
- T+21 回声复检

### C. 完成固定角色委员会 v2（按实际记录）

截至 2026-09-14：正式终态 **241** 条；已启动但缺终态 **4** 条；未启动 **115** 条；独立 **72** 次人数诊断未启动。完整主实验与人数诊断完成前，不得把中间发现写成普遍结论。登记：[实验索引](experiments/README.md)。

### D. 按有界批次削减 468 条产物引用债务

冻结基线只允许对账，不允许把新的 dangling 或新增 stale 解释成「基线如此」。消化后须 `--write-baseline` 显式刷新，且刷新前 dangling 必须为 0。

### E. 统一 trust / evidence 报告（仅在原始信号稳定之后）

不要把未稳定的选择、注入、消费、验收信号折成一张总分。语义画像保持 report-only；先有对照组，再考虑任何门禁。

## 约束（继续有效）

- 不以默认专家委员会为自动编制。
- 不以 LLM 输出作为发行闸。
- 无证据不扩张市场或角色。
- 不声称记忆必然提升能力。
- 语义层在标定完成前不做硬门禁。
- 不为叙事跑墙钟时间对比。
- 不把整机流水线做成 CLI。

## 历史

8.3.0 及更早的版本叙事、W1/W2 清单、v4–v8 功能史冻结于 [archive/roadmap-through-8.3.md](archive/roadmap-through-8.3.md)。不重写其中的历史主张。研究总账仍以 [研究综述](research/research-survey.md) 的写作时点为准。
