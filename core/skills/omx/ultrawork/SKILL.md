---
id: omx/ultrawork
name: Ultrawork
description: Tier-aware parallel execution engine for independent tasks.
intent: parallel execution
namespace: omx
version: 1.0.0
type: prompt
trigger_when: asked to execute multiple independent tasks in parallel with different complexity tiers
---

# Ultrawork — Tier-Aware Parallel Execution

Execute independent tasks in parallel with appropriate effort tiers.

## Task Tiers

- **LOW**: Simple, well-defined tasks (quick execution, minimal verification)
- **STANDARD**: Normal complexity tasks (standard verification: tests + lint)
- **THOROUGH**: Critical/complex tasks (full verification: tests + lint + type check + architect review)

## Workflow

1. **Decompose**: Break work into independent tasks
2. **Tier Assignment**: Assign each task to LOW/STANDARD/THOROUGH
3. **Parallel Execution**: Run all tasks simultaneously
4. **Aggregate**: Collect results from all workers
5. **Verify**: Run tier-appropriate verification on each result
6. **Report**: Summary of completed/failed/skipped

## State

Save to `.vibe/state/team/{session-id}/ultrawork.json`:
```json
{
  "session_id": "...",
  "total_tasks": 5,
  "tiers": {"low": 2, "standard": 2, "thorough": 1},
  "completed": 4,
  "failed": 1,
  "status": "completed"
}
```

## When to Use

- Multiple independent files to create/modify
- Batch operations (e.g., add tests to 5 modules)
- Parallel refactoring across unrelated components

## When NOT to Use

- Tasks have dependencies between them (use ralph)
- Only 1-2 tasks (overhead not worth it)
- Tasks need architectural coordination (use team)
