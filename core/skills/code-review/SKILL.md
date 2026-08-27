---
id: builtin/code-review
name: code-review
description: Structured pre-push review — correctness, security, tests, then style; findings ranked by severity
tags: [review changes, pre-push check, code walkthrough, look over diff,
       代码走查, 过一遍改动, 提交前检查, 看看这次改动,
       diff review, review the patch]
triggers:
  - "look over my changes"
  - "review before push"
  - "帮我看看这次改动"
  - "提交前帮我过一遍"
version: 1.0.0
allowed-tools:
  - Read
  - Bash
  - Grep
intent: Review pending changes (diff) against a structured checklist before pushing, reporting findings by severity
namespace: builtin
type: prompt
---

# Code Review — Structured Pre-Push Walkthrough

> Trigger: "look over my changes before I push" / "帮我看看这次改动有没有问题"

Discipline: **review the diff, not the author.** Every finding cites a
location and states the concrete failure mode it prevents.

## Core Steps

### 1. Establish scope
- `git diff` (staged + unstaged) and `git log` for context.
- One line: what is this change trying to do? (From commit/branch/ask.)

### 2. Correctness pass (P0 — blocks push)
- Logic: off-by-one, inverted conditions, wrong operator, null/None paths
- Data: type mismatches, missing validation at boundaries
- Concurrency: shared state, race windows, lock scope
- Resources: leaks (files, connections), missing cleanup on error paths

### 3. Security pass (P0 — blocks push)
- Injection: SQL/command/shell — parameterized everywhere?
- Secrets: keys, tokens, passwords in diff or logs?
- Paths: user-controlled paths escaping intended root?
- Trust: external input validated before use?

### 4. Tests & contracts (P1)
- Does the change break an existing contract? Which test proves it?
- New behavior covered by a new test (not just manual verification)?
- Public API/schema/config changes flagged for downstream consumers?

### 5. Style & clarity (P2 — never blocks)
- Naming, dead code, comments explaining WHAT instead of WHY.
- Suggest, don't block. Note and move on.

### 6. Report
- Findings grouped: **P0 must-fix / P1 should-fix / P2 nit**, each with
  `file:line` and the failure mode in one sentence.
- End with a verdict: /push-ready/ or /blocked: N×P0/.

## Anti-Patterns

- ❌ Nitpicking style while missing a null-deref two hunks up
- ❌ "LGTM" with no evidence the diff was read end-to-end
- ❌ Asking for changes you cannot justify against a failure mode

## Exit Criteria

- [ ] Diff read end-to-end, scope stated in one line
- [ ] Correctness + security passes done explicitly
- [ ] Findings ranked P0/P1/P2 with file:line citations
- [ ] Verdict stated: push-ready or blocked with count
