---
id: builtin/slash-evaluate
name: slash-evaluate
description: Evaluate skill quality and usage statistics. Check which skills are performing well and which need attention.
version: 2.0.0
tags: [evaluate, quality, stats, audit, health]
commands:
  - evaluate
intent: evaluation
namespace: builtin
type: standard
user-invocable: true
---

# /evaluate — Evaluate Skill Quality

Checks skill quality scores, usage statistics, and identifies underperforming skills.

## Execution

```bash
vibe evaluate
# Evaluate a specific skill:
vibe evaluate --skill <skill-id>
```

## Examples

```
/evaluate
/evaluate --skill gstack/review
```
