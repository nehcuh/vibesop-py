# Lane F1 — spec 缺口与注入策略（Claude Code）

你是 **claude**。只在 worktree `/Users/huchen/Projects/vibesop-distill-claude`、分支 `feat/distill-f1` 上工作。主仓有未提交文件，**不要在主仓写代码**。

先 `cd /Users/huchen/Projects/vibesop-distill-claude`。

## 先读（给路径，自己打开）

1. `/Users/huchen/Projects/vibesop-py/docs/specs/2026-09-21-skill-distill-landing.md`
2. `/Users/huchen/Projects/vibesop-py/docs/research/2026-09-09-agent-skills-paper.md`
3. `/Users/huchen/Projects/vibesop-py/docs/research/research-survey.md` §7 F1、§9.2 #1
4. `/Users/huchen/Projects/vibesop-py/.omx/artifacts/skill-distillation-review-20260921.md` 的 F1 段
5. 本 worktree：`src/vibesop/agent/runtime/skill_injector.py`、`src/vibesop/agent/runtime/agent_runtime.py`、`core/skills/adversarial-panel/SKILL.md`（当「真内化」样板）、`core/registry.yaml` 末尾技能条目

## Phase 1 — 产品设计（必须先完成）

写到本 worktree：`docs/specs/2026-09-21-distill-f1-design.md`

必须回答：

1. **用户是谁、何时触发**：写任务书的人 / 路由注入 / 两者。
2. **「spec 写满」的操作定义**：可测试的判定（长度、验收清单、是否已是完整需求文档）。承认误判代价：假阳性少注入会藏技能；假阴性继续过灌。
3. **选哪条产品路径，为什么**：
   - A. 新建 builtin 技能 `task-briefing`（教 agent 先写满任务书）
   - B. 注入层 report-only 注释（候选仍注入，信封上标 `spec_gap: low|unknown`）
   - C. A+B
   - 禁止：未验证启发式直接跳过注入（论文笔记：不要恢复每次注入，也不要用弱启发式当闸）
4. **对外契约**：hook JSON / CLI 多一个什么字段；缺字段时的旧客户端兼容。
5. **非目标**：不改匹配器、不改 hermetic、不当 CI 门禁、不声称「技能无用」。
6. **测试计划**：golden + 负例（短闲聊 vs 带验收清单的长任务书）。
7. **建议 grok 写入 project-knowledge 的 F1 条目草稿。**

写完设计后在同一文档顶部加：`Status: DESIGN LOCKED`。然后才进入 Phase 2。不要停下来等人确认——任务书已授权设计锁定后继续开发。

## Phase 2 — 开发

只许改总计划「F1 claude」那一行的可写文件。`core/registry.yaml` 只追加，不改既有 id。

若选 A：技能必须有 When-NOT-to-use、Anti-Patterns、Exit Criteria（对齐 adversarial-panel 的内化质量）。

若选 B：字段默认 `unknown`；启发式失败要 fail-open（当 unknown，不抑制注入）。

## 验收（贴输出）

```bash
cd /Users/huchen/Projects/vibesop-distill-claude
uv run ruff check src/ tests/ --quiet
uv run pytest tests/agent/runtime/ -q --tb=short
# 再跑你新增测试文件
```

Hermetic 指纹不应变。若变了，在 handback 写明原因，不要「修」benchmark.py。

## Handback

`.omx/artifacts/distill-lane-f1-handback.md`（本 worktree）

按总计划 §6。最后 `git add` 你改过的文件并 commit，message 用 conventional。不要 push。
