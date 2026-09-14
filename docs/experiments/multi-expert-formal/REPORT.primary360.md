# 多专家组织对照：正式报告

面向实际做 AI 开发方法选择的读者。这是一份**受控小型 CLI 基准**的结果，不是异质专家团队、也不是整库工程的结论。
主比较在冻结的流程与资源包络下进行。失败样本全部保留。

生成时间（UTC）：2026-09-13T03:07:54.653810+00:00
正式 run：[`runs/20260913T023645Z`](runs/20260913T023645Z)

## 1. 要回答什么

在**同一模型**（请求 `deepseek-v4-flash`，服务 DeepSeek-V4.1-Flash，响应 `deepseek-flash`）、
同一工具、同一总资源上限 T=24000 / I=400000 / K=120 下，带专家角色的委员会（D）是否比单体（A）
在隐藏 CLI 验收上交付更多成功产物？

次要（探索）：B−A 分阶段流程；C−B 多上下文；D−C 角色标签；E 明确分工。

## 2. 五组（固定流程）

| 组 | 流程 |
|---|---|
| A 单体 | 一个上下文完成实现与交付，可用满 T/I/K |
| B 单体分阶段 | 同一上下文：规划 → 实现 → 检查 |
| C 无角色委员会 | 三独立分析 + 一轮同步交流 + 成员0整合 |
| D 专家委员会 | 与 C 相同，唯一差别是架构/实现/质量角色 |
| E 明确分工 | 模型拆成两名工人（文件不重叠）+ 整合；拆解计入成本 |

C/D 独立分析每人最多 10% T（2400）。该硬阶段上限是本包络的一部分，不是事后补丁。

## 3. 任务与范围

12 个合成 CLI 任务：路由 4、跨层配置入口 4、可拆分数据/量化 4。完整/简略 spec 共享可查询合同（`contract` 问答）。
**不是**整库工程；不能推广为真实多专家团队。历史校准 45（旧执行器）+ 30（新执行器非正式）**不是**本 360 的样本。

## 4. 方法

- 成功：总预算内交付 + 全部隐藏验收通过 + 无所有权/路径违规。`failed`/`error`/`interrupted` 记 0。
- 无隐藏验收的失败**不**称为实现 bug。
- 主估计：每任务 6 个配对（2 spec × 3 repeat）的 D−A 差的均值，再对 12 任务等权平均。
- 95% cluster bootstrap，20000 次，seed=20260913，有放回抽任务；被抽中任务保留全部 spec/repeat。实现：冻结的 `harness/analysis.py`。
- +10pp 工程阈值解释见 `preregistration.md`。
- 并发 8；分配 seed 20260913；360 行一次性写入同一 manifest。
- Docker：批次边界核对 image **digest** 与 manifest 一致；**启动 argv 仍是 tag** `python:3.12-slim`（`tasks/common.py`）。运行期间未 pull。
- 输入预检用 UTF-8 字节作保守上限，不是 tokenizer；`I_precheck` 与真实 input 耗尽分开记账。

## 5. 样本完整性

- 分配 360；状态 {'passed': 149, 'failed': 211}
- 每组 72，每任务 30，每任务×规格×组 重复 3：已核对。
- 无 pending/running/missing 后才计算下列推断。

## 6. 主比较 D−A（确认性）

- 点估计：**-93.06 个百分点**
- 95% 区间：**[-100.00, -81.94]** 个百分点
- 判定（预注册）：`support_worse`

区间上界小于 0，支持 D 整体更差（仍只覆盖本包络）。

**不能**把本结果说成「专家更笨」「多智能体普遍无效」或「委员会代码更差」。
硬阶段终止（尤其 C/D 的 independent-0 = 2400 输出 token）可能主导差值。这是该特定流程+预算的端到端效果。

任务均值（D−A）：

| 任务 | D−A |
|---|---:|
| config-adapter-vs-entry-v1 | -100.0pp |
| config-home-isolation-v1 | -100.0pp |
| config-param-passthrough-v1 | -100.0pp |
| config-render-resolve-v1 | -100.0pp |
| etl-join-aggregate-v1 | -100.0pp |
| match-lot-calendar-v1 | -100.0pp |
| match-vwap-window-v1 | -100.0pp |
| route-lifecycle-v1 | -100.0pp |
| route-nomatch-contract-v1 | -33.3pp |
| route-plan-dag-v1 | -83.3pp |
| route-priority-table-v1 | -100.0pp |
| window-dedup-late-v1 | -100.0pp |

### 探索比较（同一方法，不作确认性宣称）

