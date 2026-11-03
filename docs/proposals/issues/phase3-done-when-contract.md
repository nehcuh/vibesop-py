# [FEATURE] Phase 3 · done_when 契约化：ExecutionStep 验收判据 + 激活 OutputSchema 死代码

> 对应路线图: `docs/proposals/harness-verification-roadmap.md` Phase 3（P1，地基性）
> 依赖: Phase 1 合并后启动二期

## Feature Description

给 ExecutionStep 加结构化 `done_when` 字段（可拆两期：一期字段+语义，二期机器执行），激活 OutputSchema 死代码做最小校验。完成后文章公式 ①（TASK CONTRACT 的 Done when）才真正闭环。

## Problem Statement

- `core/models.py:319-410` ExecutionStep 24 个字段**无验收判据字段**，`intent` 是自由文本；
- `task_decomposer.py:22-31,105-129` LLM 分解 prompt 只要求 intent/query/skill_id/task_type，从不生成 done-when；
- `verifier.py:105-110,233-281` verify rubric 用通用四维打分，判据非来自步骤契约；
- `collaboration_protocol.py:52-65` + `models.py:925` 的 **OutputSchema 是死代码**：定义后全仓无实例化、无校验消费；
- `models.py:1078-1103` 完成判据 = agent 自报 `<!-- [StepCompleted:N] -->` marker，grep 全 src 仅生成点、无机器解析判定点；
- `verification_loop.py:239-252` verify_step 默认无条件 `return True`。

## Proposed Solution

**一期（字段 + 语义）**：
1. ExecutionStep/SubTask 加可选 `done_when`，类型三选一：`sentinel` / `command` / `section-schema`；
2. `task_decomposer.py` 分解 prompt 增加该键的生成；
3. `verifier.py` rubric 从步骤契约取判据，替代通用四维。

**二期（机器执行）**：
4. 激活 OutputSchema 做 required_sections 最小校验；
5. 补 `<!-- [StepCompleted:N] -->` marker 的机器判定点。

## Alternatives Considered

只做 LLM 语义判据（rubric 引用 done_when 文本）不建机器校验——作为一期保留，但二期机器校验是 evidence gate 的最终形态，不可省。

## Additional Context

本项是 Phase 1 default-deny 的正向补全：翻转后必须有「什么才算过」的机器定义，否则全部输出都会被拒。

## Priority

- [ ] Critical
- [x] High

## Implementation Ideas

类型三选一的设计：sentinel（哨兵词表，兼容现有 blocked:/failed: 词汇）、command（shell 命令退出码，如 ./check.sh）、section-schema（输出分节结构校验）。可分 PR 按序落地。

## Willing to Contribute

- [ ] Yes, I'd like to implement this feature
- [ ] No, I don't have time to implement it
- [x] Maybe, I'd need guidance

## Additional Notes

4 文件改动面（models/decomposer/verifier/plan_builder），建议两期各一个 PR。
