---
id: builtin/commit-message
name: commit-message
description: Write the commit message for staged changes — conventional format, why over what
tags: [commit message, write commit, git commit, conventional commits,
       commit subject, 提交信息, 写提交, 提交说明, commit 描述,
       commit msg, git 提交]
triggers:
  - "write a commit message"
  - "draft the commit message"
  - "帮我写提交信息"
  - "写个提交说明"
version: 1.0.0
allowed-tools:
  - Read
  - Bash
intent: Draft a conventional-format commit message from the staged diff, explaining why the change was made
namespace: builtin
type: prompt
---

# Commit Message — Conventional Format, Why Over What

> Trigger: "help me write a commit message" / "帮我写提交信息"

Discipline: **the diff already says what changed; the message must say why.**

## Core Steps

### 1. Read the change, not the filename
- `git diff --staged` (fall back to `git diff` if nothing staged; say so).
- `git log --oneline -10` for the repo's message style — follow it.

### 2. Classify
- type: feat / fix / refactor / docs / test / chore / perf / build / ci
- scope (optional): the subsystem touched, if the repo uses scopes.

### 3. Subject line
- `<type>(<scope>): <imperative summary>` ≤ 72 chars, no trailing period.
- Imperative mood: "add", not "added" / "adds".

### 4. Body (when the why is non-obvious)
- The reason for the change — constraint, bug, requirement.
- What trade-off was chosen and what was rejected (one line each).
- Wrap at 72 chars; blank line between subject and body.

### 5. Verify against the diff
- Every claim in the message is true of THIS diff — no aspirational prose.
- If the change is two unrelated things, say so: recommend splitting.

## Anti-Patterns

- ❌ "update files" / "fix bug" / "misc changes"
- ❌ Message narrates the diff line-by-line (that's what diff is for)
- ❌ One commit secretly containing two logical changes
- ❌ Subject > 72 chars or past/present-tense mismatch with repo style

## Exit Criteria

- [ ] Conventional type matches the actual nature of the change
- [ ] Subject ≤ 72 chars, imperative, no period
- [ ] Body answers "why" (or states it was unnecessary)
- [ ] Message verified against the staged diff
