# B3-r2 提交后第二门禁（Grok 独立只读）

- **裁决：APPROVE**
- **评审人**：Grok，独立只读新会话，非作者。未改库内源码、测试、文档、配置，未 stage，未 commit，未调用其他模型或子代理，未重跑 Docker，未跑全套
- **日期**：2026-10-09
- **对象**：`d9d7804ffd1dfb92f6a82138e5a07f5304a11df0`（parent `57b6169d8f361a981b89999db0285bcf2c76edf3`）。工作树由 `git archive` 的 committed HEAD 重建，full 非 shallow。`git rev-parse --is-shallow-repository` = `false`
- **作者**：`huchen <curiousbull@outlook.com>`。提交说明含 `Co-authored-by: Kimi Code <noreply@moonshot.ai>`。Kimi 是本批临时开发贡献者，不是 Claude。本报告不代表 Claude，也不代签。原生 Claude 协作仍 pending

原 Grok 提交后报告是 REQUEST_CHANGES。Kimi 本批 pre-commit 报告是 APPROVE。两份都读过。下面的合同以这次提交的 blob 和这次新探针为准，不沿用那两份的结论。

## 0. 冻结与范围

[executed] `git rev-parse HEAD` = `d9d7804ffd1dfb92f6a82138e5a07f5304a11df0`，`HEAD^` = `57b6169d8f361a981b89999db0285bcf2c76edf3`。index 空。`git diff HEAD` 对已跟踪文件为空。

[executed] `git diff HEAD^ HEAD` 与 `git show --format= HEAD` 都是 37823 bytes，sha256 `98e69209f0a6fcbb847b813b5a814a46557e8c5885c1b4cae1876b1f3f2ec96b`。`.omx/artifacts/diagnosis-B3-r2.diff` 与该 diff 逐字节相同，并与收据 `/tmp/vibesop-opt-20261009/B3-r2-post-frozen.json` 的 `patch_sha256` / `post_diff_sha256` 一致。

[executed] 收据 8 个 `source_sha256` 与工作树、与 `git cat-file -p HEAD:<path>` 的内容哈希一致。探针前后这 8 个哈希未变。

本 delta 实际改动 **4 个文件**。其余审计路径相对 parent blob 未变。不把未改文件记成改动。

| 路径 | parent blob | HEAD blob | 内容 sha256 | 本 delta |
|---|---|---|---|---|
| `src/vibesop/agent/step_runner.py` | `b0b29288d81888f99c332439b99d48f673985e47` | `938cb16b086cfe15034e227c56e321856986c0a2` | `4f6ffed22a26e6e42232788fb190c21dd698077e32c74691fd9e7236f39f1b00` | 改 |
| `src/vibesop/agent/execution_protocol.py` | `4d747966087ebfe82c34e32aee1e139a5b861b51` | `52a9ab962915b82fcd457bc4bccb25e0b7c96195` | `78d65c6bebdebdc4891de999b22382cc0f5aa98a47bb5b15c1c5027991b5a885` | 改 |
| `tests/agent/test_step_runner.py` | `68e9dbfc01c25b38d85a2c6b76a774723b809eb3` | `35a8efe6775d3fa63784b07402dd8b76e99aeb0e` | `00be11b3f340a2a0e02922c8dcec81c1c9a8ff382bdb8f5163aaa9fe809da625` | 改 |
| `CHANGELOG.md` | `9d3f01cdd0c09f24724bf666502579b3be48036e` | `b1f089d62b3faeb162e75c3ff2307d1b573c37a9` | `0849e892c353aab6f81856a478aa281b00c8b06082553eba7d473307e7ee2091` | 改 |
| `src/vibesop/core/orchestration/workflow_engine.py` | `22dd49d8c71145672040dd2449c459759e47d9ee` | 同 parent | `3ccb03d3cb36ebe329558dc18c28b2645d8c65d4c404aa98938e671e14664d01` | 未改 |
| `src/vibesop/agent/__init__.py` | `2290ab952b6289b1fb6add4a4d0301e2bc03625b` | 同 parent | `a1f6cfe9dc4af5612df5a8d35e6a14d14af02f68ee4260f4a232e6afe770c25f` | 未改 |
| `tests/core/orchestration/test_workflow_engine.py` | `e07ec3093af51c14dac9be1431ad613cf3a204ad` | 同 parent | `0088d6802d8e3a44037efad322cf31e07bb3dc2265f600ec7e887c96ece9b19d` | 未改 |
| `tests/core/skills/test_workflow_engine_enhanced.py` | `caba246f65a8d3f6bdef9c873ec0adc5a1ca9cc1` | 同 parent | `fbceb667d24bf1efa18ba6b70bdb260d565d345e5d086441a01ae21f4de4a668` | 未改 |
| `src/vibesop/core/orchestration/parallel_scheduler.py` | `1846b26d639fc36136f89835b312c743515d3023` | 同 parent | — | 未改 |

