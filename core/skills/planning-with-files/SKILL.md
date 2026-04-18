---
id: builtin/planning-with-files
name: planning-with-files
version: "1.0.0"
description: File-based planning for complex tasks. Creates task_plan.md, findings.md, and progress.md. Use for multi-step tasks requiring >5 tool calls.
tags: [plan, planning, design, architect, complex, task, 规划, 设计, 计划]
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - WebFetch
  - WebSearch
intent: planning
namespace: builtin
version: 1.0.0
type: prompt
---

# Planning with Files

Work like Manus: Use persistent markdown files as your "working memory on disk."

## The Core Pattern

```
Context Window = RAM (volatile, limited)
Filesystem = Disk (persistent, unlimited)

→ Anything important gets written to disk.
```

## Quick Start

Before ANY complex task:

1. **Create `task_plan.md`** — Phase tracking with acceptance criteria
2. **Create `findings.md`** — Research storage
3. **Create `progress.md`** — Session logging
4. **Fill Acceptance Criteria** — Define done *before* writing code
5. **Re-read plan before decisions** — Refreshes goals in attention window
6. **Update after each phase** — Mark complete, log errors

## File Purposes

| File | Purpose | When to Update |
|------|---------|----------------|
| `task_plan.md` | Phases, progress, decisions | After each phase |
| `findings.md` | Research, discoveries | After ANY discovery |
| `progress.md` | Session log, test results | Throughout session |

## Critical Rules

### 1. Create Plan First
Never start a complex task without `task_plan.md`. Non-negotiable.

### 2. The 2-Action Rule
> "After every 2 view/browser/search operations, IMMEDIATELY save key findings to text files."

### 3. Read Before Decide
Before major decisions, read the plan file.

### 4. Update After Act
After completing any phase: mark status, log errors, note files changed.

### 5. Log ALL Errors
Every error goes in the plan file. Builds knowledge, prevents repetition.

### 6. Never Repeat Failures
```
if action_failed:
    next_action != same_action
```

## The 3-Strike Error Protocol

```
ATTEMPT 1: Diagnose & Fix
  → Read error carefully, identify root cause, apply targeted fix

ATTEMPT 2: Alternative Approach
  → Same error? Different method, different tool

ATTEMPT 3: Broader Rethink
  → Question assumptions, search for solutions, consider updating plan

AFTER 3 FAILURES: Escalate to User
  → Explain what you tried, share specific error, ask for guidance
```

## The 5-Question Reboot Test

| Question | Answer Source |
|----------|---------------|
| Where am I? | Current phase in task_plan.md |
| Where am I going? | Remaining phases |
| What's the goal? | Goal statement in plan |
| What have I learned? | findings.md |
| What have I done? | progress.md |

## When to Use This Pattern

**Use for**: Multi-step tasks (3+ steps), research, building projects, many tool calls
**Skip for**: Simple questions, single-file edits, quick lookups

## Anti-Patterns

| Don't | Do Instead |
|-------|------------|
| State goals once and forget | Re-read plan before decisions |
| Hide errors and retry silently | Log errors to plan file |
| Start executing immediately | Create plan file FIRST |
| Repeat failed actions | Track attempts, mutate approach |
