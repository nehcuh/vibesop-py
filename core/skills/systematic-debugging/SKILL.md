---
id: builtin/systematic-debugging
name: systematic-debugging
description: Hypothesis-driven root cause debugging — reproduce, isolate, verify, then fix
tags: [debugging workflow, root cause, hypothesis testing, reproduce first,
       isolate variable, 排查思路, 根因分析, 假设验证, 复现问题, 定位根因,
       systematic debugging, fault isolation, 故障排查, broken code,
       why broken, why is this broken, 不对劲, 出问题了, something is wrong,
       bug 排查, troubleshoot, troubleshooting]
triggers:
  - "find the root cause"
  - "why is this broken"
  - "root cause analysis"
  - "定位根因"
  - "排查这个问题"
version: 1.0.0
allowed-tools:
  - Read
  - Bash
  - Edit
  - Grep
intent: Debug a defect by forming and verifying hypotheses about the root cause, instead of patching symptoms
namespace: builtin
type: prompt
---

# Systematic Debugging — Hypothesis-Driven Root Cause Analysis

> Trigger: "this is broken, find the root cause" / "帮我定位根因"

Discipline: **never fix what you cannot reproduce.** A fix without a reproduction
is a hypothesis, not a solution.

## Core Loop (repeat until root cause is proven)

### 1. Reproduce
- Reproduce the failure with the smallest possible input/command.
- If not reproducible: vary environment, input, timing — record what changes.
- Cannot reproduce at all → say so and stop; do not "fix" a ghost.

### 2. Observe
- Capture the actual error/output verbatim (full stack, exit code, logs).
- Note the **expected** vs **actual** behavior in one line each.

### 3. Hypothesize
- State ONE falsifiable hypothesis: "I believe X causes Y because Z."
- Rank hypotheses by prior probability; cheapest-to-test first.

### 4. Isolate
- Design the smallest experiment that kills one hypothesis:
  bisect the input, stub the dependency, add one probe/logging line.
- One variable per experiment. Record the result either way.

### 5. Fix
- Only after a hypothesis is confirmed: write the minimal fix for the cause.
- No drive-by refactors. Adjacent issues go to a separate note.

### 6. Verify
- Re-run the original reproduction → must pass.
- Re-run twice more (flaky check).
- Grep for the same pattern elsewhere in the codebase (sibling bugs).

## Anti-Patterns (reject these explicitly)

- ❌ Patching the symptom because the cause is hard to reach
- ❌ Changing 3 things at once, then declaring victory
- ❌ "Works on my machine" without stating what differs
- ❌ Deleting the failing test / widening an assertion to make it green

## Exit Criteria

- [ ] Reproduction script/command exists and failed before the fix
- [ ] Root cause stated in one sentence with evidence
- [ ] Fix is minimal and touches only the cause
- [ ] Reproduction passes after the fix; re-run 3x green
