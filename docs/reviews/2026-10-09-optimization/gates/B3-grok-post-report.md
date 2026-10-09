# B3 提交后第二门禁（Grok 独立只读）

- **裁决：REQUEST_CHANGES**
- **评审人**：Grok，独立只读；未改库内源/测试/文档/配置，未 commit，未调用其他模型或子代理
- **日期**：2026-10-09
- **对象**：`57b6169d8f361a981b89999db0285bcf2c76edf3`（parent `ed8227dc855b1f8a5c262681dc703a0f96131351`），git archive 工作树，不是开发树
- **作者**：提交说明含 `Co-authored-by: Kimi Code`。本门禁按 Kimi 临时开发贡献复核，不把改动记到 Claude 或 Grok

Kimi 终审写的是 APPROVE。冻结 diff、字符串哨兵、真实 PlanBuilder 身份、review 错误轴、fail_fast 成功批继续、失败依赖跳过，这些我复跑后成立。不能放行的是：新增适配器在真实 hard-reject 反馈和 dict `status=blocked` 上，把 StepOutcome 已经判成 blocked 的步骤收成 failed。动态 lane 还把仍为 PENDING 的步骤计成 skipped，并且不回写 runner 状态。

发现交给 Kimi 修。我没有改代码。

## 0. 冻结与范围

[executed] `git rev-parse HEAD` = `57b6169d8f361a981b89999db0285bcf2c76edf3`，`HEAD^` = `ed8227dc855b1f8a5c262681dc703a0f96131351`。工作区与 index 干净。`git diff HEAD^ HEAD` 为 104959 字节，sha256 `a7db15594860f091064ecb17ad550faac638e387219b493faafc05a98363251e`，与收据逐字节一致。`git show --format= HEAD` 与该 diff 相同。

[executed] 收据 8 个 sha256 与本树、与 `/tmp/vibesop-opt-20261009/snapshots/B3-final-pre` 逐文件一致；`git cat-file -p HEAD:<path>` 与工作树字节一致。变更的 6 个路径就是收据里的 `committed_paths`。`src/vibesop/agent/__init__.py` 与 `tests/core/skills/test_workflow_engine_enhanced.py` 相对 parent blob 未变。`parallel_scheduler.py` 不在本提交中，实际路径是 `src/vibesop/core/orchestration/parallel_scheduler.py`。

[executed] CHANGELOG 只新增两条 B3 条目（Changed / Fixed）。其余 Unreleased 内容来自 parent，本门禁不重审。

[executed] 定向 pytest（`uv run pytest tests/agent tests/core/orchestration tests/core/skills/test_workflow_engine_enhanced.py -q --tb=line`）**819 passed**，15.51s。解释器走 `pythonpath = src`，导入的是本快照源码。

未做：全量套件、Docker / Node24 容器、ruff、pyright。Kimi 宿主 80+801、父容器 819、ruff/types 0 不是我这次重跑的结果。我这次的 819 是上面三条路径合在一起的宿主结果。

库外探针：`/tmp/b3-grok-post/probe.py`。探针前后五份源/测试 sha256 未变（`source-unchanged=true`）。`uv sync --frozen` 在本快照生成了 gitignore 的 `.venv`，按调度约定没有删除。

## 1. 已复核成立的合同

这些不是问题，后面的修改不要把它们改回去。

