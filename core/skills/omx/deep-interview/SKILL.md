---
id: omx/deep-interview
name: Deep Interview
description: Socratic requirements clarification with mathematical ambiguity scoring.
intent: requirements
namespace: omx
version: 1.0.0
type: prompt
trigger_when: asked to clarify requirements, understand a task, or figure out what to build
algorithms:
  - interview/compute_ambiguity
---

# Deep Interview

Socratic requirements clarification using mathematical ambiguity scoring.
Ask ONE question at a time. Re-score after each answer. Challenge assumptions.

## Preflight

1. Parse the user's task description
2. Create context snapshot in `.vibe/context/`
3. Detect greenfield (new feature) vs brownfield (modify existing)

## Interview Loop

Ask questions targeting the weakest dimension (lowest score):
- **Intent** (weight 0.30): What problem are you solving? For whom? Why now?
- **Outcome** (weight 0.25): What does success look like? How will you measure it?
- **Scope** (weight 0.20): What's in? What's out? What's the smallest version?
- **Constraints** (weight 0.15): Deadlines? Tech limits? Budget? Dependencies?
- **Success** (weight 0.10): What would make you say "this worked"?

After each answer, re-score ambiguity:
```
ambiguity = 1.0 - (intent×0.30 + outcome×0.25 + scope×0.20 + constraints×0.15 + success×0.10)
```

## Challenge Modes (round 2+)

When ambiguity remains high after initial rounds:
- **Round 2+ (Contrarian)**: "What if the opposite is true?"
- **Round 4+ (Simplifier)**: "Can this be done in half the steps?"
- **Round 5+ (Ontologist)**: "What category of problem is this really?"

## Crystallize

When ambiguity ≤ 0.2 or max rounds (12) reached:
1. Write transcript to `.vibe/interviews/`
2. Write execution spec to `.vibe/specs/`
3. Recommend next step: ralplan (if planning needed), ralph (if ready to execute), or more interview

## Handoff

Offer: ralplan (structured planning), ralph (persistent execution), team (parallel execution), or further refinement.
