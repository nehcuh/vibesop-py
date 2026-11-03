# [FEATURE] Phase 5 · 工具级权限三档：allow / require_approval / deny

> 对应路线图: `docs/proposals/harness-verification-roadmap.md` Phase 5（战略级，单独立项）
> 来源: 文章公式 ④「The model recommends. The harness decides. The tool executes.」

## Feature Description

在 security / hooks / adapter 三层引入工具级权限三档（allow 自由跑+留痕 / require_approval 人先点头 / deny 车道封死），补齐 L3 的最后一块。当前**三层全部是二态 allow/block**。

## Problem Statement

| 层 | 现状证据 |
|---|---|
| security 层 | `security/rules.py:13-26` RiskLevel 是严重度非权限档；`scanner.py:416-419`、`path_safety.py:120-126` 均 bool/raise（fail-closed 但无中间档） |
| hook 层 | `adapters/hook_based.py:175-185` 仅注入 additionalContext，无 permissionDecision；「human confirmation」（`routing-protocol.md.j2:12,23`）是**模型指令**非 harness 强制 |
| adapter 层 | `adapters/claude_code.py:580-586,708-745` settings permissions **只有 allow 数组**，无 deny/ask |
| 官方自认 | `core/loop/models.py:215-222` guard 字段注释 "human-approval… **Not yet implemented**" |

后果：「不要动生产」是愿望，受保护分支才是墙。有真实后果的动作不能依赖模型记住一句话。

## Proposed Solution

1. 引入 `PermissionTier` 枚举（allow / require_approval / deny）贯通三层；
2. hook 层输出 permissionDecision（对齐各家 hook 协议的允许/拒绝返回值）；
3. adapter 层生成 ask/deny（Claude Code settings 支持 ask/deny 语法）；
4. 设计要点（文章原则）：**closed lane ≠ very high threshold**——阈值会被赶时间的人调低，封死的车道保持封死（如 delete_data / rotate_credentials / publish_global / merge main）。

## Alternatives Considered

只在 prompt 层写权限规则——被否：文章原话「A closed lane is different from a very high threshold. Thresholds get adjusted when someone is in a hurry. Closed lanes stay closed.」

## Additional Context

改动横跨 security/ + adapters/ + hooks/，且需逐一核对 6 家 agent 平台的 hook/permissions 协议差异（kimi/pi/opencode 等的 permissions 生成本次评审未穷尽）。走正常立项流程，路线图不展开设计细节。

## Priority

- [ ] Critical
- [x] High

## Implementation Ideas

从 adapter 层最小切入（Claude Code 的 ask/deny 语法是现成的），再向 hook 层回推 permissionDecision，security 层最后做 Tier 贯通。

## Willing to Contribute

- [ ] Yes, I'd like to implement this feature
- [ ] No, I don't have time to implement it
- [x] Maybe, I'd need guidance

## Additional Notes

本文是立项占位卡，设计文档另行输出。