- **字符串哨兵四公开面** [executed]。静态 `blocked: need human`：`failed=1`、`blocked=1`、`final_status=blocked`、entry `status=failed`、`StepStatus.FAILED`、`runner.failed_count=1`、StepOutcome `blocked`、适配器 `blocked`、`review_status=not_required`。
- **并行 blocked + 成功** [executed]。`failed=1`、`blocked=1`、`final_status=partial`，entry 仍是 `completed/failed`。
- **fail_fast 成功批后继续** [executed]。FAN_OUT 形状 s1∥s2 → s3，`fail_fast=True` 时三次都执行，`completed=3`，`final_status=completed`。
- **失败依赖跳过** [executed]。s1 异常且 fail_fast：s2（依赖 s1）、s3（依赖 s2）都是 `SKIPPED`，`pending_steps()` 为空。
- **可恢复 pending 存在，但不是 Kimi C7 那张图** [executed]。同批先记录 s1 成功、再 s2 失败、s3 只依赖 s1：s1 `completed`、s2 `failed`、s3 `pending`，`pending_steps()` 返回 s3，`is_complete=false`。同批里排在失败项后面、尚未记账的独立根（Kimi C7 的 s3）会被批内中止标成 `SKIPPED`，`pending_steps()` 不返回它。这与 Kimi 报告第 4 节「同批剩余与 HEAD 一致」相符，与第 2 节 C7 的 `ok` 条件不符。**不要为了让 C7 的 s3 保持 PENDING 去改批内 skip。**
- **cancel** [executed]。`CancelledError` 抛出 `execute_all`；依赖步骤保持 `PENDING`；runner 不是 `is_complete`。终扫没有跑。
- **真实 PlanBuilder → 公共 executor** [executed]。两次回调都是 `step is plan.steps[i]`，类型是 `ExecutionStep` 不是 `SquadStep`。`skill_id` 为 `implskill` / `revskill`。`input_query` 等于计划步骤上的原字段；生产 `PlanBuilder._build_squad_steps` 把该字段写成 `""`（`plan_builder.py` 约 670 行），SquadStep 没有可冒充的 instruction 字段。`role_prompt` 等于 `render_role_prompt(role, SquadStep.skill_ids)`，`skill_isolation.allowed_skills` 与之相同，下游 handoff 含 `work-by-implementer`，ctx 带 `verdicts`。`review_status=accepted`，`plan.status=completed`。
- **review 错误轴** [executed]。无 LLM 的 review_gate：`review_status=error`（dict、适配器、StepOutcome、`plan_terminal` 都是 error），`all_succeeded=True`，`failed=0`，`blocked=0`，`completed=2`，`plan.status=COMPLETED`。`plan_terminal.final_status` 仍是 `completed`，没有改写旧键。`PlanStatus.COMPLETED` 在 squad 上只表示跑完，不表示验收通过。hard-reject（下面带前缀的那条）同样是 `plan.status=COMPLETED`，事件 `final_status=completed`，`review_status=rejected`。
- **动态失败的 legacy dict** [executed]。LOOP_UNTIL_DRY 抛错：`results` 仍是 dict，`{"s1": {"error": "dyn blew"}}`，不是 list；`failed=1`，`final_status=failed`，`plan.status=FAILED`。
- **消费面** [inspected]。`src/` 里 `execute_all(` 只有定义和 docstring。`AgentRouter.create_runner`（`src/vibesop/agent/__init__.py:419`）返回 `StepRunner`，executor 由调用方注入。`AgentRouter.execute_plan` 仍走 `parallel_scheduler.execute_plan_sync`，不经过这次的 StepRunner 词汇；这是既有旁路，不是本提交引入的回归。

## 2. 必须改（P1）：适配器丢失 blocked 粒度

F2 把逐步 entry 限制在 `completed/failed/skipped`，blocked 只能从错误文本或原始值用共享谓词回收。回收实现和生产者不一致。计数和 `review_status` 在这些案子里是对的；坏的是适配器逐步状态，以及它和 StepOutcome 的分裂。

### 2.1 真实 hard-reject 反馈

[executed] 真实 PlanBuilder review_gate，LLM 返回 `requires_revision=false`，`revision_feedback="add the missing tests"`，`issues=["missing tests"]`（不是 `blocked:` 前缀）：

| 面 | 结果 |
|---|---|
| 公开 dict | `blocked=1`，`failed=1`，`final_status=blocked`，`review_status=rejected`，`plan.status=completed` |
| entry | implementer `status=failed`，`error="add the missing tests"` |
| StepOutcome | implementer `blocked` |
| `from_step_runner_dict` | implementer **`failed`**，没有任何 `BLOCKED` |

对照 [executed]：同一路径把 `revision_feedback` 写成 `"blocked: no evidence"` 时，适配器变成 `blocked`。套件就是这样写的：`tests/agent/test_step_runner.py` 的 `_HardRejectLLM` 把反馈拼成 `blocked: ...`，`tests/core/orchestration/test_workflow_engine.py` 的新 hard-reject 用例也写死 `revision_feedback: "blocked: no evidence"`。所以现有绿测试没有覆盖普通评审文本。

原因 [inspected]：`step_runner.py` 927–935 行在角色被 hard-reject 时，用 `revision_feedback` 或 issues 覆盖 error，只有两者都空才退回 `"blocked: review gate rejected..."`。适配器 `execution_protocol.py` 102–108 行只在 error 文本等于 `blocked` 或以 `blocked:` 开头时回收 BLOCKED。普通反馈把谓词需要的文本换掉了。

