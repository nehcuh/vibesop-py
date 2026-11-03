# [FEATURE] Phase 2 · 可达性与重试语义：激活 ESCALATE 死分支 + 失败分类 + 验证环扩域

> 对应路线图: `docs/proposals/harness-verification-roadmap.md` Phase 2（P1，本迭代主线）
> 依赖: Phase 1（default-deny 翻转）先合并

## Feature Description

三个子项：激活不可达的 ESCALATE 升级通道；给失败加语义分类与「同错两次即停」；把验证环从 adversarial 独享扩到高风险计划。

## Problem Statement

1. **ESCALATE 死代码**：`verification_loop.py:134-179` 首次 failed → TERMINATE 即 break，`escalation_threshold=2`（`:64-71`）永不可达；ESCALATE 仅落为 error 字符串 "user intervention required"（`:420-421`），无升级出口。
2. **失败不分类**：decide_action 仅 passed/failed/needs_revision 三态；`step_runner.py:44-55,557,599` 异常统一裸 `except Exception` → FAILED。同一错误签名重复出现的检测**全库不存在**。
3. **验证环窄域**：仅 `workflow_pattern=="adversarial"` 生效（`verification_loop.py:362`），SEQUENTIAL/PARALLEL 计划无验证环。
4. **文档-代码矛盾**：`step_runner.py:7` docstring 宣称 "Configurable error recovery (skip / retry / abort)"，实际只有 skip/abort。

## Proposed Solution

### 2.1 激活 ESCALATE
连续失败 ≥ 阈值走 ESCALATE；接真实出口（写 plan_tracker 状态 + CLI 呈现给人）；顺带在 plan_tracker 补「风险/下一步」叙事字段（修法⑥缺口）。

### 2.2 失败分类 + 同错签名停
- 新增 FailureCategory 枚举接入 decide_action；
- **复用已有资产**：`core/loop/executor.py:64-106`（cron 子系统）已有 TRANSIENT/PERMANENT 关键词分类（timeout/429→重试；perm-denied/bad-args→不重试），迁移而非从零建；
- 错误签名 = type + message 归一化哈希，同签名两次 → ESCALATE；
- 与 `core/loop/models.py:210-214`（连续失败 ≥3 → DEAD，状态类别计数）语义对齐，本项补同一性判断。

### 2.3 验证环扩域（产品决策点）
至少让含 fallback / 低信任（QUARANTINE）步骤的计划默认走验证。

### 顺手修复
`step_runner.py:7` docstring 与实现矛盾——修文档或补实现，二选一。

## Alternatives Considered

失败分类从零设计枚举——被否：cron 子系统已有可迁移实现，语义一致性优先。

## Additional Context

B/E 两路子代理与架构对照路在「同错停」判定上有分歧（对照路初判「齐」），已用代码证据裁决为「不存在」：首次 failed 已 TERMINATE break。

## Priority

- [ ] Critical
- [x] High

## Implementation Ideas

见 Proposed Solution；先修 2.1（解锁 2.2 的 ESCALATE 语义），2.3 需产品侧确认默认策略。

## Willing to Contribute

- [ ] Yes, I'd like to implement this feature
- [ ] No, I don't have time to implement it
- [x] Maybe, I'd need guidance

## Additional Notes

建议与 Phase 1 同一迭代排期，但分 PR 落地。
