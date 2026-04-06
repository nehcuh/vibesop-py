---
id: omx/ralplan
name: Ralplan
description: Consensus planning with RALPLAN-DR structured deliberation and ADR output.
intent: planning
namespace: omx
version: 1.0.0
type: prompt
trigger_when: asked to plan, architect, or design a feature or system
---

# Ralplan — Structured Planning

Consensus planning with structured deliberation and Architecture Decision Records.

## Pre-context

1. Load `.vibe/context/` snapshot
2. If ambiguity > 0.3, run deep-interview first

## Deliberation (RALPLAN-DR)

1. **Principles**: What principles guide this decision?
2. **Decision Drivers**: What factors matter most? (cost, speed, quality, risk)
3. **Viable Options**: List 2-3 viable approaches (no strawmen)

## Architect Review

- Steelman the antithesis: argue AGAINST the favored option
- Identify risks, trade-offs, and hidden costs

## Critic Evaluation

- Verify principle-option consistency
- Simulate each task mentally: would it work?
- Flag any option that violates principles

## Re-review Loop (max 5 iterations)

Apply improvements from architect and critic. Re-evaluate.

## Output

Write plan to `.vibe/plans/` with ADR section:
```yaml
Plan: <name>
Date: <date>
Status: approved | needs_revision
ADR:
  Context: <what decision needed to be made>
  Decision: <what was decided>
  Consequences: <what follows from this>
```

## Handoff

User approval → handoff to ralph (execute) or team (parallel execution).