[executed] `src/vibesop/agent/parallel_scheduler.py` 在 HEAD 与 parent 都不存在。这是旧误路径，不是本提交的改动。

[executed] 测试 diff 只删了 1 行 import，并加上 `StepOutcomeStatus`；其余是新增断言。没有改掉原有失败断言。

[executed] CHANGELOG 只在 Fixed 下新增一条 B3-r2。上一条 B3 条目仍在。其余 Unreleased 内容来自 parent，本门禁不重审。

[executed] 快照目录里还有未跟踪路径：`.omx/artifacts/diagnosis-B3-r2.diff`、`docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/`、`docs/plans/2026-10-09-diagnosis-optimization.json`、`docs/plans/2026-10-09-diagnosis-optimization.md`。它们不在 commit 里。探针和测试结束后 `git status` 仍是这四项，已跟踪文件无差异。

## 1. 原 P1 / P2 / NIT 的亲证

历史 RED 以 `/tmp/vibesop-opt-20261009/B3-post-corrective-native-review.md` 为准：当时默认两参和 JSON 传输都是 FAILED，只有 opt-in 第三参是 BLOCKED。当前提交不再依赖那条 opt-in。

生产者在静态/squad 的逐步 entry 上写入 additive `outcome_status`（`success` / `failed` / `blocked` / `skipped`）。`PlanExecutionResult.from_step_runner_dict(result, plan)` 默认先读这个字符串。动态 lane 的 `results` 仍是 step-id → 原始值的 dict，不混入 `outcome_status`；适配器对这个 dict 走共享 `_is_blocked_output`。

[executed] 真实 `PlanBuilder` + `_PlainFeedbackRejectLLM`，反馈原文 `add the missing tests`，无 `blocked:` 前缀：

| 面 | 结果 |
|---|---|
| 公开 dict | `blocked=1`，`failed=1`，`final_status=blocked`，`review_status=rejected`，`plan.status=completed` |
| legacy entry | implementer `status=failed`，`error="add the missing tests"`，`output=None`，`outcome_status=blocked` |
| reviewer | `status=completed`，`outcome_status=success` |
| StepOutcome | implementer `blocked`，reviewer `success` |
| 默认两参 | implementer BLOCKED，reviewer SUCCESS |
| `json.dumps` / `loads` 后再默认两参 | 仍是 BLOCKED，error 原文仍在 |
| 剥掉 `outcome_status` 的旧 payload | implementer 回到 FAILED。这是无该键时的旧 fallback，当前生产者会写这个键 |

[executed] 真异常 `RuntimeError("tool crashed")`：`outcome_status=failed`，`blocked=0`，默认两参和 JSON 后都是 FAILED，error 原文保留。没有把所有 failed 收成 blocked。

[executed] 静态 `{"status": "blocked", "reason": "need evidence"}`：公开 `blocked=1/failed=1/final_status=blocked`，`failed_count=1`，`StepStatus.FAILED`，StepOutcome `blocked`。默认两参、opt-in、剥掉 `outcome_status`、非法 `outcome_status="not-a-status"` 四路都是 BLOCKED。entry `status` 仍是 `failed`，error 仍是 `str(output)`，raw dict 留在 `output` 上。

