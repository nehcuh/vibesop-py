---
id: builtin/babysit-main
name: babysit-main
description: >-
  Use when the user asks to babysit a push until origin/main CI is green
  (babysit, baybsit, 盯 CI, 合到 main, watch CI until green on main).
  Already on main — not a pull-request merge skill.
tags: [babysit, baybsit, origin/main, watch CI, job-level CI, Quickstart E2E,
       盯 CI, 合并 main, 合到 main, 盯到绿, gh run]
triggers:
  - "babysit"
  - "baybsit"
  - "babysit 到合并 main"
  - "盯到合并 main"
  - "watch CI until green"
  - "合到 main"
  - "/babysit-main"
version: 1.0.0
allowed-tools:
  - Read
  - Bash
intent: >-
  After commit and push to origin/main, watch job-level CI plus Quickstart E2E
  for that SHA until green. Not PR babysit and not auto-merge.
namespace: builtin
type: prompt
---

# Babysit origin/main until CI is green

> Trigger: "babysit 到合并 main" / "baybsit 到合并main"

Discipline: **watch the SHA's jobs, not a PR.** This repo lands on
`origin/main` by direct push. Do not open a PR, do not `gh pr merge`,
and do not treat a GitHub API EOF as red.

## When NOT to use

- Full diagnose → fix batches → merge → `deep-diagnosis-optimization`
- Feature branch that still needs a PR decision → finishing-a-development-branch
- Review not yet arbitrated → `review-arbitration`

## Steps

### 1. Land on main

- Confirm `git branch --show-current` is `main` (or the user named a
  direct-to-main push).
- Commit only the files for this change. Do not add `.omx/`,
  `.grok/workflows/`, `examples/datasets/`, or `memory/session.md`
  unless the user asked.
- `git push origin main`. Record the SHA.

### 2. Watch job-level CI, not the check-run rollup

```text
gh run list --commit SHA
```

Required greens: **CI** (every job) **and** **Quickstart E2E**. A single
green job is not done.

Use a silent poller that prints only `DONE` / `FAILED` / `CANCELLED`.
Send `gh` stderr to a log file. **`gh` API EOF / timeout is transport,
not red** — restart the watcher; do not "fix" the tree.

### 3. On red: reproduce, then fix, then re-watch

- Read the failing job log. Reproduce locally before editing.
- Do not "rerun and hope" as the first fix.
- After the fix commit, push and **retarget the watcher at the new SHA**.
  Kill the old watcher.

## Common CI traps (this repo)

| Symptom | First hypothesis (not "flake") |
|---------|--------------------------------|
| Artifact Links `NEW_STALE` on a path ending `...` | Ellipsis is prose; strip trailing `...` before the `..`-segment guard |
| Ubuntu-only `test_recall` top-k swap | `hash()` fake embeddings + `PYTHONHASHSEED`; pin angles / use sha256 |
| Local artifact-link fail, CI clean | Untracked files under the glob; CI is a clean checkout |

## Anti-Patterns

- PR babysit / auto-merge when already on main
- Treating `gh` transport EOF as a failed run
- Watching only the workflow conclusion and missing a red job
- Committing session notes or review artifacts with the fix
- Leaving the watcher on the old SHA after a follow-up push

## Exit Criteria

- [ ] SHA on `origin/main`
- [ ] Every CI job green **and** Quickstart E2E green for that SHA
- [ ] Any red job reproduced and fixed; watcher retargeted
- [ ] No PR opened, no auto-merge
---
