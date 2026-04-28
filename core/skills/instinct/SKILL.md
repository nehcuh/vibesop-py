---
id: builtin/instinct
name: instinct
description: Instinct learning system — record patterns, review candidates, view status, import/export, and evolve instincts into formal skills. Memory over intelligence.
version: 2.0.0
tags: [instinct, pattern, learn, extract, habit, memory, evolve, 本能, 模式, 学习]
commands:
  - instinct learn
  - instinct eval
  - instinct status
  - instinct export
  - instinct import
  - instinct evolve
intent: learning
namespace: builtin
type: standard
user-invocable: true
---

# /instinct — Instinct Learning System

> **Memory > Intelligence.** Remember what worked. Reuse it.

Record successful workflow patterns, review auto-detected candidates, and evolve the best instincts into formal skills.

## Sub-Commands

All commands are executed via `vibe instinct <subcommand>`.

### `/instinct learn` — Record a Pattern

```bash
vibe instinct learn "<pattern description>" "<action to take>" \
    --context "<when it applies>" \
    --tag python --tag testing
```

### `/instinct eval` — Review Candidates

```bash
vibe instinct eval
# JSON output:
vibe instinct eval --json
```

### `/instinct status` — View All Instincts

```bash
vibe instinct status
vibe instinct status --tag python
vibe instinct status --json
```

### `/instinct export` — Export to JSON

```bash
vibe instinct export
vibe instinct export --output backup.json --min-confidence 0.8
```

### `/instinct import` — Import from JSON

```bash
vibe instinct import instincts-export.json
vibe instinct import instincts-export.json --force
```

### `/instinct evolve` — Upgrade to Skill

```bash
vibe instinct evolve          # list evolution candidates
vibe instinct evolve --index 0 # evolve the first candidate
```

## When to Use

- After a successful tool sequence (3+ consecutive successes)
- At session end to review accumulated patterns
- Before team sharing: export high-confidence instincts
- When an instinct has 10+ successful uses: evolve it to a formal skill

## Storage

All instincts stored in `.vibe/instincts.jsonl`. Sequence patterns in `.vibe/sequences.jsonl`.
