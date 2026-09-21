# Lane F2 — 技能消费分账（Pi）

你是 **pi**。只在 worktree `/Users/huchen/Projects/vibesop-distill-pi`、分支 `feat/distill-f2` 上工作。主仓有未提交文件，**不要在主仓写代码**。

先 `cd /Users/huchen/Projects/vibesop-distill-pi`。

## 先读

1. `/Users/huchen/Projects/vibesop-py/docs/specs/2026-09-21-skill-distill-landing.md`
2. `/Users/huchen/Projects/vibesop-py/docs/research/2026-09-09-agent-skills-paper.md` 建议 #3
3. `/Users/huchen/Projects/vibesop-py/docs/research/research-survey.md` §7 F2、§9.3「技能消费的在线检测」
4. `/Users/huchen/Projects/vibesop-py/.omx/artifacts/skill-distillation-review-20260921.md` 的 F2 段
5. 本 worktree：`src/vibesop/core/observability/tool_call_bridge.py`、`route_observe.py`、`src/vibesop/agent/runtime/agent_runtime.py`（只读，看现有信封）、`src/vibesop/cli/commands/` 里 observability / skills 命令风格

## 要解决的问题

R6：路由 2/2 no-match、SKILL.md 读取 0 次，分数仍 22/25。没有分账就会把脚手架赢写成「技能有效」。论文要求分开记录：**选中、读到、适用、执行、验收**。读取 ≠ 有效。

## Phase 1 — 产品设计（必须先完成）

写到本 worktree：`docs/specs/2026-09-21-distill-f2-design.md`

必须回答：

1. **五段操作定义**（每一段：生产者、数据源、何时记、缺测时的值）：
   - selected（路由选中）
   - read（SKILL.md 进入上下文 / 被读）
   - applicable（agent 判定适用，或我们只能记 unknown）
   - executed（按技能步骤做事的证据）
   - accepted（验收通过；可与 verify-result 对齐，但不要新门禁）
2. **哪几段本轮能诚实落地，哪几段只能 `unknown`。** 不要假装能测「适用」。
3. **存储**：jsonl 路径、隐私（query 哈希 vs 原文）、轮转。复用 `.vibe/observability/` 惯例。
4. **查询面**：CLI 一条命令能打印某次 route/session 的五段。无数据 fail-soft，exit 0 + 空结构。
5. **非目标**：不改匹配分数、不改注入正文、不当 CI 门禁、不把分账当成功率。
6. **测试**：用真实 `to_dict()` / 序列化形状钉契约，不手搓 key（项目纪律）。
7. **建议 grok 写入 project-knowledge 的 F2 条目草稿。**

顶部加 `Status: DESIGN LOCKED` 后再写 `src/`。不要等人确认。

## Phase 2 — 开发

只许改总计划「F2 pi」可写文件。优先**新建模块** + 最小接线。不要重写 tool_call_bridge。

`applicable` / `executed` / `accepted` 若本轮测不到，schema 里保留键，值用 `null` + `reason`，测试钉住这个诚实空值。

## 验收（贴输出）

```bash
cd /Users/huchen/Projects/vibesop-distill-pi
uv run ruff check src/ tests/ --quiet
uv run pytest tests/unit/ -q --tb=short -k consumption or -k ledger or -k distill_f2
# 按你实际测试文件名调整；把完整命令写进 handback
```

## Handback

`.omx/artifacts/distill-lane-f2-handback.md`

按总计划 §6。commit，不要 push。