| 对比 | 点估计 | 95% CI | 预注册口径（仅作描述） |
|---|---:|---|---|
| B-A | -2.8pp | [-12.5, 6.9] | `rules_out_minimum_gain` |
| E-A | -72.2pp | [-86.1, -56.9] | `support_worse` |
| D-C | -2.8pp | [-6.9, 0.0] | `rules_out_minimum_gain` |
| C-A | -90.3pp | [-98.6, -77.8] | `support_worse` |

D−C 接近 0 且都极低：角色标签几乎没有机会表现，因为两边都卡在独立分析额度。

## 7. 各组与规格

| 组 | n | 通过 | 通过率 | 进入 hidden eval | 进入整合阶段 |
|---|---:|---:|---:|---:|---:|
| A | 72 | 67 | 93.1% | 93.1% | 100.0% |
| B | 72 | 65 | 90.3% | 90.3% | 100.0% |
| C | 72 | 2 | 2.8% | 2.8% | 2.8% |
| D | 72 | 0 | 0.0% | 0.0% | 0.0% |
| E | 72 | 15 | 20.8% | 36.1% | 86.1% |

完整 spec 通过率 40.0%；简略 spec 42.8%（探索）。

### 资源与费用（非发票）

单价（非高峰 Flash，美元/百万 token）：未命中输入 0.15，缓存命中 0.003，输出 0.6。
来源：https://api-docs.deepseek.com/quick_start/pricing/。周日实验窗口按非高峰估算。**不是账户账单。**

| 组 | 输出T均/中位 | 输入I均/中位 | cache均 | 工具K均/中位 | 估算USD |
|---|---:|---:|---:|---:|---:|
| A | 4433/2874 | 32338/31492 | 29598 | 14.2/14 | 0.2275 |
| B | 9361/8361 | 175774/159157 | 168243 | 34.5/34 | 0.5221 |
| C | 2761/2400 | 22036/17262 | 19244 | 14.0/11 | 0.1536 |
| D | 2519/2400 | 19186/17976 | 16848 | 12.6/11 | 0.1377 |
| E | 9571/9738 | 226926/248667 | 192492 | 39.0/38 | 0.8269 |
| 合计 |  |  |  |  | **1.8678** |

### 失败机制

| 组 | 构成 |
|---|---|
| A | {'passed': 67, 'failed_without_hidden_eval': 5} |
| B | {'passed': 65, 'i_precheck': 6, 'global_budget': 1} |
| C | {'stage_cap': 70, 'passed': 2} |
| D | {'stage_cap': 72} |
| E | {'passed': 15, 'i_precheck': 36, 'stage_cap': 9, 'ownership_or_path': 11, 'failed_without_hidden_eval': 1} |

stage_cap：C/D 独立分析 10%T 硬终止。i_precheck：UTF-8 字节预检。hidden_implementation_failure：进入隐藏验收且未通过。
failed_without_hidden_eval：流程在验收前结束，**不是**代码契约反例。

任务×组通过率热力图与 D−A 任务图见 [`report/figures/`](report/figures/)。

## 8. 可回查案例

#### `route-priority-table-v1-full-A-r0`

单体在完整 spec 上通过隐藏验收。能证明：A 在该任务上可以走完工具回路并满足 CLI 契约。不能证明：委员会做不到（本条没有配对的 D）。

- 状态 `passed`；error `None`
- 记录目录 [`runs/20260913T023645Z/route-priority-table-v1-full-A-r0`](runs/20260913T023645Z/route-priority-table-v1-full-A-r0/result.json)
- T/I/K = 2291/18075/19
- hidden eval: yes

#### `route-plan-dag-v1-full-C-r0`

无角色委员会在 independent-0 用尽 2400 输出 token，未进入 hidden eval。能证明：硬阶段上限可以在整合之前结束一次运行。不能证明：分析质量差或任务不可做。

- 状态 `failed`；error `stage_budget_exhausted:independent-0`
- 记录目录 [`runs/20260913T023645Z/route-plan-dag-v1-full-C-r0`](runs/20260913T023645Z/route-plan-dag-v1-full-C-r0/result.json)
- T/I/K = 2400/21714/19
- hidden eval: no

#### `match-lot-calendar-v1-full-E-r1`

明确分工组通过隐藏验收。能证明：E 协议在本任务上可以完成拆解、落盘与验收。不能证明：分工普遍优于单体。

- 状态 `passed`；error `None`
- 记录目录 [`runs/20260913T023645Z/match-lot-calendar-v1-full-E-r1`](runs/20260913T023645Z/match-lot-calendar-v1-full-E-r1/result.json)
- T/I/K = 9154/178190/52
- hidden eval: yes

