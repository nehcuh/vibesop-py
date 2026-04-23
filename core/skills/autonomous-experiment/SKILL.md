---
id: builtin/autonomous-experiment
name: autonomous-experiment
description: Autonomous experiment loop with predict-attribute cycle and multi-dimensional evaluation
tags: [experiment, optimize, iteration, benchmark, evaluate, 实验, 优化, 迭代]
version: "1.0.0"
commands:
  - experiment
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
user-invocable: true
intent: experimentation
namespace: builtin
type: prompt
---

# Autonomous Experiment

Run autonomous optimization experiments with predict-attribute cycles and multi-dimensional rubric evaluation.

## Prerequisites

- `.vibe/experiment.yaml` must exist in the project root
- Git repository must be initialized

## Core Loop

### Phase 1: Initialization

1. Read `.vibe/experiment.yaml` for domain definition (objective, scope, evaluator, constraints).
2. Read `.experiment/beliefs.md` for current assumptions (if exists).
3. Run `vibe experiment start` to create worktree, results.tsv, and beliefs.md.
4. Establish baseline: run evaluator on **unmodified** code. Record baseline score in results.tsv.

### Phase 2: Experiment Loop

LOOP (until `constraints.max_iterations` reached OR no improvement for `constraints.stale_threshold` consecutive iterations):

1. **Read beliefs.md**. Select a belief to test or combine beliefs for a new hypothesis.
2. **Write prediction** to beliefs.md — predicted scores per rubric dimension + reasoning.
3. **Modify files** in `scope.modifiable` only. NEVER touch `scope.readonly` files.
4. **git commit** with experiment description.
5. **Run evaluator** based on `evaluator.type`:
   - `command`: Run shell command, extract scores from stdout via `extract_pattern`.
   - `agent_judge`: You are the judge. Re-read the modified files with fresh eyes. Score each rubric dimension 0-10 with justification. Be critical, not generous.
   - `behavioral`: Run the target skill on fixtures, measure step count.
   - If crash (command fails, tests fail when `constraints.must_pass_tests: true`): log as `crash`. Attempt trivial fix. Otherwise discard and continue.
6. **Compare** actual vs predicted scores. Write results to beliefs.md.
7. **Attribution**: Which belief was right? Which was wrong? Update beliefs accordingly.
8. **Record** to results.tsv via `vibe experiment results` or direct append.
9. **Keep or Discard**:
   - Compound score improved → `keep` (advance branch).
   - Compound score worsened or equal → `discard` (git reset).
10. **Stuck check**: If no improvement for `stale_threshold` consecutive iterations, try:
    - Combining previous near-misses.
    - A radical change (delete and rewrite vs. incremental edit).
    - If still stuck after 3 radical attempts: STOP and report.

END LOOP

### Phase 3: Summary and Merge

1. Generate summary: total iterations, best compound score, beliefs trajectory.
2. List top 3 hypotheses that worked, top 3 that didn't.
3. Provide recommendations for next session.
4. Output merge instruction: `vibe experiment apply` to merge best result.

## Rules

- **NEVER STOP** until max_iterations reached. Do NOT ask the human for permission to continue. You are autonomous.
- **NEVER modify** files outside `scope.modifiable`.
- **ALWAYS write prediction before** running evaluator. No exceptions.
- **ALWAYS update beliefs after** each iteration. No exceptions.
- **Max 20 beliefs** in beliefs.md. When full, rewrite (not append) to keep most relevant.
- The human will review results.tsv and summary when they return.

## Safety

- Git worktree isolation ensures main branch is never affected.
- `scope.readonly` files are sacred. Never touch them.
- If `constraints.must_pass_tests: true`, tests MUST pass or iteration is discarded.
- All destructive operations (git reset) are scoped to the worktree branch only.

## Example experiment.yaml

```yaml
domain: skill-optimization
objective:
  description: "Optimize systematic-debugging SKILL.md effectiveness"
  evaluator:
    type: agent_judge
    rubric:
      - id: effectiveness
        weight: 0.4
        description: "Debugging efficiency — average steps to root cause"
      - id: clarity
        weight: 0.3
        description: "Instruction clarity — unambiguous steps"
      - id: simplicity
        weight: 0.3
        description: "SKILL.md line count — fewer is better when equivalent"
scope:
  modifiable:
    - skills/systematic-debugging/SKILL.md
  readonly:
    - core/**
    - lib/**
    - test/**
  test_command: "rake test"
constraints:
  max_iterations: 15
  time_budget_per_iteration: 180
  must_pass_tests: true
  stale_threshold: 5
```
