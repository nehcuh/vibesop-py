# ADR-003: Plan Completion Criteria

> **Date**: 2026-05-04
> **Status**: Active
> **Context**: Multiple prior plans (v50-v55, v6) marked "Completed" with unchecked acceptance criteria and contradictory metrics. This ADR establishes hard gates for plan completion.

## Decision

A plan may only be marked `COMPLETED` when ALL of the following are satisfied:

1. **Every acceptance criterion** `[ ]` is changed to `[x]`
2. **At least 1 integration test** verifies the delivered feature
3. **Code coverage** has not decreased from the plan's start baseline
4. **basedpyright** reports 0 errors (warnings allowed but tracked)
5. **All affected documentation** version numbers are consistent

## Status Labels

| Label | Meaning |
|-------|---------|
| `COMPLETED` | All 5 hard gates passed |
| `PARTIAL X%` | Some gates passed, percentage indicates completion |
| `PLANNED` | Not started |
| `ABANDONED` | Explicitly dropped, with reason |

## Audit of Prior Plans

| Plan | Prior Claim | Corrected Status |
|------|-------------|------------------|
| v50 | (unmarked) | PARTIAL 80% |
| v51 | "Completed" | PARTIAL 70% |
| v52 | "all features verified" | PARTIAL 85% |
| v53 | "Completed" | PARTIAL 60% |
| v55 | (unmarked) | PARTIAL 50% |
| v6 | (unmarked) | PARTIAL 20% |

## Coverage Baseline

As of 2026-05-04, the authoritative coverage baseline is:

```bash
uv run pytest tests/core tests/unit tests/security tests/hooks \
  --cov=src/vibesop --cov-report=term-missing --cov-branch 2>&1 | tail -5
```

Result to be recorded after first full coverage run.

## Consequences

- No plan may claim completion without objective evidence
- Coverage regressions block plan completion
- Version inconsistencies block plan completion
- All future plans (v6.x+) must use these criteria