### 2.2 dict 哨兵 `{"status": "blocked"}`

文档把该形状和 `blocked:` 字符串都算 blocked（`StepOutcomeStatus` 与 `is_acceptance_failure`）。runner 用 `_is_blocked_output` 认 dict；适配器不认。

[executed] 静态 lane 返回 `{"status": "blocked"}`：`blocked=1`，`failed=1`，`final_status=blocked`，StepOutcome `blocked`，`runner.failed_count=1`。entry error 被收成 `"{'status': 'blocked'}"`。适配器得到 **`failed`**。

[executed] 动态 LOOP_UNTIL_DRY 原样保留 dict（`results={"s1": {"status": "blocked"}}`）：公开 `blocked=1`、`failed=1`、`final_status=failed`。适配器得到 **`failed`**。`execution_protocol.py` 111 行对 dict 把待匹配文本设成 `""`，于是凡是 dict 验收失败都落到 FAILED，包括 `status=blocked`。

字符串动态值 `"blocked: need evidence"` 适配器仍是 `blocked` [executed]。裂口只在 dict，以及被换成非哨兵文本的 error。

修的时候要让公开 dict 的 `blocked` 计数、StepOutcome、适配器逐步状态在上述三个输入上一致：普通 hard-reject 反馈、静态 dict 哨兵、动态 dict 哨兵。不要靠把测试反馈改成 `blocked:` 前缀来保持绿。

## 3. 一并改（P2）：动态 lane 的 skipped 与 runner 状态

[executed] 两步 LOOP_UNTIL_DRY，第一步抛 `RuntimeError`：

- 公开结果：`results` 为 dict，`failed=1`，`final_status=failed`，`plan.status=failed`，`skipped=1`
- 步骤对象：s1 `failed`，s2 **`pending`**
- runner：`failed_count=0`，`pending_steps()` 仍返回 **s1 和 s2**

[inspected] `_dynamic_result_dict`（`step_runner.py` 830–834 行）把「不在 results 里且 status 不是 COMPLETED」都算 skipped。提前结束留下的 PENDING 因此被公开计数说成已跳过，但步骤状态并没有 `mark_skipped`。同一函数不调用 `mark_failed` / `mark_completed`，所以 `failed_count` 与 `pending_steps()` 仍按进引擎之前的 runner 状态。`PlanOutcome.steps` 在这条 lane 也是空的（836–844 行没有填 `steps`）。

[executed] 动态字符串哨兵 `"blocked: need evidence"`：公开 `failed=1`、`blocked=1`、`final_status=failed`、`plan.status=failed`，但该步 `StepStatus` 仍是 **`completed`**。LOOP_UNTIL_DRY 在 `workflow_engine.py` 492–496 行先把步骤标完成再原样收下返回值；这段不在本提交的 engine diff 里。新的计数层按哨兵报失败，没有把步骤状态对齐。

要求：动态公开 `skipped` 不要把仍然 PENDING、可再调度的步骤算进去；`failed_count` / `pending_steps()` 不要继续把引擎已经失败的步骤当成未跑。哨兵返回值的步骤状态要和公开 `failed`/`blocked` 同一边。这不要求改 squad 的 `PlanStatus.COMPLETED` = 跑完这一登记。

## 4. 非阻断，但注释是错的

[inspected] `step_runner.py` 469–471 行写「failed 计数必须排除 blocked，避免双重计算」。聚合实际用的是 `failed=self.failed_count`（735–738 行），blocked 步骤走 `mark_failed`，因此 **两边都计**。C1 的行为符合 F1，注释相反。留着会把下一次修改引回已经否决的减法语义。请改注释，不要改 C1 的计数。

## 5. 局限

- 没有重跑全套、容器、ruff、类型检查。
- `input_query` 的「原值」在这条生产 squad 计划上是空字符串；证据是对象身份和 `skill_id`，不是一条非空 query。
- 动态 lane 的步骤 `COMPLETED` 与哨兵失败并存，根在未改动的 loop 执行段；本门禁只要求和新公开计数对齐，不把 squad 跑完语义扩成验收语义。
- Kimi C7 的文字结论与这次提交的实际行为不符，但批内 skip 本身按已授权的 HEAD 同批语义保留。

探针输出与上述表格一致，源码哈希在探针后未变。
