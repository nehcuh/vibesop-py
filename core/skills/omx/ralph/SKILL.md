---
id: omx/ralph
name: Ralph
description: Persistent completion loop with mandatory deslop pass and tiered architect verification.
intent: execution
namespace: omx
version: 1.0.0
type: prompt
trigger_when: asked to implement something with guaranteed completion, never give up
---

# Ralph — Persistent Completion Loop

"Never give up" execution engine. Loops until the work is truly done.

## Pre-context

1. Load `.vibe/context/` snapshot
2. If ambiguity > 0.3, run deep-interview first
3. Load any existing state from `.vibe/state/ralph/`

## Loop (max 10 iterations)

Each iteration:

1. **Review Progress**: What's done? What's left? Continue from last state.
2. **Delegate**: Split remaining work into independent tasks. Run in parallel with appropriate tiers:
   - LOW: Simple, well-defined tasks
   - STANDARD: Normal complexity
   - THOROUGH: Critical/complex tasks needing extra care
3. **Verify**: Fresh evidence for every claim:
   - Run tests → must pass
   - Run build → must succeed
   - Run lint → must be clean
4. **Architect Verification** (tiered by change size):
   - < 50 lines: Self-review
   - 50-200 lines: Architecture check
   - > 200 lines: Full architect review
5. **Mandatory Deslop Pass**: Review ALL changed files for:
   - AI slop patterns (over-explanation, redundant comments, unnecessary abstractions)
   - Remove anything that doesn't serve the user's goal
6. **Regression Re-verification**: Run tests/build/lint again after deslop

## Exit Criteria

- **Approve**: All verification passes, user confirms satisfaction → clean exit
- **Reject**: Any verification fails or user rejects → fix → re-verify → loop

## State Persistence

Save state to `.vibe/state/ralph/{scope}/state.json` after each iteration:
```json
{
  "iteration": 3,
  "max_iterations": 10,
  "current_phase": "verify",
  "context_snapshot_path": ".vibe/context/snapshot.json",
  "linked_ultrawork": false,
  "linked_ecomode": false
}
```
