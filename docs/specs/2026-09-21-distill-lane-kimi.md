# Lane F9+F10 — 晋升四要素 + 账本入库（Kimi）

你是 **kimi**。只在 worktree `/Users/huchen/Projects/vibesop-distill-kimi`、分支 `feat/distill-f9` 上工作。主仓有未提交文件，**不要在主仓写代码**。

先 `cd /Users/huchen/Projects/vibesop-distill-kimi`。

## 先读

1. `/Users/huchen/Projects/vibesop-py/docs/specs/2026-09-21-skill-distill-landing.md`
2. `/Users/huchen/Projects/vibesop-py/docs/research/2026-09-09-agent-skills-paper.md` 建议 #4
3. `/Users/huchen/Projects/vibesop-py/docs/research/research-survey.md` §7 F9/F10
4. `/Users/huchen/Projects/vibesop-py/.omx/artifacts/skill-distillation-review-20260921.md` P1 F9、P2 F10、P3 workflow
5. 本 worktree：`src/vibesop/core/observability/skill_promote.py`（`_render` SKILL.md 模板，约 1953 行起）、`promote_verifier.py`（灯不是闸）、`core/skills/skill-craft/SKILL.md`「Skill Generation Template」、`core/skills/adversarial-panel/SKILL.md` 第 3 步、`scripts/check_artifact_links.py` 头部政策

## 要解决的问题

1. **F9**：候选技能写清前提、反例、验证方法、来源成败。现在 promote 草稿和 skill-craft 模板没有这四格。gate34 裁决：过滤自动化，不过滤人审 → 缺项只能 WARN。
2. **F10**：综述引用 `gate43-t7-echo-measure.md` / `gate43-t14-echo-measure.md`，文件在成稿机磁盘、未进 git。`adversarial-panel` 第 3 步依赖未跟踪的 `.grok/workflows/`（主仓甚至没有这个目录）。

主仓磁盘副本（只读复制源）：

- `/Users/huchen/Projects/vibesop-py/.omx/artifacts/gate43-t7-echo-measure.md`
- `/Users/huchen/Projects/vibesop-py/.omx/artifacts/gate43-t14-echo-measure.md`

复制进本 worktree 后再 `git add -f`。不要改测量正文。

## Phase 1 — 产品设计（必须先完成）

写到本 worktree：`docs/specs/2026-09-21-distill-f9-design.md`

必须回答：

1. **四要素的字段名、位置**（frontmatter vs 正文标题）、空位占位文案、人审最低完成定义。
2. **verifier**：缺哪一项 → 什么 WARN 码；永远不 FAIL、不阻断 activate。与现有 PASS/WARN 如何并存。
3. **skill-craft 模板**与 promote 渲染如何共用同一份结构，避免两套标题。
4. **workflow 悬空**：把最小 `adversarial-review` workflow **入库** `.grok/workflows/`，或改 SKILL.md 第 3 步为「无 Grok workflow 时 5+N 自举」。选一个，写清新 clone 行为。
5. **gate43 入库**：`git add -f` 两条测量；确认 `scripts/check_artifact_links.py` 在引用它们的 tracked md 上不再 dangling。不编造 t21。
6. **建议 grok 写入 project-knowledge 的 F9/F10 条目草稿。**

顶部 `Status: DESIGN LOCKED` 后再改 `src/`。不要等人确认。

## Phase 2 — 开发

只许改总计划「F9 kimi」可写文件。不要改 `core/registry.yaml`。不要改 skill_injector。

## 验收（贴输出）

```bash
cd /Users/huchen/Projects/vibesop-distill-kimi
uv run ruff check src/ tests/ --quiet
uv run pytest tests/unit/ -q --tb=short -k promote or -k skill_promote or -k artifact_links
git ls-files .omx/artifacts/gate43-t7-echo-measure.md .omx/artifacts/gate43-t14-echo-measure.md
uv run python scripts/check_artifact_links.py
```

`check_artifact_links.py` 若全库仍有其他历史 dangling，handback 里列出**本轮新引入或本轮应修的**条目，不要顺手修无关断链。

## Handback

`.omx/artifacts/distill-lane-f9-handback.md`

按总计划 §6。commit，不要 push。若 kimi 会在交互里问权限：全部选自动执行，做到 handback 为止。
