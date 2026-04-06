---
id: omx/autopilot
name: Autopilot
description: Full autonomous lifecycle from idea to verified code.
intent: execution
namespace: omx
version: 1.0.0
type: prompt
trigger_when: asked to autonomously build a feature from idea to verified, shippable code
---

# Autopilot — Full Autonomous Lifecycle

Take an idea from concept to verified, shippable code without human intervention.

## Phases

1. **Clarify** (deep-interview): Resolve ambiguity until clarity ≥ 0.6
2. **Plan** (ralplan): Structured deliberation with ADR output
3. **Gate**: Pre-execution approval (architect + critic + user)
4. **Execute** (ralph): Persistent completion loop with deslop
5. **Verify** (ultraqa): Autonomous QA cycling
6. **Ship** (gstack/ship): Release workflow

## State Management

Save progress to `.vibe/state/sessions/{session-id}/autopilot.json`:
```json
{
  "session_id": "...",
  "current_phase": "execute",
  "phases": {
    "clarify": {"status": "completed", "clarity": 0.8},
    "plan": {"status": "completed", "plan_path": ".vibe/plans/..."},
    "gate": {"status": "completed", "approved": true},
    "execute": {"status": "running", "iteration": 3},
    "verify": {"status": "pending"},
    "ship": {"status": "pending"}
  }
}
```

## Entry Requirements

- Clear task description (or willingness to run deep-interview first)
- User consent for autonomous execution

## Exit Criteria

- All phases completed successfully
- Tests pass, lint clean, type check clean
- Code reviewed and approved
