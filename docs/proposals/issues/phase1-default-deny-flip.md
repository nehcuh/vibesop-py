# [FEATURE] Phase 1 · default-deny 翻转：三处验证判定点从默认放行改为默认拒绝

> 对应路线图: `docs/proposals/harness-verification-roadmap.md` Phase 1（P0）
> 来源: X 文章七公式映射 + Claude Code 六路子代理取证（review_readonly，file:line 级）

## Feature Description

把验证判定从「白名单式放行」（非失败哨兵的任意输出 = 成功）翻转为「默认拒绝」（必须有正向判据才算成功）。这是 evidence gate 成立的地基，后续所有验证增强都依赖本项。

## Problem Statement

三处判定点目前默认放行，agent 无证据宣称完成会被记为成功——这正是 harness 层缺陷的定义：

1. `core/orchestration/verifier.py:60-63` — `status` 字段 Pydantic 默认值 = **PASSED**（LLM 未返回明确状态时直接通过）
2. `core/orchestration/collaboration_protocol.py:327-338` — DebateProtocol 解析失败 → `passed=True`
3. `core/orchestration/verification_loop.py:49-52` + `agent/step_runner.py:120-126` — 非 `blocked:`/`failed:` 哨兵前缀的任意散文 = SUCCESS

## Proposed Solution

| # | 改动点 | 目标 |
|---|---|---|
| 1 | `verifier.py:60-63` | 去掉默认值，或默认 ERROR |
| 2 | `collaboration_protocol.py:327-338` | 解析失败 → `passed=False` |
| 3 | `verification_loop.py:49-52` + `step_runner.py:120-126` | 要求正向判据（`passed:`/枚举匹配）才算成功 |

注意：`is_acceptance_failure` 是共享谓词（execution_protocol 亦引用），语义翻转保持哨兵侧不变、只收紧成功侧。

## Alternatives Considered

只修 verifier 默认值、保留散文判定——被否：散文判定是最大放行面，且 Phase 2 的失败分类要建立在收紧后的判定语义上。

## Additional Context

取证报告见路线图「Phase 1」一节。动工前须人工 diff 复核 file:line（评审时点 ≠ 当前 HEAD）。

## Priority

- [x] Critical

## Implementation Ideas

回归测试先行：无证据输出、无哨兵散文、解析失败三类输入不得记 SUCCESS/PASSED；盘点受影响测试基线，逐处说明预期变化原因。

## Willing to Contribute

- [ ] Yes, I'd like to implement this feature
- [ ] No, I don't have time to implement it
- [x] Maybe, I'd need guidance

## Additional Notes

default-deny 是行为变化（准 breaking），CHANGELOG 需记语义变化 + minor 版本 + 迁移说明。
