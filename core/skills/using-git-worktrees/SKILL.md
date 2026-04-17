---
name: using-git-worktrees
description: Parallel task isolation using git worktrees - create, manage, and clean up isolated branches
tags: [git, worktree, branch, isolate, parallel, workspace, 创建, 独立, 分支, 隔离, 并行]
version: 1.0.0
commands:
  - worktree-create
  - worktree-list
  - worktree-finish
  - worktree-remove
  - worktree-cleanup
  - cascade-run
  - cascade-plan
---

# Git Worktrees & Cascade Execution

Use this skill when you need to work on multiple independent tasks in parallel without polluting the main working tree, or when you want to run a dependency-ordered pipeline of shell commands.

## When to use

- Starting a feature that should be isolated from current in-progress work
- Running parallel experiments (A/B implementations)
- Executing a CI-like pipeline locally with `vibe cascade`

## Worktree workflow

```bash
# 1. Create an isolated worktree for a task
vibe worktree create "add payment feature"
# → prints the path and branch name

# 2. Work inside the worktree
cd <path>
# ... make changes, commit ...

# 3. Mark done when finished
vibe worktree finish <id>

# 4. Clean up all finished worktrees at once
vibe worktree cleanup
```

## Cascade workflow

Define a YAML pipeline and run it:

```yaml
# ci.yaml
tasks:
  - id: lint
    command: rubocop lib/
  - id: test
    command: ruby test/unit/test_*.rb
    depends_on: [lint]
  - id: build
    command: rake build
    depends_on: [test]
```

```bash
vibe cascade plan ci.yaml   # preview execution order
vibe cascade run  ci.yaml   # execute (parallel where possible)
```

## Key behaviours

- Independent tasks run in parallel automatically
- A failed task causes all downstream dependents to be **skipped**
- `stop_on_failure: false` in the YAML lets unrelated tasks continue
- `max_parallel: N` caps concurrency