[executed] 动态同一 dict：`results` 逐值等于哨兵，无 additive key。`failed=1/blocked=1/skipped=0/final_status=failed`，`plan.status=FAILED`。该步 `StepStatus.FAILED`，独立根仍 `PENDING`，`failed_count=1`，`pending_steps()==["step-2"]`，`is_complete=False`，`PlanOutcome.steps` 只有该步且为 blocked。默认两参和 JSON 后都是 BLOCKED。

[executed] 动态字符串 `"blocked: need evidence"`：公开 failed+blocked，`final_status=failed`，步骤 `FAILED`，独立根 `PENDING`，适配器 BLOCKED。

[executed] 动态真异常：`results=={"step-1": {"error": "dyn blew"}}`，`skipped=0`，`failed_count=1`。依赖步保持 `PENDING` 且 `pending_steps()` 为空。独立根异常时 `pending_steps()==["step-2"]`，失败步不在其中。适配器 FAILED。

[executed] 真正的 `is_verification_step`：引擎把它标成 `SKIPPED`，执行器没有调用它，公开 `skipped=1`，`results` 里没有这一步。

[executed] F1 注释已改。`step_runner.py` 现在写明 blocked 在 failed 与 blocked 两边都计。旧句 “failed counter must exclude them to avoid double counting” 不在文件里。聚合仍是 `failed=self.failed_count`、`blocked=len(blocked_ids)`。字符串哨兵运行结果是 `failed=1` 且 `blocked=1`。

## 2. 原合同没有被这 4 个文件改回去

[executed] D06：真实 PlanBuilder FAN_OUT，`fail_fast=True`，三次执行，`completed=3`，`final_status=completed`。执行器返回的是字符串。

[executed] C7 批内 skip 仍在。三个独立根、`fail_fast=True`、第一步抛错：后两个是 `SKIPPED`，`skipped=2`，`pending_steps()` 为空。

[executed] 可恢复 pending 仍在，而且不是 C7。s1 成功、s2 失败、s3 只依赖 s1：s1 `completed`、s2 `failed`、s3 `pending`，`pending_steps()==["step-3"]`，`skipped=0`，`is_complete=False`。

[executed] 并行 blocked 字符串 + 成功字符串：`failed=1/blocked=1/final_status=partial`，entry 仍是 `failed` / `completed`，适配器是 BLOCKED / SUCCESS。

[executed] `CancelledError` 仍抛出 `execute_all`。依赖步保持 `PENDING`，runner 不是 `is_complete`。

[executed] 真实 SkillLoader 计划（`implskill` / `revskill`，`review_gate`）：两次回调都是 `step is plan.steps[i]`，类型是 `ExecutionStep`。`input_query==""`。`role_prompt == render_role_prompt(role, squad skill_ids)`，`skill_isolation.allowed_skills` 与之相同。reviewer 的 handoff 含执行器返回的 `work-by-implementer`，ctx 有 `verdicts`。普通 hard-reject 下默认适配器是 BLOCKED / SUCCESS，`plan.status=completed`。

[executed] RED_TEAM 真实 PlanBuilder：同样的对象身份、role prompt、skill isolation，red_team handoff 含 `work-by-implementer`，`final_status=completed`，`plan.status=completed`。

[executed] 无 LLM 的 review_gate：`review_status=error`，`failed=0`，`blocked=0`，`final_status=completed`，`plan.status=COMPLETED`，逐步 `outcome_status=success`。默认适配器和 JSON 后都是 `all_succeeded=True` 且 `review_status=error`。

## 3. 分开登记，不当成这次修掉的新缺陷

这些不推翻上面的合同，也不把它们写成 B3-r2 的修复。

