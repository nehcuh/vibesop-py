# 验证器与计划交付合同

状态：SPEC 已定稿，进入四路实现。基线：`efa616a`。主控维护本文件及进度日志；各执行代理只修改各自范围。

## 用户可见结果

默认对抗计划应能使用随包提供的验收技能，不要求安装 gstack。验证围绕用户原始要求和实际产物，代码、文档、分析、部署任务均可使用；不能把通用验收偷偷换成代码评审。任一步技能正文被现有扫描器拒绝时，所有计划交付入口均应阻断，不能继续宣称可执行。

## A：计划生成（Claude）

- `PlanBuilder.build_plan` 增加可选关键字参数 `verifier_skill_id`，缺省使用 `builtin/verify-result`。不增加模型调用，不读取环境变量决定验证器，不增加全局自动注入。
- 显式指定非空技能 ID 时使用指定值；空白、非字符串、`fallback-llm` 拒绝，不能静默回退默认。参数默认值必须与显式无效输入可区分。参数只作用于 ADVERSARIAL，其他工作流行为不变。
- 验证步骤依赖所有原步骤，保留 `is_verification_step=True`、QUARANTINE、pending 和原始请求。输入提供步骤类型、预期产出和需求，要求逐项证据；不能默认通过或自行执行部署。
- 仅改 `src/vibesop/core/orchestration/plan_builder.py`、`tests/core/orchestration/test_workflow_pattern.py`、新增 `tests/core/orchestration/test_verifier_selection.py`。

## B：内置验收技能（Grok）

- 新建 `core/skills/verify-result/SKILL.md`，ID 为 `builtin/verify-result`，明确仅在显式选择/编排选择时使用，`disable-model-invocation: true`，无宽泛自然语言触发器。
- 用平实中文描述：读取原始需求、产物和机器记录；按任务类型选检查方法（代码：测试与行为；文档：完整性与来源；分析：数据和计算；部署：已有授权下的实际状态）；缺证据标 blocked，实际失败标 failed，只有满足清单才 passed。模型评审与机器验收分别记录。
- 只做验收，不修改实现、不运行未获授权的部署、不标记计划完成；不能以代理自述代替证据，不自动调用其他代理。
- 新增 `tests/core/skills/test_verify_result_skill.py`：用真实 loader/元数据解析及现有扫描器验证可加载、ID/人工调用限制、正文可通过扫描。复用随包包含 `core/skills` 的机制，不改全局 registry 来获得自动触发。

## C：正文拒绝统一（Kimi）

- 在上一轮文件可用性检查基础上，使用既有 `is_skill_content_safe`/缓存；实际正文不安全或扫描器失败都阻断。`metadata.execution_ready=False`，`blocked_steps` 提供可区分的 unsafe 原因，保留所有原步骤、验证标志与来源。
- guide 无完成标记，hook/CLI 为 notice-only/has_match=false，manifest 抛出诊断异常；不能把拒绝提示当成技能正文继续生成可执行 manifest。
- manifest 实际读入正文后仍复核，避免注解与读取之间变更漏检；提示不回显危险正文。保留既有安全正文、单技能、来源优先级及空文件语义。
- 仅改 `src/vibesop/agent/runtime/skill_injector.py`、`src/vibesop/agent/runtime/plan_executor.py`，新增 `tests/agent/runtime/test_plan_content_safety.py`；确需修改已有安全测试预期时列明依据后同步。

## D：版本、使用文档及集成合同（Pi）

- 先将开发版本更新为 `8.3.0.dev1`：默认验证器与拒绝状态属于行为变化，使用 minor。同步 pyproject、uv.lock、当前版本文档；历史决策/日志版本不改写。完成后主控验收，再委派收口为 `8.3.0`。
- 维护 CHANGELOG 的本轮条目；既有未完成未来条目不盲目归入发布。
- 新增 `docs/architecture/verification-contract.md` 说明显式选择、任务类型验收、缺失与 unsafe 阻断、证据边界。
- 新增 `tests/integration/test_verification_delivery_contract.py`：基于真实模型/临时文件/实际内置技能检查默认计划可交付、指定缺失验证器阻断、安全文件改成不安全正文后拒绝。A/B/C 未集成时如预期失败，保留结果并等待集成，不 mock 掉待验收接口。
- 限定改动 pyproject/uv.lock、当前版本引用、CHANGELOG、上述新文档和集成测试；不改 A/B/C 源码。

## 验收与重要节点

1. SPEC 与进度日志提交并推送；四个真实 CLI 独立工作树从同一基线开始，报告任务进度与真实测试结果。
2. 每路完成后主控读 diff；Kimi 独立只读复审关键代码（Kimi 自己的改动另开独立会话，主控亲证）。退回问题仍由执行代理修复。
3. 定向测试与静态检查通过后分批集成、提交、推送，更新本日志。源码冻结后运行主机常规套件、固定路由题集、Linux Docker 相关套件，记录失败与复跑。
4. Docker 使用独立可写副本，宿主只读挂载、运行时禁网，依赖与版本更新后重建或重装待测 wheel。
5. 版本收口、PR、CI job 级结果记录并推送。仅更新代码与版本，不推会触发 PyPI 发布的标签。

不扩大到自动经验进化、全文采集或证明多代理收益；同题效果实验另定任务和预算。本轮不降低既有验收标准以获得绿灯。
