---
id: builtin/test-generation
name: test-generation
description: Write focused unit tests — golden path first, then edge cases, deterministic and isolated
tags: [unit test, test cases, test coverage, golden path,
       edge cases, deterministic tests, 单元测试, 写用例, 补测试,
       测试用例, 边界情况, 表驱动测试, 单元用例, 补一组用例]
triggers:
  - "write unit tests"
  - "add tests for this"
  - "写单元测试"
  - "补充测试用例"
  - "补一组单元用例"
version: 1.0.0
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
intent: Generate focused, deterministic unit tests for a target function or module, golden path before edge cases
namespace: builtin
type: prompt
---

# Test Generation — Golden Path, Then Edges

> Trigger: "write unit tests for this module" / "给这个函数写单元测试"

Discipline: **a test that can't fail is decoration.** Every test must be able
to fail for a specific, nameable regression.

## Core Steps

### 1. Read the target before writing anything
- Identify the contract: inputs, outputs, side effects, error paths.
- Note existing test conventions in the repo (naming, fixtures, markers)
  and follow them — consistency beats creativity.

### 2. Golden path first (1-2 tests)
- The single most common input → expected output.
- If this doesn't pass, the target is broken or misread — stop and report.

### 3. Edge cases (ranked by blast radius)
- Boundary values: empty, one, many; zero/negative; unicode
- Error paths: invalid input, missing resource, timeout
- State transitions and idempotency (call twice)

### 4. Determinism rules
- No `random` without a fixed seed; no wall-clock time without injection.
- No network, no filesystem outside tmp dirs, no cross-test ordering.
- Fake doubles only at true boundaries (DB, HTTP); mock sparingly.

### 5. Run and verify
- Run the new tests: all green, and reasonably fast.
- **Mutation check**: break the target on purpose → at least one test must
  go red. Revert. This proves the tests can fail.

## Anti-Patterns

- ❌ Testing the mock instead of the target
- ❌ One giant test asserting 20 things (first failure hides the rest)
- ❌ Snapshot testing logic that has no stable contract
- ❌ Skipping the failing case with a TODO instead of reporting it

## Exit Criteria

- [ ] Golden path covered and green
- [ ] ≥3 edge/error cases or a stated reason the target has fewer
- [ ] Tests deterministic (re-run 3x, no flake) and isolated
- [ ] Mutation check performed (tests can fail)