- **基线，本 delta 未碰。** 静态串行成功路径仍把执行器原值交给 `mark_completed`，其中 `output[:200]` 要求字符串。普通 dict `{"content": "ordinary dict"}` 被这条 try 收成失败：公开 `failed=1/blocked=0`，entry error 是 `slice(None, 200, None)`（`KeyError(slice)` 的 `str`），`outcome_status=failed`。并行成功路径原本会先 `str()`。这不是本提交引入的回归，也没有被本提交修掉。
- **残留，公开计数是对的，runner `_states` 没有同步引擎 SKIPPED。** 验证步公开 `skipped=1`、`StepStatus.SKIPPED`，但 `pending_steps()` 仍返回它，`is_complete=False`，`completed_count=1`，`PlanOutcome.steps` 不含它。动态桥只对 `results` 里出现的 step id 调用 `mark_completed` / `mark_failed`。这个验证步不在 results 里。原 P2 点名的失败步、独立 PENDING、依赖 PENDING 不被计 skipped，这次都成立。
- **残留，事件先于桥。** 单步动态 dict 哨兵：引擎在桥之前发出 `step_transition status=completed`，并因当时步骤仍是 COMPLETED 而走 degraded goals-met，`final_status=terminated_early`，同时 `blocked=1`。桥随后把活对象改成 `FAILED`，没有再发一条 transition。`workflow_engine.py` 不在本 delta。原 P2 的两步 dry-abort 用例仍是 `final_status=failed`。
- **非阻断，docstring 与实现的优先级。** 同一 entry 上若 `outcome_status="blocked"` 而显式 `step_outcomes` 给的是 FAILED，默认读到的 additive 键胜出，适配器是 BLOCKED。函数后半段把这个键写成默认事实；前半段仍写 “传入 `step_outcomes` 时它是唯一事实来源”。当前要求的默认两参、JSON、以及两边一致时的 opt-in，都成立。

## 4. 这次实际跑过的检查

| 检查 | 结果 |
|---|---|
| 探针 `/tmp/b3-r2-grok-post/probe.py` → `/tmp/b3-r2-grok-post/probe-output.json` | 18 项全过。`StepRunner.__file__` 与 `PlanExecutionResult.__file__` 都在本快照 `src/`。`source_unchanged=true` |
| `uv run --extra dev pytest tests/agent tests/core/orchestration tests/core/skills/test_workflow_engine_enhanced.py -q --tb=line -p no:cacheprovider` | **826 passed**，13.47s。解释器 CPython 3.12.13，本快照 `.venv`，`pythonpath=src` |
| `ruff check` 三个改动的 Python 文件 | All checks passed |
| `ruff format --check` 同一组文件 | 3 files already formatted |
| `basedpyright --level error` | **0 errors, 0 warnings, 0 notes**。有一条 Node `NO_COLOR`/`FORCE_COLOR` 环境警告，不是类型错误 |

父流程容器证据只读、本次未重跑：`/tmp/vibesop-opt-20261009/logs/B3-r2-target-container.log.result.json` 记录 image `vibesop-next-val:node24`、同一 patch sha256、同一组 pytest 参数、`exit_code=0`。日志末行是 `826 passed in 4.36s`。该日志正文没有嵌入 commit SHA。

第一次探针曾在身份用例上失败：执行器返回的是 `"ok"`，断言却要求 handoff 含字面量 `work-by-implementer`。失败点之前，对象身份、`skill_id`、`input_query`、`role_prompt`、`skill_isolation` 已经通过。该输出留在 `/tmp/b3-r2-grok-post/probe-output-run1.json`。修正执行器返回值后的第二次探针是上面的权威结果。没有执行或覆盖 `/tmp/b3-grok-post/`、`/tmp/b3-r2-kimi-pre/`、`B3-post-corrective-native-output.json`。

## 5. 局限

- 未跑全套，未重跑 Docker / Node24。容器 826 是父流程日志，不是这次的进程。
- `uv sync --extra dev --frozen` 在本快照生成了 gitignore 的 `.venv`（70 个包）。按既有约定保留，未改 lock 或已跟踪文件。
- `input_query` 的生产原值在这条 squad 计划上是空字符串。身份证据是对象身份和 `implskill` / `revskill`。
- 第 3 节的串行 dict `mark_completed`、验证步 runner pending、事件时间差、docstring 优先级，是分开登记的基线或残留，不是本裁决要打回的原 finding。

原 P1 的默认两参与真实 JSON、原 P2 的动态状态/计数/真实 SKIPPED 与 PENDING、原 NIT 的 F1 注释，以及点名的 callback、review 错误轴、engine run-complete、C7，在当前 commit 上成立。**APPROVE**。