#### `config-home-isolation-v1-full-E-r1`

E 在输入预检处失败（I_precheck），无 hidden eval。能证明：整合上下文变长时，字节预检会先于 tokenizer 耗尽触发。不能证明：HOME 隔离实现写错。

- 状态 `failed`；error `budget_exhausted:I_precheck`
- 记录目录 [`runs/20260913T023645Z/config-home-isolation-v1-full-E-r1`](runs/20260913T023645Z/config-home-isolation-v1-full-E-r1/result.json)
- T/I/K = 8042/264649/54
- hidden eval: no

#### `route-lifecycle-v1-full-E-r2`

E 在完整 spec 上通过 17 项隐藏检查。与上一条对照：同组不同任务，结果由任务与包络共同决定。

- 状态 `passed`；error `None`
- 记录目录 [`runs/20260913T023645Z/route-lifecycle-v1-full-E-r2`](runs/20260913T023645Z/route-lifecycle-v1-full-E-r2/result.json)
- T/I/K = 5212/133806/54
- hidden eval: yes

#### `window-dedup-late-v1-brief-E-r2`

E 因工人写了所有权之外的 `_check.py`，runner 记 `ownership_or_conflict` 失败。能证明：成功定义包含路径/所有权，不只看隐藏测试。不能证明：隐藏测试本身会失败（本条未进入或未作为放行依据）。

- 状态 `failed`；error `ownership_or_conflict`
- 记录目录 [`runs/20260913T023645Z/window-dedup-late-v1-brief-E-r2`](runs/20260913T023645Z/window-dedup-late-v1-brief-E-r2/result.json)
- T/I/K = 7359/217240/32
- hidden eval: yes

#### `route-nomatch-contract-v1-full-A-r0`

单体最终阶段截断（`incomplete_final_response`），无 hidden eval。能证明：A 也会在包络内失败。不能证明：该任务的隐藏契约被实现写错。

- 状态 `failed`；error `incomplete_final_response`
- 记录目录 [`runs/20260913T023645Z/route-nomatch-contract-v1-full-A-r0`](runs/20260913T023645Z/route-nomatch-contract-v1-full-A-r0/result.json)
- T/I/K = 24000/11736/17
- hidden eval: no


## 9. 审计

- 360 唯一分配：True
- freeze 校验：True；live 漂移：False
- usage 不匹配：无
- cache 不匹配：无
- 请求中隐藏泄漏：无
- Docker digest 现在：`sha256:d764629ce0ddd8c71fd371e9901efb324a95789d2315a47db7e4d27e78f1b0e9`；与 manifest 一致：True
- 启动 argv 仍为 tag `python:3.12-slim`（文档/实现偏差，未在本 cohort 修改冻结源）
- 审计 JSON：[`report/audit360.json`](report/audit360.json)

若 runner 的 `passed` 与预注册（含所有权违规）不一致，原始 status 保留，列为协议偏差交监督仲裁。本报告不静默改结果。

## 10. 校准与轨迹（与 360 分开）

- 旧校准 45 次：`docs/experiments/multi-expert-calibration/runs/`（只读）
- 新执行器非正式 30 次：`runs/20260913T015759Z`（K=40）与 `runs/20260913T020657Z`（K=80）
- 正式 360：`runs/20260913T023645Z`
- 复现剩余（已全部完成则不必）：见 STATUS.md

## 11. 局限

- 小型 CLI，不是仓库级协作。
- 同一模型的角色提示 ≠ 真实多专家。
- 硬阶段 cap 可能主导 C/D。后续若做软结束敏感性实验，必须预先声明，不能改本 cohort。
- 模型别名不固定权重。temperature=0 仍有重复。
- 费用是公开非高峰单价估算，不是发票。
- I_precheck 用字节不是 tokenizer。
- Docker 启动未把 digest 写入 argv。

## 12. 实践建议

- 若要在产品里采用委员会，先看本电池区间是否越过 +10pp；本报告按预注册规则解释，不预设委员会必输。
- 设计多上下文流程时，阶段额度与「能否走到验收」是同一实验条件，不要事后把阶段耗尽解释成智力差异。
- 明确分工（E）的文件边界与拆解成本必须入账。
- 监督者可决定是否需要预先声明的软阶段敏感性实验。

图：[`report/figures/pass_by_arm.svg`](report/figures/pass_by_arm.svg) 等（SVG+PNG）。绘图脚本在 `report/`，**不**在冻结统计实现中。
