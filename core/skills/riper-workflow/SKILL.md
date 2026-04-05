---
name: riper-workflow
description: Structured 5-phase development workflow - Research, Innovate, Plan, Execute, Review
version: 1.0.0
commands:
  - riper-research
  - riper-innovate
  - riper-plan
  - riper-execute
  - riper-review
  - riper-status
---

# RIPER Workflow

A structured 5-phase workflow that prevents the most common AI-assisted development failure: jumping straight to implementation without sufficient understanding.

## Phases

```
Research → Innovate → Plan → Execute → Review
```

Each phase has a clear goal and exit criteria. You must complete a phase before moving to the next.

---

## Phase 1: Research

**Goal**: Understand the problem space completely before proposing solutions.

**Activities**:
- Read all relevant files (don't guess at structure)
- Identify constraints, dependencies, and existing patterns
- Clarify ambiguous requirements with the user
- Map the blast radius of potential changes

**Exit criteria**: You can answer "what exists, what is broken, and why" without looking at the code again.

**Trigger**: Start every non-trivial task here. Say: `[RIPER: Research]`

---

## Phase 2: Innovate

**Goal**: Generate multiple solution approaches before committing to one.

**Activities**:
- Propose 2-3 distinct approaches with trade-offs
- Consider edge cases and failure modes for each
- Identify the simplest approach that satisfies requirements
- Do NOT write implementation code yet

**Exit criteria**: User has selected or approved an approach.

**Trigger**: Say: `[RIPER: Innovate]`

---

## Phase 3: Plan

**Goal**: Create a precise, step-by-step implementation plan.

**Activities**:
- List every file that will be created or modified
- Define the exact changes for each file
- Identify test cases that must pass
- Estimate risk for each step

**Exit criteria**: Plan is specific enough that a different engineer could implement it without asking questions.

**Trigger**: Say: `[RIPER: Plan]`

---

## Phase 4: Execute

**Goal**: Implement exactly what was planned — no scope creep.

**Rules**:
- Follow the plan from Phase 3 step by step
- If you discover the plan is wrong, STOP and return to Plan
- Do not add "nice to have" improvements
- Commit after each logical unit of work

**Exit criteria**: All planned changes are implemented and tests pass.

**Trigger**: Say: `[RIPER: Execute]`

---

## Phase 5: Review

**Goal**: Verify the implementation is correct and complete.

**Activities**:
- Run all tests and confirm they pass
- Re-read the original requirements and verify each is met
- Check for regressions in adjacent functionality
- Update documentation if behaviour changed

**Exit criteria**: You can say "this is done" with confidence.

**Trigger**: Say: `[RIPER: Review]`

---

## Quick reference

| Phase    | Question to answer                        | Output              |
|----------|-------------------------------------------|---------------------|
| Research | What exists and what is broken?           | Understanding       |
| Innovate | What are the possible solutions?          | Approach decision   |
| Plan     | Exactly what will change?                 | Step-by-step plan   |
| Execute  | Is the plan implemented?                  | Working code        |
| Review   | Is it correct and complete?               | Confidence to ship  |

## Anti-patterns this workflow prevents

- **Hallucinated structure**: Skipping Research leads to editing files that don't exist
- **Premature commitment**: Skipping Innovate locks you into the first idea
- **Scope creep**: Skipping Plan leads to "while I'm here" changes
- **Broken tests**: Skipping Review ships regressions
