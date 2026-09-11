# Lane Cgold — 10 文件人工金标（只读）

你是 **kimi**（第二路，与写 parser 的那路互不见面），在 worktree `/Users/huchen/Projects/vibesop-evo-Cgold-kimi`、分支 `feat/evo-Cgold`。

任务是给方向 C 做 **10 文件人工对答案**，不是写 parser。不要实现 `parse_gate_findings.py`。

## 只许写

- `.omx/artifacts/gate-findings-gold-10.json`
- `.omx/artifacts/evo-lane-Cgold-handback.md`

## 只许读

- `/Users/huchen/Projects/vibesop-py/.omx/artifacts/gate*.md`（从主仓读，保证和历史文件一致）
- 提案方向 C

## 选文件（必须异构）

至少包含：

- 2 个 `gate*-review-claude.md`（`[P1]` 编号列表风格，如 gate1）
- 2 个 `gate*-claude.md` 且不是 review- 前缀（如 gate10 的 VERDICT/NITS）
- 2 个 `*-pi.md`
- 1 个 `*-grok.md`（若存在 findings）
- 1 个 `*-synthesis.md`
- 其余补到 10，优先「明显有条目」的文件；其中至少 1 个你判断为「无结构化 finding」（覆盖率分母需要负例）

## 金标 JSON 形状

```json
{
  "schema": "gate-findings-gold-v1",
  "observational": true,
  "files": [
    {
      "path": ".omx/artifacts/gate1-review-claude.md",
      "gate": "gate1",
      "reviewer": "claude",
      "parseable": true,
      "findings": [
        {"severity": "P1", "raw_title": "...", "line": 15}
      ],
      "notes": "标签体系: [P0/P1/P2]/nit"
    }
  ]
}
```

规则：

- 只标你**看见的**条目。不要补「作者可能想说但没写」的 finding。
- severity 用 P0/P1/P2/NIT。原文 MAJOR→P1，MINOR→P2，NIT/NITS 项→NIT。
- `parseable: false` 用于完全无法抽出条目的文件，`findings: []` 并写 notes。
- 不要做跨文件去重（那是 parser 的事）。金标是「单文件抽出什么」。

## 提交

```
git add .omx/artifacts/gate-findings-gold-10.json
git commit -m "docs(obs): gold labels for 10 gate finding files"
```

若 `.omx/` 被 exclude 导致 `git add` 忽略：用 `git add -f .omx/artifacts/gate-findings-gold-10.json`。不要 add 别的 artifact。

不要 push。

## Handback

`.omx/artifacts/evo-lane-Cgold-handback.md`

写：选了哪 10 个文件、各抽出几条、标签体系、有几个 parseable=false。这不是 parser 精确率（你没有 parser）。不要编精确率数字。
