---
id: builtin/slash-orchestrate
name: slash-orchestrate
description: Multi-skill orchestration for complex requests. Decomposes complex queries into sub-tasks and builds a serial/parallel execution plan.
version: 2.0.0
tags: [orchestrate, plan, multi-step, compose, parallel, workflow]
commands:
  - orchestrate
intent: orchestration
namespace: builtin
type: standard
user-invocable: true
---

# /orchestrate — Multi-Skill Orchestration

Decompose a complex, multi-intent query into an execution plan with ordered or parallel steps.

## Execution

```bash
vibe orchestrate "<QUERY>" --verbose
```

## Examples

```
/orchestrate 分析架构并review代码然后优化性能
/orchestrate review + qa + ship --strategy parallel
```

## What It Shows

- Detected intents (sub-tasks)
- Execution strategy (sequential/parallel/hybrid)
- Each step with matched skill and confidence

After orchestration, run `vibe route --execute` for interactive step-by-step.
